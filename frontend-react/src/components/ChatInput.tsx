import { useState, useRef } from "react";
import { Send, Square, ImagePlus, Loader2 } from "lucide-react";

interface Props {
  onSend: (msg: string) => void;
  onImage?: (file: File, question: string, result: string) => void;
  onStop?: () => void;
  isStreaming: boolean;
  disabled?: boolean;
}

export function ChatInput({ onSend, onImage, onStop, isStreaming, disabled }: Props) {
  const [input, setInput] = useState("");
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

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

  return (
    <div className="border-t border-border bg-card p-4">
      <div className="flex gap-3 max-w-4xl mx-auto">
        {/* Image upload */}
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          onChange={handleImageUpload}
          className="hidden"
        />
        <button
          onClick={() => fileRef.current?.click()}
          disabled={disabled || uploading}
          className="px-3 py-3 rounded-xl border border-border hover:bg-accent transition-colors disabled:opacity-50"
          title="上传图片"
        >
          {uploading ? <Loader2 className="w-5 h-5 animate-spin" /> : <ImagePlus className="w-5 h-5" />}
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
