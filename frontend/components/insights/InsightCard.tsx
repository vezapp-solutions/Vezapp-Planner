"use client";

import { useState } from "react";

import { AiBadge } from "@/components/insights/AiBadge";
import { RichText } from "@/components/RichText";
import { FormErrorLine } from "@/components/States";
import { ResultPanel } from "@/components/whatif/ResultPanel";
import { ApiError, post } from "@/lib/api";
import { SEVERITY_LABEL, TREND_LABEL, TREND_MARK, TYPE_LABEL } from "@/lib/insights";
import type { AssistantReply, Insight, ScenarioResult, Severity } from "@/lib/types";

const SEVERITY_STYLE: Record<Severity, string> = {
  critical: "bg-danger-wash text-danger",
  warning: "bg-warn-wash text-warn",
  info: "bg-sunken text-ink-soft",
};

const BORDER: Record<Severity, string> = { critical: "border-l-danger", warning: "border-l-warn", info: "border-l-line" };

const messageOf = (err: unknown) => (err instanceof ApiError ? err.message : "Could not reach the server.");

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <span className={`whitespace-nowrap rounded-sm px-1.5 py-0.5 text-xs font-medium ${SEVERITY_STYLE[severity]}`}>{SEVERITY_LABEL[severity]}</span>;
}

/** One ranked card: the line in plain English, the next step, and on request the trace, an explanation or a test. */
export function InsightCard({ card, canTest }: { card: Insight; canTest: boolean }) {
  const [why, setWhy] = useState(false);
  const [explained, setExplained] = useState<AssistantReply | null>(null);
  const [tested, setTested] = useState<ScenarioResult | null>(null);
  const [busy, setBusy] = useState<"explain" | "test" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const testable = card.type === "load_balancing" && Boolean(card.entities.dry_run);

  async function explain() {
    setBusy("explain");
    setError(null);
    try {
      setExplained(await post<AssistantReply>("/assistant/explain", { key: card.key }));
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(null);
    }
  }

  async function test() {
    setBusy("test");
    setError(null);
    try {
      setTested(await post<ScenarioResult>(`/insights/${card.id}/dry-run`));
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <article className={`panel border-l-4 px-4 py-3 ${BORDER[card.severity]}`} aria-label={card.title}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <SeverityBadge severity={card.severity} />
        <span className="text-xs text-ink-soft">{TYPE_LABEL[card.type]}</span>
        <span className="ml-auto text-xs text-ink-soft" title={TREND_LABEL[card.trend]}>
          <span aria-hidden="true">{TREND_MARK[card.trend]} </span>
          {TREND_LABEL[card.trend]}
        </span>
      </div>
      <h2 className="mt-1 font-display text-lg font-semibold leading-snug">{card.title}</h2>
      <p className="mt-1 text-sm">{card.message}</p>
      {card.action && (
        <p className="mt-2 text-sm">
          <span className="font-medium">Next step: </span>
          {card.action}
        </p>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className="btn btn-quiet !min-h-9" onClick={() => setWhy((v) => !v)} aria-expanded={why}>
          {why ? "Hide why" : "Why"}
        </button>
        <button type="button" className="btn btn-quiet !min-h-9" onClick={explain} disabled={busy !== null}>
          {busy === "explain" ? "Explaining…" : "Explain this"}
        </button>
        {testable && canTest && (
          <button type="button" className="btn btn-quiet !min-h-9" onClick={test} disabled={busy !== null}>
            {busy === "test" ? "Testing…" : "Test it"}
          </button>
        )}
      </div>

      {why && (
        <ul className="mt-3 list-disc space-y-1 rounded-md bg-sunken px-6 py-3 text-sm" aria-label="How this was worked out">
          {card.why.map((w) => <li key={w}>{w}</li>)}
        </ul>
      )}
      {error && <div className="mt-3"><FormErrorLine message={error} /></div>}
      {explained && (
        <div className={`mt-3 space-y-1 rounded-md border border-line px-3 py-2 text-sm ${explained.mode === "ai" ? "border-l-4 border-l-action" : ""}`} role="status">
          {explained.mode === "ai" && <AiBadge />}
          <RichText text={explained.answer} />
          {explained.notes.map((n) => <p key={n} className="text-xs text-ink-soft">{n}</p>)}
          <p className="text-xs text-ink-soft">{explained.disclaimer}</p>
        </div>
      )}
      {tested && (
        <div className="mt-3 space-y-2 rounded-md border border-line px-3 py-3">
          <p className="text-sm font-medium">Result of the test. Nothing was changed.</p>
          <ResultPanel result={tested} ranAt={null} stale={false} />
        </div>
      )}
    </article>
  );
}
