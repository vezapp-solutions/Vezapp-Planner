import { create } from "zustand";

/** Whether the welcome tour is open. Anything can open it: the first sign-in, the Help page, the account menu. */
export const useTour = create<{ open: boolean; start: () => void; stop: () => void }>((set) => ({
  open: false,
  start: () => set({ open: true }),
  stop: () => set({ open: false }),
}));
