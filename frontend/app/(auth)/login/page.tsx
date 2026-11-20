"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { ApiError } from "@/lib/api";
import { APP_NAME } from "@/lib/constants";
import { useSession } from "@/lib/store";

/** Machine load over the next fourteen working days: tall bars run hot. */
const LOAD = [38, 52, 61, 48, 74, 88, 66, 42, 57, 81, 93, 70, 55, 46];

export default function LoginPage() {
  const router = useRouter();
  const { status, load, login } = useSession();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (status === "loading") void load();
    if (status === "authed") router.replace("/home");
  }, [status, load, router]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username.trim(), password);
      router.replace("/home");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Cannot reach the server. Check that the backend is running.",
      );
      setBusy(false);
    }
  }

  return (
    <div className="relative grid min-h-dvh overflow-x-hidden bg-surface lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
      <div className="absolute right-4 top-4 z-10 lg:right-6 lg:top-5">
        <ThemeToggle />
      </div>

      {/* Left: the form */}
      <main className="flex min-h-dvh flex-col px-6 py-6 sm:px-10 lg:px-16 lg:py-8">
        <Logo height={28} priority />

        <div className="mx-auto flex w-full max-w-[22rem] flex-1 flex-col justify-center py-10">
          <h1 className="text-center font-display text-[1.75rem] font-bold tracking-tight">Sign into your account</h1>
          <p className="mt-2 text-center text-[0.9375rem] text-ink-soft">
            Welcome back to {APP_NAME}. Plan moulds and melting against the hours your plant really has.
          </p>

          <form onSubmit={submit} className="mt-9 space-y-5" noValidate>
            <div>
              <label htmlFor="username" className="mb-1.5 block text-sm font-medium">
                Username
              </label>
              <input
                id="username"
                name="username"
                className="field"
                placeholder="Enter your username"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? "login-error" : undefined}
                disabled={busy}
                required
              />
            </div>
            <div>
              <label htmlFor="password" className="mb-1.5 block text-sm font-medium">
                Password
              </label>
              <input
                id="password"
                name="password"
                type="password"
                className="field"
                placeholder="••••••••"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-invalid={error ? true : undefined}
                disabled={busy}
                required
              />
            </div>

            <div id="login-error" role="alert" aria-live="assertive">
              {error && <p className="rounded-card border border-danger bg-danger-wash px-3 py-2 text-sm">{error}</p>}
            </div>

            <button type="submit" className="btn btn-ink w-full" disabled={busy || !username.trim() || !password}>
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-ink-soft">
            Can&apos;t sign in? <span className="font-semibold text-ink">Ask your company administrator</span> to reset your password.
          </p>
        </div>

        <p className="text-center text-sm text-ink-soft">
          No account yet? <span className="font-semibold text-ink">Accounts are created by your administrator.</span>
        </p>
      </main>

      {/* Right: a large rounded card that runs off the edge of the window, with a soft halftone shadow beneath */}
      <aside aria-hidden="true" className="relative hidden lg:flex lg:items-center lg:pb-28 lg:pt-24">
        <div className="relative w-full">
          <div className="scene relative min-h-[max(36rem,calc(100dvh-16rem))] rounded-l-dialog shadow-[0_40px_80px_-40px_rgb(0_0_0/0.55)]">
            <div className="flex min-h-[inherit] flex-col justify-between gap-10 p-10 xl:p-12">
              <div>
                <p className="font-mono text-xs uppercase tracking-[0.2em] text-[#ff9a68]">Finite-capacity planning</p>
                <p className="mt-4 max-w-md font-display text-[2.75rem] font-bold leading-[1.04] tracking-tight xl:text-[3.25rem]">
                  Plan the pour before the shift starts.
                </p>
              </div>

              <div>
                <div className="flex items-end gap-2" style={{ height: 110 }}>
                  {LOAD.map((h, i) => (
                    <span
                      key={i}
                      className="heat-bar flex-1 rounded-t-chip"
                      style={{
                        height: `${h}%`,
                        animationDelay: `${i * 55}ms`,
                        background: h > 85 ? "linear-gradient(180deg, #ff7a3d, #e8541a)" : h > 65 ? "linear-gradient(180deg, #ffb347, #e8541a 140%)" : "linear-gradient(180deg, #1ce4d4, #00464a)",
                      }}
                    />
                  ))}
                </div>
                <div className="mt-6 flex flex-wrap gap-2">
                  {["Mould plan", "Melt plan", "What-if", "AI insights"].map((t) => (
                    <span key={t} className="rounded-full border border-white/20 bg-white/5 px-3.5 py-1 text-sm text-[#d6dfdc]">
                      {t}
                    </span>
                  ))}
                </div>
                <div className="mt-5 flex items-center gap-3.5">
                  <span className="flex h-11 w-11 flex-none items-center justify-center rounded-full bg-white/15 text-white">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                      <path d="M12 2l1.9 5.6L19.5 9.5l-5.6 1.9L12 17l-1.9-5.6L4.5 9.5l5.6-1.9L12 2z" />
                    </svg>
                  </span>
                  <p className="leading-snug">
                    <span className="block font-semibold text-white">Machine load, next 14 working days</span>
                    <span className="block text-sm text-[#b9c6c2]">Tall bars run hot. Orders that cannot make their date are flagged with the reason.</span>
                  </p>
                </div>
              </div>
            </div>
          </div>
          <div className="halftone" />
        </div>
      </aside>
    </div>
  );
}
