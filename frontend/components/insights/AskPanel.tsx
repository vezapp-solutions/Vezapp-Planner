"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { AiBadge, SparkleIcon } from "@/components/insights/AiBadge";
import { RichText } from "@/components/RichText";
import { ErrorState, FormErrorLine, LoadingState } from "@/components/States";
import { ApiError, post } from "@/lib/api";
import type { AssistantReply, AssistantStatus } from "@/lib/types";
import { useApi } from "@/lib/use-api";

interface Message {
  id: number;
  from: "you" | "assistant";
  text: string;
  notes?: string[];
  mode?: "basic" | "ai";
}

const SUMMARY = "Summarise this month";
const messageOf = (err: unknown) => (err instanceof ApiError ? err.message : "Could not reach the server.");

const icon = { viewBox: "0 0 20 20", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true } as const;

function Avatar({ size = "md" }: { size?: "md" | "lg" }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-full bg-action text-on-action shadow-sm ring-4 ring-brand-wash ${size === "lg" ? "h-14 w-14" : "h-8 w-8"}`}
      aria-hidden="true"
    >
      <SparkleIcon className={size === "lg" ? "h-7 w-7" : "h-4 w-4"} />
    </span>
  );
}

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setDone(true);
      window.setTimeout(() => setDone(false), 1600);
    } catch {
      /* clipboard blocked: nothing to do */
    }
  }
  return (
    <button
      type="button"
      onClick={() => void copy()}
      aria-label={done ? "Copied" : "Copy this answer"}
      className="inline-flex min-h-7 items-center gap-1 rounded-md px-1.5 text-xs text-ink-soft opacity-0 transition duration-150 hover:bg-sunken hover:text-ink focus-visible:opacity-100 group-hover:opacity-100"
    >
      <svg {...icon} className="h-3.5 w-3.5">
        {done ? <path d="M4 10.5l4 4 8-9" /> : <><rect x="7" y="7" width="9" height="9" rx="2" /><path d="M13 7V5.5A1.5 1.5 0 0011.5 4h-6A1.5 1.5 0 004 5.5v6A1.5 1.5 0 005.5 13H7" /></>}
      </svg>
      {done ? "Copied" : "Copy"}
    </button>
  );
}

function Bubble({ message, notice }: { message: Message; notice: string | null }) {
  if (message.from === "you") {
    return (
      <div className="chat-in flex justify-end">
        <p className="max-w-[85%] whitespace-pre-line rounded-2xl rounded-br-md bg-action px-4 py-2.5 text-[0.9375rem] leading-relaxed text-on-action shadow-sm sm:max-w-[75%]">
          {message.text}
        </p>
      </div>
    );
  }
  return (
    <div className="chat-in group flex items-start gap-3">
      <Avatar />
      <div className="min-w-0 max-w-[92%] sm:max-w-[82%]">
        <p className="mb-1 flex items-center gap-2 text-xs font-medium text-ink-soft">
          Vezapp Planner
          {message.mode === "ai" ? <AiBadge /> : <span className="rounded-full border border-line px-2 py-0.5">Basic</span>}
        </p>
        <div className="rounded-2xl rounded-tl-md border border-line bg-surface px-4 py-3 text-[0.9375rem] leading-relaxed shadow-sm">
          <RichText text={message.text} />
          {message.notes?.filter((n) => n !== notice).map((n) => (
            <p key={n} className="mt-2 text-xs text-ink-soft">{n}</p>
          ))}
        </div>
        <div className="mt-1 h-7">
          <CopyButton text={message.text} />
        </div>
      </div>
    </div>
  );
}

function Typing() {
  return (
    <div className="chat-in flex items-start gap-3" role="status">
      <Avatar />
      <div className="inline-flex items-center gap-1.5 rounded-2xl rounded-tl-md border border-line bg-surface px-4 py-3.5 shadow-sm">
        <span className="typing-dot" />
        <span className="typing-dot" style={{ animationDelay: "160ms" }} />
        <span className="typing-dot" style={{ animationDelay: "320ms" }} />
        <span className="sr-only">Thinking it through</span>
      </div>
    </div>
  );
}

/** "Ask Vezapp Planner": a conversation about the plan. It remembers the chat, so "why?" works. */
export function AskPanel() {
  const status = useApi<AssistantStatus>("/assistant/status");
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversation, setConversation] = useState<string | null>(null);
  const [followUps, setFollowUps] = useState<string[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const log = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const nextId = useRef(1);

  useEffect(() => {
    log.current?.scrollTo?.({ top: log.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  const resize = useCallback(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, []);

  useEffect(() => {
    resize();
  }, [question, resize]);

  async function send(text: string, summary = false) {
    const asked = summary ? SUMMARY : text.trim();
    if (!asked || busy) return;
    setBusy(true);
    setError(null);
    setFollowUps([]);
    setMessages((m) => [...m, { id: nextId.current++, from: "you", text: asked }]);
    setQuestion("");
    try {
      const reply = summary
        ? await post<AssistantReply>("/assistant/monthly-summary")
        : await post<AssistantReply>("/assistant/ask", { question: asked, conversation });
      if (!summary) setConversation(reply.conversation);
      setMessages((m) => [...m, { id: nextId.current++, from: "assistant", text: reply.answer, notes: reply.notes, mode: reply.mode }]);
      setFollowUps(reply.follow_ups);
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
      box.current?.focus();
    }
  }

  function startOver() {
    setMessages([]);
    setConversation(null);
    setFollowUps([]);
    setError(null);
    box.current?.focus();
  }

  if (status.loading) return <LoadingState label="Loading the assistant" rows={2} />;
  if (status.error || !status.data) return <ErrorState message={status.error?.message ?? "Could not load."} onRetry={status.reload} />;
  const info = status.data;
  const isAi = info.mode !== "basic";
  const empty = messages.length === 0;
  const starters = [...info.starters, SUMMARY];
  const left = info.max_question_chars - question.length;

  return (
    <section aria-label="Ask Vezapp Planner" className="flex h-[calc(100dvh-17rem)] max-h-[52rem] min-h-[30rem] flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-sm">
      <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <Avatar />
          <div className="min-w-0">
            <p className="flex items-center gap-2 font-semibold leading-tight">
              Vezapp Planner
              {isAi ? <AiBadge label="AI assistant" /> : <span className="rounded-full border border-line px-2 py-0.5 text-xs font-medium text-ink-soft">Basic mode</span>}
            </p>
            <p className="truncate text-xs text-ink-soft">
              {isAi ? "Remembers the chat. Only quotes numbers from your own data." : (info.notice ?? "Answers from your own data.")}
            </p>
          </div>
        </div>
        {!empty && (
          <button type="button" className="btn btn-quiet !min-h-9 !px-3 text-sm" onClick={startOver} disabled={busy}>
            <svg {...icon} className="h-4 w-4"><path d="M10 4v12M4 10h12" /></svg>
            New chat
          </button>
        )}
      </header>

      <div ref={log} role="log" aria-live="polite" aria-label="Conversation" className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-5">
        {empty ? (
          <div className="chat-in mx-auto flex max-w-xl flex-col items-center pt-4 text-center">
            <Avatar size="lg" />
            <h3 className="mt-4 font-display text-2xl font-semibold">How can I help with the plan?</h3>
            <p className="mt-1 text-sm text-ink-soft">
              Ask about late lines, bottlenecks, free machines, a customer or a part, today&apos;s plan, or the month.
            </p>
            <div className="mt-6 grid w-full gap-2 sm:grid-cols-2">
              {starters.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => void send(s, s === SUMMARY)}
                  disabled={busy}
                  className="group flex items-center justify-between gap-3 rounded-xl border border-line bg-surface px-4 py-3 text-left text-sm font-medium transition duration-150 hover:-translate-y-0.5 hover:border-action hover:bg-brand-wash hover:shadow-md"
                >
                  {s}
                  <svg {...icon} className="h-4 w-4 shrink-0 text-ink-soft transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-action"><path d="M4 10h12M11 5l5 5-5 5" /></svg>
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m) => <Bubble key={m.id} message={m} notice={info.notice} />)
        )}
        {busy && <Typing />}
        {error && <FormErrorLine message={error} />}
      </div>

      <div className="border-t border-line bg-surface px-3 pb-3 pt-2 sm:px-4">
        {!empty && followUps.length > 0 && !busy && (
          <div className="no-scrollbar -mx-1 mb-2 flex gap-2 overflow-x-auto px-1 pb-1" aria-label="You could ask next">
            {followUps.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => void send(s)}
                className="shrink-0 rounded-full border border-line bg-surface px-3.5 py-1.5 text-sm transition duration-150 hover:border-action hover:bg-brand-wash"
              >
                {s}
              </button>
            ))}
          </div>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void send(question);
          }}
          className="flex items-end gap-2 rounded-2xl border border-[color-mix(in_srgb,var(--ink)_38%,var(--ground))] bg-surface p-1.5 pl-4 transition-[border-color,box-shadow] duration-150 focus-within:border-action focus-within:shadow-[0_0_0_3px_color-mix(in_srgb,var(--action)_24%,transparent)]"
        >
          <label className="sr-only" htmlFor="ask-question">Your question</label>
          <textarea
            id="ask-question"
            ref={box}
            rows={1}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                void send(question);
              }
            }}
            placeholder="Ask anything about the plan…"
            maxLength={info.max_question_chars}
            className="max-h-40 min-h-9 flex-1 resize-none self-center bg-transparent py-1.5 text-[0.9375rem] leading-6 outline-none placeholder:text-ink-soft"
          />
          <button
            type="submit"
            aria-label="Send"
            disabled={busy || !question.trim()}
            className="btn btn-primary !min-h-10 !w-10 !rounded-xl !p-0"
          >
            <svg {...icon} strokeWidth={2.2} className="h-5 w-5"><path d="M10 16V4M5 9l5-5 5 5" /></svg>
          </button>
        </form>
        <p className="mt-1.5 flex flex-wrap items-center justify-between gap-x-3 px-1 text-xs text-ink-soft">
          <span>Enter to send, Shift+Enter for a new line. {info.disclaimer}</span>
          {left < 80 && <span aria-live="polite">{left} characters left</span>}
        </p>
      </div>
    </section>
  );
}
