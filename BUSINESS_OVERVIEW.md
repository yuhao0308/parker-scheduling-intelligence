# Parker Scheduling Intelligence — Business Overview

## What It Does

Parker Scheduling Intelligence is an automated staffing system designed for skilled nursing facilities. It handles two core problems that coordinators face every day:

1. **Monthly Schedule Generation** — Automatically builds a full month of shift assignments, making sure every unit is covered while respecting staff licenses, work hours, and experience.
2. **Emergency Call-Out Replacement** — When an employee calls out sick on the day of their shift, the system instantly ranks the best available replacements and explains why each one is a good fit.

---

## How It Works: Normal Month

A coordinator opens the Schedule page and sees April's calendar at a glance. Each day shows color-coded shift pills for every unit:

- **Green** = fully staffed, no action needed
- **Yellow** = unassigned slot, needs attention
- **Red** = someone called out, needs immediate replacement

In an ideal month with full staff (26 employees across RN, LPN, CNA, and PCT roles), the system fills all 1,080 shift slots automatically. The coordinator sees a wall of green — the schedule is done.

**What the system considers when assigning staff:**
- **Licenses and certifications** — RNs and LPNs are placed in licensed slots; CNAs and PCTs in certified slots. An LPN is never assigned to an RN-only position.
- **Full-time vs. part-time hours** — Full-time staff get scheduled up to 40 hours/week; part-time up to 20 hours. The system's top priority is making sure everyone gets their minimum hours before assigning extras.
- **Clinical experience** — Staff trained in subacute care are preferred for subacute units. Long-term care staff are not floated to subacute unless necessary.
- **Rest windows** — No one is scheduled back-to-back shifts without adequate rest (e.g., Night shift then Day shift the next morning).
- **Unit exclusions** — If a staff member has been excluded from a specific unit (for any reason), they will never be assigned there.

---

## How It Works: Staff Shortage

When the facility is short-staffed (e.g., only 15 of 26 positions filled), the system still generates the best possible schedule. The coordinator sees:

- A mix of green, yellow, and red slots
- A **scenario badge** (Ideal / Moderate / Critical) indicating severity
- A count of unfilled slots with detailed warnings
- The system prioritizes highest-acuity units first, so subacute patients always have coverage

The coordinator can click any yellow or red slot to see what happened — why it couldn't be filled, and who the closest available candidates are.

---

## How It Works: Day-Of Emergency

It's 6 AM and a CNA calls out sick for the Day shift on Subacute Unit 1. Here's what happens:

1. The red slot appears on the calendar immediately
2. The coordinator clicks the red pill
3. The system shows **3 ranked replacement candidates**, each with a clear explanation:

   **#1 — Maria Santos (CNA, Full-Time)**
   - Hours: 24.75 h worked (15.25 h remaining this cycle)
   - Distance: 3.2 miles from facility
   - Experience: CNA — Home unit match (Subacute Unit 1)

   **#2 — James Park (CNA, Part-Time)**
   - Hours: 8.25 h worked (11.75 h remaining this cycle)
   - Distance: 8.1 miles from facility
   - Experience: CNA — Subacute cross-trained

   **#3 — Lisa Chen (PCT, Full-Time)**
   - Hours: 33.0 h worked (7.0 h remaining this cycle)
   - Distance: 5.5 miles from facility
   - Experience: PCT — Floating from LT Unit 3

4. The coordinator selects the top candidate with one click
5. If they choose someone other than #1, the system asks for a brief reason (for compliance tracking)

---

## Scoring: How Candidates Are Ranked

Each replacement candidate receives a score from 0 to 100 based on five factors:

| Factor | Weight | What It Measures |
|--------|--------|-----------------|
| Overtime Headroom | 40% | How many straight-time hours remain — avoids costly overtime |
| Clinical Fit | 30% | Does their training match the unit type (subacute vs. long-term)? |
| Proximity | 20% | How close do they live? Closer = faster response |
| Float Penalty | 10% | Are they being sent to an unfamiliar unit? New hires get extra protection |
| Historical Acceptance | 10% | Have they reliably accepted shifts before? |

These weights are fully configurable. If the facility decides proximity matters more than overtime cost, the weights can be adjusted in real time from the admin panel.

---

## Data the System Needs

The system works with data that nursing facilities already track:

- **Staff roster** — Names, licenses (RN/LPN/CNA/PCT), full-time or part-time, home unit, hire date
- **Schedule entries** — Who is assigned where, on what date and shift
- **Hours ledger** — How many hours each person has worked this pay cycle
- **Callout records** — When someone calls out, which unit and shift
- **Unit information** — Unit names, types (subacute vs. long-term), active status

All data syncs from the facility's existing scheduling system. Parker does not replace their system — it sits on top of it.

---

## Key Benefits

1. **Saves coordinator time** — Monthly scheduling that used to take hours is done automatically
2. **Reduces overtime costs** — The system's #1 priority is keeping staff within straight-time hours
3. **Ensures compliance** — License requirements, rest windows, and unit exclusions are enforced automatically
4. **Fair workload distribution** — Everyone gets their minimum hours before anyone gets extra shifts
5. **Transparent decisions** — Every recommendation comes with a plain-English explanation; no black box
6. **Handles emergencies fast** — Day-of callouts get ranked replacements in seconds, not phone calls

---

## What's Next

- **Leave request integration** — Staff submit leave forms through the app; the system evaluates scheduling impact before approval and shows the coordinator exactly what changes when leave is granted
- **Multi-facility support** — Extend scheduling across multiple facility locations
- **Predictive callout modeling** — Use historical patterns to predict which shifts are likely to have callouts and pre-position backup coverage
