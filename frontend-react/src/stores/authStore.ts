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

interface AuthStore {
  user: User | null;
  token: string | null;
  isLoggedIn: boolean;
  providers: AuthProvider[];
  login: (username: string, password: string) => Promise<void>;
  loginLdap: (username: string, password: string) => Promise<void>;
  loginOidc: () => Promise<void>;
  handleOidcCallback: (code: string, state: string) => Promise<void>;
  register: (username: string, password: string, displayName: string) => Promise<void>;
  logout: () => void;
  restore: () => void;
  fetchProviders: () => Promise<void>;
}

const API = "/api/auth";

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  token: null,
  isLoggedIn: false,
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
    localStorage.setItem("auth_token", data.access_token);
    localStorage.setItem("auth_user", JSON.stringify(data.user));
    set({ token: data.access_token, user: data.user, isLoggedIn: true });
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
    localStorage.setItem("auth_token", data.access_token);
    localStorage.setItem("auth_user", JSON.stringify(data.user));
    set({ token: data.access_token, user: data.user, isLoggedIn: true });
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
    localStorage.setItem("auth_token", data.access_token);
    localStorage.setItem("auth_user", JSON.stringify(data.user));
    set({ token: data.access_token, user: data.user, isLoggedIn: true });
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
    localStorage.setItem("auth_token", data.access_token);
    localStorage.setItem("auth_user", JSON.stringify(data.user));
    set({ token: data.access_token, user: data.user, isLoggedIn: true });
  },

  logout: () => {
    localStorage.removeItem("auth_token");
    localStorage.removeItem("auth_user");
    fetch(`${API}/logout`, { method: "POST", headers: authHeader() }).catch(() => {});
    set({ token: null, user: null, isLoggedIn: false });
  },

  restore: () => {
    const token = localStorage.getItem("auth_token");
    const user = localStorage.getItem("auth_user");
    if (token && user) {
      try {
        set({ token, user: JSON.parse(user), isLoggedIn: true });
      } catch {
        localStorage.removeItem("auth_token");
        localStorage.removeItem("auth_user");
      }
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
