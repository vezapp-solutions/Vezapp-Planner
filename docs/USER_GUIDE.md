# User guide

Written as screens arrive.

## Signing in and moving around
The **Ask AI** button (sparkle) in the top bar, on every screen and for every role, opens the assistant chat. On a phone, a Vezapp Admin's "Working on" company picker sits on its own row under the top bar. Sign in with your username and password. The menu on the left (the Menu button on a phone) shows only what your role can use. The sun/moon button switches light and dark mode. A Vezapp Admin picks a client under "Working on" in the top bar before opening Masters.

## Adding a client and its people
There is no public signup. Accounts are created by an administrator:
1. **Vezapp Admin, Companies, Add company.** Enter the client's name (GSTIN and address are optional). The standard operations and resource types are created automatically. To stop a client signing in, untick **Active**; nothing is deleted, and companies cannot be deleted from the screen.
2. **Vezapp Admin, Users, Add user.** Choose the role **Company Admin**, pick the company, enter a username and an initial password (at least 8 characters, not a common one), and tell the person.
3. **The Company Admin, Settings, Users, Add user** adds their own planners, viewers and further admins; they are always added to their own company.
4. To reset a forgotten password, open the user, type a new password and save. Leave the box empty to keep the current one. There are no emailed invites or "forgot password" links yet.
5. You cannot deactivate, delete or change the role of your own account, so an admin cannot lock themselves out.

## Masters (Company Admin edits; everyone else reads)
Open **Masters** and work down the list, because each step uses the one before it.

1. **Company calendar**: add your shifts (start, end, break), tick which shifts run on which weekday (no shift = weekly off), add holidays, switch on any extra operations (shot blasting and so on) and check the planning settings.
2. **Resources**: add core machines, moulding lines, furnaces and work centres with their rated capacity, units and efficiency. Open one to add downtime and to see its available minutes for the next seven days. Click any number to see how it was worked out.
3. **Customers**: code, name and A, B or C priority.
4. **Parts and routes**: enter each part's weights, pieces per mould and cores per mould, tick the customers it is supplied to, then open **Route**. Switch on the operations the part uses, enter times, choose the allowed resources and save. Orange "to check" notes never block a save; red "fix" notes must be fixed first.

Every create, change and delete is recorded under **Audit log**.

## Planning moulds and melting from the month's orders
This phase plans **moulding and melting** only: getting the castings made. Fettling, machining and the later operations stay in the route but are marked "Not planned (Phase 2)".

1. **Upload the month's orders** (Monthly Scheduler, Upload Excel). Download the template: one row per order with Part Number, Order Qty and Dispatch Date, and optionally Month, Customer, Status (Open or Closed), WIP Stock, FG Stock and Dispatched Qty. After the preview you see the parts that are not in the Part Master; the other rows still load. Press **Create part** beside a part to add it (name, grade, weights, cavities), and the file is checked again. A blank customer uses the part's default customer.
2. **Review the parts.** An order whose part lacks master data shows **Cannot plan: missing master data** and says what to fill in: a moulding operation with a moulding machine and a rate, a pouring weight, a grade, and a furnace in the machine master.
3. **Update stock.** On the Monthly Scheduler grid or the Plan screen's Orders tab, type **WIP**, **FG** and **Dispatched** beside each order and press Enter. **Balance** = order qty − (WIP + FG + dispatched). **History** shows who changed what and when. An order with a balance of 0 shows **Covered by stock** and is not planned.
4. **Run planning** (Plan screen). Only Open orders are planned, only for the balance, earliest dispatch date first. A change to stock, quantity or status marks the plan **Stale**; press Run planning again.
5. **Read the plans.** **Mould plan**: per day, shift and machine, the part, moulds, castings and how much of the machine is used, and the orders that cannot meet their date. **Melt plan**: per day and furnace, each heat with its grade, metal, fill and what it pours; one heat is one grade. Warnings: a heat no furnace can take, and under-filled heats. **Print and export** has Excel for the mould plan, the melt plan, or both.

Order badges: **Planned**, **Covered by stock**, **Cannot plan: missing master data**, **At risk** (it cannot meet its dispatch date, or its metal has no furnace room), **Closed**.

Company settings (Masters, Company calendar, Planning settings): **Days needed after pouring** (default 3 working days) and **Start no earlier than** (default 7 working days before the deadline).

**For each real client, fill in:** the part's grade, casting weight, pouring weight per mould (castings plus runners and risers) and cavities; a moulding operation on the part with the allowed moulding lines and a rate (moulds per hour on the part, or on the line); each moulding line's rate, shifts and downtime; each furnace's heat size, heat minutes and heats per shift; the melt loss; shifts and holidays; a default customer for each part.

A sample file is in `docs/samples/monthly-orders-sample.xlsx` (it uses the demo foundry's parts).

## Plan (Planners and Admins run planning; everyone reads)
The Plan screen opens on the **Orders** tab. The tabs: Orders, Mould plan, Melt plan, Plan lines (one row per planned order with what holds it up), Gantt, Load heatmap and Print and export. A line's detail shows the numbers behind it: pieces to pour, moulds and the metal, each with its formula.

## What-if (Planners and Admins)
Use **What-if** to try a change on a copy of the plan and see which lines move, before anything real changes.

1. Type a name and press **Create scenario** (for example "F1 down on Thursday").
2. Under **Changes**, choose a kind and press **Add to scenario**. You can add several:
   - **Block a resource**: a furnace, line or work centre is out from one date and time to another.
   - **Change a quantity** or **Change a date** of a dispatch line.
   - **Add an extra shift**: for example a Sunday, with its times, break and the resources that work it.
   - **Add overtime**: extra minutes per shift on some days, for some or all resources.
3. Press **Run scenario**. The plan is calculated twice from today, as things stand and with your changes. **What changes** lists every line that moves, grouped as newly at risk, later, recovered, earlier. For each line you see the estimated date from and to, how many working days it moved, spare days and status before and after, and what holds it up. Below are the lines by status and the busiest shift of each resource before and after, and whether the bottleneck changed.
4. If you like the result, press **Apply to the real data…**. It lists exactly what will be created or edited. Apply writes the blocked period, the quantity and date edits, and the extra shifts and overtime (they then appear under Masters, Company calendar, Extra shifts and overtime) under your name, and recalculates the plan (a confirmed plan is kept and a new plan is started). An applied scenario stays as a record.

If you change the changes list, or the schedule or masters change, the result is marked **out of date** and Apply is disabled until you run it again. Viewers do not see What-if.

## Insights (everyone reads; Planners and Admins refresh)
**Insights** turns the plan and the schedule into ranked cards. Each card gives one plain line, the numbers, a **Next step**, and an arrow showing whether it is new, worse, better or unchanged since the last refresh.

- Cards are rewritten every time a plan is calculated. **Refresh insights** does it by hand.
- **Why** shows how the card was worked out. **Explain this** gives a plain-words explanation.
- On a load-balancing card, **Test it** plans twice, with and without letting another resource do that step, and shows which lines would move. Nothing is changed.
- Filter by severity (Critical, Warning, Info) and kind.
- **Daily digest**: the top five cards as a short summary. Print it, download it as PDF, or copy it as text for an email.
- **Ask Vezapp Planner**: type a question or pick one (which lines are at risk, where is the bottleneck, capacity gap, month forecast, a customer's on-time record, a part's status). Without an AI key it works in **basic mode** and says so. With a key it can answer more freely, but it may only use numbers from your own data. If an AI answer contains a number that is not in your data it is replaced by the data-based answer. **Monthly summary** writes a short narrative of the month. AI text is advisory.

  Talk to it like a colleague. It remembers the chat, so "why is the first one late?" or "and for C-102?" works, and it can answer in English, Hindi or Hinglish. After each answer it offers up to three follow-up questions you can click. **New chat** starts a fresh conversation. It can look at late lines, bottlenecks, which machines are free (for example "is HMC-1 busy tomorrow?"), a customer or a part (by name, partly typed is fine), a day's plan, the dispatch record, the month forecast, data problems, and try a what-if on a copy ("what if VMC-1 is down on Monday?"). It cannot change anything, and it says so if you ask it to; it also cannot say whether a brand-new order fits, only what spare capacity it can see.

## Reports (everyone reads)
Three reports, each on screen and as PDF or Excel with the logo:
- **Dispatch performance**: on-time share and delay by month, customer and part, for lines with an actual dispatch date. On time means shipped on or before the internal date. Filter by dates and customer code.
- **Utilisation**: planned load against capacity for every resource, with its busiest day and a column per week.
- **Plan versus actual**: each shipped line's estimated date in the latest *confirmed* plan against the real date, biggest miss first. Confirm a plan to start building this baseline.

## Data health (Planners and Admins)
**Settings, Data health** lists what makes a plan wrong or unfinished: parts without a route, route steps missing a time or resource, steps with no capacity modelled, lines past their internal date with no actual dispatch, and doubtful values. Each item says why it matters and links to where to fix it.

## Keeping the AI assistant switched on
Put your key in `.env` as `ANTHROPIC_API_KEY` (and, if you like, `ANTHROPIC_MODEL`), then restart the backend. Everything works without it.
## Machining: several operations per part, on the machines that are free
Open **Masters, Parts and routes**, a part, and its Machining row.

1. Press **Add machining operation** for each machining step the part needs (OP10, OP20, OP30...). Give each a name such as "Rough milling".
2. Under **Machine types that may run this operation** tick VMC, CNC and/or HMC. Every machine of a ticked type is allowed, including machines you add later. Untick any individual machine that cannot do this part. A machine of another type can be added on its own.
3. Enter the **time per piece for each machine type** (a VMC may take 12 minutes and an HMC 7), and a **default time** for any type left blank.
4. Enter the **setup per lot** in minutes. Each machine used for the lot is set up once before its first piece.
5. Save the route, then recalculate the plan.

The plan gives each piece of work to the allowed machine that can make the most pieces in the shift, so machines that are blocked, in maintenance, on one shift only or already full take less. The line detail on the Plan screen shows each step with the machines it ran on.

**Machine shop** (in the menu, everyone can read it) shows every machine used by a machining step, grouped by type: the share of working time planned each day with the hours left, blocked periods, and what is planned on each machine. Click a machine for its operations and setup hours. The Operations tab lists every machining step in the plan with its machines, start and finish. To see what a breakdown would do, block the machine for a day in What-if.
