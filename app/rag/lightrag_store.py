"""
LightRAG 图谱存储层 — NetworkX 内存图 + pickle 原子持久化

替代 Neo4jStore 的轻量级方案：
  - 实体提取：复用 graph_extractor._extract_entities_from_text()
  - 图存储：   networkx.MultiDiGraph（内存操作，无网络往返）
  - 持久化：   pickle 原子写入（.tmp → rename）

接口与 Neo4jStore 兼容，通过 GRAPH_BACKEND 配置切换。
"""

import logging
import os
import re
import threading
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import networkx as nx
from langchain_core.documents import Document

from app.config import settings

logger = logging.getLogger(__name__)

# 全局单例
_lightrag_store: Optional["LightRAGStore"] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LightRAGStore:
    """
    纯内存知识图谱存储（NetworkX MultiDiGraph + pickle 原子持久化）

    图模型（与 Neo4j 对齐）:
      Node key = entity.name
      Node attrs: {id, type, description, sources[], created_at, updated_at}
      Edge key = (source_name, target_name, relation)
      Edge attrs: {sources[], weight, source_type, target_type}
    """

    def __init__(self):
        self._graph = nx.MultiDiGraph()
        self._lock = threading.Lock()
        self._loaded = False

    # ---- 连接 / 探活 ----

    def is_available(self) -> bool:
        """始终可用（无外部依赖）"""
        return True

    @property
    def _persist_path(self) -> str:
        return os.path.join(settings.LIGHTRAG_PERSIST_DIR, "graph.pickle")

    # ---- 持久化 ----

    def _ensure_dir(self):
        os.makedirs(settings.LIGHTRAG_PERSIST_DIR, exist_ok=True)

    def _load_from_disk(self):
        """启动时从 pickle 恢复图"""
        import pickle as _pickle
        if not os.path.exists(self._persist_path):
            return
        try:
            with open(self._persist_path, "rb") as f:
                self._graph = _pickle.load(f)
            self._loaded = True
            logger.info(
                f"LightRAG: 从磁盘恢复图谱 "
                f"({self._graph.number_of_nodes()} 节点, "
                f"{self._graph.number_of_edges()} 边)"
            )
        except Exception as e:
            logger.warning(f"LightRAG: 图谱恢复失败，从空图开始: {e}")
            self._graph = nx.MultiDiGraph()

    def save(self):
        """原子持久化：写 .tmp → rename"""
        import pickle as _pickle
        self._ensure_dir()
        tmp_path = self._persist_path + ".tmp"
        try:
            with open(tmp_path, "wb") as f:
                _pickle.dump(self._graph, f)
            os.replace(tmp_path, self._persist_path)  # 原子 rename
            self._loaded = True
            logger.debug(f"LightRAG: 图谱已持久化 ({self._persist_path})")
        except Exception as e:
            logger.error(f"LightRAG: 持久化失败: {e}")
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    # ---- 实体 CRUD ----

    def merge_entity(
        self,
        name: str,
        type_: str,
        description: str,
        source: str,
    ) -> str:
        """
        合并实体（MERGE 语义：name 重复则更新）

        Returns:
            实体的 name（作为唯一标识）
        """
        with self._lock:
            if name in self._graph:
                node = self._graph.nodes[name]
                # 更新 type（优先保留非"其他"的 type）
                if node.get("type") in (None, "其他") and type_ and type_ != "其他":
                    node["type"] = type_
                # 合并 description（取较长者或拼接）
                existing_desc = node.get("description", "")
                if description:
                    if description in existing_desc:
                        node["description"] = description
                    elif existing_desc not in description:
                        node["description"] = existing_desc + " | " + description
                    else:
                        node["description"] = existing_desc
                # 追加 source
                sources = node.get("sources", [])
                if source not in sources:
                    sources.append(source)
                    node["sources"] = sources
                node["updated_at"] = _now_iso()
            else:
                self._graph.add_node(
                    name,
                    id=str(uuid.uuid4()),
                    type=type_ or "其他",
                    description=description or "",
                    sources=[source],
                    created_at=_now_iso(),
                    updated_at=_now_iso(),
                )
            return name

    def merge_relationship(
        self,
        source_name: str,
        source_type: str,
        target_name: str,
        target_type: str,
        relation: str,
        doc_source: str,
    ):
        """
        创建或更新关系（去重依据: source_name + target_name + relation）
        """
        with self._lock:
            # 确保两端实体存在
            for name, etype in [(source_name, source_type), (target_name, target_type)]:
                if name not in self._graph:
                    self._graph.add_node(
                        name,
                        id=str(uuid.uuid4()),
                        type=etype or "其他",
                        description="",
                        sources=[doc_source],
                        created_at=_now_iso(),
                        updated_at=_now_iso(),
                    )

            edge_key = (source_name, target_name, relation)
            if self._graph.has_edge(*edge_key):
                edge = self._graph.edges[edge_key]
                edge["weight"] = edge.get("weight", 1) + 1
                sources = edge.get("sources", [])
                if doc_source not in sources:
                    sources.append(doc_source)
                    edge["sources"] = sources
            else:
                self._graph.add_edge(
                    source_name,
                    target_name,
                    key=relation,
                    relation=relation,
                    sources=[doc_source],
                    weight=1,
                    source_type=source_type,
                    target_type=target_type,
                )

    # ---- 删除 ----

    def delete_entity(self, entity_name: str) -> bool:
        """删除实体及关联的所有边"""
        with self._lock:
            if entity_name not in self._graph:
                return False
            self._graph.remove_node(entity_name)
            return True

    def delete_by_source(self, source: str) -> int:
        """
        从所有节点/边的 sources 中移除该 source，
        清理 sources 为空的孤立节点。
        """
        with self._lock:
            # 1. 从节点的 sources 中移除
            orphan_nodes = []
            for node, data in self._graph.nodes(data=True):
                sources = list(data.get("sources", []))
                if source in sources:
                    sources.remove(source)
                    data["sources"] = sources
                    data["updated_at"] = _now_iso()
                    if not sources:
                        orphan_nodes.append(node)

            # 2. 从边的 sources 中移除
            orphan_edges = []
            for u, v, k, data in list(self._graph.edges(keys=True, data=True)):
                edge_sources = list(data.get("sources", []))
                if source in edge_sources:
                    edge_sources.remove(source)
                    data["sources"] = edge_sources
                    data["weight"] = max(0, data.get("weight", 1) - 1)
                    if not edge_sources:
                        orphan_edges.append((u, v, k))

            # 3. 删除 sources 为空的边
            for u, v, k in orphan_edges:
                self._graph.remove_edge(u, v, k)

            # 4. 删除孤立节点
            deleted = 0
            for node in orphan_nodes:
                if node in self._graph:
                    self._graph.remove_node(node)
                    deleted += 1

            if deleted:
                logger.info(f"LightRAG: 已清理 {deleted} 个孤立实体 (source={source})")

        if deleted > 0:
            self.save()
        return deleted

    def clear_all(self):
        """清空整个图谱"""
        with self._lock:
            self._graph.clear()
        # 删除持久化文件
        if os.path.exists(self._persist_path):
            try:
                os.remove(self._persist_path)
            except Exception:
                pass
        logger.warning("LightRAG: 图谱已清空")

    # ---- 查询 ----

    def get_entity_neighborhood(
        self,
        entity_name: str,
        depth: int = 2,
        limit: int = 50,
    ) -> List[dict]:
        """
        BFS 遍历实体邻域子图，返回与 Neo4jStore 兼容的格式。

        Returns:
            [
                {"entity": "华为", "type": "公司",
                 "relations": [{"target": "鸿蒙OS", "relation": "开发"}, ...]},
                ...
            ]
        """
        if entity_name not in self._graph:
            return []

        with self._lock:
            # 使用 ego_graph 获取邻域子图
            try:
                subgraph = nx.ego_graph(
                    self._graph, entity_name, radius=depth, undirected=False
                )
            except Exception:
                return []

        results = []
        for node in subgraph.nodes():
            if node == entity_name:
                continue
            node_data = self._graph.nodes.get(node, {})
            relations = []
            # 出边
            for _, tgt, key, data in list(
                self._graph.out_edges(node, keys=True, data=True)
            ):
                if tgt != entity_name:
                    relations.append({
                        "target": tgt,
                        "relation": data.get("relation", key),
                    })
            results.append({
                "entity": node,
                "type": node_data.get("type", "其他"),
                "relations": relations,
            })

        # 按关系数量降序 + limit
        results.sort(key=lambda x: len(x["relations"]), reverse=True)
        return results[:limit]

    def search_entities(
        self,
        query: str,
        type_: Optional[str] = None,
        limit: int = 20,
    ) -> List[dict]:
        """模糊搜索实体名称（子串匹配）"""
        matches = []
        for node, data in self._graph.nodes(data=True):
            if query.lower() in node.lower():
                if type_ and data.get("type") != type_:
                    continue
                matches.append({
                    "name": node,
                    "type": data.get("type", "其他"),
                    "description": data.get("description", ""),
                })
        return matches[:limit]

    def get_related_entities(
        self,
        entity_name: str,
        relation: Optional[str] = None,
        limit: int = 30,
    ) -> List[dict]:
        """按关系类型查询关联实体（出边邻居）"""
        if entity_name not in self._graph:
            return []

        results = []
        for _, tgt, key, data in list(
            self._graph.out_edges(entity_name, keys=True, data=True)
        ):
            if relation and data.get("relation") != relation:
                continue
            tgt_data = self._graph.nodes.get(tgt, {})
            results.append({
                "entity": tgt,
                "type": tgt_data.get("type", "其他"),
                "relation": data.get("relation", key),
                "weight": data.get("weight", 1),
            })

        results.sort(key=lambda x: x.get("weight", 1), reverse=True)
        return results[:limit]

    def get_stats(self) -> dict:
        """获取图谱统计信息"""
        with self._lock:
            type_dist = Counter(
                data.get("type", "其他")
                for _, data in self._graph.nodes(data=True)
            )
            return {
                "nodes": self._graph.number_of_nodes(),
                "relationships": self._graph.number_of_edges(),
                "type_distribution": [
                    {"type": t, "count": c}
                    for t, c in type_dist.most_common(20)
                ],
            }

    # ---- 批量提取（核心：复用现有 LLM 逻辑，内存写入）----

    @staticmethod
    def _has_potential_entities(text: str) -> bool:
        """快速判断文本是否可能包含实体（零 LLM 成本）"""
        if len(text.strip()) < 50:
            return False
        chinese_chars = len(re.findall(r'[一-鿿]', text))
        if chinese_chars < 10:
            return False
        return True

    def batch_extract_and_store(
        self,
        chunks: List[Document],
        batch_size: int = 20,
    ) -> Tuple[int, int]:
        """
        批量提取实体并写入 NetworkX 内存图。

        - LLM 提取：复用 graph_extractor._extract_entities_from_text()
        - 写入：NetworkX 内存操作（~0.01ms/实体 vs ~10ms Neo4j）
        - 持久化：批量完成后统一 save()
        """
        from app.rag.graph_extractor import _extract_entities_from_text

        total_entities = 0
        total_relations = 0
        all_sources = set()

        batch_idx = 0
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            combined_text = "\n\n---\n\n".join(
                f"[文档 {idx}]\n{chunk.page_content}"
                for idx, chunk in enumerate(batch, i + 1)
            )
            source = (
                batch[0].metadata.get("source", "unknown") if batch else "unknown"
            )

            # 预过滤：跳过高概率无实体的 chunk
            if not self._has_potential_entities(combined_text):
                continue

            batch_idx += 1
            try:
                entities = _extract_entities_from_text(combined_text)
            except Exception as e:
                logger.warning(
                    f"LightRAG 实体提取失败 (batch {i // batch_size}): {e}"
                )
                continue

            for ent in entities:
                ent_name = ent.get("entity", "").strip()
                ent_type = ent.get("type", "其他").strip()
                if not ent_name:
                    continue

                description = ent.get("description", "")
                if not description:
                    description = f"实体类型: {ent_type}"

                self.merge_entity(
                    name=ent_name,
                    type_=ent_type,
                    description=description,
                    source=source,
                )
                total_entities += 1
                all_sources.add(source)

                for rel in ent.get("relations", []):
                    target = rel.get("target", "").strip()
                    relation_desc = rel.get("relation", "").strip()
                    if not target or not relation_desc:
                        continue
                    self.merge_relationship(
                        source_name=ent_name,
                        source_type=ent_type,
                        target_name=target,
                        target_type="其他",
                        relation=relation_desc,
                        doc_source=source,
                    )
                    total_relations += 1

        # 批量完成后统一持久化
        if total_entities > 0:
            self.save()

        logger.info(
            f"LightRAG 批量提取完成: {total_entities} 实体, "
            f"{total_relations} 关系 (来自 {len(chunks)} chunks, "
            f"{batch_idx} 有效批次, {len(all_sources)} 源文件)"
        )
        return total_entities, total_relations


def get_lightrag_store() -> Optional[LightRAGStore]:
    """
    获取 LightRAG 存储实例（惰性加载单例）
    与 get_neo4j_store() 风格一致
    """
    global _lightrag_store
    if _lightrag_store is None:
        try:
            store = LightRAGStore()
            store._load_from_disk()
            _lightrag_store = store
            logger.info(
                f"LightRAG 就绪: {store.get_stats()['nodes']} 节点, "
                f"{store.get_stats()['relationships']} 边"
            )
        except Exception as e:
            logger.warning(f"LightRAG 初始化失败: {e}")
            _lightrag_store = False  # type: ignore
            return None
    return _lightrag_store if _lightrag_store is not False else None
