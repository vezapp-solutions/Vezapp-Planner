"use client";

import { useEffect } from "react";

/**
 * Makes tables usable on a phone, for every table in the app, with no change to the screens themselves.
 *
 * 1. Labels. Every cell gets a `data-label` copied from its column heading. On a narrow screen the CSS in
 *    globals.css turns each row into a card that shows "heading: value" for every column, so nobody has to
 *    scroll sideways to discover that more columns exist. (Wide screens ignore the labels.) A table that is
 *    a true grid (a day-by-machine heatmap) opts out with `data-matrix` and keeps scrolling.
 * 2. Scroll hints. Anything that still scrolls sideways (those grids, the tab bar, filter chips) gets a
 *    `data-more` flag saying which side has more, which the CSS turns into a fading edge and, for grids on a
 *    phone, a "swipe sideways" line, so the extra content is never invisible.
 */
export function ResponsiveTables() {
  useEffect(() => {
    let frame = 0;
    const watched = new WeakSet<Element>();

    function labelTable(table: HTMLTableElement) {
      if (table.hasAttribute("data-matrix")) return;
      const headRows = table.tHead?.rows;
      if (!headRows || headRows.length === 0) return;
      const labels: string[] = [];
      for (const th of Array.from(headRows[headRows.length - 1].cells)) {
        const text = (th.textContent ?? "").trim();
        for (let i = 0; i < (th.colSpan || 1); i += 1) labels.push(text);
      }
      for (const body of Array.from(table.tBodies)) {
        for (const row of Array.from(body.rows)) {
          let column = 0;
          for (const cell of Array.from(row.cells)) {
            const label = labels[column] ?? "";
            if (cell.getAttribute("data-label") !== label) cell.setAttribute("data-label", label);
            column += cell.colSpan || 1;
          }
        }
      }
    }

    function updateHint(el: HTMLElement) {
      const max = el.scrollWidth - el.clientWidth;
      let state = "";
      if (max > 2) {
        const left = el.scrollLeft > 2;
        const right = el.scrollLeft < max - 2;
        state = left && right ? "both" : right ? "right" : left ? "left" : "";
      }
      if (state) {
        if (el.getAttribute("data-more") !== state) el.setAttribute("data-more", state);
      } else if (el.hasAttribute("data-more")) {
        el.removeAttribute("data-more");
      }
    }

    function run() {
      frame = 0;
      document.querySelectorAll<HTMLTableElement>("table").forEach(labelTable);
      document.querySelectorAll<HTMLElement>(".overflow-x-auto, .overflow-auto, .seg, .no-scrollbar").forEach((el) => {
        if (!watched.has(el)) {
          watched.add(el);
          el.addEventListener("scroll", () => updateHint(el), { passive: true });
        }
        updateHint(el);
      });
    }

    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(run);
    };

    const observer = new MutationObserver(schedule);
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    window.addEventListener("resize", schedule);
    schedule();
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", schedule);
      if (frame) cancelAnimationFrame(frame);
    };
  }, []);

  return null;
}
