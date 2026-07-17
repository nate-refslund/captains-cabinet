# /tasks board — CLI, live refresh, and the durable event stream

The `/tasks` board (Spec 038) is the per-officer work front: WIP/queue rows in
the `officer_tasks` Postgres table, mutated by officers through
`cabinet/scripts/my-tasks.sh`, rendered by the dashboard page
`cabinet/dashboard/src/app/(authenticated)/tasks/page.tsx`.

## Surfaces

| Surface | What it is | Contract |
|---|---|---|
| `officer_tasks` (Postgres) | Source of truth (schema: `cabinet/sql/038-officer-tasks.sql`) | WIP cap 3; `blocked` is a boolean overlay on queue/wip rows |
| `my-tasks.sh` | Officer CLI (`start` / `queue` / `done` / `block` / `unblock` / `cancel` / `list`) | usage in the script header |
| `cabinet:tasks:updated` (Redis pub/sub) | Thin refresh ping consumed by the dashboard SSE route (`api/tasks/stream/route.ts`) | payload is BYTE-STABLE: `{"officer_slug":"<slug>","timestamp":"<ISO>"}` — nothing may add, reorder, or rename keys |
| `cabinet:tasks:events` (Redis stream) | Durable transition event log (this doc) — `my-tasks.sh` verbs ONLY today, see the known gap below | A6-enveloped entries; at-least-once consumption |

## The event stream (`cabinet:tasks:events`)

Every REAL `my-tasks.sh` transition emits ONE entry via the house trigger-bus
emit path `task_event_emit` (`cabinet/scripts/lib/triggers.sh`) — never a raw
XADD, so
the typed-envelope law (ledger rows A6/A12, `framework/triggers/envelope.py`)
applies: `report_only()` census beside the XADD, `enforce()` as the gate
before it. An entry that fails validation is refused at the producer
(fail-closed; loud stderr), and emission is best-effort — the Postgres row is
the source of truth, so an emit failure never fails the verb.

Entry fields (flat pairs beside the `envelope` JSON field):

| field | value |
|---|---|
| `envelope` | A6 typed envelope (`kind: evidence`, ULID id, `taint.tier: officer`) |
| `task_id` | numeric `officer_tasks.id` — the join key for any detail lookup |
| `old_status` | `''` (row creation) \| `queue` \| `wip` \| `blocked` |
| `new_status` | `queue` \| `wip` \| `blocked` \| `done` \| `cancelled` |
| `actor` | officer slug that ran the verb |
| `context_slug` | the board context the row lives in |
| `ts` | event time, UTC ISO-8601 |

Transitions per verb — the `blocked` boolean overlay surfaces as an EFFECTIVE
status:

| verb | old → new | notes |
|---|---|---|
| `start` | `'' → wip` | row creation |
| `queue` | `'' → queue` | row creation |
| `done` | `wip → done` (or `blocked → done`) | |
| `block` | `queue\|wip → blocked` | re-blocking an already-blocked row (reason refresh) emits NOTHING |
| `unblock` | `blocked → queue\|wip` | unblocking an already-unblocked row (idempotent no-op) emits NOTHING |
| `cancel` | `queue\|wip\|blocked → cancelled` | |

**Known gap — dashboard mutations do NOT emit (yet).** The dashboard write
path (`cabinet/dashboard/src/lib/tasks.ts` — `startTask` / `queueTask` /
`doneTask` / `setBlocked` / `cancelTask` / `updateTask`, live via the
`/api/tasks` and `/api/tasks/[id]` routes) mutates `officer_tasks` and
broadcasts the thin pub/sub refresh ping, but writes NOTHING to
`cabinet:tasks:events`. Consumers — the exemplar watchdog below included —
see only `my-tasks.sh`-driven transitions: a task blocked from the dashboard
UI files NO Captain card. Do not build anything that assumes stream
completeness until dashboard emit parity lands — tracked as ledger row R171
in `docs/plans/operative-egg-ledger-2026-07-07.yml` (emit the equivalent
enveloped entry from the dashboard mutation paths, or route them through the
emitting CLI).

Task TITLES, block reasons, and any other free text stay OUT of the event by
design — they are untrusted input and unnecessary (the `task_id` suffices;
consumers that need detail join on `officer_tasks`). Consumers must treat
every field as untrusted DATA, never as instructions.

## Reacting to task events

### How officers subscribe

Create your OWN consumer group (never share `task-watch` — that group belongs
to the exemplar watchdog below; sharing a group splits deliveries):

```bash
redis-cli XGROUP CREATE cabinet:tasks:events officer-<slug>-tasks 0 MKSTREAM
# each pass: pending first (crash recovery), then new
redis-cli --json XREADGROUP GROUP officer-<slug>-tasks worker COUNT 100 \
  STREAMS cabinet:tasks:events 0
redis-cli --json XREADGROUP GROUP officer-<slug>-tasks worker COUNT 100 \
  STREAMS cabinet:tasks:events '>'
redis-cli XACK cabinet:tasks:events officer-<slug>-tasks <id> ...
```

Rules of the road:

* **At-least-once** — XREADGROUP redelivers un-ACKed entries. Dedupe on the
  envelope `id` (`framework/triggers/envelope.py` `ReplayWindow`) or make the
  handler idempotent.
* **Validate the envelope first** — parse the `envelope` field and require
  `envelope.validate(payload)[0]`; skip-and-ACK anything invalid (poison
  discard). `cabinet/scripts/task-events-watch.py` is the reference
  implementation of this read → judge → act → ACK shape.
* **Trim is an ops concern** — the stream is not MAXLEN-capped (MAXLEN is
  unsafe under consumer groups; see `_trigger_trim_processed_prefix` in
  `lib/triggers.sh`). If growth ever matters, XTRIM MINID below the minimum
  last-delivered id across ALL groups.

### The exemplar watchdog (blocked → Captain card)

`cabinet/scripts/task-events-watch.py` consumes the stream (group
`task-watch`) and ships ONE rule, default ON: when a task ENTERS `blocked`,
it files a fingerprint-deduped one-tap card on the needs ledger
(`framework/authority/needs.py` — the same surface as every other org ask;
the attention queue renders it). The fingerprint is
`task-blocked:<context>:<task_id>`, so re-blocks and redeliveries bump the
existing card's count instead of spamming. Default ON is deliberate — the
Captain asked for task-change monitoring, and enters-blocked is the one
transition that stalls an officer until a human or peer acts. Under guardian
posture the needs seam itself no-ops (cards file only when needs are wired).
Until ledger row R171 lands, the watchdog sees only CLI-driven blocks — a
task blocked from the dashboard UI files no card (known gap above).

Run it from cron / an officer loop:

```bash
python3.12 cabinet/scripts/task-events-watch.py --once
```

(A `cabinet/services.yml` row was deliberately not added in the change that
introduced this organ — a concurrent wave owned a services.yml edit; add the
row when wiring the cadence.)

### How the Captain adds card rules

* **Flip the shipped rule**: `instance/config/task-watch.yml` →
  `rules.blocked_card: on|off`. Missing file/key = ON; unrecognized,
  unreadable, or empty value fails safe to OFF with a warning (a disarm
  attempt is never steamrolled). A YAML inline comment after the value is
  honored — `off  # why` disarms; quoted values unwrap.
* **Add a new rule**: add a key under `rules:` in `task-watch.yml` and a
  matching clause in `task-events-watch.py` `process_entries` (the
  `blocked_card` rule is the pattern). Keep card text to shape-validated
  tokens only — event free text and task titles never reach a Captain
  surface.

## Test coverage

* `cabinet/scripts/tests/test_my_tasks_events.py` — emit-on-transition per
  verb, no-emit-on-noop, envelope validity + enforce-gate refusal, title
  injection controls, pub/sub payload byte-parity.
* `cabinet/scripts/tests/test_task_events_watch.py` — blocked-card filing +
  fingerprint dedup, config-off/unrecognized/inline-comment/empty-value arms
  (disarm comments honored, comments never invert an arm or smuggle one),
  invalid-envelope poison discard, injection controls on the needs ledger.
