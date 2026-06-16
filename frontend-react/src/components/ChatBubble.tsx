import { useState } from "react";
import { Bot, User, ChevronDown, ChevronRight, Code2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "../stores/chatStore";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line,
} from "recharts";

const AGENT_ICONS: Record<string, string> = {
  data_agent: "📊 数据分析",
  oa_agent: "📋 OA审批",
  crm_agent: "👤 CRM",
  knowledge_agent: "📚 知识库",
};

const PIE_COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#06b6d4", "#f97316"];

export function ChatBubble({ msg }: { msg: ChatMessage }) {
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
              <div className="overflow-auto max-h-72 rounded-lg border border-border">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-muted sticky top-0">
                      {dr.columns.map((col) => (
                        <th key={col} className="px-2 py-1.5 text-left font-medium whitespace-nowrap border-b border-border">{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {dr.rows.slice(0, 50).map((row, ri) => (
                      <tr key={ri} className="border-t border-border hover:bg-accent/30">
                        {(row as unknown[]).map((cell, ci) => (
                          <td key={ci} className="px-2 py-1 whitespace-nowrap">{String(cell ?? "")}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {dr.shape && dr.shape[0] > 50 && (
                  <div className="text-xs text-muted-foreground text-center py-2 border-t border-border">
                    显示前50行，共{dr.shape[0]}行
                  </div>
                )}
              </div>
            )}

            {/* Scalar value */}
            {dr?.type === "scalar" && dr.value != null && (
              <div className="text-lg font-bold text-primary">{String(dr.value)}</div>
            )}

            {/* Chart */}
            {dr?.type === "chart" && dr.chart && <ChartView chart={dr.chart} />}
            {dr?.chart && <ChartView chart={dr.chart} />}

            {/* Code - collapsed by default */}
            {msg.code && (
              <div>
                <button onClick={() => setShowCode(!showCode)}
                  className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors">
                  {showCode ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                  <Code2 className="w-3 h-3" />
                  查看分析代码
                </button>
                {showCode && (
                  <pre className="mt-1 p-2 rounded bg-accent text-xs overflow-x-auto font-mono max-h-40">
                    {msg.code}
                  </pre>
                )}
              </div>
            )}
          </div>
        )}

        {/* Streaming cursor */}
        {msg.isStreaming && <span className="inline-block w-2 h-4 bg-primary animate-pulse rounded-sm ml-0.5" />}

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
              <p key={i} className="text-xs text-muted-foreground truncate">· {s.filename}: {s.excerpt.slice(0, 80)}...</p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ChartView({ chart }: { chart: Record<string, unknown> }) {
  const type = chart.type as string || "bar";
  const dataKey = (chart.y as string) || "value";
  const nameKey = (chart.x as string) || "name";
  const rawData = (chart.data as Record<string, unknown>[]) || [];

  if (rawData.length === 0) return null;

  return (
    <div className="h-64 w-full">
      <p className="text-xs text-muted-foreground mb-1">{(chart.title as string) || "图表"}</p>
      <ResponsiveContainer>
        {type === "pie" ? (
          <PieChart>
            <Pie data={rawData} dataKey={dataKey} nameKey={nameKey} cx="50%" cy="50%" outerRadius={80} label>
              {rawData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
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
