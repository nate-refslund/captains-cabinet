"""The interview's availability question (Captain ruling 2026-07-26):
ASK how much of his day the cabinet gets, then fit the org to the answer.

Teeth: the question must FOLLOW framework.env.AVAILABILITY_MODES (a changed
band changes the question — hardcoding the prose fails the negative control);
`skip` must leave the answers file byte-untouched, because an honest UNKNOWN is
the designed outcome and a placeholder number is the named failure; every
refusal must write nothing; and the recorded verb must be exactly what the
generator's own validator accepts, so an answer can never be recorded in a
shape the generator then rejects.
"""
import json
from pathlib import Path

import pytest
import yaml

from framework import env
from framework.onboarding import availability


@pytest.fixture(autouse=True)
def answers_file(tmp_path, monkeypatch):
    """Every test runs against a tmp answers file and a tmp deployment root —
    no test here can touch a real deployment's config or the repo tree."""
    p = tmp_path / "cabinet-init.answers.yml"
    monkeypatch.setenv("CABINET_INIT_ANSWERS", str(p))
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.setenv("CABINET_CAPTAIN_AVAILABILITY_FILE",
                       str(tmp_path / "absent-availability.yml"))
    env._captain_availability_cache = None
    yield p
    env._captain_availability_cache = None


# ---------------------------------------------------------------------------
# question
# ---------------------------------------------------------------------------
def test_question_names_every_offered_verb_and_its_live_band():
    q = availability.render_question()
    for mode, minutes, _label in env.AVAILABILITY_MODES:
        if mode == "away":
            continue                   # not offered at init; set from the phone
        assert mode in q, f"{mode} missing from the question"
    assert "10 minutes a day" in q      # the LIVE minimal band's label
    assert "2 hours a day" in q
    assert "skip" in q


def test_question_follows_the_live_table_not_a_hardcoded_copy(monkeypatch):
    """NEGATIVE CONTROL: swap a band in the live table and the rendered question
    must change with it. A hardcoded sentence passes the arm above and fails
    this one."""
    patched = tuple(
        (name, 7 if name == "minimal" else minutes,
         "minimal — about 7 minutes a day" if name == "minimal" else label)
        for name, minutes, label in env.AVAILABILITY_MODES)
    monkeypatch.setattr(env, "AVAILABILITY_MODES", patched)
    q = availability.render_question()
    assert "7 minutes a day" in q
    assert "10 minutes a day" not in q


def test_question_discloses_an_existing_declaration(tmp_path, monkeypatch):
    """A re-run interview must not talk him into silently reverting a ruling he
    made later from his phone."""
    store = tmp_path / "avail.yml"
    store.write_text("entries:\n  - at: 2026-07-26T21:30:00Z\n"
                     "    minutes_per_day: 20\n    mode: part_time\n",
                     encoding="utf-8")
    monkeypatch.setenv("CABINET_CAPTAIN_AVAILABILITY_FILE", str(store))
    env._captain_availability_cache = None
    q = availability.render_question()
    assert "already declares" in q
    assert "20 min/day" in q
    assert "2026-07-26T21:30:00Z" in q


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------
def test_skip_writes_nothing_at_all(answers_file):
    """The DESIGNED outcome for an unclear answer: availability stays UNKNOWN.
    A placeholder number here is the named failure (a value pretending to be an
    answer), so `written` must be False and the file must not exist."""
    receipt = availability.apply_answer("skip")
    assert receipt["written"] is False
    assert receipt["minutes_per_day"] is None
    assert not answers_file.exists()
    assert env.captain_availability()["minutes_per_day"] is None


def test_apply_records_the_verb_for_the_generator(answers_file):
    receipt = availability.apply_answer("part_time")
    assert receipt["written"] is True
    doc = yaml.safe_load(answers_file.read_text(encoding="utf-8"))
    assert doc == {"captain": {"availability": "part_time"}}
    assert receipt["minutes_per_day"] == \
        env.availability_minutes_for_mode("part_time")


def test_apply_preserves_the_rest_of_the_answers_file(answers_file):
    """The interview's other answers are the expensive part — recording one
    verb must never rewrite them away."""
    answers_file.write_text(yaml.safe_dump({
        "version": 1,
        "captain": {"name": "Ada", "timezone": "Europe/Madrid",
                    "telegram_chat_id": "12345678"},
        "lanes": [{"name": "Acme", "slug": "acme"}],
    }, sort_keys=False), encoding="utf-8")
    availability.apply_answer("substantial")
    doc = yaml.safe_load(answers_file.read_text(encoding="utf-8"))
    assert doc["version"] == 1
    assert doc["captain"]["name"] == "Ada"
    assert doc["captain"]["timezone"] == "Europe/Madrid"
    assert doc["captain"]["availability"] == "substantial"
    assert doc["lanes"] == [{"name": "Acme", "slug": "acme"}]


def test_reapplying_the_same_verb_is_an_honest_no_op(answers_file):
    availability.apply_answer("minimal")
    before = answers_file.read_bytes()
    receipt = availability.apply_answer("minimal")
    assert receipt["written"] is False
    assert "no-op" in receipt["note"]
    assert answers_file.read_bytes() == before


def test_a_later_answer_replaces_the_earlier_one(answers_file):
    availability.apply_answer("minimal")
    availability.apply_answer("full_time")
    doc = yaml.safe_load(answers_file.read_text(encoding="utf-8"))
    assert doc["captain"]["availability"] == "full_time"


@pytest.mark.parametrize("bad", ["", None, "  ", "away-ish", "20m", "keep",
                                 "SKIP ME", "part time"])
def test_free_text_and_unknown_verbs_refuse_and_write_nothing(bad, answers_file):
    with pytest.raises(availability.AvailabilityError):
        availability.apply_answer(bad)
    assert not answers_file.exists()


def test_unreadable_answers_file_refuses_rather_than_overwriting(answers_file):
    """An interview's work is never destroyed by this question: a file we cannot
    parse refuses loudly instead of being replaced."""
    answers_file.write_text("captain: [name, timezone\n", encoding="utf-8")
    before = answers_file.read_bytes()
    with pytest.raises(availability.AvailabilityError):
        availability.apply_answer("part_time")
    assert answers_file.read_bytes() == before


def test_non_mapping_captain_block_refuses(answers_file):
    answers_file.write_text("captain: just-a-string\n", encoding="utf-8")
    before = answers_file.read_bytes()
    with pytest.raises(availability.AvailabilityError):
        availability.apply_answer("part_time")
    assert answers_file.read_bytes() == before


# ---------------------------------------------------------------------------
# the recorded verb must be one the generator accepts
# ---------------------------------------------------------------------------
def test_every_offered_verb_is_accepted_by_the_generator(answers_file):
    """LOCKSTEP: the interview writes `captain.availability`, the generator
    validates it against its own enum. A verb this module can record but the
    generator rejects would fail the hatch AFTER the interview is over."""
    import importlib.util
    repo = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "generate_instance_for_availability_test",
        repo / "cabinet/scripts/generate-instance.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    for verb in availability._ONBOARDING_MODES:
        assert verb in gen.AVAILABILITY_VERBS, (
            f"the interview can record {verb!r} but the generator refuses it")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def test_cli_question_and_apply(capsys, answers_file):
    assert availability.main(["question"]) == 0
    assert "cabinet" in capsys.readouterr().out
    assert availability.main(["apply", "--choice", "part_time"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["written"] is True and receipt["choice"] == "part_time"


def test_cli_refuses_an_unknown_choice(answers_file):
    with pytest.raises(SystemExit):          # argparse rejects the enum itself
        availability.main(["apply", "--choice", "20m"])
    assert not answers_file.exists()
