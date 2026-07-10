"""
实体关系提取模块 — 从文本中提取实体和关系

从 advanced.py 中抽离，复用现有 ENTITY_EXTRACT_PROMPT，
增加批量处理和查询实体提取能力。

使用场景：
  1. 索引阶段：batch_extract_entities() — 批量提取写入 Neo4j
  2. 查询阶段：extract_query_entities() — 从问题中提取关键实体名
  3. 上下文构建：build_graph_context() — 查询邻域并格式化为文本
"""

import json
import logging
import re
from typing import List, Optional, Tuple

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate

from app.config import settings
from app.rag.llm_factory import get_llm

logger = logging.getLogger(__name__)

# 实体提取 Prompt（复用 advanced.py 中的定义）
ENTITY_EXTRACT_PROMPT = ChatPromptTemplate.from_template("""\
从以下文本中提取关键实体及其关系。
文本：
{text}

请输出 JSON 格式的实体关系列表：
[
  {{"entity": "实体名", "type": "人物/公司/产品/制度/时间/数值/地点/其他", "description": "简短描述（可选）", "relations": [{{"target": "关联实体", "relation": "关系描述"}}]}}
]

只输出 JSON 数组。若没有实体，输出 []。""")

# 查询实体提取 Prompt（轻量，用于从问题中提取）
QUERY_ENTITY_PROMPT = ChatPromptTemplate.from_template("""\
从以下问题中提取关键实体名称（名词性短语，如人名、公司名、产品名、地名等）。
问题：{question}

请输出 JSON 数组：
["实体1", "实体2", ...]

只输出 JSON 数组。若没有实体，输出 []。""")


def _extract_entities_from_text(text: str) -> List[dict]:
    """
    调用 LLM 从文本中提取实体关系列表

    Returns:
        [
            {"entity": "华为", "type": "公司", "description": "...",
             "relations": [{"target": "鸿蒙OS", "relation": "开发"}]},
            ...
        ]
    """
    if not settings.is_llm_available:
        return []

    llm = get_llm(temperature=0, timeout=15)
    chain = ENTITY_EXTRACT_PROMPT | llm
    try:
        result = chain.invoke({"text": text[:3000]})  # 限制输入长度
        content = result.content.strip()

        # 提取 JSON 数组
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        if not json_match:
            logger.warning("实体提取: 未找到 JSON 输出")
            return []

        entities = json.loads(json_match.group())
        if not isinstance(entities, list):
            return []
        return entities
    except Exception as e:
        logger.debug(f"实体提取失败: {e}")
        return []


def extract_query_entities(question: str) -> List[str]:
    """
    从用户问题中提取关键实体名称

    用于查询阶段在 Neo4j 中匹配实体。
    不使用 LLM 时降级为简单分词规则。

    Returns:
        ["华为", "鸿蒙OS"]
    """
    if not settings.is_llm_available:
        # 降级：简单提取引号内容和中文名词
        quoted = re.findall(r'["""]([^"""]+)["""]', question)
        if quoted:
            return quoted
        # 简单启发式：提取 2-6 个中文字符的连续词
        tokens = re.findall(r'[\u4e00-\u9fff]{2,8}', question)
        # 过滤常见停用词
        stop_words = {"什么", "如何", "为什么", "怎么", "哪个", "哪些", "这个", "那个", "这样"}
        return [t for t in tokens if t not in stop_words][:5]

    llm = get_llm(temperature=0, timeout=10)
    chain = QUERY_ENTITY_PROMPT | llm
    try:
        result = chain.invoke({"question": question})
        content = result.content.strip()
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        if json_match:
            entities = json.loads(json_match.group())
            if isinstance(entities, list):
                return [e.strip() for e in entities if isinstance(e, str) and e.strip()]
        return []
    except Exception as e:
        logger.debug(f"查询实体提取失败: {e}")
        return []


def batch_extract_entities(
    docs: List[Document],
    store: "Neo4jStore",  # type: ignore
    batch_size: int = 20,
) -> Tuple[int, int]:
    """
    批量提取实体并写入 Neo4j

    直接委托给 store.batch_extract_and_store

    Returns:
        (entity_count, relationship_count)
    """
    return store.batch_extract_and_store(docs, batch_size=batch_size)


def build_graph_context(
    entity_names: List[str],
    store: "Neo4jStore",  # type: ignore
    depth: int = 2,
) -> str:
    """
    查询实体邻域并格式化为 LLM 友好的文本上下文

    Args:
        entity_names: 从问题中提取的实体名称列表
        store: Neo4jStore 实例
        depth: BFS 遍历深度

    Returns:
        格式化的图谱上下文文本，用于注入 LLM prompt
    """
    all_subgraphs = []

    for entity_name in entity_names[:3]:  # 最多 3 个实体
        neighborhood = store.get_entity_neighborhood(entity_name, depth=depth, limit=30)
        if neighborhood:
            all_subgraphs.append({
                "root": entity_name,
                "neighbors": neighborhood,
            })

    if not all_subgraphs:
        return ""

    lines = ["## 实体关系图（来自知识图谱）"]
    for subgraph in all_subgraphs:
        lines.append(f"\n### 中心实体: {subgraph['root']}")
        for neighbor in subgraph["neighbors"]:
            entity = neighbor.get("entity", "?")
            etype = neighbor.get("type", "")
            type_tag = f" ({etype})" if etype and etype != "其他" else ""
            lines.append(f"- {entity}{type_tag}")
            for rel in neighbor.get("relations", []):
                target = rel.get("target", "?")
                rel_desc = rel.get("relation", "?")
                lines.append(f"   └─ [{rel_desc}] → {target}")

    return "\n".join(lines)
