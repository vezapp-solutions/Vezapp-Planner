// Same-origin API client. Auth lives in httpOnly cookies, so there is no token handling here.
// A 401 triggers one silent refresh and a retry before the caller sees the failure.
// A sleeping server (Render's free plan) is handled in `guarded`: wait for it to wake, then carry on.

import { checkWhySlow, isFromApi, isHostFailure, markAwake, waitUntilAwake } from "./server-status";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body: unknown = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const CLIENT_HEADER = { "X-VP-Client": "web" };

// A Vezapp Admin has no company of their own and acts for one client at a time.
let actingCompanyId: number | null = null;
export function setActingCompany(id: number | null) {
  actingCompanyId = id;
}

/** A request that takes this long makes us check whether the server is the reason. */
const SLOW_AFTER_MS = 5000;

/**
 * Send a request and cope with a sleeping server. If the host answers with an error our API did not write (or
 * not at all), the server is asleep or starting: show the "waking up" message, ask until it answers, then send
 * the request again. A request that only changes data is repeated just when the server cannot have received
 * it, so nothing is ever saved twice.
 */
async function guarded(run: () => Promise<Response>, safeToRepeat: boolean): Promise<Response> {
  const slow = setTimeout(() => void checkWhySlow(), SLOW_AFTER_MS);
  let woke = false;
  try {
    for (;;) {
      let response: Response | null = null;
      try {
        response = await run();
      } catch (error) {
        // The person's own connection is down, or we already waited and it still fails: say so.
        if (woke || (typeof navigator !== "undefined" && navigator.onLine === false)) throw error;
      }
      if (response && !isHostFailure(response)) {
        if (isFromApi(response)) markAwake();
        return response;
      }
      if (response && woke) return response; // awake, yet the host still reports an error: pass it on
      if (!(await waitUntilAwake())) {
        throw new ApiError(503, "The server is taking longer than usual to start. Please try again in a minute.");
      }
      woke = true;
      // A request that timed out on the way may still have reached the server, so do not run it twice.
      const mayHaveArrived = !response || response.status === 504;
      if (!safeToRepeat && mayHaveArrived) {
        throw new ApiError(503, "The server was asleep and has just woken up. Please try that again.");
      }
    }
  } finally {
    clearTimeout(slow);
  }
}

function request(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  for (const [key, value] of Object.entries(CLIENT_HEADER)) headers.set(key, value);
  if (actingCompanyId) headers.set("X-Company-Id", String(actingCompanyId));
  const method = (init.method ?? "GET").toUpperCase();
  const safe = method === "GET" || method === "HEAD" || path.startsWith("/auth/");
  return guarded(() => fetch(`/api/v1${path}`, { ...init, credentials: "same-origin", headers }), safe);
}

let refreshing: Promise<boolean> | null = null;

function refreshSession(): Promise<boolean> {
  refreshing ??= request("/auth/refresh", { method: "POST" })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

/**
 * Turn any error value the server sends (text, a list, a nested object such as { operations: { 6: { time_value:
 * [...] } } }) into one readable sentence. A numbered key (a position in a list) is left out of the text.
 */
export function errorText(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map(errorText).filter(Boolean).join(" ");
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, inner]) => {
        const text = errorText(inner);
        return /^\d+$/.test(key) || key === "non_field_errors" ? text : `${key}: ${text}`;
      })
      .filter(Boolean)
      .join(" ");
  }
  return String(value);
}

function messageFrom(body: unknown, status: number): string {
  if (body && typeof body === "object") {
    const record = body as Record<string, unknown>;
    if (typeof record.detail === "string") return record.detail;
    const entries = Object.entries(record);
    if (entries.length > 0) {
      const [field, value] = entries[0];
      const text = errorText(value);
      return field === "non_field_errors" ? text : `${field}: ${text}`;
    }
  }
  return status >= 500 ? "The server had a problem. Try again." : `Request failed (${status}).`;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response = await request(path, init);
  if (response.status === 401 && !path.startsWith("/auth/")) {
    if (await refreshSession()) response = await request(path, init);
  }
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, messageFrom(body, response.status), body);
  return body as T;
}

const withBody = (method: string, data?: unknown): RequestInit => ({
  method,
  body: data === undefined ? undefined : JSON.stringify(data),
});

export const post = <T>(path: string, data?: unknown) => api<T>(path, withBody("POST", data));
export const put = <T>(path: string, data?: unknown) => api<T>(path, withBody("PUT", data));
export const patch = <T>(path: string, data?: unknown) => api<T>(path, withBody("PATCH", data));
export const del = (path: string) => api<void>(path, { method: "DELETE" });

/** POST a file (multipart). The browser sets the multipart boundary, so no JSON content type. */
export async function upload<T>(path: string, form: FormData): Promise<T> {
  const send = () => {
    const headers = new Headers(CLIENT_HEADER);
    if (actingCompanyId) headers.set("X-Company-Id", String(actingCompanyId));
    return guarded(() => fetch(`/api/v1${path}`, { method: "POST", body: form, credentials: "same-origin", headers }), false);
  };
  let response = await send();
  if (response.status === 401 && (await refreshSession())) response = await send();
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, messageFrom(body, response.status), body);
  return body as T;
}

/** Fetch a file and hand it to the browser as a download. */
export async function download(path: string, filename: string, form?: FormData): Promise<void> {
  const headers = new Headers(CLIENT_HEADER);
  if (actingCompanyId) headers.set("X-Company-Id", String(actingCompanyId));
  const response = await guarded(
    () => fetch(`/api/v1${path}`, { method: form ? "POST" : "GET", body: form, credentials: "same-origin", headers }),
    true, // building a report changes nothing, so repeating it is safe
  );
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, messageFrom(body, response.status), body);
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/** Field errors from a 400, keyed by field, when the server sent them that way. */
export function fieldErrors(err: unknown): Record<string, string> {
  if (!(err instanceof ApiError) || !err.body || typeof err.body !== "object") return {};
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(err.body as Record<string, unknown>)) {
    out[key] = errorText(value);
  }
  return out;
}
