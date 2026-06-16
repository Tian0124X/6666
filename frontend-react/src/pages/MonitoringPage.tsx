import { useState, useEffect, useCallback } from "react";
import {
  Activity, TrendingUp, Clock, AlertTriangle,
  Star, RefreshCw, Users, Brain, Wrench,
} from "lucide-react";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend,
} from "recharts";

interface OverviewData {
  today: {
    dau: number; requests: number; success_rate: number;
    avg_latency_ms: number; avg_rating: number | null; errors: number;
  };
  knowledge: Record<string, number>;
  tools: { total_calls: number };
  performance: { latest_eval_accuracy: string | null; latest_eval_at: string | null };
}
interface TrendPoint {
  date: string; total: number; chat_start?: number; chat_end?: number;
}
interface KnowledgeStats {
  rag_queries_today: number; top_tools: Record<string, number>; cache_hit_rate: number;
}
interface PerfStats {
  p50: number; p95: number; p99: number; min: number; max: number; samples: number;
}

const PIE_COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899"];

export default function MonitoringPage() {
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [trends, setTrends] = useState<TrendPoint[]>([]);
  const [knowledge, setKnowledge] = useState<KnowledgeStats | null>(null);
  const [perf, setPerf] = useState<PerfStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(7);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [ov, tr, kn, pf] = await Promise.all([
        fetch("/api/analytics/overview").then((r) => r.json()),
        fetch(`/api/analytics/trends?days=${days}`).then((r) => r.json()),
        fetch("/api/analytics/knowledge").then((r) => r.json()),
        fetch("/api/analytics/performance").then((r) => r.json()),
      ]);
      setOverview(ov); setTrends(tr.trends || []); setKnowledge(kn); setPerf(pf);
    } catch { /* ignore */ }
    setLoading(false);
  }, [days]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  return (
    <div className="h-screen flex flex-col">
      <header className="border-b border-[var(--color-border)] bg-[var(--color-card)] px-6 py-4 flex items-center justify-between">
        <h2 className="font-semibold text-[var(--color-foreground)] flex items-center gap-2">
          <Activity className="w-5 h-5" />
          业务仪表盘
        </h2>
        <div className="flex items-center gap-2">
          {[1, 7, 30].map((d) => (
            <button key={d} onClick={() => setDays(d)}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                days === d ? "bg-primary text-primary-foreground" : "border border-[var(--color-border)] hover:bg-[var(--color-accent)]"
              }`}
            >{d === 1 ? "今天" : `${d}天`}</button>
          ))}
          <button onClick={fetchAll} className="p-2 rounded-lg hover:bg-[var(--color-accent)] transition-colors">
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-7xl mx-auto space-y-6">
          {/* KPI Cards */}
          {overview && (
            <div className="grid grid-cols-3 lg:grid-cols-6 gap-3">
              <KpiCard icon={<Users />} label="今日活跃" value={overview.today.dau} color="blue" />
              <KpiCard icon={<Activity />} label="今日请求" value={overview.today.requests} color="indigo" />
              <KpiCard icon={<TrendingUp />} label="成功率" value={`${overview.today.success_rate}%`} color="green" />
              <KpiCard icon={<Brain />} label="知识库查询" value={knowledge?.rag_queries_today || 0} color="purple" />
              <KpiCard icon={<Star />} label="平均评分" value={overview.today.avg_rating ? `${overview.today.avg_rating}/5` : "暂无"} color="amber" />
              <KpiCard icon={<AlertTriangle />} label="今日错误" value={overview.today.errors} color="red" />
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Trends Chart */}
            <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-6">
              <h3 className="font-medium mb-4">📈 请求趋势 ({days}天)</h3>
              {trends.length > 0 ? (
                <div className="h-64">
                  <ResponsiveContainer>
                    <LineChart data={trends}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                      <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="var(--color-muted-foreground)" />
                      <YAxis tick={{ fontSize: 11 }} stroke="var(--color-muted-foreground)" />
                      <Tooltip />
                      <Line type="monotone" dataKey="total" name="总请求" stroke="#3b82f6" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="chat_start" name="对话" stroke="#10b981" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <p className="text-sm text-[var(--color-muted-foreground)] text-center py-12">暂无趋势数据，开始使用后自动采集</p>
              )}
            </div>

            {/* Performance Distribution */}
            <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-6">
              <h3 className="font-medium mb-4">⚡ 响应延迟分布</h3>
              {perf && perf.samples > 0 ? (
                <div className="space-y-3">
                  {[
                    { label: "P50", value: perf.p50, color: "bg-green-500" },
                    { label: "P95", value: perf.p95, color: "bg-amber-500" },
                    { label: "P99", value: perf.p99, color: "bg-red-500" },
                  ].map((p) => (
                    <div key={p.label} className="flex items-center gap-3">
                      <span className="text-xs font-mono w-8">{p.label}</span>
                      <div className="flex-1 h-6 bg-[var(--color-accent)] rounded-full overflow-hidden">
                        <div className={`h-full ${p.color} rounded-full flex items-center justify-end pr-2`}
                          style={{ width: `${Math.min((p.value / Math.max(perf.p99, 1)) * 100, 100)}%` }}>
                          <span className="text-[10px] text-white font-medium">{p.value}ms</span>
                        </div>
                      </div>
                    </div>
                  ))}
                  <div className="text-xs text-[var(--color-muted-foreground)] pt-2">
                    最小 {perf.min}ms · 最大 {perf.max}ms · 样本 {perf.samples}
                  </div>
                </div>
              ) : (
                <p className="text-sm text-[var(--color-muted-foreground)] text-center py-12">等待数据...</p>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Tool Usage Pie */}
            <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-6">
              <h3 className="font-medium mb-4">🔧 工具调用分布</h3>
              {knowledge?.top_tools && Object.keys(knowledge.top_tools).length > 0 ? (
                <div className="h-64">
                  <ResponsiveContainer>
                    <PieChart>
                      <Pie
                        data={Object.entries(knowledge.top_tools).map(([name, count]) => ({ name, value: count }))}
                        dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                      >
                        {Object.keys(knowledge.top_tools).map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                      </Pie>
                      <Tooltip />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <p className="text-sm text-[var(--color-muted-foreground)] text-center py-12">暂无工具调用数据</p>
              )}
            </div>

            {/* Latest Eval + RAG Stats */}
            <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-6">
              <h3 className="font-medium mb-4">🎯 质量指标</h3>
              <div className="space-y-4">
                {overview?.performance.latest_eval_accuracy && (
                  <div className="flex items-center justify-between p-3 rounded-lg bg-[var(--color-accent)]">
                    <span className="text-sm">最新评测准确率</span>
                    <span className="text-lg font-bold text-green-600">
                      {(parseFloat(overview.performance.latest_eval_accuracy) * 100).toFixed(0)}%
                    </span>
                  </div>
                )}
                <div className="flex items-center justify-between p-3 rounded-lg bg-[var(--color-accent)]">
                  <span className="text-sm">RAG 缓存命中率</span>
                  <span className="text-lg font-bold text-blue-600">
                    {knowledge ? `${(knowledge.cache_hit_rate * 100).toFixed(0)}%` : "N/A"}
                  </span>
                </div>
                <div className="flex items-center justify-between p-3 rounded-lg bg-[var(--color-accent)]">
                  <span className="text-sm">工具调用成功率</span>
                  <span className="text-lg font-bold text-purple-600">
                    {overview ? `${overview.today.success_rate}%` : "N/A"}
                  </span>
                </div>
                {overview?.performance.latest_eval_at && (
                  <div className="text-xs text-[var(--color-muted-foreground)] text-right">
                    最后评测: {new Date(overview.performance.latest_eval_at).toLocaleString("zh-CN")}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function KpiCard({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: string | number; color: string }) {
  const colors: Record<string, string> = {
    blue: "bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400",
    green: "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400",
    amber: "bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400",
    purple: "bg-purple-50 text-purple-700 dark:bg-purple-900/20 dark:text-purple-400",
    red: "bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400",
    indigo: "bg-indigo-50 text-indigo-700 dark:bg-indigo-900/20 dark:text-indigo-400",
  };
  return (
    <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-3">
      <div className={`w-7 h-7 rounded-lg flex items-center justify-center mb-2 ${colors[color] || colors.blue}`}>
        {icon}
      </div>
      <p className="text-lg font-bold">{value}</p>
      <p className="text-[10px] text-[var(--color-muted-foreground)]">{label}</p>
    </div>
  );
}
