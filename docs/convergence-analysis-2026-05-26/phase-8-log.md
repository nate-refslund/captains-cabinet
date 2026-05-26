# Phase 8 Log — MacMini Hardening

**Started:** 2026-05-26
**Branch:** `claude/convergence`
**Status:** **COMPLETE** for everything that doesn't require physical Mac state ✅
            **DEFERRED**: 72h soak, code-signing actually executed, UPS hardware test (Captain-physical work)

## Goal

Resolve the open MacMini-deployment gaps from the convergence plan: `setup-mac.sh --check` mode (turned out already done), `verify-launchagents.sh` automation, the code-signing/notarization runbook the Cabinet has been deferring, Tailscale + UPS + backup runbooks.

## Audit findings

1. **setup-mac.sh `--check` flag** — **ALREADY EXISTS in the rebuild branch.** My Phase 0 finding was based on an older version. The rebuild's setup-mac.sh has `--check`, `--dry-run` (alias), and `--help` already. The spawn-task chip created in Phase 0 was a false alarm. Verified by re-running `setup-mac.sh --check` on the convergence worktree → exit 0, all prereqs present.

2. **LaunchAgent verification** — no existing script; needed.

3. **Code-signing runbook** — `docs/mac-mini-setup.md` Checkpoint 1.10 had marked this as a stub. Now resolved in the consolidated runbook below.

4. **Tailscale + UPS + backups** — referenced in scattered places, no consolidated runbook.

## Delivered

### 8.1 — `cabinet/scripts/verify-launchagents.sh`

Post-deploy verification gate. Checks:
- Each expected plist is present in `~/Library/LaunchAgents/`
- Each is registered with `launchctl list`
- Each is running (non-`-` PID column)
- `~/Library/Logs/cabinet/` exists

Expected plists are derived dynamically:
- Static set: `com.cabinet.heartbeat-watchdog`, `com.cabinet.cost-summary`, `com.cabinet.ovi-weekly`, `com.cabinet.worktree-listener`
- Per-officer: `com.cabinet.officer.<slug>` for each `instance/roles/active/<slug>.yml`

Output modes: human-readable (default) or `--json` for chaining into other scripts. Exit code reflects pass/fail.

Smoke-tested on the convergence dev worktree (no plists deployed, no Mac LaunchAgents) — correctly reported all expected agents missing + returned exit 1.

### 8.2 — `docs/mac-mini-deploy-runbook.md`

Consolidated end-to-end runbook with 11 numbered sections + troubleshooting table + Captain-readable summary:

1. Hardware prerequisites (Mac Mini, UPS, ethernet, Apple Developer ID)
2. Base macOS setup (Xcode tools, Homebrew, sleep/power settings)
3. Cabinet repo clone
4. `setup-mac.sh` invocation + verification
5. Configuration (.env, platform.yml Captain identity, triplet bootstrap)
6. First product onboarding (`bootstrap-project.sh`)
7. **Code-signing + notarization** (Apple Developer cert, `codesign --entitlements`, `xcrun notarytool submit`, TCC permission grants) — this resolves the long-deferred Checkpoint 1.10
8. LaunchAgent deployment + verification
9. Tailscale remote access setup
10. APC UPS + `apcupsd` + shutdown hook test
11. Backup strategy (Postgres via Neon PITR, filesystem rsync to NAS/S3, Redis snapshot)
12. 72h soak verification protocol
13. Troubleshooting table covering 6 common failure modes

Steps requiring Captain-physical actions are flagged `[CAPTAIN]` (Apple Developer enrollment, certificate import, Telegram setup, UPS hardware connection).

## Files touched

- `cabinet/scripts/verify-launchagents.sh` (NEW, ~110 lines)
- `docs/mac-mini-deploy-runbook.md` (NEW, ~230 lines)
- `docs/convergence-analysis-2026-05-26/phase-8-log.md` (this file)

## Deferred — requires physical Mac state

These items in the convergence plan's MacMini-readiness checklist cannot be verified in this dev session:

- [ ] **72h soak passes** — by definition takes 72 hours of unattended runtime
- [ ] **Forced crash test (kill -9 officer → supervisor restarts within 30s)** — requires deployed officers
- [ ] **Mac restart test (power-cycle → full Cabinet back up)** — requires deployed officers
- [ ] **Code-signing actually executed** — requires Apple Developer ID + the Mac Mini hardware
- [ ] **UPS hardware test (unplug → graceful shutdown)** — requires physical UPS

These move from "open work" to "Captain-time verification" — they're the actual MacMini deployment + soak, executed against the runbook above. The runbook is the deliverable; running it is the Captain's job.

## Resume signal

Phase 8 complete (within session scope). Next: **Phase 9 — Final validation + convergence merge prep** (golden eval pass, OVI baseline, updated README + CLAUDE.md, PR readiness).
