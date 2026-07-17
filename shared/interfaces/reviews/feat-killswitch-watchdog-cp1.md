# Checkpoint review — feat/killswitch-watchdog cp1 (2026-07-17)

Lane checkpoint (FW-019) for the captain-controls Phase 1 re-arm watchdog
(ratified design docs/plans/captain-controls-no-terminal-2026-07-17.md,
"Raw-write backstop"). One lane, three files on a clean worktree off
origin/master @a51f98f3: the watchdog script (496 lines), its pytest suite
(380 lines), and one staged services.yml row (+27 lines). No existing file
besides the manifest is touched; kill-switch.sh is EXECUTED, never edited.

## What landed

1. **`cabinet/scripts/killswitch-watchdog.py`** — 60s tick: reads the
   switch (redis GET `cabinet:killswitch`, kill-switch.sh REDIS_URL parse
   parity incl. the docker `redis`-host residue guard) and the newest
   `kill_switch_*` ledger rows (day files newest-first, shared flock,
   torn-tail tolerant; scan stops at the first file containing an
   activation row — every sanctioned deactivation at/after that arm is
   necessarily already collected). Verdict is **provenance-keyed, not
   row-order-keyed**: sanctioned rows carry `payload.via="kill-switch.sh"`
   (pinned by test_kill_switch_events.py); the staged
   authority-transitions sweep's rows (actor `authority-watch`,
   `attribution=state-observed`, no `via`) describe a raw clear and
   sanction nothing — the brief's literal "newest row is
   kill_switch_deactivated = sanctioned" rule would let that sweep mask
   every raw clear it observes, so the implemented rule is: newest ARM of
   any provenance vs newest SANCTIONED deactivation at/after it.
   Unattributed clears must persist past a **grace** (default 90s, env
   `CABINET_KILLSWITCH_REARM_GRACE_S` / `--grace-s`) keyed to the arm
   row's id in an atomic state file (authority-sweep shape;
   `CABINET_KILLSWITCH_WATCHDOG_STATE_FILE` / `--state-file`) — an
   in-flight activate→deactivate ceremony is never fought and a new
   episode restarts the clock. Re-arm rides the SAME sanctioned surface
   (`bash kill-switch.sh activate`, `CABINET_OFFICER=killswitch-watchdog`
   → attributable audit row, read-back verified by the brake script
   itself), then ONE plain-English captain notification (the design doc's
   sentence) through `framework/frontdoor/channel.py` via the
   evidence-anchor `_send_receipt` idiom (env-NAME presence check →
   skipped-unconfigured; catch-all → failed; never unwinds the re-arm).
   **E-stop asymmetry pinned**: the watchdog only ever activates
   (source-level test). Fail-safe no-ops, all loud: unreachable redis,
   missing events dir (cannot attribute → never a guessed re-arm), cold
   ledger. FATAL + exit 1 only when a due re-arm itself fails (anomaly
   kept, next tick retries) or the state write fails. `--dry-run`
   supported.
2. **`cabinet/scripts/tests/test_killswitch_watchdog.py`** — behavioral
   (disposable redis ports 26200+, tmp CABINET_EVENT_LOG_DIR, real
   kill-switch.sh + real watchdog subprocesses): switch active → no-op;
   sanctioned resume (grace 0) → never fought; raw DEL → grace-pending
   first tick, re-arm past grace with `rearm_rc=0`, new activation row
   `actor=killswitch-watchdog` + `via=kill-switch.sh`, notification
   ATTEMPTED through the real channel door (fake env creds, non-runtime →
   `blocked-dev`, zero network, belt TELEGRAM_API_BASE at a dead local
   port), anomaly episode closed in the state file; in-flight ceremony
   (DEL observed mid-ceremony, grace 600) → grace-pending then
   stands down when the sanctioned deactivation row lands; missing events
   dir → loud WARN "fail-safe no-op", nothing touched; --dry-run acts on
   nothing. Unit (pure `decide()`, redis-free, Linux-CI-safe): observed
   deactivation never sanctions; sanctioned resume wins over observer
   noise; a later arm re-opens the episode; anomaly-key change restarts
   the grace clock; re-arm only past grace; E-stop asymmetry source pin;
   services-row manifest pin (60s, watchdog kind, staged-disabled with
   reason).
3. **`cabinet/services.yml` row `killswitch-watchdog`** — kind watchdog,
   `interval_s: 60`, `env: { CABINET_ENV: runtime }` (channel gate),
   ships `disabled: true` + `disabled_reason` per the staged convention
   (authority-transitions / officer-lifecycle-transitions /
   evidence-anchor precedent); enable = remove flag + generate-plists +
   load. `expected` floor + `sunset` criteria carried per manifest schema.

## Design decisions vs the brief (said plainly)

- **Provenance beats row order** (deviation from the brief's letter, honors
  its parenthetical intent "cleared WITHOUT a matching deactivation row"):
  required so the staged authority-transitions sweep can never mask raw
  clears once enabled. A raw SET still counts as an arm (activate is
  unrestricted by design), so its raw clear also re-arms.
- **Row ships disabled** (staged convention; the brief anticipated this).
  The watchdog protects nothing until the deploy step enables it — flagged
  for the integrator/Captain ceremony.
- **Grace persistence lives in a disk state file**, not redis: a FLUSHALL
  (itself an unattributed clear) cannot also erase the anomaly clock.
- Unreachable-redis and missing-ledger both fail-safe to loud no-ops;
  enforcement elsewhere already treats an unreachable plane as ACTIVE.

## Verification evidence (this worktree, python3.12)

- `cabinet/scripts/tests/test_killswitch_watchdog.py` → **15 passed** (2.94s).
- `test_cron_officer_targets.py` + `test_kill_switch_events.py` +
  `framework/watchdog/tests/test_registry.py` → **81 passed**.
- Full `cabinet/scripts/tests` → **1416 passed, 5 skipped, 1 failed** —
  the failure (`test_evidence_seam_bypass_replay.py::
  test_shipped_catalog_harness_still_green[evidence-access.sh]`) is
  PRE-EXISTING: reproduced identically on a pristine origin/master
  worktree @a51f98f3 (1 failed, 23 passed in that file), unrelated
  surface, not introduced here.
- `python3.12 cabinet/scripts/generate-plists.py` → rc=0; row listed under
  "disabled (manifest-parked, not rendered)" as intended.
- `check-layer-separation.sh` → new=0 (baseline=24 allowlist=18 current=42).
- Egg gate: `grep -E '[0-9]{9,}'` over both new files → clean.
- No shell files added → bash -n/shellcheck n/a (kill-switch.sh untouched).
- Corridor plan-analysis MCP not available in this build environment —
  analysis step could not run; noted for the integrator.

## Residuals

- The row is staged dark: the re-arm protection is INERT until the deploy
  ceremony enables it (remove flag, generate-plists, load) — same posture
  as its authority-transitions sibling, but this one is a safety organ:
  recommend enabling in the same ceremony that arms Phase 1.
- If both this watchdog and authority-transitions are enabled, a raw
  clear+re-arm inside one sweep cadence may produce no observed rows from
  the sweep (state unchanged at its tick) — the watchdog's own sanctioned
  activation row remains the durable record; no action needed.
