"""Formation (Phase 3 SCAFFOLD) — stage machine helpers, resume, undo, and the
"proposes, never activates" invariant as a TESTED property.

Hermetic: tmp_path roots only — no LLM, no network, no subprocess, and never
the checkout's own instance/.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.onboarding import formation

_REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# run ids + path containment
# ---------------------------------------------------------------------------
def test_new_run_id_shape_and_uniqueness():
    a = formation.new_run_id(now="2026-07-14T10:15:30Z")
    b = formation.new_run_id(now="2026-07-14T10:15:30Z")
    assert a.startswith("formation-20260714-101530-")
    assert a != b                                  # collision suffix


@pytest.mark.parametrize("bad", [
    "../escape", "a/b", "_pre-adopt-x", ".hidden", "", "x y", "run\nid",
])
def test_run_dir_refuses_path_escapes(tmp_path, bad):
    with pytest.raises(ValueError):
        formation.run_dir(tmp_path, bad)


def test_run_dir_is_contained(tmp_path):
    rdir = formation.run_dir(tmp_path, "formation-20260714-101530-ab12")
    assert rdir.parent == tmp_path / formation.FORMATION_DIR_REL


# ---------------------------------------------------------------------------
# journal — append-only, tolerant reads
# ---------------------------------------------------------------------------
def test_journal_appends_and_never_rewrites(tmp_path):
    rid = "formation-20260714-000000-0001"
    r1 = formation.append_journal(tmp_path, rid, "FORMATION_START",
                                  status="open", note="call_cap=25",
                                  now="2026-07-14T00:00:00Z")
    first = formation.journal_path(tmp_path, rid).read_text()
    formation.append_journal(tmp_path, rid, "DISCOVERY_DONE",
                             status="stub-iou", now="2026-07-14T00:00:01Z")
    text = formation.journal_path(tmp_path, rid).read_text()
    assert text.startswith(first)                  # append-only: prefix intact
    rows = formation.read_journal(tmp_path, rid)
    assert [r["stage"] for r in rows] == ["FORMATION_START", "DISCOVERY_DONE"]
    assert rows[0] == r1


def test_journal_skips_malformed_lines_without_rewriting(tmp_path):
    rid = "formation-20260714-000000-0002"
    formation.append_journal(tmp_path, rid, "FORMATION_START", status="open")
    path = formation.journal_path(tmp_path, rid)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("{truncated-by-crash\n")
    rows = formation.read_journal(tmp_path, rid)
    assert len(rows) == 1                          # honest partial read
    assert "{truncated-by-crash" in path.read_text()   # never rewritten


def test_append_journal_refuses_unknown_stamp(tmp_path):
    with pytest.raises(ValueError):
        formation.append_journal(tmp_path, "formation-x", "NOT_A_STAMP",
                                 status="open")


# ---------------------------------------------------------------------------
# the stage machine — open, stubs, resume
# ---------------------------------------------------------------------------
def test_open_run_records_start_and_call_cap(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_FORMATION_CALL_CAP", "7")
    res = formation.open_run(tmp_path, now="2026-07-14T00:00:00Z")
    assert res["resumed"] is False and res["call_cap"] == 7
    assert res["next_stage"] == "DISCOVERY_DONE"
    rows = formation.read_journal(tmp_path, res["run_id"])
    assert rows[0]["stage"] == "FORMATION_START"
    assert "call_cap=7" in rows[0]["note"]
    # the recorded cap rides the run even if the knob changes afterwards
    monkeypatch.setenv("CABINET_FORMATION_CALL_CAP", "999")
    assert formation.run_call_cap(tmp_path, res["run_id"]) == 7


@pytest.mark.parametrize("raw", ["banana", "-3", "0", ""])
def test_call_cap_knob_falls_back_on_malformed(monkeypatch, raw):
    monkeypatch.setenv("CABINET_FORMATION_CALL_CAP", raw)
    assert formation.call_cap() == formation._DEFAULT_CALL_CAP


def test_stage_stub_writes_honest_iou_and_journals(tmp_path):
    res = formation.open_run(tmp_path, now="2026-07-14T00:00:00Z")
    rid = res["run_id"]
    out = formation.run_stage(tmp_path, rid, "DISCOVERY_DONE",
                              now="2026-07-14T00:00:01Z")
    assert out["status"] == "stub-iou"
    artifact = Path(out["artifact"])
    assert artifact.name == "discovery-IOU.md"
    text = artifact.read_text()
    assert formation.IOU_PREFIX + " 1" in text     # "not yet built — increment 1"
    assert formation.GENERATED_MARKER in text
    assert "DISCOVERY_DONE" in formation.journaled_stamps(tmp_path, rid)


def test_read_scope_stub_states_no_consent_was_recorded(tmp_path):
    rid = formation.open_run(tmp_path)["run_id"]
    out = formation.run_stage(tmp_path, rid, "READ_SCOPE_RATIFIED")
    text = Path(out["artifact"]).read_text()
    assert "NO consent was requested or recorded" in text
    assert "formation reads nothing of the Captain's" in text


def test_stage_is_idempotent_resume_skips(tmp_path):
    rid = formation.open_run(tmp_path)["run_id"]
    first = formation.run_stage(tmp_path, rid, "DISCOVERY_DONE")
    artifact = Path(first["artifact"])
    mtime = artifact.stat().st_mtime_ns
    again = formation.run_stage(tmp_path, rid, "DISCOVERY_DONE")
    assert again["status"] == "already-done"
    assert artifact.stat().st_mtime_ns == mtime    # untouched on resume
    rows = [r for r in formation.read_journal(tmp_path, rid)
            if r["stage"] == "DISCOVERY_DONE"]
    assert len(rows) == 1                          # no duplicate journal row


def test_full_run_stamps_all_stages_in_order(tmp_path):
    rid = formation.open_run(tmp_path)["run_id"]
    while (stamp := formation.next_stage(tmp_path, rid)) is not None:
        formation.run_stage(tmp_path, rid, stamp)
    rows = formation.read_journal(tmp_path, rid)
    assert [r["stage"] for r in rows] == list(formation.ALL_STAMPS)
    assert formation.next_stage(tmp_path, rid) is None
    rdir = formation.run_dir(tmp_path, rid)
    assert sorted(p.name for p in rdir.glob("*-IOU.md")) == [
        "briefing-IOU.md", "discovery-IOU.md", "ingest-IOU.md",
        "read-scope-IOU.md", "strategy-IOU.md",
    ]


def test_open_run_resume_keeps_original_start_row(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_FORMATION_CALL_CAP", "5")
    rid = formation.open_run(tmp_path)["run_id"]
    monkeypatch.setenv("CABINET_FORMATION_CALL_CAP", "50")
    res = formation.open_run(tmp_path, run_id=rid)
    assert res["resumed"] is True
    starts = [r for r in formation.read_journal(tmp_path, rid)
              if r["stage"] == "FORMATION_START"]
    assert len(starts) == 1                        # START written once
    assert formation.run_call_cap(tmp_path, rid) == 5


def test_estimate_is_honest_about_zero_calls(tmp_path):
    rid = formation.open_run(tmp_path)["run_id"]
    text = "\n".join(formation.estimate_lines(tmp_path, rid))
    assert "LLM CLI calls this run: 0" in text
    assert "cap" in text and "CABINET_FORMATION_CALL_CAP" in text


# ---------------------------------------------------------------------------
# undo — supersede-archive in the _pre-adopt idiom
# ---------------------------------------------------------------------------
def test_undo_archives_nothing_deleted(tmp_path):
    rid = formation.open_run(tmp_path)["run_id"]
    formation.run_stage(tmp_path, rid, "DISCOVERY_DONE")
    res = formation.undo_run(tmp_path, rid, now="2026-07-14T01:02:03Z")
    assert res["status"] == "archived"
    dest = Path(res["archived_to"])
    assert dest.name == rid
    assert dest.parent.name.startswith("_pre-adopt-")
    assert dest.parent.parent == formation.formation_dir(tmp_path)
    assert not formation.run_dir(tmp_path, rid).exists()   # moved, not copied
    assert (dest / "journal.jsonl").is_file()              # contents intact
    assert (dest / "discovery-IOU.md").is_file()
    assert "nothing deleted" in (dest / "undo-receipt.md").read_text()


def test_undo_missing_run_is_honest_refusal(tmp_path):
    res = formation.undo_run(tmp_path, "formation-19990101-000000-dead")
    assert res["status"] == "no-such-run" and res["archived_to"] is None


def test_undo_never_clobbers_an_earlier_archive(tmp_path):
    rid = formation.open_run(tmp_path)["run_id"]
    formation.undo_run(tmp_path, rid, now="2026-07-14T01:02:03Z")
    # same run-id hatched again, undone at the same stamp second
    formation.open_run(tmp_path, run_id=rid)
    res = formation.undo_run(tmp_path, rid, now="2026-07-14T01:02:03Z")
    assert res["status"] == "archived"
    assert Path(res["archived_to"]).name == f"{rid}.2"     # sibling, no clobber


def test_undo_refuses_path_escapes(tmp_path):
    with pytest.raises(ValueError):
        formation.undo_run(tmp_path, "../outside")
    with pytest.raises(ValueError):
        formation.undo_run(tmp_path, "_pre-adopt-20260714/x")


# ---------------------------------------------------------------------------
# THE INVARIANT — the mission compiler structurally never reads ANY formation
# surface ("proposes, never activates" as a tested property, not a convention)
# ---------------------------------------------------------------------------
_MISSIONS_DIR = _REPO_ROOT / "framework" / "missions"
# word-anchored so "information"/"transformation" never false-positive
import re as _re
_FORBIDDEN_PATTERNS = (
    _re.compile(r"(?<![a-z])formation"),   # no formation surface/helper/import
    _re.compile(r"outcomes-proposed"),     # the genesis staging file stays unread
    _re.compile(r"instance/onboarding"),   # the whole formation tree
)


def test_mission_compiler_sources_never_reference_formation_surfaces():
    """Structural half: no file in framework/missions/ (the compiler,
    session bridge, supervisor, standing pull) so much as NAMES a formation
    surface. If this fails, "proposes, never activates" has been breached at
    the source level — stop and re-review the change that did it."""
    sources = sorted(p for p in _MISSIONS_DIR.rglob("*.py")
                     if "tests" not in p.parts)
    assert sources, f"missions sources not found under {_MISSIONS_DIR}"
    for src in sources:
        text = src.read_text(encoding="utf-8").lower()
        for pat in _FORBIDDEN_PATTERNS:
            assert not pat.search(text), (
                f"{src.relative_to(_REPO_ROOT)} matches {pat.pattern!r} — the "
                "mission compiler must stay structurally unable to read "
                "formation/proposal surfaces")


def test_mission_compiler_instance_config_read_is_outcomes_yml_only():
    """Every instance/config path literal in the missions sources is
    outcomes.yml — the single filename gate everything propose-only builds
    on (genesis.py:12-17; formation inherits it)."""
    import re
    pat = re.compile(r"instance[/\"'\s,)]+[\"']?config[/\"'\s,)]+[\"']?([\w.-]+\.ya?ml)")
    hits = set()
    for src in _MISSIONS_DIR.rglob("*.py"):
        if "tests" in src.parts:
            continue
        for m in pat.finditer(src.read_text(encoding="utf-8")):
            hits.add(m.group(1))
    assert hits <= {"outcomes.yml"}, (
        f"missions sources read unexpected instance/config files: {hits}")


def test_compiler_finds_no_work_in_a_formation_populated_root(tmp_path):
    """Behavioral half: a root carrying a COMPLETE formation run (with
    outcome-looking bait in a stage artifact) but no outcomes.yml yields no
    missions — the session bridge's read gate never wanders into
    instance/onboarding/."""
    from framework.missions import session_bridge

    rid = formation.open_run(tmp_path)["run_id"]
    while (stamp := formation.next_stage(tmp_path, rid)) is not None:
        formation.run_stage(tmp_path, rid, stamp)
    # bait: an outcomes-shaped file inside the formation surface
    bait = formation.run_dir(tmp_path, rid) / "outcomes.yml"
    bait.write_text(
        "outcomes:\n"
        "  - id: poisoned\n    name: MUST NEVER COMPILE\n    status: active\n"
        "    captain_ratified: true\n"
        "    measurable_criteria: ['x']\n", encoding="utf-8")

    assert session_bridge._outcomes_path(str(tmp_path)) == (
        tmp_path / "instance" / "config" / "outcomes.yml")
    assert session_bridge.get_next_task("cos", cabinet_root=str(tmp_path)) is None
