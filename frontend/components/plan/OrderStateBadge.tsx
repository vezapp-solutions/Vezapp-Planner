import { ORDER_STATE_LABEL, type OrderState } from "@/lib/types";

const STYLE: Record<OrderState, string> = {
  closed: "bg-sunken text-ink-soft",
  covered: "bg-brand-wash text-link",
  cannot_plan: "bg-warn-wash text-warn",
  at_risk: "bg-danger-wash text-danger",
  planned: "bg-ok-wash text-ok",
  not_planned_yet: "border border-line text-ink-soft",
};

/** The badge beside an order: Planned, Covered by stock, Cannot plan (missing data), At risk, Closed. */
export function OrderStateBadge({ state, reasons = [] }: { state: OrderState; reasons?: string[] }) {
  return (
    <span className="inline-flex flex-col items-start gap-0.5">
      <span
        className={`badge ${STYLE[state]}`}
        title={reasons.join("\n") || undefined}
      >
        {ORDER_STATE_LABEL[state]}
      </span>
      {reasons.length > 0 && (state === "cannot_plan" || state === "at_risk") && (
        <span className="max-w-[16rem] text-xs leading-snug text-ink-soft">
          {reasons[0]}
          {reasons.length > 1 && ` (+${reasons.length - 1} more)`}
        </span>
      )}
    </span>
  );
}
