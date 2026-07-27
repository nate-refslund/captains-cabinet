# Review checkpoint 1 — `fix/propose-means-propose`

**Change:** the authority gate's `propose_only` and `always_gated` verdicts were
OPERATIONALLY IDENTICAL (`main()` exits 2 on any non-None result). They are now
distinguished by a structured field, a propose verdict files a deduped need, and
the split is counted by the dry-run instrument.

**Scope:** 915 changed lines across 7 files. Germline modules
(`policy_engine.py`, `needs.py`) are landed-then-ceremonied: built in a clone,
landed to master like any change, germline SET untouched.

---

## What was verified, with the command that produced it

| gate | result |
|---|---|
| `framework` sweep (serial) | **1 failed, 6982 passed, 25 skipped** — the single red is `test_retro_shim.py::test_reexports_constants`, **confirmed pre-existing on clean master** (stash → run → 1 failed → unstash) |
| `cabinet/scripts/tests` | 4835 passed, 28 skipped (after the census allowance was corrected to +151) |
| `cabinet/scripts/lib/tests` | 469 passed |
| census | PASS, `framework_production_noncomment_lines: 69466 <= 69466` — zero headroom preserved |
| `test_cognitive_architecture_census.py` | 79 passed |
| golden evals + guardian parity | 46 passed |
| `check-layer-separation.sh` | OK — baseline=24 allowlist=19 new=0 |
| `cog2-import-gate.py` | OK — shadow boundary intact |
| `ledger-status-parity.sh` (A13) | GREEN, ids=353 md_rows=353 findings=0 |
| germline SET hash | FILES=73 DIRS=7 SKIP=4, sha256 `4d1cde9de935c762…` **identical to HEAD** (extractor asserts >3 members per array, so it cannot pass vacuously) |
| blast-radius re-measurement | 80,307 records, exact round-trip; live DB md5 `3ad9664c…` unchanged before/after |

## The six hard-ceiling arms — the reason this change is safe

One arm per class, each asserting the block, the EXACT guardian byte string,
`kind == GATE`, and that no `capability` need was filed. Plus an end-to-end arm
per class asserting the subprocess still exits 2.

**All six FAIL against pre-change code** (`.kind` does not exist on a plain
`str`). Verified both directions with `__pycache__` purged: **26 passed after,
18 failed before.** The 8 that pass in both directions are deliberate
regression guards (ceilings exit 2, propose still withholds, guardian bytes
unchanged) — they exist to prove nothing already-correct broke.

**Independent cross-check from the corpus:** the `gate` count is 11,570 =
6,507 `deploy_prod` + 4,471 `secrets` + 364 `network_write` + 219 `spend` + 6
`credentials_grant` + 3 `external_comms` — **exactly the six ceilings and
nothing else**, over 80,307 real recorded calls. No ceiling leaked into a
softer kind.

## No widening — stated as the property, not the intent

Exit codes are unchanged and every guardian message is byte-identical. A
propose verdict still withholds the step. The propose set is dominated by
`unclassified`, which both arms of the direction gate proved is
byte-indistinguishable from `bash send-to-group.sh` (a Telegram POST), `gh api
-X POST …/comments`, and `python3 -c "…smtplib…"`. Letting a propose verdict
execute would ship exactly the widening the gate refused.

`permissionDecision: "ask"` was considered and REJECTED: its meaning depends on
the session's permission mode, and officers run with permissions bypassed, so
`ask` could resolve to auto-allow — a fail-open on the enforcer itself.

## Two defects found in my own work, both by a check rather than by reading

1. **A sensor that lied.** The first measurement reported `legacy_typed: 52659`
   — every record without a kind — while printing a clean, plausible 75.66%.
   Cause: `_first_block` returned `name, str(result)`, and that `str()`
   flattened the subclass, so the split was UNMEASURED. Fixed, plus a
   sensor-on-the-sensor: if `authority_matrix` is in the candidate set and
   produced blocks, it is impossible for none to carry a kind — the instrument
   now exits 3 rather than reporting a plausible number.

2. **Two switches one word apart.** `needs_enabled()` was first given an
   `instance/config/authority-enforcing` FILE disjunct, on the reasonable
   grounds that `pre-tool-use.sh` honours it. That file is a DIFFERENT switch,
   already true since the Captain's 2026-07-03 "flip it", and its own scope
   line reads *"typed STATELESS policy set enforcing"* — a set that EXCLUDES
   `authority_matrix`. Because every deployment carries the file, the seam
   turned on everywhere and the guardian world stopped being bit-identical. Six
   digest/gate parity tests went red and caught it. Now `CABINET_AUTHORITY_ENFORCING=1`
   only, with a test asserting the FILE does **not** wire the seam.

## Measured, not assumed

`file_need` costs **~102ms flat** — profiled to `_emit` → `evidence_mirror` →
`recorder.append` → `verify_trial` (54k `contains_secret_shape` calls per
filing), NOT the ledger read. This gate runs on every tool call and a live flip
withholds ~41k steps, so unconditional filing would have been a ~100ms hot-path
regression plus an unbounded ledger. A stat-based marker holds the hot path to
one `os.stat`; true per-call counts already live in the shadow record.

## Known gaps, carried forward rather than hidden

- **A filed need is visible but not answerable.** `binder_wire.py:720
  _needs_wired()` reads `CABINET_NEEDS_WIRED` and nothing else, unlike
  `attention_drain.py:411` which delegates to `needs.needs_enabled()`. So the
  Captain's `grant NEED-x` / `deny` / `later` reply verbs stay dark. Left alone
  deliberately — `cabinet/services.yml` marks that plane dark by design and
  arming a live authority-reply surface is not this unit's call.
- **The flip is still not possible.** 52,659 calls still do not execute. The
  residual is 54.06% `unclassified`, which is a classifier problem. This change
  establishes that only **16.62%** of what the fleet runs is a genuine ceiling —
  the number a per-invocation sub-decider has to get down to.

---

# Checkpoint 2 — adversarial review round

A fresh-context adversarial reviewer attacked the change on six axes. Its two
headline results, then every finding and what was done.

## Axis 2 — widening: CLEAN, independently proved

- **Static:** AST-enumerated every `return` in `_eval_authority_matrix` on both
  trees. 15 returns before, 15 after; **5 `return None` before, 5 after**, at
  identical control-flow positions. No allow site added, removed or re-guarded.
- **Dynamic:** **166,656 differential cases** (8 policy variants × 4 postures ×
  7 cell states × 4 officers × ~174 tool/input pairs including junk types)
  through both trees: `ALLOW pre=20008 post=20008` · **newly allowed = 0** ·
  newly blocked = 0 · verdict-string differing cases = 0 · message-text
  differing cases = 0.
- **Coverage-proved:** a `sys.settrace` run hit all 5 allow-return lines in
  both trees with 0 differences.

## Axis 1 — hard ceilings: clean under the shipped floor

Could not make any of the six classes allow or report `.kind != "gate"` across
guardian / sovereign / earn_up / bogus posture, the quarantine stub,
`classify_action` returning `None`/`""`/`42`/list/dict/`object()`, and a forced
`auto` rung-lift at `graduated`. All 6 × 8 scenarios: `allow=False,
kind='gate', filed=[]`.

## Findings and dispositions

| # | sev | finding | disposition |
|---|---|---|---|
| 1 | MED | a floor whose `hard_ceiling` is missing/empty/mistyped sent ceilings to the step-6 collapse, where they were labelled PROPOSE **and filed "grant autonomous external_message for this lane"** onto the Captain's deny surface | **FIXED** — the gate now fail-closes on the CANONICAL set (`classifier.CEILING_CLASS_ACTION_TYPES`), not the floor's own list. Deliberately narrow: an empty `hard_ceiling` stays legal for a matrix declaring no ceiling classes (a posture fixture relies on it); only a canonical ceiling class ABSENT from the list is corrupt. New arm covers `{}`, `[]`, a str, a dict, and a well-formed list that omits the class |
| 2 | HIGH | same shape **plus** a hand-edited `verdicts.external_comms: auto` allows | **FIXED by #1** — pre-existing, needs an unlock window to reach; the canonical-set guard closes it at the gate |
| 5 | LOW | `copy`/`deepcopy`/`pickle` raised `TypeError` where a plain `str` round-tripped | **FIXED** — `__getnewargs__`, with an arm |
| 6 | LOW | the kind sensor caught only a TOTAL coercion; a partial one passed | **FIXED** — now asserts `legacy_typed == 0` |
| 11 | MED | `CABINET_ROOT` unset silently disabled the rate limit — measured **45.65 ms/call vs 3.87** | **FIXED** — falls back to the needs kernel's own root resolver |
| 12 | MED | a future-dated marker satisfied `delta < window` forever, permanently muting a need while the step kept being refused | **FIXED** — `abs()`, with an arm that back-dates a marker to 2027 |
| 13 | LOW | an undo-plane outage filed under the capability wording and deduped onto a genuine below-bar refusal | **FIXED** — `_propose(why=…)`; the undo gap files its own reason naming it an undo-plane defect |
| 14 | MED | **three deliberately wrong implementations passed the whole 1199-test suite**: a constant marker path, an unclassified branch that files nothing, and an infinite refile window | **FIXED** — three arms added. Verified as real sensors: each mutant now fails, control green |
| 3, 4, 9, 10 | — | `__slots__` legal on a str subclass; `decision_kind` never raises; `need_id` cannot traverse (42 hostile inputs, all `NEED-[0-9a-f]{8}`); a filing failure never changes a verdict | NON-ISSUE, confirmed |

### Mutation check — the new arms are sensors, not decoration

| mutant | result |
|---|---|
| constant marker path | **1 failed** |
| unclassified files nothing | **2 failed** |
| `_PROPOSE_REFILE_SECONDS = 10**12` | **1 failed** |
| `hard_ceiling` guard removed | **1 failed** |
| control (unmutated) | 33 passed |

## Carried forward, NOT fixed here — named so they are not lost

- **#7 (MED) — the shadow twin still collapses the buckets.**
  `cabinet/scripts/policy-shadow.py:509 authority_decision()` re-implements the
  gate instead of calling `_eval_authority_matrix`, and its `verdict` field is
  what the shadow record stores. It reports `propose_only` for BOTH the 37,624
  unclassified calls and the quarantine, so anyone reading the recorded field
  as "the propose bucket" gets the exact misattribution this change fixes on
  the other half of the plane. **My measurement is unaffected — the dry run
  recomputes through the real gate rather than reading that field.** Fixing it
  properly means removing a duplicate implementation of the verdict logic,
  which is larger than this unit.
- **#8 (MED) — `authority-matrix-dryrun.py` has no test and is in no CI step.**
  The `by_kind` counter, the `nargs="*"` fix, the `_id_only` guard and the
  FATAL sensor are unpinned by CI. Worth a fixture-corpus test.
- The `_id_only` guard stub crashed the measurement once when `_file_propose_need`
  gained a `why=` parameter. Now `*args/**kwargs`: a stub that pins a shadowed
  function's signature converts any later parameter into a hard failure.

## Re-verification after the fixes

framework **6989 passed** (1 pre-existing red) · `cabinet/scripts/tests` 4874
passed · census PASS `69509 <= 69509` zero headroom · layer-sep OK · import
gate OK · A13 GREEN 353/353 · germline SET identical · RES-007 cite re-pointed
`:454 → :466` (the register predicts this at every re-bind) · **blast radius
re-measured identical: 52,659 = 75.66%, split 16.62 / 4.98 / 54.06**.
