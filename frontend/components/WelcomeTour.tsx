"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { hasSeenTour, markTourSeen, stepsFor } from "@/lib/help-content";
import { useSession } from "@/lib/store";
import { useTour } from "@/lib/tour-store";

interface Spot {
  top: number;
  left: number;
  width: number;
  height: number;
}

/** The first visible match for a selector, as a rectangle (the same item can exist for the pill and the bottom bar). */
function findSpot(selector: string | undefined): Spot | null {
  if (!selector) return null;
  for (const el of Array.from(document.querySelectorAll<HTMLElement>(selector))) {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < window.innerHeight) {
      return { top: r.top, left: r.left, width: r.width, height: r.height };
    }
  }
  return null;
}

/**
 * The welcome tour: a friendly card that walks through each screen, spotlighting its place in the navigation.
 * It opens by itself the first time someone signs in (once per person per browser) and can be replayed from Help.
 */
export function WelcomeTour() {
  const user = useSession((s) => s.user);
  const open = useTour((s) => s.open);
  const start = useTour((s) => s.start);
  const stop = useTour((s) => s.stop);
  const [index, setIndex] = useState(0);
  const [spot, setSpot] = useState<Spot | null>(null);
  const next = useRef<HTMLButtonElement>(null);

  const steps = user ? stepsFor(user.role) : [];
  const step = steps[Math.min(index, steps.length - 1)];

  // First sign-in: offer the tour once, a moment after the screen has settled.
  useEffect(() => {
    if (!user || hasSeenTour(user.id)) return;
    const timer = setTimeout(start, 900);
    return () => clearTimeout(timer);
  }, [user, start]);

  const close = useCallback(() => {
    if (user) markTourSeen(user.id);
    stop();
    setIndex(0);
  }, [user, stop]);

  useLayoutEffect(() => {
    if (!open || !step) return;
    const place = () => setSpot(findSpot(step.target));
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [open, step]);

  useEffect(() => {
    if (!open) return;
    next.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
      else if (e.key === "ArrowRight") setIndex((i) => Math.min(i + 1, steps.length - 1));
      else if (e.key === "ArrowLeft") setIndex((i) => Math.max(i - 1, 0));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, close, steps.length]);

  useEffect(() => {
    if (open) next.current?.focus();
  }, [open, index]);

  if (!open || !step) return null;
  const last = index >= steps.length - 1;
  const pad = 6;

  // Put the card on the far side of the highlighted item from the screen edge it sits on.
  const cardStyle: React.CSSProperties = {};
  if (spot) {
    if (spot.top > window.innerHeight / 2) cardStyle.bottom = window.innerHeight - spot.top + pad + 16;
    else cardStyle.top = spot.top + spot.height + pad + 16;
  }

  return (
    <div className="fixed inset-0 z-[120]" role="dialog" aria-modal="true" aria-labelledby="tour-title">
      {spot ? (
        <span
          aria-hidden="true"
          className="tour-spot"
          style={{ top: spot.top - pad, left: spot.left - pad, width: spot.width + pad * 2, height: spot.height + pad * 2 }}
        />
      ) : (
        <span aria-hidden="true" className="absolute inset-0 bg-black/60" />
      )}

      <div className={`tour-card ${spot ? "" : "tour-card-center"}`} style={cardStyle}>
        <div className="flex items-center justify-between gap-3">
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-ember-ink">
            {index + 1} of {steps.length}
          </p>
          <button type="button" className="min-h-9 rounded-chip px-2 text-sm text-ink-soft hover:text-ink" onClick={close}>
            {last ? "Close" : "Skip tour"}
          </button>
        </div>

        <h2 id="tour-title" className="mt-2 font-display text-2xl font-bold tracking-tight">
          {step.title}
        </h2>
        <p className="mt-2 text-[0.9375rem] leading-relaxed text-ink-soft">{step.body}</p>

        <div className="mt-5 flex items-center justify-between gap-3">
          <div className="flex gap-1.5" aria-hidden="true">
            {steps.map((s, i) => (
              <span key={s.id} className={`h-1.5 rounded-full transition-all duration-200 ${i === index ? "w-5 bg-action" : "w-1.5 bg-line"}`} />
            ))}
          </div>
          <div className="flex gap-2">
            {index > 0 && (
              <button type="button" className="btn btn-quiet !min-h-10" onClick={() => setIndex((i) => i - 1)}>
                Back
              </button>
            )}
            <button ref={next} type="button" className="btn btn-primary !min-h-10" onClick={() => (last ? close() : setIndex((i) => i + 1))}>
              {last ? "Let's go" : index === 0 ? "Show me around" : "Next"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
