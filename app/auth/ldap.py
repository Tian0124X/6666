"""LDAP / Active Directory 认证

依赖: ldap3 (纯 Python，无需编译)
"""

import logging
from typing import Optional
from app.config import settings

logger = logging.getLogger(__name__)


def is_ldap_enabled() -> bool:
    """检查 LDAP 是否已配置并启用"""
    return bool(
        settings.LDAP_ENABLED
        and settings.LDAP_URL
        and settings.LDAP_BASE_DN
    )


def ldap_authenticate(username: str, password: str) -> Optional[dict]:
    """LDAP 认证用户。

    Args:
        username: 登录用户名
        password: 密码

    Returns:
        dict(username, display_name, email, department) 或 None
    """
    if not is_ldap_enabled():
        logger.warning("LDAP 未启用，跳过 LDAP 认证")
        return None

    try:
        from ldap3 import Server, Connection, ALL, NTLM

        # 构建用户 DN
        user_dn = _build_user_dn(username)

        # 连接 LDAP 服务器
        server = Server(settings.LDAP_URL, get_info=ALL, connect_timeout=5)
        conn = Connection(
            server,
            user=user_dn,
            password=password,
            auto_bind=True,
            raise_exceptions=True,
        )

        # 搜索用户属性
        conn.search(
            search_base=settings.LDAP_BASE_DN,
            search_filter=f"(&(objectClass=person)(sAMAccountName={username}))",
            attributes=["displayName", "mail", "department", "cn"],
            size_limit=1,
        )

        display_name = username
        email = ""
        department = ""

        if conn.entries:
            entry = conn.entries[0]
            display_name = str(entry.displayName) if entry.displayName else str(entry.cn) if entry.cn else username
            email = str(entry.mail) if entry.mail else ""
            department = str(entry.department) if entry.department else ""

        conn.unbind()

        return {
            "username": username.lower(),
            "display_name": display_name,
            "email": email,
            "department": department,
        }

    except ImportError:
        logger.error("ldap3 未安装，无法使用 LDAP 认证。请执行: pip install ldap3")
        return None
    except Exception as e:
        logger.error(f"LDAP 认证失败 [{username}]: {e}")
        return None


def _build_user_dn(username: str) -> str:
    """根据模板构建用户 DN。

    支持模板变量:
    - {username} → 登录名
    - 若无模板则默认: cn={username},{LDAP_BASE_DN}
    """
    template = settings.LDAP_USER_DN_TEMPLATE
    if template:
        return template.format(username=username)
    return f"cn={username},{settings.LDAP_BASE_DN}"


def ldap_search_user(username: str) -> Optional[dict]:
    """搜索 LDAP 用户是否存在（只读操作，不验证密码）。"""
    if not is_ldap_enabled():
        return None

    try:
        from ldap3 import Server, Connection, ALL

        server = Server(settings.LDAP_URL, get_info=ALL, connect_timeout=5)
        conn = Connection(server, auto_bind=True)

        conn.search(
            search_base=settings.LDAP_BASE_DN,
            search_filter=f"(&(objectClass=person)(sAMAccountName={username}))",
            attributes=["displayName", "mail", "department", "cn"],
            size_limit=1,
        )

        if not conn.entries:
            conn.unbind()
            return None

        entry = conn.entries[0]
        conn.unbind()

        return {
            "username": username.lower(),
            "display_name": str(entry.displayName or entry.cn or username),
            "email": str(entry.mail or ""),
            "department": str(entry.department or ""),
        }
    except ImportError:
        return None
    except Exception as e:
        logger.debug(f"LDAP 搜索用户失败 [{username}]: {e}")
        return None
