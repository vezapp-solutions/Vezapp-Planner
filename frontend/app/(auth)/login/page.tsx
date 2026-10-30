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
    <div className="grid min-h-dvh lg:grid-cols-[1fr_28rem]">
      <section
        aria-hidden="true"
        className="relative hidden flex-col justify-between border-r border-line bg-sunken p-10 lg:flex"
      >
        <Logo height={40} />
        <div>
          <p className="font-display text-4xl font-semibold leading-tight tracking-tight">
            Plan the pour
            <br />
            before the shift starts.
          </p>
          <p className="mt-4 max-w-md text-ink-soft">
            Finite-capacity planning for iron and steel sand-casting foundries: cores, moulding,
            melting, fettling and dispatch against the hours your plant really has.
          </p>
        </div>
        {/* Fourteen day ticks: the same strip the home screen uses for the bottleneck forecast. */}
        <div className="flex items-end gap-3" style={{ height: 28 }}>
          {Array.from({ length: 14 }, (_, i) => (
            <span
              key={i}
              className="border-l-2 border-ink-soft"
              style={{ height: i % 7 === 6 ? 28 : i % 7 === 5 ? 14 : 20 }}
            />
          ))}
        </div>
      </section>

      <main className="flex flex-col px-5 py-6 sm:px-10">
        <div className="flex items-center justify-between lg:justify-end">
          <span className="lg:hidden">
            <Logo height={32} priority />
          </span>
          <ThemeToggle />
        </div>

        <div className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center py-10">
          <h1 className="font-display text-3xl font-semibold tracking-tight">Sign in</h1>
          <p className="mt-1 text-sm text-ink-soft">to {APP_NAME}</p>

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
