"""framework.attention.acted_overlay — P2 world-grounding: what did we act on?

WHY (spec §8 P2, 2026-07-08): acting updates the world (calendar, Monday),
the ledger, and the undo journal — but not the perception surface the
proposer reads. The lane therefore re-discovered already-handled situations
forever ("reminder_set: false" stays false in the vault after the calendar
event exists). This module joins the two records the executor already
writes — consequence-ledger ``acted:<kind>`` rows (which carry the card's
evidence refs) and undo-journal rows (which carry execution status,
created ids, and reversals) — into ONE acted-state view with three
consumers:

1. ``render_overlay`` — an ALREADY-ACTED section appended to the gather
   signals, so the proposer LLM *sees* acted state (gather-then-decide).
2. ``live_canonical`` — canonical refs of NON-reversed acted artifacts; the
   propose core drops overlapping proposals with the distinct
   ``already-acted`` reason.
3. ``reversed_canonical`` — canonical refs of Captain-REVERSED acts; these
   are SUBTRACTED from the covered set so an undone situation may present
   again (undo means "that act was wrong", not "this situation is fake" —
   P1 alone wrongly kept suppressing it for the covered window).

Failure bias: an unreadable journal/ledger raises to the caller, who treats
world state as UNKNOWN — cards still propose, act-first disarms for the run
(spec: "probe-outage → unknown; card still proposes, never acts").

Loaders are injectable; the pure join/render halves take plain lists so the
replay/sim harness can drive them deterministically.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, Optional

from framework.attention.situation import canonical_refs

# Mirrors action_undo._undo_dir's resolution (env override, same default) —
# read-only twin; the writer stays the single owner of the directory.
_UNDO_DIR_ENV = "CABINET_UNDO_DIR"
_UNDO_DIR_DEFAULT = "~/Library/Application Support/cabinet/undo"

_REVERSED_STATUSES = frozenset({"reversed"})


def _undo_dir() -> Path:
    return Path(os.environ.get(_UNDO_DIR_ENV) or
                os.path.expanduser(_UNDO_DIR_DEFAULT))


def load_journal_rows(base: "Path | None" = None) -> list:
    """All undo-journal rows, collapsed by jid last-write-wins (the writer
    appends a write-ahead row and an enrichment row per jid). Unreadable
    files/lines are skipped; a missing dir is an empty journal, NOT an error
    (a fresh deployment has acted on nothing)."""
    d = base or _undo_dir()
    if not d.exists():
        return []
    rows: list = []
    for f in sorted(d.glob("undo-journal-*.jsonl")):
        try:
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(r, dict) and r.get("jid"):
                        rows.append(r)
        except OSError as e:
            # An UNREADABLE journal file loses reversal state — that is
            # world-UNKNOWN, not world-empty (review cp2 Low-1). Raise so
            # the lane disarms act-first instead of suppressing wrongly.
            raise RuntimeError(f"undo journal unreadable: {f.name}: {e}") from e
    rows.sort(key=lambda r: str(r.get("ts", "")))
    collapsed: dict = {}
    for r in rows:
        collapsed[r["jid"]] = r
    return list(collapsed.values())


def _acted_ledger_rows(ledger_rows: Iterable, since: str) -> list:
    out = []
    for ev in ledger_rows:
        if not isinstance(ev, dict):
            continue
        if not str(ev.get("action") or "").startswith("acted:"):
            continue
        if since and str(ev.get("ts") or "") < since:
            continue
        out.append(ev)
    return out


def _cid_of(refs: Iterable) -> str:
    for r in refs or ():
        s = str(r)
        if s.startswith("cabinet-proposal-id:"):
            return s.split(":", 1)[1]
    return ""


def load_acted(*, since: str = "",
               ledger_rows: "Iterable | None" = None,
               journal_rows: "Iterable | None" = None) -> dict:
    """The acted-state view: entries + live/reversed canonical ref-sets.

    ``since`` is an inclusive ISO floor on the LEDGER acted rows (same clock
    the covered window uses). Journal rows are read in full — reversal state
    must be honored even for an act just outside the window. Raises on a
    ledger read failure (world state unknown ≠ world state empty); the
    journal loader's missing-dir case is a true empty.
    """
    _default_load = ledger_rows is None
    if ledger_rows is None:
        from framework.fidelity.consequence import read_ledger
        ledger_rows = read_ledger(since=since or None)
    if journal_rows is None:
        journal_rows = load_journal_rows()
    # Consistency fence (review cp2 M2): a box that has JOURNALED acts but
    # shows a completely empty ledger is env drift (CABINET_EVENT_LOG_DIR
    # pointing elsewhere), not a fresh deployment — that world is UNKNOWN,
    # not empty. A truly fresh box (both empty) is a legitimately empty
    # world and acting on it duplicates nothing.
    # (window-matched: journal rows older than the ledger's since-floor say
    # nothing about THIS window — a box quiet for weeks is not drifted.)
    _recent_journal = [r for r in journal_rows
                       if not since or str(r.get("ts") or "") >= since]
    if _default_load and _recent_journal and not ledger_rows:
        raise RuntimeError(
            "acted-state inconsistent: undo journal has rows in-window but "
            "the consequence ledger read returned nothing (env drift?)")

    # cid -> reversed? from the journal (any reversed step reverses the card
    # for suppression purposes: the Captain pulled SOME of it back, so the
    # situation may be live again — conservative toward presenting).
    # STATUS ONLY (review cp2 High): the writer also stamps reversed_at on
    # reversal_failed / dead_letter rows, where the artifact explicitly
    # STAYS STANDING — a reversed_at disjunct would report a false world.
    reversed_cids = set()
    for jr in journal_rows:
        cid = str(jr.get("cid") or "")
        if cid and str(jr.get("status") or "") in _REVERSED_STATUSES:
            reversed_cids.add(cid)

    entries, live, undone = [], set(), set()
    for ev in _acted_ledger_rows(ledger_rows, since):
        refs = [r for r in (ev.get("refs") or []) if isinstance(r, str)]
        canon = canonical_refs(refs)
        cid = _cid_of(refs)
        is_reversed = cid in reversed_cids
        entries.append({
            "kind": str(ev.get("action") or "")[len("acted:"):],
            "subject": str(ev.get("subject") or ""),
            "ts": str(ev.get("ts") or ""),
            "cid": cid,
            "reversed": is_reversed,
            "canonical": canon,
        })
        (undone if is_reversed else live).update(canon)
    # Approved-then-undone (review cp2 M3): reversal must un-cover ANY card
    # whose cid the journal marks reversed — approved executions journal the
    # same way but their ledger rows are 'action-card', not 'acted:*'.
    for ev in ledger_rows:
        if not isinstance(ev, dict) or str(ev.get("action") or "") != "action-card":
            continue
        refs = [r for r in (ev.get("refs") or []) if isinstance(r, str)]
        if _cid_of(refs) in reversed_cids:
            undone.update(canonical_refs(refs))
    # A ref both live and reversed (two acts, one undone) stays LIVE —
    # something acted on it still stands.
    undone -= live
    return {"entries": entries,
            "live_canonical": frozenset(live),
            "reversed_canonical": frozenset(undone)}


def render_overlay(acted: "dict | None") -> str:
    """The ALREADY-ACTED signals section (empty string when nothing acted).
    Cabinet-generated text (from our own journal/ledger), not captured
    content — but it is still rendered as DATA for the proposer, same as
    every other section."""
    if not acted or not acted.get("entries"):
        return ""
    lines = ["", "== ALREADY ACTED (cabinet-executed — do NOT re-propose; "
                 "reversed items were UNDONE by the Captain: propose again "
                 "only on genuinely new evidence) =="]
    for e in sorted(acted["entries"], key=lambda x: x["ts"], reverse=True)[:40]:
        mark = "REVERSED-BY-CAPTAIN" if e["reversed"] else "acted"
        lines.append(f"- [{e['kind'] or '?'}] {e['subject'][:120]} — {mark} {e['ts']}")
    return "\n".join(lines) + "\n"
