import { describe, expect, it } from "vitest";

import { richBlocks, runsOf } from "./rich-text";

describe("runsOf", () => {
  it("splits bold from plain text", () => {
    expect(runsOf("The **outlook** is critical")).toEqual([
      { text: "The ", bold: false },
      { text: "outlook", bold: true },
      { text: " is critical", bold: false },
    ]);
  });
  it("leaves an unmatched marker alone", () => {
    expect(runsOf("2 ** 3")).toEqual([{ text: "2 ** 3", bold: false }]);
  });
  it("handles text with no markup", () => expect(runsOf("plain")).toEqual([{ text: "plain", bold: false }]));
});

describe("richBlocks", () => {
  it("shows list items and bold without raw markers", () => {
    const blocks = richBlocks("**Month:** on course\n- SPR-900 for **C-101**\n* second");
    expect(blocks).toEqual([
      { kind: "paragraph", runs: [{ text: "Month:", bold: true }, { text: " on course", bold: false }] },
      { kind: "item", runs: [{ text: "SPR-900 for ", bold: false }, { text: "C-101", bold: true }] },
      { kind: "item", runs: [{ text: "second", bold: false }] },
    ]);
  });
  it("turns a heading into a bold line", () => {
    expect(richBlocks("## October summary")).toEqual([{ kind: "paragraph", runs: [{ text: "October summary", bold: true }] }]);
  });
  it("keeps one gap between paragraphs and drops edge gaps", () => {
    expect(richBlocks("\n\none\n\n\ntwo\n\n").map((b) => b.kind)).toEqual(["paragraph", "gap", "paragraph"]);
  });
  it("never produces markup from angle brackets", () => {
    const [block] = richBlocks("<img src=x onerror=alert(1)>");
    expect(block).toEqual({ kind: "paragraph", runs: [{ text: "<img src=x onerror=alert(1)>", bold: false }] });
  });
});
