"use client";

import { useState } from "react";

import { CapacityAdjustments } from "@/components/masters/CapacityAdjustments";
import { CompanyDetails } from "@/components/masters/CompanyDetails";
import { Holidays } from "@/components/masters/Holidays";
import { OperationTypes } from "@/components/masters/OperationTypes";
import { PlanningSettings } from "@/components/masters/PlanningSettings";
import { ShiftsWeek } from "@/components/masters/ShiftsWeek";
import { PageHeader } from "@/components/States";
import { Tabs } from "@/components/Tabs";
import { canEditMasters } from "@/lib/nav";
import { useSession } from "@/lib/store";

const TABS = [
  { id: "hours", label: "Working hours" },
  { id: "holidays", label: "Holidays" },
  { id: "extra", label: "Extra shifts and overtime" },
  { id: "operations", label: "Operations" },
  { id: "settings", label: "Planning settings" },
  { id: "company", label: "Company and plants" },
];

export default function CompanyMaster() {
  const role = useSession((s) => s.user!.role);
  const canEdit = canEditMasters(role);
  const [tab, setTab] = useState("hours");

  return (
    <>
      <PageHeader title="Company calendar" subtitle="Working hours, holidays and planning settings" />
      <Tabs tabs={TABS} active={tab} onChange={setTab}>
        {tab === "hours" && <ShiftsWeek canEdit={canEdit} />}
        {tab === "holidays" && <Holidays canEdit={canEdit} />}
        {tab === "extra" && <CapacityAdjustments canEdit={canEdit} />}
        {tab === "operations" && <OperationTypes canEdit={canEdit} />}
        {tab === "settings" && <PlanningSettings canEdit={canEdit} />}
        {tab === "company" && <CompanyDetails canEdit={canEdit} />}
      </Tabs>
    </>
  );
}
