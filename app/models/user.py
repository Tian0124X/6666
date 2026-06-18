"""用户模型 — JWT 认证"""

import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel, Field

try:
    import bcrypt
    _BCRYPT_AVAILABLE = True
except ImportError:
    _BCRYPT_AVAILABLE = False

logger = logging.getLogger(__name__)

# ====== 简易内存用户存储 (生产换 MySQL) ======

_users: dict[str, dict] = {}
_tokens: dict[str, str] = {}  # token → username

JWT_SECRET = secrets.token_hex(32)
TOKEN_EXPIRE_HOURS = 24


def _hash_password(password: str) -> str:
    """bcrypt 密码哈希 (cost=12, 自动加盐)"""
    if not _BCRYPT_AVAILABLE:
        raise RuntimeError("bcrypt 未安装，请执行: pip install bcrypt")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def create_user(username: str, password: str, display_name: str = "") -> Optional[dict]:
    """注册新用户。返回用户信息或 None（用户名已存在）"""
    username = username.lower().strip()
    if username in _users:
        return None

    pw_hash = _hash_password(password)
    user = {
        "username": username,
        "display_name": display_name or username,
        "password_hash": pw_hash,
        "created_at": datetime.now().isoformat(),
        "role": "user",
    }
    _users[username] = user
    return {"username": username, "display_name": user["display_name"], "role": "user"}


def authenticate(username: str, password: str) -> Optional[str]:
    """验证用户密码。成功返回 JWT token，失败返回 None"""
    username = username.lower().strip()
    user = _users.get(username)
    if not user:
        return None

    if not _BCRYPT_AVAILABLE:
        logger.error("bcrypt 未安装，无法验证密码")
        return None

    if not bcrypt.checkpw(password.encode("utf-8"), user["password_hash"].encode("utf-8")):
        return None

    # 生成 token
    token = secrets.token_hex(32)
    _tokens[token] = username
    return token


def get_user_by_token(token: str) -> Optional[dict]:
    """通过 token 获取用户信息"""
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


def logout(token: str):
    """登出，销毁 token"""
    _tokens.pop(token, None)


# ====== 默认用户（首次启动自动创建，仅开发环境） ======

def _create_default_users():
    """创建默认用户。仅在开发环境或显式启用时执行。"""
    import os
    app_env = os.getenv("APP_ENV", "development")
    create_default = os.getenv("CREATE_DEFAULT_USERS", "").lower()
    if create_default == "true" or (create_default != "false" and app_env == "development"):
        if "admin" not in _users:
            create_user("admin", "admin123", "管理员")
            create_user("demo", "demo123", "体验用户")
            logger.warning("⚠ 默认用户已创建: admin/admin123, demo/demo123 — 生产环境请设置 CREATE_DEFAULT_USERS=false")

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
    token_type: str = "bearer"
    user: UserInfo
