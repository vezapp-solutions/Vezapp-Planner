# Planning logic

How Vezapp Planner turns masters and the monthly schedule into a plan. The engine lives in `backend/planning/` (pure Python, no Django) and is a deterministic function: the same inputs always give the same plan. Every number on screen can be clicked to show its formula and inputs (the `Traced` objects in `planning/trace.py`).

## 1. Working time

- A **shift** has a start, an end and a break. Its **net minutes** are `clock minutes (end − start, past midnight if end ≤ start) − break minutes`. A shift crossing midnight belongs to the day it starts. Example: 06:00–14:00 with a 30 minute break = 450 net minutes; two such shifts = 900 a day.
- The **timeline** is every shift that actually runs, from the plan start day to the later of the planning horizon and the last internal dispatch date + 30 days (at most 400 days). A weekly off has no shift. A full holiday removes the day; a holiday for some shifts removes only those.
- **Capacity of a resource in one shift** = `shift net minutes × units × efficiency% ÷ 100 − downtime minutes`, never below 0. Downtime periods are merged first so overlapping ones count once, and only the part inside the shift counts. A resource that is inactive, under maintenance, or does not work that shift has 0.
- Example (section 7.5): 450 × 1 × 85% = 382.5 minutes per shift per unit, 765 a day; fettling with 3 units = 2,295 a day.

## 2. What a line asks for (section 7.1)

For dispatch quantity `Q`, rejection `r%`:

| Quantity | Formula |
|---|---|
| Pieces to pour `P` | `ceil(Q × (1 + r ÷ 100))` |
| Moulds `M` | `ceil(P ÷ cavities per mould)` (the moulding operation's cavities, else the part's) |
| Cores `C` | `ceil(M × cores per mould × (1 + core scrap% ÷ 100))` |
| Metal (kg) | `M × pouring weight per mould` |
| Moulds per heat | the value entered on the melting operation, else `floor(heat kg × (1 − melt loss% ÷ 100) ÷ pouring weight per mould)` for the smallest allowed furnace; melt loss falls back to the company default |
| Heats (internal) | `ceil(M ÷ moulds per heat)` |

Minutes per operation = units × minutes per unit:

| Operation | Units | Minutes per unit |
|---|---|---|
| Core | `C` cores | entered time, else `60 ÷ cores per hour`, else `cycle seconds ÷ 60 ÷ cores per shot` |
| Moulding | `M` moulds | entered time, else `60 ÷ moulds per hour` of the line |
| Melting | heats | entered minutes per heat, else the furnace's |
| Post-casting, per piece | `P` up to and including the operation where rejection is booked, `Q` after it | entered time (or `60 ÷ pieces per hour` of the work centre) |
| per mould | `M` | |
| per batch | `ceil(quantity ÷ batch size)` | |
| fixed per shift / per day | 1 block | the entered minutes (one block per lot) |
| Outsourced | no minutes | lead time in calendar days |

Worked example (section 7.5, 600 pieces of H-120): `P = 630`, `M = 315`, `C = 630`, metal 18,900 kg, 21 heats; core 630 min, moulding 472.5, melting 1,575, knockout 315, fettling 1,890. This is a mandatory test.

Heats are an internal furnace figure. Screens and prints show pieces, moulds and minutes; the heat count appears only inside a formula popover.

## 3. Order of planning

Lines are planned one at a time in this order: **internal dispatch date, then customer priority (A before B before C), then entry order**. An earlier line takes capacity first; a later one gets what is left.

## 4. Forward pass: finite capacity

**Supply curves.** Each operation consumes what the previous one releases: a list of (release time, cumulative share of the lot). In *progressive* mode (default) every upstream shift releases its share when it ends, plus the wait after that operation (and the **cooling time** after pouring). In *whole lot* mode the curve collapses to one step at the end. One allocator serves both.

**Allocation.** For each released share, in order: start at the first shift that ends after the release time and fill the earliest shifts with room. Inside a shift the resource with the **most free minutes** is used first, then the next, splitting the work. Free minutes in the first shift after a late release are `capacity − max(minutes already used, capacity × share of the shift before the release)`: earlier work fills the front of a shift.

**Moulding and melting together.** Moulds made in a shift are poured in the same shift (company setting `pour_same_shift`). Cores come first. In every shift, moulds that can be made =

`min( moulding capacity ÷ minutes per mould, cores finished by the end of the shift minus the core lead hours, furnace room )`

with `furnace room = moulds in an already opened heat + floor(free furnace minutes ÷ minutes per heat) × moulds per heat` (also limited by the furnace's max heats per shift). New heats are `ceil(moulds not fitting in open heats ÷ moulds per heat)`, each taking its minutes. The pair (moulding line, furnace) that allows the most moulds is used first, ties by code. **Heats are counted per part and are never shared between lines**; a heat is never carried from one shift to the next.

Example: furnace 765 minutes a day = 382.5 per shift → `floor(382.5 ÷ 75) = 5` heats a shift = 75 moulds, 150 a day, so 315 moulds take three days (150 + 150 + 15) although the moulding line could make them in one. The furnace is the bottleneck.

With `pour_same_shift` off, moulding is limited only by line and cores; moulds wait in a queue and are poured, oldest first, as furnace room allows.

**Outsourced** operation: finish = release of the whole lot + wait + lead days (calendar). It takes no resource capacity. **Unconstrained** operation (no work centre): its minutes are consumed on the company calendar without taking any resource's capacity, and it is flagged "capacity not modelled". A **day-bucket** operation draws on the same shift ledger but releases its output at the end of the working day.

## 5. Dates, status and what held a line up

- **Estimated dispatch date** = the working day on which the last operation finishes (a night shift counts for the day it started).
- **Slack** = working days from the estimated date to the internal date (positive = spare, negative = late), counted on the company calendar.
- **Status:** On Track = 2 or more working days spare; Tight = 0 or 1; At Risk = late; Not scheduled = the lot does not fit inside the planning window.
- **Holding operation** (shown for lines that are not On Track): the operation whose work **waited longest for capacity**, measured as the average time from when each piece was ready to when it was processed. For moulding and melting the wait is credited to what limited the moulds most (furnace, moulding line, or cores). If nothing waited 6 hours or more, the operation with the longest span is named instead.

## 6. Backward pass: infinite capacity

From the end of working time on the internal date, walk back through the route: each operation's duration is `minutes ÷ (units × efficiency of its allowed resources)` in working time, plus the waits between steps (the wait after an operation, plus cooling after melting). Moulding and melting run side by side. This gives each operation's **latest start and finish**, and spreads its minutes over the shifts between them (by shift length, and by units × efficiency across resources) as the **required load**. Where required load exceeds capacity, the due dates cannot all be met; the load heatmap marks it with a red dot.

## 7. Load and bottlenecks

- Load, capacity and required load are kept per resource per shift. Utilisation = load ÷ capacity.
- **Bottleneck of a day** = the resource with the highest utilisation that day (ties: more load, then code). The **overall bottleneck** of a plan is the resource with the highest single-day utilisation.

## 8. Plans

A plan is calculated from the current masters and schedule (lines that are Planned or In progress) and starts today at 00:00 with no credit for work already done. It is **stale** when schedule lines, parts, routes, resources, downtime, calendar, customers or settings have changed since, or when it was calculated on an earlier day. A draft can be recalculated; **Confirm** freezes it as a baseline (not allowed while stale). A confirmed plan never goes stale and is not recalculated; a new plan starts from current data.

## 9. What-if scenarios (section 7.4)

A scenario is a list of changes. **Running** it plans the company **twice** from the same data with the same engine: once as things stand (baseline) and once with the changes. Nothing real is touched.

Each change is applied to a copy of the planning input:

| Change | Effect on the copy |
|---|---|
| Block a resource, from to | A downtime on that resource for the period. |
| Change a quantity | The line asks for the new number of pieces. |
| Change a date | The line has the new internal dispatch date (and therefore a new priority order and backward pass). |
| Extra shift, days, times, resources | A one-off shift is added to the timeline on those days. Named resources (all if none) have capacity in it. It may fall on a weekly off or holiday and then counts as a working day. |
| Overtime, days, minutes, shift, resources | Each named resource gains `minutes × units × efficiency %` of capacity in every shift of those days. The shift's length on the calendar does not change. |

**The diff** lists every line whose estimated date, status, spare days, quantity or internal date differs, with from and to values, and the working days it moved on the company calendar. Each line gets a tag, the first of which decides its group: *newly at risk or not scheduled*, *moves later*, *recovered*, *moves earlier*, *other change*. It also gives lines by status before and after, the overall bottleneck before and after, the days on which the busiest resource differs, and each resource's peak shift utilisation before and after.

A result is **fresh** only if it was run after the last edit of the change list (a hash of the changes) and the schedule and masters have not changed since (the same data fingerprint plans use). **Apply** needs a fresh result and, in one transaction, creates a downtime for a block, edits the schedule line for a quantity or date, and creates an extra shift or overtime record in the masters for the others. The engine reads those records in every real plan, which is why the recalculated plan matches the scenario.

## 10. Insights (section 9.1)

The Insight Engine (`backend/insights/`) is pure Python: it reads plain facts and returns ranked cards, each with a one-line message, key numbers, the entities involved, a next step and a "why" trace. A card's **rank** = severity weight × (1 + impact), with weights critical 1,000, warning 50, info 4 and impact between 0 and 10. All thresholds live in `insights/rules.py`.

| Rule | How it is worked out |
|---|---|
| At risk | Lines with status At risk or Not scheduled. Working days late = −(spare working days). Critical if any line does not fit the window or one is 3 or more working days late. Held up by comes from the plan (section 5). |
| Bottleneck forecast | Busiest resource of each of the next 14 working days. The bottleneck is the resource that reaches the highest utilisation; ties go to the one busiest on more days. Critical with 3 or more full days, warning at 85%. |
| Capacity gap | Per resource per week (Monday start): required = Σ required minutes, available = Σ capacity. Shortfall = required − available. Extra shifts = ⌈shortfall ÷ the resource's average shift capacity⌉. Critical when the shortfall is 25% or more of the week's capacity. A resource under 50% overall utilisation gets a spare-capacity card (the lowest three). |
| Melting | Each line's metal kg × (melting minutes on a day ÷ its total melting minutes) gives kg per grade per day. Furnace load is uneven when its daily utilisation has a standard deviation over mean above 0.35, or it is full on some days and at 40% or less on others (at least 4 working days). |
| Load balancing | A route step whose allowed resources are all at 85% or more (utilisation on days with work, next 14 working days) and a rated resource of the same kind, not allowed, 25 points quieter. Test it plans twice, with and without the extra resource. |
| Dispatch performance | On time = actual date ≤ internal date. On-time % = on time ÷ lines; average delay = mean days late of the late lines. Warning under 80%, critical under 60%. Repeat offenders: 3 or more lines and under 70% on time. |
| Month forecast | Scope: lines with an internal date this month. Forecast: estimated date ≤ month end. Shortfall = 1 − forecast pieces ÷ planned pieces; critical at 15% or more. |
| Concentration | Share of the month's tonnes (casting weight × quantity) by customer and grade; warning when one customer is 50% or more. A line of at least 3 times the part's median quantity (3 or more other lines) is flagged. |
| Data health | Parts with no enabled operation, route steps with an error, steps with no resource (capacity not modelled), past internal dates with no actual date, and the warnings of the master-data checks. Ranked by the schedule lines affected. |

**Refresh.** Cards are rewritten after every plan calculation (and after uploads of actual dispatch dates). Each rewrite is a run; a card is compared with the same key in the previous run for its trend.


**The assistant** answers only from read-only tools over the company's data. Its answer may contain a number only if the same number appears in that turn's tool results (A81).
## 11. Machining steps and machines

An operation type marked **multi-step** (machining) may appear several times in a part's route. Each appearance is a **step**: `OP10 Rough milling`, `OP20 Finish bore`. A step has its own code (`machining~10`, `machining~20`; the original single row keeps `machining`), so requirement, allocations, windows and results are kept per step. Steps run in route order with pieces flowing on, like any other operations (section 4).

**Which machines.** A step's machines = the machines chosen one by one + every machine of the allowed machine types − the machines marked not suitable. Machine types are resource types of kind Work Centre (VMC, CNC, HMC). A machine added later to an allowed type is allowed automatically.

**Time on a machine.** `minutes per piece = the time of that machine's type`, else the step's default time, else the rated speed of the machine. Each machine is therefore timed by its own type.

**Requirement (due-date load).** `minutes = pieces × average minutes per piece of the allowed machines + setup minutes of one machine`. The average makes the backward pass neither optimistic nor pessimistic; it is shown in the formula popover.

**Allocation.** In each shift, the allowed machine that can make the **most pieces** goes first, then the next: `pieces = (free minutes − setup still to do) ÷ minutes per piece`. For machines of one speed this is the same as most free minutes, so earlier results do not change. A machine that is down, in maintenance, on another shift pattern or already full simply has fewer free minutes or none, which is how availability enters the plan.

**Setup.** Each machine used for a lot is set up once, before its first piece: `setup minutes` are taken from its free time and recorded as setup on that machine and shift. A setup longer than a shift carries into the machine's next shift. A machine whose free time in a shift is only enough for setup waits, unless no machine can make pieces in that shift. The minutes shown for the step are the minutes really allocated, setup included.

Example: `OP10`, 200 pieces, VMC 12 min and HMC 6 min per piece, setup 45 min, one VMC and one HMC with 382.5 free minutes in the first shift. HMC: `(382.5 − 45) ÷ 6 = 56.25` pieces. VMC: `(382.5 − 45) ÷ 12 = 28.1` pieces. The rest follows in the next shifts.

**The Machine shop** (`/machine-shop`) reads the stored plan: for each machine and working day, capacity (after downtime and its shifts), planned load and setup, free minutes = capacity − load, and the operations on it. Nothing is recalculated there.

