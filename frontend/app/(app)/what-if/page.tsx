"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { EmptyState, ErrorState, FormErrorLine, LoadingState, PageHeader } from "@/components/States";
import { ApiError, fieldErrors, post } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { Page, Scenario, ScenarioDetail } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { headline, STATE_TEXT } from "@/lib/whatif";

function StatusChip({ scenario }: { scenario: Scenario }) {
  if (scenario.status === "applied") return <span className="rounded-sm bg-ok-wash px-1.5 py-0.5 text-xs font-medium text-ok">Applied</span>;
  const stale = scenario.state === "changes_edited" || scenario.state === "data_changed";
  if (stale) return <span className="rounded-sm bg-warn-wash px-1.5 py-0.5 text-xs font-medium text-warn">Out of date</span>;
  if (scenario.state === "never_run") return <span className="rounded-sm bg-sunken px-1.5 py-0.5 text-xs font-medium text-ink-soft">Not run</span>;
  return <span className="rounded-sm bg-brand-wash px-1.5 py-0.5 text-xs font-medium">Ready to apply</span>;
}

function NewScenario() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function create() {
    setBusy(true);
    setError(null);
    try {
      const made = await post<ScenarioDetail>("/scenarios", { name });
      router.push(`/what-if/${made.id}`);
    } catch (err) {
      setError(fieldErrors(err).name ?? (err instanceof ApiError ? err.message : "Could not reach the server."));
      setBusy(false);
    }
  }

  return (
    <form
      className="panel mb-5 flex flex-wrap items-end gap-3 px-4 py-3"
      onSubmit={(e) => {
        e.preventDefault();
        void create();
      }}
    >
      <label className="min-w-[14rem] flex-1 text-sm font-medium">
        New scenario
        <input className="field mt-1" value={name} onChange={(e) => setName(e.target.value)} placeholder="F1 down on Thursday" maxLength={120} />
      </label>
      <button type="submit" className="btn btn-primary" disabled={busy || !name.trim()}>
        {busy ? "Creating…" : "Create scenario"}
      </button>
      {error && <div className="w-full"><FormErrorLine message={error} /></div>}
    </form>
  );
}

export default function WhatIfPage() {
  const list = useApi<Page<Scenario>>("/scenarios?page_size=200");

  return (
    <>
      <PageHeader title="What-if" subtitle="Try a change on a copy of the plan and see which lines move before anything real changes" />
      <NewScenario />
      {list.loading ? (
        <LoadingState label="Loading scenarios" rows={4} />
      ) : list.error ? (
        <ErrorState message={list.error.message} onRetry={list.reload} />
      ) : list.data?.results.length === 0 ? (
        <EmptyState title="No scenarios yet">
          Start one above, then add changes such as blocking a furnace for a day, changing a quantity or date, or adding a shift or overtime. Nothing is changed until you apply it.
        </EmptyState>
      ) : (
        <div className="panel overflow-x-auto">
          <table className="w-full min-w-[40rem] text-left text-sm">
            <thead className="border-b border-line bg-sunken text-ink-soft">
              <tr>
                {["Scenario", "State", "Changes", "Result", "Last run"].map((h, i) => (
                  <th key={h} scope="col" className={`px-4 py-2 font-medium ${i === 2 ? "text-right" : ""}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {list.data?.results.map((s) => (
                <tr key={s.id} className="border-b border-line last:border-0 hover:bg-sunken/60">
                  <td className="px-4 py-2">
                    <Link href={`/what-if/${s.id}`} className="inline-flex min-h-6 items-center font-medium underline-offset-2 hover:underline">{s.name}</Link>
                    {s.created_by_name && <span className="block text-xs text-ink-soft">by {s.created_by_name}</span>}
                  </td>
                  <td className="px-4 py-2">
                    <StatusChip scenario={s} />
                    {s.status === "draft" && STATE_TEXT[s.state] && s.state !== "never_run" && <span className="sr-only"> {STATE_TEXT[s.state]}</span>}
                  </td>
                  <td className="px-4 py-2 text-right font-mono">{s.change_count}</td>
                  <td className="px-4 py-2 text-ink-soft">{s.headline ? headline(s.headline) : "–"}</td>
                  <td className="whitespace-nowrap px-4 py-2 font-mono text-xs">{s.last_run_at ? formatDateTime(s.last_run_at) : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
