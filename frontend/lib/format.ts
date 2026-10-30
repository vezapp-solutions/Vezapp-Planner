// Indian-context formatting: DD-MM-YYYY, Asia/Kolkata, 1,00,000 grouping, kg and tonnes.
const TZ = "Asia/Kolkata";

type DateInput = Date | string | number;

function toDate(value: DateInput): Date {
  // A bare YYYY-MM-DD is a calendar date, not an instant: read it as that day in India.
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return new Date(`${value}T00:00:00+05:30`);
  }
  return value instanceof Date ? value : new Date(value);
}

function parts(value: DateInput, options: Intl.DateTimeFormatOptions) {
  const out: Record<string, string> = {};
  for (const p of new Intl.DateTimeFormat("en-IN", { timeZone: TZ, ...options }).formatToParts(
    toDate(value),
  )) {
    out[p.type] = p.value;
  }
  return out;
}

export function formatDate(value: DateInput): string {
  const p = parts(value, { day: "2-digit", month: "2-digit", year: "numeric" });
  return `${p.day}-${p.month}-${p.year}`;
}

export function formatDayMonth(value: DateInput): string {
  const p = parts(value, { day: "2-digit", month: "2-digit" });
  return `${p.day}-${p.month}`;
}

export function formatWeekday(value: DateInput, style: "long" | "short" = "long"): string {
  return parts(value, { weekday: style }).weekday;
}

export function formatDateTime(value: DateInput): string {
  const p = parts(value, { hour: "2-digit", minute: "2-digit", hour12: false });
  return `${formatDate(value)} ${p.hour}:${p.minute}`;
}

export function formatNumber(value: number, maximumFractionDigits = 0): string {
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits }).format(value);
}

export function formatKg(kg: number): string {
  return `${formatNumber(kg, 1)} kg`;
}

export function formatTonnes(kg: number): string {
  return `${formatNumber(kg / 1000, 2)} t`;
}

/** Weights: kg below one tonne, tonnes from one tonne up. */
export function formatWeight(kg: number): string {
  return Math.abs(kg) >= 1000 ? formatTonnes(kg) : formatKg(kg);
}

/** Today in India as YYYY-MM-DD, independent of the browser's own timezone. */
export function todayInIndia(now: Date = new Date()): string {
  const p = parts(now, { year: "numeric", month: "2-digit", day: "2-digit" });
  return `${p.year}-${p.month}-${p.day}`;
}

export function addDays(isoDate: string, days: number): string {
  const d = toDate(isoDate);
  d.setUTCDate(d.getUTCDate() + days);
  return todayInIndia(d);
}
