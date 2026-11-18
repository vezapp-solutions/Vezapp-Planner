import { formatDayMonth, formatWeekday } from "@/lib/format";
import { CAPACITY_COLOR, CAPACITY_LABEL, capacityLevel, percent, type CapacityLevel } from "@/lib/plan-utils";
import type { BottleneckDay } from "@/lib/types";

const LEVELS: CapacityLevel[] = ["cool", "warm", "hot", "none"];
const BAR_HEIGHT = "6.5rem";

/**
 * The busiest machine of each working day as one row of bars: the taller and the redder, the closer to full.
 * An idle day is a short gray stub, so a quiet stretch reads as a gap in the chart rather than a row of dashes.
 */
export function CapacityStrip({ days }: { days: BottleneckDay[] }) {
  return (
    <div>
      <div className="overflow-x-auto pb-1">
        <ol aria-label="Busiest machine each day" className="grid gap-1.5" style={{ gridTemplateColumns: `repeat(${days.length}, minmax(3.25rem, 1fr))` }}>
          {days.map((d) => {
            const level = capacityLevel(d.utilisation);
            const loaded = Boolean(d.resource_code) && level !== "none";
            const height = loaded ? `${Math.max(8, Math.min(100, d.utilisation * 100))}%` : "4px";
            const day = `${formatWeekday(d.date, "short")} ${formatDayMonth(d.date)}`;
            return (
              <li key={d.date} aria-label={loaded ? `${day}: ${d.resource_code} ${percent(d.utilisation)} loaded` : `${day}: nothing planned`} className="flex min-w-0 flex-col items-center text-center">
                <span className={`font-mono text-xs ${loaded ? "font-semibold" : "text-ink-soft"}`}>{loaded ? percent(d.utilisation) : "–"}</span>
                <span className="mt-1.5 flex w-full items-end justify-center rounded-chip bg-sunken/70" style={{ height: BAR_HEIGHT }} aria-hidden="true">
                  <span className="w-[62%] max-w-8 rounded-t-chip rounded-b-[3px]" style={{ height, background: CAPACITY_COLOR[level], transition: "height 500ms cubic-bezier(0.2, 0.8, 0.2, 1)" }} />
                </span>
                <span className="mt-1.5 block max-w-full truncate font-mono text-xs font-medium">
                  {loaded ? d.resource_code : ""}
                  {!loaded && <span className="invisible">–</span>}
                </span>
                <span className="text-xs uppercase text-ink-soft">{formatWeekday(d.date, "short")}</span>
                <span className="font-mono text-xs text-ink-soft">{formatDayMonth(d.date)}</span>
              </li>
            );
          })}
        </ol>
      </div>

      <ul className="mt-4 flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-ink-soft" aria-label="Colour key">
        {LEVELS.map((l) => (
          <li key={l} className="flex items-center gap-1.5">
            <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full" style={{ background: CAPACITY_COLOR[l] }} />
            {CAPACITY_LABEL[l]}
          </li>
        ))}
      </ul>
    </div>
  );
}
