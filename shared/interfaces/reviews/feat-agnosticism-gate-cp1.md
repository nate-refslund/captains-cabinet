# Checkpoint review — feat/agnosticism-gate cp1

Reviewed-Scope-Digest: bae89a09ab1c015ee139a06e44e644622ce65e1943d4b63f6aecea71256e7ae8

Scope: the specifics ratchet (Arm 2 of `framework/tests/test_no_launcher_hardcode.py`)
plus its debt baseline, and two removals — the Danish-keyboard charset whitelist and
the launcher product name in `framework/`.

## What was checked, and against what

| Claim | How it was verified | Result |
|---|---|---|
| Arm 2 fails on a new specific | planted `framework/attention/_probe_plant.py` with a vendor URL + three vendor names, ran the CLI and pytest | RED (4 findings, 1 test failed); GREEN again on removal |
| Arm 2 does not fire on ordinary work | replayed 177 non-merge commits touching `framework/` from git objects, computing `findings(commit) ⊄ findings(parent)` with the parent's own derived vocabulary | 33 fire (18.6%), **0** on a non-vendor |
| The vocabulary is derived, not listed | `derive_vendor_vocabulary` self-joins the tree's own URL hosts; `test_the_live_vocabulary_is_derived_and_non_empty` asserts ≥10 labels so an empty seed can never read as green | 47 labels |
| The baseline cannot become a vendor registry | `test_baseline_is_a_debt_ledger_not_a_vendor_registry` requires every line to end in an opaque digest | enforced |
| The charset removal is non-vacuous | ran the NEW `framework/acting/tests/test_voice_charset.py` fixtures against the PRE-change implementation (stashed tree, `__pycache__` purged) | 12/12 script arms RED before, 11/11 tests green after |
| Behaviour preserved where it belongs | `instance/flavor-a` keeps the Danish set via the new parameterised seam | 99 tests green (flavor-a + binder_wire) |
| No test weakened, skipped or xfailed | full `framework/tests` + the two touched authority/cost suites | 1185 passed / 1 skipped (pre-existing), 405 passed |
| Germline SET untouched | `git diff --stat origin/master -- cabinet/scripts/germline-lock.sh` empty; path-line extractor over the lock script found 77 path lines and intersected them with the changed set | set unchanged |

## Risks accepted

1. **`framework/authority/policy_engine.py` is a germline-locked path.** The change is
   one comment (`polads-ceo` → `<lane>-ceo`). Landed-then-ceremonied: it needs one
   Captain unlock/relock to re-materialize the landed bytes on the live machine. The
   germline SET is byte-identical.
2. **18.6% of framework-touching commits would have gone red.** Every one names a real
   third party newly entering `framework/` — that number IS the finding (the framework
   was acquiring a new named third party in roughly one commit in five). The remedy is
   one command plus a visible cap bump, and it is spelled out in the failure message.
3. **Four word-collision exclusions** (`make`, `linear`, `acme`, `evil`) are the only
   hand-maintained element. Each carries its measurement, each is still enforced by
   `EXTERNAL_HOST`, and the set is capped shrink-only.
4. **What the gate cannot see** is documented in the module, not implied by green:
   closed enums, capability names, currency units, cadence thresholds, vendors with no
   URL anywhere, and vendors laundered through namespace position.
