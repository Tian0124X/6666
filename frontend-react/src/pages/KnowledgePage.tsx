import { useState, useEffect, useCallback, useRef } from "react";
import { knowledgeApi } from "../lib/api";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  BookOpen, Upload, Trash2, Loader2, FileText, RefreshCw,
  Activity, Zap, FileUp, Search, X, CheckCircle2,
  AlertTriangle, Clock, Database, GitGraph, Brain, Circle,
  HardDrive, Cpu, BarChart3, ChevronRight, ChevronDown,
  ArrowUp, Sparkles, Layers, Share2, Plus,
} from "lucide-react";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";

/* ========================================================================
   Types
   ======================================================================== */

type Tab = "qa" | "docs" | "graph";

interface ChatMsg {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: { filename: string; excerpt: string }[];
  mode?: string;
  level?: number;
  fromCache?: boolean;
  iterations?: number;
}

interface ToastItem {
  id: string;
  type: "success" | "error" | "info";
  message: string;
}

interface DiagInfo {
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
}

interface DocEntry {
  name: string;
  indexed: boolean;
}

/* ========================================================================
   Constants
   ======================================================================== */

const PIE_COLORS = ["#1A8A7D", "#D4952B", "#3b82f6", "#8b5cf6", "#ec4899", "#f59e0b", "#06b6d4", "#84cc16", "#f97316", "#6366f1"];

const MODE_CONFIG: Record<string, { icon: string; label: string; color: string }> = {
  direct:   { icon: "⚡", label: "直接回答",  color: "bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-950 dark:text-sky-300 dark:border-sky-800" },
  standard: { icon: "📖", label: "标准 RAG",  color: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950 dark:text-emerald-300 dark:border-emerald-800" },
  agentic:  { icon: "🔄", label: "Agentic",  color: "bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-950 dark:text-purple-300 dark:border-purple-800" },
  graphrag: { icon: "🕸️", label: "GraphRAG", color: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-300 dark:border-amber-800" },
};

const SUGGESTED_QUESTIONS = [
  { icon: "📋", text: "公司年假政策是什么？" },
  { icon: "📊", text: "帮我总结最近的销售数据" },
  { icon: "💰", text: "最新的报销流程是怎样的？" },
  { icon: "📝", text: "员工入职需要准备哪些材料？" },
];

const ALLOWED_EXTS = ".pdf,.docx,.xlsx,.xls,.txt,.csv";
const ALLOWED_EXT_LIST = ["pdf", "docx", "xlsx", "xls", "txt", "csv"];
const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB

/* ========================================================================
   Toast System
   ======================================================================== */

let toastIdCounter = 0;

/* ========================================================================
   Main Component
   ======================================================================== */

export default function KnowledgePage() {
  const [tab, setTab] = useState<Tab>("qa");
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [streamStatus, setStreamStatus] = useState("");  // SSE 实时状态文字
  const abortRef = useRef<AbortController | null>(null);  // 取消流式请求
  const chatEndRef = useRef<HTMLDivElement>(null);

  /* Upload state */
  const [file, setFile] = useState<File | null>(null);
  const [uploadMsg, setUploadMsg] = useState("");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [dragOver, setDragOver] = useState(false);
  const [indexingFiles, setIndexingFiles] = useState<Map<string, { status: string; chunks: number; error?: string }>>(new Map());

  /* Documents */
  const [docs, setDocs] = useState<{ indexed: string[]; uploaded: string[]; total: number }>({
    indexed: [], uploaded: [], total: 0,
  });
  const [docFilter, setDocFilter] = useState("");
  const [deleting, setDeleting] = useState<string | null>(null);

  /* Diagnostics */
  const [diag, setDiag] = useState<DiagInfo | null>(null);
  const [showDiag, setShowDiag] = useState(false);

  /* Toasts */
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  /* =====================================================================
     Toast helpers
     ===================================================================== */

  const addToast = useCallback((type: ToastItem["type"], message: string) => {
    const id = String(++toastIdCounter);
    setToasts((prev) => [...prev, { id, type, message }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000);
  }, []);

  /* =====================================================================
     Data fetching
     ===================================================================== */

  const fetchDocs = useCallback(async () => {
    try {
      const data = await knowledgeApi.listDocs();
      setDocs({
        indexed: data.indexed_documents || [],
        uploaded: data.uploaded_files || [],
        total: data.total,
      });
    } catch { /* ignore */ }
  }, []);

  const fetchDiag = useCallback(async () => {
    try {
      const d = await knowledgeApi.diagnostics();
      setDiag(d as DiagInfo);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    fetchDocs();
    fetchDiag();
  }, [fetchDocs, fetchDiag]);

  /* Poll indexing status for files in progress */
  useEffect(() => {
    const pending: string[] = [];
    indexingFiles.forEach((v, k) => {
      if (v.status === "pending" || v.status === "indexing") pending.push(k);
    });
    if (pending.length === 0) return;

    const timer = setInterval(async () => {
      let changed = false;
      const next = new Map(indexingFiles);
      for (const filename of pending) {
        try {
          const s = await knowledgeApi.uploadIndexStatus(filename);
          next.set(filename, { status: s.status, chunks: s.chunks, error: s.error });
          if (s.status === "done") {
            addToast("success", `"${filename}" 索引完成 (${s.chunks} chunks)`);
            fetchDocs();
            fetchDiag();
          } else if (s.status === "error") {
            addToast("error", `"${filename}" 索引失败: ${s.error || "未知错误"}`);
          }
          changed = true;
        } catch { /* ignore */ }
      }
      if (changed) setIndexingFiles(next);
    }, 2000);

    return () => clearInterval(timer);
  }, [indexingFiles, fetchDocs, fetchDiag, addToast]);

  /* Scroll chat to bottom */
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  /* =====================================================================
     Handlers — Q&A
     ===================================================================== */

  const handleAsk = () => {
    const q = input.trim();
    if (!q || loading) return;

    // 取消上一次未完成的请求
    abortRef.current?.abort();

    const userMsg: ChatMsg = { id: crypto.randomUUID(), role: "user", content: q };
    const assistantId = crypto.randomUUID();
    // 占位消息：初始为空，流式追加内容
    const assistantMsg: ChatMsg = { id: assistantId, role: "assistant", content: "" };
    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setInput("");
    setLoading(true);
    setStreamStatus("正在分析问题...");

    const controller = knowledgeApi.streamSmartQa(
      q,
      // onStatus
      (status) => setStreamStatus(status),
      // onChunk — 逐段追加到占位消息
      (text) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: m.content + text } : m
          )
        );
      },
      // onData — 完成后设置元数据
      (data) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  sources: (data.sources || []).map((s: any) => ({
                    filename: s.filename || "",
                    excerpt: s.excerpt || "",
                  })),
                  mode: data.mode,
                  level: data.level,
                  fromCache: data.from_cache,
                  iterations: data.iterations,
                }
              : m
          )
        );
      },
      // onDone
      () => {
        setLoading(false);
        setStreamStatus("");
        abortRef.current = null;
      },
      // onError
      (err) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId && !m.content
              ? { ...m, content: `❌ 查询失败: ${err}` }
              : m
          )
        );
        setLoading(false);
        setStreamStatus("");
        abortRef.current = null;
        addToast("error", `知识问答失败: ${err}`);
      },
    );

    abortRef.current = controller;
  };

  /** 停止当前流式生成 */
  const handleStop = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setLoading(false);
    setStreamStatus("");
  };

  /* =====================================================================
     Handlers — Upload
     ===================================================================== */

  const validateFile = (f: File): string | null => {
    const ext = "." + f.name.split(".").pop()?.toLowerCase();
    if (!ALLOWED_EXT_LIST.includes(ext.slice(1))) {
      return `不支持的文件类型: ${ext}。支持: ${ALLOWED_EXT_LIST.join(", ")}`;
    }
    if (f.size > MAX_FILE_SIZE) {
      return `文件过大 (${(f.size / 1024 / 1024).toFixed(1)}MB，上限 50MB)`;
    }
    return null;
  };

  const handleFileSelect = (f: File | null) => {
    if (!f) { setFile(null); setUploadMsg(""); return; }
    const err = validateFile(f);
    if (err) { setUploadMsg(`❌ ${err}`); setFile(null); return; }
    setFile(f);
    setUploadMsg("");
    setUploadProgress(0);
  };

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setUploadMsg("");
    setUploadProgress(0);
    try {
      const res: any = await knowledgeApi.upload(file, (pct: number) => setUploadProgress(pct));
      setUploadMsg(`✅ ${res.message || "上传成功"}`);
      addToast("success", `文件 "${file.name}" 已上传，正在后台索引...`);
      setIndexingFiles((prev) => {
        const next = new Map(prev);
        next.set(file.name, { status: "indexing", chunks: 0 });
        return next;
      });
      setFile(null);
      setUploadProgress(0);
      fetchDocs();
      fetchDiag();
    } catch (e: unknown) {
      const errMsg = e instanceof Error ? e.message : String(e);
      setUploadMsg(`❌ 上传失败: ${errMsg}`);
      addToast("error", `上传失败: ${errMsg}`);
    }
    setLoading(false);
  };

  /* Drag & drop */
  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); setDragOver(true); };
  const handleDragLeave = () => setDragOver(false);
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFileSelect(f);
  };

  /* =====================================================================
     Handlers — Documents
     ===================================================================== */

  const handleDelete = async (filename: string) => {
    setDeleting(filename);
    try {
      await knowledgeApi.deleteDoc(filename);
      addToast("success", `"${filename}" 已删除`);
      fetchDocs();
      fetchDiag();
    } catch (e: unknown) {
      addToast("error", `删除失败: ${e instanceof Error ? e.message : String(e)}`);
    }
    setDeleting(null);
  };

  /* =====================================================================
     Helpers
     ===================================================================== */

  const allDocs: DocEntry[] = [...new Set([...docs.indexed, ...docs.uploaded])].map((name) => ({
    name,
    indexed: docs.indexed.includes(name),
  }));

  const filteredDocs = docFilter
    ? allDocs.filter((d) => d.name.toLowerCase().includes(docFilter.toLowerCase()))
    : allDocs;

  const indexingCount = [...indexingFiles.values()].filter(
    (v) => v.status === "pending" || v.status === "indexing"
  ).length;

  /* ====================================================================
     Sub-components — defined BEFORE render to avoid TDZ ReferenceError
     ==================================================================== */

  /* ---- Q&A Panel ---- */
  const qaPanel = (
      <>
        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-6">
          {messages.length === 0 ? (
            /* Empty state */
            <div className="flex flex-col items-center justify-center h-full max-w-lg mx-auto text-center space-y-6">
              <div className="w-20 h-20 rounded-2xl bg-kb-surface flex items-center justify-center">
                <Brain className="w-10 h-10 text-kb-accent" />
              </div>
              <div className="space-y-1.5">
                <h3 className="text-lg font-semibold text-kb-ink dark:text-white"
                  style={{ fontFamily: "var(--font-display)" }}>
                  向知识库提问
                </h3>
                <p className="text-sm text-kb-muted">
                  基于已上传的企业文档，AI 会检索相关内容并给出带来源标注的回答。
                </p>
              </div>
              <div className="grid grid-cols-2 gap-2 w-full">
                {SUGGESTED_QUESTIONS.map((q) => (
                  <button
                    key={q.text}
                    onClick={() => setInput(q.text)}
                    className="flex items-center gap-2 text-left px-4 py-3 rounded-xl bg-kb-card border border-kb-border
                               hover:border-kb-accent hover:shadow-sm transition-all duration-200 group"
                  >
                    <span className="text-base shrink-0">{q.icon}</span>
                    <span className="text-xs text-kb-muted group-hover:text-kb-ink dark:group-hover:text-white leading-relaxed line-clamp-2">
                      {q.text}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            /* Chat messages */
            <div className="max-w-4xl mx-auto space-y-5">
              {messages.map((msg) => (
                <ChatMessage key={msg.id} msg={msg} />
              ))}
              {loading && <TypingIndicator status={streamStatus} />}
              <div ref={chatEndRef} />
            </div>
          )}
        </div>

        {/* Input bar */}
        <div className="shrink-0 border-t border-kb-border bg-kb-card px-6 py-4">
          <div className="flex gap-3 max-w-4xl mx-auto">
            <div className="flex-1 relative">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleAsk(); }
                }}
                placeholder="输入问题，按 Enter 发送..."
                className="w-full px-4 py-3 pr-10 rounded-xl border border-kb-border bg-kb-bg text-sm
                           text-kb-ink dark:text-white placeholder:text-kb-muted
                           focus:ring-2 focus:ring-kb-accent/30 focus:border-kb-accent focus:outline-none
                           transition-all duration-200"
                disabled={loading}
              />
              {input && (
                <button
                  onClick={() => setInput("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 p-1 rounded-md text-kb-muted hover:text-kb-ink dark:hover:text-white transition-colors"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
            {loading ? (
              <button
                onClick={handleStop}
                className="flex items-center gap-2 px-5 py-3 rounded-xl bg-red-500 text-white font-medium text-sm
                           hover:bg-red-600 transition-all duration-200 active:scale-[0.97] shadow-sm"
              >
                <X className="w-4 h-4" />
                停止
              </button>
            ) : (
              <button
                onClick={handleAsk}
                disabled={!input.trim()}
                className="flex items-center gap-2 px-5 py-3 rounded-xl bg-kb-accent text-white font-medium text-sm
                           hover:brightness-110 disabled:opacity-40 disabled:cursor-not-allowed
                           transition-all duration-200 active:scale-[0.97] shadow-sm"
              >
                <ArrowUp className="w-4 h-4" />
                发送
              </button>
            )}
          </div>
          <p className="text-[10px] text-kb-muted mt-2 text-center max-w-4xl mx-auto">
            按 Enter 发送 · AI 回答基于已索引文档，请核实关键信息
          </p>
        </div>
      </>
  );

  /* ---- Documents Panel ---- */
  const docsPanel = (
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto p-6 space-y-6">
          {/* Upload Zone */}
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={`relative rounded-2xl border-2 border-dashed transition-all duration-300 p-8 text-center ${
              dragOver
                ? "border-kb-accent bg-kb-accent/5 scale-[1.01] shadow-lg"
                : "border-kb-border bg-kb-card hover:border-kb-muted hover:bg-kb-surface/50"
            }`}
          >
            {dragOver ? (
              <div className="space-y-3 pointer-events-none">
                <div className="w-14 h-14 mx-auto rounded-2xl bg-kb-accent/10 flex items-center justify-center">
                  <FileUp className="w-7 h-7 text-kb-accent" />
                </div>
                <p className="text-base font-medium text-kb-accent">释放以上传文件</p>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="w-14 h-14 mx-auto rounded-2xl bg-kb-surface flex items-center justify-center">
                  <Upload className="w-7 h-7 text-kb-muted" />
                </div>
                <div>
                  <p className="text-sm font-medium text-kb-ink dark:text-white">
                    拖拽文件到此处，或点击下方按钮选择
                  </p>
                  <p className="text-xs text-kb-muted mt-1">
                    支持 PDF · Word · Excel · TXT · CSV · 最大 50MB
                  </p>
                </div>
                <label className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-kb-surface text-sm font-medium
                                  text-kb-ink dark:text-white hover:bg-kb-border cursor-pointer transition-colors">
                  <Plus className="w-4 h-4" />
                  选择文件
                  <input
                    type="file"
                    accept={ALLOWED_EXTS}
                    onChange={(e) => handleFileSelect(e.target.files?.[0] || null)}
                    className="hidden"
                  />
                </label>
              </div>
            )}
          </div>

          {/* Selected file + Upload button */}
          {file && (
            <div className="bg-kb-card border border-kb-border rounded-2xl p-4 space-y-3 animate-[slideIn_0.2s_ease-out]">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-kb-accent/10 flex items-center justify-center shrink-0">
                  <FileText className="w-5 h-5 text-kb-accent" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-kb-ink dark:text-white truncate">{file.name}</p>
                  <p className="text-xs text-kb-muted">{(file.size / 1024).toFixed(1)} KB</p>
                </div>
                <button
                  onClick={() => handleFileSelect(null)}
                  className="p-1.5 rounded-lg text-kb-muted hover:text-kb-error hover:bg-red-50 dark:hover:bg-red-950 transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Upload progress */}
              {uploadProgress > 0 && (
                <div className="space-y-1.5">
                  <div className="h-2 rounded-full bg-kb-surface overflow-hidden">
                    <div
                      className="h-full rounded-full bg-kb-accent transition-all duration-500 ease-out"
                      style={{ width: `${uploadProgress}%` }}
                    />
                  </div>
                  <p className="text-xs text-kb-muted text-right">{uploadProgress}%</p>
                </div>
              )}

              <button
                onClick={handleUpload}
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-kb-accent text-white
                           text-sm font-medium hover:brightness-110 disabled:opacity-40 transition-all"
              >
                {loading ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> 上传中...</>
                ) : (
                  <><Upload className="w-4 h-4" /> 上传并索引</>
                )}
              </button>

              {uploadMsg && (
                <p className={`text-xs ${uploadMsg.startsWith("✅") ? "text-emerald-600" : "text-red-600"}`}>
                  {uploadMsg}
                </p>
              )}
            </div>
          )}

          {/* Indexing status */}
          {indexingFiles.size > 0 && (
            <div className="bg-kb-card border border-kb-border rounded-2xl p-4 space-y-2">
              <h3 className="text-sm font-medium text-kb-ink dark:text-white flex items-center gap-2">
                <Clock className="w-4 h-4 text-kb-highlight" />
                索引进度
              </h3>
              {[...indexingFiles.entries()].map(([name, info]) => (
                <div key={name} className="flex items-center gap-3 text-xs">
                  <FileText className="w-3.5 h-3.5 text-kb-muted shrink-0" />
                  <span className="flex-1 truncate text-kb-ink dark:text-white">{name}</span>
                  {info.status === "done" ? (
                    <span className="flex items-center gap-1 text-emerald-600"><CheckCircle2 className="w-3 h-3" /> 完成 ({info.chunks} chunks)</span>
                  ) : info.status === "error" ? (
                    <span className="flex items-center gap-1 text-kb-error"><AlertTriangle className="w-3 h-3" /> 失败</span>
                  ) : (
                    <span className="flex items-center gap-1 text-kb-highlight"><Loader2 className="w-3 h-3 animate-spin" /> 索引中...</span>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Document list */}
          <div className="bg-kb-card border border-kb-border rounded-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-kb-border">
              <h3 className="text-sm font-medium text-kb-ink dark:text-white flex items-center gap-2">
                <FileText className="w-4 h-4 text-kb-muted" />
                已上传文档
                <span className="text-xs text-kb-muted font-normal">({filteredDocs.length}{allDocs.length !== filteredDocs.length ? ` / ${allDocs.length}` : ""})</span>
              </h3>
              <div className="flex items-center gap-2">
                {/* Search */}
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-kb-muted" />
                  <input
                    value={docFilter}
                    onChange={(e) => setDocFilter(e.target.value)}
                    placeholder="搜索文档..."
                    className="w-44 pl-8 pr-3 py-1.5 rounded-lg border border-kb-border bg-kb-bg text-xs
                               text-kb-ink dark:text-white placeholder:text-kb-muted
                               focus:ring-1 focus:ring-kb-accent focus:border-kb-accent focus:outline-none"
                  />
                </div>
                <button
                  onClick={fetchDocs}
                  className="p-2 rounded-lg hover:bg-kb-surface text-kb-muted hover:text-kb-accent transition-colors"
                  title="刷新列表"
                >
                  <RefreshCw className="w-4 h-4" />
                </button>
              </div>
            </div>

            {filteredDocs.length === 0 ? (
              <div className="px-5 py-12 text-center space-y-3">
                <div className="w-12 h-12 mx-auto rounded-xl bg-kb-surface flex items-center justify-center">
                  <Database className="w-6 h-6 text-kb-muted" />
                </div>
                <p className="text-sm text-kb-muted">
                  {docFilter ? "没有匹配的文档" : "尚未上传任何文档"}
                </p>
                {!docFilter && (
                  <p className="text-xs text-kb-muted">
                    上传 PDF、Word、Excel 等文档以构建知识库
                  </p>
                )}
              </div>
            ) : (
              <div className="divide-y divide-kb-border">
                {filteredDocs.map((doc) => (
                  <div
                    key={doc.name}
                    className="flex items-center justify-between px-5 py-3 hover:bg-kb-surface/50 transition-colors group"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-8 h-8 rounded-lg bg-kb-surface flex items-center justify-center shrink-0">
                        <FileText className="w-4 h-4 text-kb-muted" />
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm text-kb-ink dark:text-white truncate">{doc.name}</p>
                        <div className="flex items-center gap-2 mt-0.5">
                          {doc.indexed ? (
                            <span className="inline-flex items-center gap-1 text-[10px] text-emerald-600 font-medium">
                              <CheckCircle2 className="w-3 h-3" /> 已索引
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-[10px] text-kb-muted">
                              <Circle className="w-3 h-3" /> 未索引
                            </span>
                          )}
                          {indexingFiles.has(doc.name) && indexingFiles.get(doc.name)?.status !== "done" && (
                            <span className="inline-flex items-center gap-1 text-[10px] text-kb-highlight">
                              <Loader2 className="w-3 h-3 animate-spin" /> 索引中
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <button
                      onClick={() => handleDelete(doc.name)}
                      disabled={deleting === doc.name}
                      className="p-2 rounded-lg text-kb-muted hover:text-kb-error hover:bg-red-50 dark:hover:bg-red-950
                                 opacity-0 group-hover:opacity-100 transition-all duration-200 disabled:opacity-50"
                      title="删除文档"
                    >
                      {deleting === doc.name ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Trash2 className="w-4 h-4" />
                      )}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
  );

  /* ---- Graph Dashboard Panel ---- */
  let graphPanel: React.ReactNode;
  if (!diag) {
    graphPanel = (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-kb-muted" />
      </div>
    );
  } else {
    const gs = diag.graph_stats;
    const graphAvailable = diag.lightrag_available || diag.neo4j_available;
    graphPanel = (
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-5xl mx-auto p-6 space-y-6">
          {/* Stat cards row */}
          <div className="grid grid-cols-3 gap-4">
            <StatCard
              icon={GitGraph}
              label="实体节点"
              value={gs ? String(gs.nodes) : "—"}
              subtitle="知识图谱中的实体"
              color="kb-accent"
            />
            <StatCard
              icon={Share2}
              label="关系边"
              value={gs ? String(gs.relationships) : "—"}
              subtitle="实体之间的关联"
              color="kb-highlight"
            />
            <StatCard
              icon={HardDrive}
              label="图谱后端"
              value={graphAvailable ? (diag.neo4j_available ? "Neo4j" : "LightRAG") : "未启用"}
              subtitle={diag.graph_backend === "none" ? "GRAPH_BACKEND=none" : `引擎: ${diag.graph_backend || "unknown"}`}
              color={graphAvailable ? "emerald-500" : "kb-muted"}
              available={graphAvailable}
            />
          </div>

          {/* Graph details */}
          <div className="grid grid-cols-5 gap-6">
            {/* Type distribution donut */}
            <div className="col-span-3 bg-kb-card border border-kb-border rounded-2xl p-6">
              <h3 className="text-sm font-medium text-kb-ink dark:text-white mb-4 flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-kb-accent" />
                实体类型分布
              </h3>
              {gs && gs.type_distribution && gs.type_distribution.length > 0 ? (
                <div className="flex items-center gap-6">
                  <div className="w-52 h-52 shrink-0">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={gs.type_distribution}
                          dataKey="count"
                          nameKey="type"
                          cx="50%"
                          cy="50%"
                          innerRadius={50}
                          outerRadius={85}
                          paddingAngle={2}
                          strokeWidth={0}
                        >
                          {gs.type_distribution.map((_, i) => (
                            <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip
                          contentStyle={{
                            borderRadius: "12px",
                            border: "1px solid #E8E4DD",
                            fontSize: "12px",
                            fontFamily: "Inter, sans-serif",
                          }}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="flex-1 space-y-2">
                    {gs.type_distribution.slice(0, 8).map((item, i) => (
                      <div key={item.type} className="flex items-center gap-2 text-xs">
                        <div
                          className="w-2.5 h-2.5 rounded-full shrink-0"
                          style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }}
                        />
                        <span className="flex-1 text-kb-ink dark:text-white">{item.type || "其他"}</span>
                        <span className="font-medium text-kb-muted font-[family-name:var(--font-mono)]">
                          {item.count}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <EmptyGraphState message="暂无图谱数据" detail="上传文档并完成索引后，系统会自动构建知识图谱" />
              )}
            </div>

            {/* Backend status */}
            <div className="col-span-2 space-y-4">
              <div className="bg-kb-card border border-kb-border rounded-2xl p-5">
                <h3 className="text-sm font-medium text-kb-ink dark:text-white mb-3 flex items-center gap-2">
                  <Cpu className="w-4 h-4 text-kb-muted" />
                  后端状态
                </h3>
                <div className="space-y-2.5">
                  <StatusRow label="LightRAG" ok={diag.lightrag_available} />
                  <StatusRow label="Neo4j" ok={diag.neo4j_available} />
                  <StatusRow label="向量存储" ok={diag.document_count >= 0} detail={diag.vector_backend.toUpperCase()} />
                  <StatusRow label="BM25 检索" ok={diag.bm25_status === "ready"} detail={diag.bm25_status === "ready" ? `${diag.bm25_document_count} docs` : "空"} />
                  <StatusRow label="重排序器" ok={diag.reranker_available} detail={diag.reranker_available ? "BGE" : "LLM"} />
                </div>
              </div>

              {/* Cache info */}
              <div className="bg-kb-card border border-kb-border rounded-2xl p-5">
                <h3 className="text-sm font-medium text-kb-ink dark:text-white mb-3 flex items-center gap-2">
                  <Database className="w-4 h-4 text-kb-muted" />
                  存储信息
                </h3>
                <div className="space-y-2 text-xs text-kb-muted">
                  <div className="flex justify-between">
                    <span>向量后端</span>
                    <span className="font-medium text-kb-ink dark:text-white">{diag.vector_backend.toUpperCase()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>文档总数</span>
                    <span className="font-medium text-kb-ink dark:text-white font-[family-name:var(--font-mono)]">{diag.document_count}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>BM25 文档</span>
                    <span className="font-medium text-kb-ink dark:text-white font-[family-name:var(--font-mono)]">{diag.bm25_document_count}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  /* =====================================================================
     Render — references qaPanel, docsPanel, graphPanel defined above
     ===================================================================== */

  return (
    <div className="h-screen flex flex-col bg-kb-bg">
      {/* ================================================================
          Header
          ================================================================ */}
      <header className="shrink-0 border-b border-kb-border bg-kb-card px-6 py-4">
        <div className="flex items-center justify-between">
          {/* Title */}
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-kb-accent flex items-center justify-center shadow-sm">
                <BookOpen className="w-5 h-5 text-white" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-kb-ink dark:text-white">
                  知识库管理
                </h2>
                <p className="text-xs text-kb-muted">
                  {diag ? `${diag.document_count} 份文档已索引` : "加载中..."}
                </p>
              </div>
            </div>

            {/* Tab switcher — pill style */}
            <div className="flex bg-kb-surface rounded-xl p-1 gap-0.5">
              {([
                { key: "qa" as Tab, icon: Zap, label: "知识问答" },
                { key: "docs" as Tab, icon: Layers, label: "文档管理" },
                { key: "graph" as Tab, icon: Share2, label: "图谱概览" },
              ]).map(({ key, icon: Icon, label }) => (
                <button
                  key={key}
                  onClick={() => setTab(key)}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                    tab === key
                      ? "bg-kb-accent text-white shadow-sm"
                      : "text-kb-muted hover:text-kb-ink dark:hover:text-white"
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Right side */}
          <div className="flex items-center gap-3">
            {/* Indexing indicator */}
            {indexingCount > 0 && (
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-kb-highlight/10 text-kb-highlight text-xs font-medium">
                <Loader2 className="w-3 h-3 animate-spin" />
                {indexingCount} 个文件索引中
              </div>
            )}
            {/* Diagnostics toggle */}
            <button
              onClick={() => { setShowDiag(!showDiag); if (!diag) fetchDiag(); }}
              className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-all duration-200 ${
                showDiag
                  ? "bg-kb-accent text-white shadow-sm"
                  : "bg-kb-surface text-kb-muted hover:text-kb-ink dark:hover:text-white hover:bg-kb-border"
              }`}
            >
              <Activity className="w-3.5 h-3.5" />
              系统诊断
            </button>
          </div>
        </div>
      </header>

      {/* ================================================================
          Diagnostics Bar
          ================================================================ */}
      {showDiag && diag && (
        <div className="shrink-0 border-b border-kb-border bg-kb-surface/60 px-6 py-3">
          <div className="flex flex-wrap gap-x-6 gap-y-1.5 text-xs">
            <DiagItem label="向量后端" value={diag.vector_backend.toUpperCase()} ok={diag.pgvector_available || diag.vector_backend === "chromadb"} />
            <DiagItem label="文档数" value={String(diag.document_count)} />
            <DiagItem label="BM25" value={diag.bm25_status === "ready" ? `✅ ${diag.bm25_document_count} 条` : "❌ 空"} ok={diag.bm25_status === "ready"} />
            <DiagItem label="重排序" value={diag.reranker_available ? "✅ BGE" : "⚠️ LLM 备用"} ok={diag.reranker_available} />
            <DiagItem label="LLM" value={diag.llm_available ? "✅ 已连接" : "❌ 未配置"} ok={diag.llm_available} />
            <DiagItem label="图谱后端" value={diag.graph_backend || "none"} ok={diag.lightrag_available || diag.neo4j_available} />
            {diag.graph_stats && (
              <DiagItem label="图谱数据" value={`${diag.graph_stats.nodes} 节点 · ${diag.graph_stats.relationships} 关系`} />
            )}
          </div>
        </div>
      )}

      {/* ================================================================
          Content Area
          ================================================================ */}
      <div className="flex-1 overflow-hidden flex flex-col">
        {tab === "qa" && qaPanel}
        {tab === "docs" && docsPanel}
        {tab === "graph" && graphPanel}
      </div>

      {/* ================================================================
          Toast Container
          ================================================================ */}
      <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2 pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`pointer-events-auto flex items-center gap-2 px-4 py-3 rounded-xl shadow-lg text-sm animate-[slideIn_0.3s_ease-out] ${
              t.type === "success"
                ? "bg-emerald-600 text-white"
                : t.type === "error"
                ? "bg-red-600 text-white"
                : "bg-kb-ink text-white dark:bg-white dark:text-kb-ink"
            }`}
          >
            {t.type === "success" ? <CheckCircle2 className="w-4 h-4 shrink-0" />
              : t.type === "error" ? <AlertTriangle className="w-4 h-4 shrink-0" />
              : <Sparkles className="w-4 h-4 shrink-0" />}
            <span>{t.message}</span>
            <button onClick={() => setToasts((prev) => prev.filter((x) => x.id !== t.id))} className="ml-2 opacity-60 hover:opacity-100">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ========================================================================
   Sub-components (standalone, outside KnowledgePage)
   ======================================================================== */

/* Chat message bubble */
function ChatMessage({ msg }: { msg: ChatMsg }) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const isUser = msg.role === "user";
  const modeInfo = msg.mode ? MODE_CONFIG[msg.mode] : null;

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      {/* Avatar */}
      <div
        className={`w-8 h-8 rounded-xl flex items-center justify-center shrink-0 shadow-sm ${
          isUser ? "bg-kb-accent" : "bg-kb-surface border border-kb-border"
        }`}
      >
        {isUser ? (
          <span className="text-xs text-white font-medium">U</span>
        ) : (
          <Brain className="w-4 h-4 text-kb-accent" />
        )}
      </div>

      {/* Bubble */}
      <div
        className={`max-w-[75%] rounded-2xl px-4 py-3 space-y-2 ${
          isUser
            ? "bg-kb-accent text-white rounded-tr-md"
            : "bg-kb-card border border-kb-border rounded-tl-md shadow-sm"
        }`}
      >
        {/* Content */}
        {isUser ? (
          <p className="text-sm whitespace-pre-wrap leading-relaxed">{msg.content}</p>
        ) : (
          <div className="space-y-3">
            {msg.content && (
              <div className="prose prose-sm max-w-none dark:prose-invert prose-p:leading-relaxed prose-a:text-kb-accent">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
              </div>
            )}

            {/* Badges row */}
            {(modeInfo || msg.fromCache || (msg.level !== undefined && msg.level >= 0)) && (
              <div className="flex items-center gap-1.5 flex-wrap">
                {modeInfo && (
                  <span className={`inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border ${modeInfo.color}`}>
                    {modeInfo.icon} {modeInfo.label}
                  </span>
                )}
                {msg.fromCache && (
                  <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-300 dark:border-amber-800">
                    💾 缓存命中
                  </span>
                )}
                {msg.level !== undefined && msg.level >= 0 && (
                  <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border bg-slate-50 text-slate-600 border-slate-200 dark:bg-slate-900 dark:text-slate-400 dark:border-slate-700">
                    Lv.{msg.level}
                  </span>
                )}
                {msg.iterations && msg.iterations > 1 && (
                  <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border bg-purple-50 text-purple-600 border-purple-200 dark:bg-purple-950 dark:text-purple-300 dark:border-purple-800">
                    {msg.iterations} 轮迭代
                  </span>
                )}
              </div>
            )}

            {/* Sources */}
            {msg.sources && msg.sources.length > 0 && (
              <div className="border-t border-kb-border pt-2">
                <button
                  onClick={() => setSourcesOpen(!sourcesOpen)}
                  className="flex items-center gap-1.5 text-xs text-kb-muted hover:text-kb-accent transition-colors"
                >
                  {sourcesOpen ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                  📚 {msg.sources.length} 个参考来源
                </button>
                {sourcesOpen && (
                  <div className="mt-2 space-y-1.5 max-h-40 overflow-y-auto">
                    {msg.sources.map((s, i) => (
                      <div key={i} className="text-xs bg-kb-surface rounded-lg px-3 py-2">
                        <span className="font-medium text-kb-ink dark:text-white">[{i + 1}] {s.filename || "未知来源"}</span>
                        {s.excerpt && (
                          <p className="text-kb-muted mt-0.5 leading-relaxed line-clamp-2">{s.excerpt}</p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/* Typing indicator */
function TypingIndicator({ status }: { status?: string }) {
  return (
    <div className="flex gap-3">
      <div className="w-8 h-8 rounded-xl bg-kb-surface border border-kb-border flex items-center justify-center shadow-sm">
        <Brain className="w-4 h-4 text-kb-accent" />
      </div>
      <div className="bg-kb-card border border-kb-border rounded-2xl rounded-tl-md px-4 py-3 shadow-sm">
        <div className="flex items-center gap-2">
          <span className="text-sm text-kb-muted">{status || "正在检索知识库"}</span>
          <span className="flex gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-kb-accent animate-bounce [animation-delay:0ms]" />
            <span className="w-1.5 h-1.5 rounded-full bg-kb-accent animate-bounce [animation-delay:150ms]" />
            <span className="w-1.5 h-1.5 rounded-full bg-kb-accent animate-bounce [animation-delay:300ms]" />
          </span>
        </div>
      </div>
    </div>
  );
}

/* Diagnostics item */
function DiagItem({ label, value, ok }: { label: string; value: string; ok?: boolean }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-kb-muted">{label}:</span>
      <span className={`font-medium ${
        ok === undefined ? "text-kb-ink dark:text-white"
          : ok ? "text-emerald-600 dark:text-emerald-400"
          : "text-kb-error"
      }`}>
        {value}
      </span>
    </div>
  );
}

/* Stat card for graph dashboard */
function StatCard({
  icon: Icon, label, value, subtitle, color, available,
}: {
  icon: typeof GitGraph;
  label: string;
  value: string;
  subtitle: string;
  color: "kb-accent" | "kb-highlight" | "kb-muted" | "emerald-500";
  available?: boolean;
}) {
  const bgMap: Record<string, string> = {
    "kb-accent": "bg-kb-accent/10",
    "kb-highlight": "bg-kb-highlight/10",
    "kb-muted": "bg-kb-muted/10",
    "emerald-500": "bg-emerald-500/10",
  };
  const textMap: Record<string, string> = {
    "kb-accent": "text-kb-accent",
    "kb-highlight": "text-kb-highlight",
    "kb-muted": "text-kb-muted",
    "emerald-500": "text-emerald-500",
  };
  return (
    <div className="bg-kb-card border border-kb-border rounded-2xl p-5 hover:shadow-md transition-shadow duration-300">
      <div className="flex items-start justify-between">
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${bgMap[color]}`}>
          <Icon className={`w-5 h-5 ${textMap[color]}`} />
        </div>
        {available !== undefined && (
          <span className={`w-2 h-2 rounded-full ${available ? "bg-emerald-500" : "bg-kb-muted"}`} />
        )}
      </div>
      <div className="mt-4">
        <p
          className="text-3xl font-semibold text-kb-ink dark:text-white tracking-tight"
          style={{ fontFamily: "var(--font-display)" }}
        >
          {value}
        </p>
        <p className="text-xs text-kb-muted mt-1">{label}</p>
        <p className="text-[10px] text-kb-muted/70 mt-0.5">{subtitle}</p>
      </div>
    </div>
  );
}

/* Backend status row */
function StatusRow({ label, ok, detail }: { label: string; ok: boolean; detail?: string }) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-kb-muted">{label}</span>
      <div className="flex items-center gap-1.5">
        {detail && <span className="text-kb-muted font-[family-name:var(--font-mono)]">{detail}</span>}
        <span className={`w-1.5 h-1.5 rounded-full ${ok ? "bg-emerald-500" : "bg-kb-muted"}`} />
      </div>
    </div>
  );
}

/* Empty graph state */
function EmptyGraphState({ message, detail }: { message: string; detail: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center space-y-3">
      <div className="w-14 h-14 rounded-2xl bg-kb-surface flex items-center justify-center">
        <Share2 className="w-7 h-7 text-kb-muted" />
      </div>
      <div>
        <p className="text-sm text-kb-muted">{message}</p>
        <p className="text-xs text-kb-muted/70 mt-1 max-w-xs">{detail}</p>
      </div>
    </div>
  );
}
