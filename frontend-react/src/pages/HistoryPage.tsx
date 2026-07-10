import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useChatStore } from "../stores/chatStore";
import { authHeader } from "../stores/authStore";
import {
  MessageSquare, Search, Trash2, Clock, RefreshCw,
  ChevronRight, Loader2, ChevronDown,
} from "lucide-react";

interface Message {
  role: string;
  content: string;
  time: string;
}

export default function HistoryPage() {
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loadingMsgs, setLoadingMsgs] = useState(false);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const {
    sessions,
    sessionsLoaded,
    loadSessions,
    switchSession,
    deleteSession,
  } = useChatStore();
  const navigate = useNavigate();

  useEffect(() => {
    if (!sessionsLoaded) loadSessions();
  }, [sessionsLoaded, loadSessions]);

  const refresh = useCallback(() => {
    loadSessions();
  }, [loadSessions]);

  const viewSession = async (sid: string) => {
    setSelected(sid);
    setLoadingMsgs(true);
    setExpanded(new Set());
    try {
      const res = await fetch(`/api/chat/history/${sid}`, { headers: { ...authHeader() } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setMessages(data.messages || []);
    } catch {
      setMessages([]);
    }
    setLoadingMsgs(false);
  };

  const handleDelete = async (sid: string) => {
    if (!confirm("确定删除此会话及其所有消息？")) return;
    await deleteSession(sid);
    if (selected === sid) { setSelected(null); setMessages([]); }
    refresh();
  };

  const handleResume = async (sid: string) => {
    await switchSession(sid);
    navigate("/");
  };

  // 按轮次分组：user+assistant 对
  const turns: { user: Message; assistant: Message | null }[] = [];
  for (let i = 0; i < messages.length; i++) {
    if (messages[i].role === "user") {
      const assistant = messages[i + 1]?.role === "assistant" ? messages[i + 1] : null;
      turns.push({ user: messages[i], assistant });
      if (assistant) i++;
    }
  }

  const filtered = sessions.filter((s) =>
    (s.name || "").toLowerCase().includes(search.toLowerCase()) ||
    s.session_id.toLowerCase().includes(search.toLowerCase()) ||
    (s.preview || "").toLowerCase().includes(search.toLowerCase())
  );

  const formatTime = (iso: string): string => {
    try {
      const d = new Date(iso);
      const now = new Date();
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
  };

  const toggleExpand = (idx: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx); else next.add(idx);
      return next;
    });
  };

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
              placeholder="搜索会话名称..."
              className="w-full pl-9 pr-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] text-xs focus:ring-2 focus:ring-blue-500 focus:outline-none"
            />
          </div>
          <button
            onClick={refresh}
            className="mt-2 flex items-center gap-1 text-xs text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)] transition-colors"
          >
            <RefreshCw className="w-3 h-3" />
            刷新
          </button>
        </header>

        <div className="flex-1 overflow-auto">
          {!sessionsLoaded ? (
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
                  <span className="text-xs font-medium text-[var(--color-foreground)] truncate max-w-[160px]">
                    {s.name || "未命名"}
                  </span>
                  <div className="flex items-center gap-1">
                    <span className="text-[10px] text-[var(--color-muted-foreground)]">
                      {s.message_count || 0}
                    </span>
                    <button
                      onClick={(e) => { e.stopPropagation(); handleDelete(s.session_id); }}
                      className="p-0.5 rounded hover:bg-red-100 dark:hover:bg-red-900/30 text-[var(--color-muted-foreground)] hover:text-red-500 transition-colors"
                      title="删除"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                </div>
                {(s.preview || s.name) && (
                  <p className="text-[10px] text-[var(--color-muted-foreground)] line-clamp-1 mb-1">
                    {s.preview || s.name}
                  </p>
                )}
                <div className="flex items-center gap-3 text-[10px] text-[var(--color-muted-foreground)]">
                  <span className="flex items-center gap-1">
                    <MessageSquare className="w-3 h-3" /> {s.message_count} 条
                  </span>
                  {s.updated_at && (
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3" /> {formatTime(s.updated_at)}
                    </span>
                  )}
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Right: Message Detail — 按轮次展开 */}
      <div className="flex-1 flex flex-col">
        <header className="p-4 border-b border-[var(--color-border)] bg-[var(--color-card)] flex items-center justify-between">
          <h3 className="font-medium text-sm text-[var(--color-foreground)]">
            {selected ? "会话详情" : "选择一个会话查看详情"}
          </h3>
          {selected && messages.length > 0 && (
            <button
              onClick={() => handleResume(selected)}
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
          ) : turns.length === 0 ? (
            <p className="text-center text-sm text-[var(--color-muted-foreground)] py-12">
              {selected ? "该会话无消息" : "← 左侧选择会话"}
            </p>
          ) : (
            <div className="max-w-3xl mx-auto space-y-3">
              {/* 会话信息卡 */}
              <div className="mb-4 px-4 py-3 rounded-xl bg-[var(--color-accent)]/50 text-xs text-[var(--color-muted-foreground)]">
                <span className="font-medium text-[var(--color-foreground)]">
                  {turns.length} 轮对话
                </span>
                <span className="mx-2">·</span>
                {messages.length} 条消息
                {messages[0]?.time && (
                  <>
                    <span className="mx-2">·</span>
                    始于 {formatTime(messages[0].time)}
                  </>
                )}
              </div>

              {turns.map((turn, idx) => (
                <div
                  key={idx}
                  className="rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] overflow-hidden"
                >
                  {/* 轮次标题：可点击展开 */}
                  <button
                    onClick={() => toggleExpand(idx)}
                    className="w-full flex items-center gap-2 px-4 py-2.5 hover:bg-[var(--color-accent)] transition-colors text-left"
                  >
                    <ChevronDown
                      className={`w-4 h-4 text-[var(--color-muted-foreground)] transition-transform ${
                        expanded.has(idx) ? "" : "-rotate-90"
                      }`}
                    />
                    <span className="text-sm font-medium text-[var(--color-foreground)]">
                      第 {idx + 1} 轮
                    </span>
                    <span className="text-xs text-[var(--color-muted-foreground)] truncate max-w-[400px]">
                      {(turn.user.content || "").slice(0, 80)}
                      {(turn.user.content || "").length > 80 ? "…" : ""}
                    </span>
                  </button>

                  {/* 展开内容 */}
                  {expanded.has(idx) && (
                    <div className="px-4 pb-4 space-y-3 border-t border-[var(--color-border)] pt-3">
                      {/* 用户消息 */}
                      <div className="flex gap-3">
                        <div className="w-6 h-6 rounded-full bg-blue-600 flex items-center justify-center shrink-0 mt-0.5">
                          <span className="text-[10px] text-white">U</span>
                        </div>
                        <div className="flex-1">
                          <p className="text-xs font-medium text-[var(--color-muted-foreground)] mb-1">用户</p>
                          <div className="bg-blue-600 text-white rounded-xl rounded-tl-sm px-3 py-2 text-sm">
                            <p className="whitespace-pre-wrap">{turn.user.content}</p>
                          </div>
                          {turn.user.time && (
                            <p className="text-[10px] text-[var(--color-muted-foreground)] mt-1">
                              {formatTime(turn.user.time)}
                            </p>
                          )}
                        </div>
                      </div>

                      {/* 助手消息 */}
                      {turn.assistant && (
                        <div className="flex gap-3">
                          <div className="w-6 h-6 rounded-full bg-green-600 flex items-center justify-center shrink-0 mt-0.5">
                            <span className="text-[10px] text-white">A</span>
                          </div>
                          <div className="flex-1">
                            <p className="text-xs font-medium text-[var(--color-muted-foreground)] mb-1">AI 助手</p>
                            <div className="bg-[var(--color-accent)] rounded-xl rounded-tl-sm px-3 py-2 text-sm">
                              <p className="whitespace-pre-wrap">{turn.assistant.content}</p>
                            </div>
                            {turn.assistant.time && (
                              <p className="text-[10px] text-[var(--color-muted-foreground)] mt-1">
                                {formatTime(turn.assistant.time)}
                              </p>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
