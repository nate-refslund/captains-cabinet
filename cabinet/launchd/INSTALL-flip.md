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
