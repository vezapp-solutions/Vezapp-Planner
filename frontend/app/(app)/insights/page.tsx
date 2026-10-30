"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { AskPanel } from "@/components/insights/AskPanel";
import { DigestTab } from "@/components/insights/DigestTab";
import { InsightCard } from "@/components/insights/InsightCard";
import { EmptyState, ErrorState, FormErrorLine, LoadingState, PageHeader } from "@/components/States";
import { Tabs } from "@/components/Tabs";
import { ApiError, post } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { bySeverity, filterCards, SEVERITY_LABEL, SEVERITY_ORDER, summaryText, triggerText, TYPE_LABEL, typesPresent } from "@/lib/insights";
import { useSession } from "@/lib/store";
import type { InsightList } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const TABS = [
  { id: "cards", label: "Insights" },
  { id: "digest", label: "Daily digest" },
  { id: "ask", label: "Ask Vezapp Planner" },
];

/** `/insights?tab=ask` (the AI button in the top bar) opens the assistant straight away. */
export default function InsightsPage() {
  return (
    <Suspense>
      <InsightsEntry />
    </Suspense>
  );
}

function InsightsEntry() {
  const wanted = useSearchParams().get("tab");
  const initial = TABS.some((t) => t.id === wanted) ? (wanted as string) : "cards";
  // Keyed, so pressing the AI button again while on this page switches back to the assistant.
  return <InsightsView key={initial} initialTab={initial} />;
}

function InsightsView({ initialTab }: { initialTab: string }) {
  const role = useSession((s) => s.user!.role);
  const canRefresh = role !== "viewer";
  const [tab, setTab] = useState(initialTab);
  const [version, setVersion] = useState(0);
  const [type, setType] = useState("");
  const [severity, setSeverity] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const list = useApi<InsightList>(`/insights?v=${version}`);

  async function refresh() {
    setBusy(true);
    setError(null);
    try {
      await post("/insights/refresh");
      setVersion((v) => v + 1);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }

  const run = list.data?.run ?? null;
  const cards = list.data?.results ?? [];
  const shown = filterCards(cards, type, severity);

  return (
    <>
      <PageHeader title="Insights" subtitle="What needs attention, ranked, with the numbers behind it">
        {canRefresh && (
          <button type="button" className="btn btn-primary" onClick={refresh} disabled={busy}>
            {busy ? "Refreshing…" : "Refresh insights"}
          </button>
        )}
      </PageHeader>
      {error && <div className="mb-4"><FormErrorLine message={error} /></div>}

      <Tabs tabs={TABS} active={tab} onChange={setTab}>
        {tab === "cards" && (
          <>
            {list.loading ? (
              <LoadingState label="Loading insights" rows={4} />
            ) : list.error ? (
              <ErrorState message={list.error.message} onRetry={list.reload} />
            ) : !run ? (
              <EmptyState title="No insights yet">
                Insights are produced every time a plan is calculated. Calculate a plan on the Plan screen
                {canRefresh ? ", or press Refresh insights to check the schedule and data health now." : "."}
              </EmptyState>
            ) : (
              <div className="space-y-4">
                <p className="text-sm text-ink-soft" aria-live="polite">
                  <span className="font-medium text-ink">{summaryText(bySeverity(cards))}.</span>{" "}
                  {run.plan_version ? `Plan v${run.plan_version}, ` : "No plan yet, "}
                  {triggerText(run.trigger)} on {formatDateTime(run.created_at)}.
                  {run.counts.resolved ? ` ${run.counts.resolved} earlier card${run.counts.resolved === 1 ? " is" : "s are"} gone.` : ""}
                </p>

                <div className="flex flex-wrap items-end gap-3">
                  <label className="text-sm">
                    <span className="mb-1 block text-ink-soft">Severity</span>
                    <select className="field !min-h-10 !w-40" value={severity} onChange={(e) => setSeverity(e.target.value)}>
                      <option value="">All</option>
                      {SEVERITY_ORDER.map((s) => <option key={s} value={s}>{SEVERITY_LABEL[s]}</option>)}
                    </select>
                  </label>
                  <label className="text-sm">
                    <span className="mb-1 block text-ink-soft">Kind</span>
                    <select className="field !min-h-10 !w-56" value={type} onChange={(e) => setType(e.target.value)}>
                      <option value="">All kinds</option>
                      {typesPresent(cards).map((t) => <option key={t} value={t}>{TYPE_LABEL[t]}</option>)}
                    </select>
                  </label>
                </div>

                {shown.length === 0 ? (
                  <EmptyState title="No insight matches">Clear a filter to see more.</EmptyState>
                ) : (
                  <ol className="space-y-3">
                    {shown.map((c) => <li key={c.key}><InsightCard card={c} canTest={canRefresh} /></li>)}
                  </ol>
                )}
              </div>
            )}
          </>
        )}
        {tab === "digest" && <DigestTab version={run ? String(run.id) : "none"} />}
        {tab === "ask" && <AskPanel />}
      </Tabs>
    </>
  );
}
