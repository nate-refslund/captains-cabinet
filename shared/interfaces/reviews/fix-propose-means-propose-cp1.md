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
