/** The AI sparkle, used on the AI badge and on the header button that opens the assistant. */
export function SparkleIcon({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className={className} fill="currentColor">
      <path d="M12 2l1.9 5.6L19.5 9.5l-5.6 1.9L12 17l-1.9-5.6L4.5 9.5l5.6-1.9L12 2z" />
      <path d="M19 15l.9 2.6 2.6.9-2.6.9L19 22l-.9-2.6-2.6-.9 2.6-.9L19 15z" />
    </svg>
  );
}

/** A solid "AI" pill with a sparkle, so AI-written text is always marked as such. */
export function AiBadge({ label = "AI" }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-action px-2 py-0.5 text-xs font-semibold text-on-action">
      <SparkleIcon />
      {label}
    </span>
  );
}
