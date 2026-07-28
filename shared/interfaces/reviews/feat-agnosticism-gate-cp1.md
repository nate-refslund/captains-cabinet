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

---

# Checkpoint review — feat/agnosticism-gate cp2 (CI-driven fixes)

Reviewed-Scope-Digest: f35a7244e7b504a64440ab16ecaded4e882280913384a3e6cc1b206751a8e473

Two reds, both real, both found only because the artifact became TRACKED at commit
time — the working tree passed the same suite (class 2: working tree ≠ committed tree).

| Red | Cause | Fix |
|---|---|---|
| `clean-room-source`, `null-hatch` — three evidence shadow-law tests | their zero-consumer greps scan `git ls-files`, and the new debt ledger keys rows by the framework path that carries the literal, so it "references" `evidence_calibration` / `_detectors` / `_recompute` | one allowlist entry each, in the idiom those files already document for `architecture-baseline-sets.yml` ("a member-name row in a data file, never an import and never a consumer") |
| `cognitive-phase4` — census budget | `framework_production_noncomment_lines` 73055 > 73050: the charset seam is 5 non-comment lines larger than the whitelist it replaces | `maximum` raised 60164 → 60169, **visibly**, with the measurement — not a temporary allowance, because an allowance promises a deletion gate and this seam is permanent |

Zero new production modules, so `framework_production_modules` is untouched. Census
now PASS with every other budget still at zero headroom.

---

# Checkpoint review — feat/agnosticism-gate cp3 (layer-separation red)

Reviewed-Scope-Digest: c855190b061aa5f271e63ae874ab4e598c8ee5667d6fa5ff193517b150c0b54e

`check-layer-separation.sh` flagged `framework/tests/test_no_launcher_hardcode.py`
with `FRAMEWORK_PATH_INSTANCE` — its per-deployment-layer grep has no `tests/`
exclusion, and the seed walk named that layer twice (a skip-set member and a
fixture path).

The fix is not an allowlist entry: the seed walk is now an **include list of this
repository's own layers** (`_SEED_ROOTS`) rather than an exclude list of layers to
dodge. Strictly better on three counts — the per-deployment and preset layers are
absent by construction rather than by name, an omitted root can only shrink the
vocabulary (fails toward green, never toward a false red), and it no longer
depends on enumerating everything a stranger's tree might contain. The fixture now
uses a directory that is simply not a root, **with a control arm** proving the same
file under a root does seed, so the negative cannot pass by the walk being broken.

Measured after the change: vocabulary 47 labels (unchanged), 318 debt keys
(unchanged), layer-sep `new=0`, 42 tests green.
