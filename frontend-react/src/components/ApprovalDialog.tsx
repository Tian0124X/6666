import { ShieldAlert, Check, X, Loader2 } from "lucide-react";
import { useState } from "react";

interface ApprovalData {
  thread_id: string;
  action: string;
  description: string;
  details: Record<string, unknown>;
}

const ACTION_LABELS: Record<string, string> = {
  delete_file: "🗑 删除文件",
  run_code: "💻 执行代码",
  external_api: "🌐 调用外部API",
  modify_config: "⚙️ 修改配置",
};

interface Props {
  approval: ApprovalData;
  onApprove: () => void;
  onReject: () => void;
}

export function ApprovalDialog({ approval, onApprove, onReject }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handle = async (action: "approve" | "reject") => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/chat/approvals/${approval.thread_id}/${action}`, { method: "POST" });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(err.detail || `操作失败 (${res.status})`);
      }
      if (action === "approve") {
        onApprove();
      } else {
        onReject();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失败，请重试");
    }
    setLoading(false);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-2xl p-6 max-w-md w-full mx-4 shadow-2xl">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-xl bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
            <ShieldAlert className="w-5 h-5 text-amber-600" />
          </div>
          <div>
            <h3 className="font-semibold text-[var(--color-foreground)]">需要您的确认</h3>
            <p className="text-xs text-[var(--color-muted-foreground)]">
              Agent 请求执行敏感操作
            </p>
          </div>
        </div>

        <div className="bg-[var(--color-background)] rounded-xl p-4 mb-4 space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-[var(--color-muted-foreground)]">操作类型:</span>
            <span className="text-sm font-medium">{ACTION_LABELS[approval.action] || approval.action}</span>
          </div>
          <div>
            <span className="text-xs text-[var(--color-muted-foreground)]">描述:</span>
            <p className="text-sm mt-0.5">{approval.description}</p>
          </div>
          {Object.keys(approval.details).length > 0 && (
            <div>
              <span className="text-xs text-[var(--color-muted-foreground)]">参数:</span>
              <pre className="text-xs mt-0.5 bg-[var(--color-card)] p-2 rounded overflow-auto max-h-24">
                {JSON.stringify(approval.details, null, 2)}
              </pre>
            </div>
          )}
        </div>

        {error && (
          <div className="mb-4 px-3 py-2 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-600 text-sm">
            {error}
          </div>
        )}

        <div className="flex gap-3">
          <button
            onClick={() => handle("reject")}
            disabled={loading}
            className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg border border-red-300 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 font-medium text-sm transition-colors disabled:opacity-50"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <X className="w-4 h-4" />}
            拒绝
          </button>
          <button
            onClick={() => handle("approve")}
            disabled={loading}
            className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700 font-medium text-sm transition-colors disabled:opacity-50"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
            批准
          </button>
        </div>
      </div>
    </div>
  );
}
