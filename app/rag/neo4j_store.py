"""
Neo4j 图数据库存储层 — 持久化知识图谱

替代 advanced.py 中的内存级 GraphRAG Lite。
支持：实体 CRUD、关系管理、邻域查询、批量提取写入。

设计风格与 PGVectorStore 一致：
  单例模式 + 惰性加载 + is_available() 探活
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from langchain_core.documents import Document
from app.config import settings

logger = logging.getLogger(__name__)

# 全局单例
_neo4j_store: Optional["Neo4jStore"] = None


class Neo4jStore:
    """
    Neo4j 图数据库操作层（通用模式）

    图模型：
      (:Entity {id, name, type, description, sources, created_at, updated_at})
        -[:RELATES_TO {relation, sources, weight}]->
      (:Entity {id, name, type, ...})

    去重策略：
      - 实体：name + type 作为唯一标识（MERGE）
      - 关系：source_name + target_name + relation 作为唯一标识
    """

    def __init__(self):
        self._driver = None

    # ---- 连接管理 ----

    def _connect(self):
        """建立 Neo4j Bolt 连接"""
        try:
            from neo4j import GraphDatabase
        except ImportError as e:
            raise RuntimeError("neo4j 驱动未安装，请执行: pip install neo4j") from e

        if not settings.NEO4J_PASSWORD:
            raise RuntimeError("NEO4J_PASSWORD 未配置，Neo4j 不可用")

        self._driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
            max_connection_lifetime=3600,
        )
        # 验证连接
        self._driver.verify_connectivity()
        self._ensure_constraints()
        logger.info(f"Neo4j 连接就绪: {settings.NEO4J_URI}")

    @property
    def driver(self):
        if self._driver is None:
            self._connect()
        return self._driver

    def close(self):
        if self._driver is not None:
            self._driver.close()
            self._driver = None
            logger.info("Neo4j 连接已关闭")

    def is_available(self) -> bool:
        """探活：检查 Neo4j 连接是否正常"""
        try:
            if self._driver is None:
                self._connect()
            self._driver.verify_connectivity()
            return True
        except Exception as e:
            logger.warning(f"Neo4j 不可用: {e}")
            return False

    def _ensure_constraints(self):
        """启动时确保索引约束存在"""
        with self.driver.session() as session:
            session.run(
                "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE"
            )
            session.run(
                "CREATE INDEX IF NOT EXISTS FOR (e:Entity) ON (e.type)"
            )
            logger.debug("Neo4j 索引约束检查完成")

    # ---- 实体 CRUD ----

    def merge_entity(
        self,
        name: str,
        type_: str,
        description: str,
        source: str,
    ) -> str:
        """
        合并实体（MERGE 语义：name 重复则更新，不重复则创建）

        Returns:
            实体的 name（作为唯一标识）
        """
        now = datetime.now(timezone.utc).isoformat()
        entity_id = str(uuid.uuid4())
        with self.driver.session() as session:
            result = session.run(
                """
                MERGE (e:Entity {name: $name})
                ON CREATE SET
                    e.id = $entity_id,
                    e.type = $type,
                    e.description = $description,
                    e.sources = [$source],
                    e.created_at = $now,
                    e.updated_at = $now
                ON MATCH SET
                    e.type = CASE WHEN e.type = '其他' OR e.type IS NULL THEN $type ELSE e.type END,
                    e.description = CASE
                        WHEN $description CONTAINS e.description THEN $description
                        WHEN e.description CONTAINS $description THEN e.description
                        ELSE e.description || ' | ' || $description
                    END,
                    e.sources = CASE
                        WHEN $source IN e.sources THEN e.sources
                        ELSE e.sources + $source
                    END,
                    e.updated_at = $now
                RETURN e.name
                """,
                name=name,
                entity_id=entity_id,
                type=type_,
                description=description,
                source=source,
                now=now,
            )
            record = result.single()
            return record[0] if record else name

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
        创建或更新实体间关系
        去重依据：(source_name, target_name, relation)
        """
        now = datetime.now(timezone.utc).isoformat()
        with self.driver.session() as session:
            # 确保两端实体存在（可能尚未被 merge）
            session.run(
                """
                MERGE (s:Entity {name: $source_name})
                ON CREATE SET
                    s.id = $source_id, s.type = $source_type,
                    s.sources = [$doc_source], s.created_at = $now, s.updated_at = $now
                MERGE (t:Entity {name: $target_name})
                ON CREATE SET
                    t.id = $target_id, t.type = $target_type,
                    t.sources = [$doc_source], t.created_at = $now, t.updated_at = $now
                WITH s, t
                MERGE (s)-[r:RELATES_TO {relation: $relation}]->(t)
                ON CREATE SET
                    r.sources = [$doc_source],
                    r.weight = 1
                ON MATCH SET
                    r.sources = CASE
                        WHEN $doc_source IN r.sources THEN r.sources
                        ELSE r.sources + $doc_source
                    END,
                    r.weight = r.weight + 1
                """,
                source_name=source_name,
                source_id=str(uuid.uuid4()),
                source_type=source_type,
                target_name=target_name,
                target_id=str(uuid.uuid4()),
                target_type=target_type,
                relation=relation,
                doc_source=doc_source,
                now=now,
            )

    def delete_entity(self, entity_name: str) -> bool:
        """删除实体及关联的所有关系"""
        with self.driver.session() as session:
            result = session.run(
                "MATCH (e:Entity {name: $name}) DETACH DELETE e RETURN count(e) AS deleted",
                name=entity_name,
            )
            record = result.single()
            return record and record["deleted"] > 0

    def delete_by_source(self, source: str) -> int:
        """
        删除指定来源文档的所有实体和关系
        策略：从 sources 列表中移除该 source，若 sources 变空则删节点
        """
        with self.driver.session() as session:
            # 从实体 sources 中移除
            session.run(
                """
                MATCH (e:Entity)
                WHERE $source IN e.sources
                SET e.sources = [s IN e.sources WHERE s <> $source],
                    e.updated_at = $now
                """,
                source=source,
                now=datetime.now(timezone.utc).isoformat(),
            )
            # 从关系 sources 中移除
            session.run(
                """
                MATCH ()-[r:RELATES_TO]->()
                WHERE $source IN r.sources
                SET r.sources = [s IN r.sources WHERE s <> $source],
                    r.weight = r.weight - 1
                """,
                source=source,
            )
            # 删除 sources 为空的实体（孤立节点）
            result = session.run(
                "MATCH (e:Entity) WHERE e.sources IS NULL OR size(e.sources) = 0 DETACH DELETE e RETURN count(e) AS deleted",
            )
            record = result.single()
            deleted = record["deleted"] if record else 0
            if deleted:
                logger.info(f"Neo4j: 已清理 {deleted} 个孤立实体 (source={source})")
            return deleted

    def clear_all(self):
        """清空整个图谱"""
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        logger.warning("Neo4j: 图谱已清空")

    # ---- 查询 ----

    def get_entity_neighborhood(
        self,
        entity_name: str,
        depth: int = 2,
        limit: int = 50,
    ) -> List[dict]:
        """
        BFS 遍历实体邻域子图

        Returns:
            [
                {
                    "entity": "华为",
                    "type": "公司",
                    "relations": [
                        {"target": "鸿蒙OS", "relation": "开发"},
                        {"target": "任正非", "relation": "创始人"}
                    ]
                },
                ...
            ]
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (start:Entity {name: $name})
                MATCH (start)-[r:RELATES_TO*1..$depth]-(neighbor:Entity)
                WITH DISTINCT neighbor
                OPTIONAL MATCH (neighbor)-[rel:RELATES_TO]->(target:Entity)
                WHERE target.name <> $name
                RETURN neighbor.name AS entity, neighbor.type AS type,
                       collect(DISTINCT {
                           target: target.name,
                           relation: rel.relation
                       }) AS relations
                ORDER BY size(collect(DISTINCT rel)) DESC
                LIMIT $limit
                """,
                name=entity_name,
                depth=depth,
                limit=limit,
            )
            records = result.data()
            return records if records else []

    def search_entities(
        self,
        query: str,
        type_: Optional[str] = None,
        limit: int = 20,
    ) -> List[dict]:
        """模糊搜索实体名称"""
        with self.driver.session() as session:
            if type_:
                result = session.run(
                    """
                    MATCH (e:Entity)
                    WHERE e.name CONTAINS $query AND e.type = $type
                    RETURN e.name AS name, e.type AS type,
                           e.description AS description
                    LIMIT $limit
                    """,
                    query=query,
                    type=type_,
                    limit=limit,
                )
            else:
                result = session.run(
                    """
                    MATCH (e:Entity)
                    WHERE e.name CONTAINS $query
                    RETURN e.name AS name, e.type AS type,
                           e.description AS description
                    LIMIT $limit
                    """,
                    query=query,
                    limit=limit,
                )
            return result.data()

    def get_related_entities(
        self,
        entity_name: str,
        relation: Optional[str] = None,
        limit: int = 30,
    ) -> List[dict]:
        """按关系类型查询关联实体"""
        with self.driver.session() as session:
            if relation:
                result = session.run(
                    """
                    MATCH (e:Entity {name: $name})-[r:RELATES_TO {relation: $relation}]->(target:Entity)
                    RETURN target.name AS entity, target.type AS type,
                           r.relation AS relation, r.weight AS weight
                    ORDER BY r.weight DESC
                    LIMIT $limit
                    """,
                    name=entity_name,
                    relation=relation,
                    limit=limit,
                )
            else:
                result = session.run(
                    """
                    MATCH (e:Entity {name: $name})-[r:RELATES_TO]->(target:Entity)
                    RETURN target.name AS entity, target.type AS type,
                           r.relation AS relation, r.weight AS weight
                    ORDER BY r.weight DESC
                    LIMIT $limit
                    """,
                    name=entity_name,
                    limit=limit,
                )
            return result.data()

    def get_stats(self) -> dict:
        """获取图谱统计信息"""
        with self.driver.session() as session:
            node_count = session.run("MATCH (e:Entity) RETURN count(e) AS count").single()["count"]
            rel_count = session.run("MATCH ()-[r:RELATES_TO]->() RETURN count(r) AS count").single()["count"]
            type_dist = session.run(
                """
                MATCH (e:Entity)
                RETURN e.type AS type, count(e) AS count
                ORDER BY count DESC
                LIMIT 20
                """
            ).data()
            return {
                "nodes": node_count,
                "relationships": rel_count,
                "type_distribution": type_dist,
            }

    # ---- 批量提取（优化版：并发 LLM + 批量写入 + 预过滤）----

    @staticmethod
    def _has_potential_entities(text: str) -> bool:
        """快速判断文本是否可能包含实体（零 LLM 成本）"""
        import re
        if len(text.strip()) < 50:
            return False
        chinese_chars = len(re.findall(r'[一-鿿]', text))
        if chinese_chars < 10:
            return False
        return True

    def _batch_merge_entities(
        self, entities_data: List[dict], source: str
    ) -> int:
        """
        一次 Cypher 调用批量 MERGE 实体（UNWIND 模式）

        Args:
            entities_data: [{"name": ..., "type": ..., "description": ..., "id": ...}, ...]
            source: 来源文档路径

        Returns:
            创建的实体数
        """
        if not entities_data:
            return 0

        now = datetime.now(timezone.utc).isoformat()
        with self.driver.session() as session:
            result = session.run(
                """
                UNWIND $entities AS ent
                MERGE (e:Entity {name: ent.name})
                ON CREATE SET
                    e.id = ent.id,
                    e.type = ent.type,
                    e.description = ent.description,
                    e.sources = [ent.source],
                    e.created_at = ent.now,
                    e.updated_at = ent.now
                ON MATCH SET
                    e.type = CASE
                        WHEN e.type = '其他' OR e.type IS NULL THEN ent.type
                        ELSE e.type
                    END,
                    e.description = CASE
                        WHEN ent.description CONTAINS e.description THEN ent.description
                        WHEN e.description CONTAINS ent.description THEN e.description
                        ELSE e.description + ' | ' + ent.description
                    END,
                    e.sources = CASE
                        WHEN ent.source IN e.sources THEN e.sources
                        ELSE e.sources + ent.source
                    END,
                    e.updated_at = ent.now
                RETURN count(e) AS created
                """,
                entities=entities_data,
                now=now,
            )
            record = result.single()
            return record["created"] if record else 0

    def _batch_merge_relationships(
        self, rels_data: List[dict], source: str
    ) -> int:
        """
        一次 Cypher 调用批量 MERGE 关系（UNWIND 模式）

        Args:
            rels_data: [{"source": ..., "s_type": ..., "target": ..., "t_type": ...,
                         "relation": ..., "s_id": ..., "t_id": ...}, ...]
            source: 来源文档路径

        Returns:
            创建的关系数
        """
        if not rels_data:
            return 0

        now = datetime.now(timezone.utc).isoformat()
        with self.driver.session() as session:
            result = session.run(
                """
                UNWIND $rels AS r
                MERGE (s:Entity {name: r.source})
                ON CREATE SET
                    s.id = r.s_id, s.type = r.s_type,
                    s.sources = [r.doc_source],
                    s.created_at = r.now, s.updated_at = r.now
                MERGE (t:Entity {name: r.target})
                ON CREATE SET
                    t.id = r.t_id, t.type = r.t_type,
                    t.sources = [r.doc_source],
                    t.created_at = r.now, t.updated_at = r.now
                WITH s, t, r
                MERGE (s)-[rel:RELATES_TO {relation: r.relation}]->(t)
                ON CREATE SET
                    rel.sources = [r.doc_source],
                    rel.weight = 1
                ON MATCH SET
                    rel.sources = CASE
                        WHEN r.doc_source IN rel.sources THEN rel.sources
                        ELSE rel.sources + r.doc_source
                    END,
                    rel.weight = rel.weight + 1
                RETURN count(rel) AS created
                """,
                rels=rels_data,
                now=now,
            )
            record = result.single()
            return record["created"] if record else 0

    def batch_extract_and_store(
        self,
        chunks: List[Document],
        batch_size: int = 20,
        max_workers: int = 3,
    ) -> Tuple[int, int]:
        """
        批量提取并写入实体和关系到 Neo4j（优化版）

        优化点：
          1. 并发 LLM 提取（ThreadPoolExecutor, max_workers=3）
          2. 空 chunk 预过滤（_has_potential_entities）
          3. 批量 UNWIND 写入（实体 + 关系各 1 次网络往返）

        Returns:
            (entity_count, relationship_count)
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from app.rag.graph_extractor import _extract_entities_from_text

        # 1. 预分组 + 过滤
        batches = []
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
            batches.append((combined_text, source))

        if not batches:
            logger.info("Neo4j: 所有 chunks 被预过滤跳过（无可提取实体）")
            return 0, 0

        # 2. 并发 LLM 提取实体
        all_entities_raw = []  # [(ent_dict, source), ...]
        effective_workers = min(max_workers, len(batches))

        with ThreadPoolExecutor(max_workers=effective_workers) as executor:
            future_map = {}
            for text, src in batches:
                future = executor.submit(_extract_entities_from_text, text)
                future_map[future] = (text, src)

            for future in as_completed(future_map):
                _, src = future_map[future]
                try:
                    entities = future.result()
                    for ent in entities:
                        ent_name = ent.get("entity", "").strip()
                        if not ent_name:
                            continue
                        all_entities_raw.append((ent, src))
                except Exception as e:
                    logger.warning(f"Neo4j 实体提取失败: {e}")

        if not all_entities_raw:
            return 0, 0

        # 3. 收集实体和关系数据（用于批量 UNWIND）
        entities_batch = []
        rels_batch = []
        seen_entities = set()

        for ent, src in all_entities_raw:
            ent_name = ent.get("entity", "").strip()
            ent_type = ent.get("type", "其他").strip()

            # 实体数据
            key = (ent_name, src)
            if key not in seen_entities:
                seen_entities.add(key)
                entities_batch.append({
                    "id": str(uuid.uuid4()),
                    "name": ent_name,
                    "type": ent_type,
                    "description": self._build_entity_desc(ent, src),
                    "source": src,
                })

            # 关系数据
            for rel in ent.get("relations", []):
                target = rel.get("target", "").strip()
                relation_desc = rel.get("relation", "").strip()
                if not target or not relation_desc:
                    continue
                rels_batch.append({
                    "source": ent_name,
                    "s_type": ent_type,
                    "target": target,
                    "t_type": "其他",
                    "relation": relation_desc,
                    "s_id": str(uuid.uuid4()),
                    "t_id": str(uuid.uuid4()),
                    "doc_source": src,
                })

        # 4. 批量写入 Neo4j（仅 2 次网络往返）
        entity_count = self._batch_merge_entities(entities_batch, source="batch")
        rel_count = self._batch_merge_relationships(rels_batch, source="batch")

        logger.info(
            f"Neo4j 批量提取完成: {entity_count} 实体, "
            f"{rel_count} 关系 "
            f"(来自 {len(chunks)} chunks, {len(batches)} 有效批次, "
            f"{effective_workers} 并发 worker)"
        )
        return entity_count, rel_count

    @staticmethod
    def _build_entity_desc(ent: dict, source: str) -> str:
        """构建实体描述（合并来源上下文）"""
        desc = ent.get("description", "")
        if not desc:
            desc = f"实体类型: {ent.get('type', '其他')}"
        return desc


def get_neo4j_store() -> Optional[Neo4jStore]:
    """
    获取 Neo4j 存储实例（惰性加载单例）
    与 get_pgvector_store() 风格一致
    """
    global _neo4j_store
    if not settings.NEO4J_ENABLED:
        return None
    if _neo4j_store is None:
        store = Neo4jStore()
        if store.is_available():
            _neo4j_store = store
        else:
            _neo4j_store = False  # type: ignore
            return None
    return _neo4j_store if _neo4j_store is not False else None
