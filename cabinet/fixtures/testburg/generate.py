#!/usr/bin/env python3.12
"""generate.py — deterministic generator for the Testburg fixture's JSONL.

Writes ``undo/undo-journal-*.jsonl`` and ``world/chronicle-*.jsonl`` for the
three-day Ada Testburg story (see README.md). Two honesty properties are
enforced BY CONSTRUCTION:

1. SCHEMA PARITY THROUGH THE REAL CODE, ZERO COPIED CONTENT — journal rows
   are minted with ``framework.frontdoor.action_undo.new_row`` (then
   validated with ``_validate_row``), and every chronicle record is produced
   by running the REAL ingest normalizers from
   ``cabinet/scripts/world-chronicle.py`` (``normalize_org_event``,
   ``normalize_consequence``, ``normalize_undo``, ``normalize_toollog``)
   over synthetic source rows, with the same scrub gate
   (``assert_scrubbed``), the same partitioning (``chronicle_path_for``),
   the same serialization (``json.dumps(..., sort_keys=True)``) and
   monotonic iids like ``collect_batch``. No line of a real chronicle or
   journal is read, let alone copied.

2. LEAK SAFETY — every output line is asserted free of 9+ digit runs
   (telegram-id shaped) before writing; the full banned-pattern audit lives
   in ``cabinet/scripts/tests/test_testburg_fixture.py``. The two
   ``wrote_sha256`` fingerprints are REAL sha256 hex of the shipped tier2
   note files (the fixture is internally true); if editing a note ever
   makes its hash carry a 9-digit run, this script fails loudly — reword
   the note and re-run.

Wave-B additive receipt fields (``why`` / ``cost`` / ``demo``) are added on
top of the base rows exactly as documented in README.md: ``why`` from the
write-ahead line on, ``cost`` only on enrichment (measured after the act),
``demo`` present only on the seeded demo row.

Usage:  python3.12 cabinet/fixtures/testburg/generate.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent
REPO = FIXTURE.parents[2]
sys.path.insert(0, str(REPO))

from framework.frontdoor import action_undo  # noqa: E402

# The real ingest module (its filename carries a hyphen, so importlib —
# same pattern as cabinet/scripts/tests/test_world_chronicle.py).
_spec = importlib.util.spec_from_file_location(
    "world_chronicle", REPO / "cabinet" / "scripts" / "world-chronicle.py")
wch = importlib.util.module_from_spec(_spec)
sys.modules["world_chronicle"] = wch
_spec.loader.exec_module(wch)

_DIGIT_RUN = re.compile(r"[0-9]{9,}")


def _sha(text: str) -> str:
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if _DIGIT_RUN.search(h):
        raise SystemExit(
            "sha256 fingerprint carries a 9+ digit run (would trip the "
            "leak audit) — reword the hashed content slightly and re-run:\n"
            + h)
    return h


def _note_sha(rel: str) -> str:
    return _sha((FIXTURE / rel).read_text(encoding="utf-8"))


def _payload_sha(payload: dict) -> str:
    return _sha(json.dumps(payload, sort_keys=True))


def _write_jsonl(path: Path, lines: list[str]) -> None:
    for ln in lines:
        if _DIGIT_RUN.search(ln):
            raise SystemExit(f"digit-run leak guard tripped in {path.name}: {ln[:120]}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(FIXTURE)} ({len(lines)} lines)")


# ---------------------------------------------------------------------------
# The undo journal — 6 logical rows, 8 physical lines (R1 write-ahead +
# enrichment pair; R2 executed + reversal pair). Times are the fixed story
# clock (README): story-now is 2026-07-10T08:00Z, so R1 (ttl 07-10T06:10Z)
# is EXPIRED, R3/R4/R5/R6 (ttl 07-11) are ACTIVE, R2 is UNDONE.
# ---------------------------------------------------------------------------

def _row(*, jid, ts, pid, cid, step, kind, backend, subject, officer,
         prestate=None, created=None, inverse=None, executed_at=None,
         status="executed", why, payload, extra=None):
    row = action_undo.new_row(
        pid=pid, cid=cid, step=step, kind=kind, backend=backend,
        lane="action", subject=subject,
        actor={"kind": "officer", "id": officer},
        prestate=prestate, created=created, inverse=inverse,
        executed_at=executed_at, status=status, jid=jid, now=ts)
    row["payload_sha256"] = _payload_sha(payload)   # action_exec stamps this
    row["why"] = why                                 # Wave-B receipt field
    if extra:
        row.update(extra)
    action_undo._validate_row(row)
    return row


def build_journal() -> tuple[list[str], list[str], list[tuple[str, dict]]]:
    """Returns (lines for 07-08 file, lines for 07-09 file,
    [(source_ref, row_dict)] in ingest order for the chronicle)."""
    sha_cos_note = _note_sha("notes/tier2/cos/2026-07-08-bakery-site-launch.md")
    sha_cro_note = _note_sha("notes/tier2/cro/2026-07-09-newsletter-audience-research.md")
    p_cos_note = "/opt/testburg-cabinet/instance/memory/tier2/cos/2026-07-08-bakery-site-launch.md"
    p_cro_note = "/opt/testburg-cabinet/instance/memory/tier2/cro/2026-07-09-newsletter-audience-research.md"

    why_r1 = ("The launch checklist agreed at the morning huddle lived only in "
              "a session transcript; officer memory keeps it past compaction.")
    why_r2 = ("All six pilot-bake subtasks read done on the board, so the card "
              "moved to Done. Ada undid this from her morning receipt: tasting "
              "feedback was still open.")
    why_r3 = ("The mill confirmed Friday 06:00-07:00 for the flour delivery; "
              "a calendar block keeps the oven warm-up from colliding with it.")
    why_r4 = ("Issue-1 audience research was requested in the newsletter lane "
              "brief; saving it to officer memory makes it citable evidence.")
    why_r5 = ("The oven vendor slipped to week 30, so the upgrade card is "
              "tagged supplier-blocked to surface it in the Friday review.")
    why_r6 = ("Seeded demo receipt: written at hatch so the /receipts page "
              "shows one complete receipt (what/why/cost/undo) before the "
              "cabinet has acted for real. Clearly labeled demo — remove any "
              "time.")

    # Attributed cost — EXACTLY the Wave-B stamped shape
    # (framework/frontdoor/action_language.py::_valid_cost: subset of
    # usd/tokens_in/tokens_out/model/source, ≥1 non-negative numeric; any
    # unknown key fails closed to "unattributed"). ``source`` names the
    # per-act meter — never the daily aggregates, which the grammar refuses
    # to apportion. Unattributed rows OMIT the field entirely (the honest
    # absence renders "cost: unattributed").
    cost = lambda usd, tin, tout: {  # noqa: E731
        "usd": usd, "tokens_in": tin, "tokens_out": tout,
        "source": "lane-metered"}

    # R1 — tier2_note by cos, 07-08: write-ahead + enrichment pair. EXPIRED
    # at story-now (ttl = ts + 48h = 2026-07-10T06:10:00Z < 08:00Z).
    r1_payload = {"path": p_cos_note, "content_kind": "officer_note"}
    r1_common = dict(
        jid="jid-tb-r1-cos-checklist", ts="2026-07-08T06:10:00Z",
        pid="card-testburg-0007", cid="cid-testburg-0007", step=1,
        kind="tier2_note", backend="file", subject="Save the bakery-site launch checklist to officer memory",
        officer="cos", why=why_r1, payload=r1_payload)
    r1_ahead = _row(**r1_common,
                    prestate={"existed": False, "prior_content": None},
                    inverse={"op": "file_compare_restore",
                             "args": {"path": p_cos_note, "existed": False,
                                      "prior_content": None, "wrote_sha256": None}})
    r1_done = _row(**r1_common,
                   prestate={"existed": False, "prior_content": None},
                   created={"path": p_cos_note, "wrote_sha256": sha_cos_note},
                   inverse={"op": "file_compare_restore",
                            "args": {"path": p_cos_note, "existed": False,
                                     "prior_content": None,
                                     "wrote_sha256": sha_cos_note}},
                   executed_at="2026-07-08T06:10:02Z",
                   extra={"cost": cost(0.0148, 1930, 210)})

    # R2 — task_status_move by cpo, 07-08, REVERSED by Ada on 07-09. The
    # reversal line lands in the 07-09 journal file (journal_step appends to
    # the current day) while keeping the row's original ts — exactly like
    # the live writer; _read_journal's last-write-wins collapse handles it.
    r2_payload = {"monday_id": "itm-testburg-0042", "board_id": "brd-testburg-01",
                  "set": {"status": "Done", "status_column": "status"}}
    r2_inverse = {"op": "monday_compare_restore",
                  "args": {"board_id": "brd-testburg-01", "item_id": "itm-testburg-0042",
                           "columns": {"status": {"wrote": "Done", "prior_text": "In review",
                                                  "kind": "label"}},
                           "update_id": None}}
    r2_common = dict(
        jid="jid-tb-r2-cpo-statusmove", ts="2026-07-08T14:20:00Z",
        pid="card-testburg-0009", cid="cid-testburg-0009", step=1,
        kind="task_status_move", backend="local_board",
        subject="Move pilot-bake card to Done on the Testburg board",
        officer="cpo", why=why_r2, payload=r2_payload)
    r2_exec = _row(**r2_common,
                   prestate={"status": {"text": "In review"}},
                   created={"item_id": "itm-testburg-0042"},
                   inverse=r2_inverse, executed_at="2026-07-08T14:20:01Z",
                   extra={"cost": cost(0.0022, 310, 45)})
    r2_undone = dict(r2_exec)
    r2_undone.update(status="reversed", reversed_at="2026-07-09T07:45:12Z")

    # R3 — reminder_create by coo on the calendar backend, 07-09, ACTIVE.
    r3_payload = {"title": "Flour delivery window (mill truck)",
                  "start": "2026-07-11T06:00:00Z", "calendar": "Testburg-Cabinet"}
    r3 = _row(jid="jid-tb-r3-coo-flourwindow", ts="2026-07-09T05:30:00Z",
              pid="card-testburg-0011", cid="cid-testburg-0011", step=1,
              kind="reminder_create", backend="calendar",
              subject="Calendar block for the Friday flour delivery window",
              officer="coo", why=why_r3, payload=r3_payload,
              prestate={},
              created={"uid": "cal-testburg-0003", "calendar": "Testburg-Cabinet"},
              inverse={"op": "calendar_delete_by_uid",
                       "args": {"uid": "cal-testburg-0003", "calendar": "Testburg-Cabinet"}},
              executed_at="2026-07-09T05:30:02Z",
              extra={"cost": cost(0.0031, 540, 60)})

    # R4 — tier2_note by cro, 07-09, ACTIVE, cost honestly UNATTRIBUTED.
    r4_payload = {"path": p_cro_note, "content_kind": "officer_note"}
    r4 = _row(jid="jid-tb-r4-cro-audience", ts="2026-07-09T09:15:00Z",
              pid="card-testburg-0012", cid="cid-testburg-0012", step=1,
              kind="tier2_note", backend="file",
              subject="Save newsletter audience research to officer memory",
              officer="cro", why=why_r4, payload=r4_payload,
              prestate={"existed": False, "prior_content": None},
              created={"path": p_cro_note, "wrote_sha256": sha_cro_note},
              inverse={"op": "file_compare_restore",
                       "args": {"path": p_cro_note, "existed": False,
                                "prior_content": None, "wrote_sha256": sha_cro_note}},
              executed_at="2026-07-09T09:15:01Z",
              extra=None)  # cost OMITTED — honest "cost: unattributed" row

    # R5 — label write by cpo, 07-09, ACTIVE.
    r5_payload = {"monday_id": "itm-testburg-0057", "board_id": "brd-testburg-01",
                  "set": {"label": "supplier-blocked", "label_column": "label"}}
    r5 = _row(jid="jid-tb-r5-cpo-ovenlabel", ts="2026-07-09T11:40:00Z",
              pid="card-testburg-0013", cid="cid-testburg-0013", step=1,
              kind="label", backend="local_board",
              subject="Tag oven-upgrade card supplier-blocked",
              officer="cpo", why=why_r5, payload=r5_payload,
              prestate={"label": {"text": None}},
              created={"item_id": "itm-testburg-0057"},
              inverse={"op": "monday_compare_restore",
                       "args": {"board_id": "brd-testburg-01", "item_id": "itm-testburg-0057",
                                "columns": {"label": {"wrote": "supplier-blocked",
                                                      "prior_text": None, "kind": "label"}},
                                "update_id": None}},
              executed_at="2026-07-09T11:40:01Z",
              extra={"cost": cost(0.0019, 260, 38)})

    # R6 — the seeded demo receipt (demo: true), ACTIVE. Mirrors the
    # emit-demo-receipt.sh doctrine: a demo row NEVER claims an undo that is
    # not registered — inverse op "none" with a demo reason (an `undo`
    # against it is an honest no-op), nothing real created, no cost stamp.
    # FIXTURE-ONLY journal row: the live emit-demo-receipt.sh validates its
    # row but never journals it (its artifact is the rendered receipt FILE
    # at instance/memory/demo-receipt.md; a live day-one journal is honestly
    # empty). This row exists to exercise the /receipts DEMO-badge
    # defense-in-depth path (README "demo" bullet).
    r6_payload = {"note": "seeded-demo-receipt", "content_kind": "officer_note"}
    r6 = _row(jid="jid-tb-r6-cos-seeded-demo", ts="2026-07-09T16:00:00Z",
              pid="card-testburg-0014", cid="cid-testburg-0014", step=1,
              kind="tier2_note", backend="file",
              subject="[demo] Seeded demo receipt - bakery-site",
              officer="cos", why=why_r6, payload=r6_payload,
              prestate={},
              created={},
              inverse={"op": "none",
                       "args": {"reason": "seeded demo receipt - nothing real "
                                          "to reverse"}},
              executed_at="2026-07-09T16:00:01Z",
              extra={"demo": True})

    dump = lambda r: json.dumps(r, default=str)  # noqa: E731 — journal_step's format
    day8 = [dump(r) for r in (r1_ahead, r1_done, r2_exec)]
    day9 = [dump(r) for r in (r3, r2_undone, r4, r5, r6)]

    # (source_ref, row) in INGEST order with real byte offsets, exactly what
    # tail_jsonl would hand normalize_undo.
    ingest: list[tuple[str, dict]] = []
    for fname, lines, rows in (
            ("undo-journal-2026-07-08.jsonl", day8, (r1_ahead, r1_done, r2_exec)),
            ("undo-journal-2026-07-09.jsonl", day9, (r3, r2_undone, r4, r5, r6))):
        off = 0
        for ln, row in zip(lines, rows):
            ingest.append((f"{fname}:{off}", row))
            off += len(ln.encode("utf-8")) + 1
    return day8, day9, ingest


# ---------------------------------------------------------------------------
# The chronicle — synthetic org_events / consequence / toollog source rows
# plus the journal lines above, all through the REAL normalizers.
# ---------------------------------------------------------------------------

def _org(eid, etype, agg, actor, ts, attrs=None):
    rec = wch.normalize_org_event(
        (0, eid, etype, agg, actor, "framework",
         json.dumps(attrs or {}), ts))
    assert rec is not None, f"org event {eid} failed normalization"
    return rec


def _consequence(line: dict, ref: str):
    rec = wch.normalize_consequence(json.dumps(line), ref)
    assert rec is not None, f"consequence row at {ref} failed normalization"
    return rec


def _toollog(officer, tool, ts, ref):
    rec = wch.normalize_toollog(
        json.dumps({"officer": officer, "tool": tool, "ts": ts}), ref)
    assert rec is not None, f"toollog row at {ref} failed normalization"
    return rec


def build_chronicle(journal_ingest: list[tuple[str, dict]]) -> dict[str, list[str]]:
    recs: list[dict] = []

    # Day 1 — 2026-07-07: hatch, sessions, the staked mission, first tools.
    recs += [
        _org("ev-0707-hatch-cos", "session_started", "officer_session", "cos",
             "2026-07-07T06:05:00Z"),
        _org("ev-0707-hatch-cto", "session_started", "officer_session", "cto",
             "2026-07-07T06:06:10Z"),
        _org("ev-0707-mission-bake", "mission_created", "mission", "cos",
             "2026-07-07T06:20:00Z", {"lane": "bakery-site"}),
        _org("ev-0707-assign-menu", "work_item_assigned", "work_item", "cos",
             "2026-07-07T06:25:00Z", {"lane": "bakery-site"}),
        _toollog("cto", "Read", "2026-07-07T07:02:00Z", "2026-07-07.jsonl:0"),
        _toollog("cto", "Edit", "2026-07-07T07:41:00Z", "2026-07-07.jsonl:214"),
        _org("ev-0707-digest", "digest_published", "captain_channel", "cos",
             "2026-07-07T17:30:00Z"),
    ]

    # Day 2 — 2026-07-08: menu work ships; the acted tier2 note (R1) and the
    # premature Done (R2); the newsletter draft is PROPOSED (propose-first).
    j = {ref: row for ref, row in journal_ingest}
    def _undo(ref):
        rec = wch.normalize_undo(json.dumps(j[ref], default=str), ref)
        assert rec is not None, f"undo row at {ref} failed normalization"
        return rec

    recs += [
        _org("ev-0708-sess-cpo", "session_started", "officer_session", "cpo",
             "2026-07-08T05:58:00Z"),
        _undo("undo-journal-2026-07-08.jsonl:0"),      # R1 write-ahead
        _consequence({"actor": "cos", "action": "acted:tier2_note",
                      "ts": "2026-07-08T06:10:01Z",
                      "proposal": {"required": False},
                      "lane": "bakery-site", "kind": "tier2_note"},
                     "consequence-events-2026-07-08.jsonl:0"),
        *(_undo(r) for r in _refs_for(journal_ingest,
                                      "undo-journal-2026-07-08.jsonl", 1, 3)),
        _org("ev-0708-menu-shipped", "work_item_completed", "work_item", "cpo",
             "2026-07-08T11:05:00Z", {"lane": "bakery-site", "outcome": "shipped"}),
        _consequence({"actor": "cro", "action": "proposed:draft_only",
                      "ts": "2026-07-08T15:35:00Z",
                      "proposal": {"required": True},
                      "lane": "newsletter", "kind": "draft_only"},
                     "consequence-events-2026-07-08.jsonl:412"),
        _org("ev-0708-digest", "digest_published", "captain_channel", "cos",
             "2026-07-08T17:30:00Z"),
    ]

    # Day 3 — 2026-07-09: the calendar block (R3), Ada's undo of R2, the
    # research note (R4), the label (R5), the seeded demo receipt (R6),
    # graduation movement, wind-down. NOTE: the R2 reversal line keeps the
    # row's ORIGINAL ts (2026-07-08…), so its chronicle record partitions
    # into chronicle-2026-07-08.jsonl even though it ingests on day 3 —
    # exactly the live writer's partition-by-source-date behavior.
    recs += [
        _org("ev-0709-sess-coo", "session_started", "officer_session", "coo",
             "2026-07-09T05:20:00Z"),
        *(_undo(r) for r in _refs_for(journal_ingest,
                                      "undo-journal-2026-07-09.jsonl", 0, 2)),
        _consequence({"actor": "coo", "action": "acted:reminder_create",
                      "ts": "2026-07-09T05:30:01Z",
                      "proposal": {"required": False},
                      "action_type": "calendar_event_create",
                      "lane": "bakery-site", "kind": "reminder_create"},
                     "consequence-events-2026-07-09.jsonl:0"),
        *(_undo(r) for r in _refs_for(journal_ingest,
                                      "undo-journal-2026-07-09.jsonl", 2, 5)),
        _org("ev-0709-newsletter-note", "work_item_completed", "work_item", "cro",
             "2026-07-09T09:16:00Z", {"lane": "newsletter"}),
        _org("ev-0709-graduation", "graduation_transition", "trust", "system",
             "2026-07-09T12:00:00Z", {"transition": "observe-to-act_with_undo"}),
        _org("ev-0709-sess-end-cto", "session_ended", "officer_session", "cto",
             "2026-07-09T17:55:00Z"),
        _org("ev-0709-digest", "digest_published", "captain_channel", "cos",
             "2026-07-09T17:58:00Z"),
    ]

    # Scrub gate + monotonic iids in ingest order, then partition by source
    # date — the collect_batch / append_records mechanics.
    by_file: dict[str, list[str]] = {}
    iid = 0
    for rec in recs:
        assert wch.assert_scrubbed(rec), f"record failed the scrub gate: {rec}"
        iid += 1
        rec["iid"] = iid
        name = wch.chronicle_path_for(rec).name
        by_file.setdefault(name, []).append(json.dumps(rec, sort_keys=True))
    return by_file


def _refs_for(ingest, fname, start, stop):
    """The ingest refs for lines [start, stop) of one journal file."""
    return [ref for ref, _ in ingest if ref.startswith(fname + ":")][start:stop]


def main() -> int:
    day8, day9, ingest = build_journal()
    _write_jsonl(FIXTURE / "undo" / "undo-journal-2026-07-08.jsonl", day8)
    _write_jsonl(FIXTURE / "undo" / "undo-journal-2026-07-09.jsonl", day9)
    for name, lines in sorted(build_chronicle(ingest).items()):
        _write_jsonl(FIXTURE / "world" / name, lines)
    print("testburg fixture regenerated — run the leak audit: "
          "python3.12 -m pytest cabinet/scripts/tests/test_testburg_fixture.py -q")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
