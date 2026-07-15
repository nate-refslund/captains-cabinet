# INSTALL-flip — arming the machine-label producers (L7-ops-scheduling)

> **Fresh-deployment note (PC-E).** The rendered `com.cabinet.<name>.plist`
> files named below are a live deployment's artifacts and do not ride the
> public egg (only the `.template.plist` twins + `officer-entitlements.plist`
> ship). On a fresh deployment, render them first — daemons/watchdogs/crons
> via `python3.12 cabinet/scripts/generate-plists.py` (from
> `cabinet/services.yml`, output under `cabinet/launchd/generated/`), officers
> via `deploy-mac.sh` — then follow the same deliberate-human loading steps.

Three NEW LaunchAgents ship with this lane. None are loaded by the repo — a
human integrator runs the commands below on the target Mac (checkpoint
2026-07-04 conditions 5 + 12; DO NOT script these — loading is a deliberate
human step of the flip protocol).

| Label | Cadence | What it arms |
| --- | --- | --- |
| `com.cabinet.undo-sweep` | hourly | UNDO-3 TTL sweep → first machine ttl_ok / silent_revert labels + F2b revert-rates (real Monday probe; skips on outage rather than mint false ttl_ok) |
| `com.cabinet.actfirst-canary` | weekly (Mon 07:15) | TI-7 journal-only create→verify→reverse canaries + kind/silence breakers + veto audit (failure freezes the kind) |
| `com.cabinet.falsifier-daily` | daily (08:05) | one read-only JSON line/day → `shared/interfaces/falsifier-series.jsonl` so Day-14/Day-30/Quarter falsifiers are measurable (since 2026-07-07 the line also carries `memory_ingestion` per-source_type liveness + `recall_drops` + `session_insert_failures`, with ALERT digest lines for stale wired capture classes) |

Not yet scheduled (run manually or add via the fleet manifest, which the supply lane owns): `cabinet/scripts/emit-graduation-transitions.py` — sweeps per-cell graduation state and emits `graduation_transition` org events when a cell MOVES (unmeasured/propose_only/eligible/graduated/demote), so briefings can see cells moving instead of only counting snapshots. First run seeds its state file silently (`--emit-baseline` to override); `--dry-run` prints without emitting.

Install + load (from the live cabinet checkout, e.g. `~/captains-cabinet`):

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
- **Un-freezing a frozen kind (CRIT-5 — no auto/blind unfreeze).** A kind frozen
  by a failed canary/breaker is re-armed ONLY by a Captain-triggered green probe
  that first PROVES `create→verify→reverse` for that kind, then lifts the freeze
  (durable JSONL mirror supersede + Redis flag clear):
  `python3.12 -m framework.frontdoor.actfirst_canary --unfreeze <kind>` — takes
  the action_type (e.g. `board_status`) or the step kind (e.g.
  `monday_task_update`). Exits non-zero and LEAVES the freeze if the probe is
  non-green. Never scheduled; the only manual lift path
  (`action_undo.unfreeze` has no auto caller).
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
| `com.cabinet.backup` | daily 03:00 | Daily checksum-verified state backup to `~/Cabinet-Backups` (topology-preserved filesystem, configured Postgres, fresh Redis RDB or fsynced/restore-tested AOF fallback, 14-day retention). Drill: `bash cabinet/scripts/restore-drill.sh`. |

```sh
cp cabinet/launchd/com.cabinet.retro-trigger.plist ~/Library/LaunchAgents/
launchctl bootout gui/$(id -u)/com.cabinet.retro-trigger 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.cabinet.retro-trigger.plist

cp cabinet/launchd/com.cabinet.backup.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.cabinet.backup.plist
```

One hardening step is deliberately left open as a recorded Captain decision
— see the deliberately-NOT-wired notes where they live: the
`cabinet/services.yml` backup row (rendered into the backup plist header) and
the `cabinet/scripts/backup.sh` header: an off-machine backup copy (e.g. a
post-backup rsync to a host you control). Redis AOF is the live durability
layer and backup.sh now uses it as a verified fallback when fresh RDB capture
is unavailable.

## Verdict-supply engine (lane-supply 2026-07-05) — THE keystone wave

The 2026-07-03 re-review's core finding: the machine eval/probe/verifier stack
was **dead at runtime** — no `__main__`, no `services.yml` rows, no plists;
`CABINET_PROBES_ENABLED` existed only in comments. This wave builds the
scheduling + runners so `verdict_judge` / probe-outcome labels flow into the
consequence ledger on the SAME `(actor, lane, action_type)` cells the
act-first graduation gate reads — machine labels with zero Captain attention.
Same deliberate-human loading rule as every section above; additionally,
**installing one of these plists IS its enable flip** (each verifier/probe
plist carries `CABINET_PROBES_ENABLED=1`, and the entrypoints are inert
without it — there is no second hidden knob).

| Label | Cadence | What it arms |
| --- | --- | --- |
| `com.cabinet.verifier` | hourly | B2.8 claims↔outcomes reconciler (`cabinet/scripts/run-verifier.sh` → `framework/probes/run_verifier.py`): executed act-first action cards → `review{source: verdict_judge}` supersedes. Human verdicts never overwritten; `outcome=unknown` → no verdict (RT#4). Ledger-only. |
| `com.cabinet.probe-github` | 5 min | B2.3 PR outcomes (merged/reverted/held) joined by the `Cabinet-Proposal-Id` trailer (`run-probes.sh github`). |
| `com.cabinet.probe-vercel` | 10 min | B2.4 deploy outcomes (deploy_ready/rolled_back/deploy_error), meta-stamp join with commit-trailer fallback (`run-probes.sh vercel`). |
| `com.cabinet.probe-sentry` | 15 min | B2.5 error-budget outcomes (within_budget/regressed); frozen feed reads unknown, never ok (`run-probes.sh sentry`). |
| `com.cabinet.fidelity-f1` | monthly (1st 06:30) | F1 fidelity batch (`run-fidelity-f1.sh` → `framework/fidelity/run_f1.py`): asserts the clone still beats the 0.083 generic-assistant baseline — the slow decay canary. |
| `com.cabinet.regression-corpus` | daily 04:30 | Regression-corpus refresh — **script ships with another lane of this wave**; install only after `cabinet/scripts/build-regression-corpus.py` exists. |
| `com.cabinet.graduation-transitions` | hourly | Cell promote/demote/hold transition emitter — **script ships with another lane of this wave**; install only after `cabinet/scripts/emit-graduation-transitions.py` exists. |

Products the probes observe live in `instance/config/probes.yml` (repo slug /
Vercel app / Sentry org+project / local checkout per product — seeded with
the deployment's first product lane; edit freely, config gaps skip
fail-closed).

Install + load (from the cabinet checkout):

```sh
for p in verifier probe-github probe-vercel probe-sentry fidelity-f1; do
  cp cabinet/launchd/com.cabinet.$p.plist ~/Library/LaunchAgents/
  launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.cabinet.$p.plist
done
# post-integration only (scripts from the other lanes of this wave):
for p in regression-corpus graduation-transitions; do
  cp cabinet/launchd/com.cabinet.$p.plist ~/Library/LaunchAgents/
  launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.cabinet.$p.plist
done
```

Verify (logs in `~/.cabinet/logs/`):

```sh
launchctl list | grep -E "verifier|probe-|fidelity|corpus|transitions"
bash cabinet/scripts/run-verifier.sh --dry-run       # eyeball: zero writes
bash cabinet/scripts/run-probes.sh all --dry-run     # eyeball: zero writes
tail -f ~/.cabinet/logs/verifier.log
```

Notes for the integrator:

- Everything is READ-ONLY against GitHub/Vercel/Sentry; tokens
  (`VERCEL_API_KEY` from `~/.screenpipe/pipes/_shared/.env`,
  `SENTRY_AUTH_TOKEN` from `cabinet/.env`) reach the processes via env only —
  never argv, never in plists; empty values never claim keys.
- FAIL-CLOSED everywhere: probe/config error or `outcome=unknown` → NO verdict
  (never a spurious pass); a silent source while local git shows activity
  pages healthchecks and emits nothing.
- Healthchecks checks (`verifier`, `probe-github` 5m, `probe-vercel` 10m,
  `probe-sentry` 15m) are still the Captain's to create — `hc_ping` is fail-open
  without `HEALTHCHECKS_PING_KEY`, so the agents run correctly before the
  checks exist; they just aren't externally dead-manned yet.
- `mission-supervisor` stays STAGED DISABLED in the manifest (pull-only
  ratified 2026-07-04) — this wave deliberately does not touch it.
