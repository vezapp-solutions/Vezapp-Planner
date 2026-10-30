"use client";

import { useState } from "react";

import { SeverityBadge } from "@/components/insights/InsightCard";
import { EmptyState, ErrorState, FormErrorLine, LoadingState } from "@/components/States";
import { ApiError, download } from "@/lib/api";
import type { Digest } from "@/lib/types";
import { useApi } from "@/lib/use-api";

/** The top five cards as a short summary to read, print, save as PDF or paste into an email. */
export function DigestTab({ version }: { version: string }) {
  const digest = useApi<Digest>(`/insights/digest?v=${encodeURIComponent(version)}`);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setNote("Copied. Paste it into an email or a message.");
    } catch {
      setNote("Could not copy automatically. Select the text and copy it.");
    }
  }

  async function pdf() {
    setError(null);
    try {
      await download("/insights/digest?output=pdf", "daily-digest.pdf");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not download.");
    }
  }

  if (digest.loading) return <LoadingState label="Loading the digest" rows={3} />;
  if (digest.error || !digest.data) return <ErrorState message={digest.error?.message ?? "Could not load."} onRetry={digest.reload} />;
  const d = digest.data;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 print:hidden">
        <button type="button" className="btn btn-primary" onClick={() => window.print()}>Print</button>
        <button type="button" className="btn btn-quiet" onClick={pdf}>Download PDF</button>
        <button type="button" className="btn btn-quiet" onClick={() => void copy(d.text)}>Copy as text</button>
      </div>
      {note && <p role="status" className="text-sm text-ink-soft print:hidden">{note}</p>}
      {error && <FormErrorLine message={error} />}

      <section aria-label="Daily digest" className="panel px-4 py-4">
        <h2 className="font-display text-xl font-semibold">{d.title}</h2>
        {d.items.length === 0 ? (
          <div className="mt-3"><EmptyState title="Nothing needs attention today">Refresh the insights after calculating a plan.</EmptyState></div>
        ) : (
          <ol className="mt-3 space-y-4">
            {d.items.map((i, n) => (
              <li key={i.key} className="text-sm">
                <p className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-ink-soft">{n + 1}.</span>
                  <SeverityBadge severity={i.severity} />
                  <span className="font-medium">{i.title}</span>
                </p>
                <p className="mt-0.5">{i.message}</p>
                <p className="mt-0.5 text-ink-soft"><span className="font-medium text-ink">Next: </span>{i.action}</p>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
