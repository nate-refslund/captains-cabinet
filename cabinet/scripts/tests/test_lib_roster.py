"""lib_roster.py — roster-derived officer service rows (product/captain-
agnostic foundation, 2026-07-14). Pins: absent roster -> empty (never
invented rows, never a hard error), row shape matches what services.yml used
to hand-author per officer, optional expected/notes overrides apply, and
roster order is preserved (file order, matching deploy-mac.sh's own
roster_officers() contract)."""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

import lib_roster  # noqa: E402


def _write_roster(tmp_path: Path, body: str) -> Path:
    cfg = tmp_path / "instance" / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "roster.yml").write_text(body, encoding="utf-8")
    return tmp_path


def test_absent_roster_yields_empty_not_an_error(tmp_path):
    assert lib_roster.load_roster(tmp_path) == {}
    assert lib_roster.officer_service_rows(tmp_path) == []


def test_generic_row_shape_matches_the_old_hardcoded_pattern(tmp_path):
    root = _write_roster(tmp_path, """
roster:
  widget-ceo:
    title: "Widget CEO"
    model: "claude-opus-4-8[1m]"
    capabilities: [deploys_code, logs_captain_decisions]
    authority_level: "mission_executor"
    type: fulltime
""")
    rows = lib_roster.officer_service_rows(root)
    assert rows == [{
        "name": "officer-widget-ceo",
        "label": "com.cabinet.officer.widget-ceo",
        "kind": "officer",
        "command": "bash cabinet/scripts/start-officer-mac.sh widget-ceo",
        "schedule": "keepalive",
        "expected": "redis heartbeat cabinet:heartbeat:widget-ceo",
    }]


def test_optional_expected_and_notes_overrides(tmp_path):
    root = _write_roster(tmp_path, """
roster:
  cos:
    title: Chair
    model: "claude-opus-4-8[1m]"
    capabilities: [logs_captain_decisions]
    authority_level: captain_proxy
    expected: "redis heartbeat cabinet:heartbeat:cos (idle≠dead)"
    notes: "sole Telegram voice"
""")
    rows = lib_roster.officer_service_rows(root)
    assert rows == [{
        "name": "officer-cos",
        "label": "com.cabinet.officer.cos",
        "kind": "officer",
        "command": "bash cabinet/scripts/start-officer-mac.sh cos",
        "schedule": "keepalive",
        "expected": "redis heartbeat cabinet:heartbeat:cos (idle≠dead)",
        "notes": "sole Telegram voice",
    }]


def test_roster_order_is_preserved(tmp_path):
    root = _write_roster(tmp_path, """
roster:
  cos:
    title: Chair
    model: m
    capabilities: [a]
    authority_level: captain_proxy
  widget-ceo:
    title: "Widget CEO"
    model: m
    capabilities: [a]
    authority_level: mission_executor
  gadget-ceo:
    title: "Gadget CEO"
    model: m
    capabilities: [a]
    authority_level: mission_executor
""")
    rows = lib_roster.officer_service_rows(root)
    assert [r["name"] for r in rows] == [
        "officer-cos", "officer-widget-ceo", "officer-gadget-ceo"]


def test_malformed_roster_top_level_raises(tmp_path):
    root = _write_roster(tmp_path, "roster: not-a-mapping\n")
    try:
        lib_roster.officer_service_rows(root)
        assert False, "expected ValueError on a non-mapping roster: value"
    except ValueError:
        pass


def test_empty_roster_file_yields_empty(tmp_path):
    root = _write_roster(tmp_path, "roster:\n")
    assert lib_roster.officer_service_rows(root) == []


def test_non_dict_officer_entry_raises_not_crashes(tmp_path):
    # A slug mapped to a scalar/list (operator typo) must raise a clear
    # ValueError, not an AttributeError from fields.get() on a non-dict.
    root = _write_roster(tmp_path, "roster:\n  cos: not-a-mapping\n")
    try:
        lib_roster.officer_service_rows(root)
        assert False, "expected ValueError on a non-dict officer entry"
    except ValueError:
        pass


def test_null_officer_entry_yields_generic_defaults(tmp_path):
    # A slug with NO fields at all (bare key, YAML null) is a legitimate
    # minimal roster entry -- falls back to the generic pattern, not an error.
    root = _write_roster(tmp_path, "roster:\n  cos:\n")
    rows = lib_roster.officer_service_rows(root)
    assert rows == [{
        "name": "officer-cos",
        "label": "com.cabinet.officer.cos",
        "kind": "officer",
        "command": "bash cabinet/scripts/start-officer-mac.sh cos",
        "schedule": "keepalive",
        "expected": "redis heartbeat cabinet:heartbeat:cos",
    }]
