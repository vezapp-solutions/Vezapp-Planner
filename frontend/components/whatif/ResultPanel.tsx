import { Panel } from "@/components/Panel";
import { EmptyState } from "@/components/States";
import { Slack, StatusBadge } from "@/components/plan/StatusBadge";
import { formatDate, formatDateTime, formatNumber } from "@/lib/format";
import { percent } from "@/lib/plan-utils";
import { PLAN_STATUS_LABEL, type PlanLineStatus, type ScenarioResult } from "@/lib/types";
import { bottleneckText, dateChange, groupLines, headline, movedText, utilisationChanges } from "@/lib/whatif";

function Card({ label, value, tone }: { label: string; value: string; tone?: "bad" | "good" }) {
  const colour = tone === "bad" ? "text-danger" : tone === "good" ? "text-ok" : "";
  return (
    <div className="panel px-4 py-3">
      <p className="text-xs text-ink-soft">{label}</p>
      <p className={`mt-0.5 font-mono text-xl font-semibold ${colour}`}>{value}</p>
    </div>
  );
}

function StatusMove({ before, after }: { before: PlanLineStatus; after: PlanLineStatus }) {
  if (before === after) return <StatusBadge status={after} />;
  return (
    <span className="flex flex-wrap items-center gap-1">
      <StatusBadge status={before} />
      <span aria-label="becomes">→</span>
      <StatusBadge status={after} />
    </span>
  );
}

function StatusCounts({ before, after }: { before: ScenarioResult["diff"]["status_before"]; after: ScenarioResult["diff"]["status_after"] }) {
  return (
    <ul className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
      {(Object.keys(PLAN_STATUS_LABEL) as PlanLineStatus[]).map((s) => {
        const a = before[s] ?? 0;
        const b = after[s] ?? 0;
        return (
          <li key={s} className="flex justify-between gap-3">
            <span>{PLAN_STATUS_LABEL[s]}</span>
            <span className="font-mono">{a} → {b}</span>
          </li>
        );
      })}
    </ul>
  );
}

/** The before and after of a run: headline cards, every changed line with its from → to date, and load. */
export function ResultPanel({ result, ranAt, stale }: { result: ScenarioResult; ranAt: string | null; stale: boolean }) {
  const { diff } = result;
  const groups = groupLines(diff.lines);
  const util = utilisationChanges(result);

  return (
    <div className={`space-y-5 ${stale ? "opacity-60" : ""}`} aria-label="Result of the last run">
      <div>
        <p className="text-sm font-medium">{headline(diff.counts)}</p>
        <p className="text-xs text-ink-soft">
          Planned {formatNumber(result.lines_planned)} lines twice from {formatDate(result.plan_from)}, once as things stand and once with these changes
          {ranAt ? ` · run ${formatDateTime(ranAt)}` : ""}.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Card label="Moved later" value={String(diff.counts.later)} tone={diff.counts.later ? "bad" : undefined} />
        <Card label="Moved earlier" value={String(diff.counts.earlier)} tone={diff.counts.earlier ? "good" : undefined} />
        <Card label="Newly at risk" value={String(diff.counts.newly_at_risk)} tone={diff.counts.newly_at_risk ? "bad" : undefined} />
        <Card label="Bottleneck" value={bottleneckText(result)} />
      </div>

      {groups.length === 0 ? (
        <EmptyState title="No line moves">With these changes every line keeps its estimated date and status.</EmptyState>
      ) : (
        groups.map((g) => (
          <section key={g.tag} aria-label={g.label}>
            <h3 className="mb-1 font-display text-base font-semibold">
              {g.label} <span className="font-mono text-sm font-normal text-ink-soft">({g.lines.length})</span>
            </h3>
            <div className="panel overflow-x-auto">
              <table className="w-full min-w-[46rem] text-left text-sm">
                <thead className="border-b border-line bg-sunken text-ink-soft">
                  <tr>
                    {["Customer", "Part", "Internal date", "Estimated date", "Moved", "Spare days", "Status", "Held up by"].map((h, i) => (
                      <th key={h} scope="col" className={`px-3 py-2 font-medium ${i === 5 ? "text-right" : ""}`}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {g.lines.map((l) => (
                    <tr key={l.line_id} className="border-b border-line last:border-0">
                      <td className="px-3 py-2"><span className="font-mono text-xs text-ink-soft">{l.customer_code}</span> {l.customer_name}</td>
                      <td className="px-3 py-2">
                        <span className="font-medium">{l.part_number}</span> <span className="text-ink-soft">{l.part_name}</span>
                        {l.qty_before !== l.qty_after && <span className="block font-mono text-xs">{formatNumber(l.qty_before)} → {formatNumber(l.qty_after)} pcs</span>}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 font-mono">
                        {l.internal_date_before === l.internal_date_after ? formatDate(l.internal_date_after) : `${formatDate(l.internal_date_before)} → ${formatDate(l.internal_date_after)}`}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 font-mono">{dateChange(l)}</td>
                      <td className="whitespace-nowrap px-3 py-2">{movedText(l.moved_working_days) ?? "–"}</td>
                      <td className="whitespace-nowrap px-3 py-2 text-right font-mono">
                        <Slack days={l.slack_before} /> → <Slack days={l.slack_after} />
                      </td>
                      <td className="px-3 py-2"><StatusMove before={l.status_before} after={l.status_after} /></td>
                      <td className="max-w-[16rem] px-3 py-2 text-ink-soft">{l.holding_after ? <span title={l.holding_text_after}>{l.holding_after}</span> : "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ))
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Lines by status" note="before → after">
          <StatusCounts before={diff.status_before} after={diff.status_after} />
        </Panel>
        <Panel title="Busiest shift of each resource" note="before → after">
          {util.length === 0 ? (
            <p className="text-sm text-ink-soft">No resource&apos;s peak load changes.</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {util.map((u) => (
                <li key={u.id} className="flex justify-between gap-3">
                  <span className="font-medium">{u.code}</span>
                  <span className="font-mono">{percent(u.before)} → {percent(u.after)}</span>
                </li>
              ))}
            </ul>
          )}
          {diff.day_bottlenecks.length > 0 && (
            <p className="mt-3 text-xs text-ink-soft">The busiest resource changes on {diff.day_bottlenecks.length} day{diff.day_bottlenecks.length === 1 ? "" : "s"}.</p>
          )}
        </Panel>
      </div>
    </div>
  );
}
