# Outcome-Monitoring Watchdog

**Built 2026-06-29.** The cabinet's independent answer to *silent failures* — the
class where a process runs cleanly (`exit 0`, launchd "active", pipe-health
green) but the **OUTCOME never happens**.

## Why it exists (the bug of record)

On 2026-06-29 the 07:30 front-door briefing cron exited 0. launchd showed it
active. Every existing monitor said "green" — because they all check that the
**PROCESS ran**. But the briefing's Telegram send `400`'d, and the failure was
swallowed: the run-log recorded `send.sent == false` and silently re-queued the
undelivered backlog, which snowballed to **77 recovered-but-undelivered items**
over days. The Captain never got those briefings, and nothing noticed.

The gap is structural: **nothing verified the OUTCOME actually happened.** This
watchdog adds exactly that layer — and only that layer. It composes with the
existing telemetry (`anomaly-scan`, `pipe-watchdog`, `status-sweep`) rather than
duplicating them: anomaly-scan reads telemetry, pipe-watchdog heals stalled
ingestion pipes; this verifies *outcomes* and routes the failures.

## The four pieces

| Piece | File | Role |
|-------|------|------|
| **Expectations registry** | `framework/watchdog/registry.py` | Declarative catalog of "what should be TRUE" + cadence + verify-fn + tier. Add an outcome = add one `Expectation(...)` row to `_CATALOG`. Deployment data (briefing slot times, officer roster, pipe-freshness table, enabled row ids) is instance config: `instance/config/watchdog.yml` (egg R017). |
| **Independent checker** | `framework/watchdog/check.py` + `cabinet/scripts/run-outcome-watchdog.sh` | Stdlib-only, imports NOTHING it watches. Evaluates the registry, routes failures by tier, stamps its heartbeat. launchd every :00/:30. |
| **Tiered response** | `check.py::route_failure` | auto-fix / escalate-to-Chair / drift-note, with anti-thrash cooldown. |
| **Dead-man's switch** | `~/.screenpipe/pipes/pipe-watchdog/check.py::check_outcome_watchdog_deadman` | A *separate* survivor pings the Chair if the watchdog's own heartbeat staleens. Who-watches-the-watchman. |

## 1. The expectations registry

An **expectation** is a statement of what should be TRUE in the world, NOT that a
process ran. Each row in `EXPECTATIONS` carries:

- `id` — stable slug (logs, dedup keys, proposal ids)
- `what` — one-line human statement (shown to the Chair on escalation)
- `cadence_s` — how often the outcome must (re)occur
- `tier` — `AUTO_FIX` | `ESCALATE_CHAIR` | `DRIFT`
- `verify(probe) -> CheckResult` — cheap, side-effect-free; reads only
- `auto_fix(probe, result) -> str|None` — only for `AUTO_FIX` tier

**Instance config (egg R017):** the briefing slot times, the fulltime-officer
roster, the pipe-freshness table, and WHICH catalog rows are enabled live in
`instance/config/watchdog.yml` — parsed with a narrow stdlib parser (survival
contract: no PyYAML), so edit only in that file's documented shapes. The PATH
itself resolves through the ratified env seam
(`framework.env.watchdog_config_path()`; env `CABINET_WATCHDOG_CONFIG`
overrides — layer-separation gate: the registry carries no instance path
tokens). A missing or unparseable file degrades to generic defaults (briefing 07:30/19:30 +45m,
empty roster, empty pipe table, ALL rows enabled): a bad config can narrow the
watchdog's inputs, never blind the sweep itself.

**Seeded expectations** (the schedule/roster/pipe values shown are this
deployment's `watchdog.yml`):

| id | Outcome verified | Tier | How it's verified (OUTCOME, not process) |
|----|------------------|------|------------------------------------------|
| `briefing-delivered` | Briefing DELIVERED to the Captain 2×/day (07:30 + 19:30 local) | auto-fix | **Satisfied by delivery via ANY means** (refinement below). Checks the `cabinet:schedule:last-run:cos:briefing` marker first (the Chair stamps it on every delivery, incl. a manual one); if ≥ the due slot → OUTCOME TRUE. Else falls back to the cron log: newest record `send.sent == True` after the slot = delivered; a fresh `sent:false` = ran-but-send-failed; a stale success = didn't-run. |
| `officer-reflection` | Each fulltime officer that did recent work reflected within 48h | escalate-chair | Reuses the same `cabinet:schedule:last-run:<o>:reflection` + `cabinet:last-experience:<o>` stamps the anomaly-scan reads. Idle officers (no recent work) are not expected to reflect. |
| `captain-decisions-logged` | Relayed Captain decisions are logged to `captain-decisions.md` | drift | Soft backstop to the real-time post-tool-use enforcement: flags if the newest dated entry is >7 days old (a structural lapse). |
| `no-silent-cron-failure` | The cabinet's own crons produce output and don't silently error | escalate-chair | Per watched job log: error-marker in the tail (`FATAL`, `Traceback`, `trigger NOT pushed`) OR stale past cadence. |
| `pipes-fresh` | Brain ingestion pipes (msgraph/teams/embeddings) fresh | escalate-chair | Log mtimes only (no Graph poll). pipe-watchdog auto-heals stalls; a residual stale pipe here = the heal didn't take. |

**To add an expectation:** append one `Expectation(...)` to `_CATALOG` in
`registry.py` with a `verify` fn that takes the `Probe` and returns a
`CheckResult`. Pick the tier by how a failure should be handled. If
`instance/config/watchdog.yml` narrows `expectations:`, also enable the new id
there (an absent/empty list already enables every catalog row). The checker
picks it up automatically.

## 2. Independence (the load-bearing property)

The checker is **stdlib only** and **imports nothing it watches** (no
`framework.frontdoor`, no screenpipe libs, no `org_runtime`). A watchdog built on
top of the thing it watches dies with it. Every verify reads a **file**, a
**Redis key** (via `redis-cli` subprocess), or a **file mtime** — the cheapest
possible probe. It NEVER polls Graph/Vercel/an LLM, so it's free to run every
30 min.

All I/O is funnelled through one injectable `Probe` object — which is also what
makes the whole registry testable with an in-memory fake (zero network, zero
real Redis) and guarantees a verify can't quietly reach for the network.

## 3. Tiered response (per failed expectation)

| Tier | Action | Routing |
|------|--------|---------|
| **AUTO_FIX** | Run the expectation's deterministic-safe `auto_fix`. For the briefing, that re-triggers the **Chair** with full context to re-run the send through the gated front-door channel — the watchdog NEVER sends outbound itself (brain-bridge rule: `queue_draft`/the Chair is the only send path). | `cabinet:triggers:cos` |
| **ESCALATE_CHAIR** | Push ONE consolidated trigger to the Chair to triage (gather-then-decide, fix root cause). | `cabinet:triggers:cos` |
| **DRIFT** | Append a proposal to `meta-cognition-proposals.md` via `mc_emit_proposal` (proposal-only, Captain-gated — **not** an alert). | meta-cognition sink |

**The Captain is never DM'd directly.** Per the `P-Alerts-To-Chair` pattern, every
operational alert routes to the Chair; the Chair escalates to the Captain only if
genuinely stuck. Every Chair trigger explicitly says *"do NOT DM the Captain the raw
failure."*

**Anti-thrash:** each routed action is deduped on `(expectation_id, action)` via
a Redis cooldown key (`cabinet:watchdog:outcome:cooldown:*`, default 3h TTL), so
a persistently-broken outcome fires its fix/escalation **once per cooldown**, not
every cycle. Verified: run #1 fired the auto-fix; run #2 (same cycle) reported
`auto-fix SKIPPED (cooldown active)`. For expectations that report a `slot_id`
(the briefing), the cooldown is **scoped to that slot** — a handled AM-slot
failure never suppresses a fresh PM-slot failure, and a flagged+handled slot
never re-alerts.

## Refinements from first live fire (2026-06-29)

The watchdog fired on its very first cycle and correctly detected the 07:30
briefing's silent send failure → escalated to the Chair (not the Captain). That live
fire surfaced two refinements, now built in:

1. **Satisfied by ANY delivery, not just the cron's send.** The OUTCOME is "the Captain
   got his briefing" — delivered by any means. The first fire flagged the 07:30
   slot as undelivered even though the Chair had *manually* delivered it after the
   cron missed (the Chair stamped `cabinet:schedule:last-run:cos:briefing =
   "2026-06-29T06:29:35Z (manual — cron miss)"`). The verify now reads that
   marker first (parsing the leading ISO token, ignoring the trailing
   annotation); if it's dated ≥ the due slot, the outcome is TRUE regardless of
   the cron's send-status. A stale marker (before the slot) does NOT satisfy it.
2. **Per-slot dedup.** The auto-fix/escalation cooldown is scoped by `slot_id`
   (`YYYY-MM-DD-AM|PM`), so a handled slot never re-alerts each cycle while a
   *new* slot's failure can still fire.

Net effect: a briefing recovered by any path no longer false-positives, and the
19:30 delivery (the chunking fix is applied) verifies OK and stays quiet.

## 4. Dead-man's switch (who-watches-the-watchman)

On every successful sweep the checker stamps `cabinet:watchdog:outcome:heartbeat`
= now. A **separate, simpler survivor** — the screenpipe `pipe-watchdog` (already
calendar-scheduled, proven immune to the `StartInterval` throttle, and NOT built
on the cabinet's own trigger/briefing path) — reads that heartbeat every 10 min
and pings the Chair if it's >75 min stale (2.5 missed cycles). Self-contained
`redis-cli XADD` to `cabinet:triggers:cos` — no cabinet-python import, so a
broken cabinet can't break the dead-man's switch. Cooldown ~3h, never-seen vs
went-absent distinguished (a fresh install with no heartbeat yet doesn't page).

## Running it

```bash
# Dry-run (evaluate + print, NO side-effects: no triggers, no proposals, no heartbeat)
python3 -m framework.watchdog.check --dry-run

# Real run (what launchd invokes via the wrapper)
PATH=/opt/homebrew/bin:$PATH REDIS_HOST=localhost python3 -m framework.watchdog.check

# JSON
python3 -m framework.watchdog.check --json
```

Exit code is **always 0 when the checker ran** — a failed outcome is *data*, not
a checker error, so launchd never marks the watchdog "failed" for doing its job.

## Install (launchd)

```bash
cp cabinet/launchd/com.cabinet.outcome-watchdog.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.cabinet.outcome-watchdog.plist
# verify
launchctl print gui/$(id -u)/com.cabinet.outcome-watchdog | head
tail -f ~/.cabinet/logs/outcome-watchdog.log
```

Disable (reversible):
```bash
launchctl bootout gui/$(id -u)/com.cabinet.outcome-watchdog
rm ~/Library/LaunchAgents/com.cabinet.outcome-watchdog.plist   # optional, full removal
```

Schedule: `StartCalendarInterval` at :00 and :30 (wall-clock — **not**
`StartInterval`, which the macOS power manager can silently coalesce/throttle for
hours; a watchdog that silently stops is worse than none). The dead-man's switch
covers a watchdog that stops firing for any reason.

> **MacBook limit:** launchd doesn't fire while the Mac is asleep; a missed slot
> fires once on wake. True 24/7 cadence needs the always-on Mac Mini. The
> dead-man's switch (also calendar-scheduled) is the backstop.

## Tests

```bash
# registry verifies + tiered routing (in-memory FakeProbe, no network)
python3 -m pytest framework/watchdog/tests/ -q          # 28 tests

# dead-man's switch (fake redis)
cd ~/.screenpipe/pipes/pipe-watchdog && python3 -m pytest test_deadman.py -q   # 5 tests
```

The headline test reconstructs the exact production failure (a briefing log whose
process ran but whose send 400'd) and asserts it verifies FALSE and routes to the
auto-fix Chair re-trigger. Further tests cover: satisfied-by-any-delivery (manual
marker), per-slot dedup, `sent`-alone success (no false-fail on a renamed status),
record-level-ts preference over mtime, TZ-unresolved skip, and the deadline guard.

## Known follow-ups (non-blocking)

- **Briefing record `ts` (structural):** the verify currently uses the log file
  mtime as the run time (preferring a record-level `ts`/`run_time` if present).
  mtime can in theory advance without a new complete record (rotation/partial
  write), so the durable fix is for `run_briefing` to stamp a top-level `ts` per
  appended record — then the verify uses it natively. The satisfied-by-marker
  path is the primary guard today, so this is hardening, not a live gap.

## Secrets

The checker reads **no secrets**. Its only outbound is a localhost Redis trigger
(which the Chair turns into a gated send) — the bot token never enters the
process. The wrapper reads none either; it only fixes the launchd-minimal-PATH
gotcha and points Redis at localhost.

## Files

- `framework/watchdog/registry.py` — expectations registry + verifies
- `framework/watchdog/check.py` — checker + tiered router + RealProbe
- `framework/watchdog/tests/test_registry.py` — 20 tests
- `cabinet/scripts/run-outcome-watchdog.sh` — launchd wrapper
- `cabinet/launchd/com.cabinet.outcome-watchdog.plist` — schedule (calendar :00/:30)
- `~/.screenpipe/pipes/pipe-watchdog/check.py` — dead-man's switch (added function)
- `~/.screenpipe/pipes/pipe-watchdog/test_deadman.py` — 5 dead-man's-switch tests
