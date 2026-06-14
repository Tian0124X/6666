import { authHeader } from "../stores/authStore";

const BASE = "/api";

async function request<T>(
  url: string,
  options?: RequestInit
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...authHeader(),
  };
  const res = await fetch(`${BASE}${url}`, {
    headers,
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

/** SSE 流式请求 — 用于对话流式输出 */
export function streamChat(
  body: { message: string; session_id?: string; user_id?: string },
  onChunk: (text: string) => void,
  onDone: () => void,
  onError: (err: string) => void
): AbortController {
  const controller = new AbortController();

  fetch(`${BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify(body),
    signal: controller.signal,
  }).then(async (res) => {
    if (!res.ok || !res.body) {
      onError(`HTTP ${res.status}`);
      return;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            const data = JSON.parse(line.slice(6));
            if (data.content) onChunk(data.content);
            if (data.done) onDone();
            if (data.error) onError(data.error);
          } catch { /* skip malformed JSON */ }
        }
      }
    }
  }).catch((e) => {
    if (e.name !== "AbortError") onError(e.message);
  });

  return controller;
}

// === Chat API ===
export const chatApi = {
  send: (msg: string, sessionId = "default", userId = "anonymous") =>
    request<{ answer: string; task_type: string }>("/chat", {
      method: "POST",
      body: JSON.stringify({ message: msg, session_id: sessionId, user_id: userId }),
    }),
};

// === Tools API ===
export const toolsApi = {
  list: () => request<{ tools: { name: string; description: string }[] }>("/tools/list"),
  analyze: (file_path: string, action = "summary", target_column?: string, chart_type?: string) =>
    request<{ result: string }>("/tools/analyze", {
      method: "POST",
      body: JSON.stringify({ file_path, action, target_column, chart_type }),
    }),
  oa: (action = "list_approvals", value?: string) =>
    request<{ result: string }>(`/tools/oa?action=${action}&value=${encodeURIComponent(value || "")}`,
      { method: "POST" }),
  crm: (action = "list_customers", value?: string) =>
    request<{ result: string }>(`/tools/crm?action=${action}&value=${encodeURIComponent(value || "")}`,
      { method: "POST" }),
};

// === Knowledge API ===
export const knowledgeApi = {
  qa: (question: string, topK = 5) =>
    request<{ answer: string; sources: { filename: string; page: number | null; excerpt: string }[] }>(
      "/knowledge/qa", { method: "POST", body: JSON.stringify({ question, top_k: topK }) }
    ),
  smartQa: (question: string) =>
    request<{ answer: string; sources: { filename: string; page: number | null; excerpt: string }[] }>(
      "/knowledge/qa/smart", { method: "POST", body: JSON.stringify({ question }) }
    ),
  upload: async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${BASE}/knowledge/upload`, { method: "POST", body: fd });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },
  listDocs: () => request<{ total: number; indexed_documents: string[]; uploaded_files: string[] }>(
    "/knowledge/documents"
  ),
  deleteDoc: (filename: string) =>
    request<{ status: string }>(`/knowledge/documents/${encodeURIComponent(filename)}`, { method: "DELETE" }),
  indexStatus: () => request<Record<string, unknown>>("/knowledge/index/status"),
  rebuildIndex: (dir = "data/documents") =>
    request<Record<string, unknown>>(`/knowledge/index/rebuild?directory=${encodeURIComponent(dir)}`,
      { method: "POST" }),
};

// === System API ===
export const systemApi = {
  health: () => request<{ status: string; version: string }>("/health"),
  info: () => request<{ version: string; services: Record<string, string> }>("/info"),
};
