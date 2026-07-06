import { useState, useEffect, useCallback, useRef } from "react";
import { knowledgeApi } from "../lib/api";
import {
  BookOpen,
  Upload,
  Trash2,
  Loader2,
  FileText,
  RefreshCw,
  Send,
  Activity,
  Zap,
} from "lucide-react";

type Tab = "chat" | "upload";

interface ChatMsg {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: { filename: string; excerpt: string }[];
  mode?: string;
  level?: number;
  fromCache?: boolean;
}

interface DocEntry {
  name: string;
  indexed: boolean;
}

interface DiagInfo {
  vector_backend: string;
  document_count: number;
  bm25_status: string;
  bm25_document_count: number;
  reranker_available: boolean;
  llm_available: boolean;
  pgvector_available: boolean;
}

export default function KnowledgePage() {
  const [tab, setTab] = useState<Tab>("chat");
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Upload
  const [file, setFile] = useState<File | null>(null);
  const [uploadMsg, setUploadMsg] = useState("");

  // Documents list
  const [docs, setDocs] = useState<{
    indexed: string[];
    uploaded: string[];
    total: number;
  }>({ indexed: [], uploaded: [], total: 0 });

  // Diagnostics
  const [diag, setDiag] = useState<DiagInfo | null>(null);
  const [showDiag, setShowDiag] = useState(false);

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
      setDiag(d);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    fetchDocs();
    fetchDiag();
  }, [fetchDocs, fetchDiag]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleAsk = async () => {
    const q = input.trim();
    if (!q || loading) return;
    const userMsg: ChatMsg = { id: crypto.randomUUID(), role: "user", content: q };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await knowledgeApi.smartQa(q);
      const assistantMsg: ChatMsg = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: res.answer,
        sources: (res.sources || []).map((s) => ({ filename: s.filename, excerpt: s.excerpt || "" })),
        mode: res.mode,
        level: res.level,
        fromCache: res.from_cache,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (e: unknown) {
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "assistant", content: `❌ ${e instanceof Error ? e.message : String(e)}` },
      ]);
    }
    setLoading(false);
  };

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setUploadMsg("");
    try {
      const res = await knowledgeApi.upload(file);
      setUploadMsg(`✅ ${res.message}`);
      setFile(null);
      fetchDocs();
      fetchDiag();
    } catch (e: unknown) {
      setUploadMsg(`❌ ${e instanceof Error ? e.message : String(e)}`);
    }
    setLoading(false);
  };

  const handleDelete = async (filename: string) => {
    try {
      await knowledgeApi.deleteDoc(filename);
      fetchDocs();
      fetchDiag();
    } catch { /* ignore */ }
  };

  const modeBadge = (mode?: string) => {
    if (!mode) return null;
    const map: Record<string, { bg: string; label: string }> = {
      direct: { bg: "bg-sky-100 dark:bg-sky-900/30 text-sky-700", label: "⚡ 直答" },
      standard: { bg: "bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700", label: "📖 标准 RAG" },
      agentic: { bg: "bg-purple-100 dark:bg-purple-900/30 text-purple-700", label: "🔄 Agentic" },
      graphrag: { bg: "bg-orange-100 dark:bg-orange-900/30 text-orange-700", label: "🕸️ GraphRAG" },
    };
    const info = map[mode] || { bg: "bg-gray-100 text-gray-600", label: mode };
    return <span className={`text-[10px] px-1.5 py-0.5 rounded ${info.bg}`}>{info.label}</span>;
  };

  return (
    <div className="h-screen flex flex-col">
      <header className="border-b border-border bg-card px-6 py-4 flex items-center justify-between">
        <h2 className="font-semibold text-foreground flex items-center gap-2">
          <BookOpen className="w-5 h-5" />
          知识库管理
        </h2>
        <div className="flex items-center gap-2">
          {diag && (
            <button
              onClick={() => setShowDiag(!showDiag)}
              className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-colors ${
                showDiag ? "bg-primary text-primary-foreground" : "bg-muted hover:bg-accent"
              }`}
            >
              <Activity className="w-3.5 h-3.5" />
              诊断
            </button>
          )}
        </div>
      </header>

      {/* Tabs */}
      <div className="border-b border-border bg-card px-6 flex gap-0">
        {[
          { key: "chat" as Tab, icon: <Zap className="w-4 h-4" />, label: "知识问答" },
          { key: "upload" as Tab, icon: <Upload className="w-4 h-4" />, label: "上传文档" },
        ].map(({ key, icon, label }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors -mb-px ${
              tab === key
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {icon}
            {label}
          </button>
        ))}
      </div>

      {/* Diagnostics bar */}
      {showDiag && diag && (
        <div className="border-b border-border bg-muted/30 px-6 py-3 flex flex-wrap gap-4 text-xs">
          <div className="flex items-center gap-1.5">
            <span className="text-muted-foreground">后端:</span>
            <span className={`font-medium ${diag.pgvector_available ? "text-emerald-600" : "text-amber-600"}`}>
              {diag.vector_backend.toUpperCase()}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-muted-foreground">文档:</span>
            <span className="font-medium">{diag.document_count}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-muted-foreground">BM25:</span>
            <span className={`font-medium ${diag.bm25_status === "ready" ? "text-emerald-600" : "text-red-500"}`}>
              {diag.bm25_status === "ready" ? `✅ ${diag.bm25_document_count} 条` : "❌ 空"}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-muted-foreground">重排序:</span>
            <span className={`font-medium ${diag.reranker_available ? "text-emerald-600" : "text-amber-600"}`}>
              {diag.reranker_available ? "✅ BGE" : "⚠️ LLM"}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-muted-foreground">LLM:</span>
            <span className={`font-medium ${diag.llm_available ? "text-emerald-600" : "text-red-500"}`}>
              {diag.llm_available ? "✅" : "❌"}
            </span>
          </div>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-auto flex flex-col">
        {tab === "chat" && (
          <>
            {/* Chat area */}
            <div className="flex-1 overflow-auto px-6 py-4 space-y-4">
              {messages.length === 0 && (
                <div className="flex flex-col items-center justify-center h-full text-muted-foreground space-y-3">
                  <BookOpen className="w-12 h-12 opacity-20" />
                  <p className="text-sm">向知识库提问任何问题</p>
                  <div className="flex gap-2">
                    {["公司年假政策是什么？", "帮我总结销售数据", "最新的报销流程"].map((q) => (
                      <button
                        key={q}
                        onClick={() => setInput(q)}
                        className="text-xs px-3 py-1.5 rounded-full bg-muted hover:bg-accent transition-colors"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {messages.map((msg) => (
                <div key={msg.id} className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                    msg.role === "user" ? "bg-primary" : "bg-secondary"
                  }`}>
                    {msg.role === "user" ? (
                      <span className="text-xs text-primary-foreground">U</span>
                    ) : (
                      <BookOpen className="w-4 h-4 text-secondary-foreground" />
                    )}
                  </div>
                  <div className={`max-w-[80%] rounded-2xl px-4 py-3 space-y-2 ${
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-card border border-border text-foreground"
                  }`}>
                    {msg.mode === "direct" && (
                      <p className="text-[11px] text-sky-600 dark:text-sky-400 italic mb-1">💡 此问题无需检索知识库，直接回答</p>
                    )}
                    <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                    {/* RAG badges */}
                    {msg.role === "assistant" && (
                      <div className="flex items-center gap-1.5">
                        {modeBadge(msg.mode)}
                        {msg.fromCache && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-900/30 text-amber-700">💾 缓存</span>
                        )}
                        {msg.level !== undefined && msg.level >= 0 && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-600">L{msg.level}</span>
                        )}
                      </div>
                    )}
                    {/* Sources */}
                    {msg.sources && msg.sources.length > 0 && (
                      <div className="border-t border-border pt-2 space-y-1">
                        <p className="text-xs text-muted-foreground">📚 参考来源:</p>
                        {msg.sources.map((s, i) => (
                          <p key={i} className="text-xs text-muted-foreground truncate">
                            [{i + 1}] {s.filename}: {(s.excerpt || "").slice(0, 100)}
                          </p>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {loading && (
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded-lg bg-secondary flex items-center justify-center">
                    <BookOpen className="w-4 h-4 text-secondary-foreground" />
                  </div>
                  <div className="bg-card border border-border rounded-2xl px-4 py-3 flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                    <span className="text-sm text-muted-foreground">正在检索知识库...</span>
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            {/* Input bar */}
            <div className="border-t border-border bg-card px-6 py-4">
              <div className="flex gap-3 max-w-4xl mx-auto">
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleAsk()}
                  placeholder="输入知识问题..."
                  className="flex-1 px-4 py-3 rounded-xl border border-input bg-background text-sm focus:ring-2 focus:ring-ring focus:outline-none"
                  disabled={loading}
                />
                <button
                  onClick={handleAsk}
                  disabled={loading || !input.trim()}
                  className="flex items-center gap-2 px-5 py-3 rounded-xl bg-primary text-primary-foreground font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
                >
                  {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                  提问
                </button>
              </div>
            </div>
          </>
        )}

        {tab === "upload" && (
          <div className="max-w-4xl mx-auto p-6 space-y-6 w-full">
            <div className="bg-card border border-border rounded-xl p-6 space-y-4">
              <h3 className="font-medium">上传企业文档</h3>
              <p className="text-xs text-muted-foreground">
                支持 PDF, Word (.docx), Excel (.xlsx/.xls), TXT, CSV · 上限 50MB
              </p>
              <div className="flex gap-3 items-center">
                <label className="flex items-center gap-2 px-4 py-2.5 rounded-lg border-2 border-dashed border-border hover:border-primary cursor-pointer transition-colors">
                  <Upload className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm text-muted-foreground">
                    {file ? file.name : "选择文件..."}
                  </span>
                  <input
                    type="file"
                    accept=".pdf,.docx,.xlsx,.xls,.txt,.csv"
                    onChange={(e) => setFile(e.target.files?.[0] || null)}
                    className="hidden"
                  />
                </label>
                <button
                  onClick={handleUpload}
                  disabled={!file || loading}
                  className="px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50"
                >
                  {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "上传并索引"}
                </button>
              </div>
              {uploadMsg && <p className="text-sm text-muted-foreground">{uploadMsg}</p>}
            </div>

            {/* Document list */}
            <div className="bg-card border border-border rounded-xl p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-medium flex items-center gap-2">
                  <FileText className="w-4 h-4" />
                  已上传文档 ({docs.total})
                </h3>
                <button onClick={fetchDocs} className="p-2 rounded-lg hover:bg-accent transition-colors">
                  <RefreshCw className="w-4 h-4 text-muted-foreground" />
                </button>
              </div>
              {[...new Set([...docs.indexed, ...docs.uploaded])].length === 0 ? (
                <p className="text-sm text-muted-foreground">暂无文档</p>
              ) : (
                <div className="space-y-1">
                  {[...new Set([...docs.indexed, ...docs.uploaded])].map((name) => (
                    <div key={name} className="flex items-center justify-between px-3 py-2 rounded-lg hover:bg-accent/50 transition-colors">
                      <div className="flex items-center gap-2">
                        <FileText className="w-4 h-4 text-muted-foreground" />
                        <span className="text-sm">{name}</span>
                        {docs.indexed.includes(name) && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary">已索引</span>
                        )}
                      </div>
                      <button
                        onClick={() => handleDelete(name)}
                        className="p-1.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
