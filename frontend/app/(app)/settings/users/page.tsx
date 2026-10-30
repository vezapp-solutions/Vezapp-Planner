"use client";

import { EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/States";
import { useSession } from "@/lib/store";
import { ROLE_LABEL, type AppUser, type Page } from "@/lib/types";
import { useApi } from "@/lib/use-api";

export default function UsersPage() {
  const role = useSession((s) => s.user!.role);
  const users = useApi<Page<AppUser>>("/users");
  const canView = role === "vezapp_admin" || role === "company_admin";

  return (
    <>
      <PageHeader title="Users" subtitle="People who can sign in, and what they can do" />
      {!canView ? (
        <EmptyState title="You do not have access to this screen">
          Only a Company Admin or Vezapp Admin can see users.
        </EmptyState>
      ) : users.loading ? (
        <LoadingState label="Loading users" rows={4} />
      ) : users.error ? (
        <ErrorState message={users.error.message} onRetry={users.reload} />
      ) : users.data && users.data.results.length === 0 ? (
        <EmptyState title="No users yet" />
      ) : (
        <div className="panel overflow-x-auto">
          <table className="w-full min-w-[34rem] text-left text-sm">
            <thead className="border-b border-line bg-sunken text-ink-soft">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium">Username</th>
                <th scope="col" className="px-4 py-2 font-medium">Name</th>
                <th scope="col" className="px-4 py-2 font-medium">Role</th>
                <th scope="col" className="px-4 py-2 font-medium">Company</th>
                <th scope="col" className="px-4 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {users.data?.results.map((u) => (
                <tr key={u.id} className="border-b border-line last:border-0">
                  <td className="px-4 py-2 font-mono">{u.username}</td>
                  <td className="px-4 py-2">{`${u.first_name} ${u.last_name}`.trim() || "–"}</td>
                  <td className="px-4 py-2">{ROLE_LABEL[u.role]}</td>
                  <td className="px-4 py-2">{u.company_name ?? "All companies"}</td>
                  <td className="px-4 py-2">{u.is_active ? "Active" : "Inactive"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
