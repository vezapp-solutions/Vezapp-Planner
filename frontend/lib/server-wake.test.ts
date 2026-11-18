import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, ApiError, post } from "./api";
import { useServerStatus } from "./server-status";

const APP = { "X-Vezapp-API": "1", "Content-Type": "application/json" };
const json = (body: unknown, status = 200, headers: Record<string, string> = APP) => new Response(JSON.stringify(body), { status, headers });
/** What a sleeping host or proxy sends: an error page that does not carry our marker header. */
const hostError = (status = 502) => new Response("<html>bad gateway</html>", { status, headers: { "Content-Type": "text/html" } });

let fetchMock: ReturnType<typeof vi.fn>;
const urls = () => fetchMock.mock.calls.map((c) => String(c[0]).replace("/api/v1", ""));

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  useServerStatus.setState({ phase: "ok", since: null });
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("a sleeping server", () => {
  it("waits for the server to wake, then repeats the request and returns its answer", async () => {
    fetchMock
      .mockResolvedValueOnce(hostError(502)) // the request: the host is asleep
      .mockResolvedValueOnce(json({ status: "ok", app: "Vezapp Planner" })) // the health check: awake
      .mockResolvedValueOnce(json({ hello: "world" })); // the request again
    await expect(api("/plans/latest")).resolves.toEqual({ hello: "world" });
    expect(urls()).toEqual(["/plans/latest", "/health", "/plans/latest"]);
    expect(useServerStatus.getState().phase).toBe("ok");
  });

  it("shows the waking state while it waits and keeps asking until the server answers", async () => {
    vi.useFakeTimers();
    fetchMock
      .mockResolvedValueOnce(hostError(503))
      .mockResolvedValueOnce(hostError(502)) // health: still asleep
      .mockResolvedValueOnce(hostError(502)) // health: still asleep
      .mockResolvedValueOnce(json({ status: "ok" })) // health: awake
      .mockResolvedValueOnce(json([1, 2]));
    const pending = api("/parts");
    await vi.advanceTimersByTimeAsync(100);
    expect(useServerStatus.getState().phase).toBe("waking");
    await vi.advanceTimersByTimeAsync(2100);
    expect(useServerStatus.getState().phase).toBe("waking");
    await vi.advanceTimersByTimeAsync(2100);
    await expect(pending).resolves.toEqual([1, 2]);
    expect(useServerStatus.getState().phase).toBe("ok");
  });

  it("treats a network failure like a sleeping server", async () => {
    fetchMock
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(json({ status: "ok" }))
      .mockResolvedValueOnce(json({ ok: true }));
    await expect(api("/customers")).resolves.toEqual({ ok: true });
  });

  it("does not run a saving request twice when it may already have reached the server", async () => {
    fetchMock
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(json({ status: "ok" }));
    const failure = post("/customers", { code: "X" });
    await expect(failure).rejects.toBeInstanceOf(ApiError);
    await expect(failure).rejects.toMatchObject({ status: 503, message: expect.stringContaining("try that again") });
    expect(urls().filter((u) => u === "/customers")).toHaveLength(1); // sent once, never repeated
  });

  it("does repeat a saving request when the host refused it outright (it never reached the app)", async () => {
    fetchMock
      .mockResolvedValueOnce(hostError(502))
      .mockResolvedValueOnce(json({ status: "ok" }))
      .mockResolvedValueOnce(json({ id: 7 }, 201));
    await expect(post("/customers", { code: "X" })).resolves.toEqual({ id: 7 });
    expect(urls().filter((u) => u === "/customers")).toHaveLength(2);
  });

  it("does not mistake an error the app itself returned for a sleeping server", async () => {
    fetchMock.mockResolvedValueOnce(json({ detail: "Something broke." }, 500));
    await expect(api("/plans")).rejects.toMatchObject({ status: 500, message: "Something broke." });
    expect(urls()).toEqual(["/plans"]); // no health check, no waiting
    expect(useServerStatus.getState().phase).toBe("ok");
  });

  it("reports a host error that remains after the server is awake instead of looping", async () => {
    fetchMock
      .mockResolvedValueOnce(hostError(502))
      .mockResolvedValueOnce(json({ status: "ok" }))
      .mockResolvedValueOnce(hostError(502));
    await expect(api("/plans")).rejects.toBeInstanceOf(ApiError);
    expect(urls()).toEqual(["/plans", "/health", "/plans"]);
  });

  it("recognises an older API that has no marker header by its health answer", async () => {
    fetchMock
      .mockResolvedValueOnce(hostError(502))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "ok", app: "Vezapp Planner" }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(json({ fine: true }));
    await expect(api("/plans")).resolves.toEqual({ fine: true });
  });
});
