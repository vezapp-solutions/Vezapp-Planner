// Calendar maths for the date picker. Everything works on plain strings (YYYY-MM-DD, YYYY-MM,
// YYYY-MM-DDTHH:mm) so no time zone can shift a day.

export type PickerMode = "date" | "month" | "datetime";

export const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
] as const;
export const MONTH_SHORT = MONTH_NAMES.map((m) => m.slice(0, 3));
/** Weeks start on Monday, as on the plant's shift calendar. */
export const WEEKDAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"] as const;

export interface Parsed {
  y: number;
  m: number; // 1-12
  d: number;
  hh: number;
  mm: number;
}

export interface Cell {
  iso: string;
  day: number;
  inMonth: boolean;
}

export const pad = (n: number) => String(n).padStart(2, "0");

export function daysInMonth(y: number, m: number): number {
  return new Date(Date.UTC(y, m, 0)).getUTCDate();
}

export function toIso(y: number, m: number, d: number): string {
  return `${y}-${pad(m)}-${pad(d)}`;
}

/** Reads YYYY-MM-DD, YYYY-MM or YYYY-MM-DDTHH:mm. Returns null for anything else or an impossible date. */
export function parseValue(value: string): Parsed | null {
  const found = /^(\d{4})-(\d{2})(?:-(\d{2}))?(?:T(\d{2}):(\d{2}))?/.exec(value ?? "");
  if (!found) return null;
  const [y, m, d, hh, mm] = [found[1], found[2], found[3] ?? "1", found[4] ?? "0", found[5] ?? "0"].map(Number);
  if (m < 1 || m > 12 || d < 1 || d > daysInMonth(y, m) || hh > 23 || mm > 59) return null;
  return { y, m, d, hh, mm };
}

/** Today in India, as YYYY-MM-DD. */
export function todayIso(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}

export function addDays(iso: string, delta: number): string {
  const p = parseValue(iso)!;
  const next = new Date(Date.UTC(p.y, p.m - 1, p.d + delta));
  return toIso(next.getUTCFullYear(), next.getUTCMonth() + 1, next.getUTCDate());
}

export function addMonths(y: number, m: number, delta: number): { y: number; m: number } {
  const index = y * 12 + (m - 1) + delta;
  return { y: Math.floor(index / 12), m: (index % 12) + 1 };
}

/** The six weeks (42 days) shown for a month, starting on a Monday. */
export function monthGrid(y: number, m: number): Cell[] {
  const mondayIndex = (new Date(Date.UTC(y, m - 1, 1)).getUTCDay() + 6) % 7;
  const first = toIso(y, m, 1);
  const cells: Cell[] = [];
  for (let i = 0; i < 42; i++) {
    const iso = addDays(first, i - mondayIndex);
    const p = parseValue(iso)!;
    cells.push({ iso, day: p.d, inMonth: p.m === m && p.y === y });
  }
  return cells;
}

/** What the picker button shows: 30-10-2026, October 2026, or 30-10-2026 14:30. */
export function displayValue(value: string, mode: PickerMode): string {
  const p = parseValue(value);
  if (!p) return "";
  if (mode === "month") return `${MONTH_NAMES[p.m - 1]} ${p.y}`;
  const date = `${pad(p.d)}-${pad(p.m)}-${p.y}`;
  return mode === "datetime" ? `${date} ${pad(p.hh)}:${pad(p.mm)}` : date;
}
