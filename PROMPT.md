# Vezapp Planner: build prompt for Claude Code

Project folder: `C:\Projects\Vezapp-Planner`
How to start: open Claude Code in this folder and say: "Read PROMPT.md fully. Start in plan mode, ask me only blocking questions, show me your plan, and wait for my approval before writing code."

---

## 0. Your role and working rules

You are a senior full-stack engineer and foundry-planning domain expert. You are building **Vezapp Planner**, a production planning platform that Vezapp Solutions LLP will provide to its foundry clients (iron and steel sand-casting foundries in India).

Rules:
1. Work in phases (section 11). After each phase: run all tests, run the app, summarise what works and what does not, and **wait for my approval** before the next phase.
2. Never invent business rules silently. Every assumption goes into `docs/ASSUMPTIONS.md`, and every unresolved point into `docs/OPEN_QUESTIONS.md`. Make uncertain values configurable, not hardcoded.
3. All calculations must be deterministic, unit-tested and explainable: any number on screen can be clicked to show the formula and inputs used.
4. Use the worked example in section 7.5 as a mandatory test case.
5. The machine runs Windows. Scripts and README commands must work in PowerShell.

## 1. What the product does (plain words)

A foundry receives monthly dispatch requirements (customer, part, quantity, date). Each part passes through operations: **Core making → Moulding → Melting and pouring → (cooling) → Knockout → Fettling → Machining → Packing → Dispatch**. Each operation uses limited resources (core machines, moulding lines, furnaces, work stations) during limited working hours.

Vezapp Planner:
1. Stores the foundry's resources and their availability, each part's operation route and times, working hours, customers and parts.
2. Takes the monthly dispatch schedule (manual entry or bulk Excel upload).
3. Calculates how much load each schedule line puts on each resource, day by day and shift by shift, and checks it against real availability.
4. Produces a feasible plan, an **estimated dispatch date** for every line, and flags lines at risk with the operation holding them up.
5. Shows the bottleneck for each working day, supports "what if" (block a machine or furnace and preview what moves), and prints shift and day plans.
6. Has an **Insights / AI module** that turns all of this into plain-language, prioritised insights and answers questions.

It is inspired by CASCULATE (casculate.com). Its planning features are: planning proposals against real capacity, the busiest resource of each workday for the next two weeks, load per machine, line, furnace and station, an estimated delivery date next to the requested one, the operation holding up an at-risk order, resource blocking with a preview of moved orders, and printable shift plans. Match these and go further with dispatch-performance insights. Build our own design and wording, and do not copy their text or screens.

## 2. Name and branding

- Product name: **Vezapp Planner**. Keep it in one constant (`APP_NAME` in backend settings and `NEXT_PUBLIC_APP_NAME` in the frontend).
- **Logo: use the Vezapp logo from my Downloads folder.** Search `%USERPROFILE%\Downloads`:
  `Get-ChildItem "$env:USERPROFILE\Downloads" -Recurse -Depth 1 -Include *vezapp*.png,*vezapp*.svg,*vezapp*.jpg,*vezapp*.jpeg,*vezapp*.webp`
  If there are several matches, show them and ask me which one to use. If there are none, stop and ask for the path. Never generate or imitate a logo. **Copy** it (do not move or edit the original) into `frontend/public/brand/`, then create the favicon and app icons from the copy.
- Use the logo in the top bar, login page, and printed or exported plans and reports. Derive the colour palette from the logo as CSS variables, support light and dark mode, and meet WCAG AA contrast.
- Look and feel: clean, calm, industrial-professional. Planner screens are desktop-first and tablet-friendly. Viewer and insight screens must work on a phone.
- Locale: Indian context. Display dates as DD-MM-YYYY, timezone Asia/Kolkata, Indian number grouping (1,00,000), weights in kg and tonnes.

## 3. Tech stack

- Backend: Python 3.12, Django 5, Django REST Framework, PostgreSQL (SQLite allowed only for quick local dev through an env flag), JWT auth, `openpyxl` and `pandas` for Excel, pytest.
- Frontend: Next.js (App Router), TypeScript, Tailwind CSS, Recharts, Zustand, a data-grid component good for editable tables, and a custom SVG Gantt/timeline component (or a lightweight maintained library, with the choice justified).
- Planning engine: a pure-Python package `backend/planning/` with no Django imports in the core maths, so it can be unit-tested fast.
- AI: Anthropic Claude API via the official `anthropic` Python SDK. API key and model name come from env (`ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`). The app must work fully without a key (see section 9).
- Secrets only in `.env`. Provide `.env.example`. Never commit secrets.
- Optional `docker-compose.yml` for Postgres, but the README must also explain running without Docker on Windows.

## 4. Users, companies, roles

- **Multi-company (multi-tenant).** Vezapp serves many foundries. Every record belongs to a Company, and users see only their own company's data. Enforce this in the query layer and test it.
- Roles: **Vezapp Admin** (manages companies), **Company Admin** (masters, users), **Planner** (schedules, plans, what-if), **Viewer** (read-only: plans, insights).
- Audit log for every create, update and delete on masters and schedules (who, when, before and after).

## 5. Masters (build exactly these, in this order)

### 5.1 Company Master (working calendar)
- Company details: name, plant name(s), address, GSTIN, logo override (optional).
- **Working hours for each day of the week**: for Monday to Sunday, define one or more **shifts** (name, start time, end time, break minutes). A day with no shift is a weekly off. Shifts may cross midnight (for example 22:00–06:00); the shift belongs to the day it starts.
- **Holiday calendar**: dates with name; option for a full holiday or specific shifts off.
- Derived and shown: available minutes per shift, per day and per week.
- Planning settings: planning horizon (default 30 days), default planning bucket (shift or day), and the operation where rejection is booked (default: after Fettling; see 7.2).

### 5.2 Machine / Resource and Availability Master
Users add the resources the foundry plans against. Resource types (seeded, extendable by Company Admin):
- **Core Machine** (core shooter or core-making station)
- **Moulding Line** (automatic line, jolt squeeze, hand moulding bay and so on)
- **Furnace** (induction furnace or other melting unit)
- **Work Centre**, for Knockout, Fettling, Machining, Packing and Dispatch (station, cell or team)

Fields per resource: code, name, type, plant, number of parallel units (for example 2 identical machines = 2), status (Active / Inactive / Under maintenance), planned efficiency % (default 100), remarks.

**Availability (rated capacity)**, entered as value plus unit, depending on type:
- Core Machine: cores per hour (or cycle time in seconds per shot plus cores per shot).
- Moulding Line: moulds per hour (example: 90 moulds/hour).
- Furnace: heat size in kg (liquid metal per heat), melt cycle time in minutes per heat (tap to tap), and optionally max heats per shift.
- Work Centre: optional rated pieces per hour. Capacity is otherwise its working minutes × number of units.

Also:
- **Which shifts the resource works** (default: all company shifts). A resource may work fewer shifts than the company.
- **Downtime / blocked periods**: from date-time to date-time, reason (maintenance, breakdown, lining change and so on). These remove capacity and are used by what-if.
- Derived: available minutes per shift and per day = shift minutes × units × efficiency − downtime.

### 5.3 Customer Master
Code, name, contact person, phone, email, billing and shipping address, GSTIN, state, priority (A / B / C, used as the tie-breaker in scheduling), active flag.

### 5.4 Part Master
Part number (unique per company), part name and description, customer (link; a part may be supplied to more than one customer, so use a many-to-many relation with one default customer), drawing number and revision, material grade (free text plus a Grade list), casting weight kg (per piece), finished weight kg, **pouring (bunch) weight per mould kg** (metal poured into one mould including runners and risers), **cavities per mould (pieces per mould)**, **cores per mould**, pattern number, expected rejection % (default 0), optional selling price per piece (for value insights), and active flag.

### 5.5 Product-wise Operation Master (routing per part)
For each part, an ordered list of operations. Default template, in order: **Core, Moulding, Melting, Knockout, Fettling, Machining, Packing, Dispatch**. Each operation can be switched on or off for a part (for example, no Core for coreless parts, no Machining for as-cast parts). Company Admin may add optional operation types (Shot Blasting, Grinding, Heat Treatment, Painting, Inspection). Seed them as inactive.

Fields by operation:

**Core**
- Cycle time **in minutes per core** (or per shot, plus cores per shot).
- Cores per mould (pre-filled from Part Master, editable).
- Allowed core machines (multi-select from the Resource Master, type Core Machine).
- Core scrap allowance % (default 0).
- Cores must be ready **before** moulding of the same moulds; minimum lead time between core and moulding in hours (default 0).

**Moulding**
- Time **in minutes per mould**. If blank, use the line's rated speed (60 ÷ moulds per hour).
- Allowed moulding lines (multi-select, type Moulding Line).
- Cavities per mould (pre-filled from Part Master).

**Melting (and pouring)**
- Allowed furnace(s) (multi-select, type Furnace).
- **Moulds poured per heat** (user enters). Show a helper: suggested = floor(furnace heat kg × (1 − melt loss %) ÷ pouring weight per mould). Melt loss % defaults to 0, is editable, and has a warning if blank.
- **Total minutes per heat** (tap to tap; pre-filled from the furnace, editable per part).
- **Minutes per piece**: derived and shown read-only = minutes per heat ÷ (moulds per heat × cavities per mould). Do not let it drift from its inputs.
- Grade (from Part Master). **Only one grade per heat**; parts of the same grade may share a heat (see 7.3).
- Pouring happens on the same day (same shift by default) as moulding. The rule is configurable.

**Cooling (lag, not an operation)**
- Cooling time in mould before knockout, **in hours** (default 0). This is waiting time, not resource load. Research shows cooling takes from hours to days depending on size and alloy. Show a warning if it is 0 for parts above 50 kg.

**Knockout, Fettling, Machining, Packing, Dispatch**
- Time in minutes, plus a **time basis**: per piece, per mould, or per batch (with batch size).
- **Capacity bucket: per shift or per day.** This decides whether capacity is checked and the plan printed shift-wise or day-wise for this operation.
- Allowed work centre(s) (multi-select). If none is set, treat the operation as unconstrained, but show "capacity not modelled" on every screen that uses it.
- Optional transfer lag after the operation, in hours (for example inspection hold or transport to the machining vendor).
- Machining may be **outsourced**: a flag plus a lead time in days instead of minutes.

> Open question to record: my manager said "give minutes to each operation and specify if it is per shift or per day". I have interpreted this as **minutes per piece (or mould or batch) plus a capacity bucket of shift or day**. The alternative meaning is "this operation takes N minutes of the shift or day as a block". Support both through the time basis option "fixed minutes per shift" and "fixed minutes per day", and confirm with me.

### 5.6 Validation and sanity warnings (all masters)
Block clearly impossible values (negative or zero times, 0 cavities, heat smaller than one mould's pouring weight). Show soft warnings, not blocks, for values outside these typical ranges, which come from the research (section 12):
- Core cycle: 0.25–10 min per core. Blown cores are often about 1 min; cold-box cycles are about 0.5–1 min, and mounting can make it 4–5 min.
- Moulding: 0.2–30 min per mould. Automatic lines run hundreds of moulds an hour; manual mould preparation can take 9–14 min or more.
- Furnace minutes per heat: 30–240.
- Fettling: 0.1–120 min per piece.

## 6. Monthly Scheduler (dispatch schedule)

Each line holds: **Customer** (select from Customer Master), **Part** (select from Part Master, filtered to that customer), **Dispatch Qty** (pieces), **Internal Dispatch Date** (the plant's target), **Actual Dispatch Date** (filled when shipped), optional Actual Dispatched Qty (for partial dispatch), remarks, and status (Planned / In Progress / Dispatched / Cancelled). Month is derived from the internal dispatch date.

Screens: a month grid (filter by customer, part, status, grade), totals in pieces, tonnes (qty × casting weight) and value (if price is set). Inline edit and copy-from-previous-month.

**Bulk Excel upload:**
- "Download template" button. Columns: Customer Code, Customer Name, Part Number, Dispatch Qty, Internal Dispatch Date, Actual Dispatch Date, Actual Dispatched Qty, Remarks.
- Accept .xlsx and .csv. Accept dates as DD-MM-YYYY, DD/MM/YYYY and Excel serial numbers.
- Validate before saving: customer exists (match by code, then exact name), part exists, part is linked to that customer (warning, not block), qty is a positive integer, dates are valid, and the actual date is not in the future. Flag duplicates of the same customer, part and internal date.
- Show a **preview** with green, amber and red rows, and let me choose to insert new rows, update matching rows, or skip errors. Error report downloadable as Excel. All-or-nothing commit per upload. Keep upload history (file name, user, time, row counts).

## 7. Planning engine (the core logic)

All maths lives in `backend/planning/`, is pure Python and is fully unit-tested.

### 7.1 Requirement explosion (per schedule line)
For a line with dispatch qty `Q`:
- Pieces to pour `P = ceil(Q × (1 + rejection%))`
- Moulds `M = ceil(P ÷ cavities_per_mould)`
- Cores `C = ceil(M × cores_per_mould × (1 + core_scrap%))`
- Core minutes `= C × core_min_per_core`
- Moulding minutes `= M × min_per_mould`
- Liquid metal kg `= M × pouring_weight_per_mould`
- Heats `= ceil(M ÷ moulds_per_heat)` at line level (grade pooling in 7.3 may reduce this at plan level)
- Furnace minutes `= heats × min_per_heat`
- Post-casting operations: basis quantity is P up to and including the operation where rejection is booked (default Fettling), and Q after it. Configurable.
- Each operation's minutes = quantity on its basis × its time (per piece, mould or batch), or a fixed block for "fixed minutes per shift or day".

### 7.2 Capacity model
- Time buckets: shift (default) and day, built from the Company Master calendar and holidays.
- Capacity of a resource in a bucket = bucket minutes × parallel units × efficiency − overlapping downtime.
- Load is in minutes. Rated speeds in the Resource Master supply default times when a part has none.

### 7.3 Scheduling algorithm (finite capacity, deterministic, explainable)
1. **Backward pass (infinite capacity):** from each line's internal dispatch date, subtract operation durations and lags in reverse route order to get the latest start per operation. This gives the "required load profile" and shows overloads.
2. **Forward pass (finite capacity):** sort lines by internal dispatch date, then customer priority A > B > C, then entry order. For each line and each operation in route order, allocate its minutes into the earliest buckets on the allowed resources, starting from max(today, predecessor finish + lag). Choose the least-loaded allowed resource. Split across buckets when needed.
3. **Moulding–melting coupling:** moulds made in a bucket must be poured in the same bucket. So the moulds per bucket are the minimum of moulding capacity and furnace capacity, converted through moulds per heat. If the furnace is full, moulding for that line moves too.
4. **Grade pooling (plan-level option, default ON):** in each furnace bucket, moulds of different parts with the **same grade** may share a heat. Heats per bucket per grade = ceil(total pouring kg of that grade ÷ usable heat kg). Never mix grades in a heat. Show the heat plan per furnace per bucket (grade, moulds by part, kg, minutes).
5. **Cores** must be finished before moulding of the same moulds (respect lead time).
6. **Cooling** lag between pouring and knockout. Then knockout, fettling, machining (or outsourced lead time), packing, dispatch.
7. Output per line: planned start and finish per operation, the resource used, the **estimated dispatch date**, slack (internal date − estimated date), and status: On Track (slack ≥ 2 working days), Tight (0–1), or **At Risk** (negative), with the **operation holding it up** (the operation whose waiting or capacity caused the most delay).
8. Output per resource per bucket: load minutes, capacity minutes, utilisation %, and the lines contributing. **Bottleneck of the day** = the resource with the highest utilisation that day.
9. Unconstrained operations (no work centre defined) are scheduled with their duration only and flagged.

### 7.4 Plan lifecycle and what-if
- Plan versions: Draft → Confirmed. Recompute on demand. Show "last calculated at" and mark the plan stale when masters or schedules change.
- **What-if scenarios:** copy the current plan, then block a resource for a period, change a quantity or date, or add a shift or overtime. Recompute and show a **before-and-after diff**: lines whose estimated date changed, from and to, newly at-risk lines, and the bottleneck change. Apply only when the planner confirms.
- **Printable outputs (PDF and Excel) with the logo:** day plan and shift plan per department (core shop, moulding, melting heat plan, knockout, fettling, machining, packing, dispatch), the monthly dispatch plan versus estimated dates, and the resource load report.

### 7.5 Worked example (must be a unit test)
Company: 2 shifts per day, each 8 h with a 30 min break, so **900 min per day** (450 per shift). Efficiency 85%, so **765 usable min per day per unit**.
Part H-120 ("Housing"): cavities 2, cores per mould 2, core 1.0 min per core, moulding 1.5 min per mould on Line A, pouring weight 60 kg per mould, Furnace F1 heat 1,000 kg, melt loss 5% (950 kg usable), so suggested moulds per heat = floor(950 ÷ 60) = **15**. Minutes per heat 75. Knockout 0.5 min per piece on work centre KO (1 unit), fettling 3 min per piece on work centre FT (3 parallel units, so 2,295 usable min per day), rejection 5%, booked at fettling, cooling 4 h.
Schedule: Q = 600 pieces.
Expected: P = 630, M = 315, C = 630 → core 630 min; moulding 472.5 min; metal 18,900 kg; heats 21 → furnace 1,575 min; knockout 315 min; fettling 1,890 min.
Furnace capacity per day = floor(765 ÷ 75) = 10 heats = 150 moulds. So moulding must spread over **3 days (150 + 150 + 15 moulds)** even though Line A could make all 315 in one day. The bottleneck is **Furnace F1**. Assert these numbers.

## 8. Dashboards and screens (only what planning needs)
1. Home: today's and tomorrow's plan summary, the bottleneck for the next 14 working days (strip view), at-risk lines, top 5 insights.
2. Masters: Company, Resources, Customers, Parts, Operation routes (per part, with a copy-route-from-another-part option).
3. Monthly Scheduler (grid plus Excel upload).
4. Plan: Gantt/timeline by resource and by line; heat plan per furnace; load heatmap (resource × day, colour by utilisation).
5. What-if: scenario list, edit, diff, apply.
6. Insights / AI (section 9).
7. Reports: dispatch performance (needs actual dates), utilisation, plan versus actual dispatch.
8. Settings: users, roles, company settings, audit log, data health.

Every screen needs loading, empty and error states, and must look right at 375, 768 and 1440 px.

## 9. Insights / AI module

Build it in two layers. Numbers always come from layer 1 and never from a language model.

### 9.1 Layer 1: Insight Engine (deterministic, always on)
Rule and statistics based. It produces **insight cards**: type, severity (Critical / Warning / Info), title, a one-line plain-English message, key numbers, affected entities (lines, parts, customers, resources, dates), a suggested action, and "why" (the calculation trace). Rank cards by severity × impact (qty, tonnes or value). Refresh on every plan run, and store the history so trends can be shown.

Insights to implement:
1. **At-risk dispatches**: lines whose estimated date is later than the internal date, with days late and the operation holding them up.
2. **Bottleneck forecast**: the busiest resource of each working day for the next 14 days, with utilisation.
3. **Capacity gap**: per resource per week, required versus available minutes, translated into actions such as "Fettling needs about 2 extra shifts in week 3" or "Line A is at 40%: spare capacity".
4. **Melting and heat insights**: tonnes per grade per day, heats needed, heats saved by grade pooling, and days where furnace load is uneven.
5. **Load-balancing suggestions**: if a part is allowed on more than one line or furnace, suggest moving load from an overloaded resource to one with spare capacity, and show the effect after a dry-run.
6. **Dispatch performance** (from actual dispatch dates): on-time % and average delay by customer, by part and by month; parts and customers that are repeatedly late; trend versus last month.
7. **Month-end forecast**: forecast dispatch qty, tonnes and value versus plan, and the lines that will slip into next month.
8. **Concentration and mix**: share of the month's tonnes by top customers and grades; unusually large lines versus history.
9. **Data health**: parts without routes, routes missing times or resources, operations with no capacity modelled, schedule lines with past internal dates and no actual date, unrealistic values (section 5.6). Each item says why it hurts the plan.
10. **Daily digest**: the top 5 cards as a short summary that can be printed or emailed. Design an interface for WhatsApp later, but do not build it now.

### 9.2 Layer 2: AI Assistant (Claude, optional)
- If `ANTHROPIC_API_KEY` is set: an "Ask Vezapp Planner" chat panel. Use tool-calling. Tools are read-only functions over the company's own data and engine outputs (for example `get_at_risk_lines`, `get_resource_load(resource, from, to)`, `get_line_plan(line_id)`, `get_dispatch_performance(filters)`, `run_what_if_dry_run(params)`). The model explains, summarises and compares. It must quote numbers only from tool results and say "I don't have that data" otherwise. Also add an "Explain this" button on each insight card and a narrative monthly summary.
- If no key is set: the same panel answers a fixed set of supported intents (at-risk, bottleneck, capacity gap, customer performance, part status, month forecast). Use keyword and intent matching with templated, data-filled answers, and say plainly that it is in basic mode.
- Security: tenant isolation in every tool, no raw SQL from the model, log prompts and tool calls (excluding secrets), cap tokens per request, rate limit per user, and show a disclaimer that AI text is advisory.

### 9.3 Later idea (do not build now; record in OPEN_QUESTIONS)
CASCULATE's award-winning product is AI-based **Instant Pricing** for castings. A future Vezapp module could estimate cost per part from weight, grade, operation minutes and hourly rates.

## 10. Data model (starting point; refine in plan mode)
Company, Plant, Shift, WeekdayShift, Holiday, User, Role, ResourceType, Resource, ResourceShift, Downtime, Customer, Grade, Part, PartCustomer, OperationType, PartOperation (part, operation type, sequence, enabled, time value, time basis, batch size, capacity bucket, lag hours, outsourced, lead days, extra JSON for operation-specific fields), PartOperationResource, ScheduleLine, UploadBatch, Plan, PlanLine (estimated dates, status, holding operation), PlanAllocation (plan, line, operation, resource, bucket, minutes, qty), HeatPlan, Scenario, ScenarioChange, Insight, AuditLog.

## 11. Phases and acceptance criteria

**Phase 0: Foundation.** Repo layout (`backend/`, `frontend/`, `docs/`), auth and roles, multi-company, branding with the logo, app shell, seed script with a **synthetic demo foundry** (fake customers and parts, realistic resources: 2 core machines, 2 moulding lines, 2 furnaces, work centres; no real client data). README with Windows setup. *Done when:* I can log in as each role and see the branded shell; tests and lint pass.

**Phase 1: Masters.** Company calendar, Resources plus availability and downtime, Customers, Parts, the Operation Master with all fields and derived values, validation and warnings, and the audit log. *Done when:* I can enter the worked-example data through the UI and the derived values match section 7.5.

**Phase 2: Monthly Scheduler.** Grid, Excel template, upload with preview, validation and error report, upload history. *Done when:* a 200-row Excel file with deliberate errors is validated correctly.

**Phase 3: Planning engine.** Requirement explosion, capacity, backward and forward passes, moulding–melting coupling, grade pooling, estimated dates, at-risk status and holding operation, bottlenecks, plan screens, heat plan, and printable plans. *Done when:* the section 7.5 test passes, plus tests for holidays, downtime, multiple lines, grade pooling, outsourced machining and unconstrained operations; replanning 500 lines takes under 5 seconds.

**Phase 4: What-if.** Scenarios, diff, apply. *Done when:* blocking a furnace for a day shows exactly which lines move and their new dates.

**Phase 5: Insights / AI.** Insight Engine, cards, digest, data health, then the Claude assistant and basic mode. *Done when:* each insight type has a test with fixture data, and the assistant never states a number that is not in its tool results.

**Phase 6: Hardening.** Performance, security review, accessibility, docs (`ARCHITECTURE.md`, `PLANNING_LOGIC.md` with every formula, `USER_GUIDE.md`).

## 12. Domain research notes (use these to understand the domain and set sanity ranges, not as fixed defaults)
- Foundry flow: planning sets dates, chooses items for the next few days, tells moulding which moulds to make, and selects the alloys to melt. Molten metal from the induction furnace is poured; castings cool, then go through knockout, runner and riser removal, shot blasting, fettling, inspection and dispatch. Only **one alloy per furnace per period**, and alloy changes consume capacity, so grouping by grade matters.
- Moulding lines can feed a single furnace that becomes the bottleneck (one case study: lines of 300, 270 and 250 moulds/h feeding a 23,000 kg/h furnace). Plans must balance hourly metal demand against melting capacity.
- Induction melting runs in batches (heats). A single furnace spends part of each cycle on non-melting work (slag removal, sampling, temperature checks, pouring), so utilisation can be around 50%. Tap-to-tap time is melt time plus that non-production time. Melting is planned from the moulding requirement.
- Cooling in the mould before shakeout can take hours to days depending on casting size and alloy, and is often set by experience. It ties up floor space and WIP.
- Core making: blown cores about 1 per minute; cold-box cycles about 30–60 s, and mounting can make it 4–5 min per core. Make the cores needed plus a few spare for breakage.
- Fettling and finishing times can be seconds per small casting on a grinding line, and much longer for large steel castings. Keep them per part.

## 13. What to do first
1. Find the logo (section 2) and show me the chosen file.
2. Ask me at most 5 blocking questions (including the per-shift or per-day meaning in 5.5).
3. Present the plan: folder structure, final data model, API list, screen list, the engine module design with function signatures, and the test plan. Wait for approval.
4. Then build Phase 0 only.
