import { formatDate } from "./format";
import type { ChangeKind, DiffCounts, DiffTag, LineDiff, ScenarioResult, ScenarioState } from "./types";

export const TAG_LABEL: Record<DiffTag, string> = {
  newly_at_risk: "Newly at risk",
  later: "Moves later",
  recovered: "Recovered",
  earlier: "Moves earlier",
  changed: "Other change",
};

/** Order the groups are shown in: bad news first. */
export const TAG_ORDER: DiffTag[] = ["newly_at_risk", "later", "recovered", "earlier", "changed"];

export function groupLines(lines: LineDiff[]): { tag: DiffTag; label: string; lines: LineDiff[] }[] {
  return TAG_ORDER.map((tag) => ({ tag, label: TAG_LABEL[tag], lines: lines.filter((l) => l.tags[0] === tag) })).filter((g) => g.lines.length > 0);
}

/** "5 working days later", "1 working day earlier", or null when the date did not move. */
export function movedText(days: number | null): string | null {
  if (days == null || days === 0) return null;
  const n = Math.abs(days);
  return `${n} working day${n === 1 ? "" : "s"} ${days > 0 ? "later" : "earlier"}`;
}

/** The estimated date as "05-11-2026 → 06-11-2026", with a dash for a line that is not scheduled. */
export function dateChange(line: Pick<LineDiff, "est_before" | "est_after">): string {
  const side = (d: string | null) => (d ? formatDate(d) : "–");
  return `${side(line.est_before)} → ${side(line.est_after)}`;
}

export function headline(counts: DiffCounts): string {
  if (counts.total === 0) return "No line changes.";
  const parts: string[] = [];
  if (counts.later) parts.push(`${counts.later} later`);
  if (counts.earlier) parts.push(`${counts.earlier} earlier`);
  if (counts.newly_at_risk) parts.push(`${counts.newly_at_risk} newly at risk`);
  if (counts.recovered) parts.push(`${counts.recovered} recovered`);
  if (counts.changed) parts.push(`${counts.changed} otherwise changed`);
  return `${counts.total} line${counts.total === 1 ? "" : "s"} change: ${parts.join(", ")}.`;
}

export const STATE_TEXT: Record<ScenarioState, string | null> = {
  never_run: "Not run yet. Run it to see what the changes do.",
  fresh: null,
  changes_edited: "The changes were edited after the last run. Run it again to refresh the result.",
  data_changed: "The schedule or masters changed after the last run. Run it again before applying.",
};

/** Resources whose busiest-shift utilisation moves, biggest change first. Unchanged ones are left out. */
export function utilisationChanges(result: ScenarioResult): { id: number; code: string; before: number; after: number }[] {
  return Object.entries(result.diff.peak_utilisation)
    .map(([id, [before, after]]) => ({ id: Number(id), code: result.resources[id]?.code ?? `#${id}`, before, after }))
    .filter((r) => Math.abs(r.after - r.before) >= 0.005)
    .sort((a, b) => Math.abs(b.after - b.before) - Math.abs(a.after - a.before) || a.code.localeCompare(b.code));
}

export function bottleneckText(result: ScenarioResult): string {
  const { bottleneck_before: b, bottleneck_after: a } = result.diff;
  const name = (id: number | null) => (id == null ? "none" : (result.resources[String(id)]?.code ?? `#${id}`));
  return b === a ? `Unchanged (${name(a)})` : `${name(b)} → ${name(a)}`;
}

/** What Apply will really create or edit for each kind of change, for the confirmation. */
export const EFFECT: Record<ChangeKind, string> = {
  block_resource: "Adds a blocked period to the resource, so every plan loses that capacity.",
  change_qty: "Edits the quantity on the Monthly Scheduler line.",
  change_date: "Edits the internal dispatch date on the Monthly Scheduler line.",
  extra_shift: "Adds an extra shift to Company calendar, so every plan can use it.",
  overtime: "Adds overtime to Company calendar, so every plan gets the extra minutes.",
};
