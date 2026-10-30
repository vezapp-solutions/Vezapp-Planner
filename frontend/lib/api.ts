// Same-origin API client. Auth lives in httpOnly cookies, so there is no token handling here.
// A 401 triggers one silent refresh and a retry before the caller sees the failure.

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

function request(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  for (const [key, value] of Object.entries(CLIENT_HEADER)) headers.set(key, value);
  if (actingCompanyId) headers.set("X-Company-Id", String(actingCompanyId));
  return fetch(`/api/v1${path}`, { ...init, credentials: "same-origin", headers });
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

function messageFrom(body: unknown, status: number): string {
  if (body && typeof body === "object") {
    const record = body as Record<string, unknown>;
    if (typeof record.detail === "string") return record.detail;
    for (const [field, value] of Object.entries(record)) {
      const text = Array.isArray(value) ? value.join(" ") : String(value);
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
    return fetch(`/api/v1${path}`, { method: "POST", body: form, credentials: "same-origin", headers });
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
  const response = await fetch(`/api/v1${path}`, {
    method: form ? "POST" : "GET",
    body: form,
    credentials: "same-origin",
    headers,
  });
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
    out[key] = Array.isArray(value) ? value.map(String).join(" ") : JSON.stringify(value);
  }
  return out;
}
