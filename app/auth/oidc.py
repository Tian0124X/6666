"""OAuth2 / OIDC 单点登录

支持标准 OIDC Provider (Keycloak, Okta, Azure AD, etc.)
流程: Authorization Code Flow + PKCE (可选)

依赖: httpx (已安装)
"""

import logging
import secrets
from typing import Optional
from app.config import settings

logger = logging.getLogger(__name__)

# 内存存储 state → redirect_uri 映射 (用于验证回调)
_oidc_states: dict[str, str] = {}


def is_oidc_enabled() -> bool:
    """检查 OIDC 是否已配置并启用"""
    return bool(
        settings.OIDC_ENABLED
        and settings.OIDC_ISSUER
        and settings.OIDC_CLIENT_ID
        and settings.OIDC_CLIENT_SECRET
    )


def _get_oidc_config() -> Optional[dict]:
    """从 issuer 获取 OIDC discovery 配置 (.well-known/openid-configuration)"""
    import httpx
    issuer = settings.OIDC_ISSUER.rstrip("/")
    url = f"{issuer}/.well-known/openid-configuration"

    try:
        r = httpx.get(url, timeout=10.0)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"获取 OIDC discovery 配置失败 [{issuer}]: {e}")
        return None


def oidc_get_authorization_url(redirect_uri: str = "") -> Optional[str]:
    """生成 OIDC 授权 URL (Authorization Code Flow)。

    Returns:
        跳转 URL 字符串，或 None (OIDC 未启用/配置错误)
    """
    if not is_oidc_enabled():
        return None

    oidc_config = _get_oidc_config()
    if not oidc_config:
        return None

    auth_endpoint = oidc_config.get("authorization_endpoint")
    if not auth_endpoint:
        logger.error("OIDC discovery 配置缺少 authorization_endpoint")
        return None

    # 生成随机 state 防 CSRF
    state = secrets.token_hex(16)
    redirect = redirect_uri or settings.OIDC_REDIRECT_URI
    _oidc_states[state] = redirect

    # 构建授权 URL
    params = {
        "response_type": "code",
        "client_id": settings.OIDC_CLIENT_ID,
        "redirect_uri": redirect,
        "scope": "openid profile email",
        "state": state,
    }

    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{auth_endpoint}?{query}"


def oidc_exchange_code(code: str, state: str = "") -> Optional[dict]:
    """用授权码换取用户信息 (Authorization Code → Token → UserInfo)。

    Args:
        code: IdP 回调返回的 authorization code
        state: 防 CSRF 的 state 参数

    Returns:
        dict(username, display_name, email, external_id) 或 None
    """
    if not is_oidc_enabled():
        return None

    # 验证 state (防 CSRF)
    if state and state in _oidc_states:
        redirect_uri = _oidc_states.pop(state)
    else:
        redirect_uri = settings.OIDC_REDIRECT_URI
        if state:
            logger.warning(f"OIDC state 不匹配: {state}")

    oidc_config = _get_oidc_config()
    if not oidc_config:
        return None

    token_endpoint = oidc_config.get("token_endpoint")
    if not token_endpoint:
        logger.error("OIDC discovery 配置缺少 token_endpoint")
        return None

    import httpx

    try:
        # Step 1: code → token
        token_resp = httpx.post(
            token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": settings.OIDC_CLIENT_ID,
                "client_secret": settings.OIDC_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
            },
            timeout=10.0,
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()

        access_token = token_data.get("access_token")
        if not access_token:
            logger.error(f"OIDC token 响应缺少 access_token: {token_data}")
            return None

        # Step 2: token → userinfo
        userinfo_endpoint = oidc_config.get("userinfo_endpoint")
        if not userinfo_endpoint:
            logger.error("OIDC discovery 配置缺少 userinfo_endpoint")
            return None

        user_resp = httpx.get(
            userinfo_endpoint,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10.0,
        )
        user_resp.raise_for_status()
        user_data = user_resp.json()

        # 提取用户信息
        username = (
            user_data.get("preferred_username")
            or user_data.get("sub", "")
        )
        display_name = (
            user_data.get("name")
            or user_data.get("given_name", username)
        )
        email = user_data.get("email", "")
        external_id = user_data.get("sub", username)

        return {
            "username": username.lower(),
            "display_name": display_name,
            "email": email,
            "external_id": external_id,
            "provider": "oidc",
        }

    except httpx.HTTPError as e:
        logger.error(f"OIDC token 交换失败: {e}")
        return None
    except Exception as e:
        logger.error(f"OIDC 回调处理异常: {e}")
        return None
