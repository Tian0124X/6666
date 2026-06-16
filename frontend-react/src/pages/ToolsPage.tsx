import { useState, useRef, useEffect } from "react";
import { toolsApi } from "../lib/api";
import {
  BarChart3, FileSpreadsheet, ClipboardCheck, Users,
  Upload, Loader2, Play, MessageCircle, Send, Code2,
  ChevronDown, ChevronRight, Table2, BarChart,
} from "lucide-react";
import {
  BarChart as ReBarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line,
} from "recharts";

type Tab = "data-chat" | "data" | "oa" | "crm";

interface ChatMessage {
  role: "user" | "assistant";
  question?: string;
  answer?: string;
  code?: string;
  result?: Record<string, unknown> | null;
  chart?: Record<string, unknown> | null;
  error?: string;
}

const COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#06b6d4", "#f97316"];

export default function ToolsPage() {
  const [tab, setTab] = useState<Tab>("data-chat");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState("");

  // Data Analysis (legacy)
  const [filePath, setFilePath] = useState("");
  const [action, setAction] = useState("summary");
  const [targetCol, setTargetCol] = useState("");
  const [chartType, setChartType] = useState("bar");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);

  // OA
  const [oaAction, setOaAction] = useState("list_approvals");
  const [oaValue, setOaValue] = useState("");

  // CRM
  const [crmAction, setCrmAction] = useState("list_customers");
  const [crmValue, setCrmValue] = useState("");

  // Data Chat
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatFilePath, setChatFilePath] = useState("");
  const [chatFileName, setChatFileName] = useState("");
  const [chatUploading, setChatUploading] = useState(false);
  const [showCode, setShowCode] = useState<Record<number, boolean>>({});
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [chatMessages]);

  const handleAnalyze = async () => {
    if (!filePath.trim()) return;
    setLoading(true);
    setResult("");
    try {
      const res = await toolsApi.analyze(filePath, action, targetCol || undefined, chartType || undefined);
      setResult(res.result);
    } catch (e: unknown) {
      setResult(`❌ ${e instanceof Error ? e.message : String(e)}`);
    }
    setLoading(false);
  };

  const handleOa = async () => {
    setLoading(true); setResult("");
    try { setResult((await toolsApi.oa(oaAction, oaValue || undefined)).result); }
    catch (e: unknown) { setResult(`❌ ${e instanceof Error ? e.message : String(e)}`); }
    setLoading(false);
  };

  const handleCrm = async () => {
    setLoading(true); setResult("");
    try { setResult((await toolsApi.crm(crmAction, crmValue || undefined)).result); }
    catch (e: unknown) { setResult(`❌ ${e instanceof Error ? e.message : String(e)}`); }
    setLoading(false);
  };

  const handleChatSend = async () => {
    if (!chatInput.trim() || !chatFilePath) return;
    const question = chatInput.trim();
    setChatInput("");
    setChatMessages((prev) => [...prev, { role: "user", question }]);
    setLoading(true);

    try {
      const res = await toolsApi.dataChat(chatFilePath, question);
      setChatMessages((prev) => [...prev, {
        role: "assistant",
        answer: res.answer,
        code: res.code,
        result: res.result,
        chart: res.chart,
      }]);
    } catch (e: unknown) {
      setChatMessages((prev) => [...prev, {
        role: "assistant",
        answer: "请求失败",
        error: e instanceof Error ? e.message : String(e),
      }]);
    }
    setLoading(false);
  };

  const handleChatFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setChatUploading(true);
    try {
      const { knowledgeApi } = await import("../lib/api");
      const res = await knowledgeApi.upload(f);
      const uploadedName = res.filename || f.name;
      const safeName = uploadedName.replace(/\.\./g, '').replace(/[\\/]/g, '');
      const path = `data/documents/${safeName}`;
      setChatFilePath(path);
      setChatFileName(f.name);
      setChatMessages([{
        role: "assistant",
        answer: `✅ 文件已上传: **${f.name}**\n\n你可以用自然语言对数据进行提问，例如：\n- "这个数据有多少行多少列？"\n- "哪个产品的销售额最高？"\n- "按月份统计销售总额"\n- "画一个销售额分布的柱状图"`,
      }]);
    } catch (err: unknown) {
      setChatMessages([{ role: "assistant", answer: "上传失败", error: err instanceof Error ? err.message : String(err) }]);
    }
    setChatUploading(false);
  };

  const tabs: { key: Tab; icon: React.ReactNode; label: string }[] = [
    { key: "data-chat", icon: <MessageCircle className="w-4 h-4" />, label: "数据对话" },
    { key: "data", icon: <BarChart3 className="w-4 h-4" />, label: "传统分析" },
    { key: "oa", icon: <ClipboardCheck className="w-4 h-4" />, label: "OA 查询" },
    { key: "crm", icon: <Users className="w-4 h-4" />, label: "CRM 查询" },
  ];

  return (
    <div className="h-screen flex flex-col">
      <header className="border-b border-border bg-card px-6 py-4">
        <h2 className="font-semibold text-foreground flex items-center gap-2">
          <WrenchIcon />
          工具测试
        </h2>
      </header>

      {/* Tabs */}
      <div className="border-b border-border bg-card px-6 flex gap-0 overflow-x-auto">
        {tabs.map(({ key, icon, label }) => (
          <button
            key={key}
            onClick={() => { setTab(key); if (key !== "data-chat") setResult(""); }}
            className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors -mb-px whitespace-nowrap ${
              tab === key ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {icon}{label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-4xl mx-auto space-y-6">

          {/* === DATA CHAT TAB === */}
          {tab === "data-chat" && (
            <div className="bg-card border border-border rounded-xl flex flex-col" style={{ height: "calc(100vh - 160px)" }}>
              {/* File upload bar */}
              <div className="p-4 border-b border-border flex items-center gap-3">
                <FileSpreadsheet className="w-4 h-4 text-muted-foreground shrink-0" />
                {chatFileName ? (
                  <span className="text-sm font-medium flex-1 truncate">{chatFileName}</span>
                ) : (
                  <span className="text-sm text-muted-foreground flex-1">上传数据文件开始分析</span>
                )}
                <label className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium cursor-pointer transition-colors ${
                  chatUploading ? "bg-muted text-muted-foreground" : "bg-primary/10 text-primary hover:bg-primary/20"
                }`}>
                  <Upload className="w-3 h-3" />
                  {chatUploading ? "上传中..." : chatFileName ? "换文件" : "上传"}
                  <input type="file" accept=".xlsx,.xls,.csv" onChange={handleChatFileUpload} className="hidden" disabled={chatUploading} />
                </label>
              </div>

              {/* Messages area */}
              <div className="flex-1 overflow-auto p-4 space-y-4">
                {chatMessages.length === 0 && (
                  <div className="text-center text-muted-foreground py-12">
                    <MessageCircle className="w-12 h-12 mx-auto mb-3 opacity-30" />
                    <p className="text-sm">上传 Excel/CSV 文件后，用自然语言提问</p>
                    <p className="text-xs mt-2">支持：统计汇总、筛选排序、分组聚合、趋势分析、图表生成</p>
                  </div>
                )}
                {chatMessages.map((msg, i) => (
                  <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                    <div className={`max-w-[85%] rounded-xl px-4 py-3 ${
                      msg.role === "user"
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted/50 border border-border"
                    }`}>
                      {msg.role === "user" ? (
                        <p className="text-sm whitespace-pre-wrap">{msg.question}</p>
                      ) : (
                        <div className="space-y-2">
                          {/* Answer */}
                          {msg.answer && (
                            <div className="text-sm whitespace-pre-wrap leading-relaxed">{msg.answer}</div>
                          )}
                          {msg.error && (
                            <div className="text-sm text-red-500">{msg.error}</div>
                          )}

                          {/* Code toggle */}
                          {msg.code && (
                            <div>
                              <button
                                onClick={() => setShowCode((p) => ({ ...p, [i]: !p[i] }))}
                                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                              >
                                {showCode[i] ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                                <Code2 className="w-3 h-3" />
                                执行代码
                              </button>
                              {showCode[i] && (
                                <pre className="mt-1 p-2 rounded bg-[var(--color-accent)] text-xs overflow-x-auto font-mono">
                                  {msg.code}
                                </pre>
                              )}
                            </div>
                          )}

                          {/* Table result */}
                          {msg.result && (msg.result as Record<string, unknown>).type === "dataframe" && (
                            <div>
                              <div className="flex items-center gap-1 text-xs text-muted-foreground mb-1">
                                <Table2 className="w-3 h-3" />
                                结果表格 ({(msg.result as Record<string, unknown>).shape as number[] | undefined || [0, 0]})
                              </div>
                              <div className="overflow-auto max-h-60 rounded border border-border">
                                <table className="w-full text-xs">
                                  <thead>
                                    <tr className="bg-muted">
                                      {((msg.result as Record<string, unknown>).columns as string[])?.map((col: string) => (
                                        <th key={col} className="px-2 py-1.5 text-left font-medium whitespace-nowrap">{col}</th>
                                      ))}
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {((msg.result as Record<string, unknown>).rows as unknown[][])?.map((row, ri) => (
                                      <tr key={ri} className="border-t border-border">
                                        {row.map((cell, ci) => (
                                          <td key={ci} className="px-2 py-1 whitespace-nowrap">{String(cell ?? "")}</td>
                                        ))}
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          )}

                          {/* Scalar result */}
                          {msg.result && (msg.result as Record<string, unknown>).type === "scalar" && (
                            <div className="text-lg font-bold text-primary">
                              {String((msg.result as Record<string, unknown>).value)}
                            </div>
                          )}

                          {/* Chart */}
                          {msg.chart && <ChartPreview chart={msg.chart as Record<string, unknown>} />}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
                {loading && (
                  <div className="flex justify-start">
                    <div className="bg-muted/50 rounded-xl px-4 py-3 flex items-center gap-2">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span className="text-sm text-muted-foreground">分析中...</span>
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>

              {/* Input bar */}
              <div className="p-3 border-t border-border flex gap-2">
                <input
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleChatSend(); } }}
                  placeholder={chatFilePath ? "输入数据分析问题... (Enter 发送)" : "请先上传数据文件"}
                  disabled={!chatFilePath || loading}
                  className="flex-1 px-3 py-2 rounded-lg border border-input bg-background text-sm focus:ring-2 focus:ring-ring focus:outline-none disabled:opacity-50"
                />
                <button
                  onClick={handleChatSend}
                  disabled={!chatFilePath || loading || !chatInput.trim()}
                  className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
                >
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}

          {/* === LEGACY DATA ANALYSIS TAB === */}
          {tab === "data" && (
            <div className="bg-card border border-border rounded-xl p-6 space-y-4">
              <h3 className="font-medium flex items-center gap-2">
                <FileSpreadsheet className="w-4 h-4" />
                数据分析 (Excel/CSV)
              </h3>
              <div className="flex gap-3 items-end">
                <div className="flex-1">
                  <label className="text-xs text-muted-foreground block mb-1">上传文件 (Excel/CSV, 限 50MB)</label>
                  <label className="flex items-center gap-2 px-3 py-2 rounded-lg border-2 border-dashed border-border hover:border-primary cursor-pointer transition-colors">
                    <Upload className="w-4 h-4 text-muted-foreground" />
                    <span className="text-sm text-muted-foreground">{file ? file.name : filePath || "选择文件..."}</span>
                    <input type="file" accept=".xlsx,.xls,.csv" onChange={async (e) => {
                      const f = e.target.files?.[0]; if (!f) return;
                      setFile(f); setUploading(true);
                      try {
                        const { knowledgeApi } = await import("../lib/api");
                        const res = await knowledgeApi.upload(f);
                        const safeName = (res.filename || f.name).replace(/\.\./g, '').replace(/[\\/]/g, '');
                        setFilePath(`data/documents/${safeName}`);
                        setResult(`✅ 文件已上传: ${res.message}`);
                      } catch (err: unknown) { setResult(`❌ 上传失败: ${err instanceof Error ? err.message : String(err)}`); }
                      setUploading(false);
                    }} className="hidden" />
                  </label>
                </div>
                <div className="w-32">
                  <label className="text-xs text-muted-foreground block mb-1">&nbsp;</label>
                  <button onClick={handleAnalyze} disabled={loading || uploading || !filePath.trim()}
                    className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity">
                    {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}分析
                  </button>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="text-xs text-muted-foreground block mb-1">分析模式</label>
                  <select value={action} onChange={(e) => setAction(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm focus:ring-2 focus:ring-ring focus:outline-none">
                    <option value="summary">概览 (Summary)</option>
                    <option value="analyze">深度分析 (Analyze)</option>
                    <option value="full_report">Word 报告 (Full Report)</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-muted-foreground block mb-1">目标列 (可选)</label>
                  <input value={targetCol} onChange={(e) => setTargetCol(e.target.value)} placeholder="例如: 销售额"
                    className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm focus:ring-2 focus:ring-ring focus:outline-none" />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground block mb-1">图表类型</label>
                  <select value={chartType} onChange={(e) => setChartType(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm focus:ring-2 focus:ring-ring focus:outline-none">
                    <option value="bar">柱状图</option>
                    <option value="line">折线图</option>
                    <option value="pie">饼图</option>
                    <option value="scatter">散点图</option>
                  </select>
                </div>
              </div>
            </div>
          )}

          {/* === OA TAB === */}
          {tab === "oa" && (
            <div className="bg-card border border-border rounded-xl p-6 space-y-4">
              <h3 className="font-medium flex items-center gap-2"><ClipboardCheck className="w-4 h-4" />OA 审批查询</h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-muted-foreground block mb-1">查询模式</label>
                  <select value={oaAction} onChange={(e) => setOaAction(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm focus:ring-2 focus:ring-ring focus:outline-none">
                    <option value="list_approvals">全部审批</option>
                    <option value="query_by_id">按编号查询</option>
                    <option value="query_by_user">按申请人查询</option>
                    <option value="query_by_status">按状态查询</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-muted-foreground block mb-1">查询值</label>
                  <input value={oaValue} onChange={(e) => setOaValue(e.target.value)}
                    placeholder={oaAction === "query_by_id" ? "例如: OA-001" : "例如: 张三"}
                    className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm focus:ring-2 focus:ring-ring focus:outline-none" />
                </div>
              </div>
              <button onClick={handleOa} disabled={loading}
                className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity">
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}查询
              </button>
            </div>
          )}

          {/* === CRM TAB === */}
          {tab === "crm" && (
            <div className="bg-card border border-border rounded-xl p-6 space-y-4">
              <h3 className="font-medium flex items-center gap-2"><Users className="w-4 h-4" />CRM 客户查询</h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-muted-foreground block mb-1">查询模式</label>
                  <select value={crmAction} onChange={(e) => setCrmAction(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm focus:ring-2 focus:ring-ring focus:outline-none">
                    <option value="list_customers">全部客户</option>
                    <option value="query_by_id">按编号查询</option>
                    <option value="query_by_industry">按行业查询</option>
                    <option value="query_by_level">按等级查询</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-muted-foreground block mb-1">查询值</label>
                  <input value={crmValue} onChange={(e) => setCrmValue(e.target.value)}
                    placeholder={crmAction === "query_by_id" ? "例如: CRM-001" : "例如: 互联网"}
                    className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm focus:ring-2 focus:ring-ring focus:outline-none" />
                </div>
              </div>
              <button onClick={handleCrm} disabled={loading}
                className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity">
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}查询
              </button>
            </div>
          )}

          {/* Legacy result */}
          {result && tab !== "data-chat" && (
            <div className="bg-card border border-border rounded-xl p-4">
              <pre className="text-sm whitespace-pre-wrap font-mono text-foreground">{result}</pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// === Chart Preview Component ===
function ChartPreview({ chart }: { chart: Record<string, unknown> }) {
  const type = chart.type as string;
  const dataKey = (chart.y as string) || "value";
  const nameKey = (chart.x as string) || "name";

  // Build data from chart config or result
  const rawData = (chart.data as Record<string, unknown>[]) || [];
  if (rawData.length === 0) return null;

  return (
    <div className="mt-2">
      <div className="flex items-center gap-1 text-xs text-muted-foreground mb-1">
        <BarChart className="w-3 h-3" />
        {(chart.title as string) || "图表"}
      </div>
      <div className="h-56 w-full">
        <ResponsiveContainer>
          {type === "pie" ? (
            <PieChart>
              <Pie data={rawData} dataKey={dataKey} nameKey={nameKey} cx="50%" cy="50%" outerRadius={80} label>
                {rawData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip />
            </PieChart>
          ) : type === "line" ? (
            <LineChart data={rawData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey={nameKey} tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Line type="monotone" dataKey={dataKey} stroke="#3b82f6" strokeWidth={2} />
            </LineChart>
          ) : (
            <ReBarChart data={rawData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey={nameKey} tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey={dataKey} fill="#3b82f6" radius={[4, 4, 0, 0]} />
            </ReBarChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function WrenchIcon() {
  return (
    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
    </svg>
  );
}
