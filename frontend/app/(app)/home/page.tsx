"use client";

import Link from "next/link";

import { SeverityBadge } from "@/components/insights/InsightCard";
import { Panel } from "@/components/Panel";
import { EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/States";
import { Slack, StatusBadge } from "@/components/plan/StatusBadge";
import { addDays, formatDate, formatDayMonth, formatNumber, formatWeekday, todayInIndia } from "@/lib/format";
import { HEAT_STYLE, heatLevel, percent } from "@/lib/plan-utils";
import { useSession } from "@/lib/store";
import { ROLE_LABEL, type BottleneckDay, type DayView, type InsightList, type Page, type Plan, type PlanLine, type Plant } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const UNIT: Record<string, string> = { core: "cores", moulding: "moulds", melting: "moulds" };

function Workspace() {
  const user = useSession((s) => s.user!);
  const plants = useApi<Page<Plant>>("/plants");

  return (
    <Panel title="Your workspace">
      <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-ink-soft">Company</dt>
          <dd className="font-medium">{user.company?.name ?? "All companies (Vezapp)"}</dd>
        </div>
        <div>
          <dt className="text-ink-soft">Signed in as</dt>
          <dd className="font-medium">
            {user.full_name} · {ROLE_LABEL[user.role]}
          </dd>
        </div>
        <div>
          <dt className="text-ink-soft">Plants</dt>
          <dd>
            {plants.loading && <LoadingState rows={1} label="Loading plants" />}
            {plants.error && <ErrorState message={plants.error.message} onRetry={plants.reload} />}
            {plants.data &&
              (plants.data.results.length ? (
                <span className="font-medium">{plants.data.results.map((p) => p.name).join(", ")}</span>
              ) : user.company ? (
                <span className="text-ink-soft">None added yet</span>
              ) : (
                <span className="text-ink-soft">Choose a company to see plants</span>
              ))}
          </dd>
        </div>
      </dl>
    </Panel>
  );
}

/** The busiest resource of each of the next 14 working days. */
function BottleneckStrip({ plan }: { plan: Plan }) {
  const strip = useApi<BottleneckDay[]>(`/plans/${plan.id}/bottlenecks?days=14&v=${encodeURIComponent(plan.calculated_at ?? "")}`);
  if (strip.loading) return <LoadingState rows={2} label="Loading the forecast" />;
  if (strip.error || !strip.data) return <ErrorState message={strip.error?.message ?? "Could not load."} onRetry={strip.reload} />;
  if (strip.data.length === 0) return <p className="text-sm text-ink-soft">No working days in the plan window.</p>;
  return (
    <>
      <ol className="grid grid-cols-4 gap-px overflow-hidden rounded-sm border border-line bg-line sm:grid-cols-7 xl:grid-cols-14">
        {strip.data.map((d) => (
          <li key={d.date} className="bg-surface px-1 py-2 text-center" style={d.resource_code ? undefined : { color: "var(--ink-soft)" }}>
            <p className="text-[0.6875rem] uppercase text-ink-soft">{formatWeekday(d.date, "short")}</p>
            <p className="whitespace-nowrap font-mono text-xs">{formatDayMonth(d.date)}</p>
            <p className="mt-1 truncate font-mono text-xs font-medium" title={d.resource_code ? `${d.resource_code}: ${percent(d.utilisation)} loaded` : "Nothing planned"}>
              {d.resource_code ?? "–"}
            </p>
            {d.resource_code && (
              <p className="mx-1 rounded-sm font-mono text-[0.6875rem]" style={HEAT_STYLE[heatLevel(d.utilisation)]}>
                {percent(d.utilisation)}
              </p>
            )}
          </li>
        ))}
      </ol>
      <p className="mt-3 text-sm text-ink-soft">The most heavily loaded resource each day, with how full it is.</p>
    </>
  );
}

function DayPanel({ plan, day, title }: { plan: Plan; day: string; title: string }) {
  const view = useApi<DayView>(`/plans/${plan.id}/day?date=${day}&v=${encodeURIComponent(plan.calculated_at ?? "")}`);
  return (
    <Panel title={title} note={`${formatWeekday(day, "short")} ${formatDate(day)}`}>
      {view.loading ? (
        <LoadingState label="Loading the day" rows={2} />
      ) : view.error || !view.data ? (
        <ErrorState message={view.error?.message ?? "Could not load."} onRetry={view.reload} />
      ) : view.data.work.length === 0 ? (
        <EmptyState title="Nothing planned">No work is scheduled for this day (it may be a weekly off or a holiday).</EmptyState>
      ) : (
        <div className="space-y-4">
          <ul className="divide-y divide-line text-sm">
            {view.data.work.map((w) => (
              <li key={w.op_code} className="flex items-baseline justify-between gap-3 py-1.5">
                <span className="font-medium">{w.name}</span>
                <span className="text-right text-ink-soft">
                  {w.lines} line{w.lines > 1 ? "s" : ""} · <span className="font-mono text-ink">{formatNumber(w.qty)}</span> {UNIT[w.op_code] ?? "pcs"}
                </span>
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap gap-1.5" aria-label="Load per resource">
            {view.data.resources.filter((r) => r.load > 0).map((r) => (
              <span key={r.id} className="rounded-sm px-2 py-0.5 font-mono text-xs" style={HEAT_STYLE[heatLevel(r.utilisation)]} title={`${formatNumber(r.load)} of ${formatNumber(r.capacity)} minutes`}>
                {r.code} {percent(r.utilisation)}
              </span>
            ))}
          </div>
        </div>
      )}
    </Panel>
  );
}

function AtRisk({ plan }: { plan: Plan }) {
  const risky = useApi<Page<PlanLine>>(`/plans/${plan.id}/lines?status=at_risk&page_size=5&v=${encodeURIComponent(plan.calculated_at ?? "")}`);
  return (
    <Panel title="Dispatch lines at risk" note={plan.summary.by_status?.at_risk ? `${plan.summary.by_status.at_risk} in total` : undefined}>
      {risky.loading ? (
        <LoadingState label="Loading lines" rows={2} />
      ) : risky.error || !risky.data ? (
        <ErrorState message={risky.error?.message ?? "Could not load."} onRetry={risky.reload} />
      ) : risky.data.results.length === 0 ? (
        <EmptyState title="No line is at risk">Every planned line is expected to ship on or before its internal date.</EmptyState>
      ) : (
        <ul className="divide-y divide-line text-sm">
          {risky.data.results.map((l) => (
            <li key={l.id} className="py-2">
              <div className="flex flex-wrap items-baseline gap-x-3">
                <StatusBadge status={l.status} />
                <span className="font-medium">{l.part_number}</span>
                <span className="text-ink-soft">{l.customer_code}</span>
                <span className="ml-auto font-mono">
                  due {formatDate(l.internal_date)} · est. {l.est_dispatch_date ? formatDate(l.est_dispatch_date) : "–"} · <Slack days={l.slack_working_days} />
                </span>
              </div>
              {l.holding_text && <p className="mt-0.5 text-xs text-ink-soft">{l.holding_text}</p>}
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-sm">
        <Link href="/plan" className="inline-flex min-h-6 items-center text-link underline-offset-2 hover:underline">Open the plan →</Link>
      </p>
    </Panel>
  );
}

function PlanSection() {
  const latest = useApi<Plan | undefined>("/plans/latest");
  const today = todayInIndia();

  if (latest.loading) return <LoadingState label="Loading the plan" rows={3} />;
  if (latest.error) return <ErrorState message={latest.error.message} onRetry={latest.reload} />;
  const plan = latest.data;
  if (!plan) {
    return (
      <Panel title="Plan">
        <EmptyState title="No plan calculated yet">
          Once masters and the monthly schedule are in, open the Plan screen and calculate. Today&apos;s plan, the bottleneck forecast and lines at risk then appear here.{" "}
          <Link href="/plan" className="text-link underline-offset-2 hover:underline">Open the plan</Link>
        </EmptyState>
      </Panel>
    );
  }
  return (
    <div className="space-y-6">
      {plan.stale && plan.status === "draft" && (
        <p role="status" className="rounded-md border border-warn bg-warn-wash px-4 py-2 text-sm">
          <strong className="text-warn">This plan is out of date.</strong> {plan.stale_reasons.join(" ")}{" "}
          <Link href="/plan" className="font-medium text-link underline-offset-2 hover:underline">Recalculate it</Link>
        </p>
      )}
      <Panel title="Bottleneck, next 14 working days" note={`plan v${plan.version}`}>
        <BottleneckStrip plan={plan} />
      </Panel>
      <div className="grid gap-6 md:grid-cols-2">
        <DayPanel plan={plan} day={today} title="Today's plan" />
        <DayPanel plan={plan} day={addDays(today, 1)} title="Tomorrow's plan" />
      </div>
      <AtRisk plan={plan} />
    </div>
  );
}

/** The five most important insight cards. */
function TopInsights() {
  const list = useApi<InsightList>("/insights");
  const top = list.data?.results.slice(0, 5) ?? [];
  return (
    <Panel title="Top insights" note={list.data?.run?.plan_version ? `plan v${list.data.run.plan_version}` : undefined}>
      {list.loading ? (
        <LoadingState label="Loading insights" rows={3} />
      ) : list.error ? (
        <ErrorState message={list.error.message} onRetry={list.reload} />
      ) : top.length === 0 ? (
        <EmptyState title="No insights yet">Insight cards are produced every time a plan is calculated.</EmptyState>
      ) : (
        <ol className="divide-y divide-line text-sm">
          {top.map((c) => (
            <li key={c.key} className="py-2">
              <p className="flex flex-wrap items-center gap-2">
                <SeverityBadge severity={c.severity} />
                <span className="font-medium">{c.title}</span>
              </p>
              <p className="mt-0.5 text-ink-soft">{c.message}</p>
            </li>
          ))}
        </ol>
      )}
      <p className="mt-3 text-sm">
        <Link href="/insights" className="inline-flex min-h-6 items-center text-link underline-offset-2 hover:underline">All insights, the daily digest and the assistant →</Link>
      </p>
    </Panel>
  );
}

export default function HomePage() {
  const today = todayInIndia();
  return (
    <>
      <PageHeader title="Home" subtitle={`${formatWeekday(today)}, ${formatDate(today)}`} />
      <div className="space-y-6">
        <Workspace />
        <PlanSection />
        <TopInsights />
      </div>
    </>
  );
}
