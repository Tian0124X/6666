import { useState } from "react";
import { Bot, User, ChevronDown, ChevronRight, Code2, BarChart3, LineChart as LineChartIcon, PieChart as PieChartIcon, FileDown, ArrowUpDown, Search, Copy, Lightbulb, AlertTriangle } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage, ChartConfig, DataInsights } from "../stores/chatStore";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line,
  AreaChart, Area, ScatterChart, Scatter, ComposedChart, Legend,
} from "recharts";

const AGENT_ICONS: Record<string, string> = {
  data_agent: "📊 数据分析",
  oa_agent: "📋 OA审批",
  crm_agent: "👤 CRM",
  knowledge_agent: "📚 知识库",
};

const PIE_COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#06b6d4", "#f97316"];

export function ChatBubble({ msg, onSuggestionClick }: { msg: ChatMessage; onSuggestionClick?: (q: string) => void }) {
  const isUser = msg.role === "user";
  const [showCode, setShowCode] = useState(false);
  const dr = msg.dataResult;

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
        isUser ? "bg-primary" : "bg-secondary"
      }`}>
        {isUser ? <User className="w-4 h-4 text-primary-foreground" /> : <Bot className="w-4 h-4 text-secondary-foreground" />}
      </div>

      <div className={`max-w-[80%] rounded-2xl px-4 py-3 ${
        isUser ? "bg-primary text-primary-foreground" : "bg-card border border-border text-foreground"
      }`}>
        {/* User message: plain text */}
        {isUser && <p className="text-sm whitespace-pre-wrap">{msg.content}</p>}

        {/* Assistant message: markdown + data */}
        {!isUser && (
          <div className="space-y-3">
            {/* Text answer */}
            {msg.content && (
              <div className="prose prose-sm dark:prose-invert max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
              </div>
            )}

            {/* Data Table */}
            {dr?.type === "dataframe" && dr.columns && dr.rows && (
              <InteractiveTable columns={dr.columns} rows={dr.rows} shape={dr.shape} />
            )}

            {/* Scalar value */}
            {dr?.type === "scalar" && dr.value != null && (
              <div className="text-lg font-bold text-primary">{String(dr.value)}</div>
            )}

            {/* Chart */}
            {dr?.chart && <ChartView chart={dr.chart} />}

            {/* Code - collapsed by default */}
            {msg.code && (
              <div>
                <button onClick={() => setShowCode(!showCode)}
                  aria-expanded={showCode} aria-controls={`code-${msg.id}`}
                  className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors">
                  {showCode ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                  <Code2 className="w-3 h-3" />
                  查看分析代码
                </button>
                {showCode && (
                  <pre id={`code-${msg.id}`} className="mt-1 p-2 rounded bg-accent text-xs overflow-x-auto font-mono max-h-40">
                    {msg.code}
                  </pre>
                )}
              </div>
            )}

            {/* Insights */}
            {dr?.insights && <InsightsPanel insights={dr.insights} />}

            {/* Suggested Questions */}
            {dr?.suggestedQuestions && dr.suggestedQuestions.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {dr.suggestedQuestions.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => onSuggestionClick?.(q)}
                    className="text-[11px] px-2.5 py-1 rounded-full bg-accent text-accent-foreground border border-border hover:bg-primary/20 hover:border-primary/50 cursor-pointer transition-colors active:scale-95"
                    title="点击继续提问"
                  >
                    💡 {q}
                  </button>
                ))}
              </div>
            )}

            {/* Report download button */}
            {dr && msg.dataFilePath && (
              <div className="pt-1">
                <a
                  href={`/api/chat/report/generate?file_path=${encodeURIComponent(msg.dataFilePath)}`}
                  download
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary/10 text-primary text-xs hover:bg-primary/20 transition-colors"
                >
                  <FileDown className="w-3.5 h-3.5" />
                  下载 Word 报告
                </a>
              </div>
            )}
          </div>
        )}

        {/* Streaming cursor */}
        {msg.isStreaming && <span aria-live="polite" aria-label="AI 正在生成回答..." className="inline-block w-2 h-4 bg-primary animate-pulse rounded-sm ml-0.5" />}

        {/* Task badge */}
        {msg.taskType && (
          <span className="inline-block mt-1 text-[10px] px-1.5 py-0.5 rounded bg-secondary text-muted-foreground">
            {msg.taskType === "simple" ? "💬 快速问答" : msg.taskType === "multi_agent" ? "🤖 多Agent协作" : "📊 深度分析"}
          </span>
        )}
        {msg.agents && msg.agents.length > 0 && (
          <div className="flex gap-1 mt-1 flex-wrap">
            {msg.agents.map((a: string) => (
              <span key={a} className="text-[10px] px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-900/30 text-blue-700">
                {AGENT_ICONS[a] || a}
              </span>
            ))}
          </div>
        )}

        {/* Sources */}
        {msg.sources && msg.sources.length > 0 && (
          <div className="mt-2 pt-2 border-t border-border">
            <p className="text-xs text-muted-foreground mb-1">📚 参考来源:</p>
            {msg.sources.slice(0, 3).map((s, i) => (
              <p key={i} className="text-xs text-muted-foreground truncate">· {s.filename}: {(s.excerpt || '').slice(0, 80)}...</p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ChartView({ chart }: { chart: ChartConfig }) {
  const defaultType = chart.type || "bar";
  const [chartType, setChartType] = useState<string>(defaultType);
  const dataKey = chart.y || "value";
  const nameKey = chart.x || "name";
  const rawData = chart.data || [];

  if (rawData.length === 0) return null;

  const chartTypes = [
    { id: "bar", icon: BarChart3, label: "柱状图" },
    { id: "line", icon: LineChartIcon, label: "折线图" },
    { id: "pie", icon: PieChartIcon, label: "饼图" },
    { id: "area", icon: BarChart3, label: "面积图" },
    { id: "scatter", icon: LineChartIcon, label: "散点图" },
    { id: "composed", icon: BarChart3, label: "组合图" },
  ] as const;

  // 漏斗图用横向柱状图模拟
  if (chartType === "funnel") {
    return (
      <div className="h-64 w-full">
        <p className="text-xs text-muted-foreground mb-1">{(chart.title as string) || "漏斗图"}</p>
        <ResponsiveContainer>
          <BarChart data={rawData} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" tick={{ fontSize: 11 }} />
            <YAxis type="category" dataKey={nameKey} tick={{ fontSize: 11 }} width={80} />
            <Tooltip />
            <Bar dataKey={dataKey} fill="#8b5cf6" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  }

  // 组合图
  if (chartType === "composed") {
    const series = chart.series || [
      { dataKey: dataKey, chartType: "bar" },
    ];
    const secondKey = series.length > 1 ? series[1].dataKey : null;
    return (
      <div className="h-64 w-full">
        <div className="flex items-center justify-between mb-1">
          <p className="text-xs text-muted-foreground">{(chart.title as string) || "组合图"}</p>
          <div className="flex gap-0.5 bg-muted rounded-md p-0.5">
            {chartTypes.filter(c => c.id !== "pie" && c.id !== "scatter").map(({ id, icon: Icon, label }) => (
              <button key={id} onClick={() => setChartType(id)} title={label}
                className={`px-1.5 py-0.5 rounded text-xs transition-colors ${chartType === id ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}>
                <Icon className="w-3.5 h-3.5" />
              </button>
            ))}
          </div>
        </div>
        <ResponsiveContainer>
          <ComposedChart data={rawData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey={nameKey} tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Legend />
            <Bar dataKey={dataKey} fill="#3b82f6" radius={[4, 4, 0, 0]} />
            {secondKey && <Line type="monotone" dataKey={secondKey} stroke="#ef4444" strokeWidth={2} yAxisId={0} />}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    );
  }

  return (
    <div className="h-64 w-full">
      <div className="flex items-center justify-between mb-1">
        <p className="text-xs text-muted-foreground">{(chart.title as string) || "图表"}</p>
        <div className="flex gap-0.5 bg-muted rounded-md p-0.5">
          {chartTypes.map(({ id, icon: Icon, label }) => (
            <button key={id} onClick={() => setChartType(id)} title={label}
              className={`px-1.5 py-0.5 rounded text-xs transition-colors ${chartType === id ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}>
              <Icon className="w-3.5 h-3.5" />
            </button>
          ))}
        </div>
      </div>
      <ResponsiveContainer>
        {chartType === "pie" ? (
          <PieChart>
            <Pie data={rawData} dataKey={dataKey} nameKey={nameKey} cx="50%" cy="50%" outerRadius={80} label>
              {rawData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
            </Pie>
            <Tooltip />
          </PieChart>
        ) : chartType === "line" ? (
          <LineChart data={rawData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey={nameKey} tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Line type="monotone" dataKey={dataKey} stroke="#3b82f6" strokeWidth={2} />
          </LineChart>
        ) : chartType === "area" ? (
          <AreaChart data={rawData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey={nameKey} tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Area type="monotone" dataKey={dataKey} stroke="#10b981" fill="#10b981" fillOpacity={0.3} strokeWidth={2} />
          </AreaChart>
        ) : chartType === "scatter" ? (
          <ScatterChart>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey={nameKey} name={nameKey} tick={{ fontSize: 11 }} />
            <YAxis dataKey={dataKey} name={dataKey} tick={{ fontSize: 11 }} />
            <Tooltip cursor={{ strokeDasharray: "3 3" }} />
            <Scatter data={rawData} fill="#f59e0b" />
          </ScatterChart>
        ) : (
          <BarChart data={rawData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey={nameKey} tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Bar dataKey={dataKey} fill="#3b82f6" radius={[4, 4, 0, 0]} />
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

function InteractiveTable({ columns, rows, shape }: { columns: string[]; rows: unknown[][]; shape?: number[] }) {
  const [sortCol, setSortCol] = useState<number | null>(null);
  const [sortAsc, setSortAsc] = useState(true);
  const [filter, setFilter] = useState("");
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 30;

  // 排序
  const sortedRows = [...rows].sort((a, b) => {
    if (sortCol === null) return 0;
    const va = a[sortCol], vb = b[sortCol];
    if (typeof va === "number" && typeof vb === "number") return sortAsc ? va - vb : vb - va;
    return sortAsc ? String(va ?? "").localeCompare(String(vb ?? "")) : String(vb ?? "").localeCompare(String(va ?? ""));
  });

  // 过滤
  const filtered = filter
    ? sortedRows.filter((row) => row.some((cell) => String(cell ?? "").toLowerCase().includes(filter.toLowerCase())))
    : sortedRows;

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const pageRows = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const handleSort = (ci: number) => {
    if (sortCol === ci) setSortAsc(!sortAsc);
    else { setSortCol(ci); setSortAsc(true); }
  };

  const handleCopy = () => {
    const csv = [columns.join(","), ...filtered.slice(0, 100).map((r) => r.map((c) => `"${String(c ?? "").replace(/"/g, '""')}"`).join(","))].join("\n");
    navigator.clipboard.writeText(csv);
  };

  return (
    <div className="rounded-lg border border-border">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-2 py-1.5 border-b border-border bg-muted/50">
        <div className="relative flex-1">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground" />
          <input value={filter} onChange={(e) => { setFilter(e.target.value); setPage(0); }}
            placeholder="搜索..." className="w-full pl-6 pr-2 py-1 text-xs rounded border border-border bg-background" />
        </div>
        <button onClick={handleCopy} title="复制为CSV" className="p-1 rounded hover:bg-accent"><Copy className="w-3.5 h-3.5" /></button>
        <span className="text-[10px] text-muted-foreground">{shape ? `${shape[0]}行` : `${filtered.length}行`}</span>
      </div>

      {/* Table */}
      <div className="overflow-auto max-h-72">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-muted sticky top-0">
              {columns.map((col, ci) => (
                <th key={col} onClick={() => handleSort(ci)}
                  className="px-2 py-1.5 text-left font-medium whitespace-nowrap border-b border-border cursor-pointer hover:bg-accent/50 select-none">
                  <span className="flex items-center gap-1">
                    {col}
                    {sortCol === ci && <ArrowUpDown className="w-3 h-3" />}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.map((row, ri) => (
              <tr key={ri} className="border-t border-border hover:bg-accent/30">
                {(row as unknown[]).map((cell, ci) => (
                  <td key={ci} className={`px-2 py-1 whitespace-nowrap ${typeof cell === "number" ? "text-right tabular-nums" : ""}`}>{String(cell ?? "")}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-2 py-1 border-t border-border text-[10px] text-muted-foreground">
          <button disabled={page === 0} onClick={() => setPage(page - 1)} className="px-2 py-0.5 rounded hover:bg-accent disabled:opacity-30">上一页</button>
          <span>{page + 1} / {totalPages}</span>
          <button disabled={page >= totalPages - 1} onClick={() => setPage(page + 1)} className="px-2 py-0.5 rounded hover:bg-accent disabled:opacity-30">下一页</button>
        </div>
      )}
    </div>
  );
}

function InsightsPanel({ insights }: { insights: DataInsights }) {
  const [open, setOpen] = useState(false);
  const hasContent = insights.summary || (insights.anomalies && insights.anomalies.length > 0) || (insights.correlations && insights.correlations.length > 0);
  if (!hasContent) return null;

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center gap-2 px-3 py-2 bg-accent/30 hover:bg-accent/50 transition-colors text-xs">
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        <Lightbulb className="w-3.5 h-3.5 text-amber-500" />
        <span className="font-medium">数据洞察</span>
        {insights.summary && <span className="text-muted-foreground ml-auto truncate max-w-[60%]">{insights.summary}</span>}
      </button>
      {open && (
        <div className="px-3 py-2 space-y-2 text-xs">
          {insights.anomalies && insights.anomalies.length > 0 && (
            <div>
              <p className="font-medium text-amber-600 flex items-center gap-1"><AlertTriangle className="w-3 h-3" />异常值检测</p>
              {insights.anomalies.map((a, i) => (
                <p key={i} className="text-muted-foreground ml-4">
                  {a.description || `${a.column}: ${a.count}个异常值 (${a.percentage}%), 正常范围${a.range}`}
                </p>
              ))}
            </div>
          )}
          {insights.correlations && insights.correlations.length > 0 && (
            <div>
              <p className="font-medium text-blue-600">相关性发现</p>
              {insights.correlations.map((c, i) => (
                <p key={i} className="text-muted-foreground ml-4">{c.description}</p>
              ))}
            </div>
          )}
          {insights.suggestions && insights.suggestions.length > 0 && (
            <div>
              <p className="font-medium text-green-600">分析建议</p>
              {insights.suggestions.map((s, i) => (
                <p key={i} className="text-muted-foreground ml-4">· {s}</p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
