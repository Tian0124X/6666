import { useState, useEffect, useCallback } from "react";
import { knowledgeApi } from "../lib/api";
import {
  BookOpen,
  Upload,
  Search,
  Trash2,
  Loader2,
  FileText,
  RefreshCw,
} from "lucide-react";

type Tab = "upload" | "qa";

interface DocEntry {
  name: string;
  indexed: boolean;
}

export default function KnowledgePage() {
  const [tab, setTab] = useState<Tab>("qa");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState("");
  const [sources, setSources] = useState<{ filename: string; excerpt: string }[]>([]);

  // QA
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState(5);

  // Upload
  const [file, setFile] = useState<File | null>(null);
  const [uploadMsg, setUploadMsg] = useState("");

  // Documents list
  const [docs, setDocs] = useState<{
    indexed: string[];
    uploaded: string[];
    total: number;
  }>({ indexed: [], uploaded: [], total: 0 });

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

  useEffect(() => {
    fetchDocs();
  }, [fetchDocs]);

  const handleQA = async (smart = false) => {
    if (!question.trim()) return;
    setLoading(true);
    setResult("");
    setSources([]);
    try {
      const res = smart
        ? await knowledgeApi.smartQa(question)
        : await knowledgeApi.qa(question, topK);
      setResult(res.answer);
      setSources(
        (res.sources || []).map((s) => ({
          filename: s.filename,
          excerpt: s.excerpt || "",
        }))
      );
    } catch (e: unknown) {
      setResult(`❌ ${e instanceof Error ? e.message : String(e)}`);
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
    } catch (e: unknown) {
      setUploadMsg(`❌ ${e instanceof Error ? e.message : String(e)}`);
    }
    setLoading(false);
  };

  const [deleteError, setDeleteError] = useState<string | null>(null);

  const handleDelete = async (filename: string) => {
    try {
      await knowledgeApi.deleteDoc(filename);
      fetchDocs();
    } catch (e: unknown) {
      setDeleteError(e instanceof Error ? e.message : "删除失败");
      setTimeout(() => setDeleteError(null), 5000);
    }
  };

  return (
    <div className="h-screen flex flex-col">
      <header className="border-b border-border bg-card px-6 py-4">
        <h2 className="font-semibold text-foreground flex items-center gap-2">
          <BookOpen className="w-5 h-5" />
          知识库管理
        </h2>
      </header>

      {/* Tabs */}
      <div className="border-b border-border bg-card px-6 flex gap-0">
        {[
          { key: "qa" as Tab, icon: <Search className="w-4 h-4" />, label: "知识问答" },
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

      {/* Content */}
      <div className="flex-1 overflow-auto">
        <div className="max-w-4xl mx-auto p-6 space-y-6">
          {deleteError && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg px-4 py-3 text-red-600 text-sm">
              {deleteError}
            </div>
          )}
          {tab === "qa" && (
            <div className="bg-card border border-border rounded-xl p-6 space-y-4">
              <h3 className="font-medium">知识问答</h3>
              <div className="flex gap-3">
                <input
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleQA(false)}
                  placeholder="输入问题，例如：公司年假政策是什么？"
                  className="flex-1 px-3 py-2.5 rounded-lg border border-input bg-background text-sm focus:ring-2 focus:ring-ring focus:outline-none"
                />
                <select
                  value={topK}
                  onChange={(e) => setTopK(Number(e.target.value))}
                  className="w-20 px-2 py-2.5 rounded-lg border border-input bg-background text-sm"
                >
                  {[3, 5, 10, 20].map((k) => (
                    <option key={k} value={k}>Top {k}</option>
                  ))}
                </select>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => handleQA(false)}
                  disabled={loading || !question.trim()}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50"
                >
                  {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                  标准 RAG
                </button>
                <button
                  onClick={() => handleQA(true)}
                  disabled={loading || !question.trim()}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-secondary text-secondary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50"
                >
                  智能 RAG (自适应)
                </button>
              </div>
            </div>
          )}

          {tab === "upload" && (
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
              {uploadMsg && (
                <p className="text-sm text-muted-foreground">{uploadMsg}</p>
              )}
            </div>
          )}

          {/* Results */}
          {result && (
            <div className="bg-card border border-border rounded-xl p-6 space-y-4">
              <h3 className="font-medium">回答</h3>
              <div className="prose prose-sm dark:prose-invert max-w-none text-foreground whitespace-pre-wrap">
                {result}
              </div>
              {sources.length > 0 && (
                <div className="border-t border-border pt-3">
                  <p className="text-xs text-muted-foreground mb-2">📚 参考来源:</p>
                  {sources.map((s, i) => (
                    <p key={i} className="text-xs text-muted-foreground">
                      [{i + 1}] {s.filename}: {s.excerpt?.slice(0, 150)}...
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Document list */}
          <div className="bg-card border border-border rounded-xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-medium flex items-center gap-2">
                <FileText className="w-4 h-4" />
                已上传文档 ({docs.total})
              </h3>
              <button
                onClick={fetchDocs}
                className="p-2 rounded-lg hover:bg-accent transition-colors"
              >
                <RefreshCw className="w-4 h-4 text-muted-foreground" />
              </button>
            </div>
            {[...new Set([...docs.indexed, ...docs.uploaded])].length === 0 ? (
              <p className="text-sm text-muted-foreground">暂无文档</p>
            ) : (
              <div className="space-y-1">
                {[...new Set([...docs.indexed, ...docs.uploaded])].map((name) => (
                  <div
                    key={name}
                    className="flex items-center justify-between px-3 py-2 rounded-lg hover:bg-accent/50 transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4 text-muted-foreground" />
                      <span className="text-sm">{name}</span>
                      {docs.indexed.includes(name) && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary">
                          已索引
                        </span>
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
      </div>
    </div>
  );
}
