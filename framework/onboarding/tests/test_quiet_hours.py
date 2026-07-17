"""The interview's quiet-hours question (Captain insight 2026-07-17):
PRESENT the default, don't assume — keep/change/disable, materialized
through the charter system's own amend path, fail-closed everywhere.

Teeth: the question must FOLLOW charter-default.yml (a changed default file
changes the question — hardcoding fails the negative control); every refusal
path must leave the deployment charter byte-untouched; disable must be
proven at the GATE level (never-quiet), not just in the written YAML."""
import json
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from framework.attention import charter, gate
from framework.onboarding import quiet_hours


@pytest.fixture(autouse=True)
def charter_file(tmp_path, monkeypatch):
    """Every test runs against a tmp deployment charter — no test in this
    module can touch a real deployment's comms charter (or the repo tree)."""
    p = tmp_path / "comms-charter.yml"
    monkeypatch.setenv("CABINET_CHARTER_PATH", str(p))
    return p


def _default_doc():
    return {k: v for k, v in charter.load_default().items() if k != "_source"}


def _write_custom_default(tmp_path, start="20:15", end="05:45",
                          floor=("deadline-critical",)):
    p = tmp_path / "charter-default-custom.yml"
    p.write_text(yaml.safe_dump({
        "version": 1,
        "quiet_hours": {"start": start, "end": end,
                        "floor_classes": list(floor)},
        "classes": [{"id": "default", "route": "next-briefing"}],
    }), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# render — the question follows the FILE, never a hardcoded copy
# ---------------------------------------------------------------------------

def test_question_states_the_shipped_default():
    d = _default_doc()["quiet_hours"]
    q = quiet_hours.render_question()
    assert f"{d['start']}–{d['end']}" in q
    assert q.rstrip().endswith("Keep, change, or disable?")
    for slug in d["floor_classes"]:
        # every floor class is NAMED in the question (label or verbatim slug)
        root = slug.split("-")[0][:5].lower()
        assert root in q.lower()


def test_question_follows_a_changed_default(tmp_path):
    """The not-hardcoded proof: a different default file must change the
    question — and the shipped window must NOT appear anywhere in it."""
    p = _write_custom_default(tmp_path)
    q = quiet_hours.render_question(default_path=p)
    assert "20:15–05:45" in q
    assert "21:00" not in q and "07:00" not in q
    assert "deadline-critical" in q          # unknown slug renders verbatim


def test_question_notes_an_existing_override():
    quiet_hours.apply_answer("change", "23:00", "05:00")
    q = quiet_hours.render_question()
    assert "23:00–05:00" in q
    assert "keep" in q.lower()               # warns keep will refuse


def test_question_malformed_default_fails_closed(tmp_path):
    bad = tmp_path / "bad-default.yml"
    bad.write_text("version: 1\nclasses: not-a-list\n", encoding="utf-8")
    with pytest.raises(ValueError):
        quiet_hours.render_question(default_path=bad)
    bad.write_text("just a string\n", encoding="utf-8")
    with pytest.raises(ValueError):
        quiet_hours.render_question(default_path=bad)


# ---------------------------------------------------------------------------
# keep — nothing written; never a silent revert
# ---------------------------------------------------------------------------

def test_keep_writes_nothing(charter_file):
    r = quiet_hours.apply_answer("keep")
    assert r["written"] is False
    assert not charter_file.exists()


def test_keep_refuses_to_revert_an_existing_ruling(charter_file):
    quiet_hours.apply_answer("change", "23:00", "05:00")
    before = charter_file.read_bytes()
    with pytest.raises(ValueError):
        quiet_hours.apply_answer("keep")
    assert charter_file.read_bytes() == before      # byte-untouched


def test_keep_is_a_noop_when_override_matches_default_window(charter_file):
    # an override that tunes something ELSE (voice/verbosity) keeps the
    # default window — keep must not refuse, and must not rewrite the file
    charter.amend({"verbosity": "verbose"}, "tune", {"trust": "chair"})
    before = charter_file.read_bytes()
    r = quiet_hours.apply_answer("keep")
    assert r["written"] is False
    assert charter_file.read_bytes() == before


# ---------------------------------------------------------------------------
# change — schema-valid override, provenance row, honest no-ops
# ---------------------------------------------------------------------------

def test_change_materializes_a_house_valid_override(charter_file):
    r = quiet_hours.apply_answer("change", "22:00", "06:00")
    assert r["written"] is True and r["version"] == 2
    doc = yaml.safe_load(charter_file.read_text(encoding="utf-8"))
    charter.validate_charter(doc)            # the loader's own gate passes
    qh = doc["quiet_hours"]
    assert (qh["start"], qh["end"]) == ("22:00", "06:00")
    # floor carried from the default, untouched by a window answer
    assert qh["floor_classes"] == _default_doc()["quiet_hours"]["floor_classes"]
    assert charter.load_charter()["_source"] == "override"


def test_change_override_validates_against_the_json_schema(charter_file):
    jsonschema = pytest.importorskip("jsonschema")
    quiet_hours.apply_answer("change", "22:00", "06:00")
    doc = yaml.safe_load(charter_file.read_text(encoding="utf-8"))
    schema_path = (Path(charter.__file__).resolve().parents[2]
                   / "framework" / "schemas" / "comms-charter.schema.json")
    jsonschema.validate(doc, json.loads(schema_path.read_text(encoding="utf-8")))


def test_change_appends_a_provenance_ledger_row(charter_file):
    quiet_hours.apply_answer("change", "22:00", "06:00")
    ledger = charter_file.parent / "comms-charter-amendments.jsonl"
    rows = [json.loads(l) for l in ledger.read_text().splitlines()]
    assert rows[-1]["provenance"] == {"trust": "chair",
                                      "via": "cabinet-init-interview"}
    assert "22:00–06:00" in rows[-1]["why"]


def test_change_rerun_is_an_honest_noop(charter_file):
    r1 = quiet_hours.apply_answer("change", "22:00", "06:00")
    r2 = quiet_hours.apply_answer("change", "22:00", "06:00")
    assert r1["written"] is True and r2["written"] is False
    doc = yaml.safe_load(charter_file.read_text(encoding="utf-8"))
    assert doc["version"] == 2               # no idle version bump
    ledger = charter_file.parent / "comms-charter-amendments.jsonl"
    assert len(ledger.read_text().splitlines()) == 1


def test_change_to_the_default_window_writes_nothing(charter_file):
    """A pointless override that duplicates the default would freeze today's
    default body forever — the honest materialization is NO file."""
    d = _default_doc()["quiet_hours"]
    if d["start"] == d["end"]:
        pytest.skip("shipped default already zero-length")
    r = quiet_hours.apply_answer("change", d["start"], d["end"])
    assert r["written"] is False
    assert not charter_file.exists()


def test_window_change_never_rewidens_a_captain_narrowed_floor(charter_file):
    d = _default_doc()["quiet_hours"]
    assert d["floor_classes"], "shipped default must carry a floor"
    narrowed = [d["floor_classes"][0]]
    charter.amend(
        {"quiet_hours": {"start": d["start"], "end": d["end"],
                         "floor_classes": narrowed}},
        "Captain narrows the floor",
        {"trust": "captain", "receipt_message_id": 5})
    r = quiet_hours.apply_answer("change", "22:00", "06:00")
    assert r["written"] is True
    doc = yaml.safe_load(charter_file.read_text(encoding="utf-8"))
    assert doc["quiet_hours"]["floor_classes"] == narrowed   # not re-widened


# ---------------------------------------------------------------------------
# disable — zero-length window, proven at the GATE, floor preserved
# ---------------------------------------------------------------------------

def test_disable_zero_length_window_proven_at_the_gate(charter_file):
    d = _default_doc()["quiet_hours"]
    sh, sm = (int(x) for x in d["start"].split(":"))
    probe = datetime(2026, 1, 1, sh, sm)
    # positive control: under the SHIPPED window its own start minute IS
    # quiet — so a broken disable could not pass the assertions below.
    assert gate._in_quiet_hours(probe, d) is True
    r = quiet_hours.apply_answer("disable")
    assert r["written"] is True
    doc = yaml.safe_load(charter_file.read_text(encoding="utf-8"))
    charter.validate_charter(doc)            # still schema-valid
    qh = doc["quiet_hours"]
    assert qh["start"] == qh["end"]          # the zero-length window
    assert qh["floor_classes"] == d["floor_classes"]   # floor NOT dropped
    assert gate._in_quiet_hours(probe, qh) is False
    for hh, mm in ((3, 0), (23, 0), (0, 0), (12, 30)):
        assert gate._in_quiet_hours(datetime(2026, 1, 1, hh, mm), qh) is False


def test_disable_rerun_is_a_noop(charter_file):
    quiet_hours.apply_answer("disable")
    before = charter_file.read_bytes()
    r = quiet_hours.apply_answer("disable")
    assert r["written"] is False
    assert charter_file.read_bytes() == before


# ---------------------------------------------------------------------------
# refusals — invalid input never writes a byte
# ---------------------------------------------------------------------------

def test_invalid_times_refused_and_nothing_written(charter_file):
    bad = ["25:00", "9:00", "21:60", "2100", "seven pm", "07:00PM", "",
           None, "22:00;echo pwned", "$(reboot)", "–", "24:00", "12:5"]
    for b in bad:
        with pytest.raises(ValueError):
            quiet_hours.apply_answer("change", b, "06:00")
        with pytest.raises(ValueError):
            quiet_hours.apply_answer("change", "22:00", b)
    assert not charter_file.exists()         # not one byte written


def test_equal_times_change_refused_points_to_disable(charter_file):
    with pytest.raises(ValueError) as ei:
        quiet_hours.apply_answer("change", "07:00", "07:00")
    assert "disable" in str(ei.value)
    assert not charter_file.exists()


def test_unknown_choice_refused(charter_file):
    for c in ("mute", "yes", "", None, "keep; rm -rf", "KEEPALL", 7):
        with pytest.raises(ValueError):
            quiet_hours.apply_answer(c)
    assert not charter_file.exists()


def test_change_missing_times_refused(charter_file):
    with pytest.raises(ValueError):
        quiet_hours.apply_answer("change")
    with pytest.raises(ValueError):
        quiet_hours.apply_answer("change", "22:00", None)
    assert not charter_file.exists()


# ---------------------------------------------------------------------------
# CLI — the exact surface the interview skill calls
# ---------------------------------------------------------------------------

def test_cli_question_prints_the_default(capsys):
    assert quiet_hours.main(["question"]) == 0
    d = _default_doc()["quiet_hours"]
    assert f"{d['start']}–{d['end']}" in capsys.readouterr().out


def test_cli_apply_disable_then_refusals(charter_file, capsys):
    assert quiet_hours.main(["apply", "--choice", "disable"]) == 0
    assert charter_file.exists()
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["written"] is True
    after = charter_file.read_bytes()
    # bad time → domain refusal on stderr, rc 1, charter untouched
    assert quiet_hours.main(["apply", "--choice", "change",
                             "--start", "25:00", "--end", "06:00"]) == 1
    assert "REFUSED" in capsys.readouterr().err
    assert charter_file.read_bytes() == after
    # non-enum verb → argparse hard-stops before any code runs
    with pytest.raises(SystemExit) as ei:
        quiet_hours.main(["apply", "--choice", "nuke"])
    assert ei.value.code == 2
