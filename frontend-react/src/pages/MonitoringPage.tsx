import { useState, useEffect, useCallback } from "react";
import {
  Activity, TrendingUp, Clock, AlertTriangle,
  Zap, Star, RefreshCw, BarChart3,
} from "lucide-react";

interface DashboardData {
  requests_total: number;
  success_rate: number;
  avg_latency_ms: number;
  errors_today: number;
  avg_rating: number | null;
  tools_used: number;
}

interface FullStats {
  overview: {
    total_requests: number;
    success: number;
    errors: number;
    error_rate_pct: number;
    avg_latency_ms: number;
    total_tokens: number;
  };
  avg_rating: number | null;
  rating_count: number;
  top_endpoints: { endpoint: string; count: number; avg_ms: number; errors: number }[];
  top_tools: { tool: string; calls: number }[];
  hourly_requests: { hour: string; count: number }[];
  recent_requests: { time: string; method: string; path: string; status: number; latency_ms: number }[];
  uptime_since: string;
}

export default function MonitoringPage() {
  const [dash, setDash] = useState<DashboardData | null>(null);
  const [stats, setStats] = useState<FullStats | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [dRes, sRes] = await Promise.all([
        fetch("/api/stats/dashboard").then((r) => r.json()),
        fetch("/api/stats").then((r) => r.json()),
      ]);
      setDash(dRes);
      setStats(sRes);
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  return (
    <div className="h-screen flex flex-col">
      <header className="border-b border-[var(--color-border)] bg-[var(--color-card)] px-6 py-4 flex items-center justify-between">
        <h2 className="font-semibold text-[var(--color-foreground)] flex items-center gap-2">
          <Activity className="w-5 h-5" />
          LLMOps 监控面板
        </h2>
        <button onClick={fetchData} className="p-2 rounded-lg hover:bg-[var(--color-accent)] transition-colors">
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
        </button>
      </header>

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-6xl mx-auto space-y-6">
          {/* KPI Cards */}
          {dash && (
            <div className="grid grid-cols-4 gap-4">
              <KpiCard icon={<Zap />} label="总请求" value={dash.requests_total} color="blue" />
              <KpiCard icon={<TrendingUp />} label="成功率" value={`${dash.success_rate}%`} color="green" />
              <KpiCard icon={<Clock />} label="平均延迟" value={`${dash.avg_latency_ms}ms`} color="amber" />
              <KpiCard icon={<Star />} label="用户评分" value={dash.avg_rating ? `${dash.avg_rating}/5` : "暂无"} color="purple" />
              <KpiCard icon={<AlertTriangle />} label="今日错误" value={dash.errors_today} color="red" />
              <KpiCard icon={<BarChart3 />} label="工具调用" value={dash.tools_used} color="indigo" />
            </div>
          )}

          {stats && (
            <>
              {/* Hourly Distribution */}
              <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-6">
                <h3 className="font-medium mb-4">📊 请求分布 (按小时)</h3>
                <div className="flex items-end gap-1 h-32">
                  {stats.hourly_requests.map((h) => {
                    const maxCount = Math.max(...stats.hourly_requests.map((x) => x.count), 1);
                    const height = (h.count / maxCount) * 100;
                    return (
                      <div key={h.hour} className="flex-1 flex flex-col items-center gap-1" title={`${h.hour}: ${h.count} 请求`}>
                        <span className="text-xs text-[var(--color-muted-foreground)]">{h.count}</span>
                        <div
                          className="w-full bg-blue-500 rounded-t"
                          style={{ height: `${Math.max(height, 2)}%` }}
                        />
                        <span className="text-[10px] text-[var(--color-muted-foreground)]">{h.hour}</span>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Top Endpoints & Tools */}
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-6">
                  <h3 className="font-medium mb-3">🔝 Top API 端点</h3>
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-[var(--color-muted-foreground)] text-xs">
                        <th className="text-left pb-2">端点</th>
                        <th className="text-right pb-2">次数</th>
                        <th className="text-right pb-2">平均</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stats.top_endpoints.slice(0, 8).map((ep) => (
                        <tr key={ep.endpoint} className="border-t border-[var(--color-border)]">
                          <td className="py-1.5 text-xs font-mono">{ep.endpoint}</td>
                          <td className="py-1.5 text-right text-xs">{ep.count}</td>
                          <td className="py-1.5 text-right text-xs">{ep.avg_ms}ms</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-6">
                  <h3 className="font-medium mb-3">🔧 Top 工具调用</h3>
                  {stats.top_tools.length === 0 ? (
                    <p className="text-sm text-[var(--color-muted-foreground)]">暂无工具调用</p>
                  ) : (
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-[var(--color-muted-foreground)] text-xs">
                          <th className="text-left pb-2">工具</th>
                          <th className="text-right pb-2">次数</th>
                        </tr>
                      </thead>
                      <tbody>
                        {stats.top_tools.map((t) => (
                          <tr key={t.tool} className="border-t border-[var(--color-border)]">
                            <td className="py-1.5 text-xs">{t.tool}</td>
                            <td className="py-1.5 text-right text-xs font-mono">{t.calls}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>

              {/* Recent Requests */}
              <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-6">
                <h3 className="font-medium mb-3">📜 最近请求</h3>
                <div className="space-y-1 max-h-64 overflow-auto">
                  {stats.recent_requests.map((r, i) => (
                    <div key={i} className="flex items-center gap-3 text-xs py-1 border-b border-[var(--color-border)] last:border-0">
                      <span className={`w-2 h-2 rounded-full ${r.status < 400 ? "bg-green-500" : "bg-red-500"}`} />
                      <span className="text-[var(--color-muted-foreground)] w-16">{r.time.slice(11, 19)}</span>
                      <span className="font-mono w-12">{r.method}</span>
                      <span className="font-mono flex-1 truncate">{r.path}</span>
                      <span className={r.status < 400 ? "text-green-600" : "text-red-600"}>{r.status}</span>
                      <span className="text-[var(--color-muted-foreground)] w-16 text-right">{r.latency_ms}ms</span>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function KpiCard({ icon, label, value, color }: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  color: string;
}) {
  const colors: Record<string, string> = {
    blue: "bg-blue-50 text-blue-700",
    green: "bg-green-50 text-green-700",
    amber: "bg-amber-50 text-amber-700",
    purple: "bg-purple-50 text-purple-700",
    red: "bg-red-50 text-red-700",
    indigo: "bg-indigo-50 text-indigo-700",
  };
  return (
    <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-4">
      <div className="flex items-center gap-2 mb-2">
        <span className={colors[color] + " p-1.5 rounded-lg"}>{icon}</span>
        <span className="text-xs text-[var(--color-muted-foreground)]">{label}</span>
      </div>
      <p className="text-2xl font-bold text-[var(--color-foreground)]">{value}</p>
    </div>
  );
}
