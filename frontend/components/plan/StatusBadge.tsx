import { PLAN_STATUS_LABEL, type PlanLineStatus } from "@/lib/types";

const STYLE: Record<PlanLineStatus, string> = {
  on_track: "bg-ok-wash text-ok",
  tight: "bg-warn-wash text-warn",
  at_risk: "bg-danger-wash text-danger",
  unscheduled: "bg-sunken text-ink-soft",
};

export function StatusBadge({ status }: { status: PlanLineStatus }) {
  return <span className={`badge ${STYLE[status]}`}>{PLAN_STATUS_LABEL[status]}</span>;
}

/** Working days spare (+) or late (-), as a short signed number. */
export function Slack({ days }: { days: number | null }) {
  if (days == null) return <span className="text-ink-soft">–</span>;
  const tone = days < 0 ? "text-danger" : days < 2 ? "text-warn" : "text-ok";
  return <span className={`font-mono ${tone}`}>{days > 0 ? `+${days}` : days}</span>;
}
