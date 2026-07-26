# Germline amendment — `draft_only` moves to act-then-tell

**Filed** 2026-07-26 · **Ledger row** CG-35 · **Status** captain-gated (NAMED
Captain sudo-unlock handback, non-grantable)

## 1. The ruling being implemented

The Captain ruled on 2026-07-26 that **drafting moves to act-then-tell**,
overriding his own 2026-07-04 ruling. His stated reason: **with the trust
ladder unable to climb, earn-up meant asking forever.** Sending still requires
him — this changes only whether the cabinet asks before *writing* a draft.

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

**Optional, Captain's call at the window:** adding `"draft_only":
"notify_after"` to `_TRUST_FIRST_UNMEASURED` in `framework/authority/matrix.py`
(also germline) would pin the new cell by equality the way the two beachhead
rows are pinned, making a future silent earn-up regression a hard validation
error. It also makes the stale comment at `matrix.py:147-148` ("draft_only and
deploy_nonprod are deliberately absent … they keep earn-up") true again. This
is a strict tightening; it is listed separately because it widens the ceremony
to a second file.

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
which this amendment does not touch, so no eval body changes.

## 6. Ceremony (Captain sudo, relock SAME day)

Batchable with the CG-33 / CG-34 windows.

1. Re-verify lock state fresh: `bash cabinet/scripts/germline-lock.sh status`
   plus `ls -lO framework/policies/authority-matrix.yml` — boundary state
   changes between sessions.
2. `sudo bash cabinet/scripts/germline-lock.sh unlock`
3. Apply §3 edits 1 and 2 (and the §3 optional `matrix.py` tightening if the
   Captain wants it) — or, if the edit was landed to master first, check the
   landed bytes out into the live tree.
4. Gates green, in this order:
   * `python3.12 -c "import yaml;yaml.safe_load(open('framework/policies/authority-matrix.yml'))"`
   * `python3.12 -m pytest framework/authority -q` (matrix validators, posture
     tables, earn-up narrows, policy engine)
   * `bash cabinet/scripts/run-golden-evals.sh`
   * `python3.12 cabinet/scripts/cognitive-architecture-census.py`
5. `sudo bash cabinet/scripts/germline-lock.sh lock` then `status` + `verify`
   in the SAME session.

## 7. Rollback

One revert of `framework/policies/authority-matrix.yml` (and `matrix.py` if the
optional tightening was taken) to the pre-amendment bytes — itself a
Captain-windowed germline edit. Nothing depends on the amendment until it is
applied: until the window opens, drafting keeps asking, which is the
pre-ruling behaviour, not a broken state.

## 8. Honest status until the window opens

**The ruling is NOT in effect.** No setting anywhere claims otherwise — the
arm-the-cabinet unit deliberately shipped no config naming `act_then_tell`,
because that token resolves to `guardian` and would have been a setting that
lies. The live matrix still reads as the 2026-07-04 ruling, which is the truth
of the deployment until the Captain's unlock window.
