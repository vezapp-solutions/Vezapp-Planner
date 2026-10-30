"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Popover } from "@/components/ui/Popover";
import { Select } from "@/components/ui/Select";
import {
  addDays,
  addMonths,
  displayValue,
  MONTH_NAMES,
  MONTH_SHORT,
  monthGrid,
  pad,
  parseValue,
  todayIso,
  WEEKDAYS,
  type PickerMode,
} from "@/lib/calendar";

export interface PickerChange {
  target: { value: string };
}

const navButton =
  "inline-flex h-8 w-8 items-center justify-center rounded-lg text-ink-soft transition-colors duration-150 hover:bg-sunken hover:text-ink";

function Arrow({ dir }: { dir: "left" | "right" }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d={dir === "left" ? "M12 5l-5 5 5 5" : "M8 5l5 5-5 5"} />
    </svg>
  );
}

/**
 * A calendar drop-down in place of the browser's date, month and date-time inputs. Values are the same
 * strings the inputs gave: YYYY-MM-DD, YYYY-MM and YYYY-MM-DDTHH:mm, and onChange reads `e.target.value`.
 * Keyboard: arrows move by day or week, PageUp/PageDown by month, Enter chooses, Esc closes.
 */
export function DatePicker({
  value,
  onChange,
  mode = "date",
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
  onChange?: (e: PickerChange) => void;
  mode?: PickerMode;
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
  const parsed = parseValue(value);
  const today = todayIso();
  const [open, setOpen] = useState(false);
  const [view, setView] = useState({ y: 2026, m: 1 });
  const [level, setLevel] = useState<"days" | "months">("days");
  const [focus, setFocus] = useState(today);
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);

  function openPicker() {
    if (disabled) return;
    const base = parsed ?? parseValue(today)!;
    setView({ y: base.y, m: base.m });
    setFocus(parsed ? `${base.y}-${pad(base.m)}-${pad(base.d)}` : today);
    setLevel(mode === "month" ? "months" : "days");
    setOpen(true);
  }

  const emit = (next: string) => onChange?.({ target: { value: next } });
  const timePart = `${pad(parsed?.hh ?? 0)}:${pad(parsed?.mm ?? 0)}`;

  function pickDay(iso: string) {
    if (mode === "datetime") emit(`${iso}T${timePart}`);
    else {
      emit(iso);
      setOpen(false);
      trigger.current?.focus();
    }
  }

  function pickMonth(m: number) {
    if (mode === "month") {
      emit(`${view.y}-${pad(m)}`);
      setOpen(false);
      trigger.current?.focus();
    } else {
      setView({ y: view.y, m });
      setLevel("days");
      setFocus(`${view.y}-${pad(m)}-01`);
    }
  }

  function setTime(hh: number, mm: number) {
    const day = parsed ? `${parsed.y}-${pad(parsed.m)}-${pad(parsed.d)}` : today;
    emit(`${day}T${pad(hh)}:${pad(mm)}`);
  }

  function goToDay(iso: string) {
    const p = parseValue(iso)!;
    setFocus(iso);
    setView({ y: p.y, m: p.m });
  }

  function onPanelKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (level !== "days" || !(e.target as HTMLElement).dataset.iso) return;
    const steps: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };
    if (e.key in steps) {
      e.preventDefault();
      goToDay(addDays(focus, steps[e.key]));
    } else if (e.key === "PageUp" || e.key === "PageDown") {
      e.preventDefault();
      const p = parseValue(focus)!;
      const next = addMonths(p.y, p.m, e.key === "PageUp" ? -1 : 1);
      const lastDay = new Date(Date.UTC(next.y, next.m, 0)).getUTCDate();
      goToDay(`${next.y}-${pad(next.m)}-${pad(Math.min(p.d, lastDay))}`);
    }
  }

  // Keep keyboard focus on the highlighted day while the panel is open.
  useEffect(() => {
    if (open && level === "days") panel.current?.querySelector<HTMLElement>(`[data-iso="${focus}"]`)?.focus({ preventScroll: true });
  }, [open, level, focus, view]);

  const text = displayValue(value, mode);
  const minutes = Array.from({ length: 12 }, (_, i) => i * 5);
  if (parsed && !minutes.includes(parsed.mm)) minutes.push(parsed.mm);
  minutes.sort((a, b) => a - b);

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
        onClick={() => (open ? close() : openPicker())}
        className={`field flex items-center justify-between gap-2 text-left transition-[border-color,box-shadow] duration-150 ${ariaInvalid ? "!border-danger" : ""} ${className}`}
      >
        <span className={`min-w-0 truncate font-mono text-sm ${text ? "" : "font-sans text-ink-soft"}`}>
          {text || placeholder || (mode === "month" ? "Pick a month" : "Pick a date")}
        </span>
        <svg aria-hidden="true" viewBox="0 0 20 20" className="h-4 w-4 shrink-0 text-ink-soft" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="4.5" width="14" height="12.5" rx="2.5" />
          <path d="M3 8.5h14M7 2.5v3M13 2.5v3" />
        </svg>
      </button>

      <Popover anchor={trigger} open={open} onClose={close} label={mode === "month" ? "Choose a month" : "Choose a date"} matchWidth={false} onKeyDown={onPanelKeyDown} className="w-[19.5rem] max-w-[calc(100vw-1rem)] p-3">
        <div ref={panel}>
          <div className="mb-2 flex items-center justify-between gap-1">
            <button type="button" className={navButton} aria-label={level === "days" ? "Previous month" : "Previous year"} onClick={() => setView((v) => (level === "days" ? addMonths(v.y, v.m, -1) : { y: v.y - 1, m: v.m }))}>
              <Arrow dir="left" />
            </button>
            {level === "days" ? (
              <button type="button" className="rounded-lg px-2 py-1 text-sm font-semibold transition-colors duration-150 hover:bg-sunken" aria-label={`${MONTH_NAMES[view.m - 1]} ${view.y}, choose a month`} onClick={() => setLevel("months")}>
                {MONTH_NAMES[view.m - 1]} {view.y}
              </button>
            ) : (
              <span className="px-2 py-1 text-sm font-semibold" aria-live="polite">{view.y}</span>
            )}
            <button type="button" className={navButton} aria-label={level === "days" ? "Next month" : "Next year"} onClick={() => setView((v) => (level === "days" ? addMonths(v.y, v.m, 1) : { y: v.y + 1, m: v.m }))}>
              <Arrow dir="right" />
            </button>
          </div>

          {level === "days" ? (
            <div role="grid" aria-label={`${MONTH_NAMES[view.m - 1]} ${view.y}`}>
              <div className="mb-1 grid grid-cols-7 text-center text-xs text-ink-soft" aria-hidden="true">
                {WEEKDAYS.map((d) => (
                  <span key={d} className="py-1">{d}</span>
                ))}
              </div>
              <div className="grid grid-cols-7 gap-y-0.5">
                {monthGrid(view.y, view.m).map((cell) => {
                  const isSelected = parsed !== null && cell.iso === `${parsed.y}-${pad(parsed.m)}-${pad(parsed.d)}`;
                  const isToday = cell.iso === today;
                  return (
                    <button
                      key={cell.iso}
                      type="button"
                      data-iso={cell.iso}
                      tabIndex={cell.iso === focus ? 0 : -1}
                      aria-label={`${cell.day} ${MONTH_NAMES[parseValue(cell.iso)!.m - 1]} ${parseValue(cell.iso)!.y}`}
                      aria-pressed={isSelected}
                      aria-current={isToday ? "date" : undefined}
                      onClick={() => pickDay(cell.iso)}
                      className={`mx-auto flex h-9 w-9 items-center justify-center rounded-full text-sm transition-colors duration-150 ${
                        isSelected
                          ? "bg-action font-semibold text-on-action"
                          : `hover:bg-sunken ${cell.inMonth ? "" : "text-ink-soft/60"} ${isToday ? "font-semibold ring-1 ring-action" : ""}`
                      }`}
                    >
                      {cell.day}
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-1.5">
              {MONTH_SHORT.map((name, i) => {
                const isSelected = parsed !== null && parsed.y === view.y && parsed.m === i + 1;
                return (
                  <button
                    key={name}
                    type="button"
                    aria-label={`${MONTH_NAMES[i]} ${view.y}`}
                    aria-pressed={isSelected}
                    onClick={() => pickMonth(i + 1)}
                    className={`rounded-lg py-2.5 text-sm transition-colors duration-150 ${isSelected ? "bg-action font-semibold text-on-action" : "hover:bg-sunken"}`}
                  >
                    {name}
                  </button>
                );
              })}
            </div>
          )}

          {mode === "datetime" && (
            <div className="mt-3 flex items-center gap-2 border-t border-line pt-3">
              <span className="text-sm text-ink-soft">Time</span>
              <Select aria-label="Hour" className="!min-h-9 !w-20" value={pad(parsed?.hh ?? 0)} onChange={(e) => setTime(Number(e.target.value), parsed?.mm ?? 0)}>
                {Array.from({ length: 24 }, (_, h) => (
                  <option key={h} value={pad(h)}>{pad(h)}</option>
                ))}
              </Select>
              <span aria-hidden="true">:</span>
              <Select aria-label="Minute" className="!min-h-9 !w-20" value={pad(parsed?.mm ?? 0)} onChange={(e) => setTime(parsed?.hh ?? 0, Number(e.target.value))}>
                {minutes.map((m) => (
                  <option key={m} value={pad(m)}>{pad(m)}</option>
                ))}
              </Select>
            </div>
          )}

          <div className="mt-3 flex items-center justify-between border-t border-line pt-2">
            <div className="flex gap-1">
              {mode !== "month" && (
                <button type="button" className="rounded-lg px-2 py-1 text-sm font-medium text-link transition-colors duration-150 hover:bg-sunken" onClick={() => { goToDay(today); pickDay(today); }}>
                  Today
                </button>
              )}
              {clearable && value && (
                <button type="button" className="rounded-lg px-2 py-1 text-sm text-ink-soft transition-colors duration-150 hover:bg-sunken hover:text-ink" onClick={() => { emit(""); close(); trigger.current?.focus(); }}>
                  Clear
                </button>
              )}
            </div>
            {mode === "datetime" && (
              <button type="button" className="btn btn-primary !min-h-8 !px-3 !text-sm" onClick={() => { close(); trigger.current?.focus(); }}>
                Done
              </button>
            )}
          </div>
        </div>
      </Popover>
    </>
  );
}
