"use client";

import { ErrorState } from "@/components/States";

export default function RouteError({ error, reset }: { error: Error; reset: () => void }) {
  return <ErrorState message={error.message || "This screen failed to load."} onRetry={reset} />;
}
