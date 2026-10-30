"use client";

import type { ReactNode } from "react";

import { EmptyState } from "@/components/States";
import { useSession } from "@/lib/store";

/** Masters belong to one company. A Vezapp Admin has none, so they must pick one first. */
export default function MastersLayout({ children }: { children: ReactNode }) {
  const { user, actingCompanyId } = useSession();
  if (user?.role === "vezapp_admin" && !actingCompanyId) {
    return (
      <EmptyState title="Choose a company first">
        Masters belong to one client foundry. Pick one from “Working on” in the top bar.
      </EmptyState>
    );
  }
  return <>{children}</>;
}
