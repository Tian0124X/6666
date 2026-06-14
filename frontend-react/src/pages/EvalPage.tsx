import { useState, useCallback } from "react";
import {
  Beaker, Play, Loader2, CheckCircle2, XCircle,
  Target, Clock, BarChart3, TrendingUp,
} from "lucide-react";

interface RAGEvalResult {
  id: string; question: string; recall: number;
  passed: boolean; latency_ms: number;
}
interface AgentEvalResult {
  id: string; task: string; expected: string;
  actual: string; match: boolean; latency_ms: number;
}
interface EvalSummary {
  api_success_rate: number; avg_latency_ms: number;
  total_requests: number; tool_calls: Record<string, number>;
  avg_rating: number | null; rating_count: number;
}

export default function EvalPage() {
  const [ragResult, setRagResult] = useState<{
    accuracy: number; avg_recall: number; avg_latency_ms: number;
    passed: number; total: number; details: RAGEvalResult[];
  } | null>(null);
  const [agentResult, setAgentResult] = useState<{
    tool_accuracy: number; avg_latency_ms: number;
    tool_match_count: number; total: number; details: AgentEvalResult[];
  } | null>(null);
  const [summary, setSummary] = useState<EvalSummary | null>(null);
  const [loading, setLoading] = useState("");

  const runRagEval = useCallback(async () => {
    setLoading("rag");
    try {
      const res = await fetch("/api/eval/rag", { method: "POST" });
      setRagResult(await res.json());
    } catch { /* ignore */ }
    setLoading("");
  }, []);

  const runAgentEval = useCallback(async () => {
    setLoading("agent");
    try {
      const res = await fetch("/api/eval/agent", { method: "POST" });
      setAgentResult(await res.json());
    } catch { /* ignore */ }
    setLoading("");
  }, []);

  const fetchSummary = useCallback(async () => {
    try {
      const res = await fetch("/api/eval/summary");
      setSummary(await res.json());
    } catch { /* ignore */ }
  }, []);

  return (
    <div className="h-screen flex flex-col">
      <header className="border-b border-[var(--color-border)] bg-[var(--color-card)] px-6 py-4 flex items-center justify-between">
        <h2 className="font-semibold text-[var(--color-foreground)] flex items-center gap-2">
          <Beaker className="w-5 h-5" />
          自动化评测
        </h2>
        <button
          onClick={fetchSummary}
          className="px-3 py-1.5 rounded-lg border border-[var(--color-border)] text-xs hover:bg-[var(--color-accent)] transition-colors"
        >
          刷新总览
        </button>
      </header>

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-6xl mx-auto space-y-6">
          {/* Summary */}
          {summary && (
            <div className="grid grid-cols-5 gap-4">
              <ScoreCard icon={<Target />} label="API 成功率" value={`${summary.api_success_rate}%`} color="green" />
              <ScoreCard icon={<Clock />} label="平均延迟" value={`${summary.avg_latency_ms}ms`} color="blue" />
              <ScoreCard icon={<BarChart3 />} label="总请求" value={summary.total_requests} color="purple" />
              <ScoreCard icon={<TrendingUp />} label="用户评分" value={summary.avg_rating ? `${summary.avg_rating}/5` : "N/A"} color="amber" />
              <ScoreCard icon={<Beaker />} label="工具调用" value={Object.keys(summary.tool_calls).length} color="indigo" />
            </div>
          )}

          <div className="grid grid-cols-2 gap-6">
            {/* RAG Eval */}
            <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-medium flex items-center gap-2">
                  📚 RAG 评测
                  <span className="text-xs text-[var(--color-muted-foreground)]">
                    (10 条测试集 · 关键词召回)
                  </span>
                </h3>
                <button
                  onClick={runRagEval}
                  disabled={loading === "rag"}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
                >
                  {loading === "rag" ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
                  运行评测
                </button>
              </div>

              {ragResult && (
                <>
                  <div className="grid grid-cols-3 gap-3 mb-4">
                    <MiniStat label="准确率" value={`${(ragResult.accuracy * 100).toFixed(0)}%`} target="≥85%" ok={ragResult.accuracy >= 0.85} />
                    <MiniStat label="平均召回" value={`${(ragResult.avg_recall * 100).toFixed(0)}%`} target="≥85%" ok={ragResult.avg_recall >= 0.85} />
                    <MiniStat label="平均延迟" value={`${ragResult.avg_latency_ms.toFixed(0)}ms`} target="<2s" ok={ragResult.avg_latency_ms < 2000} />
                  </div>
                  <div className="space-y-1 max-h-60 overflow-auto">
                    {ragResult.details.map((r) => (
                      <div key={r.id} className="flex items-center gap-2 text-xs py-1 border-b border-[var(--color-border)] last:border-0">
                        {r.passed ? <CheckCircle2 className="w-3 h-3 text-green-500" /> : <XCircle className="w-3 h-3 text-red-500" />}
                        <span className="font-mono w-10">{r.id}</span>
                        <span className="flex-1 truncate">{r.question}</span>
                        <span className="w-12 text-right">{`${(r.recall * 100).toFixed(0)}%`}</span>
                        <span className="w-16 text-right text-[var(--color-muted-foreground)]">{r.latency_ms}ms</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>

            {/* Agent Eval */}
            <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-medium flex items-center gap-2">
                  🤖 Agent 评测
                  <span className="text-xs text-[var(--color-muted-foreground)]">
                    (5 条测试集 · 工具路由)
                  </span>
                </h3>
                <button
                  onClick={runAgentEval}
                  disabled={loading === "agent"}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
                >
                  {loading === "agent" ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
                  运行评测
                </button>
              </div>

              {agentResult && (
                <>
                  <div className="grid grid-cols-3 gap-3 mb-4">
                    <MiniStat label="工具准确率" value={`${(agentResult.tool_accuracy * 100).toFixed(0)}%`} target="≥80%" ok={agentResult.tool_accuracy >= 0.8} />
                    <MiniStat label="匹配数" value={`${agentResult.tool_match_count}/${agentResult.total}`} target="" ok={agentResult.tool_match_count >= 4} />
                    <MiniStat label="平均延迟" value={`${agentResult.avg_latency_ms.toFixed(0)}ms`} target="<500ms" ok={agentResult.avg_latency_ms < 500} />
                  </div>
                  <div className="space-y-1 max-h-60 overflow-auto">
                    {agentResult.details.map((r) => (
                      <div key={r.id} className="flex items-center gap-2 text-xs py-1 border-b border-[var(--color-border)] last:border-0">
                        {r.match ? <CheckCircle2 className="w-3 h-3 text-green-500" /> : <XCircle className="w-3 h-3 text-red-500" />}
                        <span className="font-mono w-10">{r.id}</span>
                        <span className="flex-1 truncate">{r.task}</span>
                        <span className="w-24 text-right font-mono">{r.expected} → {r.actual}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ScoreCard({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: string | number; color: string }) {
  const colors: Record<string, string> = {
    green: "bg-green-50 text-green-700", blue: "bg-blue-50 text-blue-700",
    purple: "bg-purple-50 text-purple-700", amber: "bg-amber-50 text-amber-700",
    indigo: "bg-indigo-50 text-indigo-700",
  };
  return (
    <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-4">
      <div className={`w-8 h-8 rounded-lg flex items-center justify-center mb-2 ${colors[color]}`}>{icon}</div>
      <p className="text-2xl font-bold">{value}</p>
      <p className="text-xs text-[var(--color-muted-foreground)]">{label}</p>
    </div>
  );
}

function MiniStat({ label, value, target, ok }: { label: string; value: string; target: string; ok: boolean }) {
  return (
    <div className={`rounded-lg p-3 ${ok ? "bg-green-50 dark:bg-green-900/20" : "bg-red-50 dark:bg-red-900/20"}`}>
      <p className="text-xs text-[var(--color-muted-foreground)]">{label}</p>
      <p className={`text-lg font-bold ${ok ? "text-green-700" : "text-red-700"}`}>{value}</p>
      {target && <p className="text-[10px] text-[var(--color-muted-foreground)]">目标: {target}</p>}
    </div>
  );
}
