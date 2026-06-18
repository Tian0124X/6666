"""用户模型 — JWT 认证 + MySQL 持久化

Token 格式: 标准 JWT (PyJWT), 签名 HS256, 过期 24h
存储: MySQL users 表优先 → 内存 dict 兜底
"""

import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel, Field

try:
    import jwt
    _JWT_AVAILABLE = True
except ImportError:
    _JWT_AVAILABLE = False
    jwt = None  # type: ignore

try:
    import bcrypt
    _BCRYPT_AVAILABLE = True
except ImportError:
    _BCRYPT_AVAILABLE = False

from sqlalchemy import text as sa_text

logger = logging.getLogger(__name__)

# ====== 内存兜底 (MySQL 不可用时) ======

_users: dict[str, dict] = {}
_tokens: dict[str, str] = {}  # token → username (deprecated, keep for migration)
_token_blacklist: set[str] = set()  # 登出黑名单

JWT_SECRET = secrets.token_hex(32)  # 服务重启后失效 (可后续改为环境变量)
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24
REFRESH_TOKEN_BYTES = 32  # refresh token 字节数


# ====== MySQL 用户持久化 ======

def _get_mysql_session():
    """获取 MySQL 会话（懒加载，失败返回 None）"""
    try:
        from app.models.database import get_session
        return get_session()
    except Exception:
        return None


def _mysql_find_user(username: str) -> Optional[dict]:
    """从 MySQL 查找用户"""
    sess = _get_mysql_session()
    if sess is None:
        return None
    try:
        row = sess.execute(
            sa_text(
                "SELECT username, password_hash, display_name, role, sso_provider, email, department, is_active "
                "FROM users WHERE username = :u"
            ),
            {"u": username},
        ).fetchone()
        if row:
            return dict(row._mapping)
        return None
    except Exception as e:
        logger.debug(f"MySQL 查用户失败: {e}")
        return None
    finally:
        sess.close()


def _mysql_insert_user(username: str, password_hash: str, display_name: str,
                       role: str = "user", sso_provider: str = None,
                       email: str = "", department: str = ""):
    """向 MySQL 插入用户（忽略重复）"""
    sess = _get_mysql_session()
    if sess is None:
        return False
    try:
        sess.execute(
            sa_text(
                """INSERT IGNORE INTO users (username, password_hash, display_name, role, sso_provider, email, department)
                   VALUES (:u, :ph, :dn, :r, :sp, :e, :d)"""
            ),
            {"u": username, "ph": password_hash, "dn": display_name, "r": role,
             "sp": sso_provider, "e": email, "d": department},
        )
        sess.commit()
        return True
    except Exception as e:
        logger.debug(f"MySQL 写用户失败: {e}")
        return False
    finally:
        sess.close()


def _mysql_update_last_login(username: str):
    """更新最后登录时间"""
    sess = _get_mysql_session()
    if sess is None:
        return
    try:
        sess.execute(
            sa_text("UPDATE users SET last_login_at = NOW() WHERE username = :u"),
            {"u": username},
        )
        sess.commit()
    except Exception:
        pass
    finally:
        sess.close()


def _mysql_migrate_memory_users():
    """启动时将内存用户迁移到 MySQL"""
    if not _users:
        return
    sess = _get_mysql_session()
    if sess is None:
        return
    try:
        count = sess.execute(sa_text("SELECT COUNT(*) FROM users")).fetchone()[0]
        if count > 0:
            return  # 已有数据，跳过
        for username, u in _users.items():
            sess.execute(
                sa_text(
                    """INSERT IGNORE INTO users (username, password_hash, display_name, role, sso_provider, email, department)
                       VALUES (:u, :ph, :dn, :r, :sp, :e, :d)"""
                ),
                {"u": username, "ph": u.get("password_hash", ""), "dn": u.get("display_name", username),
                 "r": u.get("role", "user"), "sp": u.get("sso_provider", None),
                 "e": u.get("email", ""), "d": u.get("department", "")},
            )
        sess.commit()
        logger.info(f"已迁移 {len(_users)} 个内存用户到 MySQL")
    except Exception as e:
        logger.debug(f"内存用户迁移跳过: {e}")
    finally:
        sess.close()


# ====== 密码工具 ======

def _hash_password(password: str) -> str:
    """bcrypt 密码哈希 (cost=12, 自动加盐)"""
    if not _BCRYPT_AVAILABLE:
        raise RuntimeError("bcrypt 未安装，请执行: pip install bcrypt")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    """验证密码"""
    if not _BCRYPT_AVAILABLE:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


# ====== 用户 CRUD ======

def create_user(username: str, password: str, display_name: str = "",
                role: str = "user", sso_provider: str = None,
                email: str = "", department: str = "") -> Optional[dict]:
    """注册新用户。返回用户信息或 None（用户名已存在）"""
    username = username.lower().strip()

    # 查重
    if username in _users:
        return None
    mysql_user = _mysql_find_user(username)
    if mysql_user:
        # 回填内存
        _users[username] = mysql_user
        return None

    pw_hash = _hash_password(password)
    user = {
        "username": username,
        "display_name": display_name or username,
        "password_hash": pw_hash,
        "created_at": datetime.now().isoformat(),
        "role": role,
        "sso_provider": sso_provider,
        "email": email,
        "department": department,
    }
    _users[username] = user

    # 写入 MySQL
    _mysql_insert_user(username, pw_hash, display_name or username, role,
                       sso_provider, email, department)

    return {"username": username, "display_name": user["display_name"], "role": role}


# ====== JWT Token 管理 ======

def _make_jwt(username: str, role: str) -> str:
    """签发 JWT access token"""
    if not _JWT_AVAILABLE:
        # 回退到旧式 opaque token (PyJWT 未安装时)
        token = secrets.token_hex(32)
        _tokens[token] = username
        return token

    payload = {
        "sub": username,
        "role": role,
        "jti": secrets.token_hex(8),  # 唯一 ID 确保同秒 token 不同
        "exp": datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _make_refresh_token(username: str) -> str:
    """签发 refresh token (随机 hex, 存 Redis/内存)"""
    token = secrets.token_hex(REFRESH_TOKEN_BYTES)
    # 内存兜底
    _tokens[f"refresh:{token}"] = username
    # Redis (如果可用)
    try:
        from app.memory.store import _get_redis
        redis = _get_redis()
        if redis:
            redis.setex(f"refresh:{token}", 86400 * 7, username)  # 7 天
    except Exception:
        pass
    return token


def authenticate(username: str, password: str) -> Optional[dict]:
    """验证用户密码。成功返回 {access_token, refresh_token, user}，失败返回 None"""
    username = username.lower().strip()

    # 1. 找用户: 内存 → MySQL
    user = _users.get(username)
    if not user:
        mysql_user = _mysql_find_user(username)
        if mysql_user:
            user = mysql_user
            _users[username] = user
    if not user:
        return None

    # 2. 验密码
    if not _verify_password(password, user["password_hash"]):
        return None

    # 3. 签发 JWT
    role = user.get("role", "user")
    access_token = _make_jwt(username, role)
    refresh_token = _make_refresh_token(username)

    # 4. 更新登录时间
    _mysql_update_last_login(username)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "username": username,
            "display_name": user.get("display_name", username),
            "role": role,
        },
    }


def get_user_by_token(token: str) -> Optional[dict]:
    """通过 JWT token 获取用户信息。返回 {username, display_name, role} 或 None"""
    # 检查黑名单 (登出撤销)
    if token in _token_blacklist:
        return None

    if _JWT_AVAILABLE:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            username = payload.get("sub")
            if not username:
                return None

            # 从内存/MySQL 取最新用户信息
            user = _users.get(username)
            if not user:
                mysql_user = _mysql_find_user(username)
                if mysql_user:
                    user = mysql_user
                    _users[username] = user
            if not user:
                return None

            return {
                "username": username,
                "display_name": user.get("display_name", username),
                "role": user.get("role", "user"),
            }
        except jwt.ExpiredSignatureError:
            logger.debug(f"JWT 过期: {token[:20]}...")
            return None
        except jwt.InvalidTokenError:
            logger.debug(f"JWT 无效: {token[:20]}...")
            return None

    # PyJWT 未安装: 回退到旧式 opaque token 查找
    username = _tokens.get(token)
    if not username:
        return None
    user = _users.get(username)
    if not user:
        return None
    return {
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
    }


def refresh_access_token(refresh_token: str) -> Optional[dict]:
    """用 refresh token 换新的 token pair (rotation)"""
    username = None

    # 1. Redis 查找
    try:
        from app.memory.store import _get_redis
        redis = _get_redis()
        if redis:
            username = redis.get(f"refresh:{refresh_token}")
            if username:
                redis.delete(f"refresh:{refresh_token}")  # 一次性使用
    except Exception:
        pass

    # 2. 内存兜底
    if not username:
        username = _tokens.pop(f"refresh:{refresh_token}", None)

    if not username:
        return None

    user = _users.get(username)
    if not user:
        mysql_user = _mysql_find_user(username)
        if mysql_user:
            user = mysql_user
            _users[username] = user
    if not user:
        return None

    role = user.get("role", "user")
    return {
        "access_token": _make_jwt(username, role),
        "refresh_token": _make_refresh_token(username),
        "user": {
            "username": username,
            "display_name": user.get("display_name", username),
            "role": role,
        },
    }


def logout(token: str):
    """登出 — 将 JWT 加入黑名单 (TTL = 剩余有效期)"""
    _token_blacklist.add(token)

    # 也加入 Redis 黑名单
    try:
        from app.memory.store import _get_redis
        redis = _get_redis()
        if redis and _JWT_AVAILABLE:
            try:
                payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM],
                                     options={"verify_exp": False})
                remaining = max(1, int((payload["exp"] - datetime.utcnow().timestamp())))
                redis.setex(f"blacklist:{token}", remaining, "1")
            except Exception:
                redis.setex(f"blacklist:{token}", TOKEN_EXPIRE_HOURS * 3600, "1")
    except Exception:
        pass

    # 清理旧式 token
    username = _tokens.pop(token, None)
    if username:
        for k, v in list(_tokens.items()):
            if v == username and k.startswith("refresh:"):
                del _tokens[k]


# ====== 默认用户（首次启动自动创建，仅开发环境） ======

def _create_default_users():
    """创建默认用户。仅在开发环境或显式启用时执行。"""
    import os
    app_env = os.getenv("APP_ENV", "development")
    create_default = os.getenv("CREATE_DEFAULT_USERS", "").lower()
    if create_default == "true" or (create_default != "false" and app_env == "development"):
        if "admin" not in _users and not _mysql_find_user("admin"):
            create_user("admin", "admin123", "管理员", role="admin")
            create_user("demo", "demo123", "体验用户", role="user")
            logger.warning("⚠ 默认用户已创建: admin/admin123, demo/demo123 — 生产环境请设置 CREATE_DEFAULT_USERS=false")


# 启动时: 迁移内存用户 → MySQL
_mysql_migrate_memory_users()
_create_default_users()


# ====== Pydantic Schemas ======


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=32)
    password: str = Field(..., min_length=4, max_length=64)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=32)
    password: str = Field(..., min_length=4, max_length=64)
    display_name: str = Field(default="")


class UserInfo(BaseModel):
    username: str
    display_name: str
    role: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str = ""
    token_type: str = "bearer"
    user: UserInfo
