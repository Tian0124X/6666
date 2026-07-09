import { authHeader, useAuthStore } from "../stores/authStore";

const BASE = "/api";

/** 全局 401 拦截：清掉过期 auth 状态，下次 navigate 到 /login */
function handleUnauthenticated() {
  const store = useAuthStore.getState();
  if (store.isLoggedIn) {
    store.logout();
    // 非侵入式跳转：如果不在 /login 页面就跳过去
    if (window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
  }
}

async function request<T>(
  url: string,
  options?: RequestInit & { timeout?: number }
): Promise<T> {
  const { timeout = 30_000, ...fetchOptions } = options || {};
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  try {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...authHeader(),
    };
    const res = await fetch(`${BASE}${url}`, {
      headers,
      ...fetchOptions,
      signal: controller.signal,
    });
    if (!res.ok) {
      // 401 → token 无效 (服务重启导致 JWT_SECRET 变化等)，自动登出
      if (res.status === 401) {
        handleUnauthenticated();
      }
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  } catch (e: any) {
    if (e.name === "AbortError") throw new Error("请求超时，请重试");
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

/** SSE 流式请求 — 用于对话流式输出 */
export function streamChat(
  body: { message: string; session_id?: string; user_id?: string; with_chart?: boolean },
  onChunk: (text: string) => void,
  onDone: () => void,
  onError: (err: string) => void,
  onData?: (data: {
    code?: string;
    table?: { columns: string[]; rows: unknown[][]; shape: number[] };
    chart?: Record<string, unknown>;
    scalar?: unknown;
    insights?: Record<string, unknown>;
    suggested_questions?: string[];
    file_path?: string;
    report_url?: string;
    // RAG 快速通道返回的结构化数据
    type?: string;
    sources?: { filename: string; page?: number; excerpt: string }[];
    mode?: string;
    level?: number;
    from_cache?: boolean;
  }) => void
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
    let hadError = false;
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
            if (data.report_url && onData) {
              onData({ report_url: data.report_url });
            }
            if (data.error) { hadError = true; onError(data.error); }
            // 富文本数据
            if (data.type === "data_result" && onData) {
              onData({
                code: data.code,
                table: data.table,
                chart: data.chart,
                scalar: data.scalar,
                insights: data.insights,
                suggested_questions: data.suggested_questions,
                file_path: data.file_path,
              });
            }
            // RAG 快速通道返回的结构化数据
            if (data.type === "knowledge_result" && onData) {
              onData({
                type: "knowledge_result",
                sources: data.sources,
                mode: data.mode,
                level: data.level,
                from_cache: data.from_cache,
              });
            }
            if (data.done && !hadError) onDone();
          } catch { /* skip malformed JSON */ }
        }
      }
    }
    // 处理残留 buffer
    if (buffer.startsWith("data: ")) {
      try {
        const data = JSON.parse(buffer.slice(6));
        if (data.content) onChunk(data.content);
        if (data.report_url && onData) onData({ report_url: data.report_url });
        if (data.error) { hadError = true; onError(data.error); }
        if (data.type === "data_result" && onData) {
          onData({ code: data.code, table: data.table, chart: data.chart, scalar: data.scalar, insights: data.insights, suggested_questions: data.suggested_questions, file_path: data.file_path });
        }
        if (data.type === "knowledge_result" && onData) {
          onData({ type: "knowledge_result", sources: data.sources, mode: data.mode, level: data.level, from_cache: data.from_cache });
        }
        if (data.done && !hadError) onDone();
      } catch { /* skip */ }
    }
    if (!hadError) onDone();
  }).catch((e) => {
    if (e.name !== "AbortError") onError(e.message);
  });

  return controller;
}

// === Chat API ===
export const chatApi = {
  send: (msg: string, sessionId = "default") =>
    request<{ answer: string; task_type: string }>("/chat", {
      method: "POST",
      body: JSON.stringify({ message: msg, session_id: sessionId }),
    }),
};

// === Sessions API ===
export const sessionsApi = {
  list: () => request<{ sessions: { session_id: string; user_id?: string; name: string; message_count: number; started_at?: string; updated_at?: string; created_at?: string }[]; total: number }>("/sessions"),
  create: (name?: string) => {
    const params = name ? `?name=${encodeURIComponent(name)}` : "";
    return request<{ session: { session_id: string; user_id: string; name: string; message_count: number; created_at: string } }>(`/sessions${params}`, { method: "POST" });
  },
  delete: (sessionId: string) => request<{ status: string }>(`/sessions/${sessionId}`, { method: "DELETE" }),
  rename: (sessionId: string, name: string) => request<{ status: string }>(`/sessions/${sessionId}?name=${encodeURIComponent(name)}`, { method: "PATCH" }),
  archive: (sessionId: string, archived = true) => request<{ status: string }>(`/sessions/${sessionId}/archive?archived=${archived}`, { method: "PATCH" }),
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
  dataChat: (file_path: string, question: string, session_id = "default") =>
    request<{ answer: string; code: string; result: Record<string, unknown> | null; chart: Record<string, unknown> | null }>(
      "/tools/data-chat", { method: "POST", body: JSON.stringify({ file_path, question, session_id }) }
    ),
};

// === Knowledge API ===
export const knowledgeApi = {
  qa: (question: string, topK = 5) =>
    request<{ answer: string; sources: { filename: string; page: number | null; excerpt: string }[] }>(
      "/knowledge/qa", { method: "POST", body: JSON.stringify({ question, top_k: topK }) }
    ),
  smartQa: (question: string) =>
    request<{
      answer: string;
      sources: { filename: string; page: number | null; excerpt: string }[];
      mode: string;
      level: number;
      from_cache: boolean;
      iterations: number;
    }>(
      "/knowledge/qa/smart", { method: "POST", body: JSON.stringify({ question }) }
    ),
  /** SSE 流式智能问答 — 实时推送检索进度 + 逐段回答 */
  streamSmartQa: (
    question: string,
    onStatus: (status: string) => void,
    onChunk: (text: string) => void,
    onData: (data: {
      sources?: { filename: string; page?: number; excerpt: string }[];
      mode?: string;
      level?: number;
      from_cache?: boolean;
      iterations?: number;
    }) => void,
    onDone: () => void,
    onError: (err: string) => void,
  ): AbortController => {
    const controller = new AbortController();

    fetch(`${BASE}/knowledge/qa/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeader() },
      body: JSON.stringify({ question }),
      signal: controller.signal,
    }).then(async (res) => {
      if (!res.ok || !res.body) {
        onError(`HTTP ${res.status}`);
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let hadError = false;
      try {
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
                if (data.status) onStatus(data.status);
                if (data.content) onChunk(data.content);
                if (data.type === "knowledge_result") {
                  onData({
                    sources: data.sources,
                    mode: data.mode,
                    level: data.level,
                    from_cache: data.from_cache,
                    iterations: data.iterations,
                  });
                }
                if (data.error) { hadError = true; onError(data.error); }
                if (data.done && !hadError) onDone();
              } catch { /* skip malformed JSON */ }
            }
          }
        }
        // 处理残留 buffer
        if (buffer.startsWith("data: ")) {
          try {
            const data = JSON.parse(buffer.slice(6));
            if (data.status) onStatus(data.status);
            if (data.content) onChunk(data.content);
            if (data.type === "knowledge_result") {
              onData({ sources: data.sources, mode: data.mode, level: data.level, from_cache: data.from_cache, iterations: data.iterations });
            }
            if (data.error) { hadError = true; onError(data.error); }
            if (data.done && !hadError) onDone();
          } catch { /* skip */ }
        }
        if (!hadError) onDone();
      } catch (e: any) {
        if (e.name !== "AbortError") onError(e.message);
      }
    }).catch((e) => {
      if (e.name !== "AbortError") onError(e.message);
    });

    return controller;
  },
  upload: async (file: File, onProgress?: (pct: number) => void) => {
    const fd = new FormData();
    fd.append("file", file);
    // 大文件使用 XMLHttpRequest 获取真实进度
    if (file.size > 10 * 1024 * 1024 && onProgress) {
      return new Promise<Record<string, unknown>>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", `${BASE}/knowledge/upload`);
        const authH = authHeader();
        Object.entries(authH).forEach(([k, v]) => xhr.setRequestHeader(k, v));
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 90));
        };
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            onProgress?.(100);
            resolve(JSON.parse(xhr.responseText));
          } else {
            reject(new Error(`HTTP ${xhr.status}`));
          }
        };
        xhr.onerror = () => reject(new Error("上传失败"));
        xhr.send(fd);
      });
    }
    const res = await fetch(`${BASE}/knowledge/upload`, {
      method: "POST",
      headers: { ...authHeader() },
      body: fd,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },
  uploadIndexStatus: (filename: string) =>
    request<{ filename: string; status: string; chunks: number; error?: string }>(
      `/knowledge/upload/status/${encodeURIComponent(filename)}`
    ),
  listDocs: () => request<{ total: number; indexed_documents: string[]; uploaded_files: string[] }>(
    "/knowledge/documents"
  ),
  deleteDoc: (filename: string) =>
    request<{ status: string }>(`/knowledge/documents/${encodeURIComponent(filename)}`, { method: "DELETE" }),
  indexStatus: () => request<Record<string, unknown>>("/knowledge/index/status"),
  rebuildIndex: (dir = "data/documents") =>
    request<Record<string, unknown>>(`/knowledge/index/rebuild?directory=${encodeURIComponent(dir)}`,
      { method: "POST" }),
  diagnostics: () => request<{
    vector_backend: string;
    document_count: number;
    bm25_status: string;
    bm25_document_count: number;
    reranker_available: boolean;
    llm_available: boolean;
    chromadb_url: string;
    pgvector_available: boolean;
    graph_backend: string;
    lightrag_available: boolean;
    neo4j_available: boolean;
    graph_stats: {
      nodes: number;
      relationships: number;
      type_distribution: { type: string; count: number }[];
    } | null;
  }>("/knowledge/diagnostics"),
};

// === Analytics API ===
export const analyticsApi = {
  overview: () => request<{
    today: { dau: number; requests: number; success_rate: number; avg_latency_ms: number; avg_rating: number | null; errors: number };
    knowledge: Record<string, number>;
    tools: { total_calls: number };
    performance: { latest_eval_accuracy: string | null; latest_eval_at: string | null };
  }>("/analytics/overview"),
  trends: (days = 7) => request<{ trends: { date: string; total: number; chat_start?: number; chat_end?: number }[]; days: number }>(
    `/analytics/trends?days=${days}`
  ),
  knowledge: () => request<{ rag_queries_today: number; top_tools: Record<string, number>; cache_hit_rate: number }>(
    "/analytics/knowledge"
  ),
  performance: () => request<{ p50: number; p95: number; p99: number; min: number; max: number; samples: number }>(
    "/analytics/performance"
  ),
};

// === System API ===
export const systemApi = {
  health: () => request<{ status: string; version: string }>("/health"),
  info: () => request<{ version: string; services: Record<string, string> }>("/info"),
};
