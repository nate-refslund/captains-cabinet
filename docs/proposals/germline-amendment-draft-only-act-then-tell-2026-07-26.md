# Germline amendment — `draft_only` act-then-tell — 2026-07-26

**Status:** AWAITING CAPTAIN — the *ceremony*, not the code. Ledger row
**CG-35**. The content below is **already landed on master** under the
landed-then-ceremonied rule for germline content: the edit was built in a
clone, reviewed, gated and merged like any change, and what remains is one
Captain unlock/relock window that re-materialises the landed bytes into the
locked working tree on the deployment machine. Reply **"apply draft
act-then-tell"** to run that window.

Nothing in this document asks for new authority. The germline path **SET** is
byte-identical — `cabinet/scripts/germline-lock.sh` is untouched, no path was
added to or removed from the locked set, and this amendment changes only the
CONTENT of four already-locked files.

---

## 0 · What this changes, in one paragraph

The Captain ruled (2026-07-26): *"the act first (except for emailing real
people…)"*. Composing a draft was the last obviously-reversible thing the
cabinet still had to ask permission for. The `draft_only` risk class moves off
the earn-up ladder onto **`notify_after`** — the act-and-tell verdict
`read_only_dispatch` already rides — at every non-demote confidence state, in
the root/guardian table and the sovereign table. `earn_up` is untouched
(narrowing stays legal, and the cautious start stays cautious). Every hard
ceiling is untouched. **This widens COMPOSING a draft. It cannot widen
DELIVERING one** — delivery is `external_comms`, which is `always_gated` at
every confidence state in every posture, before and after.

---

## 1 · The ruling

> the act first (except for emailing real people…)

Read narrowly and applied narrowly: drafting is act-then-tell; sending to a
real human outside the org keeps per-item Captain approval, which is a
structural, non-grantable limit and is not in scope here.

This SUPERSEDES the `draft_only` half of **CAPTAIN-RULING 2026-07-04**
(recorded in `docs/proposals/germline-amendment-trust-inversion-2026-07-04.md`),
which kept `draft_only` on the earn-up ladder as outbound-ADJACENT. The
2026-07-04 *reasoning* is not overturned — it is exactly why this is safe.
Adjacent is not outbound. The 2026-07-04 ruling's other half (`deploy_nonprod`
stays earn-up, prod-adjacent) is **untouched**.

---

## 2 · The exact edit

`framework/policies/authority-matrix.yml`. Two verdict rows, ten cells, and
the comments that describe them. No other key changed — not `risk_classes`,
not `hard_ceiling`, not `ceiling_frozenset_map`, not `bars`, not
`cooldown_days`, not `deploy`, not `veto_window_minutes`.

### 2a · Root / guardian table (`policies[0].verdicts.draft_only`)

| confidence state | BEFORE | AFTER |
|---|---|---|
| `graduated` | `auto` | `notify_after` |
| `eligible` | `propose_only` | `notify_after` |
| `propose_only` | `propose_only` | `notify_after` |
| `unmeasured` | `propose_only` | `notify_after` |
| `demote` | `propose_only` | `propose_only` (**unchanged**) |

### 2b · Sovereign posture table (`policies[0].postures.sovereign.verdicts.draft_only`)

Identical before and after to the root row above — the sovereign table
mirrored the guardian row before this amendment and mirrors it after.

| confidence state | BEFORE | AFTER |
|---|---|---|
| `graduated` | `auto` | `notify_after` |
| `eligible` | `propose_only` | `notify_after` |
| `propose_only` | `propose_only` | `notify_after` |
| `unmeasured` | `propose_only` | `notify_after` |
| `demote` | `propose_only` | `propose_only` (**unchanged**) |

### 2c · `earn_up` posture table — NOT TOUCHED

| confidence state | BEFORE | AFTER |
|---|---|---|
| all five | `propose_only` | `propose_only` (**unchanged**) |

Narrowing stays legal, so the cautious start keeps proposing. This is the one
place a reader might expect a matching widening and must not find one.

### 2d · `graduated` — the one cell that is not a widening

`graduated` goes from `auto` (act **silently**) to `notify_after` (act **and
tell**). That is deliberate and is the only cell in this amendment that is
narrower than before. For an outbound-adjacent class the notification IS the
oversight surface, so no confidence state may let a draft appear with no tell.
The result is one uniform rule for the class rather than a ladder: **compose,
then tell — always**. Nothing that acted before now proposes; the class is
strictly more autonomous at four of five states and strictly more visible at
the fifth.

### 2e · Comment-only edits in three germline modules

No executable line changed in any of these; the framework production-line
budget is unchanged (see §6).

- `framework/authority/matrix.py` — the `RISK_CLASSES` note and the
  `_TRUST_FIRST_UNMEASURED` note said `draft_only` "keeps earn-up". Corrected,
  with the reason it is still not in that equality pin (§3d).
- `framework/authority/policy_engine.py` — the `notify_after` allow-branch
  said `notify_after` is a sovereign-table verdict and "guardian carries
  none". That was already wrong on master (`read_only_dispatch` carries it in
  the root table) and is now doubly wrong. Corrected, and the branch now names
  `draft_only` as its second rider.
- `framework/frontdoor/action_undo.py` — said `draft_only` has no registered
  inverse *because* it keeps earn-up. The conclusion is unchanged (it still
  has none, deliberately) but the reason is now: `notify_after` never consults
  the undo plane, and a draft that was only composed has nothing outbound to
  reverse.

---

## 3 · Validator analysis

`framework/authority/matrix.py` is fail-closed: anything unknown, mistyped,
missing or extra raises `MatrixValidationError`. Every invariant it enforces
was checked against the new table, by reading the validator rather than by
trusting that the suite is green.

### 3a · Invariants that could have rejected this edit, and why they do not

| # | invariant | verdict on this edit |
|---|---|---|
| 1 | no ceiling/prod cell may be `auto` (`no_ceiling_or_prod_auto`, sweeps root **and every posture**) | untouched — no ceiling cell changed |
| 2 | `ceiling_frozenset_map.values()` == all six `HARD_CEILING_TOUCHES` | untouched |
| 3a | any non-ceiling row granting `act_with_undo` anywhere must grant it at `unmeasured` and demote to `propose_only` | **does not fire** — `notify_after` is not `act_with_undo`, so the row grants none |
| 3b | beachhead rows pinned by equality at `unmeasured` (`_TRUST_FIRST_UNMEASURED`) | `draft_only` is not a member, so no equality pin applies (see §3d) |
| 3c | no beachhead row may move under the hard ceiling | untouched |
| 4 | `postures.guardian` rejected; posture ceiling rows wildcard-only in {`always_gated`, `standing_grant`}; `standing_grant` never in the root table or on a non-ceiling row; **demote posture-invariant** | holds — root and sovereign `demote` are both `propose_only`, so the invariance check compares equal |
| 5 | `earn_up` may only NARROW vs root, cell by cell on `VERDICT_PERMISSIVENESS` | holds, and gets *more* headroom: `earn_up` `propose_only` (rank 1) against a root that rose from `propose_only`/`auto` to `notify_after` (rank 4) |
| — | shape rules: full 13-class coverage, all five states on non-ceiling rows, every verdict a `VERDICTS` member | holds — same shape, different values |

### 3b · Is `demote → propose_only` *required* by the validator here?

**No — and it is kept anyway.** Rule (a) requires it only of rows granting
`act_with_undo`; rule (b) only of the two `_TRUST_FIRST_UNMEASURED` members.
`draft_only` is neither, so the validator would have accepted a wider demote
cell. The demote invariance check in `_validate_postures` only requires root
and sovereign to *agree*, which they would have done at any shared value. It
stays `propose_only` because demotion evidence must always land fail-safe —
that is the doctrine, independent of whether a validator happens to enforce it
on this row. A CI arm now pins it (§7).

### 3c · `notify_after` is already implemented — not a new verdict

`notify_after` is a member of `VERDICTS`, carries rank 4 in
`VERDICT_PERMISSIVENESS`, and has a live allow-branch in
`framework/authority/policy_engine.py`: it emits the gate tell via
`_emit_gate_tell` and returns `None` (allow). The branch keys on the **verdict
string**, not on the risk class, so `draft_only` reaching it needs no new code
whatsoever. It is also in `_RUNG_LIFT_VERDICTS`, so the earn_up trust ladder
could already lift a cell to it. **No new capability is introduced by this
amendment** — an existing verdict is applied to one more class.

Notably, `notify_after` does **not** consult the undo plane. Only the
`act_with_undo` branch runs `_act_with_undo_gap` (registered inverse +
writable journal). So `draft_only` keeping no registered inverse in
`action_undo.py` is correct and required no change.

### 3d · Why `draft_only` was NOT added to `_TRUST_FIRST_UNMEASURED`

Adding it would pin `unmeasured == notify_after` by equality, which is
superficially attractive. It was deliberately not done, for two reasons, and
the code comment records both:

1. That dict defends the **preset/instance merge** channel. For this policy
   type that channel is already closed twice over: `load_policies` REFUSES any
   preset/instance policy typed `authority_matrix` or named `authority-matrix`
   (`policy_engine._is_authority_matrix_policy`), and `instance/config/policies`
   is itself germline-locked. The only remaining channel is a direct edit of
   the floor file — which the shipped-table CI pins catch (§7).
2. It costs a framework production line against a budget already **at its
   ceiling** (`cognitive-architecture-census`:
   `framework_production_noncomment_lines` 67326 ≤ 67326). A safety pin is not
   worth buying with a raised threshold, and the pin it would buy is redundant
   per (1).

---

## 4 · What stays unchanged

- **All six hard ceilings** — `external_comms`, `deploy_prod`, `spend`,
  `secrets`, `network_write`, `credentials_grant`: single-`*` wildcard,
  `always_gated` in root and `earn_up`, `standing_grant` (grant-or-file-a-NEED,
  never unconditional) in sovereign. Byte-identical before and after.
- **`earn_up`** — every cell, including `draft_only`.
- **Every other risk class** — `reversible`, `read_only_dispatch`, `pm_write`,
  `calendar_write`, `internal_comms`, `deploy_nonprod`: byte-identical.
- **`framework/authority/posture.py`'s `POSTURES`** — deliberately NOT
  extended. There is no new `act_then_tell` posture and there must not be: the
  posture ladder is a whole-cabinet selector, so a token there would widen
  every risk class at once instead of drafting. Act-then-tell is not a missing
  capability needing a new rung — the matrix already grants `act_with_undo` on
  trust-first cells from day one, so acting first is the ruled default and this
  amendment extends it to one more class.
- **`cabinet/scripts/germline-lock.sh`** — untouched. The locked path SET is
  byte-identical; only file CONTENT changed.
- **The undo registry** — `draft_only` still has no registered inverse, now
  for the correct reason (§2e).

---

## 5 · Why sending is still Captain-gated

Four independent legs, each checked rather than asserted:

1. **The ceiling row.** `external_comms` is `always_gated` for every
   confidence state in the root and `earn_up` tables, and at most the
   conditional `standing_grant` in sovereign. `no_ceiling_or_prod_auto()`
   sweeps the root table AND every posture table and still returns True.
2. **The gate short-circuits before confidence is consulted.** In
   `policy_engine`, a hard-ceiling risk class is resolved and blocked at step 2
   — above the cell resolution and above the earn_up rung-lift — with a
   dedicated `external_comms` message that literally tells the officer to
   *draft via queue_draft* instead. The widened row is never reached.
3. **The classifier routes by RECIPIENT, not by framing.** `classify_action`
   has **no branch that returns `draft_only` at all**. The draft-shaped tool
   `mcp__brain__queue_draft` classifies by who the message is addressed to: an
   outside recipient yields `external_email`/`external_message` (the ceiling),
   an internal one yields `internal_email`/`internal_message`, and an
   unresolvable recipient is **fail-closed to external**. So no
   classifier-reachable path can wear the widened class to reach a real
   person.
4. **The class owns exactly one non-egress action type.** `draft_only`'s
   `action_types` list is exactly `[draft_only]`; `external_message` and
   `external_email` remain on `external_comms`. A CI arm pins this (§7).

Per-item Captain approval for external comms is a **non-grantable limit** —
it reaches real people outside the org — and no ruling in this amendment
touches it.

---

## 6 · Open item found while landing this — NOT closed here

While writing the mutation sensors for §7 I found a **pre-existing gap in the
validator**, present identically on master and unrelated to this ruling:

> `validate_matrix` checks that every `action_type` is mapped to exactly one
> risk class, but **not which class**. Relocating `external_email` from
> `external_comms` into any non-ceiling class validates clean. Because the
> gate's ceiling short-circuit is keyed on `risk_class in hard_ceiling`, such a
> matrix would send a real egress kind down the ordinary confidence path.
> `HARD_CEILING_TOUCHES` does not backstop this — per the design doc it guards
> **self-extension** (installing a capability), a different layer from action
> execution.

This amendment does not widen that gap: the mapping is unchanged, and a
ceiling kind landing on a non-ceiling class was already unsafe before. It does
raise the stakes marginally, since `draft_only` is now an act verdict rather
than mostly-propose. Closing it properly needs new executable lines in
`framework/authority/matrix.py` against the census budget already at its
ceiling (§3d.2), which is a threshold decision, not a mechanical fix — so it
is **recorded here and covered by a CI sensor** (`test_every_egress_action_type_sits_on_a_ceiling_row`)
rather than silently left or silently relaxed.

---

## 7 · CI proofs — landed in the SAME commit ("Docs Must Track the Code")

In `framework/authority/tests/test_matrix.py`:

- `TestDraftOnlyActThenTell` — the widening, in both tables. **Verified to
  FAIL against pre-change code** (`__pycache__` purged, master's YAML restored:
  3 arms red on `graduated: auto` / `propose_only` at the other four; green
  after). Includes `test_draft_only_row_mirrors_read_only_dispatch` (one rule
  for both act-and-tell classes), `test_earn_up_draft_only_still_proposes`
  (the narrowing that must NOT have moved), and
  `test_draft_only_needs_no_registered_inverse`.
- `TestDraftWideningDidNotMoveTheCeilings` — the walls, proven not assumed:
  every ceiling row `always_gated` in root; `external_comms` never acting in
  any posture; `no_ceiling_or_prod_auto()` still True; full six-member ceiling
  coverage; egress action types still on the ceiling row (non-vacuous — the
  egress set is asserted non-degenerate first); the live-classifier
  recipient-routing proof from §5.3; and **mutation sensors** that must RAISE —
  letting `external_comms` act (`auto` and `notify_after`), letting a sovereign
  ceiling act, and drifting the sovereign `draft_only` demote cell off the
  root's.

Updated pins (old values were the pre-ruling table, not weakened assertions):
`test_matrix.py::test_reversible_is_act_with_undo_trust_first`,
`test_matrix_postures.py::_EXPECTED_GUARDIAN` / `_EXPECTED_SOVEREIGN`, and the
`test_matrix_earnup.py` widening case for `draft_only` (root rose to rank 4, so
the case now uses `auto` at rank 5 to remain a genuine widening).

---

**One-revert rollback:** revert the single commit. It restores
`framework/policies/authority-matrix.yml` (`draft_only` back to
`auto`@graduated + `propose_only` at the other four, in both the root and
sovereign tables), and the comment-only edits in `framework/authority/matrix.py`,
`framework/authority/policy_engine.py` and `framework/frontdoor/action_undo.py`,
plus the CI arms and `docs/how-your-cabinet-is-governed.md`. No schema, no
lock-set and no interface changes to unwind — `cabinet/scripts/germline-lock.sh`
was never touched, so the germline path SET needs no restoration. If the
ceremony window has already run, the revert is itself Captain-windowed (a
germline edit both ways).

---

## 8 · The ceremony (what "apply draft act-then-tell" runs)

1. Re-verify lock state fresh — `cabinet/scripts/germline-lock.sh status` plus
   `ls -lO` on `framework/policies/` and the three locked modules —
   **immediately** before the window; boundary state changes across sessions.
2. `sudo bash cabinet/scripts/germline-lock.sh unlock`.
3. `git pull` / check out master so the locked tree carries the landed bytes.
   There is no hand-editing in this window: the content is already reviewed and
   merged, and the window exists only to re-materialise it.
4. Gate battery green: `python3.12 framework/authority/matrix.py` (floor
   validation + actor-id parity), `python3.12 -m pytest framework/authority -q`,
   and the golden evals.
5. **Same-day** `sudo bash cabinet/scripts/germline-lock.sh lock`, then
   `status` and `verify` in the same session.

The unlock is interactive `sudo` — a **named handback**, non-grantable, never
worked around. Until the window runs, master carries the ruling and the
deployment's locked tree carries the previous bytes; nothing depends on the
window having run.
