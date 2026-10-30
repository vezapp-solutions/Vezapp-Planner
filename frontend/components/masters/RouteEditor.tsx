"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { Explain, Issues } from "@/components/Explain";
import { FormError } from "@/components/forms";
import { MachineChoice } from "@/components/masters/MachineChoice";
import { ApiError, post, put } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import { nextStep, opTitle } from "@/lib/machining";
import type { Part, Resource, ResourceType, Route, RouteOp, Traced } from "@/lib/types";
import { Select } from "@/components/ui/Select";

const BASIS_LABEL: Record<string, string> = {
  per_core: "Minutes per core",
  per_mould: "Minutes per mould",
  per_heat: "Minutes per heat",
  per_piece: "Minutes per piece",
  per_batch: "Minutes per batch",
  fixed_per_shift: "Fixed minutes per shift",
  fixed_per_day: "Fixed minutes per day",
};

const trace = (op: RouteOp, key: string) => op.derived?.[key] as Traced | undefined;

/** A number box that lets you type "1." or clear it without the value jumping around. */
function NumField({
  id,
  label,
  value,
  onChange,
  unit,
  hint,
  placeholder,
  error,
  disabled,
  step = "any",
  integer = false,
}: {
  id: string;
  label: string;
  value: number | null | undefined;
  onChange: (v: number | null) => void;
  unit?: string;
  hint?: ReactNode;
  placeholder?: string;
  error?: string;
  disabled?: boolean;
  step?: string;
  integer?: boolean;
}) {
  // While typing, the box keeps its own text ("1." or empty). Otherwise it mirrors the value.
  const [typed, setTyped] = useState<string | null>(null);
  const text = typed ?? (value == null ? "" : String(value));
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium">{label}</label>
      <div className="relative">
        <input
          id={id}
          type="number"
          inputMode={integer ? "numeric" : "decimal"}
          step={step}
          min={0}
          disabled={disabled}
          className={`field font-mono ${unit ? "!pr-14" : ""}`}
          value={text}
          placeholder={placeholder}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-err` : undefined}
          onFocus={() => setTyped(value == null ? "" : String(value))}
          onBlur={() => setTyped(null)}
          onChange={(e) => {
            setTyped(e.target.value);
            onChange(e.target.value === "" ? null : Number(e.target.value));
          }}
        />
        {unit && <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-ink-soft">{unit}</span>}
      </div>
      {hint && !error && <p className="mt-1 text-xs text-ink-soft">{hint}</p>}
      {error && <p id={`${id}-err`} className="mt-1 text-sm text-danger">{error}</p>}
    </div>
  );
}

function ResourcePicker({ id, label, options, chosen, onChange, disabled, hint }: { id: string; label: string; options: Resource[]; chosen: number[]; onChange: (ids: number[]) => void; disabled: boolean; hint?: string }) {
  return (
    <fieldset className="sm:col-span-2" disabled={disabled}>
      <legend className="mb-1 text-sm font-medium">{label}</legend>
      <div className="flex flex-wrap gap-2">
        {options.length === 0 && <span className="text-sm text-ink-soft">None set up yet. Add them under Resources.</span>}
        {options.map((r) => {
          const on = chosen.includes(r.id);
          return (
            <label key={r.id} className={`flex min-h-9 cursor-pointer items-center gap-2 rounded-sm border px-2.5 text-sm ${on ? "border-action bg-brand-wash" : "border-line"}`}>
              <input id={`${id}-${r.id}`} type="checkbox" className="size-4 accent-[var(--action)]" checked={on} onChange={() => onChange(on ? chosen.filter((c) => c !== r.id) : [...chosen, r.id])} />
              <span className="font-mono text-xs">{r.code}</span> {r.name}
              <span className="text-xs text-ink-soft">{r.rated_summary}</span>
            </label>
          );
        })}
      </div>
      {hint && <p className="mt-1 text-xs text-ink-soft">{hint}</p>}
    </fieldset>
  );
}

function summary(op: RouteOp): string {
  const d = (k: string) => trace(op, k)?.value;
  const n = (v: number | null | undefined, unit: string) => (v == null ? null : `${formatNumber(v, 3)} ${unit}`);
  const parts: (string | null)[] = [];
  if (op.kind === "core") parts.push(n(d("minutes_per_core"), "min/core"), n(d("cores_per_mould"), "cores/mould"));
  if (op.kind === "moulding") parts.push(n(d("minutes_per_mould"), "min/mould"));
  if (op.kind === "melting") parts.push(n(op.extra.moulds_per_heat ?? d("suggested_moulds_per_heat"), "moulds/heat"), n(d("minutes_per_piece"), "min/piece"));
  if (op.kind === "post") {
    if (op.outsourced) parts.push(op.lead_days ? `outsourced, ${op.lead_days} days` : "outsourced");
    else if (op.time_value != null) parts.push(`${formatNumber(op.time_value, 3)} min ${op.time_basis.replace("_", " ").replace("fixed per", "fixed per")}`);
  }
  return parts.filter(Boolean).join(" · ");
}

function OpCard({
  op,
  index,
  count,
  part,
  resources,
  machineTypes,
  errors,
  canEdit,
  open,
  canRemove,
  onToggleOpen,
  onChange,
  onMove,
  onRemove,
}: {
  op: RouteOp;
  index: number;
  count: number;
  part: Part;
  resources: Resource[];
  machineTypes: ResourceType[];
  errors: Record<string, string>;
  canEdit: boolean;
  open: boolean;
  canRemove: boolean;
  onToggleOpen: () => void;
  onChange: (next: RouteOp) => void;
  onMove: (dir: -1 | 1) => void;
  onRemove: () => void;
}) {
  const id = `op-${op.code.replace("~", "-")}`;
  const title = opTitle(op);
  const set = (patch: Partial<RouteOp>) => onChange({ ...op, ...patch });
  const setExtra = (key: string, v: number | null) => {
    const extra = { ...op.extra };
    if (v == null) delete extra[key];
    else extra[key] = v;
    set({ extra });
  };
  const err = (k: string) => errors[k] ?? errors[`extra.${k}`] ?? (k.startsWith("extra.") ? errors.extra : undefined);
  const mine = resources.filter((r) => r.kind === op.resource_kind && r.status !== "inactive");
  const off = !op.enabled;
  const blocked = op.issues.some((i) => i.level === "error") || Object.keys(errors).length > 0;

  const suggestion = trace(op, "suggested_moulds_per_heat");
  const mpp = trace(op, "minutes_per_piece");

  return (
    <li className={`panel ${off ? "opacity-75" : ""}`}>
      <div className="flex flex-wrap items-center gap-2 px-3 py-2">
        <span className="w-6 font-mono text-xs text-ink-soft">{index + 1}</span>
        <label className="flex items-center gap-2">
          <input type="checkbox" className="size-5 accent-[var(--action)]" checked={op.enabled} disabled={!canEdit} onChange={(e) => set({ enabled: e.target.checked })} aria-label={`Use ${title} for this part`} />
        </label>
        <button type="button" className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-3 text-left" aria-expanded={open} aria-controls={`${id}-body`} onClick={onToggleOpen}>
          <span className="font-display text-lg font-semibold">{title}</span>
          <span className="truncate text-sm text-ink-soft">{off ? "Not used for this part" : summary(op) || "Needs a time"}</span>
        </button>
        {blocked && !off && <span className="rounded-sm bg-danger-wash px-1.5 py-0.5 font-mono text-xs text-danger">fix</span>}
        {!off && op.kind === "post" && !op.capacity_modelled && !op.outsourced && (
          <span className="rounded-sm bg-sunken px-1.5 py-0.5 font-mono text-xs text-ink-soft" title="No work centre is set, so plans do not check capacity for this operation.">capacity not modelled</span>
        )}
        {canEdit && canRemove && (
          <button type="button" className="btn btn-quiet !min-h-8 !px-2 text-sm" onClick={onRemove} aria-label={`Remove ${title}`}>Remove</button>
        )}
        {canEdit && (
          <span className="flex">
            <button type="button" className="btn btn-quiet !min-h-8 !px-2" onClick={() => onMove(-1)} disabled={index === 0} aria-label={`Move ${title} earlier`}>↑</button>
            <button type="button" className="btn btn-quiet !min-h-8 !px-2" onClick={() => onMove(1)} disabled={index === count - 1} aria-label={`Move ${title} later`}>↓</button>
          </span>
        )}
      </div>

      {open && !off && (
        <div id={`${id}-body`} className="space-y-4 border-t border-line px-4 py-4">
          <Issues issues={op.issues} />
          <div className="grid gap-x-4 gap-y-4 sm:grid-cols-2">
            {op.kind === "core" && (
              <>
                <NumField id={`${id}-time`} label="Time per core" unit="min" value={op.time_value} onChange={(v) => set({ time_value: v })} disabled={!canEdit} error={err("time_value")} placeholder={trace(op, "minutes_per_core")?.value?.toString()} hint="Blank uses the machine's rated speed." />
                <NumField id={`${id}-cpm`} label="Cores per mould" integer step="1" value={op.extra.cores_per_mould} onChange={(v) => setExtra("cores_per_mould", v)} disabled={!canEdit} error={err("extra.cores_per_mould")} placeholder={String(part.cores_per_mould)} hint={`Blank takes ${part.cores_per_mould} from the Part Master.`} />
                <NumField id={`${id}-scrap`} label="Core scrap allowance" unit="%" value={op.extra.scrap_pct} onChange={(v) => setExtra("scrap_pct", v)} disabled={!canEdit} error={err("extra.scrap_pct")} hint="Extra cores made to cover breakage. Default 0." />
                <NumField id={`${id}-lead`} label="Cores ready before moulding" unit="h" value={op.extra.lead_hours} onChange={(v) => setExtra("lead_hours", v)} disabled={!canEdit} error={err("extra.lead_hours")} hint="Minimum lead time. Default 0." />
                <ResourcePicker id={`${id}-res`} label="Allowed core machines" options={mine} chosen={op.resource_ids} onChange={(ids) => set({ resource_ids: ids })} disabled={!canEdit} />
              </>
            )}

            {op.kind === "moulding" && (
              <>
                <NumField id={`${id}-time`} label="Time per mould" unit="min" value={op.time_value} onChange={(v) => set({ time_value: v })} disabled={!canEdit} error={err("time_value")} placeholder={trace(op, "minutes_per_mould")?.value?.toString()} hint="Blank uses 60 ÷ the line's moulds per hour." />
                <NumField id={`${id}-cav`} label="Pieces per mould (cavities)" integer step="1" value={op.extra.cavities_per_mould} onChange={(v) => setExtra("cavities_per_mould", v)} disabled={!canEdit} error={err("extra.cavities_per_mould")} placeholder={String(part.cavities_per_mould)} hint={`Blank takes ${part.cavities_per_mould} from the Part Master.`} />
                <ResourcePicker id={`${id}-res`} label="Allowed moulding lines" options={mine} chosen={op.resource_ids} onChange={(ids) => set({ resource_ids: ids })} disabled={!canEdit} />
              </>
            )}

            {op.kind === "melting" && (
              <>
                <ResourcePicker id={`${id}-res`} label="Allowed furnaces" options={mine} chosen={op.resource_ids} onChange={(ids) => set({ resource_ids: ids })} disabled={!canEdit} hint={`Grade: ${part.grade_name ?? "not set on the part"}. Only one grade goes into a heat.`} />
                <NumField id={`${id}-loss`} label="Melt loss" unit="%" value={op.extra.melt_loss_pct} onChange={(v) => setExtra("melt_loss_pct", v)} disabled={!canEdit} error={err("extra.melt_loss_pct")} hint="Blank uses the company default." />
                <NumField
                  id={`${id}-mph`}
                  label="Moulds poured per heat"
                  integer
                  step="1"
                  value={op.extra.moulds_per_heat}
                  onChange={(v) => setExtra("moulds_per_heat", v)}
                  disabled={!canEdit}
                  error={err("extra.moulds_per_heat")}
                  placeholder={suggestion?.value?.toString()}
                  hint={
                    suggestion?.value != null ? (
                      <span>
                        Suggested: <Explain traced={suggestion} label="Suggested moulds per heat" />
                        {canEdit && op.extra.moulds_per_heat !== suggestion.value && (
                          <button type="button" className="ml-2 inline-flex min-h-6 items-center text-link underline-offset-2 hover:underline" onClick={() => setExtra("moulds_per_heat", suggestion.value)}>
                            Use it
                          </button>
                        )}
                      </span>
                    ) : (
                      "Pick a furnace to get a suggestion."
                    )
                  }
                />
                <NumField id={`${id}-time`} label="Total time per heat" unit="min" value={op.time_value} onChange={(v) => set({ time_value: v })} disabled={!canEdit} error={err("time_value")} placeholder={trace(op, "minutes_per_heat")?.value?.toString()} hint="Tap to tap. Blank takes the furnace's figure." />
                <div>
                  <p className="mb-1 text-sm font-medium">Minutes per piece</p>
                  <p className="flex min-h-10 items-center">{mpp ? <Explain traced={mpp} label="Minutes per piece" unit=" min" /> : "–"}</p>
                  <p className="mt-1 text-xs text-ink-soft">Worked out from the figures on this screen, so it cannot drift from them.</p>
                </div>
                <NumField id={`${id}-cool`} label="Cooling in the mould before knockout" unit="h" value={op.extra.cooling_hours} onChange={(v) => setExtra("cooling_hours", v)} disabled={!canEdit} error={err("extra.cooling_hours")} hint="Waiting time, not machine load. Default 0." />
              </>
            )}

            {op.kind === "post" && (
              <>
                {op.multi_step && (
                  <div className="sm:col-span-2 grid gap-x-4 gap-y-4 sm:grid-cols-2">
                    <div>
                      <label htmlFor={`${id}-label`} className="mb-1 block text-sm font-medium">Operation name{op.step ? ` (OP${op.step})` : ""}</label>
                      <input id={`${id}-label`} className="field" value={op.label} disabled={!canEdit} maxLength={80} placeholder="For example Rough milling" onChange={(e) => set({ label: e.target.value })} />
                      {err("label") && <p className="mt-1 text-sm text-danger">{err("label")}</p>}
                    </div>
                  </div>
                )}
                <div className="sm:col-span-2 grid gap-x-4 gap-y-4 sm:grid-cols-2">
                  <div>
                    <label htmlFor={`${id}-basis`} className="mb-1 block text-sm font-medium">Time basis</label>
                    <Select id={`${id}-basis`} className="field" value={op.time_basis} disabled={!canEdit} onChange={(e) => set({ time_basis: e.target.value })}>
                      {op.allowed_time_bases.map((b) => (
                        <option key={b} value={b}>{BASIS_LABEL[b] ?? b}</option>
                      ))}
                    </Select>
                    {err("time_basis") && <p className="mt-1 text-sm text-danger">{err("time_basis")}</p>}
                  </div>
                  <NumField
                    id={`${id}-time`}
                    label={op.time_basis.startsWith("fixed") ? "Fixed minutes" : op.multi_step ? "Default time" : "Time"}
                    unit="min"
                    value={op.time_value}
                    onChange={(v) => set({ time_value: v })}
                    disabled={!canEdit || op.outsourced}
                    error={err("time_value")}
                    hint={op.multi_step ? "Used for any machine type that has no time of its own below." : undefined}
                  />
                  {op.time_basis === "per_batch" && (
                    <NumField id={`${id}-batch`} label="Batch size" integer step="1" unit="pcs" value={op.batch_size} onChange={(v) => set({ batch_size: v })} disabled={!canEdit} error={err("batch_size")} />
                  )}
                  <div>
                    <label htmlFor={`${id}-bucket`} className="mb-1 block text-sm font-medium">Capacity is checked</label>
                    <Select id={`${id}-bucket`} className="field" value={op.capacity_bucket} disabled={!canEdit} onChange={(e) => set({ capacity_bucket: e.target.value as RouteOp["capacity_bucket"] })}>
                      <option value="shift">Per shift</option>
                      <option value="day">Per day</option>
                    </Select>
                    <p className="mt-1 text-xs text-ink-soft">Decides whether plans and prints for this operation are by shift or by day.</p>
                  </div>
                  <NumField id={`${id}-lag`} label="Wait after this operation" unit="h" value={op.lag_hours} onChange={(v) => set({ lag_hours: v ?? 0 })} disabled={!canEdit} error={err("lag_hours")} hint="For example an inspection hold or transport. Default 0." />
                </div>
                {op.type_code === "machining" || op.outsourced ? (
                  <div className="sm:col-span-2 grid gap-x-4 gap-y-3 sm:grid-cols-2">
                    <label className="flex min-h-10 items-center gap-2 text-sm font-medium">
                      <input type="checkbox" className="size-4 accent-[var(--action)]" checked={op.outsourced} disabled={!canEdit} onChange={(e) => set({ outsourced: e.target.checked, lead_days: e.target.checked ? (op.lead_days ?? 5) : null })} />
                      Done outside (outsourced)
                    </label>
                    {op.outsourced && (
                      <NumField id={`${id}-lead`} label="Lead time" integer step="1" unit="days" value={op.lead_days} onChange={(v) => set({ lead_days: v })} disabled={!canEdit} error={err("lead_days")} hint="Used instead of minutes." />
                    )}
                  </div>
                ) : (
                  <label className="sm:col-span-2 flex min-h-10 items-center gap-2 text-sm font-medium">
                    <input type="checkbox" className="size-4 accent-[var(--action)]" checked={op.outsourced} disabled={!canEdit} onChange={(e) => set({ outsourced: e.target.checked, lead_days: e.target.checked ? 5 : null })} />
                    Done outside (outsourced)
                  </label>
                )}
                {!op.outsourced &&
                  (op.multi_step ? (
                    <MachineChoice id={id} op={op} machines={mine} types={machineTypes} canEdit={canEdit} errors={errors} onChange={(patch) => set(patch)} />
                  ) : (
                    <ResourcePicker id={`${id}-res`} label="Allowed work centres" options={mine} chosen={op.resource_ids} onChange={(ids) => set({ resource_ids: ids })} disabled={!canEdit} hint="With none selected, capacity is not modelled: the operation takes its time but is not limited." />
                  ))}
              </>
            )}
          </div>
        </div>
      )}
    </li>
  );
}

/** Parse the nested 400 the route endpoints send: { operations: [ {field: [msg]}, ... ] }. */
function opErrors(err: unknown): { byIndex: Record<number, Record<string, string>>; general: string | null } {
  const out: Record<number, Record<string, string>> = {};
  if (!(err instanceof ApiError)) return { byIndex: out, general: "Could not reach the server." };
  const list = (err.body as { operations?: unknown } | null)?.operations;
  if (Array.isArray(list)) {
    list.forEach((item, i) => {
      if (item && typeof item === "object" && Object.keys(item).length) {
        out[i] = Object.fromEntries(Object.entries(item as Record<string, unknown>).map(([k, v]) => [k, Array.isArray(v) ? v.join(" ") : String(v)]));
      }
    });
    return { byIndex: out, general: Object.keys(out).length ? null : err.message };
  }
  return { byIndex: out, general: err.message };
}

function toPayload(ops: RouteOp[]) {
  return {
    operations: ops.map((o) => ({
      op_type: o.op_type,
      sequence: o.sequence,
      enabled: o.enabled,
      time_value: o.time_value,
      time_basis: o.time_basis,
      batch_size: o.time_basis === "per_batch" ? o.batch_size : null,
      capacity_bucket: o.capacity_bucket,
      lag_hours: o.lag_hours ?? 0,
      outsourced: o.outsourced,
      lead_days: o.outsourced ? o.lead_days : null,
      extra: o.extra,
      resource_ids: o.resource_ids,
      step: o.step,
      label: o.label,
      setup_minutes: o.setup_minutes,
      machine_types: o.machine_types,
      except_ids: o.except_ids,
      time_by_type: o.time_by_type,
    })),
  };
}

function merge(local: RouteOp[], server: RouteOp[]): RouteOp[] {
  const byCode = new Map(server.map((s) => [s.code, s]));
  return local.map((o) => {
    const s = byCode.get(o.code);
    return s
      ? { ...o, derived: s.derived, issues: s.issues, capacity_modelled: s.capacity_modelled, effective_resource_ids: s.effective_resource_ids }
      : o;
  });
}

export function RouteEditor({ part, initial, resources, machineTypes, otherParts, canEdit }: { part: Part; initial: Route; resources: Resource[]; machineTypes: ResourceType[]; otherParts: Part[]; canEdit: boolean }) {
  const [ops, setOps] = useState<RouteOp[]>(initial.operations);
  const [savedSig, setSavedSig] = useState(JSON.stringify(toPayload(initial.operations)));
  const [errors, setErrors] = useState<Record<number, Record<string, string>>>({});
  const [general, setGeneral] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [openCodes, setOpenCodes] = useState<Set<string>>(() => new Set(initial.operations.filter((o) => o.enabled).map((o) => o.code)));
  const [copyFrom, setCopyFrom] = useState("");
  const [confirmCopy, setConfirmCopy] = useState(false);
  const ticket = useRef(0);
  const first = useRef(true);

  const sig = useMemo(() => JSON.stringify(toPayload(ops)), [ops]);
  const dirty = sig !== savedSig;

  // Live check: ask the server what these inputs would give, without saving anything.
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    const mine = ++ticket.current;
    const timer = setTimeout(() => {
      post<Route>(`/parts/${part.id}/operations/preview`, JSON.parse(sig))
        .then((route) => {
          if (mine !== ticket.current) return;
          setErrors({});
          setGeneral(null);
          setOps((current) => merge(current, route.operations));
        })
        .catch((err) => {
          if (mine !== ticket.current) return;
          const { byIndex, general } = opErrors(err);
          setErrors(byIndex);
          setGeneral(general);
        });
    }, 450);
    return () => clearTimeout(timer);
  }, [sig, part.id]);

  function update(i: number, next: RouteOp) {
    setSaved(false);
    setOps((list) => list.map((o, j) => (j === i ? next : o)));
  }

  /** Another step of an operation that may be routed several times (machining OP10, OP20...). */
  function addStep(typeCode: string) {
    const step = nextStep(ops, typeCode);
    const code = `${typeCode}~${step}`;
    setSaved(false);
    setOps((list) => {
      const same = list.filter((o) => o.type_code === typeCode);
      const last = same[same.length - 1];
      const fresh: RouteOp = {
        ...last,
        id: null,
        code,
        step,
        label: "",
        enabled: true,
        sequence: Math.max(...same.map((o) => o.sequence)) + 1,
        time_value: null,
        setup_minutes: 0,
        outsourced: false,
        lead_days: null,
        resource_ids: [],
        effective_resource_ids: [],
        machine_types: [...last.machine_types],
        except_ids: [],
        time_by_type: {},
        extra: {},
        derived: {},
        issues: [],
      };
      const at = list.lastIndexOf(last) + 1;
      return [...list.slice(0, at), fresh, ...list.slice(at)];
    });
    setOpenCodes((s) => new Set(s).add(code));
  }

  function removeStep(i: number) {
    setSaved(false);
    setOps((list) => list.filter((_, j) => j !== i));
  }

  function move(i: number, dir: -1 | 1) {
    setSaved(false);
    setOps((list) => {
      const next = [...list];
      [next[i], next[i + dir]] = [next[i + dir], next[i]];
      return next.map((o, k) => ({ ...o, sequence: (k + 1) * 10 }));
    });
  }

  async function save() {
    setBusy(true);
    setErrors({});
    setGeneral(null);
    ticket.current++;
    try {
      const route = await put<Route>(`/parts/${part.id}/operations`, JSON.parse(sig));
      const next = merge(ops, route.operations);
      setOps(next);
      setSavedSig(JSON.stringify(toPayload(next)));
      setSaved(true);
    } catch (err) {
      const { byIndex, general } = opErrors(err);
      setErrors(byIndex);
      setGeneral(general ?? "Please fix the operations marked “fix”.");
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    setBusy(true);
    setGeneral(null);
    ticket.current++;
    try {
      const route = await post<Route>(`/parts/${part.id}/copy-route`, { source_part: Number(copyFrom) });
      setOps(route.operations);
      setSavedSig(JSON.stringify(toPayload(route.operations)));
      setOpenCodes(new Set(route.operations.filter((o) => o.enabled).map((o) => o.code)));
      setSaved(true);
      setConfirmCopy(false);
      setCopyFrom("");
    } catch (err) {
      setGeneral(err instanceof ApiError ? err.message : "Could not copy.");
    } finally {
      setBusy(false);
    }
  }

  const errorCount = Object.keys(errors).length;

  return (
    <div className="space-y-4">
      {initial.is_template && !saved && (
        <p className="rounded-md border border-line bg-sunken px-3 py-2 text-sm">
          This part has no route yet. The standard operations are listed below: switch on the ones it uses, enter times and choose the resources, then save.
        </p>
      )}

      <div className="sticky top-0 z-10 -mx-1 flex flex-wrap items-center gap-3 border-b border-line bg-ground/95 px-1 py-2 backdrop-blur">
        {canEdit && (
          <button type="button" className="btn btn-primary" onClick={save} disabled={busy || (!dirty && !initial.is_template && !errorCount)}>
            {busy ? "Saving…" : "Save route"}
          </button>
        )}
        <span role="status" className="text-sm">
          {errorCount ? <span className="text-danger">{errorCount} operation{errorCount > 1 ? "s" : ""} need fixing before this can be saved</span> : dirty ? <span className="text-warn">Unsaved changes</span> : saved ? <span className="text-ok">Saved</span> : <span className="text-ink-soft">No changes</span>}
        </span>
        {canEdit && otherParts.length > 0 && (
          <span className="ml-auto flex flex-wrap items-center gap-2">
            <label className="sr-only" htmlFor="copy-from">Copy route from another part</label>
            <Select id="copy-from" className="field !min-h-9 !w-auto max-w-[14rem]" value={copyFrom} onChange={(e) => { setCopyFrom(e.target.value); setConfirmCopy(false); }}>
              <option value="">Copy route from…</option>
              {otherParts.map((p) => (
                <option key={p.id} value={p.id}>{p.part_number} {p.name}</option>
              ))}
            </Select>
            {copyFrom && (confirmCopy ? (
              <button type="button" className="btn btn-danger !min-h-9" onClick={copy} disabled={busy}>Replace this route</button>
            ) : (
              <button type="button" className="btn btn-quiet !min-h-9" onClick={() => setConfirmCopy(true)}>Copy</button>
            ))}
          </span>
        )}
      </div>

      <FormError message={general} />

      <ol className="space-y-3">
        {ops.map((op, i) => (
          <OpCard
            key={op.code}
            op={op}
            index={i}
            count={ops.length}
            part={part}
            resources={resources}
            machineTypes={machineTypes}
            errors={errors[i] ?? {}}
            canEdit={canEdit}
            canRemove={op.multi_step && ops.filter((o) => o.type_code === op.type_code).length > 1}
            onRemove={() => removeStep(i)}
            open={openCodes.has(op.code)}
            onToggleOpen={() => setOpenCodes((s) => { const n = new Set(s); if (n.has(op.code)) n.delete(op.code); else n.add(op.code); return n; })}
            onChange={(next) => {
              if (next.enabled && !op.enabled) setOpenCodes((s) => new Set(s).add(op.code));
              update(i, next);
            }}
            onMove={(dir) => move(i, dir)}
          />
        ))}
      </ol>

      {canEdit && (
        <div className="flex flex-wrap gap-2">
          {[...new Map(ops.filter((o) => o.multi_step).map((o) => [o.type_code, o.name])).entries()].map(([typeCode, name]) => (
            <button key={typeCode} type="button" className="btn btn-quiet" onClick={() => addStep(typeCode)}>
              Add {name.toLowerCase()} operation
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
