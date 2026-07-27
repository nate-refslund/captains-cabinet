"""framework.env.captain_dates() — the dated-commitment resolver.

The sibling of ``TestCaptainAvailability`` in test_env.py, in its own file
because it is a new resolver family with a store fold of its own; the CONSUMERS
are pinned separately in cabinet/scripts/tests/test_captain_dates_wiring.py and
the WRITER in cabinet/scripts/lib/tests/test_captain_dates.py.

The load-bearing cases, each a way a date could go quiet:

  * the EMPTY LIST is the documented fallback and means exactly "he has set no
    dates" — never a guessed row, never a KeyError;
  * a later row for the same id WINS (append-only), so ``date done`` closes and
    ``date move`` re-dates without editing history;
  * an INVALID row is refused rather than repaired, and the refusal errs toward
    the date staying OPEN AND VISIBLE — a mangled ``done`` row must never be the
    thing that makes a real date disappear;
  * a corrupt or unreadable store reads as empty rather than raising, because a
    resolver that threw would take the whole briefing down with it;
  * PyYAML retypes an unquoted date into ``datetime.date`` — the class that
    silently dropped every phone-written timestamp on the availability dial, so
    both shapes are pinned here;
  * the rendered LINE is louder past due, and that is asserted with an injected
    ``today`` so the arm is clock-free (a rolling window plus a fixed date is a
    calendar time-bomb).
"""
from __future__ import annotations

import pytest

from framework import env


@pytest.fixture(autouse=True)
def _dates_store(tmp_path, monkeypatch):
    """Own store per test, cache cleared, so no read answers from a sibling's
    file and no test can touch the live declaration."""
    path = tmp_path / "captain-dates.yml"
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.setenv("CABINET_CAPTAIN_DATES_FILE", str(path))
    saved = env._captain_dates_cache
    env._captain_dates_cache = None
    try:
        yield path
    finally:
        env._captain_dates_cache = saved


def _write(path, body: str):
    path.write_text(body, encoding="utf-8")
    env._captain_dates_cache = None
    return path


ONE = ("entries:\n"
       "  - id: d-aa1\n"
       "    at: 2026-07-01T09:00:00Z\n"
       "    date: 2026-08-13\n"
       '    label: "board review"\n'
       "    status: open\n"
       "    source: telegram\n")


def test_no_store_is_an_empty_list_not_a_guess(_dates_store):
    assert not _dates_store.exists()
    assert env.captain_dates() == []
    assert env.captain_open_dates() == []


def test_an_empty_store_is_also_an_empty_list(_dates_store):
    _write(_dates_store, "schema: cabinet.captain-dates/v1\nentries:\n")
    assert env.captain_dates() == []


def test_a_row_resolves_with_every_key_present(_dates_store):
    _write(_dates_store, ONE)
    rows = env.captain_dates()
    assert len(rows) == 1
    assert rows[0] == {"id": "d-aa1", "date": "2026-08-13",
                       "label": "board review", "status": "open",
                       "set_at": "2026-07-01T09:00:00Z", "source": "telegram",
                       "supersedes": None}


def test_the_env_override_is_what_the_writer_and_reader_share(_dates_store):
    assert env.captain_dates_path() == _dates_store


def test_an_unquoted_date_is_not_dropped(_dates_store):
    """PyYAML loads an unquoted 2026-08-13 as datetime.date. The availability
    dial paid for this exact class: an isinstance-str check silently dropped
    every timestamp the phone verb wrote."""
    _write(_dates_store, ONE)                 # ONE's date is unquoted
    assert env.captain_dates()[0]["date"] == "2026-08-13"
    _write(_dates_store, ONE.replace("date: 2026-08-13",
                                     'date: "2026-08-13"'))
    assert env.captain_dates()[0]["date"] == "2026-08-13"


def test_a_later_row_for_the_same_id_wins(_dates_store):
    """Append-only: `date done` and `date move` append, so the fold is what
    makes them work. A first-row reader would report a closed date as open."""
    _write(_dates_store, ONE + (
        "  - id: d-aa1\n"
        "    at: 2026-07-05T09:00:00Z\n"
        "    date: 2026-08-13\n"
        '    label: "board review"\n'
        "    status: done\n"))
    rows = env.captain_dates()
    assert len(rows) == 1 and rows[0]["status"] == "done"
    assert env.captain_open_dates() == []


def test_a_move_keeps_the_old_row_and_opens_a_new_one(_dates_store):
    _write(_dates_store, ONE.replace("status: open", "status: moved") + (
        "  - id: d-bb2\n"
        "    at: 2026-07-05T09:00:00Z\n"
        "    date: 2026-09-01\n"
        '    label: "board review"\n'
        "    status: open\n"
        "    supersedes: d-aa1\n"))
    assert {r["id"]: r["status"] for r in env.captain_dates()} == {
        "d-aa1": "moved", "d-bb2": "open"}
    live = env.captain_open_dates()
    assert len(live) == 1
    assert live[0]["date"] == "2026-09-01"
    assert live[0]["supersedes"] == "d-aa1"


def test_rows_sort_by_date_then_id(_dates_store):
    _write(_dates_store, ONE + (
        "  - id: d-bb2\n"
        "    at: 2026-07-02T09:00:00Z\n"
        "    date: 2026-07-20\n"
        '    label: "quarterly numbers"\n'
        "    status: open\n"))
    assert [r["date"] for r in env.captain_dates()] == ["2026-07-20",
                                                       "2026-08-13"]


@pytest.mark.parametrize("drop", ["id", "date", "label", "status"])
def test_a_row_missing_a_required_field_is_refused_not_repaired(_dates_store,
                                                                drop):
    """Refused, not defaulted. A row the org cannot read must read as ABSENT so
    an earlier valid row still stands — never as a deadline nobody set.

    The row is REBUILT field-by-field rather than line-deleted from a template. A
    mutation sweep (2026-07-27) caught the line-deletion version passing for the
    wrong reason: dropping the ``- id:`` line left YAML that no longer parsed as a
    LIST, so the arm went green on a parse failure instead of on the field
    guard, and stayed green when the guard was disabled."""
    fields = {"id": "d-aa1", "at": "2026-07-01T09:00:00Z",
              "date": "2026-08-13", "label": '"board review"',
              "status": "open", "source": "telegram"}
    fields.pop(drop)
    keys = list(fields)
    body = "entries:\n" + "".join(
        f"{'  - ' if k == keys[0] else '    '}{k}: {v}\n"
        for k, v in fields.items())
    _write(_dates_store, body)
    import yaml
    parsed = yaml.safe_load(body)
    assert isinstance(parsed.get("entries"), list) and \
        len(parsed["entries"]) == 1, (
            f"the fixture must still be ONE parseable row, else the arm proves "
            f"nothing about the {drop} guard: {parsed!r}")
    assert env.captain_dates() == [], drop


def test_an_impossible_date_is_refused(_dates_store):
    _write(_dates_store, ONE.replace("date: 2026-08-13",
                                     'date: "2026-02-31"'))
    assert env.captain_dates() == []


def test_an_unknown_status_is_refused_and_leaves_the_date_open(_dates_store):
    """THE DIRECTION THAT MATTERS. A garbled closing row must not be the thing
    that makes a real date vanish: the earlier open row survives, so the worst
    case is he sees a date he already closed — not a date he never sees."""
    _write(_dates_store, ONE + (
        "  - id: d-aa1\n"
        "    at: 2026-07-05T09:00:00Z\n"
        "    date: 2026-08-13\n"
        '    label: "board review"\n'
        "    status: finishedish\n"))
    live = env.captain_open_dates()
    assert len(live) == 1 and live[0]["id"] == "d-aa1"


def test_a_corrupt_store_reads_as_empty_and_never_raises(_dates_store):
    _write(_dates_store, "entries: [this is not: valid yaml: at all\n")
    assert env.captain_dates() == []
    _write(_dates_store, "entries: 7\n")
    assert env.captain_dates() == []
    _write(_dates_store, "- just\n- a\n- list\n")
    assert env.captain_dates() == []


def test_a_label_is_length_capped_on_read(_dates_store):
    long = "x" * (env.CAPTAIN_DATE_LABEL_MAX + 50)
    _write(_dates_store, ONE.replace('"board review"', f'"{long}"'))
    assert len(env.captain_dates()[0]["label"]) == env.CAPTAIN_DATE_LABEL_MAX


def test_the_cache_is_only_re_read_when_cleared(_dates_store):
    _write(_dates_store, ONE)
    assert len(env.captain_dates()) == 1
    _dates_store.unlink()
    assert len(env.captain_dates()) == 1, "module-cached, like every config read"
    env._captain_dates_cache = None
    assert env.captain_dates() == []


def test_the_caller_cannot_mutate_the_cache(_dates_store):
    _write(_dates_store, ONE)
    env.captain_dates()[0]["label"] = "tampered"
    assert env.captain_dates()[0]["label"] == "board review"


# ---------------------------------------------------------------------------
# the rendered line — one shape, every surface
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("when,today,expect", [
    ("2026-08-13", "2026-07-27", "board review: 2026-08-13 (in 17 days)"),
    ("2026-07-28", "2026-07-27", "board review: 2026-07-28 (in 1 day)"),
    ("2026-07-27", "2026-07-27", "board review: 2026-07-27 (today)"),
])
def test_render_counts_down_while_it_is_ahead(when, today, expect):
    assert env.render_captain_date(
        {"date": when, "label": "board review"}, today=today) == expect


@pytest.mark.parametrize("when,today,expect", [
    ("2026-07-26", "2026-07-27", "OVERDUE by 1 day — board review: 2026-07-26"),
    ("2026-07-20", "2026-07-27", "OVERDUE by 7 days — board review: 2026-07-20"),
])
def test_render_is_louder_past_due(when, today, expect):
    """A passed date rendered like every other row is the quietest possible
    version of the failure this store exists to prevent."""
    assert env.render_captain_date(
        {"date": when, "label": "board review"}, today=today) == expect


def test_render_never_prints_none_for_a_broken_row():
    line = env.render_captain_date({"date": "not-a-date", "label": ""},
                                   today="2026-07-27")
    assert "None" not in line
    assert "no readable date" in line
