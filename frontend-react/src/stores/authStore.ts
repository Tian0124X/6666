import { create } from "zustand";

export interface User {
  username: string;
  display_name: string;
  role: string;
}

export interface AuthProvider {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  fields: string[];
}

function saveAuth(access_token: string, refresh_token: string, user: User) {
  localStorage.setItem("auth_token", access_token);
  if (refresh_token) localStorage.setItem("auth_refresh", refresh_token);
  localStorage.setItem("auth_user", JSON.stringify(user));
}

function clearAuth() {
  localStorage.removeItem("auth_token");
  localStorage.removeItem("auth_refresh");
  localStorage.removeItem("auth_user");
}

interface AuthStore {
  user: User | null;
  token: string | null;
  refreshToken: string | null;
  isLoggedIn: boolean;
  isRestoring: boolean;  // 初始化中，避免闪烁跳转 /login
  providers: AuthProvider[];
  login: (username: string, password: string) => Promise<void>;
  loginLdap: (username: string, password: string) => Promise<void>;
  loginOidc: () => Promise<void>;
  handleOidcCallback: (code: string, state: string) => Promise<void>;
  register: (username: string, password: string, displayName: string) => Promise<void>;
  logout: () => void;
  restore: () => void;
  refreshAuth: () => Promise<boolean>;
  fetchProviders: () => Promise<void>;
}

const API = "/api/auth";

export const useAuthStore = create<AuthStore>((set, get) => ({
  user: null,
  token: null,
  refreshToken: null,
  isLoggedIn: false,
  isRestoring: true,  // 启动时先显示 loading，等 restore 完成再判断
  providers: [{ id: "local", name: "本地账号登录", description: "", enabled: true, fields: ["username", "password"] }],

  login: async (username, password) => {
    const res = await fetch(`${API}/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "登录失败");
    }
    const data = await res.json();
    saveAuth(data.access_token, data.refresh_token || "", data.user);
    set({ token: data.access_token, refreshToken: data.refresh_token || "", user: data.user, isLoggedIn: true });
  },

  loginLdap: async (username, password) => {
    const res = await fetch(`${API}/ldap/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "LDAP 登录失败");
    }
    const data = await res.json();
    saveAuth(data.access_token, data.refresh_token || "", data.user);
    set({ token: data.access_token, refreshToken: data.refresh_token || "", user: data.user, isLoggedIn: true });
  },

  loginOidc: async () => {
    const res = await fetch(`${API}/oidc/authorize?redirect_uri=${encodeURIComponent(window.location.origin + "/login")}`);
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "获取 SSO 授权 URL 失败");
    }
    const data = await res.json();
    // 跳转到 IdP 登录页
    window.location.href = data.authorization_url;
  },

  handleOidcCallback: async (code, state) => {
    const res = await fetch(`${API}/oidc/callback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, state }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "SSO 登录失败");
    }
    const data = await res.json();
    saveAuth(data.access_token, data.refresh_token || "", data.user);
    set({ token: data.access_token, refreshToken: data.refresh_token || "", user: data.user, isLoggedIn: true });
  },

  register: async (username, password, displayName) => {
    const res = await fetch(`${API}/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, display_name: displayName }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "注册失败");
    }
    const data = await res.json();
    saveAuth(data.access_token, data.refresh_token || "", data.user);
    set({ token: data.access_token, refreshToken: data.refresh_token || "", user: data.user, isLoggedIn: true });
  },

  logout: () => {
    clearAuth();
    fetch(`${API}/logout`, { method: "POST", headers: authHeader() }).catch(() => {});
    set({ token: null, refreshToken: null, user: null, isLoggedIn: false });
  },

  restore: () => {
    const token = localStorage.getItem("auth_token");
    const refresh = localStorage.getItem("auth_refresh") || "";
    const user = localStorage.getItem("auth_user");
    if (token && user) {
      try {
        set({ token, refreshToken: refresh, user: JSON.parse(user), isLoggedIn: true, isRestoring: false });
      } catch {
        clearAuth();
        set({ isRestoring: false });
      }
    } else {
      set({ isRestoring: false });
    }
  },

  refreshAuth: async () => {
    const refresh = get().refreshToken || localStorage.getItem("auth_refresh");
    if (!refresh) return false;
    try {
      const res = await fetch(`${API}/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (!res.ok) return false;
      const data = await res.json();
      saveAuth(data.access_token, data.refresh_token || "", data.user);
      set({ token: data.access_token, refreshToken: data.refresh_token || "", user: data.user, isLoggedIn: true });
      return true;
    } catch {
      return false;
    }
  },

  fetchProviders: async () => {
    try {
      const res = await fetch(`${API}/providers`);
      if (res.ok) {
        const data = await res.json();
        set({ providers: data.providers });
      }
    } catch {
      // 默认只显示本地登录
    }
  },
}));

export function authHeader(): Record<string, string> {
  const token = localStorage.getItem("auth_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}
