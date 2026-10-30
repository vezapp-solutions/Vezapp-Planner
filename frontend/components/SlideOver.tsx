"use client";

import { useEffect, useId, type ReactNode } from "react";

/** A panel that slides in from the right (full screen on a phone) for editing one record. */
export function SlideOver({
  title,
  subtitle,
  onClose,
  footer,
  children,
  wide = false,
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  footer?: ReactNode;
  children: ReactNode;
  wide?: boolean;
}) {
  const titleId = useId();

  useEffect(() => {
    const close = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", close);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", close);
      document.body.style.overflow = previous;
    };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-labelledby={titleId}>
      <button type="button" className="absolute inset-0 bg-black/50" aria-label="Close panel" onClick={onClose} tabIndex={-1} />
      <div
        className={`slide-in relative flex h-full w-full flex-col border-l border-line bg-surface ${wide ? "sm:max-w-3xl" : "sm:max-w-xl"}`}
      >
        <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-3">
          <div className="min-w-0">
            <h2 id={titleId} className="font-display text-xl font-semibold">
              {title}
            </h2>
            {subtitle && <p className="truncate text-sm text-ink-soft">{subtitle}</p>}
          </div>
          <button type="button" className="btn btn-quiet !min-h-9" onClick={onClose}>
            Close
          </button>
        </header>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && <footer className="flex flex-wrap items-center gap-2 border-t border-line px-5 py-3">{footer}</footer>}
      </div>
    </div>
  );
}
