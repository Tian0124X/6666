import { useState, useEffect, useCallback } from "react";
import { analyticsApi } from "../lib/api";
import {
  Activity, Users, Brain, Target, Loader2, Zap,
  Clock, TrendingUp, AlertTriangle,
} from "lucide-react";
import {
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar, Legend,
} from "recharts";

interface AnalyticsOverview {
  today: {
    dau: number;
    requests: number;
    success_rate: number;
    avg_latency_ms: number;
    errors: number;
  };
}

interface KnowledgeStats {
  rag_queries_today: number;
  cache_hit_rate: number;
}

interface PerformanceStats {
  p50: number;
  p95: number;
  p99: number;
}

export default function AnalyticsPage() {
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [trends, setTrends] = useState<Record<string, unknown>[]>([]);
  const [knowledgeData, setKnowledgeData] = useState<KnowledgeStats | null>(null);
  const [perfData, setPerfData] = useState<PerformanceStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(7);

  const fetch = useCallback(async () => {
    setLoading(true);
    try {
      const [ov, tr, kn, pf] = await Promise.all([
        analyticsApi.overview(),
        analyticsApi.trends(days),
        analyticsApi.knowledge().catch(() => null),
        analyticsApi.performance().catch(() => null),
      ]);
      setOverview(ov);
      setTrends(tr.trends || []);
      setKnowledgeData(kn);
      setPerfData(pf);
    } catch { /* ignore */ }
    setLoading(false);
  }, [days]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void fetch(); }, 0);
    return () => window.clearTimeout(timer);
  }, [fetch]);

  const today = overview?.today;

  return (
    <div className="h-screen flex flex-col">
      <header className="border-b border-[var(--color-border)] bg-[var(--color-card)] px-6 py-4 flex items-center justify-between">
        <h2 className="font-semibold text-[var(--color-foreground)] flex items-center gap-2">
          <Zap className="w-5 h-5" />
          深度分析
        </h2>
        <div className="flex items-center gap-2">
          {[7, 30, 90].map((d) => (
            <button key={d} onClick={() => setDays(d)}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                days === d ? "bg-primary text-primary-foreground" : "border border-[var(--color-border)] hover:bg-[var(--color-accent)]"
              }`}
            >{d}天</button>
          ))}
        </div>
      </header>

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-7xl mx-auto space-y-6">
          {loading ? (
            <div className="flex items-center justify-center py-24"><Loader2 className="w-6 h-6 animate-spin" /></div>
          ) : (
            <>
              {/* Stats */}
              <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
                <StatCard icon={<Users />} label="DAU" value={String(today?.dau ?? 0)} />
                <StatCard icon={<Activity />} label="今日请求" value={String(today?.requests ?? 0)} />
                <StatCard icon={<TrendingUp />} label="成功率" value={`${today?.success_rate ?? 0}%`} />
                <StatCard icon={<Clock />} label="平均延迟" value={`${today?.avg_latency_ms ?? 0}ms`} />
                <StatCard icon={<AlertTriangle />} label="错误数" value={String(today?.errors ?? 0)} />
              </div>

              {/* Trend Chart */}
              <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-6">
                <h3 className="font-medium mb-4">📈 每日趋势 ({days}天)</h3>
                <div className="h-72">
                  <ResponsiveContainer>
                    <BarChart data={trends}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                      <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="var(--color-muted-foreground)" />
                      <YAxis tick={{ fontSize: 11 }} stroke="var(--color-muted-foreground)" />
                      <Tooltip />
                      <Legend />
                      <Bar dataKey="chat_start" name="对话开始" fill="#3b82f6" radius={[4, 4, 0, 0]} stackId="a" />
                      <Bar dataKey="chat_end" name="对话完成" fill="#10b981" radius={[4, 4, 0, 0]} stackId="a" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Knowledge + Quality */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-6">
                  <h3 className="font-medium mb-4 flex items-center gap-2">
                    <Brain className="w-4 h-4" />
                    知识库使用
                  </h3>
                  {knowledgeData ? (
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <p className="text-[var(--color-muted-foreground)]">今日 RAG 查询</p>
                        <p className="text-2xl font-bold">{knowledgeData.rag_queries_today ?? "--"}</p>
                      </div>
                      <div>
                        <p className="text-[var(--color-muted-foreground)]">缓存命中率</p>
                        <p className="text-2xl font-bold">{knowledgeData.cache_hit_rate != null ? `${Math.round(knowledgeData.cache_hit_rate * 100)}%` : "--"}</p>
                      </div>
                    </div>
                  ) : (
                    <div className="text-sm text-[var(--color-muted-foreground)]">暂无数据</div>
                  )}
                </div>
                <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-6">
                  <h3 className="font-medium mb-4 flex items-center gap-2">
                    <Target className="w-4 h-4" />
                    性能分布
                  </h3>
                  {perfData ? (
                    <div className="grid grid-cols-3 gap-3 text-sm">
                      <div>
                        <p className="text-[var(--color-muted-foreground)]">P50</p>
                        <p className="text-lg font-bold">{perfData.p50 ?? "--"} ms</p>
                      </div>
                      <div>
                        <p className="text-[var(--color-muted-foreground)]">P95</p>
                        <p className="text-lg font-bold">{perfData.p95 ?? "--"} ms</p>
                      </div>
                      <div>
                        <p className="text-[var(--color-muted-foreground)]">P99</p>
                        <p className="text-lg font-bold">{perfData.p99 ?? "--"} ms</p>
                      </div>
                    </div>
                  ) : (
                    <div className="text-sm text-[var(--color-muted-foreground)]">暂无数据</div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-4">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-[var(--color-muted-foreground)]">{icon}</span>
        <span className="text-xs text-[var(--color-muted-foreground)]">{label}</span>
      </div>
      <p className="text-2xl font-bold text-[var(--color-foreground)]">{value}</p>
    </div>
  );
}
