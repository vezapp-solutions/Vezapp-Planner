"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { SparkleIcon } from "@/components/insights/AiBadge";
import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { navFor } from "@/lib/nav";
import { useSession } from "@/lib/store";
import { ROLE_LABEL, type Company, type Page } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { Select } from "@/components/ui/Select";

function SideNav({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const role = useSession((s) => s.user!.role);

  return (
    <nav aria-label="Main" className="flex flex-col py-3">
      {navFor(role).map((item) => {
        const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
        const base =
          "flex min-h-10 items-center justify-between gap-2 border-l-[3px] px-4 text-[0.9375rem]";
        if (item.phase) {
          return (
            <span
              key={item.href}
              aria-disabled="true"
              title={`Arrives in Phase ${item.phase}`}
              className={`${base} border-transparent text-ink-soft opacity-70`}
            >
              {item.label}
              <span className="font-mono text-[0.6875rem] uppercase">Ph {item.phase}</span>
            </span>
          );
        }
        return (
          <div key={item.href}>
            <Link
              href={item.href}
              onClick={onNavigate}
              aria-current={active && !item.children ? "page" : undefined}
              className={`${base} ${
                active
                  ? "border-brand bg-sunken font-semibold"
                  : "border-transparent hover:bg-sunken active:bg-line"
              }`}
            >
              {item.label}
            </Link>
            {active &&
              item.children?.map((child) => {
                const here = pathname === child.href || (child.href !== item.href && pathname.startsWith(`${child.href}/`));
                return (
                  <Link
                    key={child.href}
                    href={child.href}
                    onClick={onNavigate}
                    aria-current={here ? "page" : undefined}
                    className={`flex min-h-9 items-center border-l-[3px] py-1 pl-8 pr-4 text-sm ${
                      here ? "border-brand font-semibold" : "border-transparent text-ink-soft hover:bg-sunken"
                    }`}
                  >
                    {child.label}
                  </Link>
                );
              })}
          </div>
        );
      })}
    </nav>
  );
}

function UserMenu() {
  const router = useRouter();
  const { user, logout } = useSession();
  const [busy, setBusy] = useState(false);
  if (!user) return null;

  async function signOut() {
    setBusy(true);
    await logout();
    router.replace("/login");
  }

  return (
    <div className="flex items-center gap-3">
      <div className="hidden text-right leading-tight sm:block">
        <p className="text-sm font-medium">{user.full_name}</p>
        <p className="text-xs text-ink-soft">{ROLE_LABEL[user.role]}</p>
      </div>
      <button type="button" onClick={signOut} disabled={busy} className="btn btn-quiet !min-h-9 whitespace-nowrap">
        {busy ? "Signing out…" : "Sign out"}
      </button>
    </div>
  );
}

/** Opens the AI assistant (the Ask tab on Insights) from any screen, for every role. */
function AskAiButton() {
  return (
    <Link
      href="/insights?tab=ask"
      aria-label="Ask the AI assistant"
      title="Ask the AI assistant"
      className="inline-flex min-h-9 items-center gap-1.5 rounded-sm bg-action px-2.5 text-sm font-semibold text-on-action hover:opacity-90"
    >
      <SparkleIcon className="h-4 w-4" />
      <span className="hidden sm:inline">Ask AI</span>
    </Link>
  );
}

/** Vezapp Admin only: pick the client company every screen then works on. On a phone it sits on its own row under the top bar. */
function CompanySwitcher({ full = false }: { full?: boolean }) {
  const { actingCompanyId, chooseCompany } = useSession();
  const companies = useApi<Page<Company>>("/companies?page_size=500");
  const options = companies.data?.results.filter((c) => c.is_active) ?? [];

  return (
    <label className="flex items-center gap-2 text-sm">
      <span className={`text-ink-soft ${full ? "" : "hidden lg:inline"}`}>Working on</span>
      <Select
        className={`field !min-h-9 ${full ? "min-w-0 flex-1" : "!w-auto max-w-[16rem]"}`}
        value={actingCompanyId ?? ""}
        onChange={(e) => chooseCompany(e.target.value ? Number(e.target.value) : null)}
        aria-label="Company to work on"
      >
        <option value="">Choose a company…</option>
        {options.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </Select>
    </label>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const user = useSession((s) => s.user!);
  const company = user.company?.name ?? "";
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    if (!drawerOpen) return;
    const close = (e: KeyboardEvent) => e.key === "Escape" && setDrawerOpen(false);
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [drawerOpen]);

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[15rem_1fr] lg:grid-rows-[auto_1fr]">
      <div className="col-span-2">
      <header className="flex h-14 items-center gap-2 border-b border-line border-t-[3px] border-t-brand bg-surface px-3 sm:gap-3 sm:px-4">
        <button
          type="button"
          className="btn btn-quiet !min-h-9 !px-2.5 lg:hidden"
          aria-label="Open menu"
          aria-expanded={drawerOpen}
          onClick={() => setDrawerOpen(true)}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </button>
        <Link href="/home" aria-label="Home">
          <Logo height={24} priority />
        </Link>
        {user.role === "vezapp_admin" ? (
          <div className="ml-1 hidden min-w-0 border-l border-line pl-3 md:block">
            <CompanySwitcher />
          </div>
        ) : (
          <p className="ml-1 hidden min-w-0 truncate border-l border-line pl-3 text-sm text-ink-soft md:block">
            {company}
          </p>
        )}
        <div className="ml-auto flex items-center gap-2">
          <AskAiButton />
          <ThemeToggle />
          <UserMenu />
        </div>
      </header>
      {user.role === "vezapp_admin" && (
        <div className="border-b border-line bg-surface px-3 py-2 md:hidden">
          <CompanySwitcher full />
        </div>
      )}
      </div>

      <aside className="hidden border-r border-line bg-surface lg:block">
        <SideNav />
      </aside>

      {drawerOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <button
            type="button"
            className="absolute inset-0 bg-black/50"
            aria-label="Close menu"
            onClick={() => setDrawerOpen(false)}
          />
          <aside className="relative h-full w-64 max-w-[85vw] border-r border-line bg-surface">
            <div className="flex h-14 items-center justify-between border-b border-line px-4">
              <span className="font-display text-lg font-semibold">Menu</span>
              <button
                type="button"
                className="btn btn-quiet !min-h-9"
                onClick={() => setDrawerOpen(false)}
              >
                Close
              </button>
            </div>
            <SideNav key={pathname} onNavigate={() => setDrawerOpen(false)} />
          </aside>
        </div>
      )}

      <main className="min-w-0 px-4 py-6 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-6xl">{children}</div>
      </main>
    </div>
  );
}
