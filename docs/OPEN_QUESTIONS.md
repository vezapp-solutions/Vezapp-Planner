# Open questions

Unresolved points. Each says what is blocked or assumed meanwhile.

| # | Question | Needed by | Assumed meanwhile |
|---|---|---|---|
| Q1 | **Time basis (section 5.5).** The manager said "give minutes to each operation and specify if it is per shift or per day". Does that mean (a) minutes per piece, mould or batch plus a capacity bucket of shift or day, or (b) a fixed block of N minutes of the shift or day? | Phase 1 | (a), with "fixed minutes per shift" and "fixed minutes per day" also offered as time-basis options. Please confirm with the manager. |
| Q2 | Where is rejection booked by default? The spec says after Fettling (configurable). Is that right for steel castings that are rejected at machining or inspection? | Phase 3 (built) | After Fettling, configurable per company. |
| Q3 | Must pouring always happen in the same shift as moulding? | Phase 3 | Yes by default, as a company setting (`pour_same_shift`). |
| Q4 | Melt loss default. Spec says 0 with a warning when blank. Do clients have a typical figure per alloy? | Phase 1 | 0%, with a warning. |
| Q5 | Should customers who supply several parts across grades share capacity priority beyond A/B/C (for example, by contract)? | Phase 3 | A/B/C only, as the tie-break. |
| Q6 | Which operation types beyond the default eight should clients see (shot blasting, grinding, heat treatment, painting, inspection)? | Phase 1 | Seeded as inactive; a Company Admin switches them on. |
| Q8 | ~~Should a Planner be allowed to add downtime?~~ **Resolved in Phase 4:** a Planner can block a resource, change quantities and dates, and add extra shifts or overtime by applying a what-if scenario; every record is audited under their name (A60). Planners still cannot edit masters directly. | Phase 4 | Resolved. |
| Q9 | Should company users be able to upload their own logo for printed plans? | Phase 3 | No; Vezapp logo only (A27). |
| Q10 | A fixed-minutes time basis (per shift or per day): is it one block per lot, or minutes in every shift or day the lot is in that operation? | Phase 3 (built) | One block per lot; see Q1. |
| Q11 | Should work already done (moulds made, castings in fettling) be entered so the plan starts from the real shop floor rather than from nothing? | Phase 4 | No; plans start empty today (A51). |
| Q7 | Is the Python 3.11 / 3.12 difference acceptable for the production host? | Phase 6 | Yes; see A1. |
| Q12 | **The live Claude layer has not been run against the real API.** It is tested with a stand-in model, including the number guard. Please add `ANTHROPIC_API_KEY` to `.env`, ask a few questions, and tell me what reads badly. | Before client use | Basic mode answers if the AI fails or is blocked by the guard. |
| Q13 | **Where will the production system be hosted** (your own server, a cloud provider, or a client's network)? This decides the deployment files (Docker image, proxy, backups). | Before first client | `DEPLOYMENT.md` lists what any host needs. |
| Q14 | Should the Planner see other planners' what-if scenarios, or only their own? | Phase 6 | All planners and admins of a company see all scenarios. |
| Q15 | What is a sensible on-time promise for dispatch: strictly on or before the internal date, or with a grace day? | Phase 5 | Strict (A68). A grace-days setting is a small addition if wanted. |

## Ideas for later (not built)

- **Instant pricing.** CASCULATE offers AI-based instant pricing for castings. A future Vezapp module could estimate cost per part from weight, grade, operation minutes and hourly rates.
- **WhatsApp daily digest.** The insight digest (Phase 5) is designed so a WhatsApp channel can be added later. Not built.
