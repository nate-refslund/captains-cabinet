# Captain Reminders Runbook — the /tasks due-at reminder → Captain card lane

**Status: LIVE** (needs plane must be wired — see Prerequisites). Spec 041 gave
`officer_tasks` a `due_at` + the cron worker
`cabinet/scripts/due-at-reminder-tick.sh`, which claims due rows and fires a
`task_reminder` to the **owning officer's** Redis stream. A **Captain** reminder
has no officer stream, so the Captain-arm routes it to the Captain's one-tap
card surface (the needs ledger → the frontdoor briefing digest + attention
drain → the Captain's Telegram).

## The pieces

| Piece | What it does |
|---|---|
| `cabinet/scripts/remind-captain.sh` | CREATE: files one captain-owned `officer_tasks` reminder row (`type='reminder'`, `status='queue'`, a `due_at`). |
| `cabinet/scripts/captain-reminder-arm.py` | The organ: `parse-when`, `owner-slug`, `file-card`, `reconcile`. No DB — needs-ledger + when-parsing only. |
| `cabinet/scripts/due-at-reminder-tick.sh` | DELIVER: claims due rows → captain row → card; officer row → trigger (041 behavior). Then RECONCILE the Captain's verdicts every tick. |
| `cabinet/sql/042-tasks-reminder-kind.sql` | Widens `officer_tasks.type` to admit `'reminder'`. |
| `framework/env.py` `captain_slug()` | Resolves the captain owner slug (default `captain`; `CABINET_CAPTAIN_SLUG` / `instance/config/platform.yml: captain_slug`). |

## Create a Captain reminder (the Chair files it)

When the Captain says "remind me tomorrow at 9 to chase DG JUST", the Chair runs:

```
bash cabinet/scripts/remind-captain.sh <when> <text...> [--context SLUG]
```

`<when>` is one of — **and nothing else is guessed; ambiguity is refused loudly:**

| Form | Meaning |
|---|---|
| `2026-07-20T09:00` | ISO 8601, the **Captain's local** wall clock (DST-exact) |
| `2026-07-20T09:00:00Z` / `...+02:00` | ISO 8601, timezone-aware — used as given |
| `"today 09:00"` | today at 09:00 local (quote it, or pass as two tokens) |
| `"tomorrow 09:00"` | tomorrow at 09:00 local |
| `"monday 09:00"` | the **next** monday (`mon`..`sun` / full names) at 09:00 local |
| `+3d` / `+6h` / `+90m` | N days / hours / minutes from now (`N>0`) |

A **bare date** (`2026-07-20`, no time), a **past** instant, or any other string
is REFUSED with exit 2 and the grammar — the arm never guesses a time. The
`<text...>` is the reminder body; it is **untrusted** and is bound to the INSERT
as a `psql -v` value (never interpolated into SQL text). `<when>` may be one
quoted argument or the bare `day HH:MM` two-token form.

Local forms resolve through the Captain's timezone
(`framework.env.captain_timezone()`), so a reminder set for "tomorrow 09:00"
lands at the right instant across a DST boundary.

## Delivery + the Captain's verbs

When the row comes due, the tick files a one-tap card on the needs ledger. It
renders in the **🙋 NEEDS** leg of the frontdoor briefing digest and via the
attention drain to the Captain's Telegram (the sanctioned Captain-facing
surface; this is internal, not external comms). The card body leads with the
verb legend, then the due time, then the reminder text.

The Captain replies with the standard needs-binder verbs (the digest footer
shows the exact `NEED-<id>` to use):

| Verb | Reminder meaning | Mechanism |
|---|---|---|
| `grant NEED-<id>` | **done / acknowledged** | The tick's reconcile closes the need `granted` (mirrors `grant-apply.sh`'s mark phase). No refire. |
| `later NEED-<id>` (or `snooze`) | **remind me again in 7 days** | The binder snoozes the need 7d; the tick bumps the reminder's `due_at` by +7 days with ONE guarded `psql -v` UPDATE. The 041 re-arm trigger clears `reminder_fired_at` on the `due_at` change, so the card refires in 7 days. |
| `deny NEED-<id>: <why>` | **dismiss / drop** | The binder marks the need `denied` and suppresses re-files for 90 days. |

**Snooze semantics (no new state machine):** the bump UPDATE is *guarded* — it
only touches a still-overdue, already-fired row — so a card that stays snoozed
re-emits its task id every tick yet only the **first** bump lands (once `due_at`
is in the future the guard no longer matches). When it refires in 7 days the
card re-files onto the SAME `NEED-<id>` (a content fingerprint by task id), so
the count bumps rather than spawning a second card.

## Officer self-reminders (existing 041 path — build nothing)

An officer does **not** need `remind-captain.sh`. Any `officer_tasks` row with a
`due_at` already fires a `task_reminder` to the **owning officer's** Redis
stream on the tick — that is the Spec 041 behavior, unchanged. An officer files
a self-reminder by setting a `due_at` on one of their own task rows; the tick
delivers it to their stream (not a Captain card). `remind-captain.sh` is only
the Captain-surface sugar (owner = the captain slug, `type='reminder'`).

## Prerequisites

- **Migration 042 applied** — `remind-captain.sh` inserts `type='reminder'`,
  which the pre-042 `officer_tasks_type_check` rejects. It is registered in the
  `load-preset.sh` + `cabinet-bootstrap.sh` apply lists (cold-start applies it).
- **The needs plane is wired** — the card is filed only when
  `framework.authority.needs.needs_enabled()` is true (sovereign posture, or
  `CABINET_NEEDS_WIRED=1`, or the `instance/config/needs-wired` flag file).
  Dark ⇒ the card no-ops (a captain reminder never falls back to a trigger,
  since there is no captain officer stream). Officer reminders are unaffected.
- **The tick is scheduled** — the `due-at-reminder-tick` row in
  `cabinet/services.yml` (kind cron, every 300s) is the worker's clock;
  `cabinet/scripts/generate-plists.py` renders it to the launchd plist and the
  normal deploy path (`cabinet/scripts/deploy-mac.sh` / cabinet-bootstrap)
  installs it. Without the installed row, reminders never fire and verdicts
  never reconcile.

## Configuration

- `captain_slug` — the officer_tasks owner slug that marks a row as the
  Captain's. Default `captain` (the /tasks-ETL + events-schema convention, a
  role token — never a personal name). Override via `CABINET_CAPTAIN_SLUG` or
  `instance/config/platform.yml: captain_slug`. The create path and the tick
  resolve it the same way, so they always agree.
- `SNOOZE_DAYS` — the snooze/bump window (default 7, matching
  `framework.authority.needs.SNOOZE_DAYS`); env-overridable on the tick.

## Known residual

- **Immediate at-fire-time Telegram push** is not built. A due reminder surfaces
  through the existing briefing digest + attention drain (≈5-minute drain
  cadence; twice-daily briefing) — the sanctioned, pacing/quiet-hours-aware
  Captain surface. An ad-hoc DM at an arbitrary fire time would bypass that
  gating, so it is deliberately left to the existing surface rather than
  inventing a new comms path.
