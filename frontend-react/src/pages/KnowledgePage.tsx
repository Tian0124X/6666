/** 知识库文件工作台：上传成功、异步索引和可用状态全部可见。 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";
import { Check, CircleAlert, Clock3, FileText, FileUp, Loader2, RefreshCw, Send, Trash2, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { authHeader } from "../stores/authStore";

type DocumentStatus = "pending" | "indexing" | "done" | "error";
type DocumentItem = {
  filename: string;
  document_id?: string | null;
  status: DocumentStatus;
  stage?: string;
  chunks?: number;
  error?: string;
  completed_at?: string | null;
  size?: number | null;
  quality?: { file_sha256?: string };
  version?: { file_sha256?: string | null; indexed_at?: string | null };
  document_date?: string | null;
};

const supportedTypes = ".pdf,.docx,.xlsx,.xls,.txt,.csv";

function formatSize(size?: number | null) {
  if (!size) return "—";
  return size < 1024 * 1024 ? `${Math.round(size / 1024)} KB` : `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function StatusBadge({ status }: { status: DocumentStatus }) {
  const styles: Record<DocumentStatus, string> = {
    pending: "bg-slate-100 text-slate-600 dark:bg-slate-400/10 dark:text-slate-300",
    indexing: "bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-200",
    done: "bg-emerald-100 text-emerald-800 dark:bg-emerald-400/15 dark:text-emerald-200",
    error: "bg-red-100 text-red-800 dark:bg-red-400/15 dark:text-red-200",
  };
  const labels: Record<DocumentStatus, string> = { pending: "等待处理", indexing: "正在索引", done: "已就绪", error: "索引失败" };
  return <span className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-medium ${styles[status]}`}>{status === "done" ? <Check className="h-3 w-3" /> : status === "error" ? <CircleAlert className="h-3 w-3" /> : <Loader2 className={`h-3 w-3 ${status === "indexing" ? "animate-spin" : ""}`} />}{labels[status]}</span>;
}

export default function KnowledgePage() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [totalChunks, setTotalChunks] = useState(0);
  const [notice, setNotice] = useState("");
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [documentDate, setDocumentDate] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  const refresh = useCallback(async () => {
    const response = await fetch("/api/rag/documents", { headers: authHeader() });
    if (!response.ok) throw new Error("无法读取知识库");
    const data = await response.json() as { documents: DocumentItem[]; total_chunks: number };
    setDocuments(data.documents);
    setTotalChunks(data.total_chunks);
  }, []);

  useEffect(() => { refresh().catch((error: unknown) => setNotice(error instanceof Error ? error.message : "加载失败")); }, [refresh]);
  useEffect(() => {
    if (!documents.some((item) => item.status === "pending" || item.status === "indexing")) return;
    const timer = window.setTimeout(() => { refresh().catch(() => undefined); }, 1500);
    return () => window.clearTimeout(timer);
  }, [documents, refresh]);

  const uploadFile = async (file: File) => {
    setUploading(true);
    setNotice("");
    const form = new FormData();
    form.append("file", file);
    if (documentDate) form.append("document_date", documentDate);
    try {
      const response = await fetch("/api/rag/documents/upload", { method: "POST", headers: authHeader(), body: form });
      const data = await response.json() as { detail?: string; stage?: string };
      if (!response.ok) throw new Error(data.detail || "上传失败");
      setNotice(`《${file.name}》已上传成功，正在建立索引。`);
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "上传失败");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const upload = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) void uploadFile(file);
  };
  const drop = (event: DragEvent<HTMLButtonElement>) => {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (file && !uploading) void uploadFile(file);
  };

  const remove = async (filename: string) => {
    if (!confirm(`确定删除“${filename}”及其全部证据切片吗？`)) return;
    await fetch(`/api/rag/documents/${encodeURIComponent(filename)}`, { method: "DELETE", headers: authHeader() });
    setNotice(`已删除《${filename}》。`);
    await refresh();
  };

  const ready = documents.filter((item) => item.status === "done").length;
  const working = documents.filter((item) => item.status === "pending" || item.status === "indexing").length;
  const failed = documents.filter((item) => item.status === "error").length;

  return <div className="min-h-full bg-kb-bg px-4 py-7 text-kb-ink dark:bg-[#0a1628] sm:px-7 lg:px-10">
    <div className="mx-auto max-w-6xl">
      <div className="flex flex-wrap items-end justify-between gap-5"><div><p className="text-xs font-semibold tracking-[0.14em] text-kb-accent">KNOWLEDGE ASSETS</p><h1 className="mt-1 font-[var(--font-display)] text-3xl font-semibold">知识库管理</h1><p className="mt-2 text-sm text-kb-muted">上传后的每个文件都会经过解析、证据切分和向量索引，完成后才会进入问答范围。</p></div><button onClick={() => inputRef.current?.click()} disabled={uploading} className="inline-flex items-center gap-2 bg-kb-accent px-4 py-2.5 text-sm font-medium text-white transition hover:bg-[#126e65] disabled:opacity-50"><FileUp className="h-4 w-4" />上传资料</button></div>

      <input ref={inputRef} type="file" className="hidden" accept={supportedTypes} onChange={upload} />
      {notice && <div className="mt-6 flex items-start justify-between gap-3 border border-kb-accent/30 bg-emerald-50 px-4 py-3 text-sm text-emerald-900 dark:bg-emerald-400/10 dark:text-emerald-100"><span className="flex items-center gap-2"><Check className="h-4 w-4 shrink-0" />{notice}</span><button onClick={() => setNotice("")} aria-label="关闭提示"><X className="h-4 w-4" /></button></div>}

      <section className="mt-7 grid gap-3 sm:grid-cols-4"><div className="border border-kb-border bg-kb-card p-4 dark:bg-[#0f1f35]"><p className="text-xs text-kb-muted">已就绪文件</p><p className="mt-2 text-2xl font-semibold">{ready}</p></div><div className="border border-kb-border bg-kb-card p-4 dark:bg-[#0f1f35]"><p className="text-xs text-kb-muted">处理中</p><p className="mt-2 text-2xl font-semibold text-amber-700 dark:text-amber-200">{working}</p></div><div className="border border-kb-border bg-kb-card p-4 dark:bg-[#0f1f35]"><p className="text-xs text-kb-muted">失败任务</p><p className="mt-2 text-2xl font-semibold text-kb-error">{failed}</p></div><div className="border border-kb-border bg-kb-card p-4 dark:bg-[#0f1f35]"><p className="text-xs text-kb-muted">可用证据切片</p><p className="mt-2 text-2xl font-semibold">{totalChunks}</p></div></section>

      <section className="mt-7 border border-kb-border bg-kb-card p-4 dark:bg-[#0f1f35]"><label className="block text-sm font-medium" htmlFor="document-date">文档生效/发布日期（可选）</label><div className="mt-2 flex flex-wrap items-center gap-3"><input id="document-date" type="date" value={documentDate} onChange={(event) => setDocumentDate(event.target.value)} className="border border-kb-border bg-kb-bg px-3 py-2 text-sm outline-none focus:border-kb-accent dark:bg-[#132238]" /><p className="text-xs text-kb-muted">仅使用你填写的日期做时间过滤；不会从文件名或文件修改时间猜测。</p></div></section>
      <button type="button" onClick={() => inputRef.current?.click()} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={drop} className={`mt-3 flex w-full flex-col items-center justify-center border border-dashed px-5 py-8 text-center transition ${dragging ? "border-kb-accent bg-emerald-50 dark:bg-emerald-400/10" : "border-kb-border bg-kb-card hover:border-kb-accent dark:bg-[#0f1f35]"}`}><FileUp className="h-6 w-6 text-kb-accent" /><p className="mt-3 text-sm font-medium">拖放文件到这里，或点击选择文件</p><p className="mt-1 text-xs text-kb-muted">支持 PDF、Word、Excel、TXT、CSV，单文件不超过 50MB</p>{uploading && <span className="mt-3 inline-flex items-center gap-2 text-xs text-kb-accent"><Loader2 className="h-3.5 w-3.5 animate-spin" />正在上传…</span>}</button>

      <section className="mt-8"><div className="flex items-center justify-between"><div><h2 className="font-semibold">文件与索引任务</h2><p className="mt-1 text-xs text-kb-muted">文件上传成功不代表立即可问；状态变为“已就绪”后才会被 RAG 检索。</p></div><button onClick={() => refresh().catch((error: unknown) => setNotice(error instanceof Error ? error.message : "刷新失败"))} className="inline-flex items-center gap-1.5 text-sm text-kb-muted hover:text-kb-accent"><RefreshCw className="h-4 w-4" />刷新</button></div>
        <div className="mt-4 overflow-hidden border border-kb-border bg-kb-card dark:bg-[#0f1f35]">{documents.map((document) => <article key={document.filename} className="flex flex-wrap items-center gap-4 border-b border-kb-border p-4 last:border-b-0"><div className="grid h-10 w-10 place-items-center bg-kb-surface text-kb-accent dark:bg-[#132238]"><FileText className="h-5 w-5" /></div><div className="min-w-[220px] flex-1"><p className="break-all text-sm font-medium">{document.filename}</p><p className="mt-1 text-xs text-kb-muted">{document.stage || "等待处理"}{document.chunks ? ` · ${document.chunks} 个证据切片` : ""}{document.size ? ` · ${formatSize(document.size)}` : ""}</p>{document.document_date && <p className="mt-1 text-xs text-kb-muted">生效/发布日期：{document.document_date}</p>}{(document.quality?.file_sha256 || document.version?.file_sha256) && <p className="mt-1 text-xs text-kb-muted">版本 SHA-256：{(document.quality?.file_sha256 || document.version?.file_sha256)?.slice(0, 12)}</p>}{document.error && <p className="mt-1 text-xs text-kb-error">{document.error}</p>}</div><StatusBadge status={document.status} />{document.status === "done" && <button onClick={() => navigate("/")} className="inline-flex items-center gap-1 text-xs font-medium text-kb-accent hover:underline"><Send className="h-3.5 w-3.5" />开始问答</button>}<button onClick={() => remove(document.filename)} className="p-2 text-kb-muted hover:text-kb-error" aria-label={`删除 ${document.filename}`}><Trash2 className="h-4 w-4" /></button></article>)}{documents.length === 0 && <div className="px-5 py-12 text-center"><Clock3 className="mx-auto h-5 w-5 text-kb-muted" /><p className="mt-3 text-sm text-kb-muted">尚未上传资料。先上传一份制度或手册，开始构建可追溯问答。</p></div>}</div>
      </section>
    </div>
  </div>;
}
