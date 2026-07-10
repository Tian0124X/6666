import { useState } from "react";
import { useThemeStore } from "../stores/themeStore";
import { Settings, Moon, Sun } from "lucide-react";

export default function SettingsPage() {
  const { theme, setTheme } = useThemeStore();
  const [model, setModel] = useState(() => {
    try { return localStorage.getItem("settings_model") || "deepseek-chat"; }
    catch { return "deepseek-chat"; }
  });
  const [temperature, setTemperature] = useState(() => {
    try { return Number(localStorage.getItem("settings_temperature") || "0.5"); }
    catch { return 0.5; }
  });
  const [tools, setTools] = useState(() => {
    try {
      const saved = localStorage.getItem("settings_tools");
      return saved ? JSON.parse(saved) : { dataAnalyzer: true, oaCrm: true, knowledgeSearch: true };
    } catch {
      return { dataAnalyzer: true, oaCrm: true, knowledgeSearch: true };
    }
  });

  const persist = (key: string, value: string) => {
    try { localStorage.setItem(key, value); } catch { /* privacy mode */ }
  };

  return (
    <div className="h-screen flex flex-col">
      <header className="border-b border-border bg-card px-6 py-4">
        <h2 className="font-semibold text-foreground flex items-center gap-2">
          <Settings className="w-5 h-5" />
          偏好设置
        </h2>
      </header>

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-2xl mx-auto space-y-6">
          {/* Theme */}
          <div className="bg-card border border-border rounded-xl p-6 space-y-4">
            <h3 className="font-medium flex items-center gap-2">
              {theme === "dark" ? <Moon className="w-4 h-4" /> : <Sun className="w-4 h-4" />}
              外观主题
            </h3>
            <div className="flex gap-3">
              {(["light", "dark"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTheme(t)}
                  className={`px-4 py-3 rounded-xl border-2 text-sm font-medium transition-all ${
                    theme === t
                      ? "border-primary bg-primary/5 text-primary"
                      : "border-border text-muted-foreground hover:border-muted-foreground"
                  }`}
                >
                  {t === "light" ? "☀️ 亮色" : "🌙 暗色"}
                </button>
              ))}
            </div>
          </div>

          {/* Model */}
          <div className="bg-card border border-border rounded-xl p-6 space-y-4">
            <h3 className="font-medium">模型设置</h3>
            <div className="space-y-4">
              <div>
                <label className="text-xs text-muted-foreground block mb-1">
                  LLM 模型
                </label>
                <select
                  value={model}
                  onChange={(e) => { setModel(e.target.value); persist("settings_model", e.target.value); }}
                  className="w-full px-3 py-2.5 rounded-lg border border-input bg-background text-sm focus:ring-2 focus:ring-ring focus:outline-none"
                >
                  <option value="deepseek-chat">DeepSeek Chat</option>
                  <option value="deepseek-reasoner">DeepSeek Reasoner</option>
                  <option value="qwen-turbo">Qwen Turbo</option>
                  <option value="qwen-plus">Qwen Plus</option>
                  <option value="qwen-max">Qwen Max</option>
                </select>
              </div>
              <div>
                <label className="text-xs text-muted-foreground block mb-1">
                  Temperature: {temperature.toFixed(1)}
                </label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.1"
                  value={temperature}
                  onChange={(e) => { setTemperature(Number(e.target.value)); persist("settings_temperature", e.target.value); }}
                  className="w-full accent-primary"
                />
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>精确 (0)</span>
                  <span>创造性 (1)</span>
                </div>
              </div>
            </div>
          </div>

          {/* Tools */}
          <div className="bg-card border border-border rounded-xl p-6 space-y-4">
            <h3 className="font-medium">工具开关</h3>
            <div className="space-y-3">
              {[
                { key: "dataAnalyzer" as const, label: "数据分析工具", desc: "Excel/CSV 读取、统计、图表生成" },
                { key: "oaCrm" as const, label: "OA / CRM 工具", desc: "审批查询、客户信息检索" },
                { key: "knowledgeSearch" as const, label: "知识库检索", desc: "RAG 文档问答与来源追溯" },
              ].map(({ key, label, desc }) => (
                <label
                  key={key}
                  className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-accent/30 transition-colors cursor-pointer"
                >
                  <div>
                    <p className="text-sm font-medium">{label}</p>
                    <p className="text-xs text-muted-foreground">{desc}</p>
                  </div>
                  <input
                    type="checkbox"
                    checked={tools[key]}
                    onChange={() => {
                      const next = { ...tools, [key]: !tools[key] };
                      setTools(next);
                      persist("settings_tools", JSON.stringify(next));
                    }}
                    className="w-5 h-5 rounded accent-primary"
                  />
                </label>
              ))}
            </div>
          </div>

          {/* Note */}
          <p className="text-xs text-muted-foreground text-center">
            设置当前保存在浏览器本地存储中。后端模型配置请修改 .env 文件。
          </p>
        </div>
      </div>
    </div>
  );
}
