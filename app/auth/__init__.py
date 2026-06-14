"""企业 SSO/LDAP 认证模块

支持三种认证方式:
- 本地 (JWT + 内存用户)
- LDAP / Active Directory
- OAuth2 / OIDC (Keycloak / Okta / Azure AD 等)

通过 .env 配置开关控制启用哪些认证源。
"""

from app.auth.ldap import ldap_authenticate, is_ldap_enabled
from app.auth.oidc import oidc_get_authorization_url, oidc_exchange_code, is_oidc_enabled
from app.auth.sso_mapping import get_or_create_sso_user, get_auth_providers

__all__ = [
    "ldap_authenticate",
    "is_ldap_enabled",
    "oidc_get_authorization_url",
    "oidc_exchange_code",
    "is_oidc_enabled",
    "get_or_create_sso_user",
    "get_auth_providers",
]
