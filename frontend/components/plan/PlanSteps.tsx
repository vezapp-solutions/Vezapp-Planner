import Link from "next/link";

import type { Plan } from "@/lib/types";

/** The planning flow as a strip, with where the plan stands: upload, review parts, stock, run, read the plans. */
export function PlanSteps({ plan, canEdit, onTab }: { plan: Plan; canEdit: boolean; onTab: (tab: string) => void }) {
  const by = plan.summary.by_status ?? {};
  const out = plan.summary.excluded ?? { covered: 0, cannot_plan: 0 };
  const planned = (plan.summary.lines ?? 0) - (by.at_risk ?? 0) - (by.unscheduled ?? 0);
  const link = "inline-flex min-h-6 items-center text-link underline-offset-2 hover:underline";

  return (
    <nav aria-label="Planning steps" className="mb-5">
      <ol className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
        {[
          { n: 1, title: "Upload orders", body: canEdit ? <Link className={link} href="/scheduler/upload">Upload the monthly Excel</Link> : "Planner uploads the month" },
          { n: 2, title: "Review parts", body: <Link className={link} href="/masters/parts">Parts and routes</Link> },
          { n: 3, title: "Update stock", body: <button type="button" className={link} onClick={() => onTab("orders")}>WIP, FG, dispatched</button> },
          { n: 4, title: "Run planning", body: <span className={plan.stale ? "font-medium text-warn" : "text-ink-soft"}>{plan.stale ? "Stale: run planning" : "Up to date"}</span> },
          { n: 5, title: "Read the plans", body: <span><button type="button" className={link} onClick={() => onTab("mould")}>Mould plan</button> · <button type="button" className={link} onClick={() => onTab("melt")}>Melt plan</button></span> },
        ].map((s) => (
          <li key={s.n} className="panel flex items-start gap-3 px-3 py-2">
            <span className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-wash text-xs font-semibold text-link">{s.n}</span>
            <span className="text-sm">
              <span className="block font-medium">{s.title}</span>
              {s.body}
            </span>
          </li>
        ))}
      </ol>
      <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-ink-soft" aria-label="Orders by state">
        <span><span className="font-mono text-ink">{planned}</span> planned</span>
        <span><span className="font-mono text-ink">{(by.at_risk ?? 0) + (by.unscheduled ?? 0)}</span> at risk</span>
        <span><span className="font-mono text-ink">{out.covered}</span> covered by stock</span>
        <span><span className="font-mono text-ink">{out.cannot_plan}</span> cannot plan (missing master data)</span>
      </p>
    </nav>
  );
}
