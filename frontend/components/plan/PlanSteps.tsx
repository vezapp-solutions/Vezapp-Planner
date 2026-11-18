import Link from "next/link";

import type { Plan } from "@/lib/types";

/** The planning flow as a strip, with where the plan stands: upload, review parts, stock, run, read the plans. */
export function PlanSteps({ plan, canEdit, onTab }: { plan: Plan; canEdit: boolean; onTab: (tab: string) => void }) {
  const link = "inline-flex min-h-6 items-center font-medium text-link underline-offset-2 hover:underline";

  return (
    <nav aria-label="Planning steps" className="mb-6">
      <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {[
          { n: 1, title: "Upload orders", body: canEdit ? <Link className={link} href="/scheduler/upload">Upload the monthly Excel</Link> : "Planner uploads the month" },
          { n: 2, title: "Review parts", body: <Link className={link} href="/masters/parts">Parts and routes</Link> },
          { n: 3, title: "Update stock", body: <button type="button" className={link} onClick={() => onTab("orders")}>WIP, FG, dispatched</button> },
          { n: 4, title: "Run planning", body: <span className={plan.stale ? "font-semibold text-ember-ink" : "text-ink-soft"}>{plan.stale ? "Stale: run planning" : "Up to date"}</span>, state: plan.stale ? "alert" : "done" },
          { n: 5, title: "Read the plans", body: <span><button type="button" className={link} onClick={() => onTab("mould")}>Mould plan</button> · <button type="button" className={link} onClick={() => onTab("melt")}>Melt plan</button></span> },
        ].map((s, i, all) => (
          <li key={s.n} className="panel relative flex items-start gap-3 px-3.5 py-3">
            <span className="step-num" data-state={s.state}>{s.n}</span>
            <span className="text-sm leading-snug">
              <span className="block font-display text-[0.9375rem] font-semibold">{s.title}</span>
              {s.body}
            </span>
            {i < all.length - 1 && (
              <span aria-hidden="true" className="absolute -right-[0.8rem] top-1/2 z-10 hidden h-px w-3 bg-ink-soft/40 lg:block" />
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
