import { formatDate, formatDateTime } from "./format";
import type { AuditEntry } from "./types";

/** What the audit log says about one change, in plain English. */
export interface AuditSummary {
  headline: string;
  lines: string[];
}

const NOUN: Record<string, string> = {
  "masters.Part": "part",
  "masters.PartOperation": "route step",
  "masters.PartCustomer": "part-customer link",
  "masters.Customer": "customer",
  "masters.Grade": "grade",
  "masters.OperationType": "operation",
  "resources.Resource": "machine",
  "resources.ResourceType": "machine type",
  "resources.Downtime": "downtime",
  "companies.Shift": "shift",
  "companies.WeekdayShift": "weekly shift",
  "companies.Holiday": "holiday",
  "companies.CompanySettings": "planning settings",
  "companies.Plant": "plant",
  "companies.Company": "company",
  "accounts.User": "user",
  "plans.Plan": "plan",
  "scenarios.Scenario": "what-if scenario",
  "scheduler.ScheduleLine": "order",
};

const PAST = { create: "Added", update: "Changed", delete: "Deleted" } as const;

/** Wording for fields whose plain name is not obvious from the code name. */
const LABEL: Record<string, string> = {
  dispatch_qty: "Order quantity",
  internal_dispatch_date: "Internal dispatch date",
  actual_dispatch_date: "Actual dispatch date",
  actual_dispatched_qty: "Dispatched quantity",
  wip_qty: "WIP stock",
  fg_qty: "FG stock",
  time_value: "Time",
  time_basis: "Time basis",
  setup_minutes: "Setup minutes",
  lag_hours: "Wait after the step (hours)",
  extra: "Operation settings",
  op_type_id: "Operation",
  resource_type_id: "Machine type",
  casting_weight_kg: "Casting weight (kg)",
  finished_weight_kg: "Finished weight (kg)",
  pouring_weight_per_mould_kg: "Pouring weight per mould (kg)",
  cavities_per_mould: "Castings per mould",
  rejection_pct: "Rejection %",
  efficiency_pct: "Efficiency %",
  rate_per_hour: "Rate per hour",
  heat_kg: "Heat size (kg)",
  heat_minutes: "Heat time (minutes)",
  max_heats_per_shift: "Maximum heats per shift",
  is_default: "Default",
  is_active: "Active",
  plan_from: "Plan start date",
  post_pour_days: "Days needed after pouring",
  max_lead_days: "Start no earlier than (days)",
};

/** Fields that are bookkeeping, not something a person changed. */
const NOISE = new Set([
  "id",
  "created_at",
  "updated_at",
  "company_id",
  "created_by_id",
  "applied_by_id",
  "upload_batch_id",
  "input_fingerprint",
  "run_fingerprint",
  "run_signature",
  "settings_snapshot",
  "summary",
  "result",
  "last_run_at",
  "calculated_at",
  "bottleneck_resource_id",
  "date_joined",
  "is_superuser",
  "is_staff",
  "password",
]);

const WORD: Record<string, string> = { qty: "quantity", pct: "%", wip: "WIP", fg: "FG", id: "ID", kg: "kg", ok: "OK" };

function humanize(key: string): string {
  if (LABEL[key]) return LABEL[key];
  const words = key
    .replace(/_id$/, "")
    .split("_")
    .map((w) => WORD[w] ?? w);
  const text = words.join(" ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

type Refs = AuditEntry["refs"];

const isEmpty = (v: unknown) => v === null || v === undefined || v === "" || (Array.isArray(v) && v.length === 0);
const isObject = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);

function formatValue(key: string, value: unknown, refs: Refs): string {
  if (isEmpty(value)) return "empty";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (key.endsWith("_id") && typeof value === "number") return refs?.[key]?.[String(value)] ?? `record #${value}`;
  if (typeof value === "number") return String(value);
  if (typeof value === "string") {
    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return formatDate(value);
    if (/^\d{4}-\d{2}-\d{2}T/.test(value)) return formatDateTime(value);
    if (/^-?\d+\.\d+$/.test(value)) return String(Number(value));
    if (/^[a-z]+(_[a-z]+)+$/.test(value)) return value.replace(/_/g, " ");
    return value;
  }
  if (Array.isArray(value)) return value.every((v) => typeof v !== "object") ? value.join(", ") : `${value.length} items`;
  return "set";
}

function sameValue(key: string, a: unknown, b: unknown, refs: Refs): boolean {
  if (isObject(a) || isObject(b)) return JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
  return formatValue(key, a, refs) === formatValue(key, b, refs);
}

function nameOf(entry: AuditEntry): string {
  const snapshot = entry.after ?? entry.before ?? {};
  // "PartOperation object (109)" is Django's placeholder for a record with no name: not worth showing.
  const repr = /^\w+ object \(\d+\)$/.test(entry.object_repr || "") ? "" : (entry.object_repr || "").trim();
  if (repr) return repr;
  if (typeof snapshot.label === "string" && snapshot.label) return `“${snapshot.label}”`;
  return "";
}

function updateLines(entry: AuditEntry): string[] {
  const before = entry.before ?? {};
  const after = entry.after ?? {};
  const refs = entry.refs;
  const lines: string[] = [];
  const keys = [...new Set([...Object.keys(before), ...Object.keys(after)])];

  // A plan or a what-if scenario is mostly large internal results; say what happened instead.
  if (entry.model_label === "plans.Plan") {
    if (before.status !== after.status && after.status === "confirmed") lines.push("Confirmed the plan as the baseline.");
    if (JSON.stringify(before.summary) !== JSON.stringify(after.summary) || before.calculated_at !== after.calculated_at) lines.push("Recalculated the plan.");
  }
  if (entry.model_label === "scenarios.Scenario") {
    if (before.status !== after.status && after.status === "applied") lines.push("Applied the scenario to the real data.");
    else if (JSON.stringify(before.result) !== JSON.stringify(after.result)) lines.push("Ran the scenario.");
  }

  for (const key of keys) {
    if (NOISE.has(key)) continue;
    if (entry.model_label === "plans.Plan" && key === "status" && after.status === "confirmed") continue;
    if (entry.model_label === "scenarios.Scenario" && key === "status" && after.status === "applied") continue;
    const was = before[key];
    const now = after[key];
    if (sameValue(key, was, now, refs)) continue;
    const label = humanize(key);
    if (isObject(was) || isObject(now)) lines.push(`${label} changed.`);
    else if (isEmpty(was)) lines.push(`${label} set to ${formatValue(key, now, refs)}.`);
    else if (isEmpty(now)) lines.push(`${label} cleared (it was ${formatValue(key, was, refs)}).`);
    else lines.push(`${label} changed from ${formatValue(key, was, refs)} to ${formatValue(key, now, refs)}.`);
  }
  return lines.length ? lines : ["Saved, with no visible change."];
}

function factsLine(entry: AuditEntry): string[] {
  const snapshot = entry.after ?? entry.before ?? {};
  const refs = entry.refs;
  const facts: string[] = [];
  for (const [key, value] of Object.entries(snapshot)) {
    if (NOISE.has(key) || isEmpty(value) || value === false || value === 0 || value === "0" || isObject(value)) continue;
    facts.push(`${humanize(key)}: ${formatValue(key, value, refs)}`);
    if (facts.length === 6) break;
  }
  return facts.length ? [facts.join(" · ")] : [];
}

/** One plain-English description of an audit record: a headline, then what changed. */
export function describeAudit(entry: AuditEntry): AuditSummary {
  const noun = NOUN[entry.model_label] ?? humanize(entry.model_label.split(".")[1] ?? "record").toLowerCase();
  const name = nameOf(entry);
  const startsWithNoun = name.toLowerCase().startsWith(noun.toLowerCase());
  const headline = `${PAST[entry.action]} ${startsWithNoun ? "" : `${noun} `}${name}`.trim();
  const lines = entry.action === "update" ? updateLines(entry) : factsLine(entry);
  return { headline, lines };
}
