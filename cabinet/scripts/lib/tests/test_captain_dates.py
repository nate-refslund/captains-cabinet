"""The Captain's dated commitments — cabinet/scripts/lib/captain_dates.py.

Every arm pins a property the store EXISTS TO DELIVER, not an internal invariant:

  * the phone grammar accepts what he would actually type ("date 2026-08-13 board
    review", "dates", "date done board", "date move board 2026-09-01") and
    REFUSES what he did not mean (a mid-sentence mention, an impossible calendar
    date, a bare date with no label) — a refusal returns None so the poller
    relays his words instead of eating them;
  * a date the store cannot represent is never REPAIRED — 2026-02-31 comes back
    to him rather than becoming the 28th;
  * the ruling reaches disk append-only, and the LATEST row per id is what the
    resolver serves, so `done` and `move` work without editing history;
  * a `move` keeps BOTH rows and links them, because "what did he originally say
    and when did it change" has to stay answerable;
  * his label is the ONE free-text field that becomes a value, and it cannot
    break out of its YAML scalar (a newline or a quote in his message must not
    corrupt the store his own dates live in);
  * a selector that matches nothing, or several rows, changes NOTHING and gets a
    precise answer — closing the wrong date is worse than refusing;
  * ZERO dates renders as an absence, never a placeholder row;
  * it survives a deploy: the store is named in runtime-provision.sh's
    persistence list, asserted against that script's actual text rather than
    against a comment about it;
  * writer and reader agree on ONE path (framework.env.captain_dates_path), so a
    fenced test can never touch the live store.

EVIDENCE NOTE (brand-new module): "these tests fail before the file exists" is
worthless here — every arm would fail on ImportError for reasons unrelated to
what it claims. The falsification evidence is the guard-mutation sweep recorded
in the landing report; arms carry ``GUARD:`` markers naming what they pin. The
arms that ARE red against pre-change code live in
cabinet/scripts/tests/test_captain_dates_wiring.py (the briefing consumer).

Run: cd cabinet/scripts/lib && python3.12 -m pytest tests/test_captain_dates.py -q
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

import captain_dates as cd

REPO = Path(__file__).resolve().parents[4]
PROVISION = REPO / "cabinet/scripts/runtime-provision.sh"
GITIGNORE = REPO / ".gitignore"


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    """Every test gets its own store, and the resolver cache is cleared so a
    read never answers from a sibling test's file."""
    path = tmp_path / "captain-dates.yml"
    monkeypatch.setenv("CABINET_CAPTAIN_DATES_FILE", str(path))
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    cd._env()._captain_dates_cache = None
    return path


def _at(day: int, hour: int = 9) -> datetime:
    return datetime(2026, 7, day, hour, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# grammar
# --------------------------------------------------------------------------
@pytest.mark.parametrize("text,when,label", [
    ("date 2026-08-13 board review", "2026-08-13", "board review"),
    ("/date 2026-08-13 board review", "2026-08-13", "board review"),
    ("dates 2026-08-13 board review", "2026-08-13", "board review"),
    ("  date: 2026-08-13  board review  ", "2026-08-13", "board review"),
    ("DATE 2026-12-31 year end", "2026-12-31", "year end"),
    ("date 2028-02-29 leap day", "2028-02-29", "leap day"),
])
def test_grammar_accepts_an_add_he_would_type(text, when, label):
    """GUARD: _CMD_RE + _ADD_RE + parse_date_value."""
    got = cd.parse_dates_command(text)
    assert got == {"kind": "add", "date": when, "label": label,
                   "text": text.strip()[:cd.TEXT_MAX]}


@pytest.mark.parametrize("text", ["dates", "/dates", "  dates  ", "dates?",
                                  "date ?", "DATES"])
def test_grammar_accepts_the_list_verb(text):
    """GUARD: _LIST_RE + _QUERY_RE."""
    assert cd.parse_dates_command(text) == {"kind": "list"}


@pytest.mark.parametrize("text,selector", [
    ("date done board", "board"),
    ("date done d-aa1", "d-aa1"),
    ("date done board review", "board review"),
    ("DATE DONE Board", "Board"),
])
def test_grammar_accepts_done_with_an_id_or_label_prefix(text, selector):
    """GUARD: _DONE_RE. The selector may carry spaces — it is a label prefix he
    retypes from a briefing line, and it is only ever matched against."""
    got = cd.parse_dates_command(text)
    assert got["kind"] == "done" and got["selector"] == selector


@pytest.mark.parametrize("text,selector,when", [
    ("date move board 2026-09-01", "board", "2026-09-01"),
    ("date move board review 2026-09-01", "board review", "2026-09-01"),
    ("date move d-aa1 2026-09-01", "d-aa1", "2026-09-01"),
])
def test_grammar_accepts_move_with_the_date_last(text, selector, when):
    """GUARD: _MOVE_RE. The ISO date anchors the tail, which is what lets the
    selector keep its spaces without ambiguity."""
    got = cd.parse_dates_command(text)
    assert got["kind"] == "move"
    assert got["selector"] == selector and got["date"] == when


@pytest.mark.parametrize("text", [
    "I think date 2026-08-13 board review is fine",  # mid-sentence
    "so date 2026-08-13 board review",   # PREFIXED — only the START anchor
                                         # rejects this one; the tail anchor and
                                         # the arg shape both accept it, so it is
                                         # the arm that makes the anchor
                                         # falsifiable at all
    "dates are hard to keep",            # a sentence starting with the word
    "date",                              # no argument at all
    "dates 2026-08-13",                  # a date with no label: not renderable
    "date 2026-08-13",                   # same, singular
    "date soon board review",            # not a date
    "date 2026-02-31 board review",      # impossible day: refuse, not repair
    "date 2026-02-29 board review",      # not a leap year: refuse, not repair
    "date 2026-13-01 board review",      # impossible month
    "date 1926-08-13 board review",      # outside the sanity window: a typo
    "date 13-08-2026 board review",      # wrong order
    "date move board soon",              # move with no date
    "date done",                         # done with no selector
    "",
])
def test_grammar_refuses_what_he_did_not_mean(text):
    """GUARD: the anchoring + calendar + required-field guards. A refusal is
    None so the poller falls through and RELAYS — never silently eats a
    message."""
    assert cd.parse_dates_command(text) is None


def test_an_impossible_date_is_refused_rather_than_snapped():
    """The paid rule from /score and the availability dial: a value the
    instrument cannot represent is REFUSED so he retypes it, never quietly
    changed into a different one."""
    assert cd.parse_date_value("2026-02-31") is None
    assert cd.parse_date_value("2026-02-28") == "2026-02-28"


# --------------------------------------------------------------------------
# write
# --------------------------------------------------------------------------
def test_add_lands_on_disk_and_the_resolver_serves_it(_store):
    row = cd.record_add("2026-08-13", "board review", source="telegram",
                        text="date 2026-08-13 board review", now=_at(27))
    assert _store.is_file()
    assert row["date"] == "2026-08-13" and row["status"] == "open"
    assert row["at"] == "2026-07-27T09:00:00Z"
    live = cd.open_dates()
    assert len(live) == 1
    assert live[0]["id"] == row["id"]
    assert live[0]["label"] == "board review"
    assert live[0]["set_at"] == "2026-07-27T09:00:00Z"


def test_done_appends_and_the_open_list_shrinks(_store):
    """GUARD: record_done + the resolver's latest-row-per-id fold. History has
    to survive — an edit-in-place would erase what he originally said."""
    row = cd.record_add("2026-08-13", "board review", now=_at(27))
    cd.record_done(cd.resolve("board"), text="date done board", now=_at(28))
    body = _store.read_text(encoding="utf-8")
    assert body.count(f"id: {row['id']}") == 2, "the open row must survive"
    assert "status: open" in body and "status: done" in body
    assert cd.open_dates() == []
    assert [r["status"] for r in cd.current()] == ["done"]


def test_move_keeps_both_rows_and_links_them(_store):
    old = cd.record_add("2026-08-13", "board review", now=_at(27))
    new = cd.record_move(cd.resolve("board"), "2026-09-01",
                         text="date move board 2026-09-01", now=_at(28))
    assert new["id"] != old["id"]
    assert new["supersedes"] == old["id"]
    states = {r["id"]: r["status"] for r in cd.current()}
    assert states == {old["id"]: "moved", new["id"]: "open"}
    live = cd.open_dates()
    assert len(live) == 1 and live[0]["date"] == "2026-09-01"
    assert live[0]["label"] == "board review", "a move keeps his own words"


def test_the_original_date_stays_readable_after_a_move(_store):
    """The whole reason a move is two rows: "what did he originally say, and when
    did it change?" must stay answerable from the store alone."""
    cd.record_add("2026-08-13", "board review", now=_at(27))
    cd.record_move(cd.resolve("board"), "2026-09-01", now=_at(28))
    body = _store.read_text(encoding="utf-8")
    assert "date: 2026-08-13" in body and "date: 2026-09-01" in body


def test_a_newline_in_his_label_cannot_break_out_of_the_scalar(_store):
    """GUARD: sanitize_label. A newline in his message must not become a second
    PHYSICAL line in the store his own dates live in.

    The resolved value is NOT the falsifiable part — a YAML double-quoted scalar
    legally folds an embedded line break to a space, so the parse survives either
    way (measured by a mutation sweep, 2026-07-27). The FILE SHAPE is: without the
    strip, the store gains a column-0 line, and the next appended entry lands
    after it. Asserting the shape is what pins the guard."""
    cd.record_add("2026-08-13", 'board review\nstatus: done', now=_at(27))
    lines = _store.read_text(encoding="utf-8").splitlines()
    assert [ln for ln in lines if ln.startswith("    label:")] == [
        '    label: "board review status: done"'], lines
    assert not [ln for ln in lines if ln.startswith("status:")], lines
    live = cd.open_dates()
    assert len(live) == 1 and live[0]["status"] == "open"
    assert live[0]["label"] == "board review status: done"


def test_a_quote_in_his_label_cannot_terminate_the_scalar(_store):
    cd.record_add("2026-08-13", 'the "big" review', now=_at(27))
    live = cd.open_dates()
    assert len(live) == 1 and live[0]["label"] == 'the "big" review'


def test_a_long_label_is_capped_at_the_writer(_store):
    cap = cd._env().CAPTAIN_DATE_LABEL_MAX
    row = cd.record_add("2026-08-13", "y" * (cap + 40), now=_at(27))
    assert len(row["label"]) == cap
    assert len(cd.open_dates()[0]["label"]) == cap


def test_verbatim_text_is_a_comment_never_a_value(_store):
    """His sentence is provenance. As a VALUE it would be free text riding into
    config; as a comment it is inert and still readable."""
    cd.record_add("2026-08-13", "board review",
                  text="date 2026-08-13 board review # and tell the team",
                  now=_at(27))
    lines = _store.read_text(encoding="utf-8").splitlines()
    note = [ln for ln in lines if "tell the team" in ln]
    assert note and note[0].lstrip().startswith("#"), lines
    assert cd.open_dates()[0]["label"] == "board review"


def test_record_refuses_an_impossible_value(_store):
    """A refusal writes NOTHING — a repair would invent a date."""
    for bad in ("2026-02-31", "1926-08-13", "not-a-date"):
        with pytest.raises(ValueError):
            cd.record_add(bad, "board review", now=_at(27))
    with pytest.raises(ValueError):
        cd.record_add("2026-08-13", "   ", now=_at(27))
    assert not _store.exists()


def test_re_adding_the_identical_row_folds_instead_of_twinning(_store):
    """GUARD: mint_id is content-derived. A duplicate send (a retried poller
    delivery) must not put the same date in front of him twice."""
    a = cd.record_add("2026-08-13", "board review", now=_at(27))
    b = cd.record_add("2026-08-13", "board review", now=_at(27))
    assert a["id"] == b["id"]
    assert len(cd.open_dates()) == 1


# --------------------------------------------------------------------------
# resolution — refuse, never guess
# --------------------------------------------------------------------------
def test_a_selector_matching_nothing_changes_nothing(_store):
    cd.record_add("2026-08-13", "board review", now=_at(27))
    with pytest.raises(cd.NoMatch):
        cd.resolve("quarterly")
    assert len(cd.open_dates()) == 1


def test_an_ambiguous_selector_refuses_and_names_the_candidates(_store):
    """GUARD: resolve's >1 branch. Closing the wrong date is worse than
    refusing, so ambiguity is an answer, not a coin flip."""
    cd.record_add("2026-08-13", "board review", now=_at(27))
    cd.record_add("2026-09-01", "board offsite", now=_at(27, 10))
    with pytest.raises(cd.Ambiguous) as got:
        cd.resolve("board")
    assert len(got.value.matches) == 2
    reply = cd.render_miss(got.value)
    assert "more than one" in reply and "nothing changed" in reply
    for r in got.value.matches:
        assert r["id"] in reply


def test_an_already_closed_date_says_so_rather_than_nothing_found(_store):
    cd.record_add("2026-08-13", "board review", now=_at(27))
    cd.record_done(cd.resolve("board"), now=_at(28))
    with pytest.raises(cd.NoMatch) as got:
        cd.resolve("board")
    assert got.value.closed is not None
    assert "already done" in cd.render_miss(got.value)


def test_a_prefix_matches_but_a_substring_does_not(_store):
    """GUARD: _matches uses startswith. A substring match would let one letter
    hit every label that happens to contain it."""
    cd.record_add("2026-08-13", "board review", now=_at(27))
    assert cd.resolve("boa")["label"] == "board review"
    with pytest.raises(cd.NoMatch):
        cd.resolve("review")


def test_an_empty_selector_never_matches_everything(_store):
    cd.record_add("2026-08-13", "board review", now=_at(27))
    with pytest.raises(cd.NoMatch):
        cd.resolve("   ")


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------
def test_zero_dates_renders_as_an_absence_not_an_empty_header(_store):
    """GUARD: render_open's empty branch. Nothing set must READ as nothing set —
    an empty list header, or a placeholder row, would be worse than silence."""
    text = cd.render_open()
    assert "No dates set" in text
    assert "•" not in text


def test_the_list_reply_is_louder_past_due_and_carries_the_id(_store):
    cd.record_add("2026-07-20", "quarterly numbers", now=_at(20))
    cd.record_add("2026-08-13", "board review", now=_at(27))
    text = cd.render_open(today="2026-07-27")
    assert "OVERDUE by 7 days — quarterly numbers: 2026-07-20" in text
    assert "board review: 2026-08-13 (in 17 days)" in text
    for r in cd.open_dates():
        assert f"[{r['id']}]" in text, "he needs a handle he can retype"


def test_apply_command_round_trips_every_verb(_store):
    """The shared path the phone and the terminal both take, so they cannot
    diverge into two behaviours."""
    code, msg = cd.apply_command(
        cd.parse_dates_command("date 2026-08-13 board review"), "telegram")
    assert code == 0 and "Date set" in msg
    code, msg = cd.apply_command(cd.parse_dates_command("dates"), "telegram")
    assert "board review" in msg
    code, msg = cd.apply_command(
        cd.parse_dates_command("date move board 2026-09-01"), "telegram")
    assert "Moved" in msg and "2026-09-01" in msg
    code, msg = cd.apply_command(
        cd.parse_dates_command("date done board"), "telegram")
    assert "Closed" in msg
    assert cd.open_dates() == []
    # and a miss changes nothing while still answering him
    code, msg = cd.apply_command(
        cd.parse_dates_command("date done nothing-like-this"), "telegram")
    assert code == 0 and "nothing changed" in msg


def test_current_rereads_after_a_write(_store):
    """A long-lived poller must not keep answering with what it read at boot —
    GUARD: the cache reset in every writer plus current()."""
    cd.record_add("2026-08-13", "board review", now=_at(27))
    assert len(cd.open_dates()) == 1
    cd.record_add("2026-09-01", "quarterly numbers", now=_at(27, 10))
    assert len(cd.open_dates()) == 2


# --------------------------------------------------------------------------
# it survives a deploy, and writer/reader share one path
# --------------------------------------------------------------------------
def test_store_is_carried_across_a_deploy():
    """Asserted against runtime-provision.sh's ACTUAL list text: a deploy
    provisions a fresh worktree, so a gitignored path that is not on that list is
    silently reset — which would drop every date he set out of every briefing,
    and would fail SILENTLY (an empty store is a legal state)."""
    text = PROVISION.read_text(encoding="utf-8")
    line = [ln for ln in text.splitlines()
            if ln.startswith("INSTANCE_PERSISTENT_FILES=")]
    assert line and "instance/config/captain-dates.yml" in line[0], (
        "it must be on the FILES list specifically, not merely mentioned in a "
        "comment somewhere in the script")


def test_store_is_gitignored_with_a_shipped_twin():
    """A captain's own calendar is never repo content — and the .example twin is
    the only shape documentation a hatching stranger gets."""
    assert "instance/config/captain-dates.yml" in \
        GITIGNORE.read_text(encoding="utf-8")
    assert (REPO / "instance/config/captain-dates.yml.example").is_file()


def test_the_egg_deletes_the_live_store_and_ships_the_twin():
    """A fresh cabinet must hatch holding NOBODY's dates."""
    manifest = (REPO / "cabinet/scripts/egg-export-manifest.txt").read_text(
        encoding="utf-8").splitlines()
    assert "delete instance/config/captain-dates.yml" in manifest
    assert "expect-present instance/config/captain-dates.yml.example" in manifest


def test_writer_and_reader_resolve_the_same_path(_store):
    """ONE resolver owns the path (framework.env.captain_dates_path), so the
    pytest fence relocates writer and reader together and no test can write the
    live store."""
    assert cd.store_path() == _store
    assert cd._env().captain_dates_path() == _store


def test_the_example_twin_parses_and_folds_the_way_it_documents(_store,
                                                               monkeypatch):
    """The twin is documentation a stranger relies on; if the resolver cannot
    read it, the documentation is wrong."""
    twin = REPO / "instance/config/captain-dates.yml.example"
    monkeypatch.setenv("CABINET_CAPTAIN_DATES_FILE", str(twin))
    env = cd._env()
    env._captain_dates_cache = None
    rows = {r["id"]: r["status"] for r in env.captain_dates()}
    assert rows, "the twin must parse"
    assert "moved" in rows.values() and "done" in rows.values(), rows
    live = env.captain_open_dates()
    assert len(live) == 1, f"the twin documents exactly one live date: {live}"
    assert live[0]["supersedes"], "the surviving row is the moved one's successor"
