"""用户模型 — JWT 认证"""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel, Field


# ====== 简易内存用户存储 (生产换 MySQL) ======

_users: dict[str, dict] = {}
_tokens: dict[str, str] = {}  # token → username

JWT_SECRET = secrets.token_hex(32)
TOKEN_EXPIRE_HOURS = 24


def _hash_password(password: str, salt: str = "") -> tuple[str, str]:
    """SHA-256 密码哈希"""
    if not salt:
        salt = secrets.token_hex(16)
    h = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return h, salt


def create_user(username: str, password: str, display_name: str = "") -> Optional[dict]:
    """注册新用户。返回用户信息或 None（用户名已存在）"""
    username = username.lower().strip()
    if username in _users:
        return None

    pw_hash, salt = _hash_password(password)
    user = {
        "username": username,
        "display_name": display_name or username,
        "password_hash": pw_hash,
        "salt": salt,
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

    h, _ = _hash_password(password, user["salt"])
    if h != user["password_hash"]:
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


# ====== 默认用户（首次启动自动创建） ======

if "admin" not in _users:
    create_user("admin", "admin123", "管理员")
    create_user("demo", "demo123", "体验用户")


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
