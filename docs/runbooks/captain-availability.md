# Captain availability — the dial the org sizes itself to

**Status:** BUILT 2026-07-26 (Captain ruling, same day). Onboarding asks;
the phone verb adjusts; two consumers read it. Nothing is scheduled — the dial
is a value and a resolver, not a service.

## What it is

One number the Captain declared about his own day: **how much time he has for
the cabinet**. The rule it exists to enforce:

> **The org fits the declared budget, never the reverse.**

Before it, the cabinet had no time-budget input at all. Twice-daily briefings
ran straight through a declared month-long absence, and 146 proactive cards
chased 2 approvals. Availability handling was two hand-parked service rows in
the services file. The dial replaces all of that with one declared value that
90%-elsewhere and 100%-cabinet are two settings of.

**UNKNOWN is a legal state**, and it means exactly: *the org does not know how
much of the captain it is entitled to.* Every consumer keeps its own
conservative default and **never invents a number**. A placeholder that pretends
to be an answer is the named failure here (the same class as the 1/3-scored
briefing that attributed to him a commitment he never made).

## The modes

`framework.env.AVAILABILITY_MODES` is the ONE source of truth — the onboarding
question, the phone grammar and every renderer read it, so a band change lands
everywhere at once.

| verb | minutes/day | means |
|---|---|---|
| `away` | 0 | nothing but a genuine emergency reaches him |
| `minimal` | 10 | about ten minutes a day |
| `part_time` | 30 | about half an hour a day |
| `substantial` | 120 | about two hours a day |
| `full_time` | 480 | the cabinet is his main seat |

`full_time`'s 480 is the framework's stated reading of a full working day. A
Captain who means something else states the number outright (`availability 6h`),
which always wins over the band.

## Precedence

`framework.env.captain_availability()` returns
`{minutes_per_day, mode, source, set_at}` — the same keys in every state.
`minutes_per_day is None` is the ONE unknown test.

1. **`instance/config/captain-availability.yml`** — the adjustment store, an
   append-only `entries:` list, **latest valid row wins**. Written by the phone
   verb, so a ruling from his phone always beats what onboarding stamped and a
   generator re-run can never demote him. `source: adjusted`.
2. **`captain_availability_minutes_per_day`** (+ optional
   `captain_availability_mode`) in `instance/config/platform.yml` — what
   cabinet-init stamped. `source: onboarding`.
3. **all-None** — UNKNOWN.

Any unreadable or out-of-range row reads as **absent** at its level, so the
next-oldest ruling stands. Nothing is ever repaired into a number nobody said.

## The verbs

**Onboarding (once, at cabinet-init):**

```bash
python3.12 -m framework.onboarding.availability question
python3.12 -m framework.onboarding.availability apply --choice part_time
python3.12 -m framework.onboarding.availability apply --choice skip
```

The question renders from the live mode table. `apply` records
`captain.availability` in `instance/config/cabinet-init.answers.yml`;
`cabinet/scripts/generate-instance.py` stamps the platform keys on its next run.
**`skip` writes nothing** — the honest absence.

**The phone (any time, the control he actually uses):** he types it in Telegram
and `cabinet/scripts/officer-inbound-poller.py` records it mechanically from its
own process, the same shape as `/killswitch` and `/score`:

```
availability 20m          availability 2h        availability 1.5h
availability minimal | part_time | substantial | full_time | away
availability ?            what does the org currently think?
```

Record first, confirm second. Anything that does not parse **falls open to the
Chair relay** — a real message is never silently eaten. A fractional minute is
refused rather than rounded: a number the dial cannot represent must come back
to him.

**Terminal (rarely needed):**

```bash
python3.12 cabinet/scripts/lib/captain_availability.py show
python3.12 cabinet/scripts/lib/captain_availability.py set 20m
```

**Dashboard:** display-only today (Settings → Captain → "Time for the cabinet"),
the same tech-debt shape as Timezone. Editing lands with the platform settings
action.

## Consumers

| consumer | what it does with the budget | when UNKNOWN |
|---|---|---|
| Captain-Seat Review (`memory/skills/cross-officer-retro.md` Part 1c) | judges cost RELATIVE to it — an ask that is fair at `full_time` is friction at minutes-a-day | the absence is itself pack evidence |
| `cabinet/scripts/meta-cognition/captain-seat-pack.sh` | prints the declared budget + `set_at` in its AVAILABILITY section | prints the measured absence line |
| `framework/comms/surface/config.py` | scales the active-card `cap` (≤10 → 1, ≤30 → 2, ≤120 → 3, ≤240 → 4, else the shipped 5) when the deployment set no cap | shipped default, unchanged |

Its sibling surface is `docs/runbooks/captain-dates.md` — the dates he SET, held
on the org's books so a briefing cannot drop one. Availability is how much of him
the org may spend; the dates store is what he told the org to remember.

A configured `cap` (env or `instance/config/comms-surface.yml`) always wins — a
configured value is a ruling. `availability_pacing: false` turns the derivation
off entirely. The front-door expiry/TTL constants are deliberately untouched.

## The balancing rules

- **The org fits the declared budget, never the reverse.** Send volume, what may
  demand a response versus FYI-only, and batching all derive from the dial.
- **Overflow escalates through act-with-undo, with receipts** — it does not pile
  up as asks he has no time to answer.
- **Silence still never means approval** (constitution D12, unchanged). A
  narrower budget narrows what is *sent*, never what counts as consent.
- **It is an INPUT he declared, never a performance number.** It is not derived
  from evidence, it is not about an officer, and it may never be rendered as an
  officer-visible measure of anyone.

## Persistence and the egg

- Live file **gitignored** (his own declaration, never repo content).
- Named in `cabinet/scripts/runtime-provision.sh`'s `INSTANCE_PERSISTENT_FILES`,
  so a deploy or rollback never resets it. Losing it would silently return the
  org to UNKNOWN and re-widen pacing with no error.
- The egg export **deletes** the live file and **ships**
  `instance/config/captain-availability.yml.example`, so a fresh cabinet starts
  UNKNOWN and asks at onboarding rather than inheriting a stranger's budget.
- `CABINET_CAPTAIN_AVAILABILITY_FILE` relocates the store; the repo-root
  `conftest.py` points it into the pytest session sandbox, so no test run can
  write the live declaration.

## Tests

| what | where |
|---|---|
| resolver: precedence, unknown, degenerate `away`, malformed rows, caching | `framework/tests/test_env.py::TestCaptainAvailability` |
| onboarding: live-table question (with a negative control), `skip` writes nothing, refusals, generator lockstep | `framework/onboarding/tests/test_availability.py` |
| phone verb: grammar accept/refuse, append-only, comment-safe provenance, deploy persistence | `cabinet/scripts/lib/tests/test_captain_availability.py` |
| consumers: pack both ends, retro clause + doctrine twin, pacing bands, poller dispatch | `cabinet/scripts/tests/test_captain_availability_wiring.py` |
| golden eval: pack present/absent arms + Part 1c contract pins | `cabinet/evals/captain-seat/harness.py` (EVAL-027-CAPTAIN-SEAT) |
