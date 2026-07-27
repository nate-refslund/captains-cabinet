# Germline amendment — `draft_only` moves to act-then-tell

**Filed** 2026-07-26 · **Ledger row** CG-35 · **Status** captain-gated (NAMED
Captain sudo-unlock handback, non-grantable) · **AWAITING CAPTAIN** for the
ceremony only

> **LANDED 2026-07-26** on `feat/draft-only-act-then-tell`. This document was
> first written (by the arm-the-cabinet unit) as a *proposal*; the edit it
> proposes is now **on master**, under the landed-then-ceremonied rule for
> germline CONTENT: build it in a clone, land it like any change, and leave ONE
> Captain unlock/relock that re-materialises the landed bytes into the locked
> tree. Reply **"apply draft act-then-tell"** to run that window. §2's original
> framing ("could not ship in that unit") remains true of *that unit* and is
> kept for provenance — it was never a claim that the change could not land at
> all, and §6 already allowed for landing first.
>
> What landed, beyond §3's two edits: the §5 test-pin moves; comment-only
> corrections in the three germline modules that still claimed `draft_only`
> "keeps earn-up" (`matrix.py`, `policy_engine.py`, `action_undo.py`); a
> plain-language fix to `docs/how-your-cabinet-is-governed.md`; and new CI arms
> verified to FAIL against pre-change code (§5a). The §3 **optional**
> `_TRUST_FIRST_UNMEASURED` tightening was **NOT** taken — it stays the
> Captain's call at the window (§3a says why). One **open item** was found
> while writing the mutation sensors and is recorded in **§9**; it is
> pre-existing on master and not introduced here.
>
> The germline path **SET** is byte-identical: `germline-lock.sh` is untouched
> and no path entered or left the locked set — only the CONTENT of four
> already-locked files changed.

## 1. The ruling being implemented

The Captain ruled on 2026-07-26 that **drafting moves to act-then-tell**,
overriding his own 2026-07-04 ruling. His stated reason: **with the trust
ladder unable to climb, earn-up meant asking forever.** Sending still requires
him — this changes only whether the cabinet asks before *writing* a draft.

Stated as the one-line safety claim the rest of this document has to earn:
**it widens composing a draft, and it cannot widen delivering one.** Delivery
is `external_comms`, which stays `always_gated` at every confidence state in
every posture, before and after (§4c proves this four independent ways).

The 2026-07-04 ruling is recorded verbatim in the file this amendment edits
(`framework/policies/authority-matrix.yml:130-138`):

> `# CAPTAIN-RULING 2026-07-04: draft_only KEEPS the old reversible earn-up`
> `# ladder (Captain judgment — a draft is outbound-ADJACENT: its content`
> `# exists to leave the machine, so it earns autonomy rather than getting`
> `# it granted; actual sending stays behind the external_comms ceiling).`

## 2. Why this could not ship inside the 2026-07-26 arm-the-cabinet unit

**The file is germline.** `framework/policies` is a whole locked DIRECTORY
(`cabinet/scripts/germline-lock.sh` `DIRS`), so `authority-matrix.yml` is
physically unwritable in the live tree by this uid — by design. The doctrine
path for a germline *content* change is landed-then-ceremonied: build it in a
clone, land it like any change, and leave ONE Captain unlock/relock that
re-materializes the landed bytes. That ceremony is the non-grantable limit; it
is filed here rather than worked around.

**A correction to the brief that ordered the work.** The unit's brief said
`act_then_tell` is defined in `framework/authority/action_mode.py:110` but
excluded from `framework/authority/posture.py:62`, so "naming it in config
silently resolves to guardian", and asked for the rung to be made real.

That premise is true as stated but points at the wrong plane, and following it
would have been a much larger and more dangerous change than the ruling asks
for. There are two distinct planes:

| plane | vocabulary | what "act-then-tell" is there |
|---|---|---|
| authority matrix — lane × action-type → verdict | `propose_only` · `act_with_undo` · `notify_after` · `auto` · `always_gated` | **`notify_after`** — "act-and-tell … the notification IS the oversight surface" (`authority-matrix.yml:119-123`) |
| posture ladder — the deployment's autonomy level | `earn_up` · `guardian` · `sovereign` (+ the forward-compatible `act_then_tell` token) | a whole-cabinet posture, not a per-class rung |

The ruling is about the **`draft_only` risk class**, which lives in the first
plane. `notify_after` is fully implemented there today — it is what
`read_only_dispatch` already rides. **No posture change is required, and the
`act_then_tell` posture token must NOT be added**: `POSTURES` is the
whole-cabinet ladder, so adding it would widen every class at once rather than
drafting, and `framework/authority/posture.py` is itself germline. The
existing guard `test_action_mode.py::test_ladder_does_not_define_act_then_tell_today`
stays true and stays green under this amendment.

## 3. The complete proposed edit

**File:** `framework/policies/authority-matrix.yml` (germline, dir-cover)

**Edit 1 — the root/guardian table** (`:130-138`). Replace the earn-up ladder
with the trust-first act-and-tell ladder, mirroring the `read_only_dispatch`
row directly above it:

```yaml
      # CAPTAIN-RULING 2026-07-26 (supersedes the 2026-07-04 ruling recorded
      # below): draft_only moves from the earn-up ladder to act-and-tell.
      # Captain's reason: with the trust ladder unable to climb, earn-up meant
      # asking forever. A draft is still outbound-ADJACENT — but the drafting
      # is now done and TOLD, while actual SENDING stays behind the
      # external_comms hard ceiling, which this edit does not touch.
      # SUPERSEDED 2026-07-04 ruling, kept for provenance: "draft_only KEEPS
      # the old reversible earn-up ladder (a draft is outbound-ADJACENT: its
      # content exists to leave the machine, so it earns autonomy rather than
      # getting it granted; actual sending stays behind the external_comms
      # ceiling)."
      draft_only:
        graduated: notify_after
        eligible: notify_after
        propose_only: notify_after
        unmeasured: notify_after
        demote: propose_only
```

**Edit 2 — the sovereign posture table** (`:228`). Sovereign currently mirrors
the old earn-up ladder; leaving it would make sovereign NARROWER than guardian
at `unmeasured`, an incoherent inversion:

```yaml
          draft_only:        { graduated: notify_after, eligible: notify_after, propose_only: notify_after, unmeasured: notify_after, demote: propose_only }
```

**NOT edited:** the `earn_up` posture table keeps `draft_only: propose_only` at
all five states — earn_up may only NARROW versus the root table
(`matrix.py:_validate_earn_up_narrows`), and `propose_only`(1) is narrower than
`notify_after`(4). **NOT edited:** every hard-ceiling row, including
`external_comms` (`{"*": always_gated}`) — sending still requires the Captain,
which is the half of the 2026-07-04 ruling he did NOT override.

### 3a. The complete before/after cell map (both edited tables)

Ten cells, and nothing else in the file: not `risk_classes`, not
`hard_ceiling`, not `ceiling_frozenset_map`, not `bars`, not `cooldown_days`,
not `deploy`, not `veto_window_minutes`.

| confidence state | root/guardian BEFORE | sovereign BEFORE | BOTH AFTER |
|---|---|---|---|
| `graduated` | `auto` | `auto` | `notify_after` |
| `eligible` | `propose_only` | `propose_only` | `notify_after` |
| `propose_only` | `propose_only` | `propose_only` | `notify_after` |
| `unmeasured` | `propose_only` | `propose_only` | `notify_after` |
| `demote` | `propose_only` | `propose_only` | `propose_only` (**unchanged**) |

`earn_up` stays `propose_only` at all five states, unchanged — the one place a
reader might expect a matching widening and must not find one.

**`graduated` is the one cell that NARROWS**, deliberately: `auto` acts
*silently*, `notify_after` acts *and tells*. For an outbound-adjacent class the
notification IS the oversight surface, so no confidence state may let a draft
appear with no tell. The class ends up with one uniform rule — compose, then
tell, always — instead of a ladder. Nothing that acted before now proposes: it
is strictly more autonomous at four of five states and strictly more visible at
the fifth.

### 3b. Optional tightening — offered, NOT taken

**Captain's call at the window:** adding `"draft_only":
"notify_after"` to `_TRUST_FIRST_UNMEASURED` in `framework/authority/matrix.py`
(also germline) would pin the new cell by equality the way the two beachhead
rows are pinned, making a future silent earn-up regression a hard validation
error. This is a strict tightening; it is listed separately because it widens
the ceremony to a second file.

It was **not** taken at landing, for two reasons — either of which the Captain
may overrule at the window:

1. **Its threat model is already covered twice.** That dict defends the
   *preset/instance merge* channel, and for this policy type the channel is
   shut: `load_policies` REFUSES any preset/instance policy typed
   `authority_matrix` or named `authority-matrix`
   (`policy_engine._is_authority_matrix_policy`), and `instance/config/policies`
   is itself germline-locked. The only remaining channel is a direct edit of the
   floor file, which the shipped-table CI pins (§5, §5a) catch.
2. **It costs a framework production line against a budget at its ceiling.**
   `cognitive-architecture-census` holds
   `framework_production_noncomment_lines` at 67326 ≤ 67326 — zero headroom. A
   safety pin is not worth buying with a raised threshold, and per (1) the pin
   it buys is redundant.

The stale comment it would have repaired was fixed directly instead: the
`matrix.py` note now records the 2026-07-26 ruling *and* states why
`draft_only` is absent from the pin, so the file no longer claims `draft_only`
keeps earn-up.

## 4. Validator analysis (why the edit is legal)

`_validate_act_first_floor` (`matrix.py:597`) — three rules, all satisfied:

* rule (a) applies only when a row grants `act_with_undo` somewhere.
  `notify_after` is not `act_with_undo`, so it does not fire.
* rule (b) pins only `_TRUST_FIRST_UNMEASURED` = {`reversible`,
  `read_only_dispatch`}. `draft_only` is not a member, so no equality pin
  fires (see §3's optional tightening).
* rule (c) concerns beachhead rows moved under the hard ceiling — not this
  edit.

`_validate_earn_up_narrows` (`matrix.py:753`) — cell-by-cell on
`VERDICT_PERMISSIVENESS`. earn_up's `draft_only` stays `propose_only`(1) against
a root of `notify_after`(4): still narrowing, still legal.

Demote stays posture-invariant at `propose_only` in every table (§2.1) —
evidence still beats posture, and demotion evidence still lands fail-safe.

### 4a. `demote → propose_only` is NOT validator-required on this row

Worth stating plainly, because it is easy to assume the opposite and then stop
checking: rule (a) demands the safe demote landing only of rows granting
`act_with_undo`, and rule (b) only of the two `_TRUST_FIRST_UNMEASURED`
members. `draft_only` is neither, so the validator would have accepted a wider
`demote` cell here. `_validate_postures`' demote-invariance check only requires
root and sovereign to *agree* — which they would at any shared value. It is
kept at `propose_only` on doctrine, not because a check forced it, and §5a now
pins it so the choice cannot drift silently.

### 4b. `notify_after` is already implemented — no new capability

`notify_after` is a `VERDICTS` member, ranks 4 in `VERDICT_PERMISSIVENESS`, and
has a live allow-branch in `policy_engine`: it emits the gate tell via
`_emit_gate_tell` and returns `None` (allow). **The branch keys on the verdict
string, not the risk class**, so `draft_only` reaching it needs no new code. It
is also already in `_RUNG_LIFT_VERDICTS`. This amendment applies an existing
verdict to one more class; it introduces nothing.

Note also that `notify_after` never consults the undo plane — only the
`act_with_undo` branch runs `_act_with_undo_gap` (registered inverse + writable
journal). So `draft_only` keeping **no** registered inverse in `action_undo.py`
is correct and required no behavioural change there.

### 4c. Why DELIVERING a draft is still Captain-gated — four legs

Each checked in code rather than assumed:

1. **The ceiling row.** `external_comms` is `{"*": always_gated}` in the root
   and `earn_up` tables and at most the conditional `standing_grant` in
   sovereign. `no_ceiling_or_prod_auto()` sweeps the root table *and every
   posture table* and still returns True.
2. **The gate short-circuits above confidence.** A hard-ceiling risk class is
   resolved and blocked at step 2 of `_eval_authority_matrix` — above cell
   resolution and above the earn_up rung lift — with a dedicated
   `external_comms` message that tells the officer to *draft via queue_draft*
   instead. The widened row is never reached.
3. **The classifier routes by RECIPIENT, not by framing.** `classify_action`
   has **no branch that returns `draft_only` at all**. The draft-shaped tool
   `mcp__brain__queue_draft` classifies on who the message is addressed to: an
   outside recipient yields `external_email`/`external_message` (the ceiling),
   an internal one yields the internal kinds, and an unresolvable recipient is
   **fail-closed to external**. No classifier-reachable path can wear the
   widened class to reach a real person.
4. **The class owns exactly one non-egress action type.** `draft_only`'s
   `action_types` is exactly `[draft_only]`; `external_message` and
   `external_email` stay on `external_comms`.

Per-item Captain approval for external comms is a **non-grantable** limit — it
reaches real people outside the org — and nothing here touches it.

## 5. Test pins that must move in the SAME commit as the edit

These pin the 2026-07-04 ruling by value. They are not being weakened — they
are re-pinned to the new ruled values, which is what makes a future silent
drift red:

| file:line | current pin | becomes |
|---|---|---|
| `framework/authority/tests/test_matrix.py:235` | `draft_only.graduated == "auto"` | `== "notify_after"` |
| `framework/authority/tests/test_matrix.py:236` | `draft_only.unmeasured == "propose_only"` | `== "notify_after"` |
| `framework/authority/tests/test_matrix.py:231` (comment) | "draft_only keeps the old earn-up ladder verbatim" | rewrite to the 2026-07-26 ruling |
| `framework/authority/tests/test_matrix_postures.py:67,116` | expected earn_up + sovereign `draft_only` tables | sovereign row → `notify_after`; earn_up row unchanged |
| `framework/authority/tests/test_matrix_earnup.py:112` | mutation fixture `("draft_only","eligible","act_with_undo")` expects REJECT because root `propose_only`(1) < `act_with_undo`(4) | the mutation stops widening once root is `notify_after`(4) — re-point the fixture at a cell that still widens (e.g. `("draft_only","eligible","auto")`, 5 > 4) |

`memory/golden-evals/` is germline too; EVAL-026 exercises the *posture* seam,
which this amendment does not touch, so no eval body changes. (All 30 golden
evals ran green at landing.)

### 5a. New CI arms landed with the edit

Moving the pins above proves the new values are *present*; it does not prove
the walls held. Two classes were added in
`framework/authority/tests/test_matrix.py`:

- **`TestDraftOnlyActThenTell`** — the widening, in both tables. **Verified to
  FAIL against pre-change code**: master's YAML restored with `__pycache__`
  purged, three arms go red on `graduated: auto` / `propose_only` at the other
  four; green after. Also pins `draft_only == read_only_dispatch` (one rule for
  both act-and-tell classes), `earn_up` still proposing (the narrowing that must
  NOT have moved), the `demote` cell from §4a, and that the row never claims
  `act_with_undo` (which would silently demand an inverse it deliberately
  lacks).
- **`TestDraftWideningDidNotMoveTheCeilings`** — the walls. These pass before
  *and* after by design, so they are not left as shape assertions: they are
  backed by **mutation sensors that must RAISE** (letting `external_comms` act
  via `auto` and via `notify_after`; letting a sovereign ceiling act; drifting
  the sovereign `draft_only` demote off the root's), plus the live-classifier
  recipient-routing proof from §4c.3 and a **non-degeneracy guard** asserting
  the egress set is exactly `{external_message, external_email}` so the egress
  loop cannot pass vacuously over an empty set.

## 6. Ceremony (Captain sudo, relock SAME day)

Batchable with the CG-33 / CG-34 windows.

1. Re-verify lock state fresh: `bash cabinet/scripts/germline-lock.sh status`
   plus `ls -lO framework/policies/authority-matrix.yml` — boundary state
   changes between sessions.
2. `sudo bash cabinet/scripts/germline-lock.sh unlock`
3. **The edit is already on master** (see the landing note at the top), so this
   is a checkout, not a hand-edit: bring the locked tree to master so it carries
   the landed bytes. There is nothing to type. Only if the Captain wants the §3b
   optional `matrix.py` tightening is there an edit to make in this window.
4. Gates green, in this order:
   * `python3.12 -c "import yaml;yaml.safe_load(open('framework/policies/authority-matrix.yml'))"`
   * `python3.12 -m pytest framework/authority -q` (matrix validators, posture
     tables, earn-up narrows, policy engine)
   * `bash cabinet/scripts/run-golden-evals.sh`
   * `python3.12 cabinet/scripts/cognitive-architecture-census.py`
5. `sudo bash cabinet/scripts/germline-lock.sh lock` then `status` + `verify`
   in the SAME session.

## 7. Rollback

**One-revert rollback:** revert the single landing commit. It restores
`framework/policies/authority-matrix.yml` (`draft_only` back to `auto`@graduated
+ `propose_only` at the other four, in both the root and sovereign tables) and
the comment-only edits in `framework/authority/matrix.py`,
`framework/authority/policy_engine.py` and `framework/frontdoor/action_undo.py`,
plus the §5/§5a CI arms and `docs/how-your-cabinet-is-governed.md`. No schema
and no interface changes to unwind, and the **germline path SET** needs no
restoration — `cabinet/scripts/germline-lock.sh` was never touched, so no path
entered or left the locked set. If the §3b optional tightening was taken at the
window, revert that `matrix.py` hunk with it. Post-window the revert is itself a
Captain-windowed germline edit. Nothing depends on the amendment until the
window runs: until then the deployment keeps asking before drafting, which is
the pre-ruling behaviour, not a broken state.

## 8. Honest status

**On master: in effect. On the deployment: NOT in effect until the window.**
Those are two different trees and the distinction is the whole point of
landed-then-ceremonied. Master carries the new bytes; the deployment's
schg-locked tree still reads as the 2026-07-04 ruling, and will until the
Captain's unlock/relock window runs. A session reading the live locked tree and
concluding "the ruling never landed" would be reading the right file on the
wrong tree.

No setting anywhere claims otherwise — the arm-the-cabinet unit deliberately
shipped no config naming `act_then_tell`, because that token resolves to
`guardian` and would have been a setting that lies. That remains true: nothing
in this landing added such a config, and `POSTURES` is unchanged.

## 9. Open item found while landing — recorded, NOT closed

Writing the §5a mutation sensors surfaced a **pre-existing gap in the
validator**, present identically on master before this landing and unrelated to
the ruling. One sensor was written expecting a rejection and did not get one:

> `validate_matrix` checks that every `action_type` is mapped to exactly one
> risk class, but **not which class**. Relocating `external_email` from
> `external_comms` into any non-ceiling class validates clean. Because the
> gate's ceiling short-circuit is keyed on `risk_class in hard_ceiling`, such a
> matrix would route a real egress kind down the ordinary confidence path.
> `HARD_CEILING_TOUCHES` does not backstop this — per the design doc it guards
> **self-extension** (installing a capability), a different layer from action
> execution.

This landing does not widen that gap: the mapping is unchanged, and a ceiling
kind on a non-ceiling class was already unsafe. It does raise the stakes
marginally, since `draft_only` is now an act verdict rather than mostly-propose.

**The test was not weakened to match the behaviour.** It was rewritten to pin
the shipped mapping — `test_every_egress_action_type_sits_on_a_ceiling_row`,
with the non-degeneracy guard from §5a — which is a real sensor on the only
channel that can reach this file: the floor is germline and schg-locked, and
`load_policies` refuses any preset/instance `authority_matrix`, so a direct edit
is the sole route and it lands on that test.

Closing it *in the validator* needs new executable lines in
`framework/authority/matrix.py` against the census budget already at its ceiling
(§3b.2). That is a threshold decision, not a mechanical fix, so it is written
down here rather than silently left or silently bought with a raised budget.
