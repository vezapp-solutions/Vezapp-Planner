export type Role = "vezapp_admin" | "company_admin" | "planner" | "viewer";

export const ROLE_LABEL: Record<Role, string> = {
  vezapp_admin: "Vezapp Admin",
  company_admin: "Company Admin",
  planner: "Planner",
  viewer: "Viewer",
};

export interface Me {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  full_name: string;
  email: string;
  role: Role;
  company: { id: number; name: string } | null;
}

export interface Page<T> {
  count: number;
  results: T[];
}

export interface Plant {
  id: number;
  name: string;
  address: string;
  is_active: boolean;
}

export interface Issue {
  level: "error" | "warning" | "info";
  field: string;
  message: string;
}

export interface Traced {
  value: number | null;
  formula: string;
  inputs: Record<string, number | string | null>;
  note: string;
}

export type ResourceKind = "core_machine" | "moulding_line" | "furnace" | "work_centre";

export const KIND_LABEL: Record<ResourceKind, string> = {
  core_machine: "Core machine",
  moulding_line: "Moulding line",
  furnace: "Furnace",
  work_centre: "Work centre",
};

export interface Shift {
  id: number;
  name: string;
  start_time: string;
  end_time: string;
  break_minutes: number;
  net_minutes: number;
  crosses_midnight: boolean;
}

export interface WeekDay {
  weekday: number;
  name: string;
  shift_ids: number[];
  minutes: number;
}

export interface Week {
  shifts: Shift[];
  days: WeekDay[];
  week_minutes: number;
}

export interface Holiday {
  id: number;
  date: string;
  name: string;
  full_day: boolean;
  shifts_off: number[];
}

export interface CompanySettings {
  horizon_days: number;
  default_bucket: "shift" | "day";
  rejection_booked_at: string;
  flow_mode: "progressive" | "whole_lot";
  pour_same_shift: boolean;
  melt_loss_default_pct: string;
}

export interface ResourceType {
  id: number;
  name: string;
  kind: ResourceKind;
  is_default: boolean;
}

export interface Resource {
  id: number;
  code: string;
  name: string;
  resource_type: number;
  type_name: string;
  kind: ResourceKind;
  plant: number | null;
  units: number;
  status: "active" | "inactive" | "maintenance";
  efficiency_pct: string;
  remarks: string;
  rate_per_hour: string | null;
  cycle_seconds: string | null;
  cores_per_shot: number | null;
  heat_kg: string | null;
  heat_minutes: string | null;
  max_heats_per_shift: number | null;
  shifts: number[];
  rated_summary: string;
  warnings: Issue[];
}

export interface Downtime {
  id: number;
  resource: number;
  start_at: string;
  end_at: string;
  reason: string;
}

export interface AvailabilityRow {
  date: string;
  shift_id: number;
  shift_name: string;
  shift_minutes: number;
  downtime_minutes: number;
  available_minutes: number;
  trace: Traced;
  heats?: Traced;
}

export interface Availability {
  shifts: AvailabilityRow[];
  days: { date: string; available_minutes: number }[];
  total_available_minutes: number;
}

export interface Customer {
  id: number;
  code: string;
  name: string;
  contact_person: string;
  phone: string;
  email: string;
  billing_address: string;
  shipping_address: string;
  gstin: string;
  state: string;
  priority: "A" | "B" | "C";
  is_active: boolean;
}

export interface Grade {
  id: number;
  name: string;
  description: string;
  part_count: number;
}

export interface Part {
  id: number;
  part_number: string;
  name: string;
  description: string;
  grade: number | null;
  grade_name: string | null;
  material_grade: string;
  drawing_number: string;
  drawing_revision: string;
  casting_weight_kg: string;
  finished_weight_kg: string | null;
  pouring_weight_per_mould_kg: string;
  cavities_per_mould: number;
  cores_per_mould: number;
  pattern_number: string;
  rejection_pct: string;
  selling_price: string | null;
  is_active: boolean;
  customers: { id: number; code: string; name: string; is_default: boolean }[];
  warnings: Issue[];
}

export interface OperationType {
  id: number;
  code: string;
  name: string;
  kind: "core" | "moulding" | "melting" | "post";
  default_sequence: number;
  default_enabled: boolean;
  default_bucket: "shift" | "day";
  is_active: boolean;
  is_builtin: boolean;
  multi_step: boolean;
}

export interface RouteOp {
  id: number | null;
  op_type: number;
  code: string;
  name: string;
  kind: OperationType["kind"];
  sequence: number;
  enabled: boolean;
  time_value: number | null;
  time_basis: string;
  batch_size: number | null;
  capacity_bucket: "" | "shift" | "day";
  lag_hours: number;
  outsourced: boolean;
  lead_days: number | null;
  extra: Record<string, number>;
  resource_ids: number[];
  resource_kind: ResourceKind;
  allowed_time_bases: string[];
  /** The operation type's code; `code` is unique per step (`machining~20`). */
  type_code: string;
  multi_step: boolean;
  step: number;
  label: string;
  setup_minutes: number;
  /** Machine types whose machines may run this step, machines marked unsuitable, and minutes per piece by type id. */
  machine_types: number[];
  except_ids: number[];
  time_by_type: Record<string, number>;
  effective_resource_ids: number[];
  derived: Record<string, Traced | { code: string; value: number | null; formula: string }[]>;
  issues: Issue[];
  capacity_modelled: boolean;
}

export interface Route {
  part: number;
  is_template: boolean;
  operations: RouteOp[];
}

export interface AuditEntry {
  id: number;
  username: string;
  action: "create" | "update" | "delete";
  model_label: string;
  object_pk: string;
  object_repr: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  created_at: string;
}

export type LineStatus = "planned" | "in_progress" | "dispatched" | "cancelled";

export const LINE_STATUS_LABEL: Record<LineStatus, string> = {
  planned: "Planned",
  in_progress: "In progress",
  dispatched: "Dispatched",
  cancelled: "Cancelled",
};

export interface ScheduleLine {
  id: number;
  customer: number;
  customer_code: string;
  customer_name: string;
  part: number;
  part_number: string;
  part_name: string;
  grade_name: string | null;
  dispatch_qty: number;
  internal_dispatch_date: string;
  actual_dispatch_date: string | null;
  actual_dispatched_qty: number | null;
  remarks: string;
  status: LineStatus;
  month: string;
  tonnes: number;
  value: number | null;
  warnings: string[];
}

export interface ScheduleSummary {
  lines: number;
  pieces: number;
  tonnes: number;
  value: number | null;
  lines_without_price: number;
}

export interface UploadMessage {
  level: "error" | "warning";
  field: string;
  text: string;
}

export interface UploadRow {
  row: number;
  status: "ok" | "warning" | "error";
  action: "insert" | "update" | "skip" | "unchanged" | "error";
  messages: UploadMessage[];
  raw: Record<string, string>;
}

export interface UploadPreview {
  file_name: string;
  mode: "insert" | "upsert";
  summary: {
    total: number;
    ok: number;
    warning: number;
    error: number;
    insert: number;
    update: number;
    skip: number;
    unchanged: number;
  };
  rows: UploadRow[];
}

export interface UploadBatch {
  id: number;
  file_name: string;
  mode: "insert" | "upsert";
  username: string;
  created_at: string;
  rows_total: number;
  rows_inserted: number;
  rows_updated: number;
  rows_unchanged: number;
  rows_skipped: number;
  rows_error: number;
  rows_warning: number;
  skipped_errors: boolean;
}

export type PlanLineStatus = "on_track" | "tight" | "at_risk" | "unscheduled";

export const PLAN_STATUS_LABEL: Record<PlanLineStatus, string> = {
  on_track: "On track",
  tight: "Tight",
  at_risk: "At risk",
  unscheduled: "Not scheduled",
};

export interface Plan {
  id: number;
  version: number;
  status: "draft" | "confirmed";
  plan_from: string;
  calculated_at: string | null;
  confirmed_at: string | null;
  summary: {
    lines?: number;
    by_status?: Partial<Record<PlanLineStatus, number>>;
    runtime_ms?: number;
  };
  bottleneck: { id: number; code: string; name: string } | null;
  stale: boolean;
  stale_reasons: string[];
  created_by_name: string | null;
}

export interface PlanLine {
  id: number;
  schedule_line: number | null;
  customer_code: string;
  customer_name: string;
  part_number: string;
  part_name: string;
  qty: number;
  internal_date: string;
  priority: string;
  status: PlanLineStatus;
  est_dispatch_date: string | null;
  slack_working_days: number | null;
  holding_op: string;
  holding_text: string;
  notes: string[];
}

export interface PlanOperationRow {
  code: string;
  name: string;
  kind: string;
  sequence: number;
  minutes: number;
  units: number;
  ready_at: string | null;
  start_at: string | null;
  finish_at: string | null;
  latest_start: string | null;
  latest_finish: string | null;
  delay_days: number | null;
  wait_hours: number | null;
  capacity_modelled: boolean;
  outsourced: boolean;
  complete: boolean;
  resource_codes: string;
}

export interface PlanLineDetail extends PlanLine {
  finish_at: string | null;
  requirement: {
    pieces_to_pour?: number;
    moulds?: number;
    cores?: number;
    metal_kg?: number;
    minutes?: Record<string, number>;
    traces?: Record<string, Traced>;
  };
  operations: PlanOperationRow[];
  allocations: {
    op_code: string;
    resource: string | null;
    date: string;
    shift: string;
    start: string;
    end: string;
    minutes: number;
    qty: number;
  }[];
}

export interface LoadCellData {
  load: number;
  capacity: number;
  required: number;
  utilisation: number | null;
}

export interface LoadGrid {
  columns: { key: string; date: string; shift: string | null }[];
  resources: { id: number; code: string; name: string; kind: ResourceKind; cells: Record<string, LoadCellData> }[];
}

export interface BottleneckDay {
  date: string;
  resource_id: number | null;
  resource_code: string | null;
  utilisation: number;
  load: number;
  capacity: number;
}

export interface DayView {
  date: string;
  resources: { id: number; code: string; load: number; capacity: number; utilisation: number | null }[];
  work: { op_code: string; name: string; lines: number; minutes: number; qty: number }[];
}

export interface GanttBar {
  row: number;
  row_label: string;
  status: PlanLineStatus;
  start: string;
  end: string;
  code: string;
  label?: string;
  name?: string;
  line?: number;
  slot?: number;
  slot_capacity?: number | null;
  minutes?: number;
  due?: string;
}

export interface Company {
  id: number;
  name: string;
  address: string;
  gstin: string;
  is_active: boolean;
  created_at: string;
}

export interface AppUser {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
  role: Role;
  company: number | null;
  company_name: string | null;
  is_active: boolean;
}

// --- Machine shop --------------------------------------------------------------------------------------
export interface MachineDay {
  capacity: number;
  load: number;
  setup: number;
  free: number;
  utilisation: number | null;
}

export interface MachineOperation {
  line_id: number;
  part_number: string;
  customer_code: string;
  op_code: string;
  name: string;
  pieces: number;
  minutes: number;
  setup_minutes: number;
}

export interface Machine {
  id: number;
  code: string;
  name: string;
  status: "active" | "inactive" | "maintenance";
  units: number;
  efficiency_pct: number;
  days: Record<string, MachineDay>;
  capacity: number;
  load: number;
  setup: number;
  free: number;
  utilisation: number | null;
  downtime: { start: string; end: string; reason: string }[];
  operations: MachineOperation[];
}

export interface MachineType {
  id: number;
  name: string;
  machines: Machine[];
  capacity: number;
  load: number;
  free: number;
  utilisation: number | null;
}

export interface MachineShop {
  plan: { id: number; version: number; status: string } | null;
  from: string;
  to: string;
  days: string[];
  types: MachineType[];
  operations: {
    line_id: number;
    part_number: string;
    customer_code: string;
    qty: number;
    status: PlanLineStatus;
    op_code: string;
    name: string;
    machines: string;
    start_at: string | null;
    finish_at: string | null;
    minutes: number;
    complete: boolean;
  }[];
}

// --- What-if ------------------------------------------------------------------------------------------
export type ChangeKind = "block_resource" | "change_qty" | "change_date" | "extra_shift" | "overtime";

export const CHANGE_KIND_LABEL: Record<ChangeKind, string> = {
  block_resource: "Block a resource",
  change_qty: "Change a quantity",
  change_date: "Change a date",
  extra_shift: "Add an extra shift",
  overtime: "Add overtime",
};

export interface ScenarioChange {
  id: number;
  kind: ChangeKind;
  params: Record<string, unknown>;
  text: string;
}

export type ScenarioState = "never_run" | "fresh" | "changes_edited" | "data_changed";
export type DiffTag = "later" | "earlier" | "newly_at_risk" | "recovered" | "changed";

export interface DiffCounts {
  later: number;
  earlier: number;
  newly_at_risk: number;
  recovered: number;
  changed: number;
  total: number;
}

export interface LineDiff {
  line_id: number;
  part_number: string;
  part_name: string;
  customer_code: string;
  customer_name: string;
  status_before: PlanLineStatus;
  status_after: PlanLineStatus;
  est_before: string | null;
  est_after: string | null;
  slack_before: number | null;
  slack_after: number | null;
  moved_working_days: number | null;
  holding_after: string | null;
  holding_text_after: string;
  tags: DiffTag[];
  internal_date_before: string;
  internal_date_after: string;
  qty_before: number;
  qty_after: number;
}

export interface ScenarioResult {
  plan_from: string;
  lines_planned: number;
  runtime_ms: number;
  resources: Record<string, { code: string }>;
  diff: {
    lines: LineDiff[];
    counts: DiffCounts;
    status_before: Partial<Record<PlanLineStatus, number>>;
    status_after: Partial<Record<PlanLineStatus, number>>;
    bottleneck_before: number | null;
    bottleneck_after: number | null;
    day_bottlenecks: { date: string; before: number | null; after: number | null }[];
    peak_utilisation: Record<string, [number, number]>;
  };
}

export interface Scenario {
  id: number;
  name: string;
  notes: string;
  status: "draft" | "applied";
  state: ScenarioState;
  created_by_name: string | null;
  created_at: string;
  last_run_at: string | null;
  applied_at: string | null;
  applied_by_name: string | null;
  change_count: number;
  headline: DiffCounts | null;
}

export interface AppliedSummary {
  downtimes: number;
  line_edits: number;
  adjustments: number;
  plan: { id: number; version: number; new: boolean } | null;
}

export interface ScenarioDetail extends Scenario {
  changes: ScenarioChange[];
  result: ScenarioResult | null;
  applied_summary?: AppliedSummary;
}

// --- Insights, reports, assistant ---------------------------------------------------------------------
export type Severity = "critical" | "warning" | "info";
export type Trend = "new" | "worse" | "better" | "same";

export type InsightType =
  | "at_risk"
  | "bottleneck_forecast"
  | "capacity_gap"
  | "melting"
  | "load_balancing"
  | "dispatch_performance"
  | "month_forecast"
  | "concentration"
  | "data_health";

export interface Insight {
  id: number;
  key: string;
  type: InsightType;
  severity: Severity;
  title: string;
  message: string;
  numbers: Record<string, unknown>;
  entities: Record<string, unknown>;
  action: string;
  why: string[];
  impact: number;
  rank: number;
  trend: Trend;
}

export interface InsightRun {
  id: number;
  created_at: string;
  trigger: "plan" | "manual" | "actuals";
  counts: { total?: number; by_severity?: Partial<Record<Severity, number>>; by_type?: Record<string, number>; resolved?: number };
  plan: number | null;
  plan_version: number | null;
  plan_status: string | null;
}

export interface InsightList {
  run: InsightRun | null;
  count: number;
  results: Insight[];
}

export interface Digest {
  title: string;
  date: string;
  text: string;
  items: { severity: Severity; title: string; message: string; action: string; key: string }[];
}

export interface HealthItem {
  kind: string;
  subject: string;
  detail: string;
  why: string;
  severity: "error" | "warning" | "info";
  link: string;
  lines_affected: number;
}

export interface DataHealth {
  count: number;
  items: HealthItem[];
}

export interface PerfGroup {
  group: string;
  name?: string;
  lines: number;
  pieces: number;
  on_time: number;
  late: number;
  on_time_pct: number;
  avg_delay_days: number;
  max_delay_days: number;
}

export interface DispatchPerformance {
  overall: PerfGroup | null;
  by_customer: PerfGroup[];
  by_part: PerfGroup[];
  by_month: PerfGroup[];
}

export interface UtilisationReport {
  plan: { id: number; version: number } | null;
  from: string | null;
  to: string | null;
  resources: {
    id: number;
    code: string;
    name: string;
    kind: ResourceKind;
    load: number;
    capacity: number;
    utilisation: number | null;
    peak_utilisation: number | null;
    peak_date: string | null;
    weeks: { week_start: string; load: number; capacity: number; utilisation: number | null }[];
  }[];
}

export interface PlanVsActualRow {
  line_id: number;
  customer_code: string;
  customer_name: string;
  part_number: string;
  qty: number;
  internal_date: string;
  est_date: string | null;
  actual_date: string;
  plan_version: number | null;
  est_error_days: number | null;
  delay_days: number;
}

export interface PlanVsActual {
  summary: {
    lines: number;
    with_confirmed_plan: number;
    without_confirmed_plan: number;
    mean_abs_error_days: number | null;
    within_one_day: number | null;
    estimated_on_time_actual_late: number;
    estimated_late_actual_on_time: number;
  };
  lines: PlanVsActualRow[];
}

export interface AssistantStatus {
  mode: "basic" | "ai";
  notice: string | null;
  disclaimer: string;
  max_question_chars: number;
  starters: string[];
}

export interface AssistantReply {
  answer: string;
  mode: "basic" | "ai";
  notes: string[];
  disclaimer: string;
  tools: string[];
  intent: string | null;
  conversation: string;
  follow_ups: string[];
}

export interface CapacityAdjustment {
  id: number;
  kind: "extra_shift" | "overtime";
  day_from: string;
  day_to: string;
  name: string;
  start_time: string | null;
  end_time: string | null;
  break_minutes: number;
  shift: number | null;
  minutes: number | null;
  resources: number[];
  note: string;
  summary: string;
}
