"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { ApiError } from "@/lib/api";
import { APP_NAME } from "@/lib/constants";
import { useSession } from "@/lib/store";

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
    <div className="grid min-h-dvh lg:grid-cols-[1fr_30rem]">
      <section aria-hidden="true" className="scene hidden flex-col justify-between p-12 lg:flex">
        <Logo height={34} onDark />
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-[#ff9a68]">Finite-capacity planning</p>
          <p className="mt-4 font-display text-[3.5rem] font-bold leading-[1.02] tracking-tight">
            Plan the pour
            <br />
            before the shift
            <br />
            starts.
          </p>
          <p className="mt-6 max-w-md text-[1.0625rem] leading-relaxed text-[#b9c6c2]">
            Moulds and melts for iron and steel sand-casting foundries, planned against the hours
            and furnaces your plant really has.
          </p>
        </div>
        {/* Machine load over the next fourteen working days: tall bars run hot. */}
        <div>
          <div className="flex items-end gap-2" style={{ height: 96 }}>
            {[38, 52, 61, 48, 74, 88, 66, 42, 57, 81, 93, 70, 55, 46].map((h, i) => (
              <span
                key={i}
                className="heat-bar flex-1 rounded-t-md"
                style={{
                  height: `${h}%`,
                  animationDelay: `${i * 55}ms`,
                  background: h > 85 ? "linear-gradient(180deg, #ff7a3d, #e8541a)" : h > 65 ? "linear-gradient(180deg, #ffb347, #e8541a 140%)" : "linear-gradient(180deg, #1ce4d4, #0a6b63)",
                }}
              />
            ))}
          </div>
          <p className="mt-3 font-mono text-[0.6875rem] uppercase tracking-[0.18em] text-[#8fa09b]">Machine load · next 14 working days</p>
        </div>
      </section>

      <main className="canvas flex flex-col px-5 py-6 sm:px-10">
        <div className="flex items-center justify-between lg:justify-end">
          <span className="lg:hidden">
            <Logo height={28} priority />
          </span>
          <ThemeToggle />
        </div>

        <div className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center py-10">
          <span className="page-tick" aria-hidden="true" />
          <h1 className="font-display text-4xl font-bold tracking-tight">Sign in</h1>
          <p className="mt-1.5 text-[0.9375rem] text-ink-soft">to {APP_NAME}</p>

          <form onSubmit={submit} className="mt-8 space-y-5" noValidate>
            <div>
              <label htmlFor="username" className="mb-1.5 block text-sm font-medium">
                Username
              </label>
              <input
                id="username"
                name="username"
                className="field"
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
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-invalid={error ? true : undefined}
                disabled={busy}
                required
              />
            </div>

            <div id="login-error" role="alert" aria-live="assertive">
              {error && (
                <p className="rounded-md border border-danger bg-danger-wash px-3 py-2 text-sm">
                  {error}
                </p>
              )}
            </div>

            <button
              type="submit"
              className="btn btn-primary w-full"
              disabled={busy || !username.trim() || !password}
            >
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-ink-soft">Vezapp Solutions LLP</p>
      </main>
    </div>
  );
}
