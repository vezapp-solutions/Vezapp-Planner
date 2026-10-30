"use client";

import { Children, Fragment, isValidElement, useCallback, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";

import { Popover } from "@/components/ui/Popover";

interface Item {
  value: string;
  label: string;
  disabled: boolean;
}

/** Reads <option> children, including ones inside fragments or produced by .map(). */
function readItems(children: ReactNode): Item[] {
  const items: Item[] = [];
  const walk = (nodes: ReactNode) => {
    Children.forEach(nodes, (child) => {
      if (!isValidElement(child)) return;
      const props = child.props as { value?: string | number; children?: ReactNode; disabled?: boolean };
      if (child.type === Fragment) walk(props.children);
      else if (child.type === "option") {
        const label = Children.toArray(props.children).join("");
        items.push({ value: String(props.value ?? label), label, disabled: Boolean(props.disabled) });
      }
    });
  };
  walk(children);
  return items;
}

export interface SelectChange {
  target: { value: string };
}

/**
 * A drop-in for the browser <select>: the same <option> children and an onChange that reads `e.target.value`,
 * but with a styled, animated list. Keyboard: arrows, Home/End, Enter or Space to choose, Esc to close,
 * and typing to jump to an option.
 */
export function Select({
  value,
  onChange,
  children,
  className = "",
  id,
  disabled = false,
  "aria-label": ariaLabel,
  "aria-invalid": ariaInvalid,
  "aria-describedby": ariaDescribedBy,
}: {
  value: string | number;
  onChange?: (e: SelectChange) => void;
  children: ReactNode;
  className?: string;
  id?: string;
  disabled?: boolean;
  "aria-label"?: string;
  "aria-invalid"?: boolean;
  "aria-describedby"?: string;
}) {
  const items = useMemo(() => readItems(children), [children]);
  const current = String(value ?? "");
  const selected = items.findIndex((i) => i.value === current);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const trigger = useRef<HTMLButtonElement>(null);
  const typed = useRef({ text: "", at: 0 });
  const listId = useId();
  const optionId = (index: number) => `${listId}-o${index}`;

  const close = useCallback(() => setOpen(false), []);

  function openList() {
    if (disabled) return;
    setActive(selected >= 0 ? selected : Math.max(0, items.findIndex((i) => !i.disabled)));
    setOpen(true);
  }

  function choose(index: number) {
    const item = items[index];
    if (!item || item.disabled) return;
    onChange?.({ target: { value: item.value } });
    setOpen(false);
    trigger.current?.focus();
  }

  function move(from: number, step: 1 | -1): number {
    for (let i = from + step; i >= 0 && i < items.length; i += step) if (!items[i].disabled) return i;
    return from;
  }

  function jumpTo(letters: string) {
    const start = open ? active + 1 : Math.max(selected, -1) + 1;
    const order = [...items.keys()].map((i) => (i + start) % items.length);
    const hit = order.find((i) => !items[i].disabled && items[i].label.toLowerCase().startsWith(letters));
    if (hit === undefined) return;
    if (open) setActive(hit);
    else onChange?.({ target: { value: items[hit].value } });
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLButtonElement>) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) openList();
      else setActive((a) => move(a, e.key === "ArrowDown" ? 1 : -1));
    } else if (e.key === "Home" || e.key === "End") {
      if (!open) return;
      e.preventDefault();
      setActive(e.key === "Home" ? move(-1, 1) : move(items.length, -1));
    } else if (e.key === "Enter" || e.key === " ") {
      if (e.key === " " && typed.current.text) return;
      e.preventDefault();
      if (open) choose(active);
      else openList();
    } else if (e.key === "Tab") {
      close();
    } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const now = Date.now();
      typed.current = { text: now - typed.current.at < 700 ? typed.current.text + e.key.toLowerCase() : e.key.toLowerCase(), at: now };
      jumpTo(typed.current.text);
    }
  }

  useEffect(() => {
    if (open) document.getElementById(optionId(active))?.scrollIntoView({ block: "nearest" });
    // optionId is derived from listId, which never changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, active]);

  const shown = selected >= 0 ? items[selected] : undefined;
  const placeholder = shown !== undefined && shown.value === "";

  return (
    <>
      <button
        ref={trigger}
        type="button"
        id={id}
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-activedescendant={open ? optionId(active) : undefined}
        aria-label={ariaLabel}
        aria-invalid={ariaInvalid}
        aria-describedby={ariaDescribedBy}
        disabled={disabled}
        onClick={() => (open ? close() : openList())}
        onKeyDown={onKeyDown}
        className={`field flex items-center justify-between gap-2 text-left transition-[border-color,box-shadow] duration-150 ${className}`}
      >
        <span className={`min-w-0 truncate ${placeholder ? "text-ink-soft" : ""}`}>{shown?.label ?? ""}</span>
        <svg
          aria-hidden="true"
          viewBox="0 0 20 20"
          className={`h-4 w-4 shrink-0 text-ink-soft transition-transform duration-200 ${open ? "rotate-180" : ""}`}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M5 8l5 5 5-5" />
        </svg>
      </button>
      <Popover anchor={trigger} open={open} onClose={close} role="listbox" id={listId} label={ariaLabel} className="max-h-72 max-w-[min(26rem,calc(100vw-1rem))] overflow-y-auto p-1">
        {items.map((item, index) => {
          const isSelected = index === selected;
          return (
            <div
              key={`${item.value}-${index}`}
              id={optionId(index)}
              role="option"
              aria-selected={isSelected}
              aria-disabled={item.disabled || undefined}
              onMouseEnter={() => !item.disabled && setActive(index)}
              onClick={() => choose(index)}
              className={`flex cursor-pointer items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm transition-colors duration-150 ${
                item.disabled ? "cursor-not-allowed opacity-50" : index === active ? "bg-sunken" : ""
              } ${isSelected ? "font-semibold text-link" : ""} ${item.value === "" && !isSelected ? "text-ink-soft" : ""}`}
            >
              <span className="truncate">{item.label}</span>
              {isSelected && (
                <svg aria-hidden="true" viewBox="0 0 20 20" className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 10.5l4 4 8-9" />
                </svg>
              )}
            </div>
          );
        })}
      </Popover>
    </>
  );
}
