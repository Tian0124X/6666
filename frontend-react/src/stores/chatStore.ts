import { create } from "zustand";

export interface DataResult {
  type: "dataframe" | "series" | "scalar" | "chart";
  columns?: string[];
  rows?: unknown[][];
  shape?: number[];
  value?: unknown;
  data?: Record<string, unknown>;
  name?: string;
  chart?: { type: string; x: string; y: string; title: string; data?: Record<string, unknown>[] };
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
}

interface ChatStore {
  messages: ChatMessage[];
  isStreaming: boolean;
  sessionId: string;
  addMessage: (msg: Omit<ChatMessage, "id">) => void;
  updateLastAssistant: (content: string) => void;
  setLastAssistantData: (data: { code?: string; dataResult?: DataResult }) => void;
  setStreaming: (v: boolean) => void;
  clearMessages: () => void;
}

export const useChatStore = create<ChatStore>((set) => ({
  messages: [],
  isStreaming: false,
  sessionId: "default",
  addMessage: (msg) =>
    set((s) => ({
      messages: [...s.messages, { ...msg, id: crypto.randomUUID() }],
    })),
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
}));
