"""
数据对话引擎 — LLM 驱动的自然语言数据分析

上传 Excel/CSV → 自然语言提问 → LLM 生成 pandas 代码 → 安全执行 → 图表+解读
"""

import os
import re
import json
import logging
import traceback
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
import pandas as pd
import numpy as np

from app.config import settings
from app.tools.base import register_tool
from app.tools.registry import validate_file_path

logger = logging.getLogger(__name__)

# ====== 安全沙箱 ======

SAFE_BUILTINS = {
    "len": len, "range": range, "list": list, "dict": dict, "tuple": tuple,
    "str": str, "int": int, "float": float, "bool": bool, "complex": complex,
    "print": print, "zip": zip, "enumerate": enumerate,
    "sorted": sorted, "min": min, "max": max, "sum": sum, "abs": abs, "round": round,
    "set": set, "frozenset": frozenset, "reversed": reversed,
    "True": True, "False": False, "None": None,
    "type": type, "isinstance": isinstance, "hasattr": hasattr, "getattr": getattr,
    "map": map, "filter": filter, "any": any, "all": all,
    "format": format, "divmod": divmod, "pow": pow,
    "slice": slice, "KeyError": KeyError, "ValueError": ValueError,
    "TypeError": TypeError, "IndexError": IndexError,
}

FORBIDDEN_PATTERNS = [
    r'__', r'import\s', r'from\s+\w+\s+import',
    r'open\s*\(', r'eval\s*\(', r'exec\s*\(',
    r'os\.', r'sys\.', r'subprocess', r'shutil',
    r'globals\s*\(', r'locals\s*\(', r'getattr\s*\(.*__',
    r'compile\s*\(', r'breakpoint\s*\(', r'input\s*\(',
    r'\._', r'\.__', r'ctypes', r'builtins',
    r'write\s*\(', r'\.save\s*\(', r'\.to_excel', r'\.to_csv',
    r'requests?\.', r'urllib', r'http', r'socket',
    r'multiprocessing', r'threading', r'signal',
    r'os\.system', r'os\.popen', r'os\.spawn',
    # 禁止图表相关操作 (图表由前端渲染, 不需要后端生成图片)
    r'matplotlib', r'plt\.', r'base64', r'BytesIO', r'savefig',
    r'pyplot', r'figure\s*\(', r'imshow', r'imread',
]


def _sanitize_code(code: str) -> str:
    """检查代码安全性，抛出异常如果不安全"""
    code_lower = code.lower()
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, code_lower):
            raise ValueError(f"代码包含禁止的操作: {pattern}")

    # 检查代码是否包含 __ 双下划线访问
    if re.search(r'__\w+', code) or re.search(r'\w+__', code):
        raise ValueError("代码包含禁止的双下划线访问")

    return code


def _execute_sandbox(code: str, df: pd.DataFrame) -> dict:
    """
    安全沙箱执行 pandas 代码。

    Returns:
        {"result": any, "type": "dataframe"|"series"|"scalar"|"error", "error": str|None}
    """
    _sanitize_code(code)

    # 构建受限命名空间
    namespace = {
        "__builtins__": SAFE_BUILTINS,
        "pd": pd,
        "np": np,
        "df": df,
    }

    try:
        # 捕获最后一行表达式的值
        lines = code.strip().split("\n")
        last_line = lines[-1].strip()

        # 如果最后一行是表达式（不是赋值/控制流），包装它来捕获结果
        if not last_line.startswith(("if ", "for ", "while ", "def ", "class ", "try:", "except", "else:", "elif ", "with ")) and "=" not in last_line.split("(")[0]:
            exec_lines = "\n".join(lines[:-1]) if len(lines) > 1 else ""
            exec_lines += f"\n__result__ = {last_line}"
        else:
            exec_lines = code
            exec_lines += "\n__result__ = None"

        exec(exec_lines, namespace)

        result = namespace.get("__result__", None)

        if isinstance(result, pd.DataFrame):
            # 截断大结果
            if len(result) > 100:
                result = result.head(100)
            return {
                "type": "dataframe",
                "columns": result.columns.tolist(),
                "rows": result.fillna("").values.tolist()[:100],
                "shape": [len(result), len(result.columns)],
            }
        elif isinstance(result, pd.Series):
            data = result.head(50).to_dict()
            return {"type": "series", "data": data, "name": str(result.name)}
        elif isinstance(result, (int, float, np.integer, np.floating)):
            return {"type": "scalar", "value": float(result) if isinstance(result, (float, np.floating)) else int(result)}
        elif isinstance(result, str):
            return {"type": "scalar", "value": result}
        elif result is None:
            return {"type": "scalar", "value": "执行完成 (无返回值)"}
        else:
            return {"type": "scalar", "value": str(result)}

    except Exception as e:
        return {"type": "error", "error": f"{type(e).__name__}: {e}"}


# ====== LLM 系统提示 ======

DATA_CHAT_SYSTEM = """你是一个数据分析专家。用户上传了数据文件，你需要用 pandas 代码回答他们的问题。

## 数据信息
{df_info}

## 规则
1. 只写 pandas/numpy 代码，不要写 markdown 代码块标记
2. 代码最后一行必须是表达式（结果会自动展示给用户）
3. 如果需要画图，用 SPEC:CHART:{{"type":"bar","x":"列名","y":"列名","title":"标题","data":[{{...}}]}} 格式，不要在代码中生成 base64 图片
4. **禁止**使用 matplotlib、plt、base64、BytesIO、savefig，图表由前端渲染
5. 代码要简洁、健壮，处理可能的 NaN
6. 用中文回答，先给文字解读，再用 SPEC:CODE: 标记代码

## 输出格式
[一句话文字解读]

SPEC:CODE:
你的pandas代码（最后一行是结果表达式）
"""


def _build_df_info(df: pd.DataFrame) -> str:
    """构建 DataFrame 的摘要信息给 LLM"""
    lines = [f"- 行数: {len(df)}, 列数: {len(df.columns)}"]
    lines.append("- 列名及类型:")
    for col in df.columns:
        dtype = str(df[col].dtype)
        sample = df[col].dropna().head(3).tolist()
        sample_str = ", ".join(str(x)[:50] for x in sample)
        nulls = df[col].isna().sum()
        info = f"  {col} ({dtype})"
        if sample_str:
            info += f" 样例: [{sample_str}]"
        if nulls > 0:
            info += f" 缺失: {nulls}"
        lines.append(info)
    return "\n".join(lines)


def _parse_llm_response(response: str) -> dict:
    """解析 LLM 响应，提取文字解读 + 代码 + 图表配置"""
    result = {"answer": "", "code": "", "chart": None}

    # 提取 SPEC:CODE: 标记
    code_match = re.search(r'SPEC:CODE:\s*\n?(.*?)(?:SPEC:CHART:|$)', response, re.DOTALL)
    if code_match:
        result["code"] = code_match.group(1).strip()
        result["answer"] = response[:code_match.start()].strip()
    else:
        result["answer"] = response.strip()

    # 提取 SPEC:CHART: 标记
    chart_match = re.search(r'SPEC:CHART:\s*(\{.*?\})', response, re.DOTALL)
    if chart_match:
        try:
            result["chart"] = json.loads(chart_match.group(1))
        except json.JSONDecodeError:
            logger.warning(f"图表配置解析失败: {chart_match.group(1)}")

    return result


# ====== LLM 调用 ======

def _get_llm():
    """获取 LLM 实例"""
    return ChatOpenAI(
        model=settings.LLM_MODEL,
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        temperature=0,
        timeout=settings.LLM_TIMEOUT,
    )


def analyze_with_llm(file_path: str, question: str) -> dict:
    """
    主函数: LLM 驱动的数据分析对话。

    Args:
        file_path: Excel/CSV 文件路径
        question: 用户自然语言问题

    Returns:
        {"answer": str, "code": str, "result": dict, "chart": dict|null}
    """
    # 1. 安全路径验证 + 加载数据
    safe_path = validate_file_path(file_path)
    if not os.path.exists(safe_path):
        return {"answer": f"文件不存在: {safe_path}", "code": "", "result": None, "chart": None}

    ext = os.path.splitext(safe_path)[1].lower()
    try:
        if ext in (".xlsx", ".xls"):
            df = pd.read_excel(safe_path)
        elif ext == ".csv":
            for enc in ["utf-8", "gbk", "gb2312", "latin-1"]:
                try:
                    df = pd.read_csv(safe_path, encoding=enc)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                return {"answer": "无法识别 CSV 编码", "code": "", "result": None, "chart": None}
        else:
            return {"answer": f"不支持的文件格式: {ext}", "code": "", "result": None, "chart": None}
    except Exception as e:
        return {"answer": f"文件读取失败: {e}", "code": "", "result": None, "chart": None}

    # 2. 构建提示
    df_info = _build_df_info(df)
    system_prompt = DATA_CHAT_SYSTEM.format(df_info=df_info)

    # 3. LLM 生成代码
    try:
        llm = _get_llm()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ]
        response = llm.invoke([(msg["role"], msg["content"]) for msg in messages])
        llm_text = response.content
    except Exception as e:
        logger.error(f"LLM 调用失败: {e}")
        return {"answer": f"LLM 调用失败: {e}", "code": "", "result": None, "chart": None}

    # 4. 解析响应
    parsed = _parse_llm_response(llm_text)

    # 5. 执行代码
    result = None
    if parsed["code"]:
        try:
            result = _execute_sandbox(parsed["code"], df)
        except ValueError as e:
            result = {"type": "error", "error": f"安全检查: {e}"}

    # 6. 如果没有显式图表配置，从代码结果推断
    chart = parsed.get("chart")
    if not chart and result and result.get("type") == "dataframe":
        # 自动生成一个简单的图表建议
        df_result = pd.DataFrame(result["rows"], columns=result["columns"])
        numeric_cols = df_result.select_dtypes(include=["number"]).columns.tolist()
        if len(numeric_cols) >= 1:
            chart = {
                "type": "bar",
                "x": df_result.columns[0] if len(df_result.columns) > 0 else numeric_cols[0],
                "y": numeric_cols[0],
                "title": f"{numeric_cols[0]} 分布",
            }

    return {
        "answer": parsed["answer"],
        "code": parsed["code"],
        "result": result,
        "chart": chart,
    }


# ====== LangChain 工具包装 ======

class DataChatInput(BaseModel):
    file_path: str = Field(description="Excel/CSV 文件路径")
    question: str = Field(default="", description="自然语言数据分析问题")
    query: str = Field(default="", description="问题的别名 (兼容 LLM 生成)")


@register_tool
class DataConversationTool(BaseTool):
    """LLM 驱动的自然语言数据分析对话"""
    name: str = "data_conversation"
    description: str = (
        "上传数据文件后，用自然语言进行数据分析对话。"
        "支持：统计、筛选、排序、分组、趋势分析、图表生成。"
    )
    args_schema: type[BaseModel] = DataChatInput

    def _run(self, file_path: str, question: str = "", query: str = "") -> str:
        # 兼容 LLM 可能传 query 或 question
        q = question or query or ""
        result = analyze_with_llm(file_path, q)
        answer = result["answer"]
        if result.get("code"):
            answer += f"\n\n📝 执行代码:\n```python\n{result['code']}\n```"
        if result.get("result") and result["result"].get("type") != "error":
            r = result["result"]
            if r["type"] == "scalar":
                val_str = str(r['value'])
                # 截断 base64 图片数据，防止撑爆对话
                if 'base64' in val_str and len(val_str) > 500:
                    val_str = val_str[:200] + f"\n... [base64数据已截断, 原始长度{len(val_str)}字符]"
                if len(val_str) > 2000:
                    val_str = val_str[:1000] + f"\n... [已截断, 原始长度{len(val_str)}字符]"
                answer += f"\n\n📊 结果: {val_str}"
            elif r["type"] == "dataframe":
                answer += f"\n\n📊 结果表格 ({r.get('shape', [0,0])[0]} 行 × {r.get('shape', [0,0])[1]} 列)"
            elif r["type"] == "series":
                answer += f"\n\n📊 结果序列: {json.dumps(r.get('data', {}), ensure_ascii=False)}"
        elif result.get("result") and result["result"].get("type") == "error":
            answer += f"\n\n⚠️ 执行错误: {result['result']['error']}"
        if result.get("chart"):
            answer += f"\n\n📈 图表已生成: {json.dumps(result['chart'], ensure_ascii=False)}"
        return answer
