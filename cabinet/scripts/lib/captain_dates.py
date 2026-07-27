#!/usr/bin/env python3.12
"""captain_dates.py — the dates the Captain set, from his phone.

A DATE HE SETS MUST BE IMPOSSIBLE FOR THE ORG TO FORGET::

    date 2026-08-13 board review     put a dated commitment on the org's books
    dates                            what is still open, with countdowns
    date done board                  close one (id or label prefix)
    date move board 2026-09-01       change the date, keeping the history

WHY IT EXISTS (Captain-Seat dry run, 2026-07-26 — finding 1). The Captain set a
release date. It appeared in ZERO of the next twelve days of briefings, because
nothing in the org held it: the briefing rendered commitments he owed OTHER
people (from the personal-source adapter) and dated follow-ups the ORG wrote
down, and a date HE declared had no store, no resolver and no reader at all. The
cost was his: he had to remember, and re-say, something he had already said once.

CAPTAIN-DECLARED INPUT, NEVER A PERFORMANCE NUMBER. These rows are things the
Captain typed about HIS OWN calendar. Nothing here is derived from evidence,
nothing here is about an officer, and no consumer may render any of it as an
officer-visible measure of anyone. A countdown is a REMINDER, never a score.

WHERE THE DATA LIVES — and why it survives a deploy.
``instance/config/captain-dates.yml``, appended to, latest row per id wins. The
path is owned by ``framework.env.captain_dates_path()`` (the same resolver every
reader uses, so writer and readers cannot drift), the file is gitignored as a
captain-specific declaration, listed in ``runtime-provision.sh``'s
``INSTANCE_PERSISTENT_FILES`` so a deploy/rollback never drops a date he set,
and deleted by the egg export (a fresh cabinet starts with no dates).

APPEND-ONLY. ``done`` and ``move`` APPEND a row rather than editing one, so the
history of what he said and when stays readable. A ``move`` writes TWO rows: the
old id goes ``moved``, and a fresh id carries the new date with ``supersedes``
naming the row it replaced. His verbatim text rides along as an inert COMMENT
line — provenance without letting a whole message become a value. The one field
that IS his free text (``label``) is sanitized and length-capped at this writer
and written as a QUOTED scalar, because it is the string the briefing prints.

PHONE PATH (the control he actually uses — no terminal, per the 2026-07-17
captain-controls ruling): ``cabinet/scripts/officer-inbound-poller.py`` answers
the verb mechanically from its own process, the same shape as ``/killswitch``,
``/score`` and ``availability``, and falls OPEN to the Chair relay if anything
here raises — a real message is never silently eaten. A SELECTOR that matches
nothing or matches several rows is NOT an error: he gets a precise mechanical
answer naming the open dates, because "refuse, don't guess" beats closing the
wrong date.

CLI (one command each way)::

    python3.12 cabinet/scripts/lib/captain_dates.py add 2026-08-13 "board review"
    python3.12 cabinet/scripts/lib/captain_dates.py reply "date done board"
    python3.12 cabinet/scripts/lib/captain_dates.py list

TEST FENCE: ``CABINET_CAPTAIN_DATES_FILE`` relocates the store. The repo-root
``conftest.py`` sets it into the pytest session sandbox, so no test run can write
the live store — fenced at birth, exactly like
``CABINET_CAPTAIN_AVAILABILITY_FILE`` before it. A fabricated row here would put
a deadline nobody declared in front of the Captain twice a day; a deleted one
would reproduce the very failure this store exists to prevent.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

#: Row schema tag. Bump only with a reader that handles both.
SCHEMA = "cabinet.captain-dates/v1"

#: The store, relative to the repo root (the resolver owns the real path).
STORE_REL = "instance/config/captain-dates.yml"

#: Provenance comment cap. Notes are a memory aid, not a corpus.
TEXT_MAX = 200

#: Calendar sanity bounds. Outside these a "date" is a typo, not a ruling, and
#: is REFUSED rather than stored — the same refuse-don't-repair rule the
#: availability dial applies to an out-of-range minute count. Deliberately
#: clock-free (a bound relative to "now" would make the grammar time-dependent,
#: and a rolling window plus a fixed date is a calendar time-bomb).
YEAR_MIN = 2000
YEAR_MAX = 2100


def repo_root() -> Path:
    """CABINET_ROOT wins, else this file's repo (cabinet/scripts/lib/…)."""
    root = os.environ.get("CABINET_ROOT", "").strip()
    return Path(root) if root else Path(__file__).resolve().parents[3]


def _env():
    """``framework.env`` — THE canonical store path, status enum and line shape.

    Imported late, with the repo root on ``sys.path``, so this lib stays
    importable the way the poller imports it (``sys.path`` gets
    ``cabinet/scripts/lib``, not the repo root). Deliberately NOT wrapped in a
    fallback copy of the enum or the renderer: a second copy would drift, and a
    date rendered two different ways is how one goes unnoticed."""
    root = str(repo_root())
    if root not in sys.path:
        sys.path.insert(0, root)
    from framework import env  # noqa: PLC0415 — deliberate late import
    return env


def store_path() -> Path:
    return _env().captain_dates_path()


# --------------------------------------------------------------------------
# the phone grammar
# --------------------------------------------------------------------------
#: ``dates`` / ``dates?`` — the list verb. ANCHORED AT BOTH ENDS (``re.match``
#: plus a redundant leading ``^`` and a trailing ``$``), so "dates are hard"
#: matches nothing and relays to the Chair untouched.
_LIST_RE = re.compile(r"^\s*/?dates(?:@\w{1,64})?\s*\??\s*$", re.IGNORECASE)

#: ``[/]date <arg>`` — the write verbs. Same both-ends anchoring as
#: ``captain_availability._CMD_RE`` and for the same reason, re-measured by a
#: guard-mutation sweep at authoring time (2026-07-27): neither ``^`` alone nor
#: ``match`` alone is falsifiable — each is sufficient, so only removing the PAIR
#: turns a test red — and it is the PREFIXED case ("so date 2026-08-13 x") that
#: tests the start anchor at all, since the tail anchor and the argument shape
#: both accept it. Both arms are pinned by
#: ``tests/test_captain_dates.py::test_grammar_refuses_what_he_did_not_mean``. The
#: leading slash is OPTIONAL because the Captain types the word, not a command;
#: the ARGUMENT grammar below does the rest of the work.
_CMD_RE = re.compile(r"^\s*/?dates?(?:@\w{1,64})?[\s:]+(?P<arg>\S.*?)\s*$",
                     re.IGNORECASE)

_QUERY_RE = re.compile(r"^\?+$")
_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
#: ``done <selector>`` — the selector may contain spaces (a label prefix), so it
#: takes the rest of the line. It is only ever MATCHED against, never written.
_DONE_RE = re.compile(r"^done[\s:]+(?P<sel>\S.*?)\s*$", re.IGNORECASE)
#: ``move <selector> <ISO>`` — the ISO date is the LAST token, which anchors the
#: tail and lets the selector keep its spaces without ambiguity.
_MOVE_RE = re.compile(
    r"^move[\s:]+(?P<sel>\S.*?)[\s:]+(?P<date>\d{4}-\d{2}-\d{2})\s*$",
    re.IGNORECASE)
#: ``<ISO> <label>`` — the add arm. A label is REQUIRED: a bare date is not
#: actionable ("what is it?"), so it returns None and relays rather than storing
#: a row nothing can render.
_ADD_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})[\s:]+(?P<label>\S.*?)\s*$")


def parse_date_value(text) -> "str | None":
    """``YYYY-MM-DD`` → a real calendar date string, else None (never repaired).

    ``2026-02-31`` and ``0226-08-13`` are refused rather than snapped to a
    nearby day: a date the store cannot represent must come back to him."""
    if not isinstance(text, str):
        return None
    m = _ISO_RE.match(text.strip())
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not YEAR_MIN <= y <= YEAR_MAX:
        return None
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def parse_dates_command(text: str) -> "dict | None":
    """``date …`` / ``dates`` → a parsed command, else None.

    Returns one of::

        {"kind": "list"}
        {"kind": "add",  "date": iso, "label": str, "text": verbatim}
        {"kind": "done", "selector": str,           "text": verbatim}
        {"kind": "move", "selector": str, "date": iso, "text": verbatim}

    None means "not a dates command" — every caller must then fall through to
    its normal path. Refusing loudly here would eat a real message."""
    raw = text or ""
    if _LIST_RE.match(raw):
        return {"kind": "list"}
    m = _CMD_RE.match(raw)
    if not m:
        return None
    arg = m.group("arg").strip()
    verbatim = raw.strip()[:TEXT_MAX]

    if _QUERY_RE.match(arg):
        return {"kind": "list"}

    mv = _MOVE_RE.match(arg)
    if mv:
        when = parse_date_value(mv.group("date"))
        if when is None:
            return None                 # an impossible date: relay, never round
        return {"kind": "move", "selector": mv.group("sel").strip(),
                "date": when, "text": verbatim}

    dn = _DONE_RE.match(arg)
    if dn:
        return {"kind": "done", "selector": dn.group("sel").strip(),
                "text": verbatim}

    ad = _ADD_RE.match(arg)
    if ad:
        when = parse_date_value(ad.group("date"))
        if when is None:
            return None
        label = sanitize_label(ad.group("label"))
        if not label:
            return None
        return {"kind": "add", "date": when, "label": label, "text": verbatim}

    return None                          # unknown shape → the Chair relays it


# --------------------------------------------------------------------------
# write
# --------------------------------------------------------------------------
def _comment_safe(text: str) -> str:
    """One inert comment line: newlines and control chars flattened, capped.
    A comment can carry his words without them ever becoming a VALUE."""
    flat = re.sub(r"[\x00-\x1f\x7f]+", " ", str(text or "")).strip()
    return flat[:TEXT_MAX]


def sanitize_label(text) -> str:
    """His words as the ONE field that is a value — made safe, never guessed at.

    Control characters (a newline above all) are flattened to spaces so a
    message can never become a second YAML line, runs of whitespace collapse,
    and the result is capped at ``framework.env.CAPTAIN_DATE_LABEL_MAX``. The
    text is not otherwise altered: it is what he called the thing, and the
    briefing prints it back to him verbatim."""
    flat = re.sub(r"[\x00-\x1f\x7f]+", " ", str(text or ""))
    flat = re.sub(r"\s+", " ", flat).strip()
    return flat[:_env().CAPTAIN_DATE_LABEL_MAX]


def _yaml_dq(text: str) -> str:
    """A YAML double-quoted scalar. Backslash and quote escaped, control chars
    already gone via ``sanitize_label`` — so a label can never terminate its own
    scalar and start a new key."""
    body = str(text or "").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{body}"'


def mint_id(when: str, label: str, stamp: str) -> str:
    """A short, stable, greppable handle: ``d-<8 hex>`` over the row's own
    content. Content-derived so re-sending the identical add in the same second
    folds onto the same row (idempotent) instead of creating a twin, and so no
    counter has to be persisted anywhere."""
    blob = f"{when}\x1f{label}\x1f{stamp}".encode("utf-8")
    return "d-" + hashlib.sha256(blob).hexdigest()[:8]


def _stamp(now: "datetime | None" = None) -> str:
    at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return at.strftime("%Y-%m-%dT%H:%M:%SZ")


def _append(rows: "list[dict]", *, text: str = "",
            path: "Path | None" = None) -> None:
    """Append fixed-shape blocks. NOT a YAML re-dump: re-dumping would drop
    every comment in the file, including the provenance lines that are the only
    record of what he actually typed."""
    target = Path(path) if path is not None else store_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    header = ""
    if not target.exists() or not target.read_text(encoding="utf-8").strip():
        header = (
            "# captain-dates.yml — dates the Captain set, on the org's books.\n"
            "# MACHINE-WRITTEN (cabinet/scripts/lib/captain_dates.py);\n"
            "# append-only, LATEST ROW PER id WINS. Read by\n"
            "# framework.env.captain_dates(). Every open row rides every\n"
            "# briefing until he says done or move.\n"
            f"schema: {SCHEMA}\n"
            "entries:\n")
    note = _comment_safe(text)
    block = ""
    if note:
        block += f"  # captain text: {note}\n"
    for row in rows:
        block += (f"  - id: {row['id']}\n"
                  f"    at: {row['at']}\n"
                  f"    date: {row['date']}\n"
                  f"    label: {_yaml_dq(row['label'])}\n"
                  f"    status: {row['status']}\n"
                  f"    source: {row['source']}\n")
        if row.get("supersedes"):
            block += f"    supersedes: {row['supersedes']}\n"
    with open(target, "a", encoding="utf-8") as fh:
        if header:
            fh.write(header)
        fh.write(block)
        fh.flush()
        os.fsync(fh.fileno())


def _row(rid: str, when: str, label: str, status: str, stamp: str,
         source: str, supersedes: "str | None" = None) -> dict:
    row = {"id": rid, "at": stamp, "date": when, "label": label,
           "status": status, "source": source}
    if supersedes:
        row["supersedes"] = supersedes
    return row


def record_add(when: str, label: str, *, source: str = "telegram",
               text: str = "", now: "datetime | None" = None,
               path: "Path | None" = None) -> dict:
    """Append ONE open date. Returns the row written."""
    env = _env()
    iso = parse_date_value(when)
    if iso is None:
        raise ValueError(f"date must be a real YYYY-MM-DD in "
                         f"{YEAR_MIN}..{YEAR_MAX}, got {when!r}")
    clean = sanitize_label(label)
    if not clean:
        raise ValueError("label must be non-empty — a date with no label is "
                         "not something the briefing can render")
    stamp = _stamp(now)
    row = _row(mint_id(iso, clean, stamp), iso, clean, "open", stamp, source)
    _append([row], text=text, path=path)
    env._captain_dates_cache = None
    return row


def record_done(row: dict, *, source: str = "telegram", text: str = "",
                now: "datetime | None" = None,
                path: "Path | None" = None) -> dict:
    """Append a ``done`` row for an existing id (history preserved)."""
    env = _env()
    stamp = _stamp(now)
    out = _row(row["id"], row["date"], row["label"], "done", stamp, source,
               row.get("supersedes"))
    _append([out], text=text, path=path)
    env._captain_dates_cache = None
    return out


def record_move(row: dict, when: str, *, source: str = "telegram",
                text: str = "", now: "datetime | None" = None,
                path: "Path | None" = None) -> dict:
    """Move a date: the old id goes ``moved``, a NEW id carries the new date and
    names the row it replaced. Returns the NEW row.

    Two rows, not an edit, because the question "what did he originally say, and
    when did it change?" has to stay answerable — a move that overwrote the date
    would erase exactly the evidence a Captain-seat review needs."""
    env = _env()
    iso = parse_date_value(when)
    if iso is None:
        raise ValueError(f"date must be a real YYYY-MM-DD in "
                         f"{YEAR_MIN}..{YEAR_MAX}, got {when!r}")
    stamp = _stamp(now)
    old = _row(row["id"], row["date"], row["label"], "moved", stamp, source,
               row.get("supersedes"))
    new = _row(mint_id(iso, row["label"], stamp), iso, row["label"], "open",
               stamp, source, supersedes=row["id"])
    _append([old, new], text=text, path=path)
    env._captain_dates_cache = None
    return new


# --------------------------------------------------------------------------
# read
# --------------------------------------------------------------------------
def current(reset_cache: bool = True) -> list:
    """The rows THE RESOLVER produces — never a second parse of the store.

    ``reset_cache`` clears the resolver's process-wide cache first, because a
    long-lived poller process would otherwise keep answering with what it read
    at boot, minutes after he added a date."""
    env = _env()
    if reset_cache:
        env._captain_dates_cache = None
    return env.captain_dates()


def open_dates(reset_cache: bool = True) -> list:
    """The OPEN rows only, soonest first."""
    return [r for r in current(reset_cache) if r.get("status") == "open"]


class Ambiguous(LookupError):
    """A selector matched more than one open date — refuse, never guess which
    one he meant. Carries the candidates so the reply can name them."""

    def __init__(self, matches: list):
        self.matches = matches
        super().__init__(f"{len(matches)} open dates match")


class NoMatch(LookupError):
    """A selector matched no OPEN date. ``closed`` carries a same-selector match
    among the done/moved rows, so the reply can say "already closed" instead of
    the useless "nothing found"."""

    def __init__(self, selector: str, closed: "dict | None" = None):
        self.selector = selector
        self.closed = closed
        super().__init__(f"no open date matches {selector!r}")


def _matches(rows: list, selector: str) -> list:
    """Rows whose id or label STARTS WITH the selector (case-insensitive).

    Prefix, not substring: a prefix is what he can retype from a briefing line,
    and it keeps "b" from matching every label with a b in it."""
    want = (selector or "").strip().lower()
    if not want:
        return []
    out = []
    for r in rows:
        rid = str(r.get("id") or "").lower()
        label = str(r.get("label") or "").lower()
        if rid.startswith(want) or label.startswith(want):
            out.append(r)
    return out


def resolve(selector: str, rows: "list | None" = None) -> dict:
    """The ONE open date a selector names, or raise (never a silent pick)."""
    all_rows = current() if rows is None else rows
    hits = _matches([r for r in all_rows if r.get("status") == "open"], selector)
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise Ambiguous(hits)
    closed = _matches([r for r in all_rows if r.get("status") != "open"],
                      selector)
    raise NoMatch(selector, closed[0] if closed else None)


def render_open(rows: "list | None" = None, *,
                today: "str | None" = None) -> str:
    """The phone-sized answer to ``dates``.

    ZERO open dates renders as "no dates set" — never an empty header and never
    a placeholder row: an invented date is worse than an honest absence."""
    env = _env()
    live = open_dates() if rows is None else rows
    if not live:
        return ("No dates set — the cabinet is holding none of your dates. "
                "Reply e.g. 'date 2026-08-13 board review'.")
    lines = [f"Dates you set ({len(live)} open):"]
    for r in live:
        lines.append(f"• {env.render_captain_date(r, today=today)}  [{r['id']}]")
    lines.append("Reply 'date done <id or label>' to close one, or "
                 "'date move <id or label> <YYYY-MM-DD>' to change it.")
    return "\n".join(lines)


def render_miss(exc: LookupError, rows: "list | None" = None, *,
                today: "str | None" = None) -> str:
    """The mechanical answer when a selector does not resolve. He always gets a
    reply naming the real open dates — a silent no-op would leave him believing
    a date was closed when it was not."""
    if isinstance(exc, Ambiguous):
        ids = ", ".join(str(r.get("id")) for r in exc.matches)
        return ("That matches more than one open date — nothing changed. "
                f"Reply with one of: {ids}")
    closed = getattr(exc, "closed", None)
    if closed is not None:
        return (f"'{closed['label']}' is already {closed['status']} "
                f"({closed['date']}) — nothing changed.")
    return ("Nothing open matches that — nothing changed.\n"
            + render_open(rows, today=today))


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def apply_command(parsed: dict, source: str) -> "tuple[int, str]":
    """One parsed command → (exit code, message). Shared by the CLI and the
    poller's reply path so the phone and the terminal cannot diverge."""
    kind = parsed["kind"]
    if kind == "list":
        return 0, render_open()
    if kind == "add":
        row = record_add(parsed["date"], parsed["label"], source=source,
                         text=parsed.get("text", ""))
        return 0, (f"Date set: {row['label']} — {row['date']}  [{row['id']}]\n"
                   "It rides every briefing until you reply 'date done' or "
                   "'date move'.")
    try:
        row = resolve(parsed["selector"])
    except LookupError as exc:
        return 0, render_miss(exc)
    if kind == "done":
        out = record_done(row, source=source, text=parsed.get("text", ""))
        return 0, f"Closed: {out['label']} — {out['date']}  [{out['id']}]"
    out = record_move(row, parsed["date"], source=source,
                      text=parsed.get("text", ""))
    return 0, (f"Moved: {out['label']} — was {row['date']}, now {out['date']}  "
               f"[{out['id']}]\nThe old row is kept as history.")


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(
        prog="captain_dates.py",
        description="Record and show the dates the Captain set.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="record one date (YYYY-MM-DD + label)")
    p_add.add_argument("date")
    p_add.add_argument("label", nargs="+")
    p_add.add_argument("--source", default="cli")

    p_done = sub.add_parser("done", help="close one date (id or label prefix)")
    p_done.add_argument("selector", nargs="+")
    p_done.add_argument("--source", default="cli")

    p_move = sub.add_parser("move", help="change one date, keeping history")
    p_move.add_argument("selector")
    p_move.add_argument("date")
    p_move.add_argument("--source", default="cli")

    p_reply = sub.add_parser(
        "reply", help="record from a raw 'date …' / 'dates' reply")
    p_reply.add_argument("text")
    p_reply.add_argument("--source", default="reply")

    sub.add_parser("list", help="the open dates, soonest first")

    a = ap.parse_args(argv)

    if a.cmd == "list":
        print(render_open())
        return 0
    if a.cmd == "add":
        text = f"date {a.date} {' '.join(a.label)}"
    elif a.cmd == "done":
        text = f"date done {' '.join(a.selector)}"
    elif a.cmd == "move":
        text = f"date move {a.selector} {a.date}"
    else:
        text = a.text

    parsed = parse_dates_command(text)
    if parsed is None:
        print("not a dates command — expected e.g. "
              "'date 2026-08-13 board review', 'dates', "
              "'date done board' or 'date move board 2026-09-01'",
              file=sys.stderr)
        return 2
    code, msg = apply_command(parsed, a.source)
    print(msg)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
