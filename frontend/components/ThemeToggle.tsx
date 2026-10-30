"use client";

import { useEffect } from "react";

import { useTheme } from "@/lib/store";

export function ThemeToggle() {
  const { theme, sync, toggle } = useTheme();
  useEffect(sync, [sync]);
  const next = theme === "dark" ? "light" : "dark";

  return (
    <button
      type="button"
      onClick={toggle}
      className="btn btn-quiet !min-h-9 !px-2.5"
      aria-label={`Switch to ${next} mode`}
      title={`Switch to ${next} mode`}
    >
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        {theme === "dark" ? (
          <>
            <circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="2" />
            <path
              d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </>
        ) : (
          <path
            d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5Z"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinejoin="round"
          />
        )}
      </svg>
    </button>
  );
}
