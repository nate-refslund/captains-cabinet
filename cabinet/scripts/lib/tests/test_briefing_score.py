"""The 14-day briefing-value trial instrument — cabinet/scripts/lib/briefing_score.py.

Every arm below pins a property the instrument EXISTS TO DELIVER, not an
internal invariant:

  * the Captain's score reaches disk and is still there after the next one
    (append-only, never truncating);
  * it survives a deploy — the store sits inside the directory
    runtime-provision.sh links whole, asserted against that script's actual
    text, not against a comment about it;
  * the phone grammar accepts what he'd type and refuses what he didn't mean
    (a mid-sentence "/score", "/score 32", "/score 4");
  * a re-score corrects rather than duplicates, and the correction wins;
  * silence is counted — an archived briefing with no score is reported;
  * the summary never invents a number it does not have (no trend under 4
    scores; no unscored count with no archive).

EVIDENCE NOTE (brand-new module): an absence-failure — "these tests fail
before the file exists" — is nearly worthless here, since EVERY arm would
fail on ImportError for reasons unrelated to what it claims. The real
falsification evidence for this suite is the targeted guard-mutation sweep
recorded in the landing report: each named guard in briefing_score.py is
mutated in a scratch copy and the specific arm below is shown to go red.
Arms carry a ``GUARD:`` marker naming the line they pin so that sweep stays
mechanical.

Run: cd cabinet/scripts/lib && python3.12 -m pytest tests/test_briefing_score.py -q
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import briefing_score as bs

REPO = Path(__file__).resolve().parents[4]
PROVISION = REPO / "cabinet/scripts/runtime-provision.sh"


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    """Every test gets its own instance-memory directory."""
    monkeypatch.setenv("CABINET_BRIEFING_SCORES_DIR", str(tmp_path / "memory"))
    return tmp_path / "memory"


def _archive(store: Path, *stamps: str) -> None:
    d = store / "briefings"
    d.mkdir(parents=True, exist_ok=True)
    for s in stamps:
        (d / f"briefing-{s}.md").write_text("# body\n", encoding="utf-8")


def _at(day: int, hour: int = 7) -> datetime:
    return datetime(2026, 7, day, hour, 30, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# The durability property — the one the brief called out by name.
# ---------------------------------------------------------------------------

def test_store_survives_a_deploy_per_the_actual_provisioning_script():
    """GUARD: SCORES_REL.

    The instrument is worthless if a deploy strands the Captain's fourteen
    days of scores on the old slot. Assert it against runtime-provision.sh's
    REAL text: the store's parent directory must be one of the whole-directory
    persistence links, so a file that did not exist when the release was cut
    still lands in the shared instance-data store."""
    text = PROVISION.read_text(encoding="utf-8")
    seeded = re.search(r'^INSTANCE_PERSISTENT_SEEDED_DIRS="([^"]*)"',
                       text, re.MULTILINE)
    dirs = re.search(r'^INSTANCE_PERSISTENT_DIRS="([^"]*)"', text, re.MULTILINE)
    assert seeded and dirs, "runtime-provision.sh changed shape — re-derive"
    linked = set(seeded.group(1).split()) | set(dirs.group(1).split())

    parent = str(Path(bs.SCORES_REL).parent)          # instance/memory
    assert parent in linked, (
        f"{bs.SCORES_REL} lives under {parent}, which runtime-provision.sh "
        f"does not link whole ({sorted(linked)}) — a deploy would discard "
        "the Captain's scores")


def test_store_is_not_in_a_home_a_deploy_discards():
    """GUARD: SCORES_REL. memory/tier3/ is the trap next door — gitignored and
    named by no INSTANCE_PERSISTENT_* list, so a deploy strands it."""
    assert not bs.SCORES_REL.startswith("memory/")


def test_store_is_gitignored():
    """Runtime data the Captain typed is never a committed artifact."""
    ignored = (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert bs.SCORES_REL in [ln.strip() for ln in ignored]


# ---------------------------------------------------------------------------
# The phone grammar
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,score", [
    ("/score 0", 0), ("/score 1", 1), ("/score 2", 2), ("/score 3", 3),
    ("  /score 3  ", 3), ("/SCORE 2", 2), ("/score@CabinetChairBot 1", 1),
    ("/score: 3", 3), ("/score 3 acting on the pricing row", 3),
])
def test_grammar_accepts_what_he_would_type(text, score):
    parsed = bs.parse_score_command(text)
    assert parsed is not None and parsed["score"] == score


def test_grammar_keeps_the_note():
    assert bs.parse_score_command("/score 2 knew half of it")["note"] == \
        "knew half of it"


def test_a_trailing_period_is_punctuation_not_a_decimal():
    """'/score 3. Really useful' is a sentence, not 3.5 — it must still land."""
    parsed = bs.parse_score_command("/score 3. Really useful")
    assert parsed is not None and parsed["score"] == 3


@pytest.mark.parametrize("text", [
    "/score 4", "/score 32", "/score -1", "/score", "/score x",
    "please /score 3 when you can", "score 3", "", "3",
    "/score 3.5", "/score 2,5",
])
def test_grammar_refuses_what_he_did_not_mean(text):
    """GUARD: SCORE_CMD_RE (?![0-9]) lookahead; SCORE_CMD_RE ^ + .match()
    together (the sweep showed the anchoring survives losing either one — only
    dropping BOTH opens the grammar, so the compound mutation is the honest
    falsification, not a single-line one).

    '/score 32' must NOT read as 3 with a note of '2', and a '/score' inside a
    sentence is conversation. Each refusal returns None so the caller relays
    the message instead of eating it."""
    assert bs.parse_score_command(text) is None


# ---------------------------------------------------------------------------
# Recording — the score reaches disk and stays there
# ---------------------------------------------------------------------------

def test_two_scores_both_survive(_store):
    """GUARD: open(path, "a"). A truncating write would keep only the last
    score — the failure mode that makes a 14-day trial report day 14."""
    bs.record(1, briefing_id="briefing-A")
    bs.record(3, briefing_id="briefing-B")
    lines = (_store / "briefing-scores.jsonl").read_text(
        encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert [json.loads(ln)["score"] for ln in lines] == [1, 3]


def test_record_refuses_a_score_outside_the_scale():
    """GUARD: `score not in VALID_SCORES` raise. A 4 on a 0-3 scale is a
    different instrument and would corrupt every median below it."""
    for bad in (4, -1, 10):
        with pytest.raises(ValueError):
            bs.record(bad, briefing_id="briefing-A")
    assert bs.summarize()["n"] == 0


def test_record_binds_to_the_briefing_he_just_got(_store):
    _archive(_store, "20260726-073000Z", "20260726-193000Z")
    row = bs.record(3)
    assert row["briefing_id"] == "briefing-20260726-193000Z"


def test_record_still_lands_when_no_briefing_is_archived():
    """A Captain who scored must never lose the score because the archive was
    not where we looked."""
    row = bs.record(2)
    assert row["briefing_id"] is None
    assert bs.summarize()["n"] == 1


def test_two_unbound_scores_in_the_same_second_are_two_scores():
    """GUARD: `__unbound__{idx}` collapse key.

    Keying unbound rows on their timestamp merged two distinct scores written
    in the same second into one (found by the first smoke run, 2026-07-26)."""
    now = _at(26)
    bs.record(0, now=now)
    bs.record(3, now=now)
    assert bs.summarize()["n"] == 2


# ---------------------------------------------------------------------------
# Re-scoring is a correction, not a duplicate
# ---------------------------------------------------------------------------

def test_rescoring_a_briefing_corrects_it(_store):
    """GUARD: `latest[key] = row` (last wins). Append-only storage plus
    last-row-wins reading is how a correction keeps its history without
    double-counting the briefing."""
    _archive(_store, "20260726-073000Z")
    bs.record(1, briefing_id="briefing-20260726-073000Z", now=_at(26, 8))
    bs.record(3, briefing_id="briefing-20260726-073000Z", now=_at(26, 9))
    s = bs.summarize()
    assert s["n"] == 1
    assert s["median"] == 3
    assert len((_store / "briefing-scores.jsonl").read_text(
        encoding="utf-8").strip().splitlines()) == 2   # history kept


# ---------------------------------------------------------------------------
# The summary — silence is data, and no invented numbers
# ---------------------------------------------------------------------------

def test_unscored_briefings_are_counted(_store):
    """GUARD: `if b not in scored_ids`. An unscored briefing is likely a 0;
    dropping it from the report is how a trial flatters itself."""
    _archive(_store, "20260726-073000Z", "20260726-193000Z",
             "20260727-073000Z")
    bs.record(3, briefing_id="briefing-20260726-073000Z", now=_at(26, 8))
    s = bs.summarize()
    assert s["briefings_seen"] == 3
    assert s["unscored"] == 2
    assert s["unscored_ids"] == ["briefing-20260726-193000Z",
                                 "briefing-20260727-073000Z"]


def test_no_archive_means_unscored_is_reported_as_unknown():
    """GUARD: `archive.is_dir()`. With no archive the honest answer is 'cannot
    be counted', never a reassuring zero."""
    bs.record(3)
    s = bs.summarize()
    assert s["archive_present"] is False
    assert "cannot be counted" in bs.render_summary(s)


def test_distribution_and_median(_store):
    _archive(_store, *[f"2026072{d}-073000Z" for d in range(1, 6)])
    for i, score in enumerate([0, 1, 3, 3, 2], start=1):
        bs.record(score, briefing_id=f"briefing-2026072{i}-073000Z",
                  now=_at(20 + i))
    s = bs.summarize()
    assert s["n"] == 5
    assert s["median"] == 2
    assert s["distribution"] == {"0": 1, "1": 1, "2": 1, "3": 2}


def test_no_trend_until_there_are_four_scores():
    """GUARD: `len(values) >= 4`. Three data points do not have a direction;
    printing one would be the instrument lying to the Captain."""
    for i, score in enumerate([0, 3, 3], start=1):
        bs.record(score, briefing_id=f"briefing-{i}", now=_at(20 + i))
    assert bs.summarize()["trend"] is None
    assert "not enough scores" in bs.render_summary(bs.summarize())


def test_trend_reports_the_direction():
    """GUARD: first-half/second-half medians. Rising value must read as up."""
    for i, score in enumerate([0, 0, 3, 3], start=1):
        bs.record(score, briefing_id=f"briefing-{i}", now=_at(20 + i))
    t = bs.summarize()["trend"]
    assert t["first_half_median"] == 0
    assert t["second_half_median"] == 3
    assert t["delta"] == 3
    assert "(up)" in bs.render_summary(bs.summarize())


def test_window_excludes_older_scores_and_older_briefings(_store):
    """GUARD: the `cutoff` filter on BOTH rows and archived briefings. A 14-day
    window that trimmed scores but not briefings would report every historical
    briefing as unscored."""
    now = datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc)
    _archive(_store, "20260601-073000Z", "20260725-073000Z")
    bs.record(3, briefing_id="briefing-20260601-073000Z",
              now=now - timedelta(days=55))
    bs.record(1, briefing_id="briefing-20260725-073000Z",
              now=now - timedelta(days=1))
    s = bs.summarize(days=14, now=now)
    assert s["n"] == 1
    assert s["briefings_seen"] == 1
    assert s["unscored"] == 0


def test_days_zero_means_an_empty_window_not_everything():
    """GUARD: `days is not None`. Reinterpreting a caller's 0 as 'all' is a
    quiet argument-rewrite — the reader would trust a number it never asked
    for."""
    now = datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc)
    bs.record(3, briefing_id="briefing-A", now=now - timedelta(hours=6))
    assert bs.summarize(days=0, now=now)["n"] == 0
    assert bs.summarize(days=1, now=now)["n"] == 1
    assert bs.summarize(now=now)["n"] == 1


def test_a_corrupt_line_is_counted_not_silently_dropped(_store):
    bs.record(3, briefing_id="briefing-A")
    with open(_store / "briefing-scores.jsonl", "a", encoding="utf-8") as fh:
        fh.write("{not json\n")
        fh.write(json.dumps({"score": 9}) + "\n")
    s = bs.summarize()
    assert s["n"] == 1
    assert s["malformed_rows"] == 2
    assert "unreadable" in bs.render_summary(s)


def test_empty_store_reports_nothing_rather_than_zero():
    s = bs.summarize()
    assert s["n"] == 0 and s["median"] is None
    assert "No briefings scored yet." in bs.render_summary(s)


# ---------------------------------------------------------------------------
# Round-trip: the reply he sends → the number the summary reports
# ---------------------------------------------------------------------------

def test_reply_to_summary_round_trip(_store):
    """The whole instrument in one arm: a typed reply becomes a durable row
    becomes a reported median."""
    _archive(_store, "20260726-073000Z")
    parsed = bs.parse_score_command("/score 3 I'd the pricing row is wrong")
    bs.record(parsed["score"], note=parsed["note"], source="telegram")
    s = bs.summarize()
    assert s["n"] == 1 and s["median"] == 3 and s["unscored"] == 0
    row = json.loads((_store / "briefing-scores.jsonl").read_text(
        encoding="utf-8").strip())
    assert row["source"] == "telegram"
    assert row["briefing_id"] == "briefing-20260726-073000Z"
    assert row["note"] == "I'd the pricing row is wrong"


def test_cli_score_and_summary_round_trip(capsys, _store):
    _archive(_store, "20260726-073000Z")
    assert bs.main(["score", "3"]) == 0
    assert bs.main(["reply", "/score 1 thin"]) == 0
    assert bs.main(["summary"]) == 0
    out = capsys.readouterr().out
    assert "2 briefings scored" not in out      # same briefing, corrected
    assert "1 briefing scored" in out
    assert "median 1" in out


def test_cli_reply_refuses_a_non_command(capsys):
    assert bs.main(["reply", "hello there"]) == 2
    assert bs.summarize()["n"] == 0


def test_nothing_schedules_this():
    """The brief's hard limit: an instrument, not a metrics pipeline. No
    services.yml row, no launchd plist, may not be wired to either."""
    services = (REPO / "cabinet/services.yml").read_text(encoding="utf-8")
    assert "briefing_score" not in services
    assert "briefing-score" not in services
    assert not list((REPO / "cabinet/launchd").glob("*score*"))
