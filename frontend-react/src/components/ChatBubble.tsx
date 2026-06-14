import { Bot, User } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "../stores/chatStore";

const AGENT_ICONS: Record<string, string> = {
  data_agent: "📊 数据分析",
  oa_agent: "📋 OA审批",
  crm_agent: "👤 CRM",
  knowledge_agent: "📚 知识库",
};

export function ChatBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      {/* Avatar */}
      <div
        className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
          isUser ? "bg-primary" : "bg-secondary"
        }`}
      >
        {isUser ? (
          <User className="w-4 h-4 text-primary-foreground" />
        ) : (
          <Bot className="w-4 h-4 text-secondary-foreground" />
        )}
      </div>

      {/* Content */}
      <div
        className={`max-w-[75%] rounded-2xl px-4 py-3 ${
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-card border border-border text-foreground"
        }`}
      >
        {isUser ? (
          <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
        ) : (
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {msg.content}
            </ReactMarkdown>
          </div>
        )}

        {/* Streaming indicator */}
        {msg.isStreaming && (
          <span className="inline-block w-2 h-4 bg-primary animate-pulse rounded-sm ml-0.5" />
        )}

        {/* Task type badge */}
        {msg.taskType && (
          <span className="inline-block mt-1 text-[10px] px-1.5 py-0.5 rounded bg-secondary text-muted-foreground">
            {msg.taskType === "simple" ? "💬 快速问答" : msg.taskType === "multi_agent" ? "🤖 多Agent协作" : "📊 深度分析"}
          </span>
        )}
        {msg.agents && msg.agents.length > 0 && (
          <div className="flex gap-1 mt-1 flex-wrap">
            {msg.agents.map((a: string) => (
              <span key={a} className="text-[10px] px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-900/30 text-blue-700">
                {AGENT_ICONS[a] || a}
              </span>
            ))}
          </div>
        )}

        {/* Sources */}
        {msg.sources && msg.sources.length > 0 && (
          <div className="mt-2 pt-2 border-t border-border">
            <p className="text-xs text-muted-foreground mb-1">📚 参考来源:</p>
            {msg.sources.slice(0, 3).map((s, i) => (
              <p key={i} className="text-xs text-muted-foreground truncate">
                · {s.filename}: {s.excerpt.slice(0, 80)}...
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
