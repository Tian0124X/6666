"""
2026 进阶 RAG 模式 — Adaptive RAG + Agentic RAG + GraphRAG 轻量版

Adaptive RAG:   按问题复杂度自动切换检索策略（3 级）
Agentic RAG:    检索→生成→幻觉检测→重检索→重生成 自验证循环
GraphRAG Lite:  实体关系提取 + 多跳链式推理（无外部图数据库）
"""

import logging
from typing import List, Tuple, Literal
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from app.config import settings
from app.rag.retriever import _hybrid_search, _llm_rerank, _format_context, RAG_SYSTEM_PROMPT
from app.rag.cache import query_cache

logger = logging.getLogger(__name__)


# ============================================================
# 1. Adaptive RAG — 三级自适应检索策略
# ============================================================

ADAPTIVE_CLASSIFY_PROMPT = ChatPromptTemplate.from_template("""\
分析以下用户问题的复杂度，输出一个级别数字。

级别定义：
- 0 (direct): 问候、闲聊、简单事实性问题（不需要检索资料即可回答）
- 1 (single): 需要查一次知识库的单步问题（如 "年假有几天？""报销流程是什么？"）
- 2 (multi): 需要多步推理、对比分析、跨文档综合的复杂问题（如 "对比A产品和B产品的差异""分析近三年的业绩趋势"）

用户问题：{question}

只输出一个数字：0、1 或 2。""")


def _classify_complexity(question: str) -> int:
    """LLM 分类问题复杂度（0/1/2），失败则默认 1"""
    if not settings.LLM_API_KEY or settings.LLM_API_KEY.startswith("sk-your-"):
        # 本地规则降级
        simple_patterns = ["你好", "谢谢", "再见", "帮助", "hello", "hi"]
        if any(p in question.lower() for p in simple_patterns) and len(question) < 20:
            return 0
        multi_patterns = ["对比", "比较", "分析", "趋势", "差异", "为什么", "原因"]
        if any(p in question for p in multi_patterns):
            return 2
        return 1

    try:
        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            temperature=0,
            timeout=10,
        )
        chain = ADAPTIVE_CLASSIFY_PROMPT | llm
        result = chain.invoke({"question": question})
        level = int(result.content.strip()[0])
        return max(0, min(2, level))  # clamp 0-2
    except Exception:
        return 1


# ============================================================
# 2. Agentic RAG — 自验证检索循环
# ============================================================

VERIFY_PROMPT = ChatPromptTemplate.from_template("""\
你是回答质量审查员。检查以下回答是否严格基于提供的参考资料，是否存在幻觉（编造了上下文中不存在的信息）。

参考资料：
{context}

生成回答：
{answer}

请判断：
1. 回答中是否有任何信息在参考资料中找不到？（是/否）
2. 如果"是"，列出编造的具体内容。
3. 回答质量评分（1-10）。

输出格式：
HALLUCINATION: <是/否>
DETAILS: <编造内容，无则写"无">
SCORE: <1-10>""")


async def _agentic_retrieve_and_generate(
    question: str,
    max_iterations: int = 3,
) -> dict:
    """
    Agentic RAG 自验证循环：

    1. 检索 → 2. 生成 → 3. 幻觉检测 → 4a. 通过→返回 或 4b. 失败→重检索→重生成

    最多 3 轮，每轮用不同的检索策略（增加多样性）。
    """
    # 1. 尝试缓存
    cached = query_cache.get(question)
    if cached:
        logger.info("Agentic RAG: 缓存命中")
        return cached

    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        temperature=0.1,
        timeout=settings.LLM_TIMEOUT,
    )

    all_retrieved_docs = []
    best_answer = ""
    best_score = 0

    for iteration in range(1, max_iterations + 1):
        logger.info(f"Agentic RAG 第 {iteration}/{max_iterations} 轮")

        # 每轮调整检索策略：第1轮正常，后续轮扩展关键词
        search_query = question
        if iteration == 2:
            search_query = f"{question} 详细说明 具体内容"
        elif iteration == 3:
            search_query = f"{question} 数据 指标 规定 条款"

        # 检索
        docs = await _hybrid_search(search_query, k=15)
        docs = _llm_rerank(question, docs, top_n=5)

        for doc in docs:
            if doc.page_content[:100] not in [d.page_content[:100] for d in all_retrieved_docs]:
                all_retrieved_docs.append(doc)

        if not docs:
            continue

        # 生成
        context = _format_context(docs)
        gen_prompt = ChatPromptTemplate.from_messages([
            ("system", RAG_SYSTEM_PROMPT),
            ("user", "{question}"),
        ])
        chain = gen_prompt | llm
        answer = chain.invoke({"context": context, "question": question}).content

        # 幻觉检测
        verify_chain = VERIFY_PROMPT | llm
        verification = verify_chain.invoke({
            "context": context,
            "answer": answer,
        }).content

        # 解析验证结果
        import re
        hallucinated = "是" in re.search(r"HALLUCINATION:\s*(.+)", verification).group(1) if re.search(r"HALLUCINATION:\s*(.+)", verification) else True
        score_match = re.search(r"SCORE:\s*(\d+)", verification)
        score = int(score_match.group(1)) if score_match else 5

        logger.info(f"  幻觉检测: {'有幻觉' if hallucinated else '无幻觉'}, 评分: {score}")

        # 如果分数更高，保存为最佳回答
        if score > best_score:
            best_answer = answer
            best_score = score

        # 如果没有幻觉且分数 >= 7，直接返回
        if not hallucinated and score >= 7:
            break

    # 构建来源
    sources = []
    seen = set()
    for doc in all_retrieved_docs:
        fn = doc.metadata.get("filename", "未知")
        if fn not in seen:
            seen.add(fn)
            sources.append({
                "filename": fn,
                "page": doc.metadata.get("page"),
                "excerpt": doc.page_content[:200],
            })

    result = {
        "answer": best_answer or "抱歉，经过多轮检索仍无法给出可靠回答。",
        "sources": sources,
        "iterations": iteration,
        "verification_score": best_score,
        "mode": "agentic",
    }

    # 缓存结果
    query_cache.set(question, result)
    return result


# ============================================================
# 3. GraphRAG Lite — 实体关系提取 + 多跳推理
# ============================================================

ENTITY_EXTRACT_PROMPT = ChatPromptTemplate.from_template("""\
从以下文本中提取关键实体及其关系。

文本：
{text}

请输出 JSON 格式的实体关系列表：
[
  {{"entity": "实体名", "type": "人物/公司/产品/制度/时间/数值", "relations": [{{"target": "关联实体", "relation": "关系描述"}}]}}
]

只输出 JSON 数组。""")


def _extract_entities(docs: List[Document]) -> List[dict]:
    """从检索文档中提取实体关系图（轻量版，无需 Neo4j）"""
    if not settings.LLM_API_KEY or settings.LLM_API_KEY.startswith("sk-your-"):
        return []

    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        temperature=0,
        timeout=30,
    )

    all_entities = []
    # 对每个文档提取实体
    for doc in docs[:3]:  # 限制 3 个文档避免开销过大
        try:
            chain = ENTITY_EXTRACT_PROMPT | llm
            result = chain.invoke({"text": doc.page_content[:1500]})
            import json, re
            json_str = re.search(r'\[.*\]', result.content.strip(), re.DOTALL)
            if json_str:
                entities = json.loads(json_str.group())
                for e in entities:
                    e["_source"] = doc.metadata.get("filename", "未知")
                all_entities.extend(entities)
        except Exception as e:
            logger.debug(f"实体提取失败: {e}")

    return all_entities


def _multi_hop_infer(question: str, entities: List[dict]) -> str:
    """基于实体关系图进行多跳推理"""
    if not entities:
        return ""

    # 构建关系图描述
    graph_desc = "实体关系图：\n"
    for e in entities:
        graph_desc += f"- {e['entity']} ({e.get('type','')})"
        if e.get('relations'):
            for r in e['relations']:
                graph_desc += f" → {r['relation']} → {r['target']}"
        graph_desc += f" [来源: {e.get('_source','')}]\n"

    return graph_desc


async def graph_rag_qa(question: str) -> dict:
    """
    GraphRAG Lite — 实体提取 + 多跳推理。

    流程：
    1. 常规检索
    2. 从检索结果中提取实体关系图
    3. 将关系图作为额外上下文注入 LLM 生成
    4. 支持多跳推理（如 "A的CEO毕业于哪所大学"）
    """
    # 1. 检索
    docs = await _hybrid_search(question, k=10)
    docs = _llm_rerank(question, docs, top_n=5)

    if not docs:
        return {"answer": "未找到相关资料。", "sources": [], "entities": [], "mode": "graphrag"}

    # 2. 实体提取
    entities = _extract_entities(docs)
    graph_context = _multi_hop_infer(question, entities)

    # 3. 合并上下文（文档 + 关系图）
    doc_context = _format_context(docs)
    full_context = doc_context
    if graph_context:
        full_context += f"\n\n## 实体关系图（多跳推理辅助）\n{graph_context}"

    # 4. 生成
    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        temperature=0.1,
        timeout=settings.LLM_TIMEOUT,
    )

    enhanced_prompt = RAG_SYSTEM_PROMPT + "\n\n注意：如果提供了实体关系图，请利用其中的多跳关系进行推理回答。"
    prompt = ChatPromptTemplate.from_messages([
        ("system", enhanced_prompt),
        ("user", "{question}"),
    ])
    chain = prompt | llm
    answer = chain.invoke({"context": full_context, "question": question}).content

    sources = []
    seen = set()
    for doc in docs:
        fn = doc.metadata.get("filename", "")
        if fn not in seen:
            seen.add(fn)
            sources.append({"filename": fn, "excerpt": doc.page_content[:200]})

    return {
        "answer": answer,
        "sources": sources,
        "entities": entities[:10],  # 前 10 个实体
        "mode": "graphrag",
    }


# ============================================================
# 4. 统一 RAG 入口 — 自适应路由
# ============================================================

async def smart_rag_qa(question: str) -> dict:
    """
    2026 智能 RAG 统一入口 — 自动选择最优策略。

    路由逻辑：
    - Level 0 → 直接 LLM（不检索，节省成本）
    - Level 1 → 标准混合检索 + 缓存
    - Level 2 → Agentic RAG（自验证循环）或 GraphRAG（多跳推理）
    """
    # 1. 缓存检查
    cached = query_cache.get(question)
    if cached:
        return {**cached, "from_cache": True}

    # 2. 复杂度分类
    level = _classify_complexity(question)
    logger.info(f"自适应 RAG: Level {level} | {question[:50]}...")

    # 3. 按级别分发
    if level == 0:
        # 直接回答（不检索）
        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            temperature=0.5,
            timeout=settings.LLM_TIMEOUT,
        )
        answer = llm.invoke(question).content
        result = {"answer": answer, "sources": [], "mode": "direct", "level": 0}

    elif level == 1:
        # 标准 RAG（单轮检索 + 缓存）
        from app.rag.retriever import rag_qa
        result = await rag_qa(question, use_expansion=True, use_rerank=True)
        result["mode"] = "standard"
        result["level"] = 1

    else:  # level == 2
        # 判断用 Agentic 还是 GraphRAG
        # 含"对比""关系""关联"等 → GraphRAG；含"验证""确认""检查" → Agentic
        if any(kw in question for kw in ["对比", "关系", "关联", "联系", "相关"]):
            result = await graph_rag_qa(question)
        else:
            result = await _agentic_retrieve_and_generate(question)
        result["level"] = 2

    # 4. 缓存非 Level 0 的结果
    if level > 0:
        query_cache.set(question, result)

    return result
