import { Panel } from "@/components/Panel";
import { StatusBadge } from "@/components/plan/StatusBadge";
import { formatDateTime, formatNumber } from "@/lib/format";
import { hours } from "@/lib/machining";
import type { MachineShop } from "@/lib/types";

/** Every machining operation in the plan: which machines it runs on and when it starts and finishes. */
export function MachineOperations({ shop }: { shop: MachineShop }) {
  return (
    <Panel title="Machining operations in the plan" note={`${shop.operations.length} operation${shop.operations.length === 1 ? "" : "s"}`}>
      <div className="-mx-4 -my-4 overflow-x-auto">
        <table className="w-full min-w-[50rem] text-left text-sm">
          <thead className="border-b border-line bg-sunken text-ink-soft">
            <tr>
              {["Part", "Customer", "Pieces", "Operation", "Machines", "Starts", "Finishes", "Hours", "Line"].map((h, i) => (
                <th key={h} scope="col" className={`px-3 py-2 font-medium ${i === 2 || i === 7 ? "text-right" : ""}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shop.operations.map((o) => (
              <tr key={`${o.line_id}-${o.op_code}`} className="border-b border-line last:border-0">
                <th scope="row" className="px-3 py-1.5 font-medium">{o.part_number}</th>
                <td className="px-3 py-1.5">{o.customer_code}</td>
                <td className="px-3 py-1.5 text-right font-mono">{formatNumber(o.qty)}</td>
                <td className="px-3 py-1.5">{o.name}</td>
                <td className="px-3 py-1.5 font-mono text-xs">{o.machines || "not modelled"}</td>
                <td className="whitespace-nowrap px-3 py-1.5 font-mono">{o.start_at ? formatDateTime(o.start_at) : "–"}</td>
                <td className="whitespace-nowrap px-3 py-1.5 font-mono">{o.finish_at ? formatDateTime(o.finish_at) : "–"}</td>
                <td className="px-3 py-1.5 text-right font-mono">{hours(o.minutes)}</td>
                <td className="px-3 py-1.5"><StatusBadge status={o.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
