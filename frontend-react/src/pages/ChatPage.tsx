import { useEffect, useRef, useCallback, useState } from "react";
import { ChatBubble } from "../components/ChatBubble";
import { ChatInput } from "../components/ChatInput";
import { useChatStore } from "../stores/chatStore";
import { useAuthStore } from "../stores/authStore";
import type { ChatMessage } from "../stores/chatStore";
import { streamChat } from "../lib/api";
import { Sparkles, Trash2 } from "lucide-react";
import { StarRating } from "../components/StarRating";
import { ApprovalDialog } from "../components/ApprovalDialog";

export default function ChatPage() {
  const {
    messages,
    isStreaming,
    addMessage,
    updateLastAssistant,
    setStreaming,
    clearMessages,
  } = useChatStore();

  const { user } = useAuthStore();
  const userId = user?.username || "anonymous";
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [showRating, setShowRating] = useState(false);
  const [approval, setApproval] = useState<{ thread_id: string; action: string; description: string; details: Record<string,unknown> } | null>(null);

  // 轮询人类审批
  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/chat/approvals/${userId}`);
        const data = await res.json();
        if (data.pending) setApproval(data.approval);
      } catch { /* ignore */ }
    }, 3000);
    return () => clearInterval(interval);
  }, [userId]);

  const handleRate = async (score: number) => {
    try {
      await fetch("/api/chat/rate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: userId, score }),
      });
    } catch { /* ignore */ }
    setShowRating(false);
  };

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const handleSend = useCallback(
    (text: string) => {
      addMessage({ role: "user", content: text });
      const assistantMsg: Omit<ChatMessage, "id"> = {
        role: "assistant",
        content: "",
        isStreaming: true,
      };
      addMessage(assistantMsg);
      setStreaming(true);

      const ctrl = streamChat(
        { message: text, user_id: userId },
        (chunk) => updateLastAssistant(chunk),
        () => {
          setStreaming(false);
          // Show rating after assistant finishes
          setShowRating(true);
          useChatStore.setState((s) => {
            const msgs = [...s.messages];
            for (let i = msgs.length - 1; i >= 0; i--) {
              if (msgs[i].role === "assistant" && msgs[i].isStreaming) {
                msgs[i] = { ...msgs[i], isStreaming: false };
                break;
              }
            }
            return { messages: msgs, isStreaming: false };
          });
        },
        (err) => {
          setStreaming(false);
          updateLastAssistant(`\n\n❌ 错误: ${err}`);
        }
      );
      abortRef.current = ctrl;
    },
    [addMessage, setStreaming, updateLastAssistant]
  );

  const handleStop = () => {
    abortRef.current?.abort();
    setStreaming(false);
    useChatStore.setState((s) => {
      const msgs = [...s.messages];
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === "assistant" && msgs[i].isStreaming) {
          msgs[i] = { ...msgs[i], isStreaming: false, content: msgs[i].content + "\n\n⏹ *已停止*" };
          break;
        }
      }
      return { messages: msgs, isStreaming: false };
    });
  };

  return (
    <div className="flex flex-col h-screen">
      {/* Header */}
      <header className="border-b border-border bg-card px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Sparkles className="w-5 h-5 text-primary" />
          <h2 className="font-semibold text-foreground">智能对话</h2>
          {isStreaming && (
            <span className="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary animate-pulse">
              生成中...
            </span>
          )}
        </div>
        <button
          onClick={clearMessages}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs text-muted-foreground hover:bg-accent transition-colors"
        >
          <Trash2 className="w-3.5 h-3.5" />
          清空对话
        </button>
      </header>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-3">
            <Sparkles className="w-12 h-12 opacity-30" />
            <p className="text-lg font-medium">有什么可以帮您的？</p>
            <p className="text-sm max-w-md text-center">
              支持自然语言对话。可以问知识库问题、分析数据文件、查询 OA/CRM 信息。
            </p>
            <div className="flex gap-2 mt-2">
              {["分析本月销售数据", "公司年假政策是什么？", "帮我生成一份报表"].map((q) => (
                <button
                  key={q}
                  onClick={() => handleSend(q)}
                  className="px-3 py-1.5 rounded-full border border-border text-xs hover:bg-accent transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="max-w-4xl mx-auto py-6 px-4 space-y-4">
            {messages.map((msg) => (
              <ChatBubble key={msg.id} msg={msg} />
            ))}
            {showRating && !isStreaming && messages.length > 0 && (
              <div className="flex items-center gap-3 px-4 py-2 text-sm text-[var(--color-muted-foreground)]">
                <span>对这个回答评分:</span>
                <StarRating onRate={handleRate} />
              </div>
            )}
          </div>
        )}
      </div>

      {/* Input */}
      <ChatInput
        onSend={handleSend}
        onStop={handleStop}
        isStreaming={isStreaming}
        onImage={(file, question, answer) => {
          addMessage({
            role: "user",
            content: `🖼 [图片: ${file.name}]\n${question}`,
          });
          addMessage({
            role: "assistant",
            content: answer,
            taskType: "multi_agent",
          } as ChatMessage);
        }}
      />

      {/* Human-in-the-Loop 审批弹窗 */}
      {approval && (
        <ApprovalDialog
          approval={approval}
          onApprove={() => setApproval(null)}
          onReject={() => setApproval(null)}
        />
      )}
    </div>
  );
}
