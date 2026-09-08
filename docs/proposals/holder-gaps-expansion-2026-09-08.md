# Expansion adjudication — holder gaps (phase-1, unit 3b), 2026-09-08

One net-new member of one bijection class, and the two visible `maximum` raises
that pay for it. Two blind arms authored the unit contract on identical briefs
(**Fable 5.1**, arm A, and **Opus 5**, arm B), two further blind arms attacked
it, and the orchestrator adjudicated every divergence in writing before any code
was built (`phase1-contracts-v2-2026-09-07`, §3 and §10). This document is the
expansion registry's half of that record: what was added, what merge was refused
and on what evidence, and who reads the output.

Direction of record: **LAUNCH-DIRECTION — one owned responsibility, delivered**
(2026-09-06, three blind arms, Captain GO the same day). Its converged line
reads: *"Silent skips become recorded gaps (supervisor.py:199-203); four gap
kinds (information / skill / tool / authority missing); planner PROPOSES, the
existing rich contract VALIDATES."*

Provenance: per 2026-07-07 full-autonomy grant + 2026-07-21 ownership-on-GO.

---

## 1. `framework/missions/gaps.py` — `framework_production_modules` 212 → 213

**What it is.** `observe_holder_gaps(missions, active_slugs, actor=…)`: one pass
over a caller's compiled missions that records a keyed `capability_gaps` row for
every ready work item with no holder, and resolves the rows whose subject healed
(a roster role appeared, or the item finished). It routes nothing, claims
nothing, proposes nothing and blocks nothing.

**Why the tree needed it.** Two branches ended in a bare `continue`.
`framework/missions/supervisor.py` skipped a ready node with no `assigned_role`
under a comment that said *"Surface that gap later via OVI; silently skip for
now"*, and `framework/missions/session_bridge.py::get_next_task` answered `None`
over the same condition with no trace anywhere. A Cabinet whose work has no
holder is indistinguishable, from every surface the Captain has, from a Cabinet
with nothing to do. That is the failure the direction of record names, and
nothing in the tree closed it.

**The merge that was refused.**
`framework/learning/capability_gaps.py::record_gap` is the nearest existing
organ and the obvious fold target: it already owns gap identity, the dedupe
lock, the projection and the routing, and `observe_holder_gaps` is a caller of
it. Refused on three properties rather than on preference.

* **Different plane, and the fold inverts the dependency.** `capability_gaps`
  is the RECORD plane: it knows about needs, kinds, hit counts and autonomy
  policy, and nothing about work. The observer's whole subject is a compiled
  work graph — `mission["work_graph"]`, `ready_tasks()`, `assigned_role`,
  `NodeStatus`. Folding it in would make `framework/learning/` import
  `framework/missions/compiler` and `cabinet/scripts/lib/work_graph`, so the
  learning layer would depend on the mission layer to record a row for anybody
  at all.
* **Different failure contract.** `record_gap` RAISES on a bad input
  (`ValueError` on an empty need) — that is right for a store. The observer must
  never raise: its two callers are a supervisor pass and a locked prompt hook,
  and an exception in either costs the pass or the session, not just the row. A
  function cannot hold both contracts, and putting the swallowing wrapper inside
  the store would weaken the store for every other caller.
* **Different lifetime and different producers.** A gap record is a single
  durable fact. An observation is a repeated sweep whose whole job is to be
  idempotent across passes, and whose second half — self-resolution — is a
  decision about work-graph state that the record plane has no way to make.

The second candidate, `framework/missions/supervisor.py::find_unassigned_ready_
tasks`, is refused by direction: the supervisor is `disabled: true` in
`cabinet/services.yml` and push is parked, so the live pull path would have to
import a parked organ to record a row. That is the same refusal the claim
expansion made on the same file, for the same reason.

**Who reads the output.** `framework/missions/session_bridge.py` — the live pull
path, which calls the observer once per invocation under the claims lock, and
whose silence is the condition being recorded. The rows themselves are read by
the existing `/gaps` page (`cabinet/dashboard/src/lib/capability-gaps.ts` via
`cabinet/scripts/org-runtime.py gaps list --json`) and, for the two kinds only
the Captain can close, by the briefing card
(`framework/frontdoor/run_briefing.py::_gaps_notice`, A3.3). No new surface was
built for this and none was needed.

---

## 2. `framework_production_noncomment_lines` 66280 → 66524 (+244)

Measured with `cabinet/scripts/cognitive-architecture-census.py` on this tree:
81256 observed against the then-effective 81018. Per file:

| File | Δ | What the lines are |
|---|---:|---|
| `framework/missions/gaps.py` | +172 | the observer: keying, evidence, self-resolution, two never-raise wrappers |
| `framework/missions/session_bridge.py` | +27 | the pull path's one observation, under the claims lock |
| `framework/missions/supervisor.py` | +9 | the same on the routing pass |
| `framework/frontdoor/run_briefing.py` | +29 | `_gaps_notice`, the one card line A3.3 requires |
| `framework/learning/capability_gaps.py` | +1 | the `/gaps` ranking call, now that a keyed producer exists |

Every explanatory paragraph in the new code is a `#` comment by construction, so
what the census counts here is code and API contract, not prose.

A further **+6** on the same row, measured the same way (81262 observed against
the then-effective 81256), pays for the round-2 review fixes in §4: **+3** for
the `muted` set, the `unchanged` de-duplication and the `_warn` helper that
routes both failure paths through `claims.record_error` as well as stderr (net
+3, because the two `print(...)` blocks it replaces collapse into single
calls), and **+3** for the `_live_gap_with_id` docstring in
`framework/learning/capability_gaps.py` recording where the decline decision it
handed to this producer actually landed.

Raised VISIBLY on both rows rather than bought with a `temporary_allowances`
entry. An allowance promises a deletion gate, and there is no version of this
program in which the routing plane goes back to skipping silently: the organ is
permanent, and the ratchet re-pins at the new level.

---

## 3. What this expansion deliberately does NOT add

* **No new event type.** The observer emits `capability_gap_recorded` and
  `capability_gap_resolved`, both of which already exist and are already
  registered. `central_event_types` is unchanged.
* **No new kind.** `skill`, `authority` and `information` entered `VALID_KINDS`
  with unit 3a; this unit is their first producer, not their author.
* **No new UI.** The `/gaps` page already renders any kind it is handed.
* **No new store.** Gap state stays event-sourced; the only new file on disk is
  the lock unit 3a already created.

---

## 4. Round-2 review — the three decisions the reviewer asked for by name

The independent frozen review of PR #377 rejected the unit on three gaps and
left two notes. All five are answered here so the reasons survive the PR.

**The `unchanged` list is gap ids, one per subject (G1).** The record loop and
the resolve loop both walked every standing key and both appended it, so every
pass after the first answered `{"opened": [], "resolved": [], "unchanged":
[gid, gid]}` for ONE row — deterministic, and wrong against §3's typed return.
The resolve loop now owns the bucket outright; the record loop only opens.
Sensor: `test_a_second_pass_reports_the_standing_gap_exactly_once`, plus a
two-subject arm that pins the count per subject rather than in total.

**A Captain decline is a MUTE, and it sticks (G4 — the U3a handover).**
`capability_gaps._live_gap_with_id` answers `None` for a declined gap and its
docstring hands the decision to this producer verbatim: *"If the Captain should
be able to silence a standing condition, that is a `resolve`/mute decision for
U3b's producer."* It is one, and this is the decision: a keyed row is a
STANDING condition, so re-recording it would overturn his answer on the next
tick, every tick, and `/gaps` would show him a question he had already closed —
the system quietly outvoting its own authority root. A muted key is therefore
never re-recorded AND never resolved: closed is closed in both directions, and
only he re-opens it. It appears in none of the three lists. Two sensors, and
the second one is the guard against the naive version of this fix (folding
declined rows into `live` stops the re-record and starts RESOLVING rows the
Captain declined — measured red).

**The observation's failure channel is durable (G2, G3).** The pull path's only
production caller is `cabinet/scripts/hooks/session-task-inject.sh`, which runs
it as `RESULT="$(python3 -c "…" 2>/dev/null)"`. A stderr line there is
discarded, so an observation failing on every tick was invisible — the same
silence this unit exists to remove, one layer up. Failures now go to
`claims.err` beside the ledger (the seam the claim path in the same function
already used) and, from `observe_holder_gaps` itself, to stderr as well,
because that is where the supervisor's cron log is read by a human. The two
caller-level never-raise wrappers had no sensor at all — deleting either
`except` would have killed an officer's session or a routing pass with nothing
in the tree going red. Both now have one, each proved red by deleting the
`except` it guards.

**Residual, recorded rather than fixed: the claims lock is held wider than
A3.1 asks.** `_observe_gaps` holds `claims_lock()` across the whole
observation — a full `project_gaps()` ledger replay plus both loops — on every
claiming `get_next_task`, i.e. every prompt submit past the 90 s debounce. It
is correct and deadlock-free (nothing takes gaps → claims), and A3.1's letter
("keyed records are taken under the claims lock") is satisfied by a wider hold,
not violated by it. The cost is that every officer's claim serializes behind
every other officer's gap projection, and `project_gaps` has no `since` window.
NOT fixed here, on purpose: the phase-1 runtime set is one worker plus the
dashboard plus the poller (A0.7), so there is exactly one claimer, and
narrowing the hold means `observe_holder_gaps` acquiring the claims lock
itself — which is precisely the property the module comment relies on to argue
it cannot invert the lock order. The trigger to fix it is a second concurrent
worker; the two candidate fixes are bounding the critical section to the record
call, or giving `project_gaps` a `since` window. Whoever adds the second worker
owns this line.

**Residual, unchanged from cp1: the `/gaps` ranking for keyed rows.** A keyed
gap's `hit_count` stays 1 for life (A3.1 forbids the re-observation emit), and
`project_gaps` sorts by `-hit_count`, so a standing condition sorts below a
free-text gap seen twice. The order STANDS: 1 is the honest count, and
re-ranking would move every existing free-text row to fix an order nobody has
yet read as wrong. Rank keyed rows by `last_seen` when somebody has looked at
the page and says so.

