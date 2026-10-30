"use client";

import { useId, useRef, type KeyboardEvent, type ReactNode } from "react";

export interface TabSpec {
  id: string;
  label: string;
}

export function Tabs({
  tabs,
  active,
  onChange,
  children,
}: {
  tabs: TabSpec[];
  active: string;
  onChange: (id: string) => void;
  children: ReactNode;
}) {
  const base = useId();
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  function onKey(e: KeyboardEvent, index: number) {
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = tabs[(index + step + tabs.length) % tabs.length];
    onChange(next.id);
    refs.current[next.id]?.focus();
  }

  return (
    <div>
      <div role="tablist" aria-label="Sections" className="mb-5 flex gap-1 overflow-x-auto border-b border-line">
        {tabs.map((t, i) => (
          <button
            key={t.id}
            ref={(el) => {
              refs.current[t.id] = el;
            }}
            role="tab"
            id={`${base}-tab-${t.id}`}
            aria-selected={active === t.id}
            aria-controls={`${base}-panel`}
            tabIndex={active === t.id ? 0 : -1}
            onClick={() => onChange(t.id)}
            onKeyDown={(e) => onKey(e, i)}
            className={`-mb-px min-h-10 shrink-0 border-b-[3px] px-3 text-sm ${
              active === t.id ? "border-brand font-semibold" : "border-transparent text-ink-soft hover:text-ink"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`${base}-panel`} aria-labelledby={`${base}-tab-${active}`}>
        {children}
      </div>
    </div>
  );
}
