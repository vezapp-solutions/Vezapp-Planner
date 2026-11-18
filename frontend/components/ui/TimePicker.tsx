"use client";

import { useCallback, useRef, useState } from "react";

import { Popover } from "@/components/ui/Popover";
import { formatTime12, from12Hour, minuteChoices, parseTime, to12Hour, toTime } from "@/lib/time";

export interface TimeChange {
  target: { value: string };
}

const HOURS = Array.from({ length: 12 }, (_, i) => i + 1);
const PRESETS: { label: string; value: string }[] = [
  { label: "Midnight", value: "00:00" },
  { label: "6 AM", value: "06:00" },
  { label: "Noon", value: "12:00" },
  { label: "2 PM", value: "14:00" },
  { label: "10 PM", value: "22:00" },
];

const cell =
  "flex h-10 items-center justify-center rounded-chip text-sm font-medium transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-action";
const on = "bg-action text-on-action";
const off = "hover:bg-sunken";

/**
 * A clock drop-down in place of the browser's time input. The value is the same "HH:mm" 24-hour string the input
 * gave, and onChange reads `e.target.value`. Tap an hour, a minute and AM or PM (or a quick choice such as
 * Midnight or 2 PM); each tap applies at once and Done closes the panel. On a phone it opens as a bottom sheet.
 */
export function TimePicker({
  value,
  onChange,
  id,
  className = "",
  disabled = false,
  clearable = true,
  placeholder,
  "aria-label": ariaLabel,
  "aria-invalid": ariaInvalid,
  "aria-describedby": ariaDescribedBy,
}: {
  value: string;
  onChange?: (e: TimeChange) => void;
  id?: string;
  className?: string;
  disabled?: boolean;
  /** Offer a Clear button. Turn off where an empty value is not allowed. */
  clearable?: boolean;
  placeholder?: string;
  "aria-label"?: string;
  "aria-invalid"?: boolean;
  "aria-describedby"?: string;
}) {
  const parsed = parseTime(value);
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const close = useCallback(() => setOpen(false), []);

  // With nothing chosen yet, a first tap starts from midnight.
  const base = parsed ?? { hour: 0, minute: 0 };
  const { hour12, pm } = to12Hour(base.hour);
  const emit = (next: { hour: number; minute: number }) => onChange?.({ target: { value: toTime(next) } });
  const text = formatTime12(value);

  return (
    <>
      <button
        ref={trigger}
        type="button"
        id={id}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={ariaLabel}
        aria-describedby={ariaDescribedBy}
        disabled={disabled}
        onClick={() => !disabled && setOpen((o) => !o)}
        className={`field flex items-center justify-between gap-2 text-left transition-[border-color,box-shadow] duration-150 ${ariaInvalid ? "!border-danger" : ""} ${className}`}
      >
        <span className={`min-w-0 truncate font-mono text-sm ${text ? "" : "font-sans text-ink-soft"}`}>{text || placeholder || "Pick a time"}</span>
        <svg aria-hidden="true" viewBox="0 0 20 20" className="h-4 w-4 shrink-0 text-ink-soft" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="10" cy="10" r="7.25" />
          <path d="M10 5.5V10l3 1.75" />
        </svg>
      </button>

      <Popover anchor={trigger} open={open} onClose={close} label="Choose a time" matchWidth={false} className="w-[21rem] max-w-[calc(100vw-1rem)] p-4">
        {/* The big readout, with the AM / PM switch beside it */}
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="font-display text-[2rem] font-bold leading-none tracking-tight" aria-live="polite">
              {text || "--:-- --"}
            </p>
            <p className="mt-1.5 text-xs text-ink-soft">{parsed ? `${toTime(parsed)} in 24-hour time` : "Choose an hour and a minute"}</p>
          </div>
          <div role="group" aria-label="AM or PM" className="flex rounded-full bg-sunken p-1">
            {([false, true] as const).map((isPm) => (
              <button
                key={String(isPm)}
                type="button"
                aria-pressed={parsed ? pm === isPm : false}
                onClick={() => emit({ hour: from12Hour(hour12, isPm), minute: base.minute })}
                className={`min-h-9 min-w-12 rounded-full px-3 text-sm font-semibold transition-colors duration-150 ${parsed && pm === isPm ? "bg-surface shadow-sm" : "text-ink-soft"}`}
              >
                {isPm ? "PM" : "AM"}
              </button>
            ))}
          </div>
        </div>

        <p className="mb-1.5 mt-5 text-xs font-semibold uppercase tracking-wider text-ink-soft">Hour</p>
        <div className="grid grid-cols-6 gap-1" role="group" aria-label="Hour">
          {HOURS.map((h) => (
            <button key={h} type="button" aria-pressed={parsed ? hour12 === h : false} onClick={() => emit({ hour: from12Hour(h, pm), minute: base.minute })} className={`${cell} ${parsed && hour12 === h ? on : off}`}>
              {h}
            </button>
          ))}
        </div>

        <p className="mb-1.5 mt-4 text-xs font-semibold uppercase tracking-wider text-ink-soft">Minute</p>
        <div className="grid grid-cols-6 gap-1" role="group" aria-label="Minute">
          {minuteChoices(parsed ? parsed.minute : null).map((m) => (
            <button key={m} type="button" aria-pressed={parsed ? parsed.minute === m : false} onClick={() => emit({ hour: base.hour, minute: m })} className={`${cell} font-mono ${parsed && parsed.minute === m ? on : off}`}>
              {String(m).padStart(2, "0")}
            </button>
          ))}
        </div>

        <p className="mb-1.5 mt-4 text-xs font-semibold uppercase tracking-wider text-ink-soft">Quick choice</p>
        <div className="flex flex-wrap gap-1.5">
          {PRESETS.map((p) => (
            <button
              key={p.value}
              type="button"
              onClick={() => onChange?.({ target: { value: p.value } })}
              aria-pressed={value === p.value}
              className={`min-h-9 rounded-full border px-3 text-sm transition-colors duration-150 ${value === p.value ? "border-action bg-brand-wash font-semibold" : "border-line hover:border-ink-soft hover:bg-sunken"}`}
            >
              {p.label}
            </button>
          ))}
        </div>

        <div className="mt-5 flex items-center justify-between border-t border-line pt-3">
          {clearable ? (
            <button
              type="button"
              className="min-h-9 rounded-chip px-2 text-sm text-ink-soft transition-colors duration-150 hover:bg-sunken hover:text-ink"
              onClick={() => {
                onChange?.({ target: { value: "" } });
                close();
                trigger.current?.focus();
              }}
            >
              Clear
            </button>
          ) : (
            <span />
          )}
          <button
            type="button"
            className="btn btn-primary !min-h-9"
            onClick={() => {
              close();
              trigger.current?.focus();
            }}
          >
            Done
          </button>
        </div>
      </Popover>
    </>
  );
}
