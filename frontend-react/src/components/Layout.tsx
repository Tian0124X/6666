import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useThemeStore } from "../stores/themeStore";
import { useAuthStore } from "../stores/authStore";
import { useChatStore } from "../stores/chatStore";
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
  Plus,
  Trash2,
  MoreHorizontal,
  Pencil,
  Archive,
  ArchiveRestore,
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

function SessionSidebar() {
  const { user, isLoggedIn } = useAuthStore();
  const navigate = useNavigate();
  const {
    sessions,
    activeSessionId,
    sessionsLoaded,
    loadSessions,
    createSession,
    switchSession,
    deleteSession,
    renameSession,
    archiveSession,
  } = useChatStore();

  const [showMenu, setShowMenu] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [showArchived, setShowArchived] = useState(false);

  useEffect(() => {
    if (isLoggedIn && user && !sessionsLoaded) {
      loadSessions();
    }
  }, [isLoggedIn, user, sessionsLoaded, loadSessions]);

  if (!isLoggedIn || !user) return null;

  const activeSessions = sessions.filter((s) => !s.is_archived);
  const archivedSessions = sessions.filter((s) => s.is_archived);
  const displaySessions = showArchived ? archivedSessions : activeSessions;

  const handleNewSession = async () => {
    const sid = await createSession();
    if (sid) navigate("/");
  };

  const handleSwitch = async (sid: string) => {
    await switchSession(sid);
    navigate("/");
  };

  const handleDelete = async (sid: string) => {
    setShowMenu(null);
    if (!confirm("确定删除此会话及所有消息？此操作不可撤销。")) return;
    await deleteSession(sid);
  };

  const handleArchive = async (sid: string) => {
    setShowMenu(null);
    await archiveSession(sid, true);
  };

  const handleUnarchive = async (sid: string) => {
    setShowMenu(null);
    await archiveSession(sid, false);
  };

  const handleRenameStart = (sid: string, currentName: string) => {
    setShowMenu(null);
    setEditing(sid);
    setEditName(currentName);
  };

  const handleRenameSubmit = async (sid: string) => {
    if (editName.trim()) {
      await renameSession(sid, editName.trim());
    }
    setEditing(null);
  };

  const formatTime = (ts?: string) => {
    if (!ts) return "";
    try {
      const d = new Date(ts);
      const now = new Date();
      const diff = now.getTime() - d.getTime();
      if (diff < 86400000) return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
      if (diff < 604800000) return ["周日","周一","周二","周三","周四","周五","周六"][d.getDay()];
      return d.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
    } catch {
      return "";
    }
  };

  return (
    <div className="flex flex-col border-t border-border pt-2 pb-1">
      <div className="flex items-center justify-between px-3 mb-1">
        <span className="text-xs font-medium text-muted-foreground">对话列表</span>
        <div className="flex items-center gap-0.5">
          {archivedSessions.length > 0 && (
            <button
              onClick={() => setShowArchived(!showArchived)}
              className={`p-1 rounded text-[10px] transition-colors ${
                showArchived ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground"
              }`}
              title={showArchived ? "显示活跃对话" : "显示已归档"}
            >
              {showArchived ? "活跃" : "归档"}
            </button>
          )}
          <button
            onClick={handleNewSession}
            className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
            title="新建对话"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <div className="max-h-[40vh] overflow-y-auto px-1 space-y-0.5">
        {displaySessions.map((s) => (
          <div
            key={s.session_id}
            className={`group relative flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer text-xs transition-colors ${
              activeSessionId === s.session_id
                ? "bg-primary/10 text-primary font-medium"
                : "text-muted-foreground hover:bg-accent hover:text-foreground"
            }`}
            onClick={() => handleSwitch(s.session_id)}
          >
            {editing === s.session_id ? (
              <input
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                onBlur={() => handleRenameSubmit(s.session_id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleRenameSubmit(s.session_id);
                  if (e.key === "Escape") setEditing(null);
                }}
                onClick={(e) => e.stopPropagation()}
                className="flex-1 bg-transparent border-b border-primary outline-none text-xs"
                autoFocus
              />
            ) : (
              <>
                <MessageSquare className="w-3 h-3 shrink-0" />
                <span className="flex-1 truncate">{s.name}</span>
                <span className="text-[10px] opacity-50 shrink-0">{formatTime(s.updated_at)}</span>
              </>
            )}
            {/* Context menu trigger */}
            <div className="relative shrink-0">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setShowMenu(showMenu === s.session_id ? null : s.session_id);
                }}
                className="p-0.5 rounded opacity-0 group-hover:opacity-100 hover:bg-accent transition-all"
                title="更多操作"
              >
                <MoreHorizontal className="w-3 h-3" />
              </button>
              {showMenu === s.session_id && (
                <div
                  className="absolute right-0 top-full mt-1 bg-popover border border-border rounded-lg shadow-lg py-1 z-50 min-w-[100px]"
                  onClick={(e) => e.stopPropagation()}
                >
                  <button
                    onClick={() => handleRenameStart(s.session_id, s.name)}
                    className="flex items-center gap-2 w-full px-3 py-1.5 text-xs hover:bg-accent text-left"
                  >
                    <Pencil className="w-3 h-3" /> 重命名
                  </button>
                  {s.is_archived ? (
                    <button
                      onClick={() => handleUnarchive(s.session_id)}
                      className="flex items-center gap-2 w-full px-3 py-1.5 text-xs hover:bg-accent text-left"
                    >
                      <ArchiveRestore className="w-3 h-3" /> 取消归档
                    </button>
                  ) : (
                    <button
                      onClick={() => handleArchive(s.session_id)}
                      className="flex items-center gap-2 w-full px-3 py-1.5 text-xs hover:bg-accent text-left"
                    >
                      <Archive className="w-3 h-3" /> 归档
                    </button>
                  )}
                  <button
                    onClick={() => handleDelete(s.session_id)}
                    className="flex items-center gap-2 w-full px-3 py-1.5 text-xs hover:bg-accent text-red-500 text-left"
                  >
                    <Trash2 className="w-3 h-3" /> 删除
                  </button>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

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
      <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
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

        {/* Session list — between nav and footer */}
        <div className="pt-2">
          <SessionSidebar />
        </div>
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
  const resetChat = useChatStore((s) => s.reset);
  const navigate = useNavigate();

  if (!isLoggedIn || !user) return null;

  const handleLogout = () => {
    logout();
    resetChat();
    navigate("/login");
  };

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
        onClick={handleLogout}
        className="p-1.5 rounded-lg hover:bg-accent text-muted-foreground transition-colors"
        title="退出登录"
      >
        <LogOut className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
