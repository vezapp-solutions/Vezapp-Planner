import type { PlanningConfig } from "@/lib/types";
import { useApi } from "@/lib/use-api";

/** The operations planned in this phase. Everything else is shown as "Phase 2 / not planned". */
export function usePlanningConfig() {
  const { data } = useApi<PlanningConfig>("/planning-config");
  const planned = data ? new Set(data.planned_operations) : null;
  return {
    config: data ?? null,
    /** True when we do not know yet: show everything rather than hide it. */
    isPlanned: (code: string) => (planned ? planned.has(code) : true),
  };
}

/** Machining and the other later operations are not planned unless the deployment switches them on. */
export function plansMachining(config: PlanningConfig | null): boolean {
  return config ? config.planned_operations.includes("machining") : true;
}
