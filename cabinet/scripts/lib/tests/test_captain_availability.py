"""The Captain's availability dial — cabinet/scripts/lib/captain_availability.py.

Every arm pins a property the dial EXISTS TO DELIVER, not an internal invariant:

  * the phone grammar accepts what he would actually type ("availability 20m",
    "availability 2h", a bare band, "away", "?") and REFUSES what he did not
    mean (a mid-sentence mention, a fractional minute, an impossible number) —
    a refusal returns None so the poller relays his words instead of eating
    them;
  * a fractional minute is never ROUNDED — a number the dial cannot represent
    must come back to him;
  * the ruling reaches disk, append-only, and the LATEST one is what the
    resolver serves (so the phone always beats what onboarding stamped);
  * his verbatim text is preserved as an inert COMMENT, never as a value;
  * `away` (0 min/day) is a real ruling, not an absence — the degenerate end;
  * it survives a deploy: the store is named in runtime-provision.sh's
    persistence list, asserted against that script's actual text rather than
    against a comment about it;
  * writer and reader agree on ONE path (framework.env.captain_availability_path),
    so a fenced test can never touch the live declaration.

EVIDENCE NOTE (brand-new module): "these tests fail before the file exists" is
worthless here — every arm would fail on ImportError for reasons unrelated to
what it claims. The falsification evidence is the guard-mutation sweep recorded
in the landing report; arms carry ``GUARD:`` markers naming what they pin.

Run: cd cabinet/scripts/lib && python3.12 -m pytest tests/test_captain_availability.py -q
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

import captain_availability as ca

REPO = Path(__file__).resolve().parents[4]
PROVISION = REPO / "cabinet/scripts/runtime-provision.sh"
GITIGNORE = REPO / ".gitignore"


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    """Every test gets its own store, and the resolver cache is cleared so a
    read never answers from a sibling test's file."""
    path = tmp_path / "captain-availability.yml"
    monkeypatch.setenv("CABINET_CAPTAIN_AVAILABILITY_FILE", str(path))
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    ca._env()._captain_availability_cache = None
    return path


def _at(day: int, hour: int = 9) -> datetime:
    return datetime(2026, 7, day, hour, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# grammar
# --------------------------------------------------------------------------
@pytest.mark.parametrize("text,minutes,mode", [
    ("availability 20m", 20, "part_time"),
    ("availability 20 min", 20, "part_time"),
    ("availability 45minutes", 45, "substantial"),
    ("availability 2h", 120, "substantial"),
    ("availability 1.5h", 90, "substantial"),
    ("availability 1,5h", 90, "substantial"),        # Danish decimal comma
    ("availability 90", 90, "substantial"),          # bare int reads as minutes
    ("availability minimal", 10, "minimal"),
    ("availability part_time", 30, "part_time"),
    ("availability part-time", 30, "part_time"),     # hyphen form
    ("availability FULL_TIME", 480, "full_time"),    # case-insensitive
    ("availability away", 0, "away"),
    ("/availability 20m", 20, "part_time"),          # optional leading slash
    ("  availability: 20m  ", 20, "part_time"),      # colon separator, padding
])
def test_grammar_accepts_what_he_would_type(text, minutes, mode):
    """GUARD: _CMD_RE + _DURATION_RE + the mode arm."""
    got = ca.parse_availability_command(text)
    assert got is not None, f"{text!r} must parse"
    assert got["kind"] == "set"
    assert got["minutes_per_day"] == minutes
    assert got["mode"] == mode


@pytest.mark.parametrize("text", [
    "I think availability 20m is fine",   # mid-sentence: conversation
    "so availability 20m",                # PREFIXED — only the START anchor
                                          # rejects this one; the tail anchor
                                          # and the arg shape both accept it,
                                          # so it is the arm that makes the
                                          # anchor falsifiable at all
    "availability is worth discussing",   # a sentence that starts with the word
    "availability",                       # no argument at all
    "availability soon",                  # unknown word
    "availability 3.5m",                  # fractional MINUTE: refuse, not round
    "availability 25h",                   # above a day: a typo, not a ruling
    "availability -20m",                  # negative
    "",
])
def test_grammar_refuses_what_he_did_not_mean(text):
    """GUARD: the anchoring + range + integrality guards. A refusal is None so
    the poller falls through and RELAYS — never silently eats a message."""
    assert ca.parse_availability_command(text) is None


def test_a_query_is_not_a_write():
    """GUARD: _QUERY_RE. 'availability ?' must never record anything."""
    assert ca.parse_availability_command("availability ?") == {"kind": "query"}


def test_fractional_minutes_are_refused_rather_than_rounded():
    """The paid rule from /score: a number the instrument cannot represent is
    REFUSED so he retypes it, never quietly changed into a different number."""
    assert ca.parse_availability_command("availability 2.5m") is None
    # …but a fractional HOUR that lands on a whole minute is representable.
    assert ca.parse_availability_command(
        "availability 0.5h")["minutes_per_day"] == 30


# --------------------------------------------------------------------------
# write
# --------------------------------------------------------------------------
def test_record_lands_on_disk_and_the_resolver_serves_it(_store):
    row = ca.record(20, mode="part_time", source="telegram",
                    text="availability 20m", now=_at(26))
    assert _store.is_file()
    assert row["minutes_per_day"] == 20 and row["at"] == "2026-07-26T09:00:00Z"
    got = ca.current()
    assert got["minutes_per_day"] == 20
    assert got["source"] == "adjusted"
    assert got["set_at"] == "2026-07-26T09:00:00Z"


def test_append_only_and_latest_wins(_store):
    ca.record(120, source="telegram", text="availability 2h", now=_at(20))
    ca.record(20, source="telegram", text="availability 20m", now=_at(26))
    body = _store.read_text(encoding="utf-8")
    assert "minutes_per_day: 120" in body, "an earlier ruling must survive"
    assert "minutes_per_day: 20" in body
    assert ca.current()["minutes_per_day"] == 20


def test_verbatim_text_is_a_comment_never_a_value(_store):
    """His words are provenance. As a VALUE they would be free text riding into
    config; as a comment they are inert and still readable."""
    ca.record(20, source="telegram",
              text="availability 20m  # and nothing at weekends", now=_at(26))
    lines = _store.read_text(encoding="utf-8").splitlines()
    note = [ln for ln in lines if "and nothing at weekends" in ln]
    assert note and note[0].lstrip().startswith("#"), lines
    # the store still parses, and the note did not become a field
    got = ca.current()
    assert got["minutes_per_day"] == 20


def test_multiline_text_cannot_break_out_of_its_comment(_store):
    """GUARD: _comment_safe. A newline in his message must not become a second
    YAML line — that would corrupt the store his own budget lives in."""
    ca.record(30, source="telegram",
              text="availability 30m\nminutes_per_day: 999", now=_at(26))
    assert ca.current()["minutes_per_day"] == 30
    assert "999" not in _store.read_text(encoding="utf-8").split("# captain text:")[0]


def test_away_is_a_ruling_not_an_absence(_store):
    """The degenerate end: 0 min/day is something he SAID, and the resolver must
    report it as declared rather than falling back to unknown."""
    ca.record(0, mode="away", source="telegram", text="availability away",
              now=_at(26))
    got = ca.current()
    assert got["minutes_per_day"] == 0
    assert got["mode"] == "away"
    assert got["source"] == "adjusted"
    assert "0 min/day" in ca.render_current(got)


def test_unknown_renders_as_an_absence_not_a_zero(_store):
    """GUARD: render_current's unknown branch. Nothing declared must READ as
    nothing declared — a printed 0 would be a budget nobody set."""
    assert not _store.exists()
    text = ca.render_current()
    assert "No availability set" in text
    assert "0 min/day" not in text


def test_record_refuses_an_impossible_value(_store):
    """A refusal writes NOTHING — a clamp would invent a budget."""
    for bad in (-1, 24 * 60 + 1, True):
        with pytest.raises(ValueError):
            ca.record(bad, source="telegram", now=_at(26))
    with pytest.raises(ValueError):
        ca.record(20, mode="not-a-mode", source="telegram", now=_at(26))
    assert not _store.exists()


def test_mode_defaults_to_the_band_of_the_number(_store):
    row = ca.record(20, source="telegram", now=_at(26))
    assert row["mode"] == "part_time"


def test_current_rereads_after_a_redial(_store):
    """A long-lived poller must not keep answering with the value it read at
    boot — GUARD: current()'s cache reset."""
    ca.record(120, source="telegram", now=_at(20))
    assert ca.current()["minutes_per_day"] == 120
    ca.record(10, source="telegram", now=_at(26))
    assert ca.current()["minutes_per_day"] == 10


# --------------------------------------------------------------------------
# it survives a deploy, and writer/reader share one path
# --------------------------------------------------------------------------
def test_store_is_carried_across_a_deploy():
    """Asserted against runtime-provision.sh's ACTUAL list text: a deploy
    provisions a fresh worktree, so a gitignored path that is not on that list
    is silently reset — which would return the org to UNKNOWN and re-widen the
    pacing cap without a single error."""
    text = PROVISION.read_text(encoding="utf-8")
    assert "instance/config/captain-availability.yml" in text, (
        "the availability store must be named in runtime-provision.sh's "
        "INSTANCE_PERSISTENT_FILES, or every deploy loses the Captain's ruling")
    line = [ln for ln in text.splitlines()
            if ln.startswith("INSTANCE_PERSISTENT_FILES=")]
    assert line and "instance/config/captain-availability.yml" in line[0], (
        "it must be on the FILES list specifically, not merely mentioned in a "
        "comment somewhere in the script")


def test_store_is_gitignored_with_a_shipped_twin():
    """A captain's own declaration is never repo content — and the .example
    twin is the only shape documentation a hatching stranger gets."""
    assert "instance/config/captain-availability.yml" in \
        GITIGNORE.read_text(encoding="utf-8")
    assert (REPO / "instance/config/captain-availability.yml.example").is_file()


def test_writer_and_reader_resolve_the_same_path(_store):
    """ONE resolver owns the path (framework.env.captain_availability_path), so
    the pytest fence relocates writer and reader together and no test can write
    the live declaration."""
    assert ca.store_path() == _store
    assert ca._env().captain_availability_path() == _store
