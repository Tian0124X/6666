import { create } from "zustand";
import { sessionsApi } from "../lib/api";
import { authHeader } from "../stores/authStore";

export interface ChartConfig {
  type: "bar" | "line" | "pie" | "scatter";
  x: string;
  y: string;
  title: string;
  data?: Record<string, unknown>[];
}

export interface DataResult {
  type?: "dataframe" | "series" | "scalar";
  columns?: string[];
  rows?: unknown[][];
  shape?: number[];
  value?: unknown;
  data?: Record<string, unknown>;
  name?: string;
  chart?: ChartConfig;
  report_path?: string;
  report_available?: boolean;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  sources?: { filename: string; excerpt: string }[];
  isStreaming?: boolean;
  taskType?: string;
  agents?: string[];
  code?: string;
  dataResult?: DataResult;
  dataFilePath?: string;
}

export interface SessionSummary {
  session_id: string;
  user_id?: string;
  name: string;
  message_count: number;
  started_at?: string;
  updated_at?: string;
  created_at?: string;
  preview?: string;
  is_archived?: number;
}

interface ChatStore {
  messages: ChatMessage[];
  isStreaming: boolean;

  // Session management (统一使用 activeSessionId)
  sessions: SessionSummary[];
  activeSessionId: string;
  sessionsLoaded: boolean;

  addMessage: (msg: Omit<ChatMessage, "id">) => void;
  updateLastAssistant: (content: string) => void;
  setLastAssistantData: (data: { code?: string; dataResult?: DataResult }) => void;
  setStreaming: (v: boolean) => void;
  clearMessages: () => void;

  // Session actions
  loadSessions: () => Promise<void>;
  createSession: (name?: string) => Promise<string>;
  switchSession: (sessionId: string) => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
  renameSession: (sessionId: string, name: string) => Promise<void>;
  archiveSession: (sessionId: string, archived?: boolean) => Promise<void>;
  ensureSession: () => Promise<string>;

  // Reset
  reset: () => void;

  // Internal
  _switchAbort: AbortController | null;
}

const MAX_MESSAGES = 500; // 从 100 提升到 500，避免长对话丢失

export const useChatStore = create<ChatStore>((set, get) => ({
  messages: [],
  isStreaming: false,
  sessions: [],
  activeSessionId: "default",
  sessionsLoaded: false,
  _switchAbort: null,

  addMessage: (msg) =>
    set((s) => {
      const msgs = [...s.messages.slice(-(MAX_MESSAGES - 1)), { ...msg, id: crypto.randomUUID() }];
      // 仅增加计数，不覆盖 (避免 switchSession 后重置)
      const sessions = s.sessions.map((ss) =>
        ss.session_id === s.activeSessionId
          ? { ...ss, message_count: ss.message_count + 1 }
          : ss
      );
      return { messages: msgs, sessions };
    }),

  updateLastAssistant: (content) =>
    set((s) => {
      const msgs = [...s.messages];
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === "assistant") {
          msgs[i] = { ...msgs[i], content: msgs[i].content + content };
          break;
        }
      }
      return { messages: msgs };
    }),

  setLastAssistantData: (data) =>
    set((s) => {
      const msgs = [...s.messages];
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === "assistant") {
          msgs[i] = { ...msgs[i], ...data };
          break;
        }
      }
      return { messages: msgs };
    }),

  setStreaming: (v) => set({ isStreaming: v }),
  clearMessages: () => set({ messages: [] }),

  // ====== Session management ======

  loadSessions: async () => {
    try {
      const data = await sessionsApi.list();
      set({ sessions: data.sessions, sessionsLoaded: true });
    } catch (e) {
      console.warn("加载会话列表失败:", e);
    }
  },

  createSession: async (name) => {
    try {
      const data = await sessionsApi.create(name);
      const sid = data.session.session_id;
      set((s) => ({
        sessions: [data.session, ...s.sessions],
        activeSessionId: sid,
        messages: [],
      }));
      return sid;
    } catch (e) {
      console.warn("创建会话失败:", e);
      return get().activeSessionId;
    }
  },

  switchSession: async (sessionId) => {
    // 取消之前的切换请求 (防竞态)
    const prev = get()._switchAbort;
    if (prev) prev.abort();
    const ctrl = new AbortController();
    set({ _switchAbort: ctrl, activeSessionId: sessionId, messages: [] });

    try {
      const res = await fetch(`/api/chat/history/${sessionId}`, {
        headers: { ...authHeader() },
        signal: ctrl.signal,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      // 竞态保护: 确认 sessionId 仍然是当前活跃的
      if (get().activeSessionId !== sessionId) return;
      const msgs = (data.messages || []).map((m: { role: string; content: string }) => ({
        id: crypto.randomUUID(),
        role: (m.role === "assistant" ? "assistant" : "user") as "user" | "assistant",
        content: m.content || "",
      }));
      set({ messages: msgs });
    } catch (e: any) {
      if (e.name === "AbortError") return; // 被取消，正常
      console.warn("加载会话消息失败:", e);
    }
  },

  deleteSession: async (sessionId) => {
    try {
      await sessionsApi.delete(sessionId);
      set((s) => {
        const sessions = s.sessions.filter((ss) => ss.session_id !== sessionId);
        const activeSessionId = s.activeSessionId === sessionId
          ? (sessions[0]?.session_id || "default")
          : s.activeSessionId;
        const messages = s.activeSessionId === sessionId ? [] : s.messages;
        return { sessions, activeSessionId, messages };
      });
    } catch (e) {
      console.warn("删除会话失败:", e);
    }
  },

  renameSession: async (sessionId, name) => {
    try {
      await sessionsApi.rename(sessionId, name);
      set((s) => ({
        sessions: s.sessions.map((ss) =>
          ss.session_id === sessionId ? { ...ss, name } : ss
        ),
      }));
    } catch (e) {
      console.warn("重命名失败:", e);
    }
  },

  archiveSession: async (sessionId, archived = true) => {
    try {
      await sessionsApi.archive(sessionId, archived);
      set((s) => ({
        sessions: s.sessions.map((ss) =>
          ss.session_id === sessionId ? { ...ss, is_archived: archived ? 1 : 0 } : ss
        ),
      }));
    } catch (e) {
      console.warn("归档失败:", e);
    }
  },

  ensureSession: async () => {
    const { activeSessionId, sessionsLoaded, loadSessions, createSession } = get();
    if (!sessionsLoaded) await loadSessions();
    const { sessions } = get();
    if (activeSessionId === "default" || !sessions.find((s) => s.session_id === activeSessionId)) {
      if (sessions.length > 0) {
        const sid = sessions[0].session_id;
        await get().switchSession(sid);
        return sid;
      }
      return await createSession();
    }
    return activeSessionId;
  },

  reset: () => set({
    messages: [],
    sessions: [],
    activeSessionId: "default",
    sessionsLoaded: false,
    isStreaming: false,
    _switchAbort: null,
  }),
}));
