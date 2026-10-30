"use client";

import { allowedMachines, machineOn, runsOn, setTypeTime, timedTypes, toggleMachine, toggleType } from "@/lib/machining";
import type { Resource, ResourceType, RouteOp } from "@/lib/types";
import { Select } from "@/components/ui/Select";

/** A number box for minutes. Kept small and local so a blank means "use the default". */
function MinutesBox({ id, label, value, onChange, unit = "min", hint, error, disabled, placeholder }: { id: string; label: string; value: number | null | undefined; onChange: (v: number | null) => void; unit?: string; hint?: string; error?: string; disabled?: boolean; placeholder?: string }) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium">{label}</label>
      <div className="relative">
        <input
          id={id}
          type="number"
          inputMode="decimal"
          step="any"
          min={0}
          className="field font-mono !pr-14"
          disabled={disabled}
          value={value ?? ""}
          placeholder={placeholder}
          aria-invalid={error ? true : undefined}
          onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
        />
        <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-ink-soft">{unit}</span>
      </div>
      {hint && !error && <p className="mt-1 text-xs text-ink-soft">{hint}</p>}
      {error && <p className="mt-1 text-sm text-danger">{error}</p>}
    </div>
  );
}

/**
 * Which machines may run one machining operation, how long each machine type takes, and the setup.
 * Choosing a type allows every machine of that type (also machines bought later); unticking a
 * machine marks it unsuitable; a machine of another type can be added on its own.
 */
export function MachineChoice({
  id,
  op,
  machines,
  types,
  canEdit,
  errors,
  onChange,
}: {
  id: string;
  op: RouteOp;
  machines: Resource[];
  types: ResourceType[];
  canEdit: boolean;
  errors: Record<string, string>;
  onChange: (patch: Partial<RouteOp>) => void;
}) {
  const shown = machines.filter((m) => op.machine_types.includes(m.resource_type) || op.resource_ids.includes(m.id));
  const elsewhere = machines.filter((m) => !shown.includes(m));
  const typeName = (typeId: number) => types.find((t) => t.id === typeId)?.name ?? `type ${typeId}`;
  const count = (typeId: number) => machines.filter((m) => m.resource_type === typeId).length;
  const timed = timedTypes(op, machines);
  const permitted = allowedMachines(op, machines);

  return (
    <div className="space-y-4 sm:col-span-2">
      <fieldset disabled={!canEdit}>
        <legend className="mb-1 text-sm font-medium">Machine types that may run this operation</legend>
        <div className="flex flex-wrap gap-2">
          {types.length === 0 && <span className="text-sm text-ink-soft">No machine types yet. Add types such as VMC, CNC and HMC under Resources, then add the machines.</span>}
          {types.map((t) => {
            const on = op.machine_types.includes(t.id);
            return (
              <label key={t.id} className={`flex min-h-9 cursor-pointer items-center gap-2 rounded-sm border px-2.5 text-sm ${on ? "border-action bg-brand-wash" : "border-line"}`}>
                <input type="checkbox" className="size-4 accent-[var(--action)]" checked={on} onChange={() => onChange(toggleType(op, t.id, machines))} />
                <span className="font-medium">{t.name}</span>
                <span className="text-xs text-ink-soft">{count(t.id)} machine{count(t.id) === 1 ? "" : "s"}</span>
              </label>
            );
          })}
        </div>
        <p className="mt-1 text-xs text-ink-soft">Every machine of a chosen type is allowed, including machines you add later.</p>
        {errors.machine_types && <p className="mt-1 text-sm text-danger">{errors.machine_types}</p>}
      </fieldset>

      {shown.length > 0 && (
        <fieldset disabled={!canEdit}>
          <legend className="mb-1 text-sm font-medium">Machines (untick any that are not suitable)</legend>
          <div className="flex flex-wrap gap-2">
            {shown.map((m) => {
              const on = machineOn(op, m);
              return (
                <label key={m.id} className={`flex min-h-9 cursor-pointer items-center gap-2 rounded-sm border px-2.5 text-sm ${on ? "border-action bg-brand-wash" : "border-line"}`}>
                  <input type="checkbox" className="size-4 accent-[var(--action)]" checked={on} onChange={() => onChange(toggleMachine(op, m))} />
                  <span className="font-mono text-xs">{m.code}</span> {m.name}
                  <span className="text-xs text-ink-soft">{m.type_name}{m.status !== "active" ? `, ${m.status}` : ""}</span>
                </label>
              );
            })}
          </div>
        </fieldset>
      )}

      {canEdit && elsewhere.length > 0 && (
        <div>
          <label htmlFor={`${id}-other`} className="mb-1 block text-sm font-medium">Add a machine of another type</label>
          <Select id={`${id}-other`} className="field sm:max-w-xs" value="" onChange={(e) => e.target.value && onChange({ resource_ids: [...op.resource_ids, Number(e.target.value)] })}>
            <option value="">Choose a machine…</option>
            {elsewhere.map((m) => <option key={m.id} value={m.id}>{m.code} · {m.name} ({m.type_name})</option>)}
          </Select>
        </div>
      )}

      {timed.length > 0 && (
        <div className="grid gap-x-4 gap-y-4 sm:grid-cols-2">
          {timed.map((typeId) => (
            <MinutesBox
              key={typeId}
              id={`${id}-time-${typeId}`}
              label={`Time per piece on ${typeName(typeId)}`}
              value={op.time_by_type[String(typeId)]}
              onChange={(v) => onChange({ time_by_type: setTypeTime(op.time_by_type, typeId, v) })}
              disabled={!canEdit}
              placeholder={op.time_value != null ? String(op.time_value) : undefined}
              hint={op.time_value != null ? "Blank uses the default time." : "Enter a time, or set a default time."}
            />
          ))}
        </div>
      )}
      {errors.time_by_type && <p className="text-sm text-danger">{errors.time_by_type}</p>}

      <div className="grid gap-x-4 gap-y-4 sm:grid-cols-2">
        <MinutesBox id={`${id}-setup`} label="Setup per lot" value={op.setup_minutes} onChange={(v) => onChange({ setup_minutes: v ?? 0 })} disabled={!canEdit} error={errors.setup_minutes} hint="Fixture and tool change, taken from each machine used for the lot before its first piece." />
      </div>

      <p className="text-sm text-ink-soft" aria-live="polite">{runsOn(op, permitted)}</p>
    </div>
  );
}
