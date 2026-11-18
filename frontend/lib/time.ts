/** Time of day as the API and the forms hold it: "HH:mm", 24-hour ("06:00", "14:30", "00:00"). */

export interface ClockTime {
  /** 0 to 23 */
  hour: number;
  /** 0 to 59 */
  minute: number;
}

const pad = (n: number) => String(n).padStart(2, "0");

/** Reads "HH:mm" (a trailing ":ss" is ignored). Returns null for anything else or an impossible time. */
export function parseTime(value: string | null | undefined): ClockTime | null {
  const found = /^(\d{1,2}):(\d{2})(?::\d{2})?$/.exec((value ?? "").trim());
  if (!found) return null;
  const hour = Number(found[1]);
  const minute = Number(found[2]);
  return hour > 23 || minute > 59 ? null : { hour, minute };
}

export function toTime({ hour, minute }: ClockTime): string {
  return `${pad(hour)}:${pad(minute)}`;
}

/** 0..23 becomes 1..12 and whether it is PM. Midnight is 12 AM and noon is 12 PM. */
export function to12Hour(hour: number): { hour12: number; pm: boolean } {
  return { hour12: hour % 12 === 0 ? 12 : hour % 12, pm: hour >= 12 };
}

/** The reverse of to12Hour. */
export function from12Hour(hour12: number, pm: boolean): number {
  return (hour12 % 12) + (pm ? 12 : 0);
}

/** "06:00 AM", "02:30 PM", "12:00 AM" for midnight. */
export function formatTime12(value: string | null | undefined): string {
  const t = parseTime(value);
  if (!t) return "";
  const { hour12, pm } = to12Hour(t.hour);
  return `${pad(hour12)}:${pad(t.minute)} ${pm ? "PM" : "AM"}`;
}

/** Minutes in steps of five, plus the current one when it is not on the grid (a value saved as 07:23). */
export function minuteChoices(current: number | null): number[] {
  const steps = Array.from({ length: 12 }, (_, i) => i * 5);
  if (current !== null && !steps.includes(current)) steps.push(current);
  return steps.sort((a, b) => a - b);
}
