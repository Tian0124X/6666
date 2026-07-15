/** 知识库 RAG 问答工作台：只展示最终回答实际采纳的证据。 */

import { useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ChevronDown, ChevronUp, FileText, MessageSquarePlus, Search,
  Send, ShieldCheck, Sparkles, ThumbsDown, ThumbsUp,
} from "lucide-react";
import { EvidenceDrawer } from "../components/EvidenceDrawer";
import { streamRagAnswer, submitRagFeedback } from "../lib/ragApi";
import type { Citation } from "../lib/ragApi";

type Message = {
  role: "user" | "assistant";
  content: string;
  sources?: Citation[];
  timings?: Record<string, number>;
  question?: string;
  loading?: boolean;
  feedback?: string;
  candidateCount?: number;
  stage?: string;
};

const STORAGE_KEY = "knowledge-rag:conversation";
const SESSION_STORAGE_KEY = "knowledge-rag:session-id";
const starterQuestions = ["员工带薪年休假如何计算？", "请概括采购报销的审批规则", "这份制度中有哪些申请时限？"];

function loadMessages(): Message[] {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]") as Message[]; } catch { return []; }
}

function createSessionId(): string {
  const existing = localStorage.getItem(SESSION_STORAGE_KEY);
  if (existing) return existing;
  const sessionId = typeof crypto.randomUUID === "function"
    ? crypto.randomUUID().replace(/-/g, "")
    : `rag${Date.now()}${Math.random().toString(36).slice(2)}`;
  localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
  return sessionId;
}

function CitationPill({ source, onClick }: { source: Citation; onClick: () => void }) {
  return <button onClick={onClick} className="group flex w-full items-start gap-2 border-b border-kb-border px-4 py-3 text-left last:border-b-0 hover:bg-amber-50 dark:hover:bg-amber-400/10">
    <span className="mt-0.5 shrink-0 rounded-md bg-amber-100 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-amber-800 dark:bg-amber-400/15 dark:text-amber-200">[{source.citation_id}]</span>
    <span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium text-kb-ink">{source.filename}</span><span className="mt-1 block line-clamp-2 text-xs leading-5 text-kb-muted">{source.excerpt}</span></span>
    <span className="shrink-0 text-[11px] text-kb-muted">{source.page != null ? `第 ${source.page} 页` : "片段"}</span>
  </button>;
}

export default function RagPage() {
  const [messages, setMessages] = useState<Message[]>(loadMessages);
  const [sessionId, setSessionId] = useState<string>(createSessionId);
  const [question, setQuestion] = useState("");
  const [selected, setSelected] = useState<Citation | null>(null);
  const [showTrace, setShowTrace] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const history = useMemo(() => messages.slice(-6).map(({ role, content }) => ({ role, content })), [messages]);
  const activeAnswer = [...messages].reverse().find((message) => message.role === "assistant" && (message.sources?.length || message.loading));

  const persist = (next: Message[]) => {
    setMessages(next);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next.filter((message) => !message.loading)));
  };

  const ask = (event: FormEvent) => {
    event.preventDefault();
    const text = question.trim();
    if (!text || abortRef.current) return;
    const user: Message = { role: "user", content: text };
    const assistant: Message = { role: "assistant", content: "", question: text, loading: true, stage: "正在理解问题" };
    setMessages([...messages, user, assistant]);
    setQuestion("");
    abortRef.current = streamRagAnswer({ question: text, session_id: sessionId, history }, (eventData) => {
      setMessages((current) => {
        const updated = [...current];
        const index = updated.length - 1;
        const last = updated[index];
        if (!last || last.role !== "assistant") return current;
        if (eventData.type === "status") {
          updated[index] = { ...last, stage: eventData.message || "正在检索知识库" };
        } else if (eventData.type === "retrieval") {
          const count = eventData.candidate_count ?? eventData.retrieved_count ?? 0;
          updated[index] = { ...last, candidateCount: count, timings: eventData.timings_ms, stage: `已检索 ${count} 条候选，正在核查证据` };
        } else if (eventData.type === "content") {
          updated[index] = { ...last, content: last.content + (eventData.content || ""), stage: "正在生成带引用的回答" };
        } else if (eventData.type === "replace_content") {
          updated[index] = { ...last, content: eventData.content || last.content };
        } else if (eventData.type === "done") {
          const accepted = eventData.sources || [];
          updated[index] = { ...last, loading: false, sources: accepted, candidateCount: eventData.candidate_count ?? last.candidateCount, timings: eventData.timings_ms || last.timings, stage: accepted.length ? `已核查并采纳 ${accepted.length} 条证据` : "未采用不相关来源" };
          abortRef.current = null;
          localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
        } else if (eventData.type === "error") {
          updated[index] = { ...last, loading: false, content: eventData.message || "问答失败", stage: "问答失败" };
          abortRef.current = null;
        }
        return updated;
      });
    }, (error) => {
      abortRef.current = null;
      setMessages((current) => current.map((message, index) => index === current.length - 1
        ? { ...message, loading: false, content: message.content || `请求失败：${error}`, stage: "问答失败" } : message));
    });
  };

  const sendFeedback = async (messageIndex: number, verdict: "useful" | "not_useful") => {
    const message = messages[messageIndex];
    if (!message.question) return;
    try {
      await submitRagFeedback({ question: message.question, answer: message.content, verdict, sources: message.sources || [] });
      setMessages((current) => current.map((item, index) => index === messageIndex ? { ...item, feedback: "反馈已记录" } : item));
    } catch {
      setMessages((current) => current.map((item, index) => index === messageIndex ? { ...item, feedback: "反馈提交失败" } : item));
    }
  };

  return <div className="min-h-full bg-kb-bg text-kb-ink dark:bg-[#0a1628]">
    <header className="border-b border-kb-border bg-kb-card/80 px-5 py-4 backdrop-blur dark:bg-[#0f1f35]/80 sm:px-7">
      <div className="mx-auto flex max-w-[1440px] items-center justify-between gap-4">
        <div><div className="flex items-center gap-2 text-xs font-semibold tracking-[0.14em] text-kb-accent"><Sparkles className="h-3.5 w-3.5" /> EVIDENCE WORKSPACE</div><h1 className="mt-1 font-[var(--font-display)] text-2xl font-semibold tracking-tight">知识库问答</h1></div>
        <button onClick={() => { const nextSessionId = typeof crypto.randomUUID === "function" ? crypto.randomUUID().replace(/-/g, "") : `rag${Date.now()}`; localStorage.setItem(SESSION_STORAGE_KEY, nextSessionId); setSessionId(nextSessionId); persist([]); }} className="inline-flex items-center gap-2 rounded-lg border border-kb-border bg-kb-card px-3 py-2 text-sm font-medium transition hover:border-kb-accent hover:text-kb-accent dark:bg-[#0f1f35]"><MessageSquarePlus className="h-4 w-4" />新建问答</button>
      </div>
    </header>

    <div className="mx-auto grid max-w-[1440px] xl:grid-cols-[minmax(0,1fr)_360px] xl:gap-6 xl:px-7">
      <main className="min-w-0 px-4 py-6 sm:px-7 xl:px-0">
        {messages.length === 0 ? <section className="mx-auto max-w-3xl pt-8 sm:pt-16">
          <div className="border-l-2 border-kb-accent pl-5"><p className="text-sm font-medium text-kb-accent">严格依据你的知识库</p><h2 className="mt-2 max-w-xl font-[var(--font-display)] text-3xl leading-tight sm:text-4xl">每一个结论，都能回到它的原始证据。</h2><p className="mt-4 max-w-xl text-sm leading-6 text-kb-muted">提出问题后，系统会先检索候选，再只展示真正被回答引用的切片。点击引文即可核查原文。</p></div>
          <div className="mt-10 grid gap-3 sm:grid-cols-3">{starterQuestions.map((item) => <button key={item} onClick={() => setQuestion(item)} className="border border-kb-border bg-kb-card p-4 text-left text-sm leading-6 transition hover:-translate-y-0.5 hover:border-kb-accent hover:shadow-sm dark:bg-[#0f1f35]">{item}</button>)}</div>
        </section> : <div className="mx-auto max-w-4xl space-y-8">
          {messages.map((message, index) => <article key={`${message.role}-${index}`} className={message.role === "user" ? "border-l-2 border-kb-ink/25 pl-4" : "border-b border-kb-border pb-8"}>
            {message.role === "user" ? <><p className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-kb-muted">你的问题</p><p className="whitespace-pre-wrap text-lg leading-8">{message.content}</p></> : <>
              <div className="mb-4 flex items-center gap-2"><ShieldCheck className={`h-4 w-4 ${message.sources?.length ? "text-kb-accent" : "text-kb-muted"}`} /><span className="text-sm font-medium">{message.stage || "已完成"}</span>{message.loading && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-kb-highlight" />}</div>
              {message.content ? <div className="prose prose-slate max-w-none text-[15px] leading-7 dark:prose-invert"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: ({ href, children }) => {
                const citationId = href?.replace("#citation-", "");
                const source = message.sources?.find((item) => item.citation_id === citationId);
                return source ? <button onClick={() => setSelected(source)} className="mx-0.5 inline-flex rounded-md bg-amber-100 px-1.5 py-0.5 font-mono text-xs font-semibold text-amber-900 hover:bg-amber-200 dark:bg-amber-400/15 dark:text-amber-200">{children}</button> : <span>{children}</span>;
              } }}>{message.content.replace(/\[(S\d+)\]/g, "[[$1]](#citation-$1)")}</ReactMarkdown></div> : <div className="flex items-center gap-2 py-4 text-sm text-kb-muted"><Search className="h-4 w-4 animate-pulse" />{message.stage || "正在检索"}</div>}
              {!message.loading && message.content && <div className="mt-6 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-kb-border pt-4 text-xs text-kb-muted"><span>此回答有帮助吗？</span><button onClick={() => sendFeedback(index, "useful")} className="inline-flex items-center gap-1 hover:text-kb-accent"><ThumbsUp className="h-3.5 w-3.5" />有帮助</button><button onClick={() => sendFeedback(index, "not_useful")} className="inline-flex items-center gap-1 hover:text-kb-error"><ThumbsDown className="h-3.5 w-3.5" />无帮助</button>{message.feedback && <span className="text-kb-accent">{message.feedback}</span>}</div>}
              {message.timings && <div className="mt-4"><button onClick={() => setShowTrace(!showTrace)} className="flex items-center gap-1 text-xs text-kb-muted hover:text-kb-ink">检索过程 {showTrace ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}</button>{showTrace && <div className="mt-2 flex flex-wrap gap-2">{Object.entries(message.timings).map(([name, value]) => <span key={name} className="rounded border border-kb-border bg-kb-card px-2 py-1 font-mono text-[11px] text-kb-muted dark:bg-[#0f1f35]">{name} {Math.round(value)}ms</span>)}</div>}</div>}
            </>}
          </article>)}
        </div>}
      </main>

      <aside className="hidden border-l border-kb-border bg-kb-card/60 xl:block dark:bg-[#0f1f35]/50"><div className="sticky top-0 p-5"><div className="flex items-center gap-2"><FileText className="h-4 w-4 text-kb-accent" /><h2 className="text-sm font-semibold">证据检查器</h2></div><p className="mt-1 text-xs leading-5 text-kb-muted">仅显示本回答实际采用的来源。</p><div className="mt-4 overflow-hidden border border-kb-border bg-kb-card dark:bg-[#0f1f35]">{activeAnswer?.loading ? <p className="px-4 py-5 text-sm text-kb-muted">{activeAnswer.stage}</p> : activeAnswer?.sources?.length ? activeAnswer.sources.map((source) => <CitationPill key={source.chunk_id} source={source} onClick={() => setSelected(source)} />) : <p className="px-4 py-5 text-sm leading-6 text-kb-muted">回答完成后，已采纳的证据会显示在这里。</p>}</div>{activeAnswer?.candidateCount != null && <p className="mt-3 text-xs text-kb-muted">检索到 {activeAnswer.candidateCount} 条候选，已完成证据核查。</p>}</div></aside>
    </div>

    <form onSubmit={ask} className="sticky bottom-0 border-t border-kb-border bg-kb-bg/95 px-4 py-4 backdrop-blur dark:bg-[#0a1628]/95 sm:px-7"><div className="mx-auto flex max-w-4xl items-end gap-3 border border-kb-border bg-kb-card p-2 shadow-[0_8px_30px_rgba(10,22,40,0.06)] dark:bg-[#0f1f35]"><textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="在知识库中提出一个需要核查的问题…" rows={2} className="min-h-12 flex-1 resize-none bg-transparent px-3 py-2 text-sm outline-none placeholder:text-kb-muted" /><button type="submit" className="grid h-10 w-10 place-items-center bg-kb-accent text-white transition hover:bg-[#126e65] disabled:cursor-not-allowed disabled:opacity-40" disabled={!question.trim() || Boolean(abortRef.current)} aria-label="发送问题"><Send className="h-4 w-4" /></button></div><p className="mx-auto mt-2 max-w-4xl text-xs text-kb-muted">系统只会引用当前知识库中可核查的内容。</p></form>
    <EvidenceDrawer citation={selected} onClose={() => setSelected(null)} />
  </div>;
}
