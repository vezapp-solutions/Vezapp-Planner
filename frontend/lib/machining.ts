import type { Resource, RouteOp } from "./types";

type StepFields = Pick<RouteOp, "machine_types" | "except_ids" | "resource_ids" | "time_by_type">;
type Machine = Pick<Resource, "id" | "resource_type">;

/** "Machining OP10 Rough milling": the name a planner reads for one step of a route. */
export function opTitle(op: Pick<RouteOp, "name" | "step" | "label">): string {
  return [op.name, op.step ? `OP${op.step}` : "", op.label].filter(Boolean).join(" ");
}

/**
 * A step may run on a machine when the machine's type is allowed and the machine is not marked
 * unsuitable, or when it was chosen on its own.
 */
export function machineOn(op: StepFields, m: Machine): boolean {
  return (op.machine_types.includes(m.resource_type) && !op.except_ids.includes(m.id)) || op.resource_ids.includes(m.id);
}

/** Tick or untick one machine, keeping the type choice and the exceptions consistent. */
export function toggleMachine(op: StepFields, m: Machine): Pick<StepFields, "resource_ids" | "except_ids"> {
  const typeAllowed = op.machine_types.includes(m.resource_type);
  const on = machineOn(op, m);
  let resource_ids = op.resource_ids;
  let except_ids = op.except_ids;
  if (on) {
    resource_ids = resource_ids.filter((id) => id !== m.id);
    if (typeAllowed && !except_ids.includes(m.id)) except_ids = [...except_ids, m.id];
  } else if (typeAllowed) {
    except_ids = except_ids.filter((id) => id !== m.id);
  } else {
    resource_ids = [...resource_ids, m.id];
  }
  return { resource_ids, except_ids };
}

/** Allow or stop allowing a machine type. Leaving a type forgets its time and its exceptions. */
export function toggleType(op: StepFields, typeId: number, machines: Machine[]): Pick<StepFields, "machine_types" | "except_ids" | "time_by_type"> {
  if (!op.machine_types.includes(typeId)) {
    return { machine_types: [...op.machine_types, typeId], except_ids: op.except_ids, time_by_type: op.time_by_type };
  }
  const ofType = new Set(machines.filter((m) => m.resource_type === typeId).map((m) => m.id));
  const time_by_type = { ...op.time_by_type };
  delete time_by_type[String(typeId)];
  return {
    machine_types: op.machine_types.filter((t) => t !== typeId),
    except_ids: op.except_ids.filter((id) => !ofType.has(id)),
    time_by_type,
  };
}

/** Set the minutes per piece for one machine type; a blank removes it so the default applies. */
export function setTypeTime(times: Record<string, number>, typeId: number, minutes: number | null): Record<string, number> {
  const next = { ...times };
  if (minutes == null) delete next[String(typeId)];
  else next[String(typeId)] = minutes;
  return next;
}

/** The machines that may run the step, in the order the list shows them. */
export function allowedMachines<T extends Machine>(op: StepFields, machines: T[]): T[] {
  return machines.filter((m) => machineOn(op, m));
}

/** Types that need a time: the allowed types and the types of machines chosen on their own. */
export function timedTypes(op: StepFields, machines: Machine[]): number[] {
  const out = new Set(op.machine_types);
  for (const m of machines) if (op.resource_ids.includes(m.id)) out.add(m.resource_type);
  return [...out];
}

/** The next operation number for a multi-step operation: 10, 20, 30... */
export function nextStep(ops: Pick<RouteOp, "type_code" | "step">[], typeCode: string): number {
  const used = ops.filter((o) => o.type_code === typeCode).map((o) => o.step);
  return (Math.floor(Math.max(0, ...used) / 10) + 1) * 10;
}

/** Minutes as hours with one decimal: 382.5 becomes "6.4". */
export function hours(minutes: number): string {
  return (minutes / 60).toFixed(1);
}

/** What a machine-and-day cell prints: the share used, always as text, and the free hours. */
export function dayCell(day: { capacity: number; load: number; free: number; utilisation: number | null } | undefined): { main: string; sub: string; title: string; off: boolean } {
  if (!day || day.capacity <= 0) return { main: "off", sub: "", title: "No working time: maintenance, downtime or a weekly off", off: true };
  const used = day.utilisation == null ? 0 : Math.round(day.utilisation * 100);
  return { main: `${used}%`, sub: `${hours(day.free)} h free`, title: `${hours(day.load)} of ${hours(day.capacity)} hours used`, off: false };
}

/** "VMC-1, VMC-2 and HMC-1", or a plain sentence when nothing is allowed yet. */
export function runsOn(op: StepFields, machines: (Machine & { code: string })[]): string {
  const codes = allowedMachines(op, machines).map((m) => m.code);
  if (codes.length === 0) return "No machine is allowed yet, so capacity is not checked for this operation.";
  const head = codes.slice(0, -1).join(", ");
  return `Runs on ${codes.length > 1 ? `${head} and ${codes[codes.length - 1]}` : codes[0]}.`;
}
