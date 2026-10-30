import type { ReactNode } from "react";

export function LoadingState({ label = "Loading", rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div role="status" aria-live="polite" className="space-y-3">
      <span className="sr-only">{label}…</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton h-5" style={{ width: `${92 - i * 14}%` }} />
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-md border border-dashed border-line px-4 py-6">
      <p className="font-medium">{title}</p>
      {children && <p className="mt-1 max-w-prose text-sm text-ink-soft">{children}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div role="alert" className="rounded-md border border-danger bg-danger-wash px-4 py-4">
      <p className="font-medium text-danger">{title}</p>
      <p className="mt-1 text-sm">{message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="btn btn-quiet mt-3">
          Try again
        </button>
      )}
    </div>
  );
}

/** A short inline error line (a failed action), not a whole-section failure. */
export function FormErrorLine({ message }: { message: string }) {
  return (
    <p role="alert" className="rounded-md border border-danger bg-danger-wash px-3 py-2 text-sm">
      {message}
    </p>
  );
}

export function PageHeader({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-3 border-b border-line pb-4">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-0.5 text-sm text-ink-soft">{subtitle}</p>}
      </div>
      {children}
    </header>
  );
}
