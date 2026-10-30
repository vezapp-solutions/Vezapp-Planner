"use client";

import { EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/States";
import { formatDate } from "@/lib/format";
import { useSession } from "@/lib/store";
import type { Company, Page } from "@/lib/types";
import { useApi } from "@/lib/use-api";

export default function CompaniesPage() {
  const role = useSession((s) => s.user!.role);
  const companies = useApi<Page<Company>>("/companies");

  return (
    <>
      <PageHeader title="Companies" subtitle="Client foundries on this platform" />
      {role !== "vezapp_admin" ? (
        <EmptyState title="You do not have access to this screen">
          Only a Vezapp Admin can manage companies.
        </EmptyState>
      ) : companies.loading ? (
        <LoadingState label="Loading companies" rows={4} />
      ) : companies.error ? (
        <ErrorState message={companies.error.message} onRetry={companies.reload} />
      ) : companies.data && companies.data.results.length === 0 ? (
        <EmptyState title="No companies yet" />
      ) : (
        <div className="panel overflow-x-auto">
          <table className="w-full min-w-[30rem] text-left text-sm">
            <thead className="border-b border-line bg-sunken text-ink-soft">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium">Company</th>
                <th scope="col" className="px-4 py-2 font-medium">GSTIN</th>
                <th scope="col" className="px-4 py-2 font-medium">Status</th>
                <th scope="col" className="px-4 py-2 font-medium">Added</th>
              </tr>
            </thead>
            <tbody>
              {companies.data?.results.map((c) => (
                <tr key={c.id} className="border-b border-line last:border-0">
                  <td className="px-4 py-2 font-medium">{c.name}</td>
                  <td className="px-4 py-2 font-mono">{c.gstin || "–"}</td>
                  <td className="px-4 py-2">{c.is_active ? "Active" : "Inactive"}</td>
                  <td className="px-4 py-2 font-mono">{formatDate(c.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
