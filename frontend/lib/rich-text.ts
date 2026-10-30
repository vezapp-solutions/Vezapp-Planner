export interface Run {
  text: string;
  bold: boolean;
}

export type Block = { kind: "paragraph" | "item"; runs: Run[] } | { kind: "gap" };

/** Split one line into plain and **bold** runs. An unmatched ** is left as the text it is. */
export function runsOf(line: string): Run[] {
  const runs: Run[] = [];
  const pattern = /\*\*(.+?)\*\*/g;
  let last = 0;
  for (const m of line.matchAll(pattern)) {
    if (m.index > last) runs.push({ text: line.slice(last, m.index), bold: false });
    runs.push({ text: m[1], bold: true });
    last = m.index + m[0].length;
  }
  if (last < line.length) runs.push({ text: line.slice(last), bold: false });
  return runs;
}

/**
 * Turn an assistant answer into blocks the screen can show without raw markdown: `- ` and `* `
 * start list items, **text** is bold, a heading line becomes a bold paragraph, blank lines are gaps.
 * Nothing here produces HTML, so the answer can never inject markup.
 */
export function richBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  for (const raw of text.replace(/\r\n/g, "\n").split("\n")) {
    const line = raw.trimEnd();
    if (!line.trim()) {
      if (blocks.length && blocks[blocks.length - 1].kind !== "gap") blocks.push({ kind: "gap" });
      continue;
    }
    const item = line.match(/^\s*[-*•]\s+(.*)$/);
    const heading = line.match(/^\s*#{1,6}\s+(.*)$/);
    if (item) blocks.push({ kind: "item", runs: runsOf(item[1]) });
    else if (heading) blocks.push({ kind: "paragraph", runs: [{ text: heading[1].replace(/\*\*/g, ""), bold: true }] });
    else blocks.push({ kind: "paragraph", runs: runsOf(line) });
  }
  while (blocks.length && blocks[blocks.length - 1].kind === "gap") blocks.pop();
  return blocks;
}
