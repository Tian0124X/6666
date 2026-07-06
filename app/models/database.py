"""MySQL 数据库连接 — SQLAlchemy 2.0"""

import logging
from sqlalchemy import create_engine, Column, BigInteger, String, Text, TIMESTAMP, Enum, JSON, Integer, text, Index
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import func
from app.config import settings

logger = logging.getLogger(__name__)

Base = declarative_base()


class ConversationRecord(Base):
    """对话记录 ORM 模型"""
    __tablename__ = "conversations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)
    role = Column(Enum("user", "assistant", "system"), nullable=False)
    content = Column(Text, nullable=False)
    metadata_json = Column(JSON, nullable=True)  # 图表/表格/洞察等富数据
    created_at = Column(TIMESTAMP, server_default=func.now())


class TaskHistory(Base):
    """任务历史 ORM 模型"""
    __tablename__ = "task_history"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(String(64), unique=True, nullable=False)
    user_id = Column(String(64), nullable=False, index=True)
    task_type = Column(String(32), nullable=False)
    status = Column(Enum("pending", "running", "success", "failed", "retrying"), default="pending")
    input_params = Column(JSON, nullable=True)
    output_result = Column(JSON, nullable=True)
    error_log = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())


class EvalRecord(Base):
    """评测记录 ORM 模型 — 持久化 RAG/Agent 评测结果"""
    __tablename__ = "eval_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    eval_type = Column(String(20), nullable=False, index=True)  # "rag" | "agent"
    accuracy = Column(String(20), nullable=False)  # "0.850" 精度分数
    avg_recall = Column(String(20), nullable=True)  # RAG 专用
    tool_accuracy = Column(String(20), nullable=True)  # Agent 专用
    avg_latency_ms = Column(String(20), nullable=False)
    passed = Column(Integer, default=0)
    total = Column(Integer, default=0)
    details_json = Column(Text, nullable=True)  # JSON string
    created_at = Column(TIMESTAMP, server_default=func.now())


class ConversationSummary(Base):
    """对话摘要 ORM — 情景记忆管线"""
    __tablename__ = "conversation_summaries"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)
    summary_json = Column(Text, nullable=False)
    is_final = Column(Integer, default=0)
    created_at = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        Index("idx_summary_session_user", "session_id", "user_id", unique=True),
    )


class UserFact(Base):
    """用户事实 ORM — 语义记忆"""
    __tablename__ = "user_facts"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    fact_text = Column(String(512), nullable=False)
    category = Column(String(32), default="general")  # preference, fact, context, skill
    confidence = Column(String(8), default="0.5")  # 0.0-1.0
    source_session_id = Column(String(64), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    last_accessed_at = Column(TIMESTAMP, nullable=True)
    access_count = Column(Integer, default=0)


class AnalyticsEvent(Base):
    """业务分析事件 — 用户行为追踪"""
    __tablename__ = "analytics_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_type = Column(String(32), nullable=False, index=True)  # chat_start/chat_end/tool_call/rag_query/knowledge_upload/user_login
    user_id = Column(String(64), nullable=False, index=True)
    session_id = Column(String(64), nullable=True)
    data_json = Column(JSON, nullable=True)  # 事件附加数据
    created_at = Column(TIMESTAMP, server_default=func.now(), index=True)


class UserRecord(Base):
    """用户记录 ORM 模型 — JWT 持久化"""
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    display_name = Column(String(128), default="")
    role = Column(String(20), default="user")  # admin, user, guest
    sso_provider = Column(String(20), nullable=True)  # ldap, oidc, null=local
    email = Column(String(256), default="")
    department = Column(String(128), default="")
    is_active = Column(Integer, default=1)
    created_at = Column(TIMESTAMP, server_default=func.now())
    last_login_at = Column(TIMESTAMP, nullable=True)


class SessionRecord(Base):
    """会话记录 ORM 模型 — 多会话管理"""
    __tablename__ = "sessions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)
    name = Column(String(128), default="新对话")
    is_archived = Column(Integer, default=0)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())


# 全局引擎/会话 (懒加载，失败后不再重试)
_engine = None
_engine_failed = False
_SessionLocal = None


def _auto_migrate(engine):
    """轻量级自动迁移: 检测并添加缺失的列"""
    from sqlalchemy import inspect as sa_inspect
    try:
        inspector = sa_inspect(engine)
        # conversations 表: 添加 metadata_json 列
        if "conversations" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("conversations")}
            if "metadata_json" not in cols:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE conversations ADD COLUMN metadata_json JSON NULL"))
                logger.info("自动迁移: conversations 表已添加 metadata_json 列")
    except Exception as e:
        logger.warning(f"自动迁移失败: {e}")


def _get_engine():
    global _engine, _engine_failed
    if _engine_failed:
        return None
    if _engine is None:
        try:
            _engine = create_engine(
                settings.mysql_url,
                pool_size=5,
                max_overflow=10,
                pool_recycle=3600,
                pool_pre_ping=True,
            )
            # 测试连接
            with _engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            Base.metadata.create_all(_engine)
            # 自动迁移: 为已有表添加新列
            _auto_migrate(_engine)
            logger.info("MySQL 连接池就绪")
        except Exception as e:
            _engine_failed = True
            logger.warning(
                f"MySQL 不可用 ({e})，对话持久化降级为内存+Redis"
            )
    return _engine if not _engine_failed else None


def get_session():
    """获取数据库会话（调用方负责关闭）"""
    global _SessionLocal
    engine = _get_engine()
    if engine is None:
        return None
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=engine)
    return _SessionLocal()
