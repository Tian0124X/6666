"""认证 API — 登录/注册/登出/用户信息 + SSO/LDAP/OIDC"""

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.models.user import (
    LoginRequest, RegisterRequest, TokenResponse, UserInfo,
    authenticate, create_user, get_user_by_token, logout,
)
from pydantic import BaseModel

router = APIRouter()
security = HTTPBearer(auto_error=False)


# ====== JWT 依赖注入 ======


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> UserInfo:
    """从 Bearer token 解析当前用户。未登录返回匿名用户"""
    if credentials:
        user = get_user_by_token(credentials.credentials)
        if user:
            return UserInfo(**user)
    # 未登录：返回匿名用户（向后兼容）
    return UserInfo(username="anonymous", display_name="访客", role="guest")


async def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> UserInfo:
    """要求登录。未登录返回 401"""
    if credentials:
        user = get_user_by_token(credentials.credentials)
        if user:
            return UserInfo(**user)
    raise HTTPException(status_code=401, detail="请先登录")


# ====== Pydantic 模型 ======

class OidcCallbackRequest(BaseModel):
    code: str
    state: str = ""


class LdapLoginRequest(BaseModel):
    username: str
    password: str


# ====== 端点 ======


@router.post("/auth/login", response_model=TokenResponse, tags=["认证"])
async def login(req: LoginRequest):
    """本地用户登录"""
    token = authenticate(req.username, req.password)
    if not token:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    user = get_user_by_token(token)
    return TokenResponse(
        access_token=token,
        user=UserInfo(**user),
    )


@router.post("/auth/register", response_model=TokenResponse, tags=["认证"])
async def register(req: RegisterRequest):
    """用户注册"""
    result = create_user(req.username, req.password, req.display_name)
    if not result:
        raise HTTPException(status_code=409, detail="用户名已存在")

    token = authenticate(req.username, req.password)
    user = get_user_by_token(token)
    return TokenResponse(
        access_token=token,
        user=UserInfo(**user),
    )


@router.post("/auth/logout", tags=["认证"])
async def logout_endpoint(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    """登出"""
    if credentials:
        logout(credentials.credentials)
    return {"status": "ok", "message": "已登出"}


@router.get("/auth/me", response_model=UserInfo, tags=["认证"])
async def get_me(user: UserInfo = Depends(require_user)):
    """获取当前用户信息"""
    return user


# ====== 认证方式列表 ======


@router.get("/auth/providers", tags=["认证"])
async def list_providers():
    """返回当前启用的认证方式列表（供前端动态渲染登录入口）"""
    from app.auth.sso_mapping import get_auth_providers
    return {"providers": get_auth_providers()}


# ====== LDAP 登录 ======


@router.post("/auth/ldap/login", tags=["认证"])
async def ldap_login(req: LdapLoginRequest):
    """LDAP / AD 域账号登录"""
    from app.auth.ldap import ldap_authenticate, is_ldap_enabled

    if not is_ldap_enabled():
        raise HTTPException(status_code=400, detail="LDAP 认证未启用")

    ldap_user = ldap_authenticate(req.username, req.password)
    if not ldap_user:
        raise HTTPException(status_code=401, detail="LDAP 认证失败：用户名或密码错误")

    # SSO 映射 → 签发 JWT
    from app.auth.sso_mapping import get_or_create_sso_user
    result = get_or_create_sso_user(
        provider="ldap",
        external_id=ldap_user["username"],
        display_name=ldap_user.get("display_name", req.username),
        email=ldap_user.get("email", ""),
        department=ldap_user.get("department", ""),
    )
    if not result:
        raise HTTPException(status_code=500, detail="创建 SSO 用户失败")

    return TokenResponse(
        access_token=result["token"],
        user=UserInfo(
            username=result["username"],
            display_name=result["display_name"],
            role=result.get("role", "user"),
        ),
    )


# ====== OIDC SSO ======


@router.get("/auth/oidc/authorize", tags=["认证"])
async def oidc_authorize(redirect_uri: str = Query(default="")):
    """获取 OIDC 授权跳转 URL（前端重定向到 IdP 登录页）"""
    from app.auth.oidc import oidc_get_authorization_url, is_oidc_enabled

    if not is_oidc_enabled():
        raise HTTPException(status_code=400, detail="OIDC SSO 未启用")

    url = oidc_get_authorization_url(redirect_uri)
    if not url:
        raise HTTPException(status_code=500, detail="无法获取 OIDC 授权 URL，请检查配置")

    return {"authorization_url": url}


@router.post("/auth/oidc/callback", tags=["认证"])
async def oidc_callback(req: OidcCallbackRequest):
    """OIDC 回调：用授权码换取用户信息并签发 JWT"""
    from app.auth.oidc import oidc_exchange_code, is_oidc_enabled

    if not is_oidc_enabled():
        raise HTTPException(status_code=400, detail="OIDC SSO 未启用")

    oidc_user = oidc_exchange_code(req.code, req.state)
    if not oidc_user:
        raise HTTPException(status_code=401, detail="OIDC 认证失败：无法获取用户信息")

    # SSO 映射 → 签发 JWT
    from app.auth.sso_mapping import get_or_create_sso_user
    result = get_or_create_sso_user(
        provider="oidc",
        external_id=oidc_user.get("external_id", oidc_user["username"]),
        display_name=oidc_user.get("display_name", oidc_user["username"]),
        email=oidc_user.get("email", ""),
        department="",
    )
    if not result:
        raise HTTPException(status_code=500, detail="创建 SSO 用户失败")

    return TokenResponse(
        access_token=result["token"],
        user=UserInfo(
            username=result["username"],
            display_name=result["display_name"],
            role=result.get("role", "user"),
        ),
    )
