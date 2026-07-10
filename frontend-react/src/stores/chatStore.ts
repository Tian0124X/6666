import { create } from "zustand";
import { sessionsApi } from "../lib/api";
import { authHeader } from "../stores/authStore";

export interface ChartConfig {
  type: "bar" | "line" | "pie" | "area" | "scatter" | "funnel" | "composed";
  x: string;
  y: string;
  x2?: string;
  title: string;
  data?: Record<string, unknown>[];
  series?: { dataKey: string; chartType: string }[];
}

export interface DataInsights {
  summary?: string;
  anomalies?: { column: string; count: number; percentage: number; range: string; description?: string }[];
  correlations?: { col_a: string; col_b: string; value: number; description: string }[];
  suggestions?: string[];
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
  insights?: DataInsights;
  suggestedQuestions?: string[];
  filePath?: string;
  reportUrl?: string;
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
  metadata?: Record<string, unknown>;  // 后端持久化的富数据
  // RAG 快速通道附加字段
  knowledgeMode?: string;
  knowledgeLevel?: number;
  fromCache?: boolean;
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
  setLastAssistantData: (data: { code?: string; dataResult?: DataResult; sources?: { filename: string; excerpt: string }[]; knowledgeMode?: string; knowledgeLevel?: number; fromCache?: boolean }) => void;
  setStreaming: (v: boolean) => void;
  clearMessages: () => void;
  cacheCurrentSession: () => void;

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

// crypto.randomUUID 在 HTTP 下不可用，使用 crypto.getRandomValues 替代
function uuid(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  // fallback: crypto.getRandomValues (HTTP 下也可用)
  return (([1e7] as any) + -1e3 + -4e3 + -8e3 + -1e11).replace(/[018]/g, (c: string) =>
    (parseInt(c) ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> parseInt(c) / 4).toString(16)
  );
}

const MAX_MESSAGES = 500;

// ====== localStorage 缓存 (L1 快速层) ======

const CACHE_PREFIX = "chat_cache:";
const CACHE_MAX_ENTRIES = 30;
const CACHE_MAX_SIZE = 4 * 1024 * 1024; // 4MB 上限

function _cacheMessages(sessionId: string, messages: ChatMessage[]) {
  try {
    // 只缓存有实质内容的消息(去掉 isStreaming 等临时字段)
    const slim = messages.map((m) => ({
      id: m.id,
      role: m.role,
      content: m.content,
      code: m.code,
      dataResult: m.dataResult,
      metadata: m.metadata,
      dataFilePath: m.dataFilePath,
    }));
    const key = CACHE_PREFIX + sessionId;
    const data = JSON.stringify(slim);
    // 超过大小限制则不缓存
    if (data.length > CACHE_MAX_SIZE) return;
    localStorage.setItem(key, data);
    // LRU 淘汰: 超过条目数时删除最旧的
    const keys: { key: string; idx: number }[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k?.startsWith(CACHE_PREFIX)) {
        keys.push({ key: k, idx: i });
      }
    }
    if (keys.length > CACHE_MAX_ENTRIES) {
      // 删除最早的一半
      keys.slice(0, Math.floor(keys.length / 2)).forEach((e) => localStorage.removeItem(e.key));
    }
  } catch { /* localStorage 不可用或满了，静默失败 */ }
}

function _loadCachedMessages(sessionId: string): ChatMessage[] | null {
  try {
    const raw = localStorage.getItem(CACHE_PREFIX + sessionId);
    if (!raw) return null;
    return JSON.parse(raw) as ChatMessage[];
  } catch {
    return null;
  }
}

function _clearCache(sessionId: string) {
  try { localStorage.removeItem(CACHE_PREFIX + sessionId); } catch { /* ignore */ }
}

/** 后端 metadata → 前端 DataResult */
function _metadataToDataResult(meta: Record<string, unknown>): DataResult | undefined {
  if (!meta || typeof meta !== "object") return undefined;
  const dr: DataResult = {};
  if (meta.table) {
    const t = meta.table as Record<string, unknown>;
    dr.type = "dataframe";
    dr.columns = t.columns as string[];
    dr.rows = t.rows as unknown[][];
    dr.shape = t.shape as number[];
  }
  if (meta.chart) dr.chart = meta.chart as ChartConfig;
  if (meta.code) dr.type = dr.type || "dataframe";
  if (meta.scalar != null) {
    dr.type = dr.type || "scalar";
    dr.value = meta.scalar;
  }
  if (meta.insights) dr.insights = meta.insights as DataInsights;
  if (meta.suggested_questions) dr.suggestedQuestions = meta.suggested_questions as string[];
  if (meta.file_path) dr.filePath = meta.file_path as string;
  if (meta.report_url) dr.reportUrl = meta.report_url as string;
  return Object.keys(dr).length > 0 ? dr : undefined;
}

export const useChatStore = create<ChatStore>((set, get) => ({
  messages: [],
  isStreaming: false,
  sessions: [],
  activeSessionId: "default",
  sessionsLoaded: false,
  _switchAbort: null,

  addMessage: (msg) =>
    set((s) => {
      const msgs = [...s.messages.slice(-(MAX_MESSAGES - 1)), { ...msg, id: uuid() }];
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

  cacheCurrentSession: () => {
    const { activeSessionId, messages } = get();
    if (activeSessionId && messages.length > 0) {
      _cacheMessages(activeSessionId, messages);
    }
  },

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

    // L1: 先用 localStorage 缓存即时显示 (包含图表)
    const cached = _loadCachedMessages(sessionId);
    set({ _switchAbort: ctrl, activeSessionId: sessionId, messages: cached || [] });

    try {
      const res = await fetch(`/api/chat/history/${sessionId}`, {
        headers: { ...authHeader() },
        signal: ctrl.signal,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      // 竞态保护: 确认 sessionId 仍然是当前活跃的
      if (get().activeSessionId !== sessionId) return;
      const msgs: ChatMessage[] = (data.messages || []).map(
        (m: { role: string; content: string; metadata?: Record<string, unknown> }) => {
          const dr = m.metadata ? _metadataToDataResult(m.metadata) : undefined;
          return {
            id: uuid(),
            role: (m.role === "assistant" ? "assistant" : "user") as "user" | "assistant",
            content: m.content || "",
            metadata: m.metadata,
            dataResult: dr,
            code: m.metadata?.code as string | undefined,
          };
        }
      );
      set({ messages: msgs });
      // 刷新缓存
      if (msgs.length > 0) _cacheMessages(sessionId, msgs);
    } catch (e: any) {
      if (e.name === "AbortError") return; // 被取消，正常
      console.warn("加载会话消息失败:", e);
      // API 失败时保留缓存数据不丢失
    }
  },

  deleteSession: async (sessionId) => {
    try {
      await sessionsApi.delete(sessionId);
      _clearCache(sessionId);
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
