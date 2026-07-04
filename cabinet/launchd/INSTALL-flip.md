# INSTALL-flip — arming the machine-label producers (L7-ops-scheduling)

Three NEW LaunchAgents ship with this lane. None are loaded by the repo — a
human integrator runs the commands below on the target Mac (checkpoint
2026-07-04 conditions 5 + 12; DO NOT script these — loading is a deliberate
human step of the flip protocol).

| Label | Cadence | What it arms |
| --- | --- | --- |
| `com.cabinet.undo-sweep` | hourly | UNDO-3 TTL sweep → first machine ttl_ok / silent_revert labels + F2b revert-rates (real Monday probe; skips on outage rather than mint false ttl_ok) |
| `com.cabinet.actfirst-canary` | weekly (Mon 07:15) | TI-7 journal-only create→verify→reverse canaries + kind/silence breakers + veto audit (failure freezes the kind) |
| `com.cabinet.falsifier-daily` | daily (08:05) | one read-only JSON line/day → `shared/interfaces/falsifier-series.jsonl` so Day-14/Day-30/Quarter falsifiers are measurable |

Install + load (from the live checkout `/Users/nate/captains-cabinet`):

```sh
cp cabinet/launchd/com.cabinet.undo-sweep.plist ~/Library/LaunchAgents/
cp cabinet/launchd/com.cabinet.actfirst-canary.plist ~/Library/LaunchAgents/
cp cabinet/launchd/com.cabinet.falsifier-daily.plist ~/Library/LaunchAgents/

launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.cabinet.undo-sweep.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.cabinet.actfirst-canary.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.cabinet.falsifier-daily.plist
```

Verify (each should list the label; logs land in `~/.cabinet/logs/`):

```sh
launchctl list | grep com.cabinet
tail -f ~/.cabinet/logs/undo-sweep.log ~/.cabinet/logs/actfirst-canary.log ~/.cabinet/logs/falsifier-daily.log
```

Disable any of them (reversible, no code change):

```sh
launchctl bootout gui/$(id -u)/<label>
rm ~/Library/LaunchAgents/<label>.plist
```

Notes for the integrator:

- The sweep and canary read `MONDAY_API_TOKEN` / `MONDAY_API_KEY` from
  `~/.screenpipe/pipes/_shared/.env` at run time — no secrets in any plist.
- Forcing the first green canary per kind (flip condition 5) is a manual run:
  `bash cabinet/scripts/run-actfirst-canary.sh` — it exits non-zero and prints
  `PAGE:` lines if anything froze.
- None of this touches `instance/config/act-first-enabled` or
  `CABINET_ACT_FIRST`; the act-first flip itself stays a separate Captain step.

## Arming the veto wire (TI-4 — lane-ops 2026-07-04)

The cos-inbound officer plist now carries `CABINET_VETO_WIRED=1` in its
`EnvironmentVariables` (set in the `cos-inbound` row of `cabinet/services.yml`,
so the generated plist has it; the hand-made fallback
`cabinet/launchd/com.cabinet.officer.cos-inbound.plist` was updated to match).
What it arms — the sharpest demotion tooth, previously dark:

- A Captain **`never:`** on an acted receipt (and `lift veto-NNN` /
  `veto confirm`) now **PERSISTS** to `shared/interfaces/captain-vetoes.yml`
  via `framework/frontdoor/veto_registry.py` (before this flag, the verbs
  parsed but recorded nothing).
- `run_action_lane`'s `is_vetoed()` check thereby becomes a **real pre-act
  block** — a vetoed (action_type, board, content_family) scope can never act
  again until the Captain lifts it.
- Safety shape: writes are gated on `captain_verified` (the poller relays ONLY
  `CAPTAIN_TELEGRAM_ID` messages), so a veto is unforgeable; the flag only ever
  TIGHTENS autonomy. Rollback: remove the env line + redeploy.

Apply on the target Mac (picks up the new env):

```sh
launchctl bootout gui/$(id -u)/com.cabinet.officer.cos-inbound
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.cabinet.officer.cos-inbound.plist
```

(If the installed copy is the generated one, re-render first:
`python3.12 cabinet/scripts/generate-plists.py` and copy
`cabinet/launchd/generated/com.cabinet.officer.cos-inbound.plist` into
`~/Library/LaunchAgents/`.)

## Runtime-durability agents (lane-ops 2026-07-04)

Two more repo plists ship alongside the flip agents — same deliberate-human
loading rule:

| Label | Cadence | What it fixes |
| --- | --- | --- |
| `com.cabinet.retro-trigger` | hourly | REGENERATED with `PATH` (the old hand-made plist had none; launchd's minimal PATH → `redis-cli: command not found` → FATAL hourly since ~Jul 3). Logs move to `~/Library/Logs/cabinet/retro-trigger.{log,err}`. |
| `com.cabinet.backup` | daily 03:00 | NEW — daily state backup to `~/Cabinet-Backups` (rsync of shared/interfaces + instance + memory, Redis BGSAVE copy, 14-day retention). Drill: `bash cabinet/scripts/restore-drill.sh`. |

```sh
cp cabinet/launchd/com.cabinet.retro-trigger.plist ~/Library/LaunchAgents/
launchctl bootout gui/$(id -u)/com.cabinet.retro-trigger 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.cabinet.retro-trigger.plist

cp cabinet/launchd/com.cabinet.backup.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.cabinet.backup.plist
```

NATE-DECISIONS deliberately left open (details in the backup plist header +
`cabinet/services.yml` backup row): off-machine backup copy (recommend rsync
to the UpCloud CPH box over Tailscale) and Redis AOF enablement
(`cabinet/scripts/enable-redis-aof.sh` exists; it restarts Redis, so flipping
it stays a Captain step).
