"use client";

import { useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";

/** Open popovers, innermost last, so Escape closes only the top one and not the panel behind it. */
const openStack: symbol[] = [];

interface Position {
  left: number;
  top: number;
  minWidth: number;
}

/**
 * A floating panel under (or, when there is no room, over) an anchor element. It is drawn in a portal
 * so tables, panels and slide-overs never clip it, follows the anchor on scroll and resize, and closes on
 * a click outside it. Panels opened from inside another panel (a time list in a date picker) count as inside.
 */
export function Popover({
  anchor,
  open,
  onClose,
  children,
  label,
  role = "dialog",
  id,
  className = "",
  onKeyDown,
  matchWidth = true,
}: {
  anchor: RefObject<HTMLElement | null>;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  label?: string;
  role?: "dialog" | "listbox";
  id?: string;
  className?: string;
  onKeyDown?: (e: React.KeyboardEvent<HTMLDivElement>) => void;
  matchWidth?: boolean;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState<Position | null>(null);

  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const trigger = anchor.current;
      const box = panel.current;
      if (!trigger || !box) return;
      const t = trigger.getBoundingClientRect();
      const width = box.offsetWidth;
      const height = box.offsetHeight;
      const gap = 6;
      const below = window.innerHeight - t.bottom - gap;
      const top = below >= height || t.top < height + gap ? t.bottom + gap : t.top - height - gap;
      const left = Math.max(8, Math.min(t.left, window.innerWidth - width - 8));
      // Never run off the bottom of the screen: when neither side has room, slide up over the trigger.
      const fitted = Math.max(8, Math.min(top, window.innerHeight - height - 8));
      setPosition({ left, top: fitted, minWidth: matchWidth ? t.width : 0 });
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open, anchor, matchWidth]);

  useLayoutEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => {
      const target = e.target as Node;
      if (panel.current?.contains(target) || anchor.current?.contains(target)) return;
      if ((target as Element).closest?.("[data-popover-layer]")) return;
      onClose();
    };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [open, anchor, onClose]);

  useEffect(() => {
    if (!open) return;
    const me = Symbol("popover");
    openStack.push(me);
    // Capture phase on the window, so a slide-over or dialog behind this panel never sees the key.
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || openStack[openStack.length - 1] !== me) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      onClose();
      anchor.current?.focus();
    };
    window.addEventListener("keydown", onKey, true);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      openStack.splice(openStack.indexOf(me), 1);
    };
  }, [open, anchor, onClose]);

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div
      ref={panel}
      id={id}
      role={role}
      aria-label={label}
      data-popover-layer=""
      onKeyDown={onKeyDown}
      // Keep keyboard focus where it is when the panel is a list that the trigger controls.
      onMouseDown={role === "listbox" ? (e) => e.preventDefault() : undefined}
      style={{
        position: "fixed",
        left: position?.left ?? 0,
        top: position?.top ?? 0,
        minWidth: position?.minWidth,
        visibility: position ? "visible" : "hidden",
      }}
      className={`popover-in z-[80] rounded-xl border border-line bg-surface shadow-lg ${className}`}
    >
      {children}
    </div>,
    document.body,
  );
}
