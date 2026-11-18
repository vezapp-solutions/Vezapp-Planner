"use client";

import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore, type PointerEvent as ReactPointerEvent, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";

/** Open popovers, innermost last, so Escape closes only the top one and not the panel behind it. */
const openStack: symbol[] = [];

const PHONE = "(max-width: 767px)";

/** True on a phone-sized screen. Drop-downs and calendars open as a bottom sheet there. */
function usePhone() {
  return useSyncExternalStore(
    (notify) => {
      const query = window.matchMedia(PHONE);
      query.addEventListener("change", notify);
      return () => query.removeEventListener("change", notify);
    },
    () => window.matchMedia(PHONE).matches,
    () => false,
  );
}

interface Position {
  left: number;
  top: number;
  minWidth: number;
}

/**
 * A floating panel under (or, when there is no room, over) an anchor element. It is drawn in a portal
 * so tables, panels and slide-overs never clip it, follows the anchor on scroll and resize, and closes on
 * a click outside it. Panels opened from inside another panel (a time list in a date picker) count as inside.
 *
 * On a phone the same content opens as a bottom sheet instead: it slides up from the bottom edge over a dimmed
 * backdrop, has a handle you can drag down to dismiss, and is easy to reach with a thumb.
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
  const phone = usePhone();
  const sheet = phone && open;

  // Dragging the sheet's handle down.
  const [dragY, setDragY] = useState(0);
  const [dragging, setDragging] = useState(false);
  const drag = useRef({ startY: 0, startTime: 0 });

  useLayoutEffect(() => {
    if (!open || sheet) return;
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
  }, [open, sheet, anchor, matchWidth]);

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

  // A bottom sheet stops the page behind it from scrolling.
  useEffect(() => {
    if (!sheet) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [sheet]);

  if (!open || typeof document === "undefined") return null;

  if (sheet) {
    const onDragStart = (e: ReactPointerEvent<HTMLDivElement>) => {
      e.currentTarget.setPointerCapture(e.pointerId);
      drag.current = { startY: e.clientY, startTime: e.timeStamp };
      setDragging(true);
    };
    const onDragMove = (e: ReactPointerEvent<HTMLDivElement>) => {
      if (!dragging) return;
      setDragY(Math.max(0, e.clientY - drag.current.startY));
    };
    const onDragEnd = (e: ReactPointerEvent<HTMLDivElement>) => {
      if (!dragging) return;
      setDragging(false);
      const dy = Math.max(0, e.clientY - drag.current.startY);
      const speed = dy / Math.max(1, e.timeStamp - drag.current.startTime);
      if (dy > 110 || (speed > 0.6 && dy > 30)) {
        setDragY(window.innerHeight);
        window.setTimeout(() => {
          setDragY(0);
          onClose();
        }, 170);
      } else {
        setDragY(0);
      }
    };

    return createPortal(
      <div data-popover-layer="" className="fixed inset-0 z-[80]">
        <div
          className="sheet-backdrop"
          style={{ opacity: Math.max(0, 1 - dragY / Math.max(1, window.innerHeight * 0.6)) }}
          onClick={onClose}
          aria-hidden="true"
        />
        <div
          ref={panel}
          id={id}
          role={role}
          aria-label={label}
          aria-modal="true"
          onKeyDown={onKeyDown}
          onMouseDown={role === "listbox" ? (e) => e.preventDefault() : undefined}
          className="sheet"
          style={{ transform: `translateY(${dragY}px)`, transition: dragging ? "none" : "transform 200ms cubic-bezier(0.2, 0.8, 0.2, 1)" }}
        >
          <div className="sheet-handle" onPointerDown={onDragStart} onPointerMove={onDragMove} onPointerUp={onDragEnd} onPointerCancel={onDragEnd}>
            <span className="sheet-grip" aria-hidden="true" />
            {label && <span className="sheet-title">{label}</span>}
          </div>
          <div className={`sheet-body ${className}`}>{children}</div>
        </div>
      </div>,
      document.body,
    );
  }

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
      className={`popover-in z-[80] rounded-card-lg border border-line bg-surface shadow-lg ${className}`}
    >
      {children}
    </div>,
    document.body,
  );
}
