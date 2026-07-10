"""
独立图谱构建脚本 — 对已索引文档批量提取实体写入图存储

用法：
  python -m app.rag.build_graph --all                 # 对所有已索引文档构建图谱
  python -m app.rag.build_graph --source <file_path>   # 对指定源文件构建图谱
  python -m app.rag.build_graph --rebuild              # 重建整个图谱（先清空再构建）
  python -m app.rag.build_graph --stats                # 查看图谱统计

图谱后端由 GRAPH_BACKEND 环境变量决定 (lightrag | neo4j | none)
"""

import argparse
import logging
import sys
import os
from typing import List

# 确保能找到 app 模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _get_graph_store():
    """获取配置的图存储后端"""
    if settings.GRAPH_BACKEND == "lightrag":
        from app.rag.lightrag_store import get_lightrag_store
        return get_lightrag_store(), "lightrag"
    elif settings.GRAPH_BACKEND == "neo4j":
        from app.rag.neo4j_store import get_neo4j_store
        store = get_neo4j_store()
        if store and store.is_available():
            return store, "neo4j"
    elif settings.GRAPH_BACKEND == "none":
        logger.error("GRAPH_BACKEND=none，图谱功能已禁用")
        return None, "none"
    return None, "unknown"


def cmd_build_all():
    """对所有已索引文档构建图谱"""
    from app.rag.store import get_all_documents_for_bm25

    store, backend = _get_graph_store()
    if not store:
        logger.error(f"图谱后端不可用 (GRAPH_BACKEND={settings.GRAPH_BACKEND})")
        return

    logger.info("正在从向量存储中读取所有文档...")
    docs = get_all_documents_for_bm25(limit=10000)

    if not docs:
        logger.warning("向量存储中无文档，请先索引文档")
        return

    logger.info(f"读取到 {len(docs)} 个 chunks，开始提取实体...")
    entities, relations = store.batch_extract_and_store(docs)

    stats = store.get_stats()
    logger.info(
        f"图谱构建完成: {entities} 实体, {relations} 关系 "
        f"(图谱总计: {stats['nodes']} 节点, {stats['relationships']} 关系)"
    )


def cmd_build_source(source: str):
    """对指定源文件构建图谱"""
    from app.rag.loader import UniversalDocumentLoader
    from app.rag.splitter import split_documents
    from pathlib import Path

    store, backend = _get_graph_store()
    if not store:
        logger.error(f"图谱后端不可用 (GRAPH_BACKEND={settings.GRAPH_BACKEND})")
        return

    abs_path = os.path.abspath(source)
    filename = Path(source).name

    # 先删除该源的旧图谱数据
    logger.info(f"清理旧图谱数据 ({backend}): {filename}")
    store.delete_by_source(abs_path)

    # 加载并分块文档
    logger.info(f"加载文档: {source}")
    docs = UniversalDocumentLoader.load(source)
    if not docs:
        logger.error("文档解析后无内容")
        return

    chunks = split_documents(docs)
    if not chunks:
        logger.error("文档分块后无内容")
        return

    logger.info(f"文档分块完成: {len(chunks)} chunks，开始提取实体...")
    entities, relations = store.batch_extract_and_store(chunks)

    logger.info(f"构建完成 ({backend}): {entities} 实体, {relations} 关系")


def cmd_rebuild():
    """重建整个图谱（先清空再构建）"""
    store, backend = _get_graph_store()
    if not store:
        logger.error(f"图谱后端不可用 (GRAPH_BACKEND={settings.GRAPH_BACKEND})")
        return

    logger.warning(f"正在清空图谱 ({backend})...")
    store.clear_all()

    cmd_build_all()


def cmd_stats():
    """查看图谱统计"""
    store, backend = _get_graph_store()
    if not store:
        logger.error(f"图谱后端不可用 (GRAPH_BACKEND={settings.GRAPH_BACKEND})")
        return

    stats = store.get_stats()
    print(f"\n=== 图谱统计 ({backend}) ===")
    print(f"  实体节点数:  {stats['nodes']}")
    print(f"  关系边数:    {stats['relationships']}")
    print(f"\n  实体类型分布:")
    for item in stats.get("type_distribution", []):
        print(f"    - {item['type']}: {item['count']}")


def main():
    parser = argparse.ArgumentParser(
        description="知识图谱构建工具 (GRAPH_BACKEND=lightrag|neo4j)",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="对所有已索引文档构建图谱")
    group.add_argument("--source", type=str, help="对指定源文件构建图谱")
    group.add_argument("--rebuild", action="store_true", help="重建整个图谱（先清空再构建）")
    group.add_argument("--stats", action="store_true", help="查看图谱统计")

    args = parser.parse_args()

    if args.all:
        cmd_build_all()
    elif args.source:
        cmd_build_source(args.source)
    elif args.rebuild:
        cmd_rebuild()
    elif args.stats:
        cmd_stats()


if __name__ == "__main__":
    main()
