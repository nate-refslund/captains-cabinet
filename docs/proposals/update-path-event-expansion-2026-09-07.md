# Expansion adjudication — the update path's three receipts (2026-09-07)

Adjudicates three surplus members of `central_event_types`:

- `cabinet_update_applied`
- `cabinet_update_refused`
- `cabinet_update_rolled_back`

Registered in `framework/events/emitter.py` (`VALID_EVENT_TYPES` and
`_AGGREGATE_MAP`) by the phase-1 update-path unit, and paid for here with a
visible `maximum` raise (91 → 94) rather than a baseline line: the baseline is a
snapshot of a pinned tree and a genuinely new member belongs in the surplus,
where it stays visible.

## What the members are for

An installed Cabinet is an unpacked export with no version control in it. Until
this unit there was no way for it to learn that better bytes existed, and — the
part these three events close — no record anywhere that its bytes had changed.
The org could improve itself all day and the operator's install would sit where
it was, silently, with nothing in the ledger to say so. `/receipts` is the
surface where the Captain reads what the org did; an update that reached the
machine he actually uses is the single most consequential thing it can do, and
it was the one act that left no receipt.

All three are RECEIPT class: each describes an act that has already finished or
already been refused, and none of them may ever gate an update.

| Member | Payload | Emitted by |
|---|---|---|
| `cabinet_update_applied` | `from_sha, to_sha, changed, deleted, snapshot, door, built_at, inbox_owner, inbox_mtime, skipped_preserved` | `cabinet/scripts/cabinet-update.sh apply`, after the health gate came back green |
| `cabinet_update_refused` | `to_sha, reason, locked_paths, door` | the same script, before its first write, on a locked-path diff, a digest mismatch, an unreadable bundle, or a busy lock |
| `cabinet_update_rolled_back` | `from_sha, to_sha, reason, door` | the same script, on an automatic gate-red rollback or an operator-requested one |

They aggregate on `to_sha` — the commit the updater was trying to reach — so a
refusal, the retry that succeeded and a later rollback land on one aggregate and
read as one story.

## Why three types and not one with a status field

The merge question, answered rather than deferred: a single `cabinet_update`
event with `status ∈ {applied, refused, rolled_back}` would have moved this
budget by one instead of three.

Refused on the number that decides whether this path may run unattended. "How
often does an applied update roll back" is the safety measurement for the whole
leg, and with a status field it becomes a payload scan instead of a type filter.
Every consumer in this tree keys on event TYPE — `_AGGREGATE_MAP`,
`_COMPLETION_EVENT_TYPES`, `_EVENT_TYPE_TO_STATUS`, the receipts read model, the
mirror allow-lists — so a status-in-payload design would be the one vocabulary
in the ledger that none of them can select, and the rollback rate would be
computable only by a reader who already knew to look inside. The three payloads
also do not share a shape: a refusal carries `locked_paths` and no counts, an
apply carries counts and a snapshot, a rollback carries a reason and a restored
sha and creates nothing.

## Who reads them (corrected 2026-09-07, round-1 review)

The first spelling of these three rows named `framework/watchdog/receipts.py` as
the `consumer`. That is false and could never become true: `RECEIPT_CLASSES`
there is a frozenset of four watchdog/doctor/officer classes and `emit_receipt`
RAISES on anything else — it is a typed producer seam, not a reader. The census
could not catch it, and says so about itself: the `consumer` field is "an
EXISTENCE-AND-DISJOINTNESS check, never a USE check … Any path that exists in
the tree satisfies it — `.git/config` does, measured"
(`cabinet/scripts/cognitive-architecture-census.py`). So the label channel was
closed while the evidence channel stayed open, which is the exact failure class
this program has paid for most often.

Corrected two ways in the same commit:

1. **The claim is now true.** The three rows name
   `framework/frontdoor/run_briefing.py`, which reads all three types back by
   name through `_update_receipt_for` (`emitter.replay(event_types=…)`,
   selected on the bundle rather than on recency). It is not decoration: a
   bundle whose diff touches the constitutional set would otherwise sit in the
   inbox for ever while the only sentence the Captain ever saw said "ready to
   take — tap Apply", which did nothing every time he tapped it.

   **Corrected again 2026-09-08 (A5.15/A5.16), and the reason matters more than
   the correction.** This paragraph used to say a refusal "writes no state file
   at all", which made the ledger the ONLY channel that could carry one — and
   the first real apply on the installed Cabinet then proved that channel can
   be shut: the installed emitter predated the update path, rejected
   `cabinet_update_refused`, and the refusal reached neither the ledger nor any
   file a surface reads. A refusal now writes `state.json` as `{phase:
   "refused", bundle, reason, paths, ts, door}` with the record kept under
   `last_refusal`, and `run_briefing._update_refusal_line` reads THAT first;
   `_update_receipt_for` stays as the second channel and is still what these
   rows' `consumer` names. Two independent channels, because on 2026-09-08 one
   of them was silent and nobody could tell.
2. **The claim is now checked.**
   `test_an_event_type_expansion_names_a_consumer_that_actually_names_it` reads
   the LIVE contract and requires every `central_event_types` expansion row's
   consumer file to contain the member's name. An event type is a string, which
   makes this one class mechanically decidable; it is not a general use check —
   there cannot be one — but it is the difference between a claim and a grep.

## Adjudication

Two blind arms authored the phase-1 contracts independently on identical briefs
— arm A (Fable 5.1) and arm B (Opus 5) — and both arrived at three separate
update event types with these names and this split; the adjudicated contract of
record (§0 "New (register in `VALID_EVENT_TYPES`…)", §5 "Events") carries them,
and the attack panel that followed (amendments A5.1–A5.13) narrowed the payloads
without ever proposing to collapse the types. Agreement across two blind arms is
confidence, not proof, so the merge question above is answered on its own
evidence.

`subagent_started`, the fourth type both arms proposed, is deliberately NOT
registered (amendment A0.5): nothing emits it until a germline ceremony, and a
registered type with no emitter is vocabulary the cabinet can say about itself
for free.

Provenance: per the 2026-07-07 full-autonomy grant + 2026-07-21
ownership-on-GO; direction of record `direction-employee-2026-09-06`, contract
of record `phase1-contracts-v2-2026-09-07` §5 and amendments §5.
