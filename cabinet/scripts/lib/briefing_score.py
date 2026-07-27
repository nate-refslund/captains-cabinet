#!/usr/bin/env python3.12
"""briefing_score.py — the 14-day briefing-value trial instrument.

ONE NUMBER PER BRIEFING. The Captain scores the briefing he just got:

    0  wouldn't read it
    1  read it, no value
    2  told me something I didn't know
    3  changed what I did next

Recorded append-only, summarised on demand. That is the whole instrument.

RUNG 3 CHANGED 2026-07-27, from "I'd act on it" (adjudicated, altitude gate
of record). "Act" conflates the QUALITY of the item with the operator's
AUTHORITY over it. At founder altitude "act" means ratify an outcome; at
employee altitude the honest answer to a genuinely excellent briefing is often
"I can't act on that, it isn't mine" — a permanent 2, so the ceiling was set by
org chart rather than by cabinet quality and the 2->3 transition could never
fire. "Changed what I did next" is reachable at EVERY altitude, and it is
still a thing the operator TYPED about the cabinet's output, so the
never-a-score exemption below holds unchanged. Deliberately NOT built: a
per-altitude rubric — a second scale is a second instrument nobody asked for,
and this repo's own OVI history is the proof that composites drift from the
question.

NEVER COMPARABLE ACROSS OPERATORS. The scale is self-referenced against one
reader's own week; two operators' medians measure two different worlds. The
summary is a longitudinal read for ONE deployment and is rendered saying so.

WHY IT EXISTS: nothing in this cabinet measured whether the Captain reads or
values anything it sends him. The one value composite that exists (OVI,
``framework/ovi/components.yml``) has no ``cabinet/services.yml`` row and has
never been published. Until 2026-07-26 it also scored its attention term
INVERSE — treating Captain contact as a cost to minimise, which is the
opposite question — and that term is now ``captain_attention_well_spent``:
the share of his attention that went on decisions only he could make, reading
0.0 when the org never asked at all. Even fixed, it is an inference from
telemetry about whether attention was well spent. This file asks the Captain
himself, which is a different and better question, and remains the only
instrument that does.

WHAT IT DELIBERATELY IS NOT: a metrics framework. Nothing schedules it,
nothing gates on it, no daemon reads it, it has no launchd row and no
``services.yml`` row. It works in the propose-only, no-launchd hatch because
it is a file and a function.

NEVER-A-SCORE (EVAL-025) — why this is lawful, not an exception. The law
bars *evidence-derived aggregates* from becoming officer-visible scores or
inputs to generation/selection. A score here is a number the CAPTAIN TYPED
about the cabinet's output — the same class the law's own fixture already
exempts by name (``feedback_rating``: "a value the Captain typed about the
cabinet, not an evidence-derived aggregate about an officer"). It is not
derived from evidence, it is not about an officer, and nothing in this file
reaches ``cabinet_projection`` or any officer read surface.

WHERE THE DATA LIVES — and why it survives a deploy.
``instance/memory/briefing-scores.jsonl``. ``cabinet/scripts/runtime-provision.sh``
links ``instance/memory`` as a WHOLE DIRECTORY (it is an entry in
``INSTANCE_PERSISTENT_SEEDED_DIRS`` — named, never cited by line number, which
rots on every concurrent landing) into the shared instance-data store, so
every file under it — including one that did not exist when the release was
cut — survives a deploy, a rollback and a slot swap with no edit to any
persistence list. The archive it scores, ``instance/memory/briefings/``
(``framework/frontdoor/run_briefing.py``), is co-located under that same
surviving directory, so ONE env knob fences both (see TEST FENCE below) and
neither can drift onto a different slot than the other.

Two nearby homes were rejected at authoring time because neither then
survived a deploy: top-level ``memory/tier3/`` (named by no
``INSTANCE_PERSISTENT_*`` list) and a new ``shared/interfaces/*.jsonl``
series (a per-file list whose loop linked only a leaf shared/ ALREADY held,
so the first write of a brand-new series was lost). LANDING NOTE 2026-07-26:
the state-persistence preflight that landed on master while this branch was
in flight closed BOTH holes — ``memory/tier3`` joined the seeded-dirs list,
and the per-file loop gained runtime-file adoption — so neither is
deploy-unsafe any more, and those two sentences are kept only as the dated
reason of record. The choice stands on the reason that did not change:
co-location with the briefing archive, and a whole-directory link that needs
no persistence-list edit at all.

APPEND-ONLY. A re-score of the same briefing appends a correction; the
summary takes the LAST row per briefing. Nothing in this file ever rewrites
or deletes a row.

CLI (one command each way)::

    python3.12 cabinet/scripts/lib/briefing_score.py score 3
    python3.12 cabinet/scripts/lib/briefing_score.py score 2 --note "knew half of it"
    python3.12 cabinet/scripts/lib/briefing_score.py reply "/score 3 the pricing row is wrong"
    python3.12 cabinet/scripts/lib/briefing_score.py summary
    python3.12 cabinet/scripts/lib/briefing_score.py summary --days 14 --json

PHONE PATH (the control the Captain actually uses — no terminal, per the
2026-07-17 captain-controls ruling): he replies ``/score 3`` on Telegram.
``cabinet/scripts/officer-inbound-poller.py`` answers it mechanically from
its own process, the same shape as ``/killswitch``, and falls OPEN to the
Chair relay if anything here raises — a real message is never silently eaten.

TEST FENCE: ``CABINET_BRIEFING_SCORES_DIR`` relocates the whole memory
directory (score file + briefings archive). The repo-root ``conftest.py``
sets it into the pytest session sandbox, so no test run can write the live
instance store — fenced at birth, like ``CABINET_CAPTAIN_INBOUND_DIR`` and
``CABINET_LIVENESS_CONFIG`` before it.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

#: Row schema tag. Bump only with a reader that handles both.
SCHEMA = "cabinet.briefing-score/v1"

#: The append-only store, relative to the repo root.
SCORES_REL = "instance/memory/briefing-scores.jsonl"

#: The briefing archive this instrument scores (written by
#: framework/frontdoor/run_briefing.py in card mode).
BRIEFINGS_REL = "instance/memory/briefings"

#: The closed score set. Anything else is refused — a scale with a "4" on it
#: is a different instrument and would silently break every summary below.
VALID_SCORES = (0, 1, 2, 3)

#: What each number means, in the Captain's words. Rendered by the summary so
#: a reader never has to go looking for the scale.
SCALE = {
    0: "wouldn't read it",
    1: "read it, no value",
    2: "told me something I didn't know",
    3: "changed what I did next",
}

#: The phone grammar: ``/score <0-3> [note]`` (optional @botname suffix, an
#: optional ':' separator, any trailing note). ANCHORED TWICE, deliberately —
#: "/score" inside a sentence is conversation for the Chair, never a control
#: command, exactly like KILLSWITCH_CMD_RE. ``re.match`` already anchors at
#: position 0; the leading ``^`` is redundant defense-in-depth so a later
#: switch to ``search`` cannot silently open the grammar to mid-sentence
#: matches (a mutation sweep proved neither alone is falsifiable — only the
#: pair is). The two negative lookaheads ARE singly load-bearing: without the
#: first, "/score 32" parses as 3 with note "2"; without the second, a decimal
#: — "/score 3.5", or the Danish "/score 2,5" the Captain would actually type
#: — silently truncates to the integer part and throws away what he meant. A
#: number this instrument cannot represent must be REFUSED so he retypes it,
#: never quietly rounded. A trailing period that is punctuation ("/score 3.
#: really useful") still parses: only a separator followed by a DIGIT is a
#: decimal.
SCORE_CMD_RE = re.compile(
    r"^\s*/score(?:@\w{1,64})?[\s:]+([0-3])(?![0-9])(?![.,][0-9])\s*(.*?)\s*$",
    re.IGNORECASE | re.DOTALL)

#: Notes are a memory aid, not a corpus. Truncated on write.
NOTE_MAX = 280


# --------------------------------------------------------------------------
# paths
# --------------------------------------------------------------------------
def repo_root() -> Path:
    """CABINET_ROOT wins, else this file's repo (cabinet/scripts/lib/…)."""
    root = os.environ.get("CABINET_ROOT", "").strip()
    return Path(root) if root else Path(__file__).resolve().parents[3]


def memory_dir(root: "Path | None" = None) -> Path:
    """The instance-memory directory holding the store AND the briefing
    archive. ``CABINET_BRIEFING_SCORES_DIR`` relocates both together (the
    pytest fence) — one knob, so a fenced run can never read live briefings
    while writing sandbox scores."""
    override = os.environ.get("CABINET_BRIEFING_SCORES_DIR", "").strip()
    if override:
        return Path(override)
    return (root or repo_root()) / "instance" / "memory"


def scores_path(root: "Path | None" = None) -> Path:
    return memory_dir(root) / Path(SCORES_REL).name


def briefings_dir(root: "Path | None" = None) -> Path:
    return memory_dir(root) / Path(BRIEFINGS_REL).name


# --------------------------------------------------------------------------
# the phone grammar
# --------------------------------------------------------------------------
def parse_score_command(text: str) -> "dict | None":
    """``/score <0-3> [note]`` → ``{"score": int, "note": str}``, else None.

    None means "not a score command" — every caller must then fall through to
    its normal path. Refusing loudly here would eat a real message."""
    m = SCORE_CMD_RE.match(text or "")
    if not m:
        return None
    return {"score": int(m.group(1)), "note": (m.group(2) or "")[:NOTE_MAX]}


# --------------------------------------------------------------------------
# the briefing being scored
# --------------------------------------------------------------------------
def _stamp_of(name: str) -> str:
    """``briefing-20260726-073000Z.md`` → ``20260726-073000Z``."""
    return name[len("briefing-"):-len(".md")]


def list_briefing_ids(root: "Path | None" = None) -> "list[str]":
    """Archived briefing ids, oldest first. The filename stamp is
    ``%Y%m%d-%H%M%SZ``, so lexical sort IS chronological sort."""
    d = briefings_dir(root)
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("briefing-*.md") if p.is_file())


def latest_briefing_id(root: "Path | None" = None) -> "str | None":
    ids = list_briefing_ids(root)
    return ids[-1] if ids else None


def _briefing_time(briefing_id: str) -> "datetime | None":
    """The UTC time a briefing id names, or None when it is not our shape."""
    try:
        return datetime.strptime(
            _stamp_of(briefing_id + ".md"), "%Y%m%d-%H%M%SZ"
        ).replace(tzinfo=timezone.utc)
    except Exception:
        return None


# --------------------------------------------------------------------------
# write
# --------------------------------------------------------------------------
def record(score: int, *, briefing_id: "str | None" = None, note: str = "",
           source: str = "cli", now: "datetime | None" = None,
           root: "Path | None" = None) -> dict:
    """Append ONE score row. Returns the row written.

    ``briefing_id`` defaults to the most recently archived briefing — "the one
    I just got". When the archive is empty the row is still written with
    ``briefing_id: null``: a Captain who scored something must never lose the
    score because the archive was not where we looked."""
    if isinstance(score, bool) or score not in VALID_SCORES:
        raise ValueError(f"score must be one of {VALID_SCORES}, got {score!r}")
    at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if briefing_id is None:
        briefing_id = latest_briefing_id(root)
    row = {
        "schema": SCHEMA,
        "at": at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "briefing_id": briefing_id,
        "score": int(score),
        "note": (note or "").strip()[:NOTE_MAX],
        "source": source,
    }
    path = scores_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line)
        fh.flush()
        os.fsync(fh.fileno())
    return row


# --------------------------------------------------------------------------
# read + summarise
# --------------------------------------------------------------------------
def read_rows(root: "Path | None" = None) -> "tuple[list[dict], int]":
    """``(rows, malformed_line_count)``. A corrupt line is skipped and
    COUNTED, never dropped silently — the summary reports it."""
    path = scores_path(root)
    if not path.is_file():
        return [], 0
    rows: "list[dict]" = []
    bad = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            bad += 1
            continue
        if not isinstance(row, dict) or row.get("score") not in VALID_SCORES:
            bad += 1
            continue
        rows.append(row)
    return rows, bad


def _parse_at(value: str) -> "datetime | None":
    try:
        return datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except Exception:
        return None


def summarize(*, days: "int | None" = None, now: "datetime | None" = None,
              root: "Path | None" = None) -> dict:
    """n · median · distribution · trend · how many briefings got NO score.

    Silence is data: an archived briefing with no score row is reported as
    unscored, not omitted. ``unscored`` counts only briefings the archive
    actually holds — when there is no archive to compare against the summary
    says so (``archive_present: false``) instead of implying zero."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    # `days is not None`, NOT `if days` — a caller who asked for 0 days asked
    # for an empty window; silently reinterpreting that as "everything" is the
    # kind of quiet argument-rewrite that makes a report untrustworthy.
    cutoff = now - timedelta(days=days) if days is not None else None
    rows, malformed = read_rows(root)

    # Window the rows, then collapse to the LAST row per briefing (a re-score
    # is a correction). Rows with no briefing_id cannot be collapsed — each
    # keeps its own identity, keyed by its timestamp.
    windowed = []
    for row in rows:
        at = _parse_at(row.get("at", ""))
        if cutoff and (at is None or at < cutoff):
            continue
        windowed.append(row)
    # A row with no briefing_id cannot be collapsed against anything, so each
    # gets a key unique to its POSITION — not to its timestamp. Two scores
    # recorded in the same second are two scores; keying on `at` silently
    # merged them (found by the first smoke run, 2026-07-26).
    latest: "dict[str, dict]" = {}
    for idx, row in enumerate(windowed):
        key = row.get("briefing_id") or f"__unbound__{idx}"
        latest[key] = row
    scored = sorted(latest.values(), key=lambda r: str(r.get("at", "")))
    values = [int(r["score"]) for r in scored]

    # Trend: median of the first half vs the last half, chronologically. On an
    # odd count the middle row belongs to neither half. Under 4 scores there
    # is no trend to report and we say null rather than invent one.
    trend = None
    if len(values) >= 4:
        half = len(values) // 2
        first = statistics.median(values[:half])
        second = statistics.median(values[-half:])
        trend = {"first_half_median": first, "second_half_median": second,
                 "delta": round(second - first, 2)}

    archive = briefings_dir(root)
    archive_present = archive.is_dir()
    seen = []
    for bid in list_briefing_ids(root):
        bt = _briefing_time(bid)
        if cutoff and (bt is None or bt < cutoff):
            continue
        seen.append(bid)
    scored_ids = {r.get("briefing_id") for r in scored if r.get("briefing_id")}
    unscored = [b for b in seen if b not in scored_ids]

    return {
        "n": len(values),
        "median": statistics.median(values) if values else None,
        "distribution": {str(s): values.count(s) for s in VALID_SCORES},
        "trend": trend,
        "briefings_seen": len(seen),
        "unscored": len(unscored),
        "unscored_ids": unscored,
        "archive_present": archive_present,
        "malformed_rows": malformed,
        "window_days": days,
        "store": str(scores_path(root)),
    }


def render_summary(s: dict) -> str:
    """Plain English, short — the register the Captain reads in."""
    if not s["n"]:
        head = "No briefings scored yet."
    else:
        dist = "  ".join(
            f"{k}={s['distribution'][k]}" for k in ("0", "1", "2", "3"))
        head = (f"{s['n']} briefing{'s' if s['n'] != 1 else ''} scored · "
                f"median {s['median']}\n{dist}")
    lines = [head]
    if s["trend"]:
        t = s["trend"]
        direction = ("up" if t["delta"] > 0 else
                     "down" if t["delta"] < 0 else "flat")
        lines.append(f"Trend: {t['first_half_median']} → "
                     f"{t['second_half_median']} ({direction})")
    elif s["n"]:
        lines.append("Trend: not enough scores yet (needs 4).")
    if s["archive_present"]:
        lines.append(f"Briefings sent: {s['briefings_seen']} · "
                     f"no score: {s['unscored']} "
                     f"(an unscored briefing is probably a 0)")
    else:
        lines.append("Briefings sent: unknown — no briefing archive on this "
                     "machine, so 'no score' cannot be counted.")
    if s["malformed_rows"]:
        lines.append(f"{s['malformed_rows']} unreadable row(s) skipped.")
    lines.append("Scale: " + " · ".join(f"{k} {v}" for k, v in SCALE.items()))
    # Printed every time, deliberately. The scale is self-referenced against
    # ONE reader's own week, so a median here and a median on another
    # deployment are not the same measurement — and a bare number invites
    # exactly that comparison.
    lines.append("Not comparable across operators — one reader, over time.")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(
        prog="briefing_score.py",
        description="Record and summarise the Captain's 0-3 briefing scores.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_score = sub.add_parser("score", help="record one score (0-3)")
    p_score.add_argument("score", type=int, choices=list(VALID_SCORES))
    p_score.add_argument("--briefing", default=None,
                         help="briefing id (default: the latest archived one)")
    p_score.add_argument("--note", default="")
    p_score.add_argument("--source", default="cli")

    p_reply = sub.add_parser(
        "reply", help="record from a raw '/score N [note]' reply")
    p_reply.add_argument("text")
    p_reply.add_argument("--briefing", default=None)
    p_reply.add_argument("--source", default="reply")

    p_sum = sub.add_parser("summary", help="n, median, distribution, trend")
    p_sum.add_argument("--days", type=int, default=None)
    p_sum.add_argument("--json", action="store_true")

    a = ap.parse_args(argv)

    if a.cmd == "score":
        row = record(a.score, briefing_id=a.briefing, note=a.note,
                     source=a.source)
        print(f"recorded {row['score']} ({SCALE[row['score']]}) for "
              f"{row['briefing_id'] or 'no archived briefing'}")
        return 0

    if a.cmd == "reply":
        parsed = parse_score_command(a.text)
        if parsed is None:
            print("not a score command — expected '/score <0-3> [note]'",
                  file=sys.stderr)
            return 2
        row = record(parsed["score"], briefing_id=a.briefing,
                     note=parsed["note"], source=a.source)
        print(f"recorded {row['score']} ({SCALE[row['score']]}) for "
              f"{row['briefing_id'] or 'no archived briefing'}")
        return 0

    s = summarize(days=a.days)
    print(json.dumps(s, indent=2) if a.json else render_summary(s))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
