# p1-update-path — cp4: the merge with master (landing agent, 2026-09-08)

Branch `feat/p1-update-path` at `cc075d035a726694cc9546d9e2cd4b45a5365b23`, approved by an
independent reviewer at that exact SHA. Master moved from the review's base
`c479b5f5fccde28a2629c228b5b386d3218c4ac9` to `b50880eb140a338fca8fd0cb1444d79fa4d87126`
while the review ran: phase-1 units U1 (tap, #371), U2 (claim, #373), U3 (gap kinds, #370)
and U3a/U4r (drill, #374) all landed. This checkpoint records the merge, which is where the
only new judgement in this landing was spent. No unit code changed.

## Conflicts, and how each was resolved

### 1. `cabinet/config/cognitive-architecture-contract.yml` — the event-type ceiling

Both units raised `budgets.central_event_types.maximum` off the same base of **91**, blind
of each other: the claim unit to **93** (+2, `work_item_claim_renewed` / `_released`), this
unit to **94** (+3, `cabinet_update_applied` / `_refused` / `_rolled_back`).

Resolved to **96 — the SUM of the two raises over the common base**, per the contract of
record's round-2 amendment (`phase1-contracts-v2-2026-09-07.md`, A0.10 block: "the merged
value is the SUM of the raises over the common base (never the max of the two), and every
expansion row from both sides is kept"). Taking the max would have left one unit's members
unbudgeted while looking like a resolution. Both comment blocks are kept verbatim and a
third records the arithmetic.

Observed after the merge: `len(VALID_EVENT_TYPES) == 96` — at the ceiling, zero headroom,
which is the shape this budget is supposed to have. All five expansion rows from both sides
survive; no `temporary_allowances` row from either side was dropped (50 phase rows, master
added none).

### 2. `cabinet/config/cognitive-architecture-contract.yml` — a consumer that could not read

**This is the one substantive finding of the merge, and it is a defect on master, not in
this PR.** The claim unit's `work_item_claim_released` expansion row names

    consumer: framework/missions/supervisor.py

and that file does not contain the string `work_item_claim_released`, nor can it: the
supervisor is PARKED in `cabinet/services.yml`, and "the supervisor honours claims" is
phase-2 work — the row's own `provenance` field says so. The census's `consumer` field is an
existence-and-disjointness check by its own docstring, so any real file satisfies it and the
gate passed on a claim that was not true.

It surfaced only at the merge because the sensor that catches it is **this unit's**:
`test_an_event_type_expansion_names_a_consumer_that_actually_names_it` checks the LIVE
contract for USE rather than existence. This unit shipped it after walking into the identical
hole in round 1 (its own three rows first named `framework/watchdog/receipts.py`, a typed
seam whose `emit_receipt` raises on anything outside four watchdog classes). The sensor is
doing exactly the job it was written for, one unit over.

Resolved by correcting the field to `framework/missions/compiler.py`, which reads the type by
name in `_EVENT_TYPE_TO_STATUS` and maps it to `NodeStatus.PENDING` (compiler.py:263, :283).
That file is not a guess: it is the table this row's own `merge_refuted` field cites as the
one a reuse would have to re-map, and it is the file the sibling row
(`work_item_claim_renewed`) already names. The correction is a one-field data fix to a
contract row plus its provenance note — no code change to either unit, and the alternative
(weakening the arm so the false row passes) is the disabled-sensor failure this program has
paid for a dozen times.

### 3. `cabinet/scripts/tests/test_cognitive_architecture_census.py` — two hunks

**(a) the sibling-maximum literal.** Master keeps three deliberate literals in
`test_live_allowance_raises_only_its_named_effective_budget`, on the ground that the arm's
claim is "an allowance naming `claude_skills` raises `claude_skills` and NOTHING else", and
reading the number back out of the same contract the census read weakens that to a
tautology about the census's own echo. This unit had replaced the literal with a contract
read to stop it going stale. **Master's shape kept**, literal updated to 96 with both raises
named in the comment: the literal is the stronger sensor, and its siblings (23, 5) are
literals for the same reason.

**(b) the exact-surplus assertion.** Both sides independently fixed the same latent bug (a
hardcoded `[SYNTHETIC_MEMBER]` surplus assertion that breaks the first time a real expansion
row lands). Master extracted a `_live_expansion_members()` helper; this unit inlined the
same set comprehension and additionally added a redundant membership assert. **Master's
helper kept** — same meaning, DRY, and its comment says why `in` is not enough. This unit's
NEW test function in the same hunk (`…names_a_consumer_that_actually_names_it`, §2 above) is
kept in full.

### 4. `framework/triggers/tests/test_schema_registry.py` — `CENTRAL_ENUM_SIZE`

Master pins the enum size as a literal; this unit deleted the pin, arguing that a size
literal inside the M4 test reds for a reason M4 does not name (the enum grows legitimately
through the expansion registry, a governance route the registry under test cannot reach).

**The pin is KEPT**, updated 93 → 96, with this unit's argument recorded in the comment
beside it. Reasons: it is a lockstep sensor — an unratified member added to the enum without
a contract raise has nowhere else in this file to go red — and it is independent of the M4
identity assertion (`after == before`), which master already carries and which was this
unit's actual substitute. Keeping both loses nothing and keeps the stricter arm. Removing a
sensor at a merge, to avoid editing one number, is not a resolution.

## What was NOT needed

- **A0.10 interpreter-pin PENDING rows**: no action. `framework/tests/test_interpreter_pin.py`
  arrives from master with the `cabinet/scripts/work-graph-complete.sh` row already retired
  by U2's lander; the surviving row (`cabinet/cron/mission-supervisor.sh`) names a script
  this unit does not pin.
- **Locked set**: `germline-lock.sh` FILES(73)/DIRS(7) parsed programmatically and
  intersected with the merge's changed-file set (34 files) — **empty**, re-checked
  immediately before the merge commit.
