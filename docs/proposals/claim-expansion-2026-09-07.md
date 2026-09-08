# Expansion adjudication — the claim (phase-1, unit 2), 2026-09-07

Three net-new members of two bijection classes, and the visible `maximum` raises
that pay for them. Two blind arms authored the unit contract on identical briefs
(**Fable 5.1** and **Opus 5**), two further blind arms attacked it, and the
orchestrator adjudicated every divergence in writing before any code was built.
This document is the expansion registry's half of that record: what was added,
what merge was refused and on what evidence, and who reads the output.

Direction of record: **LAUNCH-DIRECTION — one owned responsibility, delivered**
(2026-09-06, three blind arms, Captain GO the same day). Phase 1 item 2 reads:
*"`claim(task_id, outcome_id, actor, lease)` under one lock across
replay+append; emits `work_item_started` WITH ids; lease/expiry/reassignment/
fencing; `get_next_task` skips live claims (the real pull path); the supervisor
honours claims. Sensor: two concurrent claimers ⇒ exactly one success (both
succeed today)."*

Provenance: per 2026-07-07 full-autonomy grant + 2026-07-21 ownership-on-GO.

---

## 1. `framework/missions/claims.py` — `framework_production_modules` 208 → 209

**What it is.** The atomic claim: `claim` / `renew` / `release` / `complete` /
`live_claim` / `live_claims`, plus the holder derivation and the lease. Storage
is the event ledger and one zero-byte lock file; there is no second table.

**Why the tree needed it.** Before this module the pull path had no claim at
all. `session_bridge.get_next_task` filtered ready-and-assigned nodes and
handed the same node to every caller, so two live sessions of one role both
believed they owned the same task. The compiler's `work_item_started` overlay
could not help: the only producer of that event emits a `task_ref`, never the
`task_id` + `outcome_id` pair the overlay keys on, so a started event had never
once been applied to a graph. The repo's own record already said so — the
mission supervisor's parked reason in `cabinet/services.yml` names zero
`def claim` hits as the obstacle.

**The merge that was refused.**
`framework/missions/session_bridge.py::get_next_task` is the obvious fold
target: it is the one production caller and the claim exists to make its result
exclusive. Refused on three properties of that function rather than on
preference.

* **Different lifetime.** `get_next_task` is a per-tick projection that returns
  a dict and forgets everything. A claim has a lifetime measured in ledger
  timestamps and is read back by the compiler's status overlay, the supervisor's
  routing filter and the completion fence — three consumers that must not import
  the pull path to ask whether a task is held.
* **Different failure contract.** `get_next_task` must never raise: it runs from
  a prompt hook and an exception there costs the whole session. `complete()`
  must raise, by code, on a stale token — that is what a fence is. One module
  cannot hold both rules without one of them being a comment.
* **Different interpreter floor is not the reason, and is worth saying so:**
  both are on the 3.9 floor, so that is not what separates them.

`framework/missions/supervisor.py::find_unassigned_ready_tasks` was the second
candidate and is refused by direction: the supervisor is `disabled: true` and
push is explicitly parked until pull proves insufficient. Putting the claim
inside a parked organ would mean the live pull path imports a parked one to
take a lock.

**Consumer, named before the producer landed:**
`framework/missions/compiler.py` — its `_apply_status_from_events` reads the
lease off the claim's own events and is what turns an expired claim back into a
ready task.

---

## 2. `work_item_claim_renewed` — `central_event_types` 91 → 93 (with §3)

**What it is.** A holder extending its own lease. Payload: `task_id`,
`outcome_id`, `claim_id`, `holder`, `lease_s`, `expires_at`, `renewals`.

**Why it is its own type.** The work item is neither started again nor completed
when a lease is extended, so every existing work-item type states something
false about it. `work_item_started` would be the closest, and re-emitting it
would make the replay unable to tell a first claim from a fifth renewal — which
is precisely the count the drill asserts.

**The merge that was refused.**
`framework/events/emitter.py::VALID_EVENT_TYPES` already carries
`work_item_started`, and "just re-emit started with a later expiry" is the
zero-new-type option. Refused because the claim chain is derived by replay: the
liveness rule is *the latest started with a claim_id, no terminal and no release
after it*. A renewal spelled as a second `started` would open a NEW chain with
the same token, and the fence's "is this the latest claim?" question would then
have two right answers. Keeping the renewal a distinct type is what lets the
replay chain a renewal to the claim it renews and refuse one that chains to
nothing.

**Consumer:** `framework/missions/compiler.py` (the lease fix-up in
`_apply_status_from_events` reads `expires_at` off renewals).

---

## 3. `work_item_claim_released` — `central_event_types` 91 → 93 (with §2)

**What it is.** A claim ending before its work does: a holder handing the task
back (`reason: released`), or the next claimer recording the takeover of a lease
that ran out (`reason: expired`). Payload: `task_id`, `outcome_id`, `claim_id`,
`holder`, `reason`.

**Why it is its own type, and why it is the CLAIM that is released.** The name
was adjudicated: arm A proposed `work_item_released`, arm B
`work_item_claim_released`, and B was ruled — it is the claim that ends, not the
item, and an item-shaped name would read as a completion in every replay that
scans `work_item_*`.

**Why not reuse `work_item_failed`.** A release is not a failure: the task did
not fail, nobody judged it, and `failed` sets `verification_passed = False`,
which would durably record a verdict nobody reached. The status overlay maps a
release to PENDING — back in the ready set, no verdict attached.

**The merge that was refused.**
`framework/missions/compiler.py::_EVENT_TYPE_TO_STATUS` is where the fold would
have to live if the release were expressed by re-mapping an existing type. There
is no existing type whose meaning survives the re-map: `completed` and `failed`
are terminal and `started` is the thing being ended.

**Consumer:** `framework/missions/supervisor.py` (`find_unassigned_ready_tasks`
routes a released task again, because it is no longer held).

---

## 4. Mass — `framework_production_noncomment_lines` 64741 → 65528

+787 non-comment lines under `framework/`, measured with
`cabinet/scripts/cognitive-architecture-census.py` on this tree (observed 80178
against the then-effective 79391), not summed on paper. The mass is the claim
module itself plus the claim-aware halves of the pull path, the status overlay,
the routing filter and their sensors.

RAISED VISIBLY rather than paid by a temporary allowance, for the same reason
every row above it in the contract gives: an allowance promises a deletion gate,
and a claim primitive that the whole phase-1 acceptance drill runs through is
never getting deleted.

---

## 5. What this expansion does NOT buy

* No new door, no new actor, no new authority. A claim names a holder; it grants
  nothing.
* No second store. The one durable non-event artifact is a zero-byte lock file
  beside the ledger.
* Nothing under a locked path. The session hook that pulls work is untouched:
  its call and its stdout contract are byte-identical, which is why the pull
  path keeps its Python 3.9 floor and why that floor now has a CI job of its
  own.
