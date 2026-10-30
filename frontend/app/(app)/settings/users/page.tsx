"use client";

import { useMemo } from "react";

import { CrudScreen } from "@/components/CrudScreen";
import { EmptyState, PageHeader } from "@/components/States";
import type { FieldSpec } from "@/components/forms";
import { useSession } from "@/lib/store";
import { ROLE_LABEL, type AppUser, type Company, type Page, type Role } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const COMPANY_ROLES: Role[] = ["company_admin", "planner", "viewer"];
const ALL_ROLES: Role[] = ["vezapp_admin", ...COMPANY_ROLES];

export default function UsersPage() {
  const me = useSession((s) => s.user!);
  const isVezapp = me.role === "vezapp_admin";
  const canView = isVezapp || me.role === "company_admin";
  // Only a Vezapp Admin chooses the company; a Company Admin always adds to their own.
  const companies = useApi<Page<Company>>("/companies?page_size=500");

  const fields = useMemo<FieldSpec[]>(
    () => [
      { key: "username", label: "Username", type: "text", required: true, hint: "What they type to sign in." },
      { key: "role", label: "Role", type: "select", required: true, options: (isVezapp ? ALL_ROLES : COMPANY_ROLES).map((r) => ({ value: r, label: ROLE_LABEL[r] })) },
      { key: "first_name", label: "First name", type: "text" },
      { key: "last_name", label: "Last name", type: "text" },
      { key: "email", label: "Email", type: "text", hint: "Optional." },
      ...(isVezapp
        ? [
            {
              key: "company",
              label: "Company",
              type: "select",
              required: true,
              options: (companies.data?.results ?? []).map((c) => ({ value: c.id, label: c.name })),
              showIf: (d) => d.role !== "vezapp_admin",
              hint: "Which client this person works for.",
            } satisfies FieldSpec,
          ]
        : []),
      {
        key: "password",
        label: "Password",
        type: "password",
        hint: "Needed for a new user: at least 8 characters, not a common password. When editing, fill it in only to set a new one, then tell the person.",
      },
      { key: "is_active", label: "Active (can sign in)", type: "checkbox" },
    ],
    [isVezapp, companies.data],
  );

  return (
    <>
      <PageHeader title="Users" subtitle="People who can sign in, and what they can do" />
      {!canView ? (
        <EmptyState title="You do not have access to this screen">
          Only a Company Admin or Vezapp Admin can see users.
        </EmptyState>
      ) : (
        <CrudScreen<AppUser>
          path="/users"
          noun="user"
          fields={fields}
          canEdit
          defaults={{ role: "planner", is_active: true }}
          canDelete={(u) => u.id !== me.id}
          adjustPayload={(payload, _draft, row) => {
            // A blank password on an existing user means "keep the current one".
            if (!payload.password) delete payload.password;
            // The role and company of your own account stay as they are.
            if (row && row.id === me.id) {
              delete payload.role;
              delete payload.company;
              delete payload.is_active;
            }
            if (payload.company === "") delete payload.company;
            return payload;
          }}
          emptyHint="Add the first Company Admin for each client, then they add their own planners and viewers."
          subtitle={(u) => (u.id === me.id ? "This is your own account." : (u.company_name ?? "All companies"))}
          columns={[
            { header: "Username", cell: (u) => <span className="font-mono">{u.username}</span> },
            { header: "Name", cell: (u) => `${u.first_name} ${u.last_name}`.trim() || "–" },
            { header: "Role", cell: (u) => ROLE_LABEL[u.role] },
            { header: "Company", cell: (u) => u.company_name ?? "All companies" },
            { header: "Status", cell: (u) => (u.is_active ? "Active" : <span className="text-ink-soft">Inactive</span>) },
          ]}
        />
      )}
    </>
  );
}
