import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useThemeStore } from "../stores/themeStore";
import { useAuthStore } from "../stores/authStore";
import {
  Activity,
  Beaker,
  Clock,
  MessageSquare,
  Wrench,
  BookOpen,
  Settings,
  Sun,
  Moon,
  Bot,
  LogOut,
  User,
  Zap,
} from "lucide-react";

const nav = [
  { to: "/", icon: MessageSquare, label: "智能对话" },
  { to: "/history", icon: Clock, label: "会话历史" },
  { to: "/tools", icon: Wrench, label: "工具测试" },
  { to: "/knowledge", icon: BookOpen, label: "知识库" },
  { to: "/monitoring", icon: Activity, label: "监控面板" },
  { to: "/analytics", icon: Zap, label: "深度分析" },
  { to: "/eval", icon: Beaker, label: "自动化评测" },
  { to: "/settings", icon: Settings, label: "偏好设置" },
];

export function Sidebar() {
  const { theme, toggle } = useThemeStore();

  return (
    <aside className="w-64 h-screen bg-card border-r border-border flex flex-col shrink-0">
      {/* Logo */}
      <div className="p-5 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary flex items-center justify-center">
            <Bot className="w-6 h-6 text-primary-foreground" />
          </div>
          <div>
            <h1 className="font-bold text-sm text-foreground">企业智能办公助手</h1>
            <p className="text-xs text-muted-foreground">v1.0.0</p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-3 space-y-1">
        {nav.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              }`
            }
          >
            <Icon className="w-5 h-5" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Theme toggle + footer */}
      <div className="p-4 border-t border-border space-y-3">
        <SidebarUser />
        <button
          onClick={toggle}
          className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm text-muted-foreground hover:bg-accent transition-colors"
        >
          {theme === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          {theme === "dark" ? "亮色模式" : "暗色模式"}
        </button>
        <p className="text-xs text-muted-foreground text-center">
          Powered by DeepSeek
        </p>
      </div>
    </aside>
  );
}

export function Layout() {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}

function SidebarUser() {
  const { user, isLoggedIn, logout } = useAuthStore();
  const navigate = useNavigate();

  if (!isLoggedIn || !user) return null;

  return (
    <div className="flex items-center justify-between px-1 py-1">
      <div className="flex items-center gap-2 text-sm">
        <div className="w-7 h-7 rounded-lg bg-primary flex items-center justify-center">
          <User className="w-3.5 h-3.5 text-primary-foreground" />
        </div>
        <span className="text-foreground text-xs font-medium truncate max-w-[100px]">
          {user.display_name}
        </span>
      </div>
      <button
        onClick={() => { logout(); navigate("/login"); }}
        className="p-1.5 rounded-lg hover:bg-accent text-muted-foreground transition-colors"
        title="退出登录"
      >
        <LogOut className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
