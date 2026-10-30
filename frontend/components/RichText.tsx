import type { ReactNode } from "react";

import { richBlocks, type Block } from "@/lib/rich-text";

function runs(block: Extract<Block, { runs: unknown }>): ReactNode {
  return block.runs.map((r, i) => (r.bold ? <strong key={i}>{r.text}</strong> : <span key={i}>{r.text}</span>));
}

/** An assistant answer shown as paragraphs, lists and bold, never as raw markdown. */
export function RichText({ text }: { text: string }) {
  const out: ReactNode[] = [];
  let items: ReactNode[] = [];
  const flush = () => {
    if (items.length) out.push(<ul key={`l${out.length}`} className="my-1 list-disc space-y-0.5 pl-5">{items}</ul>);
    items = [];
  };
  richBlocks(text).forEach((b, i) => {
    if (b.kind === "item") {
      items.push(<li key={i}>{runs(b)}</li>);
      return;
    }
    flush();
    if (b.kind === "paragraph") out.push(<p key={i}>{runs(b)}</p>);
    else out.push(<div key={i} className="h-2" aria-hidden="true" />);
  });
  flush();
  return <div className="space-y-0.5">{out}</div>;
}
