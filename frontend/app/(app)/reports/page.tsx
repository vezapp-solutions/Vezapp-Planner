"use client";

import { useState } from "react";

import { DispatchTab } from "@/components/reports/DispatchTab";
import { PlanVsActualTab } from "@/components/reports/PlanVsActualTab";
import { UtilisationTab } from "@/components/reports/UtilisationTab";
import { PageHeader } from "@/components/States";
import { Tabs } from "@/components/Tabs";

const TABS = [
  { id: "dispatch", label: "Dispatch performance" },
  { id: "utilisation", label: "Utilisation" },
  { id: "actual", label: "Plan versus actual" },
];

export default function ReportsPage() {
  const [tab, setTab] = useState("dispatch");
  return (
    <>
      <PageHeader title="Reports" subtitle="How the plant is doing against its dates and its capacity" />
      <Tabs tabs={TABS} active={tab} onChange={setTab}>
        {tab === "dispatch" && <DispatchTab />}
        {tab === "utilisation" && <UtilisationTab />}
        {tab === "actual" && <PlanVsActualTab />}
      </Tabs>
    </>
  );
}
