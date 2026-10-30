"use client";

import { useEffect, useRef, useState } from "react";

import { AiBadge } from "@/components/insights/AiBadge";
import { RichText } from "@/components/RichText";
import { ErrorState, FormErrorLine, LoadingState } from "@/components/States";
import { ApiError, post } from "@/lib/api";
import type { AssistantReply, AssistantStatus } from "@/lib/types";
import { useApi } from "@/lib/use-api";

interface Message {
  from: "you" | "assistant";
  text: string;
  notes?: string[];
  mode?: "basic" | "ai";
}

const messageOf = (err: unknown) => (err instanceof ApiError ? err.message : "Could not reach the server.");

/** "Ask Vezapp Planner": a conversation about the plan. It remembers the chat, so "why?" works. */
export function AskPanel() {
  const status = useApi<AssistantStatus>("/assistant/status");
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversation, setConversation] = useState<string | null>(null);
  const [followUps, setFollowUps] = useState<string[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "nearest" });
  }, [messages, busy, followUps]);

  async function send(text: string, summary = false) {
    const asked = summary ? "Summarise this month" : text.trim();
    if (!asked || busy) return;
    setBusy(true);
    setError(null);
    setFollowUps([]);
    setMessages((m) => [...m, { from: "you", text: asked }]);
    setQuestion("");
    try {
      const reply = summary
        ? await post<AssistantReply>("/assistant/monthly-summary")
        : await post<AssistantReply>("/assistant/ask", { question: asked, conversation });
      if (!summary) setConversation(reply.conversation);
      setMessages((m) => [...m, { from: "assistant", text: reply.answer, notes: reply.notes, mode: reply.mode }]);
      setFollowUps(reply.follow_ups);
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }

  function startOver() {
    setMessages([]);
    setConversation(null);
    setFollowUps([]);
    setError(null);
  }

  if (status.loading) return <LoadingState label="Loading the assistant" rows={2} />;
  if (status.error || !status.data) return <ErrorState message={status.error?.message ?? "Could not load."} onRetry={status.reload} />;
  const info = status.data;
  const chips = messages.length === 0 ? [...info.starters, "Summarise this month"] : followUps;

  return (
    <section aria-label="Ask Vezapp Planner" className="space-y-3">
      <p className={`flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 text-sm ${info.mode === "basic" ? "border-line bg-sunken" : "border-action bg-brand-wash"}`} role="note">
        {info.mode === "basic" ? (
          info.notice
        ) : (
          <>
            <AiBadge label="AI assistant" />
            <span>Chat naturally: I remember what we have talked about, and I only use numbers from your own data.</span>
          </>
        )}
      </p>

      <div className="panel max-h-[32rem] min-h-48 space-y-3 overflow-y-auto px-3 py-3" aria-live="polite" aria-label="Conversation">
        {messages.length === 0 && (
          <p className="text-sm text-ink-soft">
            Hi, I&apos;m your planning assistant. Ask me about late lines, bottlenecks, free machines, a customer or part, today&apos;s plan, or the month. Pick a question below or type your own.
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={
              m.from === "you"
                ? "ml-auto max-w-[85%] rounded-md bg-brand-wash px-3 py-2 text-sm"
                : `max-w-[95%] rounded-md bg-sunken px-3 py-2 text-sm ${m.mode === "ai" ? "border-l-4 border-action" : ""}`
            }
          >
            <p className="mb-1 flex items-center gap-2 text-xs font-medium text-ink-soft">
              {m.from === "you" ? "You" : "Vezapp Planner"}
              {m.from === "assistant" && (m.mode === "ai" ? <AiBadge /> : <span className="rounded-full border border-line px-2 py-0.5">Basic</span>)}
            </p>
            {m.from === "assistant" ? <RichText text={m.text} /> : <p className="whitespace-pre-line">{m.text}</p>}
            {m.notes?.filter((n) => n !== info.notice).map((n) => <p key={n} className="mt-1 text-xs text-ink-soft">{n}</p>)}
          </div>
        ))}
        {busy && <p className="text-sm text-ink-soft" role="status">Thinking it through…</p>}
        <div ref={end} />
      </div>
      {error && <FormErrorLine message={error} />}

      {chips.length > 0 && !busy && (
        <div className="flex flex-wrap gap-2" aria-label={messages.length === 0 ? "Suggested questions" : "You could ask next"}>
          {chips.map((s) => (
            <button key={s} type="button" className="btn btn-quiet !min-h-9" onClick={() => void send(s, s === "Summarise this month" && messages.length === 0)}>
              {s}
            </button>
          ))}
        </div>
      )}

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void send(question);
        }}
      >
        <label className="sr-only" htmlFor="ask-question">Your question</label>
        <input id="ask-question" className="field flex-1" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask anything about the plan, for example: what is planned tomorrow?" maxLength={info.max_question_chars} autoComplete="off" />
        <button type="submit" className="btn btn-primary" disabled={busy || !question.trim()}>Ask</button>
      </form>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-ink-soft">{info.disclaimer}</p>
        {messages.length > 0 && (
          <button type="button" className="btn btn-quiet !min-h-8 text-sm" onClick={startOver} disabled={busy}>
            New chat
          </button>
        )}
      </div>
    </section>
  );
}
