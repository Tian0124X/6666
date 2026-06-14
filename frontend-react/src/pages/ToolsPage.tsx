import { useState } from "react";
import { toolsApi } from "../lib/api";
import {
  BarChart3,
  FileSpreadsheet,
  ClipboardCheck,
  Users,
  Upload,
  Loader2,
  Play,
} from "lucide-react";

type Tab = "data" | "oa" | "crm";

export default function ToolsPage() {
  const [tab, setTab] = useState<Tab>("data");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState("");

  // Data Analysis
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

  const handleAnalyze = async () => {
    if (!filePath.trim()) return;
    setLoading(true);
    setResult("");
    try {
      const res = await toolsApi.analyze(
        filePath,
        action,
        targetCol || undefined,
        chartType || undefined
      );
      setResult(res.result);
    } catch (e: unknown) {
      setResult(`❌ ${e instanceof Error ? e.message : String(e)}`);
    }
    setLoading(false);
  };

  const handleOa = async () => {
    setLoading(true);
    setResult("");
    try {
      const res = await toolsApi.oa(oaAction, oaValue || undefined);
      setResult(res.result);
    } catch (e: unknown) {
      setResult(`❌ ${e instanceof Error ? e.message : String(e)}`);
    }
    setLoading(false);
  };

  const handleCrm = async () => {
    setLoading(true);
    setResult("");
    try {
      const res = await toolsApi.crm(crmAction, crmValue || undefined);
      setResult(res.result);
    } catch (e: unknown) {
      setResult(`❌ ${e instanceof Error ? e.message : String(e)}`);
    }
    setLoading(false);
  };

  const tabs: { key: Tab; icon: React.ReactNode; label: string }[] = [
    { key: "data", icon: <BarChart3 className="w-4 h-4" />, label: "数据分析" },
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
      <div className="border-b border-border bg-card px-6 flex gap-0">
        {tabs.map(({ key, icon, label }) => (
          <button
            key={key}
            onClick={() => { setTab(key); setResult(""); }}
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
      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-4xl mx-auto space-y-6">
          {tab === "data" && (
            <div className="bg-card border border-border rounded-xl p-6 space-y-4">
              <h3 className="font-medium flex items-center gap-2">
                <FileSpreadsheet className="w-4 h-4" />
                数据分析 (Excel/CSV)
              </h3>
              <div className="flex gap-3 items-end">
                <div className="flex-1">
                  <label className="text-xs text-muted-foreground block mb-1">
                    上传文件 (Excel/CSV, 限 50MB)
                  </label>
                  <label className="flex items-center gap-2 px-3 py-2 rounded-lg border-2 border-dashed border-border hover:border-primary cursor-pointer transition-colors">
                    <Upload className="w-4 h-4 text-muted-foreground" />
                    <span className="text-sm text-muted-foreground">
                      {file ? file.name : filePath || "选择文件..."}
                    </span>
                    <input
                      type="file"
                      accept=".xlsx,.xls,.csv"
                      onChange={async (e) => {
                        const f = e.target.files?.[0];
                        if (!f) return;
                        setFile(f);
                        setUploading(true);
                        try {
                          const { knowledgeApi } = await import("../lib/api");
                          const res = await knowledgeApi.upload(f);
                          const uploadedName = res.filename || f.name;
                          setFilePath(`data/documents/${uploadedName}`);
                          setResult(`✅ 文件已上传: ${res.message}`);
                        } catch (err: unknown) {
                          setResult(`❌ 上传失败: ${err instanceof Error ? err.message : String(err)}`);
                        }
                        setUploading(false);
                      }}
                      className="hidden"
                    />
                  </label>
                </div>
                <div className="w-32">
                  <label className="text-xs text-muted-foreground block mb-1">&nbsp;</label>
                  <button
                    onClick={handleAnalyze}
                    disabled={loading || uploading || !filePath.trim()}
                    className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
                  >
                    {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                    分析
                  </button>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="text-xs text-muted-foreground block mb-1">分析模式</label>
                  <select
                    value={action}
                    onChange={(e) => setAction(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm focus:ring-2 focus:ring-ring focus:outline-none"
                  >
                    <option value="summary">概览 (Summary)</option>
                    <option value="analyze">深度分析 (Analyze)</option>
                    <option value="full_report">Word 报告 (Full Report)</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-muted-foreground block mb-1">目标列 (可选)</label>
                  <input
                    value={targetCol}
                    onChange={(e) => setTargetCol(e.target.value)}
                    placeholder="例如: 销售额"
                    className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm focus:ring-2 focus:ring-ring focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground block mb-1">图表类型</label>
                  <select
                    value={chartType}
                    onChange={(e) => setChartType(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm focus:ring-2 focus:ring-ring focus:outline-none"
                  >
                    <option value="bar">柱状图</option>
                    <option value="line">折线图</option>
                    <option value="pie">饼图</option>
                    <option value="scatter">散点图</option>
                  </select>
                </div>
              </div>
            </div>
          )}

          {tab === "oa" && (
            <div className="bg-card border border-border rounded-xl p-6 space-y-4">
              <h3 className="font-medium flex items-center gap-2">
                <ClipboardCheck className="w-4 h-4" />
                OA 审批查询
              </h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-muted-foreground block mb-1">查询模式</label>
                  <select
                    value={oaAction}
                    onChange={(e) => setOaAction(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm focus:ring-2 focus:ring-ring focus:outline-none"
                  >
                    <option value="list_approvals">全部审批</option>
                    <option value="query_by_id">按编号查询</option>
                    <option value="query_by_user">按申请人查询</option>
                    <option value="query_by_status">按状态查询</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-muted-foreground block mb-1">查询值</label>
                  <input
                    value={oaValue}
                    onChange={(e) => setOaValue(e.target.value)}
                    placeholder={oaAction === "query_by_id" ? "例如: OA-001" : "例如: 张三"}
                    className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm focus:ring-2 focus:ring-ring focus:outline-none"
                  />
                </div>
              </div>
              <button
                onClick={handleOa}
                disabled={loading}
                className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                查询
              </button>
            </div>
          )}

          {tab === "crm" && (
            <div className="bg-card border border-border rounded-xl p-6 space-y-4">
              <h3 className="font-medium flex items-center gap-2">
                <Users className="w-4 h-4" />
                CRM 客户查询
              </h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-muted-foreground block mb-1">查询模式</label>
                  <select
                    value={crmAction}
                    onChange={(e) => setCrmAction(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm focus:ring-2 focus:ring-ring focus:outline-none"
                  >
                    <option value="list_customers">全部客户</option>
                    <option value="query_by_id">按编号查询</option>
                    <option value="query_by_industry">按行业查询</option>
                    <option value="query_by_level">按等级查询</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-muted-foreground block mb-1">查询值</label>
                  <input
                    value={crmValue}
                    onChange={(e) => setCrmValue(e.target.value)}
                    placeholder={crmAction === "query_by_id" ? "例如: CRM-001" : "例如: 互联网"}
                    className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm focus:ring-2 focus:ring-ring focus:outline-none"
                  />
                </div>
              </div>
              <button
                onClick={handleCrm}
                disabled={loading}
                className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                查询
              </button>
            </div>
          )}

          {/* Result */}
          {result && (
            <div className="bg-card border border-border rounded-xl p-4">
              <pre className="text-sm whitespace-pre-wrap font-mono text-foreground">
                {result}
              </pre>
            </div>
          )}
        </div>
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
