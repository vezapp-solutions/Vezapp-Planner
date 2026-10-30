"use client";

import { useState } from "react";

import { FormErrorLine } from "@/components/States";
import { ApiError, post } from "@/lib/api";
import { formatDateTime, formatNumber } from "@/lib/format";
import type { Page, Plan } from "@/lib/types";
import { useApi } from "@/lib/use-api";

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

  return (
    <section aria-label="Plan status" className="mb-5 space-y-3">
      <div className="panel flex flex-wrap items-center gap-x-5 gap-y-3 px-4 py-3">
        <div>
          <label htmlFor="plan-version" className="text-xs text-ink-soft">Plan</label>
          <select id="plan-version" className="field !min-h-9 !w-auto" value={plan.id} onChange={(e) => onSelect(Number(e.target.value))}>
            {(plans.data?.results ?? [plan]).map((p) => (
              <option key={p.id} value={p.id}>v{p.version} · {p.status === "draft" ? "Draft" : "Confirmed"}</option>
            ))}
          </select>
        </div>
        <div className="text-sm">
          <p className="text-xs text-ink-soft">Calculated</p>
          <p className="font-mono">{plan.calculated_at ? formatDateTime(plan.calculated_at) : "–"}</p>
        </div>
        <div className="text-sm">
          <p className="text-xs text-ink-soft">Lines</p>
          <p className="font-mono">
            {formatNumber(plan.summary.lines ?? 0)}
            <span className="ml-2 text-xs text-ink-soft">
              {by.at_risk ? `${by.at_risk} at risk` : "none at risk"}
              {by.tight ? ` · ${by.tight} tight` : ""}
              {by.unscheduled ? ` · ${by.unscheduled} not scheduled` : ""}
            </span>
          </p>
        </div>
        <div className="text-sm">
          <p className="text-xs text-ink-soft">Bottleneck</p>
          <p className="font-medium">{plan.bottleneck ? `${plan.bottleneck.code}` : "–"}</p>
        </div>
        {canEdit && (
          <div className="ml-auto flex flex-wrap gap-2">
            {draft && (
              <>
                <button type="button" className="btn btn-primary !min-h-9" onClick={() => run("recalc")} disabled={busy !== null}>
                  {busy === "recalc" ? "Calculating…" : "Recalculate"}
                </button>
                <button type="button" className="btn btn-quiet !min-h-9" onClick={() => run("confirm")} disabled={busy !== null || plan.stale} title={plan.stale ? "Recalculate first" : "Freeze this plan as the baseline"}>
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

      {plan.stale && draft && (
        <div role="status" className="flex flex-wrap items-center gap-3 rounded-md border border-warn bg-warn-wash px-4 py-2 text-sm">
          <span className="font-medium text-warn">This plan is out of date.</span>
          <span>{plan.stale_reasons.join(" ")}</span>
          {canEdit && (
            <button type="button" className="btn btn-quiet !min-h-8 ml-auto" onClick={() => run("recalc")} disabled={busy !== null}>
              Recalculate now
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
