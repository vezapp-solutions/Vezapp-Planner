"use client";

import { useEffect, useId, useRef, useState } from "react";

import type { Issue, Traced } from "@/lib/types";

const LABEL: Record<string, string> = {
  heat_kg: "Heat size (kg)",
  melt_loss_pct: "Melt loss (%)",
  pour_kg_per_mould: "Pouring weight per mould (kg)",
  minutes_per_heat: "Minutes per heat",
  moulds_per_heat: "Moulds per heat",
  cavities_per_mould: "Cavities per mould",
  moulds_per_hour: "Moulds per hour",
  cores_per_hour: "Cores per hour",
  cycle_seconds: "Cycle (seconds per shot)",
  cores_per_shot: "Cores per shot",
  bucket_minutes: "Shift minutes",
  units: "Units",
  efficiency_pct: "Efficiency (%)",
  downtime_minutes: "Downtime (min)",
  usable_minutes: "Usable minutes",
  max_heats: "Max heats per shift",
};

/** Click a derived number to see the formula and the inputs it came from. */
export function Explain({ traced, label, unit = "" }: { traced: Traced; label: string; unit?: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const box = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const shown = traced.value === null ? "–" : `${new Intl.NumberFormat("en-IN", { maximumFractionDigits: 3 }).format(traced.value)}${unit}`;
  const inputs = Object.entries(traced.inputs).filter(([, v]) => v !== null && v !== undefined);

  return (
    <span ref={box} className="relative inline-block">
      <button
        type="button"
        className="inline-flex min-h-6 min-w-6 items-center justify-center rounded-sm border-b border-dashed border-ink-soft font-mono font-medium hover:bg-sunken"
        aria-expanded={open}
        aria-controls={id}
        aria-label={`${label}: ${shown}. Show how this is calculated`}
        onClick={() => setOpen((v) => !v)}
      >
        {shown}
      </button>
      {open && (
        <span
          id={id}
          role="dialog"
          aria-label={`How ${label} is calculated`}
          className="absolute left-0 top-full z-30 mt-1 block w-72 max-w-[80vw] rounded-md border border-line bg-surface p-3 text-left text-sm font-normal"
        >
          <span className="block font-medium">{label}</span>
          <span className="mt-1 block text-ink-soft">{traced.formula}</span>
          {inputs.length > 0 && (
            <span className="mt-2 block space-y-0.5 border-t border-line pt-2">
              {inputs.map(([k, v]) => (
                <span key={k} className="flex justify-between gap-3">
                  <span className="text-ink-soft">{LABEL[k] ?? k.replaceAll("_", " ")}</span>
                  <span className="font-mono">{String(v)}</span>
                </span>
              ))}
            </span>
          )}
          {traced.note && <span className="mt-2 block text-ink-soft">{traced.note}</span>}
        </span>
      )}
    </span>
  );
}

const ICON: Record<Issue["level"], string> = { error: "Blocked", warning: "Check", info: "Note" };

export function Issues({ issues }: { issues: Issue[] }) {
  if (!issues.length) return null;
  return (
    <ul className="space-y-1.5">
      {issues.map((issue, i) => (
        <li
          key={i}
          className={`flex gap-2 rounded-sm border px-2.5 py-1.5 text-sm ${
            issue.level === "error"
              ? "border-danger bg-danger-wash"
              : issue.level === "warning"
                ? "border-warn bg-warn-wash"
                : "border-line bg-sunken"
          }`}
        >
          <span className="shrink-0 font-mono text-xs uppercase leading-5">{ICON[issue.level]}</span>
          <span>{issue.message}</span>
        </li>
      ))}
    </ul>
  );
}

export function WarnBadge({ issues }: { issues: Issue[] }) {
  const n = issues.filter((i) => i.level === "warning").length;
  if (!n) return null;
  return (
    <span className="ml-2 rounded-sm bg-warn-wash px-1.5 py-0.5 font-mono text-xs text-warn" title={issues.filter((i) => i.level === "warning").map((i) => i.message).join("\n")}>
      {n} to check
    </span>
  );
}
