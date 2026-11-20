import { slackLabel, slackWords } from "@/lib/plan-utils";
import { PLAN_STATUS_LABEL, type PlanLineStatus } from "@/lib/types";

const STYLE: Record<PlanLineStatus, string> = {
  on_track: "bg-ok-wash text-ok",
  tight: "bg-warn-wash text-warn",
  at_risk: "bg-danger-wash text-danger",
  unscheduled: "bg-sunken text-on-sunken",
};

export function StatusBadge({ status }: { status: PlanLineStatus }) {
  return <span className={`badge ${STYLE[status]}`}>{PLAN_STATUS_LABEL[status]}</span>;
}

/** Working days spare (+) or late (-), with its unit ("-4d") and the plain words on hover. */
export function Slack({ days }: { days: number | null }) {
  if (days == null) return <span className="text-ink-soft">–</span>;
  const tone = days < 0 ? "text-danger" : days < 2 ? "text-warn" : "text-ok";
  return (
    <span className={`font-mono ${tone}`} title={slackWords(days)} aria-label={slackWords(days)}>
      {slackLabel(days)}
    </span>
  );
}
