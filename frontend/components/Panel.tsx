import type { ReactNode } from "react";

export function Panel({
  title,
  note,
  actions,
  children,
}: {
  title: string;
  note?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="panel">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 border-b border-line px-4 py-2.5">
        <h2 className="font-display text-lg font-semibold">{title}</h2>
        <div className="flex items-center gap-3">
          {note && <span className="font-mono text-xs text-ink-soft">{note}</span>}
          {actions}
        </div>
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}
