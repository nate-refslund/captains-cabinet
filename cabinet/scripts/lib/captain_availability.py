#!/usr/bin/env python3.12
"""captain_availability.py — the Captain's availability dial, from his phone.

ONE NUMBER, HIS. How much of his day this cabinet is entitled to::

    availability 20m            20 minutes a day
    availability 2h             two hours a day
    availability part_time      a band (away | minimal | part_time |
                                substantial | full_time)
    availability away           nothing but a genuine emergency
    availability ?              what does the org currently think?

WHY IT EXISTS (Captain ruling 2026-07-26). The org had no time-budget input at
all. Availability handling was two hand-parked service rows; twice-daily
briefings ran through a declared month-long absence, and 146 proactive cards
chased 2 approvals. The dial makes the budget a first-class value: **the org
fits the declared budget, never the reverse.** Overflow routes through the
act-with-undo seam with receipts instead of piling up as asks, and silence
still never means approval (constitution D12 unchanged).

CAPTAIN-DECLARED INPUT, NEVER A PERFORMANCE NUMBER. This value is something the
Captain typed about HIMSELF. It is not derived from evidence, it is not about an
officer, and it may never be rendered as an officer-visible measure of anyone —
the same distinction the never-a-score law's own fixture draws for a value the
Captain typed. Consumers read it as a BUDGET (what may reach him), never as a
rating.

WHERE THE DATA LIVES — and why it survives a deploy.
``instance/config/captain-availability.yml``, appended to, latest valid row
wins. The path is owned by ``framework.env.captain_availability_path()`` (the
same resolver every reader uses, so writer and readers cannot drift), the file
is gitignored as a captain-specific declaration, listed in
``runtime-provision.sh``'s ``INSTANCE_PERSISTENT_FILES`` so a deploy/rollback
never resets his ruling, and deleted by the egg export (a fresh cabinet starts
UNKNOWN and asks at onboarding).

APPEND-ONLY. A re-dial appends; nothing rewrites or deletes a row, so the
history of what he said stays readable. His verbatim text rides along as an
inert COMMENT line — provenance without letting free text become a value.

PHONE PATH (the control he actually uses — no terminal, per the 2026-07-17
captain-controls ruling): ``cabinet/scripts/officer-inbound-poller.py`` answers
the verb mechanically from its own process, the same shape as ``/killswitch``
and ``/score``, and falls OPEN to the Chair relay if anything here raises — a
real message is never silently eaten.

CLI (one command each way)::

    python3.12 cabinet/scripts/lib/captain_availability.py set 20m
    python3.12 cabinet/scripts/lib/captain_availability.py reply "availability 2h"
    python3.12 cabinet/scripts/lib/captain_availability.py show

TEST FENCE: ``CABINET_CAPTAIN_AVAILABILITY_FILE`` relocates the store. The
repo-root ``conftest.py`` sets it into the pytest session sandbox, so no test
run can write the live declaration — fenced at birth, exactly like
``CABINET_BRIEFING_SCORES_DIR`` before it. A fabricated row here would not
pollute a log; it would tell the whole org it may spend time the Captain never
offered.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

#: Row schema tag. Bump only with a reader that handles both.
SCHEMA = "cabinet.captain-availability/v1"

#: The store, relative to the repo root (the resolver owns the real path).
STORE_REL = "instance/config/captain-availability.yml"

#: Provenance comment cap. Notes are a memory aid, not a corpus.
TEXT_MAX = 200


def repo_root() -> Path:
    """CABINET_ROOT wins, else this file's repo (cabinet/scripts/lib/…)."""
    root = os.environ.get("CABINET_ROOT", "").strip()
    return Path(root) if root else Path(__file__).resolve().parents[3]


def _env():
    """``framework.env`` — THE canonical mode table and store path.

    Imported late, with the repo root on ``sys.path``, so this lib stays
    importable the way the poller imports it (``sys.path`` gets
    ``cabinet/scripts/lib``, not the repo root). Deliberately NOT wrapped in a
    fallback copy of the table: a second copy of the bands would drift, and a
    drifted budget is worse than a verb that fails open to the Chair relay."""
    root = str(repo_root())
    if root not in sys.path:
        sys.path.insert(0, root)
    from framework import env  # noqa: PLC0415 — deliberate late import
    return env


def store_path() -> Path:
    return _env().captain_availability_path()


# --------------------------------------------------------------------------
# the phone grammar
# --------------------------------------------------------------------------
#: ``[/]availability <arg>`` — ANCHORED AT BOTH ENDS: ``re.match`` plus a
#: redundant leading ``^``, and a trailing ``\s*$`` after a MOST-TWO-TOKEN
#: argument. Measured by a mutation sweep at authoring time (2026-07-26), same
#: finding as ``SCORE_CMD_RE``: neither ``^`` alone nor ``match`` alone is
#: falsifiable — only the pair is, and it is the PREFIXED case ("so availability
#: 20m") that tests it, since the tail anchor already rejects a trailing
#: sentence. Both arms are pinned by
#: ``tests/test_captain_availability.py::test_grammar_refuses_what_he_did_not_mean``.
#: The leading slash is OPTIONAL because the Captain types the word, not a
#: command; the ARGUMENT grammar does the rest of the work — "availability is
#: worth discussing" matches no arm, returns None, and relays to the Chair
#: untouched.
#:
#: Arms, in order: a query (``?``), a duration (``20m`` / ``20 min`` / ``2h`` /
#: ``1.5 h`` / a bare integer read as minutes), or a mode verb (hyphen or
#: underscore). A FRACTIONAL MINUTE is deliberately unmatched rather than
#: rounded — the same refuse-don't-round rule /score applies to "3.5": a number
#: the dial cannot represent must come back to him, never be quietly changed.
_CMD_RE = re.compile(
    r"^\s*/?availability(?:@\w{1,64})?[\s:]+(?P<arg>\S+(?:\s+\S+)?)\s*$",
    re.IGNORECASE)
_QUERY_RE = re.compile(r"^\?+$")
_DURATION_RE = re.compile(
    r"^(?P<n>\d{1,5}(?:[.,]\d{1,2})?)\s*(?P<unit>h|hr|hrs|hour|hours|m|min|mins|minute|minutes)?$",
    re.IGNORECASE)


def _parse_duration(arg: str) -> "int | None":
    """``20m`` / ``2h`` / ``90`` → minutes/day, else None (never rounded)."""
    m = _DURATION_RE.match(arg.strip())
    if not m:
        return None
    unit = (m.group("unit") or "m").lower()
    raw = m.group("n").replace(",", ".")
    try:
        value = float(raw)
    except ValueError:
        return None
    if unit.startswith("h"):
        minutes = value * 60
    else:
        minutes = value
    if not float(minutes).is_integer():
        return None                     # refuse, don't round — he retypes it
    minutes = int(minutes)
    env = _env()
    if not 0 <= minutes <= env.AVAILABILITY_MAX_MINUTES:
        return None                     # a typo, not a ruling
    return minutes


def parse_availability_command(text: str) -> "dict | None":
    """``availability <arg>`` → a parsed command, else None.

    Returns ``{"kind": "query"}`` or ``{"kind": "set", "minutes_per_day": int,
    "mode": str|None, "text": <verbatim, trimmed>}``. None means "not an
    availability command" — every caller must then fall through to its normal
    path. Refusing loudly here would eat a real message."""
    m = _CMD_RE.match(text or "")
    if not m:
        return None
    arg = m.group("arg").strip()
    if _QUERY_RE.match(arg):
        return {"kind": "query"}
    verbatim = (text or "").strip()[:TEXT_MAX]
    minutes = _parse_duration(arg)
    if minutes is not None:
        env = _env()
        return {"kind": "set", "minutes_per_day": minutes,
                "mode": env.availability_mode_for_minutes(minutes),
                "text": verbatim}
    verb = arg.strip().lower().replace("-", "_")
    env = _env()
    band = env.availability_minutes_for_mode(verb)
    if band is None:
        return None                     # unknown word → the Chair relays it
    return {"kind": "set", "minutes_per_day": band, "mode": verb,
            "text": verbatim}


# --------------------------------------------------------------------------
# write
# --------------------------------------------------------------------------
def _comment_safe(text: str) -> str:
    """One inert comment line: newlines and control chars flattened, capped.
    A comment can carry his words without them ever becoming a VALUE."""
    flat = re.sub(r"[\x00-\x1f\x7f]+", " ", str(text or "")).strip()
    return flat[:TEXT_MAX]


def record(minutes_per_day: int, *, mode: "str | None" = None,
           source: str = "telegram", text: str = "",
           now: "datetime | None" = None,
           path: "Path | None" = None) -> dict:
    """Append ONE availability entry. Returns the entry written.

    The write is a plain append of a fixed-shape block, not a YAML re-dump:
    re-dumping would drop every comment in the file, including the provenance
    lines that are the only record of what he actually typed."""
    env = _env()
    if isinstance(minutes_per_day, bool):
        raise ValueError("minutes_per_day must be an int, got a bool")
    minutes = int(minutes_per_day)
    if not 0 <= minutes <= env.AVAILABILITY_MAX_MINUTES:
        raise ValueError(
            f"minutes_per_day must be 0..{env.AVAILABILITY_MAX_MINUTES}, "
            f"got {minutes_per_day!r}")
    if mode is not None and env.availability_minutes_for_mode(mode) is None:
        raise ValueError(f"mode must be one of {env.availability_modes()}, "
                         f"got {mode!r}")
    if mode is None:
        mode = env.availability_mode_for_minutes(minutes)
    at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    stamp = at.strftime("%Y-%m-%dT%H:%M:%SZ")
    target = Path(path) if path is not None else store_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    header = ""
    if not target.exists() or not target.read_text(encoding="utf-8").strip():
        header = (
            "# captain-availability.yml — the Captain's declared time budget.\n"
            "# MACHINE-WRITTEN (cabinet/scripts/lib/captain_availability.py);\n"
            "# append-only, latest valid entry wins. Read by\n"
            "# framework.env.captain_availability(). The org fits the declared\n"
            "# budget, never the reverse.\n"
            f"schema: {SCHEMA}\n"
            "entries:\n")
    note = _comment_safe(text)
    block = ""
    if note:
        block += f"  # captain text: {note}\n"
    block += (f"  - at: {stamp}\n"
              f"    minutes_per_day: {minutes}\n"
              f"    mode: {mode}\n"
              f"    source: {source}\n")
    with open(target, "a", encoding="utf-8") as fh:
        if header:
            fh.write(header)
        fh.write(block)
        fh.flush()
        os.fsync(fh.fileno())
    return {"at": stamp, "minutes_per_day": minutes, "mode": mode,
            "source": source, "path": str(target)}


# --------------------------------------------------------------------------
# read
# --------------------------------------------------------------------------
def current(reset_cache: bool = True) -> dict:
    """The reading THE RESOLVER produces — never a second parse of the store.

    ``reset_cache`` clears the resolver's process-wide cache first, because a
    long-lived poller process would otherwise keep answering with the value it
    read at boot, minutes after the Captain re-dialled."""
    env = _env()
    if reset_cache:
        env._captain_availability_cache = None
    return env.captain_availability()


def render_current(reading: "dict | None" = None) -> str:
    """The phone-sized answer to ``availability ?``."""
    env = _env()
    r = current() if reading is None else reading
    if r.get("minutes_per_day") is None:
        return ("No availability set — the cabinet does not know how much of "
                "your day it may use. Reply e.g. 'availability 20m' or "
                "'availability part_time'.")
    line = env.render_availability(r)
    when = f"\nSet: {r['set_at']}" if r.get("set_at") else ""
    return (f"Availability: {line}{when}\n"
            "The org fits this budget — it never asks you to fit the org.")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(
        prog="captain_availability.py",
        description="Record and show the Captain's declared availability.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_set = sub.add_parser("set", help="record one value (e.g. 20m, 2h, part_time)")
    p_set.add_argument("value")
    p_set.add_argument("--source", default="cli")

    p_reply = sub.add_parser(
        "reply", help="record from a raw 'availability <arg>' reply")
    p_reply.add_argument("text")
    p_reply.add_argument("--source", default="reply")

    sub.add_parser("show", help="the current reading and where it came from")

    a = ap.parse_args(argv)

    if a.cmd == "show":
        print(render_current())
        return 0

    text = f"availability {a.value}" if a.cmd == "set" else a.text
    parsed = parse_availability_command(text)
    if parsed is None:
        print("not an availability command — expected e.g. 'availability 20m', "
              "'availability part_time', 'availability away' or 'availability ?'",
              file=sys.stderr)
        return 2
    if parsed["kind"] == "query":
        print(render_current())
        return 0
    row = record(parsed["minutes_per_day"], mode=parsed["mode"],
                 source=a.source, text=parsed.get("text", ""))
    print(f"recorded {row['minutes_per_day']} min/day ({row['mode']}) "
          f"-> {row['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
