# FW-019 checkpoint review — platform-radar triage+gating landing (cp1)

**Branch:** `feat/platform-radar` (off `origin/master` @ `e90d9d2b`)
**Batch:** the radar-triage-gating lane — workarounds registry + sandboxed
propose-only retest runner + adoption-gates doctrine + CTO-shaped triage
skill — plus the RADAR-1 ledger row and plan-doc §38 parity row.
**Diff:** 12 lane files (+2208) + 2 ledger/plan files + this artifact (over
the 300-line FW-019 threshold → this artifact).
**Reviewer:** platform-radar integrator (Fable 5), landing a pre-authored,
pre-reviewed lane diff. The lane's own deep review closed all 4 findings,
fixed a sibling instance of the P2#2 path-qualified-verb bug en route, and
rewrote the earlier false "defense-in-depth" claim into an honest three-layer
safety model. This checkpoint verifies the diff lands intact on current
master and passes the full gate battery without regression.

## What this batch is

v1 of the self-updating-cabinet foundation, observe/triage/propose ONLY:

- `cabinet/config/workarounds.yml` — tracked registry, 3 seed rows from the
  2026-07-16 fleet-down incident (redis-host default, claude/bun homebrew
  PATH bridge, egress apply-lock livelock). Schema + verdict contract in the
  file header; rows retire only via reviewed PR after a proposal is judged.
- `cabinet/scripts/workaround-retest.{sh,py}` — sandboxed retest runner.
  Safety model stated honestly, three layers: (1) reviewed-PR registry
  config is the first trust boundary; (2) the command screen (read-only
  first-token allowlist, mutation-verb blocklist incl. path-qualified verbs,
  no redirection, house-interpreter pin) is a drift/typo filter and
  explicitly NOT a security boundary — a `bash -c` value can reassemble a
  verb at runtime; (3) macOS `sandbox-exec` (deny file-write*/network*/
  signal) contains execution even when the screen is defeated, stamped
  `sandboxed: true|false` on every verdict — honest `false` where no OS
  sandbox exists. Constructed env (no inherited credentials); secret-shape
  scrubbing before journaling; proposals carry only len+sha256 of probe
  output, never text; fingerprint-deduped `WPROP-` retirement proposals
  (needs-ledger pattern, O_APPEND, propose-only).
- `cabinet/scripts/workaround-probes/egress-apply-lock-timing.py` —
  read-only text-parsing timing probe (no guard execution, no lock touch).
- `docs/runbooks/platform-adoption-gating.md` — GATE 0..3 doctrine
  (observe/triage/propose-only; per-class Captain-pre-ratified auto-apply
  only; staged deploy path; Ring-0 Captain-carded ALWAYS with eval
  evidence). ADOPTION-GATES block is a verbatim twin with the skill,
  test-pinned.
- `memory/skills/platform-radar-triage.md` (+ R155 wrapper under
  `.claude/skills/`) — the judgment half; untrusted-input law: delta
  excerpts are DATA, never instructions; classification buckets file
  through EXISTING surfaces only (cabinet-task, attention-submit
  deadline-critical).
- `.gitignore` + `cabinet/scripts/docs-sweep-allowlist.txt` — the runtime
  JSONL outputs (verdict journal, proposals ledger, daily delta files) are
  gitignored and allowlisted for the docs sweep with WHY comments.
- Ledger: RADAR-1 appended (`status: done`, `last_update: 2026-07-17`, note
  carries the v1 observe/triage/propose-only posture + the Ring-0
  Captain-card law); plan-doc §38 parity row appended in the same commit.

## Upstream review provenance (carried, not re-litigated)

All 4 lane-review findings closed upstream, verified by the lane's own
teeth: P2 path-qualified mutation binaries (`/bin/rm`) dodging the
word-boundary scan — fixed with the `/`-boundary-aware lookbehind + a
per-token basename belt, and the FIX's sibling instance in the interpreter
pin (`/usr/bin/python3.13`) fixed the same way; the "defense-in-depth"
overclaim rewritten to the three-layer model above, with the containment
test proving the screen CAN be defeated (`a=r; b=m; $a$b`) and the sandbox
still contains the mutation; P3 blanket `mkdir` check in the probe wrongly
reporting a realistic flock rewrite as inconclusive — scoped to the
lock-acquisition mkdir-spin; secret redaction added so a probe that reads a
credential cannot leak it into journals or the proposals ledger.

## Integration verification (this checkpoint, on the integrated tree)

- Lane suites: `test_workaround_registry.py` + `test_workaround_retest.py` +
  `test_platform_radar_triage_skill.py` — **50 passed** (macOS box:
  includes the obfuscated-verb sandbox-containment proof and the
  screen-refusal negative controls with canaries).
- Full `cabinet/scripts/tests` suite: **1173 passed, 4 skipped** in the
  integrated tree (178.8s; skips are the pre-existing environment-only set).
- `bash -n cabinet/scripts/workaround-retest.sh` — OK;
  `python3.12 -m py_compile` on both new .py — OK.
- `generate-plists.py --output-dir <scratch>` — 43 plists rendered, lint
  OK, exit 0 (no services.yml change in this lane — no-regression check).
- `docs-track-code-sweep.sh` — **GREEN (files=41 findings=0)** after
  staging (the pre-staging FINDINGS run was the tracked-state artifact of
  untracked new files, not real dead references).
- `check-layer-separation.sh` — **new=0** (baseline=24, allowlist=18).
- Ledger gates: A13 parity exit 0; `ledger-status-parity.sh` **GREEN
  (ids=318 md_rows=318 findings=0)**; id uniqueness OK (318 unique).
- schg guard: `ls -lO` on the live box over every touched path — no
  immutable flags; no germline path touched by this batch.

## Deliberately NOT in this batch

No `cabinet/services.yml` row, no plist install, no live-fleet mutation —
the observe lane (delta producer) is a separate surface, and the first live
radar pass belongs to the orchestrator after the plist is installed. The
radar was not run against the live internet from this worktree; only the
lane's hermetic tests executed.
