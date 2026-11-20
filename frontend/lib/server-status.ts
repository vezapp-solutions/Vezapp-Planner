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
  /** The host is turning wake-up requests away (HTTP 429), so we are waiting longer between tries. */
  limited: boolean;
}

export const useServerStatus = create<ServerStatus>(() => ({ phase: "ok", since: null, limited: false }));

const HEALTH_URL = "/api/v1/health";
const POLL_EVERY_MS = 2000;
/** When the host rate-limits wake-ups, knock less often: 8s, 16s, then 30s between tries. */
const LIMITED_BACKOFF_MS = [8000, 16_000, 30_000];
const PROBE_TIMEOUT_MS = 8000;
/** How long we keep asking before we say the server is stuck. Render takes up to about a minute. */
export const MAX_WAIT_MS = 180_000;

export function markWaking() {
  useServerStatus.setState((s) => (s.phase === "waking" ? s : { phase: "waking", since: s.since ?? Date.now(), limited: s.limited }));
}

export function markAwake() {
  useServerStatus.setState((s) => (s.phase === "ok" && s.since === null && !s.limited ? s : { phase: "ok", since: null, limited: false }));
}

function markLimited(limited: boolean) {
  useServerStatus.setState((s) => (s.limited === limited ? s : { limited }));
}

/** True when a response came from our API rather than from the sleeping host or a proxy in front of it. */
export function isFromApi(response: Response): boolean {
  return response.headers.has("x-vezapp-api");
}

/**
 * An answer our API did not write, that says the host is asleep, starting or unreachable: any 5xx, a 429 (Render
 * turns requests away with "hibernate-rate-limited" while a sleeping service is being woken too often), or any
 * response stamped by Render's own routing layer. Our API's own errors carry the marker header and never match.
 */
export function isHostFailure(response: Response): boolean {
  if (isFromApi(response)) return false;
  return response.status >= 500 || response.status === 429 || response.headers.has("x-render-routing");
}

type Probe = "awake" | "asleep" | "limited";

/** One quick look: does the API answer? Any answer from the app counts, even "degraded". */
async function probe(): Promise<Probe> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
  try {
    const response = await fetch(HEALTH_URL, { cache: "no-store", signal: controller.signal });
    if (isFromApi(response)) return "awake";
    if (response.status === 429) return "limited";
    // An older API without the marker header: its health answer is JSON with a "status" field.
    const body = (await response.json().catch(() => null)) as { status?: unknown } | null;
    return typeof body?.status === "string" ? "awake" : "asleep";
  } catch {
    return "asleep";
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
    let limitedTries = 0;
    try {
      for (;;) {
        const result = await probe();
        if (result === "awake") {
          markAwake();
          return true;
        }
        markLimited(result === "limited");
        if (Date.now() - started > MAX_WAIT_MS) {
          useServerStatus.setState({ phase: "stuck" });
          return false;
        }
        const pause = result === "limited" ? LIMITED_BACKOFF_MS[Math.min(limitedTries++, LIMITED_BACKOFF_MS.length - 1)] : POLL_EVERY_MS;
        await new Promise((resolve) => setTimeout(resolve, pause));
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
  if ((await probe()) !== "awake") void waitUntilAwake();
}

/** The Try again button on the "stuck" message. */
export function retryWake() {
  useServerStatus.setState({ phase: "waking", since: Date.now(), limited: false });
  void waitUntilAwake();
}
