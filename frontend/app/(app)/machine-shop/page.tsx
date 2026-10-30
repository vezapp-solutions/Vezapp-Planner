"use client";

import Link from "next/link";
import { useState } from "react";

import { MachineAvailability } from "@/components/machine-shop/MachineAvailability";
import { MachineOperations } from "@/components/machine-shop/MachineOperations";
import { EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/States";
import { Tabs } from "@/components/Tabs";
import { query } from "@/lib/insights";
import type { MachineShop } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const TABS = [
  { id: "availability", label: "Availability" },
  { id: "operations", label: "Operations" },
];

export default function MachineShopPage() {
  const [tab, setTab] = useState("availability");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const shop = useApi<MachineShop>(`/machine-shop${query({ from, to })}`);

  return (
    <>
      <PageHeader title="Machine shop" subtitle="Which machines are free, and what is planned on them" />
      <div className="mb-5 flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="mb-1 block text-ink-soft">From</span>
          <input type="date" className="field !min-h-10 !w-44" value={from} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-ink-soft">To</span>
          <input type="date" className="field !min-h-10 !w-44" value={to} onChange={(e) => setTo(e.target.value)} />
        </label>
        <p className="text-sm text-ink-soft">Leave the dates empty for the next two weeks.</p>
      </div>

      {shop.loading ? (
        <LoadingState label="Loading the machine shop" rows={4} />
      ) : shop.error || !shop.data ? (
        <ErrorState message={shop.error?.message ?? "Could not load."} onRetry={shop.reload} />
      ) : shop.data.types.length === 0 ? (
        <EmptyState title="No machine is used by a machining operation yet">
          Add machine types (VMC, CNC, HMC) and machines under Resources, then give a part&apos;s route one or more machining operations and choose the machine types that may run them.{" "}
          <Link href="/masters/parts" className="inline-flex min-h-6 items-center text-link underline-offset-2 hover:underline">Open parts and routes</Link>
        </EmptyState>
      ) : !shop.data.plan ? (
        <EmptyState title="No plan has been calculated yet">
          The machines are set up. Calculate a plan and this screen shows how much of each machine&apos;s time is used.{" "}
          <Link href="/plan" className="inline-flex min-h-6 items-center text-link underline-offset-2 hover:underline">Open the plan</Link>
        </EmptyState>
      ) : (
        <Tabs tabs={TABS} active={tab} onChange={setTab}>
          {tab === "availability" && (shop.data.days.length ? <MachineAvailability shop={shop.data} /> : <EmptyState title="No working days in this period">Pick dates inside the plan.</EmptyState>)}
          {tab === "operations" && (shop.data.operations.length ? <MachineOperations shop={shop.data} /> : <EmptyState title="No machining operation is in the plan">No planned line has a machining operation.</EmptyState>)}
        </Tabs>
      )}
    </>
  );
}
