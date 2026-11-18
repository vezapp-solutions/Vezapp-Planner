"use client";

import { useState } from "react";

import { Stat, StatRow } from "@/components/Stat";
import { FormErrorLine } from "@/components/States";
import { ApiError, post } from "@/lib/api";
import { formatDateTime, formatNumber } from "@/lib/format";
import type { Page, Plan } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { Select } from "@/components/ui/Select";

/** Version, state and the Recalculate / Confirm / New plan actions of the plan being viewed. */
export function PlanBar({
  plan,
  canEdit,
  onChanged,
  onSelect,
}: {
  plan: Plan;
  canEdit: boolean;
  onChanged: () => void;
  onSelect: (id: number | null) => void;
}) {
  const [busy, setBusy] = useState<"recalc" | "confirm" | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const plans = useApi<Page<Plan>>(`/plans?page_size=30&v=${plan.calculated_at}`);

  async function run(kind: "recalc" | "confirm" | "new") {
    setBusy(kind);
    setError(null);
    try {
      if (kind === "new") {
        await post<Plan>("/plans");
        onSelect(null);
      } else {
        await post<Plan>(`/plans/${plan.id}/${kind === "recalc" ? "recalculate" : "confirm"}`);
      }
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server.");
    } finally {
      setBusy(null);
    }
  }

  const by = plan.summary.by_status ?? {};
  const draft = plan.status === "draft";
  const out = plan.summary.excluded ?? { covered: 0, cannot_plan: 0 };
  const atRisk = (by.at_risk ?? 0) + (by.unscheduled ?? 0);
  const onTrack = Math.max(0, (plan.summary.lines ?? 0) - atRisk);

  return (
    <section aria-label="Plan status" className="mb-5 space-y-4">
      <div className="panel flex flex-wrap items-center gap-x-6 gap-y-3 px-5 py-3.5">
        <div>
          <label htmlFor="plan-version" className="text-xs font-semibold uppercase tracking-wider text-ink-soft">Plan</label>
          <Select id="plan-version" className="field !min-h-9 !w-auto" value={plan.id} onChange={(e) => onSelect(Number(e.target.value))}>
            {(plans.data?.results ?? [plan]).map((p) => (
              <option key={p.id} value={p.id}>v{p.version} · {p.status === "draft" ? "Draft" : "Confirmed"}</option>
            ))}
          </Select>
        </div>
        <div className="text-sm">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">Calculated</p>
          <p className="font-mono">{plan.calculated_at ? formatDateTime(plan.calculated_at) : "–"}</p>
        </div>
        <div className="text-sm">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">Bottleneck</p>
          <p className="font-display text-base font-semibold">{plan.bottleneck ? `${plan.bottleneck.code}` : "–"}</p>
        </div>
        {canEdit && (
          <div className="ml-auto flex flex-wrap gap-2">
            {draft && (
              <>
                <button type="button" className="btn btn-primary !min-h-9" onClick={() => run("recalc")} disabled={busy !== null}>
                  {busy === "recalc" ? "Planning…" : "Run planning"}
                </button>
                <button type="button" className="btn btn-quiet !min-h-9" onClick={() => run("confirm")} disabled={busy !== null || plan.stale} title={plan.stale ? "Run planning first" : "Freeze this plan as the baseline"}>
                  {busy === "confirm" ? "Confirming…" : "Confirm plan"}
                </button>
              </>
            )}
            {!draft && (
              <button type="button" className="btn btn-primary !min-h-9" onClick={() => run("new")} disabled={busy !== null}>
                {busy === "new" ? "Calculating…" : "New plan"}
              </button>
            )}
          </div>
        )}
      </div>

      <div aria-label="Orders by state" role="group">
        <StatRow>
          <Stat label="On track" value={formatNumber(onTrack)} hint="planned and on time" tone="ok" />
          <Stat label="At risk" value={formatNumber(atRisk)} hint={by.tight ? `${by.tight} more are tight` : "cannot meet the date"} tone={atRisk ? "danger" : "ok"} />
          <Stat label="Covered by stock" value={formatNumber(out.covered)} hint="nothing to make" tone="brand" />
          <Stat label="Cannot plan" value={formatNumber(out.cannot_plan)} hint="missing master data" tone={out.cannot_plan ? "warn" : "plain"} />
        </StatRow>
      </div>

      {plan.stale && draft && (
        <div role="status" className="flex flex-wrap items-center gap-3 rounded-card border border-ember bg-ember-wash px-4 py-2.5 text-sm">
          <span className="font-semibold text-ember-ink">Stale: run planning again.</span>
          <span>{plan.stale_reasons.join(" ")}</span>
          {canEdit && (
            <button type="button" className="btn btn-quiet !min-h-8 ml-auto" onClick={() => run("recalc")} disabled={busy !== null}>
              Run planning
            </button>
          )}
        </div>
      )}
      {!draft && (
        <p className="text-sm text-ink-soft">
          Confirmed {plan.confirmed_at ? formatDateTime(plan.confirmed_at) : ""}. A confirmed plan is a frozen baseline; start a new plan to plan again.
        </p>
      )}
      {error && <FormErrorLine message={error} />}
    </section>
  );
}
