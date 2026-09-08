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

## 2. `framework_production_noncomment_lines` 66280 → 66518 (+238)

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
