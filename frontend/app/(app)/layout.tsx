"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { AppShell } from "@/components/AppShell";
import { ErrorState, LoadingState } from "@/components/States";
import { useSession } from "@/lib/store";

export default function AppLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { status, error, load, actingCompanyId } = useSession();

  useEffect(() => {
    if (status === "loading") void load();
    if (status === "anon") router.replace("/login");
  }, [status, load, router]);

  if (status === "error") {
    return (
      <div className="mx-auto max-w-md px-4 py-16">
        <ErrorState title="Cannot load your session" message={error ?? ""} onRetry={() => void load()} />
      </div>
    );
  }
  if (status !== "authed") {
    return (
      <div className="mx-auto max-w-md px-4 py-16">
        <LoadingState label="Checking your session" />
      </div>
    );
  }
  // Switching the company a Vezapp Admin works on remounts the screen so it reloads its data.
  return <AppShell><div key={actingCompanyId ?? "own"}>{children}</div></AppShell>;
}
