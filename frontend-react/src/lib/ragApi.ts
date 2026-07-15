/** 知识库 RAG 前端接口。 */

import { authHeader } from "../stores/authStore";

export const RAG_BASE = "/api/rag";

export interface Citation {
  citation_id: string;
  document_id: string;
  chunk_id: string;
  filename: string;
  page?: number | null;
  chunk_index?: number | null;
  excerpt: string;
  score?: number | null;
}

export interface RagEvent {
  type: "status" | "retrieval" | "content" | "replace_content" | "done" | "error";
  content?: string;
  message?: string;
  sources?: Citation[];
  timings_ms?: Record<string, number>;
  retrieved_count?: number;
  candidate_count?: number;
  query_rewritten?: boolean;
}

export interface Evidence {
  document_id: string;
  chunk_id: string;
  filename: string;
  page?: number | null;
  content: string;
  nearby: { chunk_id: string; content: string; page?: number | null; chunk_index?: number | null }[];
}

export function streamRagAnswer(
  body: { question: string; session_id: string; history: { role: "user" | "assistant"; content: string }[] },
  onEvent: (event: RagEvent) => void,
  onError: (message: string) => void,
): AbortController {
  const controller = new AbortController();
  fetch(`${RAG_BASE}/answers/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify(body),
    signal: controller.signal,
  }).then(async (response) => {
    if (!response.ok || !response.body) {
      onError(`请求失败（HTTP ${response.status}）`);
      return;
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try { onEvent(JSON.parse(line.slice(6)) as RagEvent); } catch { /* 忽略损坏事件 */ }
      }
    }
  }).catch((error: unknown) => {
    if (!(error instanceof DOMException && error.name === "AbortError")) {
      onError(error instanceof Error ? error.message : "连接失败");
    }
  });
  return controller;
}

export async function getEvidence(documentId: string, chunkId: string): Promise<Evidence> {
  const response = await fetch(`${RAG_BASE}/citations/${encodeURIComponent(documentId)}/${encodeURIComponent(chunkId)}`, {
    headers: authHeader(),
  });
  if (!response.ok) throw new Error("无法读取引用证据");
  return response.json();
}

export async function submitRagFeedback(payload: {
  question: string; answer: string; verdict: "useful" | "not_useful" | "wrong_source";
  sources: Citation[]; citation_id?: string;
}): Promise<void> {
  const response = await fetch(`${RAG_BASE}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error("反馈提交失败");
}
