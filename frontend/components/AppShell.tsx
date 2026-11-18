"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";

import { SparkleIcon } from "@/components/insights/AiBadge";
import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { navFor } from "@/lib/nav";
import { usePlanningConfig } from "@/lib/planning-config";
import { useSession } from "@/lib/store";
import { ROLE_LABEL, type Company, type Page } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { Popover } from "@/components/ui/Popover";
import { Select } from "@/components/ui/Select";

/** Simple 24px line icons, one per screen. Decorative: the label beside each carries the meaning. */
const ICONS: Record<string, ReactNode> = {
  "/home": <path d="M3 11.5 12 4l9 7.5M5.5 10v9.5h4.5v-5h4v5h4.5V10" />,
  "/masters": (
    <>
      <ellipse cx="12" cy="6" rx="7.5" ry="3" />
      <path d="M4.5 6v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3V6M4.5 12v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-6" />
    </>
  ),
  "/scheduler": (
    <>
      <rect x="3.5" y="5" width="17" height="15" rx="2.5" />
      <path d="M3.5 10h17M8 3v4M16 3v4M8 14h2M12 14h2M8 17h2" />
    </>
  ),
  "/plan": (
    <>
      <path d="M4 6h9M4 12h13M4 18h7" />
      <circle cx="17" cy="6" r="1.6" />
      <circle cx="20" cy="18" r="1.6" />
    </>
  ),
  "/machine-shop": (
    <>
      <circle cx="12" cy="12" r="3.2" />
      <path d="M12 3v2.6M12 18.4V21M3 12h2.6M18.4 12H21M5.6 5.6l1.9 1.9M16.5 16.5l1.9 1.9M18.4 5.6l-1.9 1.9M7.5 16.5l-1.9 1.9" />
    </>
  ),
  "/what-if": (
    <>
      <path d="M9.5 3.5h5M10.5 3.5v5.2L5.2 18a2 2 0 0 0 1.7 3h10.2a2 2 0 0 0 1.7-3l-5.3-9.3V3.5" />
      <path d="M8 15h8" />
    </>
  ),
  "/insights": <path d="M12 3.5 13.8 9l5.7 1.8-5.7 1.8L12 18.5l-1.8-5.9-5.7-1.8L10.2 9 12 3.5ZM19 16l.7 1.8 1.8.7-1.8.7L19 21l-.7-1.8-1.8-.7 1.8-.7L19 16Z" />,
  "/reports": (
    <>
      <path d="M6 3.5h8l4.5 4.5v12a1 1 0 0 1-1 1h-11.5a1 1 0 0 1-1-1v-15.5a1 1 0 0 1 1-1Z" />
      <path d="M14 3.5V8h4.5M8.5 17v-3M12 17v-6M15.5 17v-4" />
    </>
  ),
  "/companies": (
    <>
      <path d="M4 20.5V6.5a1 1 0 0 1 1-1h8a1 1 0 0 1 1 1v14M14 10.5h5a1 1 0 0 1 1 1v9" />
      <path d="M7.5 9h3M7.5 12.5h3M7.5 16h3M3 20.5h18" />
    </>
  ),
  "/settings/users": (
    <>
      <circle cx="9" cy="8.5" r="3.2" />
      <path d="M3 19.5c.6-3.3 3-5 6-5s5.4 1.7 6 5M16 5.5a3 3 0 0 1 0 6M18 14.8c1.7.6 2.8 2.2 3 4.7" />
    </>
  ),
  "/settings/data-health": <path d="M3 12h4l2.5-6 4 12 2.5-6H21" />,
  "/settings/audit": (
    <>
      <path d="M8 3.5h8a1.5 1.5 0 0 1 1.5 1.5v15a1 1 0 0 1-1 1h-9a1 1 0 0 1-1-1V5A1.5 1.5 0 0 1 8 3.5Z" />
      <path d="M9 8.5h6M9 12h6M9 15.5h3.5" />
    </>
  ),
};

function NavIcon({ href, className = "nav-icon", size = 20 }: { href: string; className?: string; size?: number }) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {ICONS[href] ?? <circle cx="12" cy="12" r="4" />}
    </svg>
  );
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "?") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

function Avatar({ name, size = 36 }: { name: string; size?: number }) {
  return (
    <span
      aria-hidden="true"
      className="flex flex-none items-center justify-center rounded-full font-display text-sm font-bold text-white"
      style={{ width: size, height: size, background: "linear-gradient(135deg, var(--ember), color-mix(in srgb, var(--ember) 55%, #1ce4d4))" }}
    >
      {initials(name)}
    </span>
  );
}

/** Closes a drop-down when you click elsewhere or press Escape. */
function useDismiss(open: boolean, close: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) close();
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close]);
  return ref;
}

/** The person's menu in the floating bar: who they are, and sign out. */
function PersonMenu() {
  const router = useRouter();
  const { user, logout } = useSession();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const ref = useDismiss(open, () => setOpen(false));
  if (!user) return null;

  async function signOut() {
    setBusy(true);
    await logout();
    router.replace("/login");
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account menu for ${user.full_name}`}
        className="flex h-10 w-10 items-center justify-center rounded-full focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
      >
        <Avatar name={user.full_name} size={40} />
      </button>
      {open && (
        <div role="menu" className="menu">
          <div className="flex items-center gap-3 px-3 py-2.5">
            <Avatar name={user.full_name} size={40} />
            <div className="min-w-0 leading-tight">
              <p className="truncate text-sm font-semibold">{user.full_name}</p>
              <p className="truncate text-xs text-ink-soft">{ROLE_LABEL[user.role]}</p>
            </div>
          </div>
          <div className="my-1 h-px bg-line" />
          <button type="button" role="menuitem" className="menu-item" onClick={signOut} disabled={busy}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M14 4.5h4.5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H14M10 8l-4 4 4 4M6 12h9" />
            </svg>
            {busy ? "Signing out…" : "Sign out"}
          </button>
        </div>
      )}
    </div>
  );
}

/** The less-used screens (administration, machine shop) tucked under one pill item. */
function MoreMenu({ items, active }: { items: { href: string; label: string }[]; active: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useDismiss(open, () => setOpen(false));
  const pathname = usePathname();
  return (
    <div ref={ref} className="relative">
      <button type="button" className="pill-link" data-active={active} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        More
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      {open && (
        <div role="menu" className="menu" style={{ right: "auto", left: 0 }}>
          {items.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              role="menuitem"
              onClick={() => setOpen(false)}
              aria-current={pathname === item.href || pathname.startsWith(`${item.href}/`) ? "page" : undefined}
              className="menu-item"
            >
              <NavIcon href={item.href} className="text-ink-soft" />
              {item.label}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

const PRIMARY = ["/home", "/masters", "/scheduler", "/plan", "/what-if", "/insights", "/reports"];
/** Shorter names where the pill is tight. */
const PILL_LABEL: Record<string, string> = { "/scheduler": "Scheduler" };

/** The floating dark pill: logo, the main screens, a More menu, the theme switch and the person. */
function FloatingNav() {
  const pathname = usePathname();
  const role = useSession((s) => s.user!.role);
  const { config } = usePlanningConfig();
  const all = navFor(role, config?.planned_operations);
  const primary = all.filter((i) => PRIMARY.includes(i.href));
  const more = all.filter((i) => !PRIMARY.includes(i.href));
  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);

  return (
    <nav aria-label="Main" className="pill-bar flex items-center gap-0.5">
      <Link href="/home" aria-label="Vezapp Planner home" className="flex h-10 items-center rounded-full px-3.5 focus-visible:outline-2 focus-visible:outline-brand">
        {/* Just the V: bright teal on the black bar, a deeper teal on the white bar in dark mode. */}
        {/* eslint-disable-next-line @next/next/no-img-element -- a fixed 81x64 asset, shown by CSS per theme */}
        <img src="/brand/vezapp-v.png" alt="" width={28} height={22} className="logo-on-light h-[22px] w-auto" />
        {/* eslint-disable-next-line @next/next/no-img-element -- the dark-mode twin of the V above */}
        <img src="/brand/vezapp-v-deep.png" alt="" width={28} height={22} className="logo-on-dark h-[22px] w-auto" />
      </Link>
      {primary.map((item) => (
        <Link key={item.href} href={item.href} className="pill-link" data-active={isActive(item.href)} aria-current={isActive(item.href) && !item.children ? "page" : undefined}>
          {PILL_LABEL[item.href] ?? item.label}
        </Link>
      ))}
      {more.length > 0 && <MoreMenu items={more} active={more.some((i) => isActive(i.href))} />}
      <span aria-hidden="true" className="mx-1.5 h-6 w-px bg-[var(--pill-line)]" />
      <ThemeToggle variant="pill" />
      <PersonMenu />
    </nav>
  );
}

/**
 * Ask AI: a round button of its own, outside the pill, with its name in a small speech tag whose arrow
 * points at it. On narrow screens the tag is hidden and the name shows on hover.
 */
function AskAiButton({ note = false }: { note?: boolean }) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    if (!note) return;
    const onScroll = () => setScrolled(window.scrollY > 24);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [note]);

  return (
    <div className="relative">
      <Link href="/insights?tab=ask" aria-label="Ask the AI assistant" title={note ? undefined : "Ask AI"} className="ask-btn">
        <SparkleIcon className="h-5 w-5" />
      </Link>
      {note && (
        <span className="ask-note" aria-hidden="true" data-hidden={scrolled}>
          <svg viewBox="0 0 150 70" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
            <path d="M74 39C84 8 118 4 144 19" />
            <path d="M144 19 139.8 9.9M144 19 134 19.9" />
          </svg>
          <span>Ask AI</span>
        </span>
      )}
    </div>
  );
}

/** Vezapp Admin only: pick the client company every screen then works on. */
function CompanySwitcher({ full = false, compact = false }: { full?: boolean; compact?: boolean }) {
  const { actingCompanyId, chooseCompany } = useSession();
  const companies = useApi<Page<Company>>("/companies?page_size=500");
  const options = companies.data?.results.filter((c) => c.is_active) ?? [];

  return (
    <label className="flex items-center gap-2 text-sm">
      <span className={`text-ink-soft ${full ? "" : "hidden"} ${compact ? "" : "min-[1600px]:inline"}`}>Working on</span>
      <Select
        className={`field !min-h-10 !rounded-full ${full ? "min-w-0 flex-1" : compact ? "!w-[11.5rem]" : "!w-auto max-w-[16rem]"}`}
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

/** Width of one slot in the bottom bar (an item plus the gap), in pixels. Matches .bar-item in globals.css. */
const SLOT = 66;

/** A short name under each icon, so nobody has to guess what an icon is for. */
const BAR_LABEL: Record<string, string> = {
  "/scheduler": "Scheduler",
  "/machine-shop": "Shop",
  "/settings/data-health": "Health",
  "/settings/audit": "Audit",
};

/** The window width. A phone width is assumed until the browser says otherwise. */
function useWindowWidth() {
  return useSyncExternalStore(
    (notify) => {
      window.addEventListener("resize", notify);
      return () => window.removeEventListener("resize", notify);
    },
    () => window.innerWidth,
    () => 390,
  );
}

/**
 * Phones, tablets and small laptops: a floating bar at the bottom with just an icon per screen (the name is a
 * tooltip and the screen-reader label). The wider the screen, the more icons it shows; as it narrows, the last
 * ones move under More, which also holds the account and Sign out. The top bar keeps the logo, Ask AI and the
 * theme switch.
 */
function BottomBar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useSession();
  const role = user!.role;
  const { config } = usePlanningConfig();
  const width = useWindowWidth();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const moreButton = useRef<HTMLButtonElement>(null);
  const close = useCallback(() => setOpen(false), []);
  const all = navFor(role, config?.planned_operations);
  // How many items fit, leaving room for the More button and a margin on both sides. At least three.
  const slots = Math.floor((width - 52) / SLOT);
  const shown = Math.max(3, Math.min(all.length, slots - 1));
  const main = all.slice(0, shown);
  const more = all.slice(shown);
  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);
  const moreActive = more.some((i) => isActive(i.href));

  async function signOut() {
    setBusy(true);
    await logout();
    router.replace("/login");
  }

  return (
    <>
      <nav aria-label="Main" className="bottom-bar">
        {main.map((item) => (
          <Link key={item.href} href={item.href} aria-label={item.label} aria-current={isActive(item.href) ? "page" : undefined} data-active={isActive(item.href)} className="bar-item">
            <NavIcon href={item.href} className="" size={22} />
            <span className="bar-label" aria-hidden="true">{BAR_LABEL[item.href] ?? item.label}</span>
          </Link>
        ))}
        <button ref={moreButton} type="button" aria-label="More" aria-haspopup="dialog" aria-expanded={open} data-active={moreActive || open} className="bar-item" onClick={() => setOpen((o) => !o)}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <circle cx="5.5" cy="12" r="1.8" />
            <circle cx="12" cy="12" r="1.8" />
            <circle cx="18.5" cy="12" r="1.8" />
          </svg>
          <span className="bar-label" aria-hidden="true">More</span>
        </button>
      </nav>

      <Popover anchor={moreButton} open={open} onClose={close} label="More" matchWidth={false} className="w-72 p-2">
        {more.length > 0 && (
        <ul className="space-y-0.5">
          {more.map((item) => (
            <li key={item.href}>
              <Link href={item.href} onClick={close} aria-current={isActive(item.href) ? "page" : undefined} className="menu-item !min-h-12">
                <NavIcon href={item.href} className="text-ink-soft" />
                {item.label}
              </Link>
            </li>
          ))}
        </ul>
        )}
        {user && (
          <div className="mt-2 flex items-center gap-3 border-t border-line px-1 pt-3">
            <Avatar name={user.full_name} size={40} />
            <div className="min-w-0 flex-1 leading-tight">
              <p className="truncate text-sm font-semibold">{user.full_name}</p>
              <p className="truncate text-xs text-ink-soft">{ROLE_LABEL[user.role]}</p>
            </div>
            <button type="button" className="btn btn-quiet !min-h-10" onClick={signOut} disabled={busy}>
              {busy ? "Signing out…" : "Sign out"}
            </button>
          </div>
        )}
      </Popover>
    </>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const user = useSession((s) => s.user!);
  const { config } = usePlanningConfig();
  const company = user.company?.name ?? "";
  const section = navFor(user.role, config?.planned_operations).find((i) => i.children && (pathname === i.href || pathname.startsWith(`${i.href}/`)));

  return (
    <div className="canvas min-h-dvh">
      {/* Wide screens: the floating pill, with the company on the left and Ask AI on the right. */}
      <header className="float-head hidden px-8 pb-3 pt-4 xl:block">
        <div className="mx-auto flex max-w-[96rem] items-center gap-4">
          <div className="flex min-w-0 shrink-0 basis-[11.5rem] items-center">
            {user.role === "vezapp_admin" ? (
              <CompanySwitcher compact />
            ) : (
              <p className="flex min-w-0 items-center gap-2 truncate text-sm font-medium">
                <span aria-hidden="true" className="h-2 w-2 flex-none rounded-full bg-brand shadow-[0_0_8px_var(--brand)]" />
                <span className="truncate">{company}</span>
              </p>
            )}
          </div>
          <div className="mx-auto">
            <FloatingNav />
          </div>
          <div className="flex shrink-0 basis-[11.5rem] justify-end pr-12">
            <AskAiButton note />
          </div>
        </div>
      </header>

      {section && (
        <div className="px-4 pt-3 sm:px-6 xl:px-8">
          <nav aria-label={`${section.label} sections`} className="no-scrollbar mx-auto flex max-w-7xl gap-1.5 overflow-x-auto xl:flex-wrap xl:overflow-visible">
            {section.children!.map((child) => {
              const here = pathname === child.href || (child.href !== section.href && pathname.startsWith(`${child.href}/`));
              return (
                <Link key={child.href} href={child.href} aria-current={here ? "page" : undefined} className="subtab shrink-0 whitespace-nowrap max-md:min-h-10">
                  {child.label}
                </Link>
              );
            })}
          </nav>
        </div>
      )}

      {/* Narrower than a laptop: a slim top bar; the screens are on the bottom bar. */}
      <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-line bg-ground px-3 sm:gap-3 sm:px-5 xl:hidden">
        <Link href="/home" aria-label="Home" className="flex min-h-10 items-center">
          <Logo height={22} priority />
        </Link>
        {user.role === "vezapp_admin" ? (
          <div className="ml-1 hidden min-w-0 md:block">
            <CompanySwitcher full />
          </div>
        ) : (
          <p className="ml-1 hidden min-w-0 items-center gap-2 truncate text-sm font-medium md:flex">
            <span aria-hidden="true" className="h-2 w-2 flex-none rounded-full bg-brand shadow-[0_0_8px_var(--brand)]" />
            {company}
          </p>
        )}
        <div className="ml-auto flex items-center gap-2">
          <AskAiButton />
          <ThemeToggle />
        </div>
      </header>
      {user.role === "vezapp_admin" && (
        <div className="border-b border-line bg-ground px-3 py-2 md:hidden xl:hidden">
          <CompanySwitcher full />
        </div>
      )}

      <main className="min-w-0 px-4 py-7 max-xl:pb-28 sm:px-6 xl:px-8 xl:pb-8 xl:pt-14">
        <div className="rise mx-auto max-w-7xl">{children}</div>
      </main>

      <BottomBar />
    </div>
  );
}
