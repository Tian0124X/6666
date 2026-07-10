import { useEffect, useRef, useCallback, useState } from "react";
import { ChatBubble } from "../components/ChatBubble";
import { ChatInput } from "../components/ChatInput";
import { useChatStore } from "../stores/chatStore";
import type { ChatMessage } from "../stores/chatStore";
import { streamChat } from "../lib/api";
import { authHeader } from "../stores/authStore";
import { Sparkles, Trash2, BookOpen } from "lucide-react";
import { StarRating } from "../components/StarRating";
import { ApprovalDialog } from "../components/ApprovalDialog";

export default function ChatPage() {
  const {
    messages,
    isStreaming,
    activeSessionId,
    addMessage,
    updateLastAssistant,
    setStreaming,
    createSession,
    ensureSession,
  } = useChatStore();

  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [showRating, setShowRating] = useState(false);
  const [approval, setApproval] = useState<{ thread_id: string; action: string; description: string; details: Record<string,unknown> } | null>(null);
  const [dataFilePath, setDataFilePath] = useState("");
  const [dataFileName, setDataFileName] = useState("");
  const [mode, setMode] = useState<"auto" | "rag">("auto");

  // 确保有活跃会话 (首次加载或会话被删后自动创建)
  useEffect(() => {
    ensureSession();
  }, [ensureSession]);

  // 轮询人类审批 (10s间隔，已有弹窗时跳过)
  useEffect(() => {
    if (approval) return;  // 已有审批弹窗，停止轮询
    let mounted = true;
    const interval = setInterval(async () => {
      try {
        const res = await fetch("/api/chat/approvals", { headers: { ...authHeader() } });
        const data = await res.json();
        if (mounted && data.pending) setApproval(data.approval);
      } catch { /* ignore */ }
    }, 10_000);
    return () => { mounted = false; clearInterval(interval); };
  }, [approval]);

  const handleRate = async (score: number) => {
    try {
      await fetch("/api/chat/rate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: activeSessionId, score }),
      });
    } catch { /* ignore */ }
    setShowRating(false);
  };

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    // 仅当用户在底部附近 (< 200px) 或正在流式传输时才自动滚动
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 200;
    if (isStreaming || isNearBottom) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
  }, [messages, isStreaming]);

  const handleSend = useCallback(
    (text: string) => {
      // 如果附加了数据文件，构建带文件上下文的消息
      let displayText = text;
      let sendText = text;
      if (dataFilePath) {
        displayText = `📊 [数据文件: ${dataFileName}]\n${text}`;
        sendText = `[已上传数据文件: ${dataFilePath}]\n用户问题: ${text}`;
      }

      addMessage({ role: "user", content: displayText });
      const assistantMsg: Omit<ChatMessage, "id"> = {
        role: "assistant",
        content: "",
        isStreaming: true,
        dataFilePath: dataFilePath || undefined,
      };
      addMessage(assistantMsg);
      setStreaming(true);

      const ctrl = streamChat(
        { message: sendText, session_id: activeSessionId, with_chart: true, mode },
        (chunk) => updateLastAssistant(chunk),
        () => {
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
          // 流结束后缓存到 localStorage (图表/表格/洞察不丢失)
          useChatStore.getState().cacheCurrentSession();
        },
        (err) => {
          useChatStore.setState((s) => {
            const msgs = [...s.messages];
            for (let i = msgs.length - 1; i >= 0; i--) {
              if (msgs[i].role === "assistant" && msgs[i].isStreaming) {
                msgs[i] = { ...msgs[i], isStreaming: false, content: msgs[i].content + `\n\n❌ 错误: ${err}` };
                break;
              }
            }
            return { messages: msgs, isStreaming: false };
          });
        },
        (data) => {
          // 接收结构化数据 — 表格、图表、洞察、建议、文件路径、报告URL、RAG结果
          const store = useChatStore.getState();
          const msgs = [...store.messages];
          for (let i = msgs.length - 1; i >= 0; i--) {
            if (msgs[i].role === "assistant") {
              // RAG 快速通道返回的来源数据
              if (data.type === "knowledge_result") {
                msgs[i] = {
                  ...msgs[i],
                  sources: (data.sources || []).map((s) => ({ filename: s.filename, excerpt: s.excerpt || "" })),
                  knowledgeMode: data.mode,
                  knowledgeLevel: data.level,
                  fromCache: data.from_cache,
                };
                break;
              }
              // 数据分析结构化结果
              const existing = msgs[i].dataResult || {} as Record<string, unknown>;
              const dr: Record<string, unknown> = { ...existing };
              if (data.table) {
                dr.type = "dataframe";
                dr.columns = data.table.columns;
                dr.rows = data.table.rows;
                dr.shape = data.table.shape;
              }
              if (data.chart) dr.chart = data.chart;
              if (data.scalar != null) {
                dr.type = dr.type || "scalar";
                dr.value = data.scalar;
              }
              if (data.insights) dr.insights = data.insights;
              if (data.suggested_questions) dr.suggestedQuestions = data.suggested_questions;
              if (data.file_path) dr.filePath = data.file_path;
              if (data.report_url) dr.reportUrl = data.report_url;
              msgs[i] = {
                ...msgs[i],
                code: data.code || msgs[i].code,
                dataResult: Object.keys(dr).length > 0 ? dr as ChatMessage['dataResult'] : undefined,
              };
              break;
            }
          }
          useChatStore.setState({ messages: msgs });
        }
      );
      abortRef.current = ctrl;
    },
    [addMessage, setStreaming, updateLastAssistant, activeSessionId, dataFilePath, dataFileName, mode]
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
          {mode === "rag" && (
            <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded bg-primary/10 text-primary">
              <BookOpen className="w-3 h-3" /> 知识库问答
            </span>
          )}
          {isStreaming && (
            <span className="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary animate-pulse">
              生成中...
            </span>
          )}
        </div>
        <button
          onClick={async () => { await createSession(); }}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs text-muted-foreground hover:bg-accent transition-colors"
        >
          <Trash2 className="w-3.5 h-3.5" />
          新建对话
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
              <ChatBubble key={msg.id} msg={msg} onSuggestionClick={handleSend} />
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
        onDataFile={(filePath, fileName) => { setDataFilePath(filePath); setDataFileName(fileName); }}
        dataFileName={dataFileName}
        onClearDataFile={() => { setDataFilePath(""); setDataFileName(""); }}
        mode={mode}
        onModeChange={setMode}
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
