import { create } from "zustand";

import { ApiError, api, post, setActingCompany } from "./api";
import type { Me } from "./types";

type SessionStatus = "loading" | "authed" | "anon" | "error";

interface SessionState {
  user: Me | null;
  status: SessionStatus;
  error: string | null;
  /** Vezapp Admin only: the client company being worked on. */
  actingCompanyId: number | null;
  chooseCompany: (id: number | null) => void;
  load: () => Promise<void>;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const ACTING_KEY = "vp-acting-company";

function savedCompany(): number | null {
  try {
    const raw = localStorage.getItem(ACTING_KEY);
    return raw && /^\d+$/.test(raw) ? Number(raw) : null;
  } catch {
    return null;
  }
}

export const useSession = create<SessionState>((set) => ({
  user: null,
  status: "loading",
  error: null,
  actingCompanyId: null,

  chooseCompany(id) {
    setActingCompany(id);
    try {
      if (id) localStorage.setItem(ACTING_KEY, String(id));
      else localStorage.removeItem(ACTING_KEY);
    } catch {
      // Storage can be blocked; the choice then lasts for this visit only.
    }
    set({ actingCompanyId: id });
  },

  async load() {
    try {
      const user = await api<Me>("/me");
      const acting = user.role === "vezapp_admin" ? savedCompany() : null;
      setActingCompany(acting);
      set({ user, status: "authed", error: null, actingCompanyId: acting });
    } catch (err) {
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
        set({ user: null, status: "anon", error: null });
      } else {
        set({ status: "error", error: "Cannot reach the server. Check that the backend is running." });
      }
    }
  },

  async login(username, password) {
    const user = await post<Me>("/auth/login", { username, password });
    const acting = user.role === "vezapp_admin" ? savedCompany() : null;
    setActingCompany(acting);
    set({ user, status: "authed", error: null, actingCompanyId: acting });
  },

  async logout() {
    try {
      await post("/auth/logout");
    } finally {
      setActingCompany(null);
      set({ user: null, status: "anon", error: null, actingCompanyId: null });
    }
  },
}));

type Theme = "light" | "dark";

interface ThemeState {
  theme: Theme;
  sync: () => void;
  toggle: () => void;
}

function apply(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem("vp-theme", theme);
  } catch {
    // Storage can be blocked; the choice then lasts for this visit only.
  }
}

export const useTheme = create<ThemeState>((set, get) => ({
  theme: "light",
  /** Pick up whatever the inline script in layout.tsx already applied before hydration. */
  sync: () => set({ theme: document.documentElement.dataset.theme === "dark" ? "dark" : "light" }),
  toggle: () => {
    const next: Theme = get().theme === "dark" ? "light" : "dark";
    apply(next);
    set({ theme: next });
  },
}));
