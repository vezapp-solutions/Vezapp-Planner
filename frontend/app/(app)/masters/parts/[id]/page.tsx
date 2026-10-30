"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { Issues } from "@/components/Explain";
import { ErrorState, LoadingState, PageHeader } from "@/components/States";
import { RouteEditor } from "@/components/masters/RouteEditor";
import { canEditMasters } from "@/lib/nav";
import { useSession } from "@/lib/store";
import type { Page, Part, Resource, ResourceType, Route } from "@/lib/types";
import { useApi } from "@/lib/use-api";

export default function PartRoutePage() {
  const id = useParams<{ id: string }>().id;
  const canEdit = canEditMasters(useSession((s) => s.user!.role));
  const part = useApi<Part>(`/parts/${id}`);
  const route = useApi<Route>(`/parts/${id}/operations`);
  const resources = useApi<Page<Resource>>("/resources?page_size=500");
  const types = useApi<Page<ResourceType>>("/resource-types?page_size=500");
  const parts = useApi<Page<Part>>("/parts?page_size=500");

  if (part.loading || route.loading || resources.loading || types.loading || parts.loading) {
    return <LoadingState label="Loading the route" rows={5} />;
  }
  const failure = part.error ?? route.error ?? resources.error ?? types.error ?? parts.error;
  if (failure || !part.data || !route.data || !resources.data || !types.data || !parts.data) {
    return (
      <ErrorState
        title="Cannot open this part"
        message={failure?.message ?? "Not found."}
        onRetry={() => { part.reload(); route.reload(); resources.reload(); types.reload(); parts.reload(); }}
      />
    );
  }
  const p = part.data;

  return (
    <>
      <p className="mb-2 text-sm">
        <Link href="/masters/parts" className="inline-flex min-h-6 items-center text-link underline-offset-2 hover:underline">← Parts and routes</Link>
      </p>
      <PageHeader
        title={`${p.part_number} · ${p.name}`}
        subtitle={`Operation route · ${p.grade_name ?? "no grade"} · ${p.cavities_per_mould} per mould · ${p.cores_per_mould} cores per mould · ${Number(p.pouring_weight_per_mould_kg)} kg poured per mould`}
      />
      {p.warnings.length > 0 && <div className="mb-4"><Issues issues={p.warnings} /></div>}
      <RouteEditor
        part={p}
        initial={route.data}
        resources={resources.data.results}
        machineTypes={types.data.results.filter((t) => t.kind === "work_centre")}
        otherParts={parts.data.results.filter((o) => o.id !== p.id)}
        canEdit={canEdit}
      />
    </>
  );
}
