"""MySQL 数据库连接 — SQLAlchemy 2.0"""

import logging
from sqlalchemy import create_engine, Column, BigInteger, String, Text, TIMESTAMP, Enum, JSON, Integer
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


# 全局引擎/会话 (懒加载，失败后不再重试)
_engine = None
_engine_failed = False
_SessionLocal = None


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
            Base.metadata.create_all(_engine)
            logger.info("MySQL 连接池就绪")
        except Exception:
            _engine_failed = True
            logger.info("MySQL 未配置或不可用，对话持久化暂不启用 (内存+Redis 正常运作)")
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
