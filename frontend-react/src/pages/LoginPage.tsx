import { useState, useEffect } from "react";
import { useAuthStore, type AuthProvider } from "../stores/authStore";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Bot, LogIn, UserPlus, Loader2, Building2, Shield } from "lucide-react";

export default function LoginPage() {
  const [isLogin, setIsLogin] = useState(true);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [activeProvider, setActiveProvider] = useState<string>("local");

  const { login, loginLdap, loginOidc, handleOidcCallback, register, providers, fetchProviders } = useAuthStore();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // 页面加载时获取可用的认证方式
  useEffect(() => {
    fetchProviders();
  }, [fetchProviders]);

  // OIDC 回调处理: /login?code=xxx&state=yyy
  useEffect(() => {
    const code = searchParams.get("code");
    const state = searchParams.get("state");
    if (code) {
      setLoading(true);
      setError("");
      handleOidcCallback(code, state || "")
        .then(() => navigate("/"))
        .catch((err: unknown) => {
          setError(err instanceof Error ? err.message : "SSO 登录失败");
          // 清除 URL 参数
          window.history.replaceState({}, "", "/login");
        })
        .finally(() => setLoading(false));
    }
  }, [searchParams, handleOidcCallback, navigate]);

  const currentProvider = providers.find((p) => p.id === activeProvider) || providers[0];
  const isLocal = activeProvider === "local";
  const isLdap = activeProvider === "ldap";
  const isOidc = activeProvider === "oidc";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (isOidc) {
        await loginOidc();
        // loginOidc 会跳转，不会执行到下面
        return;
      }

      if (isLogin) {
        if (isLdap) {
          await loginLdap(username, password);
        } else {
          await login(username, password);
        }
      } else {
        await register(username, password, displayName || username);
      }
      navigate("/");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "操作失败");
    }
    setLoading(false);
  };

  // OIDC 加载中（回调处理）
  if (loading && isOidc) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--color-background)]">
        <div className="text-center space-y-4">
          <Loader2 className="w-12 h-12 animate-spin text-blue-600 mx-auto" />
          <p className="text-lg font-medium text-[var(--color-foreground)]">正在通过企业 SSO 登录...</p>
          <p className="text-sm text-[var(--color-muted-foreground)]">请稍候，正在验证您的身份</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--color-background)]">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="w-16 h-16 rounded-2xl bg-blue-600 flex items-center justify-center mx-auto mb-4">
            <Bot className="w-9 h-9 text-white" />
          </div>
          <h1 className="text-xl font-bold text-[var(--color-foreground)]">企业智能办公助手</h1>
          <p className="text-sm text-[var(--color-muted-foreground)] mt-1">
            {isLogin ? "选择登录方式" : "创建新账户"}
          </p>
        </div>

        {/* Provider Tabs — 仅在登录模式且有多个 provider 时显示 */}
        {isLogin && providers.filter(p => p.enabled).length > 1 && (
          <div className="flex gap-1 p-1 bg-[var(--color-accent)]/30 rounded-lg mb-4">
            {providers.filter(p => p.enabled).map((p) => (
              <button
                key={p.id}
                onClick={() => { setActiveProvider(p.id); setError(""); }}
                className={`flex-1 py-2 px-3 rounded-md text-xs font-medium transition-all flex items-center justify-center gap-1.5 ${
                  activeProvider === p.id
                    ? "bg-[var(--color-card)] text-[var(--color-foreground)] shadow-sm"
                    : "text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]"
                }`}
              >
                {p.id === "local" && <Shield className="w-3.5 h-3.5" />}
                {p.id === "ldap" && <Building2 className="w-3.5 h-3.5" />}
                {p.id === "oidc" && <Shield className="w-3.5 h-3.5" />}
                {p.id === "local" ? "本地" : p.id === "ldap" ? "域账号" : "企业SSO"}
              </button>
            ))}
          </div>
        )}

        {/* Provider description */}
        {isLogin && currentProvider && (
          <p className="text-xs text-[var(--color-muted-foreground)] text-center mb-3">
            {currentProvider.description}
          </p>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-6 space-y-4">
          {/* OIDC: 只显示 SSO 按钮 */}
          {isLogin && isOidc ? (
            <div className="space-y-4">
              <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4 text-center">
                <p className="text-sm text-blue-700 dark:text-blue-300">
                  点击下方按钮跳转到公司统一身份认证平台进行登录
                </p>
              </div>
              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 rounded-lg bg-blue-600 text-white font-medium text-sm hover:bg-blue-700 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Building2 className="w-4 h-4" />}
                企业 SSO 单点登录
              </button>
            </div>
          ) : (
            <>
              {/* 用户名 + 密码字段 (local / ldap) */}
              <div>
                <label className="text-xs text-[var(--color-muted-foreground)] block mb-1">
                  {isLdap ? "域账号 (Domain\\Username)" : "用户名"}
                </label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder={isLdap ? "输入域账号" : "输入用户名"}
                  required
                  minLength={2}
                  className="w-full px-3 py-2.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="text-xs text-[var(--color-muted-foreground)] block mb-1">密码</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="输入密码"
                  required
                  minLength={4}
                  className="w-full px-3 py-2.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>

              {/* 注册额外字段 */}
              {!isLogin && (
                <div>
                  <label className="text-xs text-[var(--color-muted-foreground)] block mb-1">显示名称 (可选)</label>
                  <input
                    type="text"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    placeholder="你的名字"
                    className="w-full px-3 py-2.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                  />
                </div>
              )}

              {error && (
                <div className="bg-red-50 dark:bg-red-900/20 rounded-lg px-3 py-2">
                  <p className="text-red-600 dark:text-red-400 text-xs">{error}</p>
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 rounded-lg bg-blue-600 text-white font-medium text-sm hover:bg-blue-700 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : isLogin ? <LogIn className="w-4 h-4" /> : <UserPlus className="w-4 h-4" />}
                {isLogin ? (isLdap ? "域账号登录" : "登录") : "注册"}
              </button>

              {/* 注册/登录切换 — 仅本地模式 */}
              {isLocal && (
                <>
                  <p className="text-center text-xs text-[var(--color-muted-foreground)]">
                    {isLogin ? "没有账户？" : "已有账户？"}
                    <button
                      type="button"
                      onClick={() => { setIsLogin(!isLogin); setError(""); }}
                      className="text-blue-600 hover:underline ml-1"
                    >
                      {isLogin ? "立即注册" : "去登录"}
                    </button>
                  </p>

                  {isLogin && (
                    <p className="text-center text-[10px] text-[var(--color-muted-foreground)]">
                      测试账户: admin / admin123 · demo / demo123
                    </p>
                  )}
                </>
              )}
            </>
          )}
        </form>
      </div>
    </div>
  );
}
