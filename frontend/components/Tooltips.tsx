"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";

interface Tip {
  text: string;
  rect: DOMRect;
}

/**
 * Replaces the browser's plain tooltip with a styled one, everywhere in the app. Any element with a
 * `title` shows it as a bubble that fades in after a short pause, on hover and on keyboard focus.
 * The first time an element is hovered its `title` is moved to `data-tooltip`, so the browser's own
 * tooltip never appears; an icon-only element keeps its words as its accessible name.
 */
export function Tooltips() {
  const [tip, setTip] = useState<Tip | null>(null);
  const bubble = useRef<HTMLDivElement>(null);
  const owner = useRef<HTMLElement | null>(null);
  const showTimer = useRef<number>(0);
  const hideTimer = useRef<number>(0);

  useEffect(() => {
    const hide = () => {
      window.clearTimeout(showTimer.current);
      owner.current = null;
      const b = bubble.current;
      if (!b) return;
      b.dataset.show = "false";
      window.clearTimeout(hideTimer.current);
      hideTimer.current = window.setTimeout(() => setTip(null), 140);
    };

    const find = (target: EventTarget | null) => (target instanceof Element ? target.closest<HTMLElement>("[title],[data-tooltip]") : null);

    const take = (el: HTMLElement) => {
      const title = el.getAttribute("title");
      if (title) {
        el.setAttribute("data-tooltip", title);
        el.removeAttribute("title");
        if (!el.hasAttribute("aria-label") && !el.hasAttribute("aria-labelledby") && !el.textContent?.trim()) el.setAttribute("aria-label", title);
      }
      return el.getAttribute("data-tooltip") ?? "";
    };

    const enter = (e: Event) => {
      const el = find(e.target);
      if (!el) return;
      const text = take(el);
      if (!text || el === owner.current) return;
      window.clearTimeout(showTimer.current);
      window.clearTimeout(hideTimer.current);
      owner.current = el;
      showTimer.current = window.setTimeout(
        () => {
          if (owner.current === el && el.isConnected) setTip({ text, rect: el.getBoundingClientRect() });
        },
        e.type === "focusin" ? 80 : 320,
      );
    };

    const leave = (e: Event) => {
      const el = find(e.target);
      if (!el || el !== owner.current) return;
      const next = (e as MouseEvent).relatedTarget;
      if (next instanceof Node && el.contains(next)) return;
      hide();
    };

    const onKey = (e: KeyboardEvent) => e.key === "Escape" && hide();

    document.addEventListener("pointerover", enter);
    document.addEventListener("pointerout", leave);
    document.addEventListener("focusin", enter);
    document.addEventListener("focusout", leave);
    document.addEventListener("pointerdown", hide);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", hide, true);
    window.addEventListener("resize", hide);
    return () => {
      document.removeEventListener("pointerover", enter);
      document.removeEventListener("pointerout", leave);
      document.removeEventListener("focusin", enter);
      document.removeEventListener("focusout", leave);
      document.removeEventListener("pointerdown", hide);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", hide, true);
      window.removeEventListener("resize", hide);
      window.clearTimeout(showTimer.current);
      window.clearTimeout(hideTimer.current);
    };
  }, []);

  // Place the bubble above the element (below if there is no room), keep it on screen, then fade it in.
  useLayoutEffect(() => {
    const b = bubble.current;
    if (!tip || !b) return;
    const { rect } = tip;
    const gap = 10;
    const width = b.offsetWidth;
    const height = b.offsetHeight;
    const centre = rect.left + rect.width / 2;
    const left = Math.max(8, Math.min(centre - width / 2, window.innerWidth - width - 8));
    const above = rect.top - height - gap >= 8;
    b.style.left = `${left}px`;
    b.style.top = `${above ? rect.top - height - gap : rect.bottom + gap}px`;
    b.style.setProperty("--arrow-x", `${Math.max(14, Math.min(centre - left, width - 14))}px`);
    b.dataset.place = above ? "top" : "bottom";
    const frame = requestAnimationFrame(() => {
      b.dataset.show = "true";
    });
    return () => cancelAnimationFrame(frame);
  }, [tip]);

  if (!tip) return null;
  return (
    <div ref={bubble} role="tooltip" className="tooltip" data-show="false">
      {tip.text}
    </div>
  );
}
