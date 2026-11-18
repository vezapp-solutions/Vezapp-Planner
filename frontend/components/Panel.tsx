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
    <section className="panel overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 px-6 pb-1 pt-5">
        <h2 className="font-display text-[1.0625rem] font-semibold tracking-tight">{title}</h2>
        <div className="flex items-center gap-3">
          {note && <span className="rounded-full bg-sunken px-3 py-1 font-mono text-xs text-ink-soft">{note}</span>}
          {actions}
        </div>
      </div>
      <div className="px-6 pb-6 pt-4">{children}</div>
    </section>
  );
}
