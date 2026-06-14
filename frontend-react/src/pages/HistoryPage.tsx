import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../stores/authStore";
import { useChatStore } from "../stores/chatStore";
import {
  MessageSquare, Search, Trash2, Clock, RefreshCw,
  ChevronRight, Loader2,
} from "lucide-react";

interface Session {
  session_id: string;
  user_id: string;
  started_at: string;
  updated_at: string;
  message_count: number;
  preview: string;
}

interface Message {
  role: string;
  content: string;
  time: string;
}

export default function HistoryPage() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loadingMsgs, setLoadingMsgs] = useState(false);

  const { user } = useAuthStore();
  const { clearMessages } = useChatStore();
  const navigate = useNavigate();

  const fetchSessions = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/chat/history");
      const data = await res.json();
      setSessions(data.sessions || []);
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchSessions(); }, [fetchSessions]);

  const viewSession = async (sid: string) => {
    setSelected(sid);
    setLoadingMsgs(true);
    try {
      const res = await fetch(`/api/chat/history/${sid}`);
      const data = await res.json();
      setMessages(data.messages || []);
    } catch { /* ignore */ }
    setLoadingMsgs(false);
  };

  const deleteSession = async (sid: string) => {
    if (!confirm("确定删除此会话？")) return;
    try {
      await fetch(`/api/chat/history/${sid}`, { method: "DELETE" });
      setSessions((s) => s.filter((x) => x.session_id !== sid));
      if (selected === sid) { setSelected(null); setMessages([]); }
    } catch { /* ignore */ }
  };

  const resumeSession = (sid: string) => {
    // Load messages into chat store and navigate to chat
    clearMessages();
    messages.forEach((m) => {
      useChatStore.getState().addMessage({
        role: m.role as "user" | "assistant",
        content: m.content,
      });
    });
    navigate("/");
  };

  const filtered = sessions.filter((s) =>
    s.preview.includes(search) ||
    s.session_id.toLowerCase().includes(search.toLowerCase()) ||
    (s.user_id || "").toLowerCase().includes(search.toLowerCase())
  );

  const now = new Date();

  return (
    <div className="h-screen flex">
      {/* Left: Session List */}
      <div className="w-80 border-r border-[var(--color-border)] bg-[var(--color-card)] flex flex-col shrink-0">
        <header className="p-4 border-b border-[var(--color-border)]">
          <h2 className="font-semibold text-[var(--color-foreground)] flex items-center gap-2">
            <MessageSquare className="w-5 h-5" />
            会话历史
          </h2>
          <div className="mt-3 relative">
            <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-[var(--color-muted-foreground)]" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索对话..."
              className="w-full pl-9 pr-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] text-xs focus:ring-2 focus:ring-blue-500 focus:outline-none"
            />
          </div>
          <button
            onClick={fetchSessions}
            className="mt-2 flex items-center gap-1 text-xs text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)] transition-colors"
          >
            <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
            刷新
          </button>
        </header>

        <div className="flex-1 overflow-auto">
          {loading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="w-5 h-5 animate-spin text-[var(--color-muted-foreground)]" />
            </div>
          ) : filtered.length === 0 ? (
            <p className="text-center text-sm text-[var(--color-muted-foreground)] py-12">
              {search ? "无匹配结果" : "暂无对话记录"}
            </p>
          ) : (
            filtered.map((s) => (
              <button
                key={s.session_id}
                onClick={() => viewSession(s.session_id)}
                className={`w-full text-left p-3 border-b border-[var(--color-border)] hover:bg-[var(--color-accent)] transition-colors ${
                  selected === s.session_id ? "bg-blue-50 dark:bg-blue-900/20 border-l-2 border-l-blue-500" : ""
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-mono text-[var(--color-muted-foreground)] truncate max-w-[180px]">
                    {s.user_id || "anonymous"} / {s.session_id.slice(0, 16)}
                  </span>
                  <button
                    onClick={(e) => { e.stopPropagation(); deleteSession(s.session_id); }}
                    className="p-0.5 rounded hover:bg-red-100 dark:hover:bg-red-900/30 text-[var(--color-muted-foreground)] hover:text-red-500 transition-colors"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
                <p className="text-xs text-[var(--color-foreground)] line-clamp-2 mb-1">
                  {s.preview || "(空)"}
                </p>
                <div className="flex items-center gap-3 text-[10px] text-[var(--color-muted-foreground)]">
                  <span className="flex items-center gap-1">
                    <MessageSquare className="w-3 h-3" /> {s.message_count}
                  </span>
                  {s.updated_at && (
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3" /> {formatTime(s.updated_at, now)}
                    </span>
                  )}
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Right: Message Detail */}
      <div className="flex-1 flex flex-col">
        <header className="p-4 border-b border-[var(--color-border)] bg-[var(--color-card)] flex items-center justify-between">
          <h3 className="font-medium text-sm text-[var(--color-foreground)]">
            {selected ? `会话详情` : "选择一个会话查看详情"}
          </h3>
          {selected && messages.length > 0 && (
            <button
              onClick={() => resumeSession(selected)}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-medium hover:bg-blue-700 transition-colors"
            >
              继续对话 <ChevronRight className="w-3 h-3" />
            </button>
          )}
        </header>

        <div className="flex-1 overflow-auto p-4">
          {loadingMsgs ? (
            <div className="flex justify-center py-12">
              <Loader2 className="w-5 h-5 animate-spin text-[var(--color-muted-foreground)]" />
            </div>
          ) : messages.length === 0 ? (
            <p className="text-center text-sm text-[var(--color-muted-foreground)] py-12">
              {selected ? "该会话无消息" : "← 左侧选择会话"}
            </p>
          ) : (
            <div className="max-w-3xl mx-auto space-y-3">
              {messages.map((m, i) => (
                <div
                  key={i}
                  className={`flex gap-3 ${m.role === "user" ? "flex-row-reverse" : ""}`}
                >
                  <div className="w-6 h-6 rounded-full bg-[var(--color-accent)] flex items-center justify-center shrink-0">
                    <span className="text-[10px]">{m.role === "user" ? "U" : "A"}</span>
                  </div>
                  <div
                    className={`max-w-[75%] rounded-xl px-3 py-2 text-sm ${
                      m.role === "user"
                        ? "bg-blue-600 text-white"
                        : "bg-[var(--color-card)] border border-[var(--color-border)]"
                    }`}
                  >
                    <p className="whitespace-pre-wrap">{m.content.slice(0, 500)}</p>
                    {m.time && (
                      <p className="text-[10px] opacity-50 mt-1">{formatTime(m.time, now)}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function formatTime(iso: string, now: Date): string {
  try {
    const d = new Date(iso);
    const diffMs = now.getTime() - d.getTime();
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return "刚刚";
    if (mins < 60) return `${mins}分钟前`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}小时前`;
    return d.toLocaleDateString("zh-CN");
  } catch {
    return "";
  }
}
