import { create } from "zustand";

/**
 * The free Render plan puts the API to sleep when nobody uses it, and the first request after that waits a
 * minute while it starts. This keeps track of that so the screen can say so kindly, and so the app can carry
 * on by itself once the server answers.
 *
 *   ok      the server answers (or we have not seen a problem)
 *   waking  the server did not answer; we are asking it every few seconds
 *   stuck   it has been more than a few minutes; the person can press Try again
 */
export type ServerPhase = "ok" | "waking" | "stuck";

interface ServerStatus {
  phase: ServerPhase;
  /** When we first noticed the server was asleep (ms since 1970), for the "waiting N seconds" line. */
  since: number | null;
}

export const useServerStatus = create<ServerStatus>(() => ({ phase: "ok", since: null }));

const HEALTH_URL = "/api/v1/health";
const POLL_EVERY_MS = 2000;
const PROBE_TIMEOUT_MS = 8000;
/** How long we keep asking before we say the server is stuck. Render takes up to about a minute. */
export const MAX_WAIT_MS = 180_000;

export function markWaking() {
  useServerStatus.setState((s) => (s.phase === "waking" ? s : { phase: "waking", since: s.since ?? Date.now() }));
}

export function markAwake() {
  useServerStatus.setState((s) => (s.phase === "ok" && s.since === null ? s : { phase: "ok", since: null }));
}

/** True when a response came from our API rather than from the sleeping host or a proxy in front of it. */
export function isFromApi(response: Response): boolean {
  return response.headers.has("x-vezapp-api");
}

/** A 5xx that our API did not write: the host is asleep, starting, or unreachable. */
export function isHostFailure(response: Response): boolean {
  return response.status >= 500 && !isFromApi(response);
}

/** One quick look: does the API answer? Any answer from the app counts, even "degraded". */
async function probe(): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
  try {
    const response = await fetch(HEALTH_URL, { cache: "no-store", signal: controller.signal });
    if (isFromApi(response)) return true;
    // An older API without the marker header: its health answer is JSON with a "status" field.
    const body = (await response.json().catch(() => null)) as { status?: unknown } | null;
    return typeof body?.status === "string";
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

let polling: Promise<boolean> | null = null;

/**
 * Ask the server until it answers, then resolve true. Resolves false after MAX_WAIT_MS (and the status becomes
 * "stuck"). Many requests can be waiting at once; they all share one poll.
 */
export function waitUntilAwake(): Promise<boolean> {
  polling ??= (async () => {
    markWaking();
    const started = Date.now();
    try {
      for (;;) {
        if (await probe()) {
          markAwake();
          return true;
        }
        if (Date.now() - started > MAX_WAIT_MS) {
          useServerStatus.setState({ phase: "stuck" });
          return false;
        }
        await new Promise((resolve) => setTimeout(resolve, POLL_EVERY_MS));
      }
    } finally {
      polling = null;
    }
  })();
  return polling;
}

/**
 * A request has been pending for a while. Before saying anything, check whether the server is the reason: if it
 * answers quickly, the request is merely slow and the person sees nothing.
 */
export async function checkWhySlow(): Promise<void> {
  if (useServerStatus.getState().phase !== "ok") return;
  if (!(await probe())) void waitUntilAwake();
}

/** The Try again button on the "stuck" message. */
export function retryWake() {
  useServerStatus.setState({ phase: "waking", since: Date.now() });
  void waitUntilAwake();
}
