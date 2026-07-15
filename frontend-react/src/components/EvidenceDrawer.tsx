/** 可点击引用的右侧证据抽屉。 */

import { useEffect, useState } from "react";
import { ExternalLink, FileText, Loader2, X } from "lucide-react";
import { getEvidence, RAG_BASE } from "../lib/ragApi";
import type { Citation, Evidence } from "../lib/ragApi";

export function EvidenceDrawer({ citation, onClose }: { citation: Citation | null; onClose: () => void }) {
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!citation) return;
    setEvidence(null);
    setError("");
    getEvidence(citation.document_id, citation.chunk_id).then(setEvidence).catch((err: unknown) => {
      setError(err instanceof Error ? err.message : "无法读取证据");
    });
  }, [citation]);

  if (!citation) return null;
  return (
    <aside className="fixed right-0 top-0 z-50 h-screen w-full max-w-xl overflow-y-auto border-l border-kb-border bg-kb-card p-6 shadow-2xl dark:bg-[#0f1f35]">
      <div className="mb-6 flex items-start justify-between gap-3 border-b border-kb-border pb-5">
        <div>
          <p className="text-xs font-semibold tracking-[0.14em] text-kb-accent">[{citation.citation_id}] 已采纳证据</p>
          <h3 className="mt-2 break-all font-[var(--font-display)] text-xl font-semibold text-kb-ink">{citation.filename}</h3>
          {citation.page != null && <p className="mt-1 text-sm text-kb-muted">第 {citation.page} 页</p>}
        </div>
        <button onClick={onClose} className="p-2 text-kb-muted hover:bg-kb-surface hover:text-kb-ink dark:hover:bg-[#132238]" aria-label="关闭证据抽屉"><X className="w-5 h-5" /></button>
      </div>
      {!evidence && !error && <div className="flex gap-2 text-sm text-kb-muted"><Loader2 className="w-4 h-4 animate-spin" />正在读取原始片段…</div>}
      {error && <p className="text-sm text-red-600">{error}</p>}
      {evidence && <>
        <section className="border border-amber-300/70 bg-amber-50 p-5 dark:border-amber-400/25 dark:bg-amber-400/10">
          <div className="mb-3 flex gap-2 text-sm font-medium text-kb-ink"><FileText className="w-4 h-4 text-amber-700 dark:text-amber-200" />命中原文</div>
          <p className="whitespace-pre-wrap text-sm leading-7 text-kb-ink">{evidence.content}</p>
        </section>
        {evidence.nearby.length > 0 && <section className="mt-5">
          <h4 className="mb-2 text-sm font-semibold text-kb-ink">相邻上下文</h4>
          <div className="space-y-2">{evidence.nearby.map((chunk) => (
            <p key={chunk.chunk_id} className="border-l border-kb-border bg-kb-surface p-3 text-sm leading-6 whitespace-pre-wrap text-kb-muted dark:bg-[#132238]">{chunk.content}</p>
          ))}</div>
        </section>}
        <a href={`${RAG_BASE}/documents/${encodeURIComponent(citation.document_id)}/download`} className="mt-6 inline-flex items-center gap-2 bg-kb-accent px-3 py-2 text-sm font-medium text-white hover:bg-[#126e65]">
          <ExternalLink className="w-4 h-4" />下载原文件
        </a>
      </>}
    </aside>
  );
}
