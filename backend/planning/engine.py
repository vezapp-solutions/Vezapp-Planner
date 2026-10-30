"""run_plan: the single entry point. Pure function of a PlanInput."""

import time
from decimal import Decimal

from .backward import backward_pass
from .explode import explode_line
from .kpis import bottlenecks, classify, day_of, holding_operation
from .ledger import ZERO, Ledger
from .model import PRIORITY_RANK, LineResult, LoadCell, PlanInput, PlanResult
from .schedule import Scheduler
from .timeline import build_timeline


def run_plan(inp: PlanInput) -> PlanResult:
    started = time.perf_counter()
    timeline = build_timeline(inp)
    res = {r.id: r for r in inp.resources}
    ledger = (
        Ledger(timeline, inp.resources, inp.extra_shifts, inp.overtime) if len(timeline) else None
    )
    results: list[LineResult] = []
    required_total: dict[tuple[int, int], Decimal] = {}

    if ledger is None:
        for line in inp.lines:
            results.append(
                LineResult(
                    line.id,
                    "unscheduled",
                    None,
                    None,
                    None,
                    None,
                    "",
                    None,
                    [],
                    ["The company has no working shifts in the planning window."],
                )
            )
        return PlanResult([], results, [], {}, [], None, {"lines": len(results), "runtime_ms": 0})

    scheduler = Scheduler(timeline, ledger, inp.settings, res)
    ordered = sorted(
        inp.lines,
        key=lambda ln: (ln.internal_date, PRIORITY_RANK.get(ln.priority, 1), ln.entry_order, ln.id),
    )

    for line in ordered:
        part = inp.parts.get(line.part_id)
        if part is None or not part.ops:
            results.append(
                LineResult(
                    line.id,
                    "unscheduled",
                    None,
                    None,
                    None,
                    None,
                    "",
                    None,
                    [],
                    ["The part has no operation route."],
                )
            )
            continue
        req = explode_line(line, part, inp.settings, res)
        windows, required = backward_pass(line, part, req, timeline, res)
        for key, minutes in required.items():
            required_total[key] = required_total.get(key, ZERO) + minutes

        sched = scheduler.schedule_line(line, part, req)
        for op in sched.ops:
            if op.code in windows:
                op.latest_start, op.latest_finish = windows[op.code]

        if not sched.complete:
            results.append(
                LineResult(
                    line.id,
                    "unscheduled",
                    None,
                    None,
                    None,
                    sched.failed_op,
                    sched.notes[0] if sched.notes else "",
                    req,
                    sched.ops,
                    sched.notes,
                )
            )
            continue

        finishes = [op.finish_at for op in sched.ops if op.finish_at]
        finish = max(finishes) if finishes else None
        est = day_of(timeline, finish) if finish else None
        slack = timeline.working_days_between(est, line.internal_date) if est else None
        status = classify(slack) if slack is not None else "unscheduled"
        holding, text = (None, "")
        if status != "on_track":
            holding, text = holding_operation(sched.ops, timeline)
        else:
            holding_operation(sched.ops, timeline)  # still fills each operation's delay
        results.append(
            LineResult(
                line.id, status, est, finish, slack, holding, text, req, sched.ops, sched.notes
            )
        )

    loads: dict[tuple[int, int], LoadCell] = {}
    for rid, caps in ledger.cap.items():
        used = ledger.used[rid]
        for idx, cap in enumerate(caps):
            req_min = required_total.get((rid, idx), ZERO)
            if cap > 0 or used[idx] > 0 or req_min > 0:
                loads[(rid, idx)] = LoadCell(used[idx], cap, req_min)

    codes = {r.id: r.code for r in inp.resources}
    days, overall = bottlenecks(timeline, loads, codes)
    by_status: dict[str, int] = {}
    for r in results:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    summary = {
        "lines": len(results),
        "by_status": by_status,
        "slots": len(timeline),
        "runtime_ms": int((time.perf_counter() - started) * 1000),
    }
    results.sort(key=lambda r: r.line_id)
    return PlanResult(
        timeline.slots, results, scheduler.allocations(), loads, days, overall, summary
    )
