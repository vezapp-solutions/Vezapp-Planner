"use client";

import type { ReactNode } from "react";

import { DatePicker } from "@/components/ui/DatePicker";
import { Select } from "@/components/ui/Select";

export type Option = { value: string | number; label: string };
export type DraftValue = string | boolean | (string | number)[];
export type Draft = Record<string, DraftValue>;

export interface FieldSpec {
  key: string;
  label: string;
  type: "text" | "password" | "textarea" | "number" | "select" | "checkbox" | "time" | "date" | "datetime" | "multi";
  options?: Option[];
  hint?: string;
  unit?: string;
  step?: string;
  min?: number;
  required?: boolean;
  placeholder?: string;
  wide?: boolean;
  showIf?: (draft: Draft) => boolean;
  /** Choose "" ("none") as an option on a select. */
  blankLabel?: string;
  disabled?: (draft: Draft) => boolean;
}

export function toDraft(row: Record<string, unknown> | null, fields: FieldSpec[], defaults: Draft = {}): Draft {
  const draft: Draft = {};
  for (const f of fields) {
    const raw = row ? row[f.key] : undefined;
    if (raw === undefined) {
      draft[f.key] = defaults[f.key] ?? (f.type === "checkbox" ? false : f.type === "multi" ? [] : "");
    } else if (f.type === "checkbox") draft[f.key] = Boolean(raw);
    else if (f.type === "multi") draft[f.key] = Array.isArray(raw) ? (raw as (string | number)[]) : [];
    else if (raw === null) draft[f.key] = "";
    else if (f.type === "time") draft[f.key] = String(raw).slice(0, 5);
    else if (f.type === "datetime") draft[f.key] = toLocalInput(String(raw));
    else draft[f.key] = String(raw);
  }
  return draft;
}

function toLocalInput(iso: string): string {
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function toPayload(draft: Draft, fields: FieldSpec[]): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const f of fields) {
    if (f.showIf && !f.showIf(draft)) continue;
    const v = draft[f.key];
    if (f.type === "number") out[f.key] = v === "" ? null : Number(v);
    else if (f.type === "select") {
      const numeric = f.options?.some((o) => typeof o.value === "number");
      out[f.key] = v === "" ? (f.blankLabel ? null : "") : numeric ? Number(v) : v;
    } else if (f.type === "datetime") out[f.key] = v ? new Date(String(v)).toISOString() : null;
    else if (f.type === "date" || f.type === "time") out[f.key] = v === "" ? null : v;
    else out[f.key] = v;
  }
  return out;
}

export function FormError({ message }: { message?: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="rounded-md border border-danger bg-danger-wash px-3 py-2 text-sm">
      {message}
    </p>
  );
}

export function FieldShell({
  id,
  label,
  hint,
  error,
  required,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium">
        {label}
        {required && <span className="text-danger" aria-hidden="true"> *</span>}
      </label>
      {children}
      {hint && !error && <p className="mt-1 text-xs text-ink-soft">{hint}</p>}
      {error && (
        <p id={`${id}-error`} className="mt-1 text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

export function RecordForm({
  fields,
  draft,
  setDraft,
  errors = {},
  readOnly = false,
  idPrefix = "f",
}: {
  fields: FieldSpec[];
  draft: Draft;
  setDraft: (next: Draft) => void;
  errors?: Record<string, string>;
  readOnly?: boolean;
  idPrefix?: string;
}) {
  const set = (key: string, value: DraftValue) => setDraft({ ...draft, [key]: value });

  return (
    <div className="grid gap-x-4 gap-y-4 sm:grid-cols-2">
      {fields
        .filter((f) => !f.showIf || f.showIf(draft))
        .map((f) => {
          const id = `${idPrefix}-${f.key}`;
          const value = draft[f.key];
          const error = errors[f.key];
          const disabled = readOnly || f.disabled?.(draft);
          const wide = f.wide || f.type === "textarea" || f.type === "multi" || f.type === "checkbox";
          const common = {
            id,
            disabled,
            "aria-invalid": error ? true : undefined,
            "aria-describedby": error ? `${id}-error` : undefined,
          } as const;

          let control: ReactNode;
          if (f.type === "checkbox") {
            control = (
              <label className="flex min-h-10 items-center gap-2">
                <input
                  type="checkbox"
                  id={id}
                  className="size-[1.125rem]"
                  checked={Boolean(value)}
                  disabled={disabled}
                  onChange={(e) => set(f.key, e.target.checked)}
                />
                <span className="text-sm font-medium">{f.label}</span>
              </label>
            );
            return (
              <div key={f.key} className={wide ? "sm:col-span-2" : ""}>
                {control}
                {f.hint && <p className="text-xs text-ink-soft">{f.hint}</p>}
                {error && <p className="text-sm text-danger">{error}</p>}
              </div>
            );
          }
          if (f.type === "textarea") {
            control = <textarea {...common} rows={3} className="field !py-2" value={String(value)} onChange={(e) => set(f.key, e.target.value)} placeholder={f.placeholder} />;
          } else if (f.type === "select") {
            control = (
              <Select {...common} className="" value={String(value)} onChange={(e) => set(f.key, e.target.value)}>
                {(f.blankLabel !== undefined || f.required) && <option value="">{f.blankLabel ?? "Choose…"}</option>}
                {f.options?.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </Select>
            );
          } else if (f.type === "multi") {
            const chosen = (value as (string | number)[]) ?? [];
            control = (
              <div className="flex flex-wrap gap-2" role="group" aria-labelledby={`${id}-label`}>
                {f.options?.length ? (
                  f.options.map((o) => {
                    const on = chosen.includes(o.value);
                    return (
                      <label key={o.value} className={`flex min-h-10 cursor-pointer items-center gap-2 rounded-lg border px-3 text-sm transition-colors duration-150 ${on ? "border-action bg-brand-wash" : "border-line hover:border-ink-soft hover:bg-sunken"}`}>
                        <input
                          type="checkbox"
                          className="size-[1.125rem]"
                          checked={on}
                          disabled={disabled}
                          onChange={() => set(f.key, on ? chosen.filter((c) => c !== o.value) : [...chosen, o.value])}
                        />
                        {o.label}
                      </label>
                    );
                  })
                ) : (
                  <span className="text-sm text-ink-soft">None available yet.</span>
                )}
              </div>
            );
            return (
              <div key={f.key} className="sm:col-span-2">
                <p id={`${id}-label`} className="mb-1 text-sm font-medium">{f.label}</p>
                {control}
                {f.hint && !error && <p className="mt-1 text-xs text-ink-soft">{f.hint}</p>}
                {error && <p className="mt-1 text-sm text-danger">{error}</p>}
              </div>
            );
          } else if (f.type === "date" || f.type === "datetime") {
            control = (
              <DatePicker
                {...common}
                mode={f.type === "datetime" ? "datetime" : "date"}
                value={String(value)}
                onChange={(e) => set(f.key, e.target.value)}
                placeholder={f.placeholder}
                clearable={!f.required}
              />
            );
          } else {
            const type = f.type;
            control = (
              <div className="relative">
                <input
                  {...common}
                  type={type}
                  inputMode={f.type === "number" ? "decimal" : undefined}
                  autoComplete={f.type === "password" ? "new-password" : undefined}
                  step={f.type === "number" ? (f.step ?? "any") : undefined}
                  min={f.min}
                  className={`field ${f.type === "number" ? "font-mono" : ""} ${f.unit ? "!pr-14" : ""}`}
                  value={String(value)}
                  onChange={(e) => set(f.key, e.target.value)}
                  placeholder={f.placeholder}
                />
                {f.unit && <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-ink-soft">{f.unit}</span>}
              </div>
            );
          }

          return (
            <div key={f.key} className={wide ? "sm:col-span-2" : ""}>
              <FieldShell id={id} label={f.label} hint={f.hint} error={error} required={f.required}>
                {control}
              </FieldShell>
            </div>
          );
        })}
    </div>
  );
}
