"use client";

import Link from "next/link";

import { SeverityBadge } from "@/components/insights/InsightCard";
import { Panel } from "@/components/Panel";
import { Stat, StatRow } from "@/components/Stat";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { CapacityStrip } from "@/components/plan/CapacityStrip";
import { addDays, countLabel, formatDate, formatNumber, formatWeekday, todayInIndia } from "@/lib/format";
import { homeInsights } from "@/lib/insights";
import { HEAT_STYLE, heatLevel, holdingSummary, percent, slackLabel, slackWords } from "@/lib/plan-utils";
import { useSession } from "@/lib/store";
import { ROLE_LABEL, type BottleneckDay, type DayView, type InsightList, type Page, type Plan, type PlanLine, type Plant } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const UNIT: Record<string, string> = { core: "cores", moulding: "moulds", melting: "moulds" };

/** The page header: a greeting and where you are working on the left, the two things you do most on the right. */
function Hero() {
  const user = useSession((s) => s.user!);
  const plants = useApi<Page<Plant>>("/plants");
  const hour = Number(new Intl.DateTimeFormat("en-IN", { hour: "numeric", hour12: false, timeZone: "Asia/Kolkata" }).format(new Date())) % 24;
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const today = todayInIndia();
  const first = user.full_name.split(" ")[0];
  const plantNames = plants.data?.results.map((p) => p.name).join(", ");

  return (
    <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
      <div className="min-w-0">
        <h1 className="font-display text-[1.75rem] font-bold leading-tight tracking-tight sm:text-[2rem]">
          {greeting}, {first}.
        </h1>
        <p className="mt-1 max-w-3xl text-sm text-ink-soft">
          <span className="font-mono text-xs">{formatWeekday(today, "short")} {formatDate(today)}</span>
          {" · "}
          {user.company?.name ?? "All companies (Vezapp)"}
          {plants.loading ? "" : plantNames ? ` · ${plantNames}` : user.company ? " · no plants added yet" : " · choose a company to see its plants"}
          {" · "}
          {ROLE_LABEL[user.role]}
        </p>
        {plants.error && <p className="mt-1 text-sm text-danger">Could not load plants. {plants.error.message}</p>}
      </div>
      <div className="flex flex-wrap gap-2">
        <Link href="/plan" className="btn btn-primary">Open the plan</Link>
        <Link href="/scheduler/upload" className="btn btn-quiet">Upload orders</Link>
      </div>
    </header>
  );
}

/** The busiest resource of each of the next 14 working days, as a row of bars. */
function BottleneckStrip({ plan }: { plan: Plan }) {
  const strip = useApi<BottleneckDay[]>(`/plans/${plan.id}/bottlenecks?days=14&v=${encodeURIComponent(plan.calculated_at ?? "")}`);
  if (strip.loading) return <LoadingState rows={2} label="Loading the forecast" />;
  if (strip.error || !strip.data) return <ErrorState message={strip.error?.message ?? "Could not load."} onRetry={strip.reload} />;
  if (strip.data.length === 0) return <p className="text-sm text-ink-soft">No working days in the plan window.</p>;
  return <CapacityStrip days={strip.data} />;
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
                  {countLabel(w.lines, "line")} · <span className="font-mono text-ink">{formatNumber(w.qty)}</span> {UNIT[w.op_code] ?? "pcs"}
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

/** The pill beside a late order: working days late (-) or spare (+) against the internal due date. */
function VariancePill({ days }: { days: number | null }) {
  if (days == null) return <span className="text-ink-soft">–</span>;
  const tone = days < 0 ? "bg-danger-wash text-danger" : days < 2 ? "bg-warn-wash text-warn" : "bg-ok-wash text-ok";
  return (
    <span className={`badge font-mono ${tone}`} title={slackWords(days)} aria-label={slackWords(days)}>
      {slackLabel(days)}
    </span>
  );
}

/** Order-level triage: which orders will miss their date, by how much, and what holds each one up. */
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
        <div className="-mx-2 overflow-x-auto">
          <table className="w-full min-w-[40rem] text-left text-sm">
            <thead>
              <tr className="text-ink-soft">
                <th scope="col" className="rounded-l-chip px-2 py-2 font-medium">Part and customer</th>
                <th scope="col" className="px-2 py-2 font-medium">Internal due and estimated</th>
                <th scope="col" className="px-2 py-2 font-medium" title="Working days between the estimated dispatch and the internal due date">Vs internal due</th>
                <th scope="col" className="rounded-r-chip px-2 py-2 font-medium">Held up by</th>
              </tr>
            </thead>
            <tbody>
              {risky.data.results.map((l) => {
                const held = holdingSummary(l.holding_op, l.holding_text);
                return (
                  <tr key={l.id} className="align-middle">
                    <td className="border-b border-line px-2 py-2.5">
                      <span className="block font-semibold">{l.part_number}</span>
                      <span className="block max-w-[16rem] truncate text-xs text-ink-soft">
                        <span className="font-mono">{l.customer_code}</span> {l.customer_name}
                      </span>
                    </td>
                    <td className="whitespace-nowrap border-b border-line px-2 py-2.5 font-mono text-xs">
                      <span className="block"><span className="inline-block min-w-14 pr-2 font-sans text-ink-soft">int. due</span>{formatDate(l.internal_date)}</span>
                      <span className="block"><span className="inline-block min-w-14 pr-2 font-sans text-ink-soft">est.</span>{l.est_dispatch_date ? formatDate(l.est_dispatch_date) : "–"}</span>
                    </td>
                    <td className="border-b border-line px-2 py-2.5"><VariancePill days={l.slack_working_days} /></td>
                    <td className="border-b border-line px-2 py-2.5" title={l.holding_text || undefined}>
                      {held.step ? (
                        <>
                          <span className="font-medium">{held.step}</span>
                          {held.days && <span className="ml-1.5 font-mono text-xs text-ink-soft">{held.days}</span>}
                        </>
                      ) : (
                        <span className="text-ink-soft">–</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
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
        <p role="status" className="rounded-card border border-warn bg-warn-wash px-4 py-2 text-sm">
          <strong className="text-warn">This plan is out of date.</strong> {plan.stale_reasons.join(" ")}{" "}
          <Link href="/plan" className="font-medium text-link underline-offset-2 hover:underline">Recalculate it</Link>
        </p>
      )}
      <StatRow>
        <Stat label="Plan" value={`v${plan.version}`} hint={plan.status === "draft" ? (plan.stale ? "draft, out of date" : "draft, up to date") : "confirmed baseline"} tone={plan.stale ? "ember" : "brand"} />
        <Stat label="Orders planned" value={formatNumber(plan.summary.lines ?? 0)} hint="open orders with a balance" tone="plain" />
        <Stat label="At risk" value={formatNumber((plan.summary.by_status?.at_risk ?? 0) + (plan.summary.by_status?.unscheduled ?? 0))} hint="cannot meet the dispatch date" tone={(plan.summary.by_status?.at_risk ?? 0) + (plan.summary.by_status?.unscheduled ?? 0) ? "danger" : "ok"} />
        <Stat label="Bottleneck" value={plan.bottleneck ? plan.bottleneck.code : "–"} hint="the machine holding the plan back" tone="ember" />
      </StatRow>
      <div className="grid gap-6 md:grid-cols-2">
        <DayPanel plan={plan} day={today} title="Today's plan" />
        <DayPanel plan={plan} day={addDays(today, 1)} title="Tomorrow's plan" />
      </div>
      <AtRisk plan={plan} />
      <Panel title="Bottleneck, next 14 working days" note={`plan v${plan.version}`}>
        <p className="mb-4 text-sm text-ink-soft">The most heavily loaded resource each day, with how full it is.</p>
        <BottleneckStrip plan={plan} />
      </Panel>
    </div>
  );
}

/** The five most important insight cards. */
function TopInsights() {
  const list = useApi<InsightList>("/insights");
  const top = homeInsights(list.data?.results ?? []);
  return (
    <Panel title="Top insights" note={list.data?.run?.plan_version ? `plan v${list.data.run.plan_version}` : undefined}>
      <p className="mb-3 text-sm text-ink-soft">Trends and anomalies across the plant. Late orders are listed above.</p>
      {list.loading ? (
        <LoadingState label="Loading insights" rows={3} />
      ) : list.error ? (
        <ErrorState message={list.error.message} onRetry={list.reload} />
      ) : top.length === 0 ? (
        <EmptyState title="No trends or anomalies to report">Late orders are listed above. Other insight cards are produced every time a plan is calculated.</EmptyState>
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
  return (
    <div className="space-y-6">
      <Hero />
      <PlanSection />
      <TopInsights />
    </div>
  );
}
