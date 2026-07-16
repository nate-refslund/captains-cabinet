#!/usr/bin/env python3.12
"""captain-reminder-arm.py — the Captain surface for /tasks due-at reminders.

Spec 041 gave ``officer_tasks`` a ``due_at`` + the cron worker
``cabinet/scripts/due-at-reminder-tick.sh``, which claims due rows and
``trigger_send``s a ``task_reminder`` to the OWNING OFFICER's Redis stream. A
Captain reminder has no officer stream, so this organ routes it to the sanctioned
Captain one-tap surface: the needs ledger (``framework.authority.needs`` →
``shared/interfaces/needs-ledger.jsonl`` → the 🙋 NEEDS leg of the frontdoor
briefing digest + the attention drain → ``CAPTAIN_TELEGRAM_ID`` via the gated
``channel.send``). It is the sibling of ``memory-supersede-apply.py`` (both read
the needs ledger and file/close one-tap cards through the REAL needs API).

This module holds NO database access — every officer_tasks write is a bash
``psql -v`` statement in ``remind-captain.sh`` / ``due-at-reminder-tick.sh``
(mirroring ``my-tasks.sh``'s parameterization discipline). Here we only:
  * parse a deterministic ``<when>`` phrase into a UTC instant,
  * resolve the Captain owner slug (``framework.env.captain_slug``),
  * file / dedup the needs card,
  * reconcile Captain verdicts (grant/deny/later) back onto the reminder.

Subcommands:
  parse-when <when> [--now ISO] [--tz NAME]
      Prints the resolved UTC ISO instant, or exits 2 with the grammar on any
      ambiguity / a past time. Forms (documented in
      docs/runbooks/captain-reminders.md):
        * ISO 8601 datetime — ``2026-07-20T09:00`` (naive ⇒ Captain-local),
          ``2026-07-20T09:00:00Z`` / ``...+02:00`` (tz-aware ⇒ used as-is);
        * ``today HH:MM`` / ``tomorrow HH:MM`` (Captain-local wall clock);
        * ``<weekday> HH:MM`` (mon…sun / full names — the NEXT such weekday);
        * ``+Nd`` / ``+Nh`` / ``+Nm`` (N>0, absolute offset from now).
      A bare date, a past instant, or anything else is REFUSED loudly. Local
      forms resolve through zoneinfo(Captain timezone) so DST is exact. The
      ``<when>`` string is parsed by regex / ``fromisoformat`` only — never
      eval'd — and never reaches a shell or SQL.

  owner-slug
      Prints ``framework.env.captain_slug()`` — the officer_tasks owner slug
      that marks a row as the Captain's (default ``captain``, never a name).

  file-card --task-id N --due-at D    (reminder TITLE on STDIN)
      Files (or re-files) ONE needs card for reminder task N via
      ``needs.file_need``. ``action_type`` carries the task id
      (``captain-reminder:<N>``), so the content-fingerprint need id is stable
      per task: re-filing after a crash-before-mark is a count bump, never a
      second card. The untrusted title arrives on STDIN (newline / quote /
      ``$()`` safe — it never transits argv or a TSV field) and is stored as
      JSON ledger data, never executed. Prints the need id (empty when the
      needs plane is dark). Never raises.

  reconcile
      Reads the needs ledger and applies the Captain's verdicts to
      captain-reminder cards:
        * ``approved_pending_apply`` (binder ``grant`` = done/ack) → close the
          need ``granted`` (mirrors grant-apply.sh's mark phase);
        * ``snoozed`` (binder ``later`` = +7d) → print the reminder's task id
          (int-validated) on stdout so the tick bumps its ``due_at`` with ONE
          guarded ``psql -v`` UPDATE — the 041 re-arm trigger then clears
          reminder_fired_at so it refires. NO new state machine: the tick's
          UPDATE is guarded (overdue + already-fired only), so a still-snoozed
          card re-prints every tick yet only the first bump lands.
        A ``deny`` verdict needs no action here — the binder already suppresses
        re-files 90d (dismiss). Ids in the ledger are UNTRUSTED: the task id is
        ``int()``-validated before it is printed, and ``needs.mark`` fail-closes
        on an unknown id.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# The action_type prefix carrying the reminder's task id — ONE constant so the
# filer (file-card) and the reader (reconcile) can never drift.
ACTION_PREFIX = "captain-reminder:"

# Mirror the needs module's SNOOZE window so the tick's due_at bump and the
# binder's `later` snooze lapse together. Imported lazily-safe below.
DEFAULT_SNOOZE_DAYS = 7

_UTC = dt.timezone.utc

_WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}
_HHMM_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_OFFSET_RE = re.compile(r"^\+(\d{1,4})([dhm])$")

_GRAMMAR = (
    "supported <when> forms: 'YYYY-MM-DDTHH:MM' (Captain-local) or a tz-aware "
    "ISO instant ('...Z' / '...+02:00'); 'today HH:MM'; 'tomorrow HH:MM'; "
    "'<weekday> HH:MM' (mon..sun); '+Nd' / '+Nh' / '+Nm' (N>0). A bare date, "
    "a past time, or anything else is refused."
)


class WhenError(ValueError):
    """A when-phrase this parser refuses (ambiguous, malformed, or past)."""


# ---------------------------------------------------------------------------
# framework resolvers (lazy; a broken import degrades, never crashes the tick)
# ---------------------------------------------------------------------------

def _captain_slug() -> str:
    try:
        from framework.env import captain_slug
        return captain_slug()
    except Exception:  # noqa: BLE001 — never break the caller
        return "captain"


def _captain_tz() -> ZoneInfo:
    name = "Europe/Berlin"
    try:
        from framework.env import captain_timezone
        name = captain_timezone()
    except Exception:  # noqa: BLE001
        name = "Europe/Berlin"
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, Exception):  # noqa: BLE001 — UTC fail-safe
        try:
            return ZoneInfo("UTC")
        except Exception:  # noqa: BLE001
            return dt.timezone.utc  # type: ignore[return-value]


def _snooze_days() -> int:
    try:
        from framework.authority import needs
        return int(needs.SNOOZE_DAYS)
    except Exception:  # noqa: BLE001
        return DEFAULT_SNOOZE_DAYS


# ---------------------------------------------------------------------------
# when parser (deterministic; regex / fromisoformat only; DST-exact)
# ---------------------------------------------------------------------------

def _parse_hhmm(tok: str) -> tuple[int, int]:
    m = _HHMM_RE.match(tok)
    if not m:
        raise WhenError(f"'{tok}' is not a HH:MM time")
    return int(m.group(1)), int(m.group(2))


def _to_utc_iso(d: dt.datetime) -> str:
    return d.astimezone(_UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_when(when: str, *, now: dt.datetime, tz) -> dt.datetime:
    """Resolve ``when`` to an aware UTC datetime, or raise ``WhenError``.

    ``now`` is an aware datetime; ``tz`` is the Captain's zoneinfo for the
    wall-clock forms. The PAST check lives in the caller so callers that want
    the raw instant (tests) can opt out — but ``parse_when`` itself never
    guesses: an unrecognized shape raises."""
    raw = (when or "").strip()
    if not raw:
        raise WhenError("empty <when>")
    now = now.astimezone(_UTC)

    # +Nd / +Nh / +Nm — absolute offset from now (DST-agnostic by construction).
    m = _OFFSET_RE.match(raw.lower())
    if m:
        n = int(m.group(1))
        if n <= 0:
            raise WhenError("offset must be a positive whole number")
        unit = m.group(2)
        delta = {"d": dt.timedelta(days=n), "h": dt.timedelta(hours=n),
                 "m": dt.timedelta(minutes=n)}[unit]
        return now + delta

    parts = raw.split()
    # '<day> HH:MM' wall-clock forms, resolved in the Captain's timezone.
    if len(parts) == 2:
        head = parts[0].lower()
        hh, mm = _parse_hhmm(parts[1])
        local_now = now.astimezone(tz)
        if head == "today":
            day = local_now.date()
        elif head == "tomorrow":
            day = local_now.date() + dt.timedelta(days=1)
        elif head in _WEEKDAYS:
            days_ahead = (_WEEKDAYS[head] - local_now.weekday()) % 7
            day = local_now.date() + dt.timedelta(days=days_ahead)
        else:
            raise WhenError(f"'{parts[0]}' is not today/tomorrow/a weekday")
        local_dt = dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz)
        result = local_dt.astimezone(_UTC)
        # A weekday whose time already passed today means NEXT week's occurrence
        # (never today-in-the-past); today/tomorrow keep their literal day (a
        # past 'today HH:MM' is then refused by the caller's PAST check).
        if head in _WEEKDAYS and result <= now:
            result = (local_dt + dt.timedelta(days=7)).astimezone(_UTC)
        return result

    # ISO 8601 datetime (single token, MUST carry a time — a bare date is
    # ambiguous and refused).
    if len(parts) == 1 and "t" in raw.lower():
        iso = raw.replace("Z", "+00:00").replace("z", "+00:00")
        try:
            d = dt.datetime.fromisoformat(iso)
        except ValueError:
            raise WhenError(f"'{raw}' is not a parseable ISO 8601 datetime")
        if d.tzinfo is None:
            d = d.replace(tzinfo=tz)  # naive ⇒ Captain-local wall clock
        return d.astimezone(_UTC)

    raise WhenError(f"'{raw}' is ambiguous or unrecognized")


def _cmd_parse_when(args) -> int:
    tz = ZoneInfo(args.tz) if args.tz else _captain_tz()
    if args.now:
        try:
            now = dt.datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        except ValueError:
            print(f"REFUSED: --now '{args.now}' is not ISO 8601", file=sys.stderr)
            return 2
        if now.tzinfo is None:
            now = now.replace(tzinfo=_UTC)
    else:
        now = dt.datetime.now(_UTC)
    try:
        result = parse_when(args.when, now=now, tz=tz)
    except WhenError as e:
        print(f"REFUSED: {e}. {_GRAMMAR}", file=sys.stderr)
        return 2
    if result <= now.astimezone(_UTC):
        print(f"REFUSED: {_to_utc_iso(result)} is in the past — a reminder "
              "must be in the future", file=sys.stderr)
        return 2
    print(_to_utc_iso(result))
    return 0


# ---------------------------------------------------------------------------
# owner slug
# ---------------------------------------------------------------------------

def _cmd_owner_slug(_args) -> int:
    print(_captain_slug())
    return 0


# ---------------------------------------------------------------------------
# file-card — one Captain one-tap card per reminder (fingerprint-deduped)
# ---------------------------------------------------------------------------

def _local_display(due_iso: str, tz) -> str:
    try:
        d = dt.datetime.fromisoformat(str(due_iso).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=_UTC)
        return d.astimezone(tz).strftime("%a %Y-%m-%d %H:%M")
    except Exception:  # noqa: BLE001 — fall back to the raw instant
        return str(due_iso)


def build_card_why(task_id: int, due_iso: str, title: str, tz) -> str:
    """The card body: the binder verb legend FIRST (so the 160-char digest clip
    never eats it), then WHEN, then WHAT (the untrusted title, stored as data).
    No U+00B7 — the needs writer strips it (pid-marker defense), so a '·'
    separator would silently vanish."""
    due_disp = _local_display(due_iso, tz)
    title = (title or "").strip() or "(no text)"
    return (f"grant = done / later = remind me in {_snooze_days()}d / "
            f"deny = drop — reminder due {due_disp}: {title}")


def file_card(task_id: int, due_iso: str, title: str, *,
              file_need_fn=None, tz=None) -> Optional[str]:
    """File one needs card for reminder ``task_id``; return the need id or None.

    Never raises (mirrors needs.file_need's own contract). The need id is a
    content fingerprint over (kind, risk_class, action_type, lane, cabinet_id)
    — action_type = ``captain-reminder:<task_id>`` — so every re-file for the
    same task lands on the SAME id and only bumps count (one card per task)."""
    tz = tz or _captain_tz()
    why = build_card_why(task_id, due_iso, title, tz)
    try:
        if file_need_fn is None:
            from framework.authority import needs
            file_need_fn = needs.file_need
        return file_need_fn(
            "decision",
            action_type=f"{ACTION_PREFIX}{task_id}",
            why=why,
            unblocks="the Captain sees and clears this reminder",
            cost_of_delay="medium",
            filed_by="system:captain-reminder",
            cid=str(task_id))
    except Exception:  # noqa: BLE001 — a card must never break the tick
        return None


def _cmd_file_card(args) -> int:
    try:
        task_id = int(args.task_id)
    except (TypeError, ValueError):
        print(f"REFUSED: --task-id '{args.task_id}' is not an integer",
              file=sys.stderr)
        return 2
    title = sys.stdin.buffer.read().decode("utf-8", "replace")
    nid = file_card(task_id, args.due_at or "", title)
    if nid:
        print(nid)
    return 0


# ---------------------------------------------------------------------------
# reconcile — apply the Captain's verdicts to captain-reminder cards
# ---------------------------------------------------------------------------

def reconcile(*, merged_needs=None, mark_fn=None, out=None) -> dict:
    """Close acked cards + emit snooze task ids. Returns a summary dict.

    ``merged_needs`` (id→row) and ``mark_fn`` are injectable for tests;
    production reads the REAL needs ledger and calls ``needs.mark``. Snooze
    task ids are printed (one per line) to ``out`` (default stdout) for the
    tick to bump. Never raises."""
    out = out or sys.stdout
    summary = {"closed": 0, "snoozed": 0, "skipped": 0}
    try:
        from framework.authority import needs
        if merged_needs is None:
            merged_needs = needs._merged(needs.ledger_path())
        if mark_fn is None:
            mark_fn = needs.mark
    except Exception:  # noqa: BLE001 — no ledger ⇒ nothing to reconcile
        return summary

    for nid, row in (merged_needs or {}).items():
        if not isinstance(row, dict):
            continue
        action = str(row.get("action_type") or "")
        if not action.startswith(ACTION_PREFIX):
            continue
        status = str(row.get("status") or "")
        if status == "approved_pending_apply":
            # done/ack — mirror grant-apply.sh's mark phase (close the need).
            try:
                if mark_fn(str(nid), "granted", by="system:captain-reminder",
                           reason="reminder acknowledged (grant = done)"):
                    summary["closed"] += 1
            except Exception:  # noqa: BLE001 — a receipt must not break the pass
                summary["skipped"] += 1
        elif status == "snoozed":
            # later — the tick bumps due_at; the 041 re-arm trigger refires it.
            tail = action[len(ACTION_PREFIX):]
            try:
                task_id = int(tail)          # UNTRUSTED ledger text → int gate
            except (TypeError, ValueError):
                summary["skipped"] += 1
                continue
            print(task_id, file=out)
            summary["snoozed"] += 1
    return summary


def _cmd_reconcile(_args) -> int:
    summary = reconcile()
    print(f"[captain-reminder-arm] reconcile closed={summary['closed']} "
          f"snoozed={summary['snoozed']} skipped={summary['skipped']}",
          file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Captain surface for /tasks due-at reminders "
                    "(needs-ledger one-tap cards + verdict reconcile).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_when = sub.add_parser("parse-when", help="resolve a <when> phrase to UTC")
    p_when.add_argument("when")
    p_when.add_argument("--now", help="reference now (ISO; tests)")
    p_when.add_argument("--tz", help="override Captain timezone (tests)")
    p_when.set_defaults(func=_cmd_parse_when)

    p_owner = sub.add_parser("owner-slug", help="print the Captain owner slug")
    p_owner.set_defaults(func=_cmd_owner_slug)

    p_card = sub.add_parser("file-card", help="file one reminder card (title on stdin)")
    p_card.add_argument("--task-id", required=True)
    p_card.add_argument("--due-at", required=True)
    p_card.set_defaults(func=_cmd_file_card)

    p_rec = sub.add_parser("reconcile", help="apply Captain verdicts to cards")
    p_rec.set_defaults(func=_cmd_reconcile)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
