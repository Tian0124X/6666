/** 纯 RAG 产品的最小导航外壳。 */

import { BookOpen, FileSearch, LogOut, MessageSquare, Moon, Sun } from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuthStore } from "../stores/authStore";
import { useThemeStore } from "../stores/themeStore";

const navigation = [
  { to: "/", label: "RAG 问答", icon: MessageSquare },
  { to: "/knowledge", label: "知识库管理", icon: BookOpen },
];

export function Layout() {
  const { theme, toggle } = useThemeStore();
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();
  return <div className="flex min-h-screen bg-kb-bg dark:bg-[#0a1628]">
    <aside className="hidden w-60 shrink-0 border-r border-kb-border bg-kb-card p-4 lg:flex lg:flex-col dark:bg-[#0f1f35]">
      <div className="flex items-center gap-3 px-2 py-3"><span className="grid h-9 w-9 place-items-center bg-kb-ink text-white dark:bg-kb-accent"><FileSearch className="h-4 w-4" /></span><div><h1 className="font-[var(--font-display)] text-lg font-semibold text-kb-ink">知识库 RAG</h1><p className="text-[11px] tracking-wide text-kb-muted">EVIDENCE FIRST</p></div></div>
      <p className="mt-8 px-2 text-[10px] font-semibold tracking-[0.16em] text-kb-muted">工作区</p>
      <nav className="mt-2 space-y-1">{navigation.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => `flex items-center gap-3 border-l-2 px-3 py-2.5 text-sm transition ${isActive ? "border-kb-accent bg-kb-surface font-medium text-kb-ink dark:bg-[#132238]" : "border-transparent text-kb-muted hover:bg-kb-surface hover:text-kb-ink dark:hover:bg-[#132238]"}`}><Icon className="h-4 w-4" />{label}</NavLink>)}</nav>
      <div className="mt-auto space-y-2 border-t border-kb-border pt-4"><p className="px-2 text-xs text-kb-muted truncate">{user?.display_name}</p><button onClick={toggle} className="flex w-full items-center gap-2 px-3 py-2 text-sm text-kb-muted transition hover:bg-kb-surface hover:text-kb-ink dark:hover:bg-[#132238]">{theme === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}{theme === "dark" ? "浅色模式" : "深色模式"}</button><button onClick={() => { logout(); navigate("/login"); }} className="flex w-full items-center gap-2 px-3 py-2 text-sm text-kb-muted transition hover:bg-kb-surface hover:text-kb-ink dark:hover:bg-[#132238]"><LogOut className="w-4 h-4" />退出登录</button></div>
    </aside>
    <main className="flex-1 min-w-0"><Outlet /></main>
  </div>;
}
