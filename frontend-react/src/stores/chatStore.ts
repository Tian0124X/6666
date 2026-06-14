import { create } from "zustand";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  sources?: { filename: string; excerpt: string }[];
  isStreaming?: boolean;
  taskType?: string;
  agents?: string[];
}

interface ChatStore {
  messages: ChatMessage[];
  isStreaming: boolean;
  sessionId: string;
  addMessage: (msg: Omit<ChatMessage, "id">) => void;
  updateLastAssistant: (content: string) => void;
  setStreaming: (v: boolean) => void;
  clearMessages: () => void;
}

export const useChatStore = create<ChatStore>((set, get) => ({
  messages: [],
  isStreaming: false,
  sessionId: "default",
  addMessage: (msg) =>
    set((s) => ({
      messages: [
        ...s.messages,
        { ...msg, id: crypto.randomUUID() },
      ],
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
  setStreaming: (v) => set({ isStreaming: v }),
  clearMessages: () => set({ messages: [] }),
}));
