"use client";

import Link from "next/link";
import { useState } from "react";

import { EmptyState, ErrorState, FormErrorLine, LoadingState, PageHeader } from "@/components/States";
import { Tabs } from "@/components/Tabs";
import { GanttTab } from "@/components/plan/GanttTab";
import { LinesTab } from "@/components/plan/LinesTab";
import { LoadTab } from "@/components/plan/LoadTab";
import { PlanBar } from "@/components/plan/PlanBar";
import { ReportsTab } from "@/components/plan/ReportsTab";
import { ApiError, post } from "@/lib/api";
import { useSession } from "@/lib/store";
import type { Plan } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const TABS = [
  { id: "lines", label: "Lines" },
  { id: "gantt", label: "Gantt" },
  { id: "load", label: "Load heatmap" },
  { id: "reports", label: "Print and export" },
];

function FirstPlan({ canEdit, onDone }: { canEdit: boolean; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create() {
    setBusy(true);
    setError(null);
    try {
      await post<Plan>("/plans");
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server.");
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <EmptyState
        title="No plan has been calculated yet"
        action={canEdit ? <button type="button" className="btn btn-primary" onClick={create} disabled={busy}>{busy ? "Calculating…" : "Calculate the first plan"}</button> : undefined}
      >
        A plan checks every dispatch line against the real hours and capacity of your resources, then shows when each line can ship and what holds it up. It needs shifts, resources, parts with routes, and a monthly schedule.{" "}
        <Link href="/scheduler" className="text-link underline-offset-2 hover:underline">Open the Monthly Scheduler</Link>.
      </EmptyState>
      {error && <FormErrorLine message={error} />}
    </div>
  );
}

export default function PlanPage() {
  const role = useSession((s) => s.user!.role);
  const canEdit = role !== "viewer";
  const [version, setVersion] = useState(0);
  const [planId, setPlanId] = useState<number | null>(null);
  const [tab, setTab] = useState("lines");
  const current = useApi<Plan | undefined>(planId ? `/plans/${planId}?v=${version}` : `/plans/latest?v=${version}`);
  const { loading, error, data: plan } = current;

  return (
    <>
      <PageHeader title="Plan" subtitle="Dispatch lines checked against real capacity, shift by shift" />
      {loading ? (
        <LoadingState label="Loading the plan" rows={4} />
      ) : error ? (
        <ErrorState message={error.message} onRetry={() => setVersion((v) => v + 1)} />
      ) : !plan ? (
        <FirstPlan canEdit={canEdit} onDone={() => setVersion((v) => v + 1)} />
      ) : (
        <>
          <PlanBar plan={plan} canEdit={canEdit} onChanged={() => setVersion((v) => v + 1)} onSelect={setPlanId} />
          <Tabs tabs={TABS} active={tab} onChange={setTab}>
            {tab === "lines" && <LinesTab key={plan.calculated_at} plan={plan} />}
            {tab === "gantt" && <GanttTab key={plan.calculated_at} plan={plan} />}
            {tab === "load" && <LoadTab key={plan.calculated_at} plan={plan} />}
            {tab === "reports" && <ReportsTab plan={plan} />}
          </Tabs>
        </>
      )}
    </>
  );
}
