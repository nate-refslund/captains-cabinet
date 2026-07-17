# Checkpoint review — feat-killswitch-card cp1 (2026-07-17)

Lane checkpoint (FW-019) for the /killswitch Telegram control card —
captain-controls plan (`docs/plans/captain-controls-no-terminal-2026-07-17.md`,
ratified 2026-07-17) Phase 1, built on a clean worktree off origin/master
@a51f98f3. Staged churn 1,150 insertions / 8 deletions across 8 files.

## What landed

1. **Verb mint** — `decision_card.CB_VERBS` gains `ksh` (Halt) / `ksr`
   (Resume), payload-less by design; `cb()` stays the single mint and the
   enum stays a strict allowlist (out-of-enum verbs still raise; pinned).
2. **Pure card face** — new `framework/comms/surface/killswitch_card.py`:
   status classification is fail-closed (rc≠0 / garbled ⇒ UNKNOWN, worded
   "treat it as ARMED"), the flip block quotes `kill-switch.sh`'s OWN output
   verbatim (·-scrubbed, clipped, <4096), failure faces are LOUD (🚨 + the
   script's stderr), both buttons render on every face (the card stays the
   standing control). No redis, no subprocess — stdlib + the mint only.
3. **tap_wire poller-only door** — `_apply_killswitch`: verb already
   allowlist-parsed, then the payload is re-validated EMPTY before anything
   runs (hostile/spliced args refused pre-executor, pinned incl. `$()`/
   backtick splices); execution ONLY through the seam-injected
   `ks_exec` — **no seam ⇒ refused**, so importing tap_wire never grants a
   process the flip (an officer session calling `apply_tap` gets a refusal,
   the EVAL-001b hook refusal being a separate, untouched door). After the
   flip a FRESH `status` read repaints the card via the new `edit_text` seam
   (fallback: inert keyboard receipt; a repaint failure never un-handles).
   Success ⇒ handled, no relay (no LLM in the loop); failure ⇒ loud card AND
   the bracket-line relay floor.
4. **Poller** — `/killswitch` routed mechanically (anchored, case- and
   @botname-tolerant regex, precedent `_ONBOARDING_INTENT_RE`): fresh status
   card via `sendMessage` from THIS process (works precisely when officers
   are halted); send failure falls OPEN to the Chair relay — never silently
   consumed. DM archived (`kind="killswitch"`, utterance contract) +
   feed-journaled. `run_kill_switch` is the ONLY shell-out: closed action set
   (activate|deactivate|status; anything else raises), never raises on
   execution failure (loud tuple), and sets `CABINET_OFFICER=captain-telegram`
   so the SCRIPT's own audit row records telegram provenance.
   `apply_tap_live` wires `edit_text` + `ks_exec`.
5. **Runbook** — `docs/runbooks/captain-killswitch-card.md` (one law, E-stop
   asymmetry, pieces, provenance, failure modes; watchdog + skins named as
   other lanes).

## Review posture

Germline untouched: `cabinet/scripts/kill-switch.sh` and
`cabinet/scripts/hooks/` have zero diffs (executed, never edited);
`activate` acquires no new friction anywhere — this lane adds a captain door,
gates nothing. Dirty-guard clean at start (no other wave owns these files);
live tree never touched. Corridor plan analysis NOT run — the corridor MCP
server is unavailable in this environment (noted, not skipped silently).

## Verification evidence (this worktree, python3.12)

- Lane suites: `test_killswitch_card.py` + `test_tap_wire_killswitch.py` +
  `test_killswitch_telegram_card.py` → **52 passed** (incl. disposable-redis
  flips with `actor=captain-telegram` audit rows, the tap→script→repaint
  loop both directions, loud-failure card on a dead control plane, and the
  EVAL-001b distinction test: officer hook exit 2 + refusal held while the
  poller door deactivated and signed the ledger — same disposable redis).
- Full `framework`: **5569 passed, 29 skipped**.
- Full `cabinet/scripts/tests`: **1424 passed, 5 skipped, 2 failed** →
  (a) docs-sweep calibration red only while the new files were untracked
  (existence oracle = git index); green after staging — `test_docs_sweep.py`
  **13 passed**. (b) `test_evidence_seam_bypass_replay.py[evidence-access.sh]`
  fails IDENTICALLY on a pristine origin/master worktree (verified this
  session) — pre-existing/environmental, not this lane.
- Poller + kill-switch-events regression: **78 passed**.
- `framework/comms` + `framework/attention`: **477 passed**.
- `check-layer-separation.sh`: new=0 (baseline=24 allowlist=18 current=42).
- `py_compile` clean on all four touched/new source files.
- Fixture hygiene: no 9+-digit numbers, no instance/product tokens in any
  new file (egg publish gate).

## Residuals

- The re-arm watchdog (cleared-without-audit-row ⇒ re-arm + notify) and the
  dashboard/World skins are separate Phase-1/2 lanes — not in this diff.
- Pre-existing red: `test_evidence_seam_bypass_replay.py[evidence-access.sh]`
  (2 allowed-read cases refused, exit 2) on origin/master itself — needs its
  own investigation, outside this lane.
