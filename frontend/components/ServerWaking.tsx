"use client";

import { useEffect, useState } from "react";

import { retryWake, useServerStatus } from "@/lib/server-status";

/**
 * The friendly screen shown while the server wakes up. It sits over the whole app, says what is happening in
 * plain words, counts the seconds, and goes away by itself when the server answers: nothing to refresh.
 */
export function ServerWaking() {
  const phase = useServerStatus((s) => s.phase);
  const since = useServerStatus((s) => s.since);
  const limited = useServerStatus((s) => s.limited);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (phase === "ok") return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [phase]);

  if (phase === "ok") return null;
  const seconds = since ? Math.max(0, Math.round((now - since) / 1000)) : 0;
  const stuck = phase === "stuck";

  return (
    <div className="fixed inset-0 z-[150] flex items-center justify-center bg-ground/85 px-5 backdrop-blur-sm" role="status" aria-live="polite">
      <div className="panel w-full max-w-md rounded-dialog px-7 py-9 text-center shadow-2xl">
        <div className="relative mx-auto mb-6 flex h-20 w-20 items-center justify-center">
          {!stuck && <span aria-hidden="true" className="wake-ring absolute inset-0 rounded-full" />}
          <span aria-hidden="true" className="relative flex h-20 w-20 items-center justify-center rounded-full bg-brand-wash">
            {/* eslint-disable-next-line @next/next/no-img-element -- a small fixed brand mark */}
            <img src="/brand/vezapp-v-deep.png" alt="" width={44} height={35} className={`h-9 w-auto ${stuck ? "" : "wake-pulse"}`} />
          </span>
        </div>

        <h2 className="font-display text-2xl font-bold tracking-tight">{stuck ? "Still starting up" : "Waking up the server"}</h2>
        <p className="mt-3 text-[0.9375rem] leading-relaxed text-ink-soft">
          {stuck
            ? "The server is taking longer than usual. It is still worth waiting a little, or you can try again."
            : "Vezapp's free server takes a nap when nobody has used it for a while. It usually wakes in under a minute. You don't need to refresh: this page carries on by itself."}
        </p>

        {stuck ? (
          <button type="button" className="btn btn-primary mt-6" onClick={retryWake}>
            Try again
          </button>
        ) : (
          <>
            <div className="wake-bar mt-6" aria-hidden="true">
              <span />
            </div>
            <p className="mt-3 font-mono text-xs text-ink-soft">Waiting {seconds}s</p>
            {limited && (
              <p className="mt-3 text-xs leading-relaxed text-ink-soft">
                The hosting service is limiting how often we can ask it to wake, so we are waiting a little longer between tries.
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
