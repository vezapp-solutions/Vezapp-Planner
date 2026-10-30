"use client";

import Link from "next/link";

import { EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/States";
import type { DataHealth, HealthItem } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const KIND_TITLE: Record<string, string> = {
  no_route: "Parts without a route",
  route_gap: "Route steps missing a time or a resource",
  no_capacity: "Operations with no capacity modelled",
  past_due: "Past internal dates with no actual dispatch",
  unrealistic: "Unrealistic values",
};

const SEVERITY: Record<HealthItem["severity"], { label: string; style: string }> = {
  error: { label: "Fix", style: "bg-danger-wash text-danger" },
  warning: { label: "Check", style: "bg-warn-wash text-warn" },
  info: { label: "Note", style: "bg-sunken text-ink-soft" },
};

/** The items by kind, keeping the order the server ranked them in. */
function groupByKind(items: HealthItem[]): [string, HealthItem[]][] {
  const groups = new Map<string, HealthItem[]>();
  for (const item of items) groups.set(item.kind, [...(groups.get(item.kind) ?? []), item]);
  return [...groups.entries()];
}

export default function DataHealthPage() {
  const health = useApi<DataHealth>("/data-health");

  return (
    <>
      <PageHeader title="Data health" subtitle="Gaps in the masters and schedule that make a plan wrong or unfinished" />
      {health.loading ? (
        <LoadingState label="Checking the data" rows={4} />
      ) : health.error || !health.data ? (
        <ErrorState message={health.error?.message ?? "Could not load."} onRetry={health.reload} />
      ) : health.data.items.length === 0 ? (
        <EmptyState title="Nothing to fix">Every active part has a route with times and resources, and no line is past its date without an actual dispatch.</EmptyState>
      ) : (
        <div className="space-y-6">
          <p className="text-sm text-ink-soft" aria-live="polite">{health.data.count} item{health.data.count === 1 ? "" : "s"} to look at, biggest effect first. Each says why it matters.</p>
          {groupByKind(health.data.items).map(([kind, items]) => (
            <section key={kind} aria-label={KIND_TITLE[kind] ?? kind}>
              <h2 className="mb-2 font-display text-lg font-semibold">
                {KIND_TITLE[kind] ?? kind} <span className="font-mono text-sm font-normal text-ink-soft">({items?.length})</span>
              </h2>
              <ul className="panel divide-y divide-line">
                {items?.map((i) => (
                  <li key={`${i.subject}|${i.detail}`} className="px-4 py-3 text-sm">
                    <p className="flex flex-wrap items-center gap-2">
                      <span className={`rounded-sm px-1.5 py-0.5 text-xs font-medium ${SEVERITY[i.severity].style}`}>{SEVERITY[i.severity].label}</span>
                      <span className="font-medium">{i.subject}</span>
                      {i.lines_affected > 0 && <span className="text-xs text-ink-soft">touches {i.lines_affected} schedule line{i.lines_affected === 1 ? "" : "s"}</span>}
                      {i.link && <Link href={i.link} className="ml-auto inline-flex min-h-6 items-center text-link underline-offset-2 hover:underline">Open to fix →</Link>}
                    </p>
                    <p className="mt-1">{i.detail}</p>
                    <p className="mt-0.5 text-ink-soft">{i.why}</p>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </>
  );
}
