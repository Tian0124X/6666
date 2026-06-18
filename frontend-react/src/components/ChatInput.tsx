import { useState, useRef } from "react";
import { Send, Square, ImagePlus, FileSpreadsheet, Loader2, X } from "lucide-react";

interface Props {
  onSend: (msg: string) => void;
  onImage?: (file: File, question: string, result: string) => void;
  onDataFile?: (filePath: string, fileName: string) => void;
  onStop?: () => void;
  isStreaming: boolean;
  disabled?: boolean;
  dataFileName?: string;
  onClearDataFile?: () => void;
}

export function ChatInput({ onSend, onImage, onDataFile, onStop, isStreaming, disabled, dataFileName, onClearDataFile }: Props) {
  const [input, setInput] = useState("");
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const dataFileRef = useRef<HTMLInputElement>(null);

  const handleSubmit = () => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;
    onSend(trimmed);
    setInput("");
  };

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !onImage) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("question", input || "请描述这张图片的内容");
      const res = await fetch("/api/chat/image", { method: "POST", body: fd });
      const data = await res.json();
      onImage(file, input || "分析这张图片", data.answer || data.analysis || "");
      setInput("");
    } catch { /* ignore */ }
    setUploading(false);
    if (fileRef.current) fileRef.current.value = "";
  };

  const handleDataFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !onDataFile) return;

    // 文件大小校验 (最大 50MB)
    const MAX_SIZE = 50 * 1024 * 1024;
    if (file.size > MAX_SIZE) {
      alert(`文件过大 (${(file.size / 1024 / 1024).toFixed(1)}MB)，最大支持 50MB`);
      if (dataFileRef.current) dataFileRef.current.value = "";
      return;
    }

    // 文件扩展名校验
    const allowedExts = [".xlsx", ".xls", ".csv"];
    const fileName = file.name.toLowerCase();
    if (!allowedExts.some((ext) => fileName.endsWith(ext))) {
      alert(`不支持的文件格式，请上传 Excel (.xlsx, .xls) 或 CSV (.csv) 文件`);
      if (dataFileRef.current) dataFileRef.current.value = "";
      return;
    }

    setUploading(true);
    try {
      const { knowledgeApi } = await import("../lib/api");
      const res = await knowledgeApi.upload(file);
      const uploadedName = res.filename || file.name;
      const safeName = uploadedName.replace(/\.\./g, '').replace(/[\\/]/g, '');
      onDataFile(`data/documents/${safeName}`, file.name);
    } catch { /* ignore */ }
    setUploading(false);
    if (dataFileRef.current) dataFileRef.current.value = "";
  };

  return (
    <div className="border-t border-border bg-card p-4">
      {/* Data file indicator */}
      {dataFileName && (
        <div className="max-w-4xl mx-auto mb-2 flex items-center gap-2 px-1">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-primary/10 text-primary text-xs font-medium">
            <FileSpreadsheet className="w-3 h-3" />
            {dataFileName}
            <button onClick={onClearDataFile} className="ml-1 hover:bg-primary/20 rounded p-0.5">
              <X className="w-3 h-3" />
            </button>
          </span>
          <span className="text-xs text-muted-foreground">已附加，可直接提问分析</span>
        </div>
      )}
      <div className="flex gap-3 max-w-4xl mx-auto">
        {/* Image upload */}
        <input ref={fileRef} type="file" accept="image/*" onChange={handleImageUpload} className="hidden" />
        <button onClick={() => fileRef.current?.click()} disabled={disabled || uploading}
          className="px-3 py-3 rounded-xl border border-border hover:bg-accent transition-colors disabled:opacity-50" title="上传图片">
          {uploading ? <Loader2 className="w-5 h-5 animate-spin" /> : <ImagePlus className="w-5 h-5" />}
        </button>

        {/* Data file upload (Excel/CSV) */}
        <input ref={dataFileRef} type="file" accept=".xlsx,.xls,.csv" onChange={handleDataFileUpload} className="hidden" />
        <button onClick={() => dataFileRef.current?.click()} disabled={disabled || uploading}
          className="px-3 py-3 rounded-xl border border-border hover:bg-accent transition-colors disabled:opacity-50" title="上传Excel/CSV数据文件">
          <FileSpreadsheet className="w-5 h-5" />
        </button>

        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSubmit();
            }
          }}
          placeholder="输入问题或上传图片分析... (Enter 发送)"
          disabled={disabled}
          className="flex-1 px-4 py-3 rounded-xl border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
        />
        {isStreaming ? (
          <button
            onClick={onStop}
            className="px-4 py-3 rounded-xl bg-destructive text-destructive-foreground hover:opacity-90 transition-opacity flex items-center gap-2"
          >
            <Square className="w-4 h-4" fill="currentColor" />
            停止
          </button>
        ) : (
          <button
            onClick={handleSubmit}
            disabled={disabled || !input.trim()}
            className="px-4 py-3 rounded-xl bg-primary text-primary-foreground hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center gap-2"
          >
            <Send className="w-4 h-4" />
            发送
          </button>
        )}
      </div>
    </div>
  );
}
