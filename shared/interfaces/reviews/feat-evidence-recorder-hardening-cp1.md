# FW-019 checkpoint review — Evidence Recorder hardening (cp1)

**Branch:** `feat/evidence-recorder-hardening` (off `2f0253b7`)
**Batch:** the fixes for the 27-finding deep review of PR #140 Evidence
Recorder v1 (`designs/PR140-EVIDENCE-RECORDER-REVIEW-2026-07-15.md`,
orchestrator commit `e5ec86e`).
**Diff:** 15 files, +2110 / −150 (over the 300-line FW-019 threshold → this
artifact).
**Reviewer:** integration+verify engineer (Fable 5), landing pre-authored,
pre-critiqued group patches. Findings were verified in the source review;
this checkpoint verifies the FIXES land intact, add teeth, and pass the fast
deterministic gate battery without regression.

## Purpose that ranks the fixes

The Evidence Recorder exists to LOG A FULL ONBOARDING — every event across the
onboarding surfaces — so the Captain can later audit the logs and judge/repair
onboarding. Faithful, COMPLETE, TRUSTWORTHY recording is the point. So every
fix in this batch was chosen to keep the event RECORDED (scrub / normalize /
re-mint and continue) over dropping or refusing it, while never letting a real
action go unrecorded or a false event be recorded. The redaction fixes keep
secrets out of the reviewable export WITHOUT losing the event itself.

## The 7 groups → findings fixed → teeth

### 1. `hook.patch` — officer hook boundary (P0×3 + P1)
Fixes the three P0 same-UID bypasses in the hook PR #140 adds, plus the
interpreter-import evasion.
- **#1** (`pre-tool-use.sh:1198`) §5a raw-read boundary did no path
  normalization — `instance/config/../evidence/v1/.signing-key` dodged the
  literal `instance/evidence/` substring and the OS resolved `..` to the HMAC
  signing key. Fix: `normpath`+`realpath` on the native Read/Grep/Glob/Edit/
  Write arm and per-token `normpath`+`realpath` on the Bash arm; fail-closed
  sentinel on empty `python3` output.
- **#2** (`:1307`) `rm -rf instance/x/../evidence/v1` (and bare-parent `rm -rf
  instance/evidence`, and `mv` of the store) wiped the append-only store past
  §5a's `..` gap and §5b's trailing-slash-only `GERM_PATH_RE`. Fix: the
  normpath fold restores the substring match; independent target-anchored
  `rm|rmdir|unlink|shred|mv` arm blocks a destructive verb against the store.
  `GERM_PATH_RE` left untouched (its lockstep meta-test pins it).
- **#3** (`:1212`) the evidence-read AND observe-only doorways allowed via a
  line-oriented `grep -qE '^…$'` — a two-line command whose first line was the
  legit doorway smuggled the second line (`\ncat …/.signing-key`). Fix: reject
  any multi-line command BEFORE the doorway shape check, both doorways.
- **#4-hook-half** interpreter import evasion (`from framework import
  evidence`): fail-closed structural screen — an interpreter token
  (python/ipython/pypy) that names `framework` AND
  `evidence|onboarding|journey` is refused; a plain `grep evidence framework/…`
  source read stays allowed.
- **Teeth:** new `cabinet/tests/hook-regression/evidence-pathnorm.sh` (23
  probes) wired into `run-hook-regression.sh`. Every BLOCK probe ALLOWS on
  pre-fix `2f0253b7` and BLOCKS with the fix; every ALLOW probe (legit
  doorways, ordinary source reads, sibling `instance/evidence-notes.md`) stays
  exit 0. Self-contained symlink + python3-unavailable fixtures isolate the
  realpath and destructive-verb arms. **Result: 23/23 PASS.**

### 2. `redaction.patch` — secret/PII coverage without losing the event (P1×2 + P2×2)
- **#7** DB connection-URL creds (`scheme://user:pw@host`, incl. empty-user
  `redis://:pw@host`) now redacted; host stays reviewable.
- **#8** bot-token-in-URL (`…/bot<id>:<secret>`) now caught via a digit
  negative-lookbehind instead of `\b`.
- **#16** email PII + `chat_id`-shaped keys + underscore-joined keyword secrets
  (`aws_secret_access_key=…`) redacted; bare numeric counters
  (`total_bytes`) deliberately kept auditable.
- **#17** every `SECRET_VALUE_RES` shape now has an end-to-end tooth; a
  structural test fails if a pattern is added without a shape.
- **#12-redaction-half** lone UTF-16 surrogate is SCRUBBED to U+FFFD (identity
  on valid strings) so the event still records instead of crashing canonical
  JSON — a denial of evidence. Secret patterns re-run after path substitution
  and after truncation so a cut can neither manufacture nor uncover a shape.
  Keyword tail is a bounded possessive to kill a ReDoS that would stall
  recording.
- **Teeth:** new `framework/evidence/tests/test_redaction.py` (end-to-end:
  secret never reaches store / projection / export, event stays recorded and
  `verify_trial ok`).

### 3. `recorder.patch` — store robustness / availability (P1×2 + P2×3)
- **#6-recorder-half** reader frames rows on `"\n"` only (was
  `str.splitlines`, which split on U+2028/29/NEL inside a payload the
  byte-oriented verifier called healthy → bricked reads). Malformed row now a
  typed `EvidenceError('ledger_invalid')`.
- **#12-recorder-half** unserializable canonical payload → typed
  `payload_unserializable`, never a bare crash.
- **#13** construction-time `recover_pending()` heals a crash between ledger
  and anchor write on plain restart (was a permanent false-tamper verdict).
- **#14** trial mutex moved OUTSIDE the trial dir (`root/locks/<id>.lock`) so a
  purge/append race can't resurrect a ghost dir that fails verify forever;
  ghost dirs swept on construction.
- **#5** `enforce_retention(exclude=…)` protects a live-referenced trial from
  an age purge that would wedge the onboarding plane.
- **Teeth:** additions to `test_recorder.py` (no-fabrication in-flight,
  restart heal, purge/append race, retention exclude, canonical stability,
  unicode line-separator agreement).

### 4. `verifier.patch` — verifier soundness (P1 + P2 + P3s)
- **#9** non-dict `anchor.json` now FAILS CLOSED (`anchor_missing_or_unreadable`)
  instead of silently disabling anti-truncation — the one clean, complete
  one-liner, done first.
- **#18** negative-control tooth: a planted secret RE-SIGNED with the store key
  passes hash/sig/anchor and is caught ONLY by the secret-shape scan.
- **#24/#25** signed monotonic anti-rollback watermark sidecar
  (`.verify-watermarks.json`, HMAC over hashed-trial-id → {sequence,
  event_hash}); rollback / divergent-history / resurrected-purged-trial /
  removed-without-receipt all fail closed; a present-but-invalid sidecar is
  tamper evidence, never self-healed.
- **#6-verifier-half** verifier frames rows on `b"\n"` only (was
  `bytes.splitlines`, which split on `\r`).
- **Teeth:** new `test_verifier.py` (adversarial: attacks the on-disk files
  with and without the key; positive control proves clean stores keep
  verifying and recording).

### 5. `journey.patch` — onboarding fidelity / deletability (P1 + P3s)
- **#5/#10/#15** the live trial can be re-minted under the state lock when
  retention/CLI tombstones it (genesis event links the tombstone hash) so
  `act()`/`observe()` keep recording instead of wedging; `recover_interrupted`
  only synthesizes interrupted/recovered when a real `pending.json` was found
  (no fabricated events on a live trace).
- **#26** a broken/tombstoned evidence plane never blocks a typed purge —
  deletion proceeds, the failure is recorded in the purge receipt, the pending
  marker survives for a later Captain force-purge (source-derived onboarding
  data stays deletable — a real GDPR hole otherwise).
- **#27** one request-id anchor shared with the evidence plane; ids overwrite
  (never `setdefault`) so a malformed caller id can't fork the two planes.
- **#12-journey-half** lone surrogates scrubbed at the request boundary;
  unencodable source path is a clean typed refusal (still recorded), never a
  raw `UnicodeEncodeError`.
- **Teeth:** additions to `test_journey.py` (re-mint on both act/observe,
  corrupt-ledger purge, id-fork refusal, surrogate scrub).

### 6. `cli-policy.patch` — Captain-capability gate + fail-closed policy (P1 + P3×2)
- **#4** mutating CLI commands (`control` changes, `purge`, `retain`,
  `export`) now require a Captain capability token derived from the store's
  private signing key (`HMAC(signing-key,
  "cabinet.evidence-captain-capability/v1")`), presented via
  `--captain-token-file` / `$CABINET_CAPTAIN_TOKEN_FILE`, minted by the new
  `grant-token` command (O_NOFOLLOW fd, regular-file, `mode & 0o077 == 0`,
  ≤4096B, ASCII, `hmac.compare_digest` on bytes). A bare `actor="captain"`
  string no longer authorizes. Read-only (`verify`, `project`, `control`
  no-change) need no token. The same-UID residual is documented honestly (full
  closure = separate-UID deployment).
- **#22** never replays a lapsed `diagnostic_until` into `configure()` (an
  unrelated retention change was being refused).
- **#23** `RepairRequest` danger dimensions default `True` (fail-closed): an
  unstated danger fact gates to the Captain instead of auto-repair.
- **Teeth:** new `test_cli_policy.py` (capability required/accepted/forged/
  foreign/lax/symlink/non-ASCII refusals; lapsed vs live diagnostic window;
  danger-default matrix).

### 7. `dashboard.patch` — server-side onboarding seam (P2 + P3s)
- **#11** the evidence route now requires a declared bounded `Content-Length`
  BEFORE buffering (missing/NaN/negative/oversize → 413), re-checks real bytes
  after — closes the unbounded-body buffering the sibling route was already
  hardened against.
- **#20** the post-purge evidence-suppression grammar is now DERIVED from the
  real intent regex, so every form that actually purges suppresses the
  post-purge observation, and non-purge traffic keeps recording delivery
  evidence.
- **#21** `journey-card.test.ts` gains render + driven behavioral tests (typed
  purge gate stays disabled until exactly `PURGE`; feedback claimed only after
  the endpoint confirms) — the UI gate is convenience only; the server-side
  refusal is the boundary.

## Fast deterministic gate battery (all run on this branch @ working tree)

| Gate | Command | Result |
|------|---------|--------|
| Framework pytest | `python3.12 -m pytest framework/evidence framework/onboarding framework/policies framework/authority -q` | **1045 passed, 6 skipped, 1 pre-existing baseline failure** (`test_stale_open_need_expires_on_read` — wall-clock-relative rot in `framework/authority`, UNTOUCHED by this batch; fails identically on `2f0253b7`) |
| Hook regression | `bash cabinet/scripts/run-hook-regression.sh` | **No regression from this batch.** New `evidence-pathnorm.sh` 23/23 PASS. The suite's other harness failures are pre-existing on `2f0253b7` (the harnesses target the Ubuntu officer container; on a macOS host without the redis kill-switch stub the fail-closed kill switch trips — proven: with the stub on PATH every probe passes). |
| Layer separation | `bash cabinet/scripts/check-layer-separation.sh` | **PASS** — `new=0 fixed=0`, no new framework→instance coupling |
| Golden evals (FW-025) | `bash cabinet/scripts/run-golden-evals.sh` | **26/26 ALL PASSED.** (A single EVAL-018 flake on the first run — FW-034 `perl -ne` write-target, unrelated to evidence — was a transient redis kill-switch blip; direct probe = exit 0 on both trees, exact negative loop ×3 = 0 false-blocks, clean re-run = 26/26. EVAL-007, which parses every exit-2 path this batch ADDED to `pre-tool-use.sh`, PASSES.) |
| null-hatch smoke | `bash cabinet/scripts/null-hatch.sh` | see push-time run note |
| TypeScript | `cabinet/dashboard` `tsc --noEmit` | not run locally — dashboard has no `node_modules` on this host; CI runs the heavy dashboard vitest/build/tsc after push (per landing protocol) |

## Landing note (germline)
Nearly every fixed file is `schg`-locked germline in the live tree
(`pre-tool-use.sh`, `framework/evidence/*`, `framework/onboarding/journey.py`,
`cabinet/dashboard/src/app/api/onboarding`, the event schema). This branch is
pushed for CI; live application on the armed Mac is via a Captain sudo unlock
ceremony — see `docs/proposals/germline-amendment-evidence-recorder-hardening-2026-07-15.md`
and ledger row `CG-EVIDENCE-HARDENING`.
