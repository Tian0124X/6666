"""
图增强检索模块 — 查询阶段从 Neo4j 获取图谱上下文

当 Neo4j 可用时，从用户问题中提取实体名称，
查询实体邻域子图并格式化为 LLM prompt 上下文。

当 Neo4j 不可用或问题无实体命中时，返回空上下文，
由调用方（advanced.py）决定是否走内存 fallback。
"""

import logging
from typing import List, Optional, Tuple

from app.rag.graph_extractor import extract_query_entities, build_graph_context

logger = logging.getLogger(__name__)


def graph_enhanced_retrieve(
    question: str,
    store: "Neo4jStore",  # type: ignore
    depth: int = 2,
) -> Tuple[str, List[str]]:
    """
    图增强检索：从问题中提取实体 → 查询邻域子图 → 格式化为文本

    Args:
        question: 用户问题
        store: Neo4jStore 实例
        depth: 实体邻域 BFS 遍历深度

    Returns:
        (graph_context_text, entity_list)
        - graph_context_text: 注入 LLM 的图谱上下文，空字符串表示无结果
        - entity_list: 从问题中提取的实体名列表
    """
    # 1. 从问题中提取关键实体
    entities = extract_query_entities(question)
    if not entities:
        logger.debug("图增强检索: 问题中未提取到实体")
        return "", []

    logger.info(f"图增强检索: 提取到实体 {entities}")

    # 2. 查询邻域并构建上下文
    context = build_graph_context(entities, store, depth=depth)

    if not context:
        logger.debug(f"图增强检索: 实体 {entities} 在 Neo4j 中无命中")
        return "", entities

    logger.info(f"图增强检索: 图谱上下文已构建 ({len(context)} 字符)")
    return context, entities
