"""SSO 用户映射 — LDAP/OIDC 用户 → 本地 JWT 用户

映射策略:
1. 优先 MySQL (sso_user_map 表)，不可用时回退内存字典
2. 首次 SSO 登录自动创建本地映射 → 签发统一 JWT
3. 后续登录直接查映射 → 签发 JWT
"""

import logging
import secrets
from typing import Optional
from sqlalchemy import text as sa_text
from app.config import settings

logger = logging.getLogger(__name__)

# 内存回退: external_key → local_username
_sso_map_memory: dict[str, dict] = {}
_sso_table_checked = False


def _build_external_key(provider: str, external_id: str) -> str:
    """构建 SSO 映射键: provider:external_id"""
    return f"{provider}:{external_id}"


def _get_mysql_session():
    """获取 MySQL 会话，失败返回 None"""
    try:
        from app.models.database import get_session
        return get_session()
    except Exception:
        return None


def _ensure_sso_table(session) -> bool:
    """确保 sso_user_map 表存在（进程生命周期内只执行一次 DDL）"""
    global _sso_table_checked
    if _sso_table_checked:
        return True
    try:
        from app.models.database import Base
        from sqlalchemy import Column, String, TIMESTAMP, func

        # 懒检查：直接用 raw SQL 创建（避免 ORM 定义冲突）
        session.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS sso_user_map (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                external_key VARCHAR(256) NOT NULL UNIQUE,
                provider VARCHAR(32) NOT NULL,
                external_id VARCHAR(256) NOT NULL,
                local_username VARCHAR(64) NOT NULL,
                display_name VARCHAR(128) DEFAULT '',
                email VARCHAR(256) DEFAULT '',
                department VARCHAR(128) DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_local_username (local_username),
                INDEX idx_provider_external (provider, external_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))
        session.commit()
        _sso_table_checked = True
        return True
    except Exception as e:
        session.rollback()
        logger.debug(f"创建 sso_user_map 表失败: {e}")
        return False


def get_or_create_sso_user(
    provider: str,
    external_id: str,
    display_name: str = "",
    email: str = "",
    department: str = "",
) -> Optional[dict]:
    """SSO 用户查找或自动创建 → 返回本地用户信息 + JWT token。

    Args:
        provider: 认证提供方 (ldap / oidc)
        external_id: 外部系统的唯一用户 ID
        display_name: 显示名
        email: 邮箱
        department: 部门

    Returns:
        dict(username, display_name, role, token) 或 None
    """
    external_key = _build_external_key(provider, external_id)
    local_username = ""

    # === 1. 查 MySQL ===
    session = _get_mysql_session()
    if session:
        try:
            _ensure_sso_table(session)
            row = session.execute(
                sa_text("SELECT local_username, display_name FROM sso_user_map WHERE external_key = :key"),
                {"key": external_key},
            ).fetchone()

            if row:
                local_username = row[0]
                # 更新最后登录时间
                session.execute(
                    sa_text("UPDATE sso_user_map SET last_login_at = NOW() WHERE external_key = :key"),
                    {"key": external_key},
                )
                session.commit()
            else:
                # 创建新用户
                local_username = _generate_local_username(display_name, external_id, provider)
                session.execute(
                    sa_text(
                        """INSERT INTO sso_user_map
                           (external_key, provider, external_id, local_username, display_name, email, department)
                           VALUES (:key, :provider, :eid, :lun, :dn, :email, :dept)"""
                    ),
                    {
                        "key": external_key,
                        "provider": provider,
                        "eid": external_id,
                        "lun": local_username,
                        "dn": display_name or local_username,
                        "email": email,
                        "dept": department,
                    },
                )
                session.commit()
                logger.info(f"SSO 用户已创建: {external_key} → {local_username}")
            session.close()
        except Exception as e:
            session.close()
            logger.warning(f"MySQL SSO 映射失败，回退到内存: {e}")
            local_username = ""

    # === 2. 内存回退 ===
    if not local_username:
        if external_key in _sso_map_memory:
            local_username = _sso_map_memory[external_key]["local_username"]
        else:
            local_username = _generate_local_username(display_name, external_id, provider)
            _sso_map_memory[external_key] = {
                "local_username": local_username,
                "display_name": display_name,
                "provider": provider,
            }

    # === 3. 确保本地用户存在 ===
    from app.models.user import _users

    if local_username not in _users:
        from app.models.user import create_user
        create_user(
            username=local_username,
            password=secrets.token_hex(16),  # SSO 用户用随机密码（不可直接登录）
            display_name=display_name or local_username,
        )
        # 标记为 SSO 用户
        _users[local_username]["sso_provider"] = provider
        _users[local_username]["email"] = email
        _users[local_username]["department"] = department

    # === 4. 签发 JWT token ===
    from app.models.user import _make_jwt, _make_refresh_token
    role = _users[local_username].get("role", "user")
    access_token = _make_jwt(local_username, role)
    refresh_token = _make_refresh_token(local_username)

    return {
        "username": local_username,
        "display_name": _users[local_username]["display_name"],
        "role": role,
        "access_token": access_token,
        "refresh_token": refresh_token,
    }


def _generate_local_username(display_name: str, external_id: str, provider: str) -> str:
    """为 SSO 用户生成本地唯一用户名"""
    base = display_name or external_id or f"{provider}_user"
    # 转小写 + 去掉特殊字符
    base = "".join(c for c in base.lower() if c.isalnum() or c == "_")[:24]

    from app.models.user import _users

    username = base
    suffix = 1
    while username in _users:
        username = f"{base}_{suffix}"
        suffix += 1

    return username


def get_auth_providers() -> list[dict]:
    """返回当前可用的认证方式列表（供前端动态渲染登录入口）。

    Returns:
        [{id: "local", name: "本地登录", enabled: true}, ...]
    """
    providers = [
        {
            "id": "local",
            "name": "本地账号登录",
            "description": "使用平台注册的账号密码登录",
            "enabled": True,
            "fields": ["username", "password"],
        }
    ]

    if is_ldap_enabled_static():
        providers.append({
            "id": "ldap",
            "name": "企业 LDAP 登录",
            "description": "使用公司域账号登录 (Active Directory / LDAP)",
            "enabled": True,
            "fields": ["username", "password"],
        })

    if is_oidc_enabled_static():
        providers.append({
            "id": "oidc",
            "name": "企业 SSO 单点登录",
            "description": "通过公司统一身份认证平台登录",
            "enabled": True,
            "fields": [],  # 无需输入，跳转 IdP
        })

    return providers


def is_ldap_enabled_static() -> bool:
    """静态检查（避免循环导入）"""
    return bool(
        settings.LDAP_ENABLED
        and settings.LDAP_URL
        and settings.LDAP_BASE_DN
    )


def is_oidc_enabled_static() -> bool:
    """静态检查（避免循环导入）"""
    return bool(
        settings.OIDC_ENABLED
        and settings.OIDC_ISSUER
        and settings.OIDC_CLIENT_ID
        and settings.OIDC_CLIENT_SECRET
    )
