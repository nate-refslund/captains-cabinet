# Review — `fix/matrix-class-mapping-pin` cp1

**Branch:** `fix/matrix-class-mapping-pin` · **Base:** `856ef494` ·
**Date:** 2026-07-27 · **Model:** Opus 5 · **Verdict: PASS**

Closes a fail-open in the enforcer itself: `validate_matrix` pinned that every
`action_type` maps to exactly ONE `risk_class` but never to WHICH one, while
the gate's hard-ceiling short-circuit is `risk_class`-KEYED. The gap was
pre-existing on master, found in passing by another agent, and **verified here
by execution before anything was changed** — not by reading.

---

## 1. The hole, executed against pre-change master

`policy_engine._eval_authority_matrix` step 2 gates on
`risk_class in hard_ceiling`. So a ceiling kind is gated only for as long as it
maps to a ceiling class — and nothing checked that.

**Variant A — relocate the KIND.** Move `external_email` off the
`external_comms` row in a scratch copy of the loaded floor, then load it:

```
MUTANT: validate_matrix -> ACCEPTED (no exception)   <<< THE HOLE
MUTANT: external_email risk_class = reversible
MUTANT: is that class on the hard ceiling?  False

classify_action(mcp__brain__queue_draft) = external_email
gate[SHIPPED] -> 'GATED (hard ceiling: external_comms) — draft via queue_draft, never auto.'
gate[MUTANT ] -> "PROPOSE-ONLY (reversible, confidence=unmeasured; act_with_undo
                  verdict but no registered deterministic inverse for 'external_email')"
```

On `reversible` a second, unrelated backstop caught it (`_act_with_undo_gap` —
no registered inverse). That backstop does **not** exist on the `notify_after`
rows, so the same relocation onto an act-and-tell class allows outright:

```
relocate external_email -> draft_only          validate=ACCEPTED  gate=ALLOW (None)  <<< REAL SEND PROCEEDS
relocate external_email -> read_only_dispatch  validate=ACCEPTED  gate=ALLOW (None)  <<< REAL SEND PROCEEDS
relocate external_email -> internal_comms      validate=ACCEPTED  gate=PROPOSE-ONLY
```

**Variant B — relocate the CEILING (not in the original lead; found by
executing rather than reading).** Leave every `action_type` exactly where it
is; move which ROW NAME carries the ceiling — `hard_ceiling` +
`ceiling_frozenset_map` + all three verdict tables kept internally consistent,
so every pre-existing invariant (#1 ceiling coverage, #2 no-auto, #3
trust-inversion floor, #4 posture rules, #5 earn_up-narrows) still passes:

```
B-variant: ceiling row RENAMED off external_comms   ACCEPTED | gate=ALLOW (None)
```

Variant B is the more dangerous of the two: it never touches the risk_classes
mapping at all, so a reviewer diffing the mapping would see nothing.

**Blast radius:** all six ceiling classes were relocatable, not just comms —
`git_push_main`, `purchase`, `secret_write`, `mcp_post`, `oauth_grant` each
validated clean when moved onto `reversible`.

## 2. The fix

`matrix.py` invariant #6, `_validate_ceiling_class_mapping`, called from
`_validate_policy` after `_validate_hard_ceiling`. Two comparisons against
**ONE declared source**:

- `set(CEILING_CLASS_ACTION_TYPES) == hard_ceiling` → closes B.
- per class, `frozenset(risk_classes[C]["action_types"]) == declared` → closes A.

The declared source is `classifier.CEILING_CLASS_ACTION_TYPES`, whose *values*
are derived from the ceiling sets the classifier already owns
(`_EXTERNAL_COMMS`, `_SPEND`, `_SECRETS`, `_NETWORK_WRITE`,
`_CREDENTIALS_GRANT`) plus a new `_DEPLOY_PROD` split out of `_DEPLOY`
(`_DEPLOY` is now built *from* it, so `ACTION_TYPES` is unchanged — still 30,
matching the census's `central_action_types: 30 <= 30`).

**This removes a hand-maintained list rather than adding one.**
`deploy_classifier.py` previously re-declared the prod pair by hand; it now
imports `_DEPLOY_PROD as _PROD_ACTION_TYPES` (verified same object), so the
matrix can never be pinned against a stale copy. `_DEPLOY_PROD` is a
`frozenset`, preserving `_PROD_ACTION_TYPES`'s prior type exactly.

## 3. The arms fail against pre-change code

Required, and the only reason to believe the sensor. New tests copied verbatim
onto a pristine `856ef494` clone, `__pycache__` purged,
`PYTHONDONTWRITEBYTECODE=1`:

```
54 failed, 10 passed, 59 deselected      # pre-change
123 passed                               # post-change (whole file)
```

The 10 that pass pre-change are the degenerate arms (already fail-closed
before this change) and the shipped-floor positive pins — they exist to *hold*
a property that was already true, and are honestly reported as such. The 54
failures are `DID NOT RAISE` on the relocation mutants: variant A across
8 (ceiling row × kind) pairs × 6 destinations, variant B, the
`hard_ceiling`-membership arm, the standalone fail-closed arm, the
one-declared-source arm, and the end-to-end arm.

## 4. The degenerate ends — every one an arm

Asked before writing, and each is a test, not a claim. All four named ends
plus four more were probed against pre-change code first (**all were already
fail-closed**, so none of these is a new hole — they are pinned so a future
edit cannot open one) and re-probed after:

| degenerate end | behaviour |
|---|---|
| ceiling kind mapped to NO class | REJECTED — `action_types not mapped to any risk_class` |
| class that does not exist | REJECTED — `risk_classes must be exactly [...]` |
| ceiling class present but EMPTY (`[]`) | REJECTED — `must be a non-empty list` |
| whole mapping absent | REJECTED — `missing required field: risk_classes` |
| `risk_classes = {}` / `None` / `"nope"` / `[]` | REJECTED |
| ceiling row `action_types = None` / `{}` / a bare string | REJECTED |
| `hard_ceiling = []` | REJECTED — `must be a non-empty list` |
| **the DECLARED SOURCE emptied** | REJECTED — `the mapping pin would be vacuous` |

That last row is the one that matters most: the pin compares the YAML against
`CEILING_CLASS_ACTION_TYPES`, so an emptied source would make every arm above
assert nothing. The validator refuses an empty declared set, and
`test_the_declared_source_is_not_vacuous` pins the source's key set and
members independently.

## 5. The sensor is wired to the live control

`test_the_rejected_relocation_is_exactly_the_one_that_would_have_sent` drives
the real gate, not a shape: it asserts `classify_action` returns
`external_email` for an outside `queue_draft` recipient, that the shipped
policy GATES it, that the mutant's `risk_of` lands on a non-ceiling class,
that `_eval_authority_matrix` returns `None` (ALLOW) on the mutant — and only
then that `validate_matrix` refuses to load it. If the gate ever stopped
allowing the mutant, this arm fails rather than passing vacuously.

## 6. What I attacked in my own fix

- **Bypass by not validating.** Every production caller of `load_matrix`
  validates (`grep` for `validate=False` returns nothing outside the
  signature). `load_policies` quarantines a failed floor with
  `_validation_failed`, which the gate resolves to propose-only. So the new
  arm fails **closed**, not open.
- **Does the pin break a legitimate change?** Adding an egress kind now
  requires editing the classifier set *and* the YAML. That is the point, and
  the failure mode is a hard validation error → quarantine → propose-only.
- **`ceiling_frozenset_map` permutation** (e.g. `external_comms: production`).
  Still accepted — `_validate_ceiling_map` only pins the value SET. Judged
  out of scope and harmless *at this gate*: the ceiling short-circuit never
  consults that map, it reads `hard_ceiling`. Named here rather than silently
  left; see §7.
- **Mutating `CEILING_CLASS_ACTION_TYPES` at runtime.** Considered
  `MappingProxyType`; declined. The values are already frozensets, the binding
  itself could be reassigned regardless, and an attacker executing inside the
  process can monkeypatch the validator directly — it would buy no real
  property.

## 7. Residual, stated plainly

**The pin protects the matrix layer, not the classifier's routing.** If
`_classify_mcp` were changed so an outside-recipient `queue_draft` returned
`draft_only` instead of `external_email`, the matrix would never see an egress
kind and this invariant would never fire. That channel's sensor is the
pre-existing `test_a_comms_call_classifies_by_recipient_not_by_draft_framing`
plus `test_every_egress_action_type_sits_on_a_ceiling_row`, both of which
survive here (the latter's stale "KNOWN VALIDATOR GAP" comment is corrected in
the same commit). Not expanded into this change; recorded as the next hostile
pass on this surface.

## 8. Cost, paid not dodged

`framework_production_noncomment_lines` **+65** (68661 → 68726), measured on
`856ef494` *after* the captain-dates merge moved the baseline, via
`cognitive-architecture-census.py`. Paid as a `temporary_allowances` row
(`matrix-class-mapping-pin`) with the closed key set. Census re-runs PASS at
observed == max, preserving the zero-headroom law.

Docstrings are **counted, not reformatted into `#` comments** to duck the
counter; the one docstring was tightened on content, then the remainder paid.
No threshold was raised and no test was weakened, skipped or xfailed.

`cabinet/config/cognitive-architecture-contract.yml` is inside the phase-4
frozen-review digest scope (the only touched path that is), so the re-bind
ceremony rides the SAME commit — a MECHANICAL-DELTA re-bind, zero behaviour
bytes in scope.

## 9. Germline

`cabinet/scripts/germline-lock.sh` is **untouched**; the germline path SET is
byte-identical — 80 members, `sha256 673923d2754375fc586e20dc86bc393fa0f78180e7b9bf8032abb874ebbeda91`,
identical between `HEAD` and the working tree, with the extractor proven
non-vacuous (adding one path changes the hash). Only the CONTENT of three
already-locked files changed (`classifier.py`, `matrix.py`,
`deploy_classifier.py`) — landed-then-ceremonied; a later Captain unlock
re-materialises the landed bytes.

## 10. Verification

Full sweeps against a **re-measured** `856ef494` baseline (not a carried
known-red list):

| suite | baseline `856ef494` | branch |
|---|---|---|
| `framework/` | 1 failed, 6724 passed, 25 skipped | 1 failed, 6788 passed, 25 skipped |
| `cabinet/scripts/tests` (serial) | 4736 passed, 28 skipped | 4736 passed, 28 skipped |

The single `framework/` red is identical in both and pre-existing:
`test_retro_shim.py::TestRetroShim::test_reexports_constants`. The `+64` on the
branch is this change's new arms.

**A measurement error worth recording.** The first `cabinet/scripts/tests` pass
was run for both trees CONCURRENTLY and reported `6 failed` on each — with
*different* failure sets, all in `test_killswitch_*`. That was not a real red:
two sweeps in parallel contend over shared killswitch state. Re-run SERIALLY,
both trees are **0 failed**. Reported here rather than quietly dropped, because
a differing failure set across two runs of the same suite is the tell that the
measurement, not the code, was wrong.

Plus layer-separation (baseline 24 / allowlist 19 / current 43 / **new 0**),
`cog2-import-gate` OK, A13 parity (353 ids, `CG-35` appears exactly once),
`ledger-status-parity` GREEN (ids=353 md_rows=353 findings=0), census PASS at
observed == max.
