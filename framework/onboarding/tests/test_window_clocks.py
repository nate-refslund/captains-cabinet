"""Window clocks — dates as data, anchor-else-refuse.

THE ACCEPTANCE FRAME IS PRECISION-FIRST, and that is the ruling this suite
executes rather than a preference. A briefing that states a date the operator's
file does not state is a confident wrong on the surface they trust most; a
briefing that misses one is quieter than it could be. So the estate arm below
is a CEILING with no floor — every emitted row is pinned and one new row fails
— and recall is proven on a format matrix authored independently of it.

Hermetic: tmp roots only, repo fixture data read-only, no network or
subprocess.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from framework.onboarding import estate as _estate
from framework.onboarding import genesis
from framework.onboarding import journey
from framework.onboarding import salience

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "framework" / "onboarding" / "fixtures"
NOW = "2026-08-05T09:00:00Z"


def _cite(line_no, line):
    return {"path": "note.md", "line": line_no, "excerpt": line}


def _rows(lines, *, now=NOW):
    rows, _meta = salience.file_clocks(lines, now=now, cite=_cite)
    return rows


# ── A1 — the held-out format matrix ─────────────────────────────────────────
#
# AUTHORED FRESH, and deliberately not sourced from the acceptance estate: a
# matrix copied out of the fixture it is later scored on measures whether the
# implementer transcribed carefully, not whether the grammar generalises. Each
# row is ``(text, expected ISO, writing system or calendar)`` and the tags are
# what the coverage assertion counts.
FORMAT_MATRIX = (
    ("The filing deadline is 2026-08-12 and it cannot move.", "2026-08-12", "latin-iso"),
    ("recorded_at: 2026-08-12T09:14:03Z", "2026-08-12", "latin-iso"),
    ("お支払い期日 ２０２６-０８-１２", "2026-08-12", "fullwidth"),
    ("契約日 2026年8月12日", "2026-08-12", "cjk-marked"),
    ("検査日 2026年8月12日（水）", "2026-08-12", "cjk-marked"),
    ("提出期限 令和8年8月12日", "2026-08-12", "japanese-era"),
    ("開業 令和元年8月12日", "2019-08-12", "japanese-era"),
    ("계약일 2026년 8월 12일", "2026-08-12", "hangul-marked"),
    ("Invoice raised 2026/08/12", "2026-08-12", "latin-slashed"),
    ("Shipped 8/25/2026 by courier", "2026-08-25", "latin-slashed"),
    ("Shipped 25/8/2026 by courier", "2026-08-25", "latin-slashed"),
    ("التاريخ ٢٠٢٦-٠٨-١٢", "2026-08-12", "arabic-indic-digits"),
    ("दिनांक २०२६-०८-१२", "2026-08-12", "devanagari-digits"),
)


@pytest.mark.parametrize("text,expected,tag", FORMAT_MATRIX)
def test_format_matrix_resolves(text, expected, tag):
    rows = _rows([text])
    assert len(rows) == 1, f"{tag}: expected exactly one clock in {text!r}"
    assert rows[0]["iso"] == expected
    assert rows[0]["year_from"] == "clause"
    assert rows[0]["raw"] in text, "raw must be the operator's own substring"


def test_format_matrix_is_wide_enough_to_be_a_matrix():
    """The matrix itself is a sensor and can be weakened by deletion.

    Eight formats across four writing systems or calendars is the acceptance
    bar; asserting it here is what stops a later trim from quietly making the
    parametrised arms above pass by covering less.
    """
    assert len(FORMAT_MATRIX) >= 8
    assert len({tag for _t, _e, tag in FORMAT_MATRIX}) >= 4


# ── A2 — negatives on realistic text ────────────────────────────────────────
NEGATIVES = (
    ("12/12 rooms occupied on the festival night", "ratio that is date-shaped"),
    ("本館 12/12室 満室", "occupancy count in another script"),
    ("松葉蟹 茹で・中（1杯） ¥9,800", "price"),
    ("原価率 45.6%", "percentage"),
    ("Requires the toolchain at version 8.12 or newer", "version"),
    ("TEL 0796-32-4141（平日 8:30〜17:15）", "landline that is ISO-shaped"),
    ("携帯 090-1234-5678", "mobile number"),
    ("管理番号: 2026-08-1234", "registry number with a date-shaped head"),
    ("整理番号 第 218 号", "registry number"),
    ("夕食 18:00／19:30 の2部制", "two seating times, wide solidus"),
    ("秋冬のご案内 2026-2027", "season label"),
    ("入社年月 2011年4月", "year and month with no day"),
    ("有給5日 / 10日以内", "bare day counts"),
    ("消防法第4条", "statute reference"),
    ("松葉蟹は11/6解禁", "bare slashed pair in prose"),
)


@pytest.mark.parametrize("text,why", NEGATIVES)
def test_negatives_state_no_clock(text, why):
    assert _rows([text]) == [], f"{why}: {text!r} must not become a clock"


def test_a_date_that_the_calendar_does_not_have_is_refused():
    """2026 has no 29 February, and a stated year makes that checkable."""
    assert _rows(["提出 2026年2月29日"]) == []
    assert _rows(["due 2026-02-30"]) == []
    assert _rows(["平成50年8月12日"]) == [], "an era year past the era's end"


def test_an_ambiguous_slashed_order_refuses_rather_than_picks_a_locale():
    assert _rows(["Signed 8/12/2026"]) == []
    assert len(_rows(["Signed 8/25/2026"])) == 1


# ── the row schema — structurally unable to state a relation ────────────────


def test_row_carries_exactly_the_declared_fields():
    rows = _rows(["契約日 2026年8月12日", "検査 8月20日"])
    assert rows, "the arm needs rows to be about anything"
    for row in rows:
        assert set(row) == set(salience.CLOCK_ROW_FIELDS)


def test_no_field_anywhere_can_state_a_relation():
    """The schema is the guard, so the guard is asserted, not described.

    A relation needs somewhere to live. There is no key for one, and the
    forbidden names are listed rather than implied so a future field called
    ``blocks`` or ``collides_with`` fails here before it reaches a briefing.
    """
    forbidden = {
        "relation", "relates_to", "collides_with", "collision", "conflict",
        "blocks", "blocked_by", "because", "impact", "cause",
        "pair", "with", "against", "join",
    }
    assert not (set(salience.CLOCK_ROW_FIELDS) & forbidden)
    assert len(salience.CLOCK_ROW_FIELDS) == 7


def test_the_clock_surface_never_uses_the_word_that_names_another_module():
    """A module under ``framework/fidelity/`` already owns that noun.

    One tree, one meaning per name — so this capability is called CLOCKS
    everywhere and never borrows the other module's word, which would make a
    future reader searching for either one find both. The check is a grep over
    the sections this landing added rather than over whole files, because the
    older prose in those files uses the ordinary English word legitimately.
    """
    # SPELLED IN TWO PIECES so this suite is not itself a hit — the arm would
    # otherwise have to allow one occurrence, and an allowance of one is an
    # allowance of any.
    owned = "conse" + "quence"
    salience_text = (REPO / "framework/onboarding/salience.py").read_text("utf-8")
    clock_section = salience_text.split("# --- clocks:", 1)[1]
    for name, text in (
        ("salience clock section", clock_section),
        ("this suite", Path(__file__).read_text("utf-8")),
        ("fence arm", (REPO / "framework/fidelity/tests/"
                       "test_window_clocks_fence.py").read_text("utf-8")),
    ):
        assert owned not in text.lower(), f"{name} uses the name another module owns"


def test_normalisation_is_length_preserving():
    """A match's span must point at the operator's own characters.

    The degenerate end that would break it is a character whose normalised
    form is longer than one — which is exactly what NFKC does and why this
    module does not use it here.
    """
    for text in ("２０２６年８月１２日", "٢٠٢٦-٠٨-١٢", "株式会社 ㍿ ﬁle 8月12日", ""):
        assert len(salience._clock_normalize(text)) == len(text)


# ── the year rule — anchor, else refuse ─────────────────────────────────────


def test_a_bare_month_day_takes_the_year_from_a_full_date_in_the_same_file():
    rows = _rows(["令和8年7月28日", "工事は8月18日から"])
    assert [(r["iso"], r["year_from"]) for r in rows] == [
        ("2026-07-28", "clause"), ("2026-08-18", "document_anchor"),
    ]


def test_a_bare_month_day_with_no_anchor_keeps_its_text_and_refuses_a_year():
    rows = _rows(["入稿データ 締切 8月25日", "初校 8月28日"])
    assert [r["raw"] for r in rows] == ["8月25日", "8月28日"]
    assert [r["iso"] for r in rows] == [None, None]
    assert [r["year_from"] for r in rows] == [None, None]
    assert [r["direction"] for r in rows] == [None, None]


def test_two_stated_years_leave_the_file_with_no_anchor_to_lend():
    rows = _rows(["2025年8月20日 のふりかえり", "2026年8月20日 は本番", "回収は8月21日"])
    bare = [r for r in rows if r["raw"] == "8月21日"]
    assert bare and bare[0]["iso"] is None

def test_the_year_is_never_the_run_year_and_never_the_nearest_future():
    """Both banned guesses, named, with the case each gets wrong.

    Run-year: a December note saying 1月5日 means next January. Nearest-future:
    a file about last year's festival would be dragged forward into this one,
    which is precisely the distractor the estate arm below carries.
    """
    december = _rows(["会場は1月5日"], now="2026-12-20T00:00:00Z")
    assert december[0]["iso"] is None and december[0]["year_from"] is None


def test_an_empty_marker_role_matches_nothing_rather_than_everything():
    """The degenerate end that makes a data-driven grammar dangerous.

    An empty alternation ``(?:)`` matches the EMPTY STRING, so a role nobody
    filled would become a grammar that fires between every pair of characters
    in every file. The builder answers with a never-match instead, and this is
    the arm that proves it rather than a comment claiming it.
    """
    import re

    empty = salience._marker_alternation(())
    assert re.search(empty, "2026年8月12日") is None
    assert re.search(empty, "") is None
    assert salience._marker_alternation(("年", "년")) != empty


def test_direction_is_measured_against_the_run_clock_that_is_passed_in():
    """Time is an INPUT. The same row is behind or ahead depending only on it,
    and nothing in the extractor reads the wall clock."""
    line = ["契約日 2026年8月12日"]
    assert _rows(line, now="2026-01-01T00:00:00Z")[0]["direction"] == "future"
    assert _rows(line, now="2026-12-01T00:00:00Z")[0]["direction"] == "past"
    # ...and today's own date is ahead: the day has not finished.
    assert _rows(line, now="2026-08-12T23:00:00Z")[0]["direction"] == "future"


def test_an_unusable_run_clock_leaves_every_direction_unknown():
    """A missing argument must not answer "everything is ahead of you"."""
    for bad in ("", None, "not-a-date"):
        rows = _rows(["契約日 2026年8月12日"], now=bad)
        assert rows and rows[0]["iso"] == "2026-08-12"
        assert rows[0]["direction"] is None


# ── the spine guard ────────────────────────────────────────────────────────


def test_a_calendar_shaped_file_is_marked_and_an_ordinary_one_is_not():
    rota = [f"2026年8月{day}日,通,早,遅" for day in range(1, 20)]
    rows, meta = salience.file_clocks(rota, now=NOW, cite=_cite)
    assert meta["spine"] is True
    assert all(row["spine"] for row in rows)

    letter = ["拝啓", "", "工事は2026年8月18日から行います。", "", "以上"] + ["本文"] * 6
    _rows_letter, letter_meta = salience.file_clocks(letter, now=NOW, cite=_cite)
    assert letter_meta["spine"] is False


def test_a_short_file_of_dates_is_not_a_spine():
    """The sample-size end: three dated lines is a note, not a calendar."""
    _rows_out, meta = salience.file_clocks(
        ["2026年8月1日", "2026年8月2日", "2026年8月3日"], now=NOW, cite=_cite)
    assert meta["spine"] is False


# ── A3 — the estate precision ceiling ──────────────────────────────────────
#
# EVERY ROW THE 17-FILE BLIND-AUTHORED ESTATE PRODUCES, pinned. Each was read
# against its own file by hand before it was written down: a printing
# schedule, a fire-inspection notice, a supplier's price-rise date, a
# resignation, a tax filing deadline, a festival notice and last year's
# review of the same festival. ONE new row fails this arm, which is the whole
# point — a false clock is the failure this capability is allowed to have
# least. There is NO recall floor: rows are not asserted to be complete, and
# the estate's two spreadsheets and its handover log contribute nothing
# because their dates are written in a bare slashed form this grammar refuses.
ESTATE_ROWS = (
    "パンフレット印刷.md|19|8月25日|",
    "パンフレット印刷.md|20|8月28日|",
    "パンフレット印刷.md|21|9月2日|",
    "パンフレット印刷.md|22|9月3日|",
    "パンフレット印刷.md|22|9月9日|",
    "パンフレット印刷.md|23|9月10日|",
    "仕入れメモ_蟹.md|1|2026/8/3|2026-08-03",
    "仕入れメモ_蟹.md|3|9月1日|2026-09-01",
    "仕入れメモ_蟹.md|7|2026年9月1日|2026-09-01",
    "改修工事のお知らせ.md|23|2026年8月18日|2026-08-18",
    "改修工事のお知らせ.md|23|8月25日|2026-08-25",
    "改修工事のお知らせ.md|32|8月19日|2026-08-19",
    "改修工事のお知らせ.md|32|8月24日|2026-08-24",
    "改修工事のお知らせ.md|35|8月18日|2026-08-18",
    "改修工事のお知らせ.md|41|8月8日|2026-08-08",
    "改修工事のお知らせ.md|4|令和8年7月28日|2026-07-28",
    "昨年の灯籠流し反省.md|1|2025年8月20日|2025-08-20",
    "昨年の灯籠流し反省.md|3|2025/8/22|2025-08-22",
    "消防点検通知.md|18|令和8年8月22日|2026-08-22",
    "消防点検通知.md|3|令和8年7月30日|2026-07-30",
    "消防点検通知.md|43|令和8年8月12日|2026-08-12",
    "灯籠流し案内.md|14|2026年8月20日|2026-08-20",
    "灯籠流し案内.md|16|8月21日|2026-08-21",
    "灯籠流し案内.md|22|8月14日|2026-08-14",
    "灯籠流し案内.md|35|8月14日|2026-08-14",
    "灯籠流し案内.md|3|2026年7月25日|2026-07-25",
    # ONE ROW, not two. Line 2 of this CSV writes the same day in two formats
    # ("作成 2026/7/31 …,… 2026年7月31日時点 …"), which emitted a duplicate into
    # every forward-clock list and inflated rows_found. Deduped by (resolved
    # day, line) at emission, first spelling kept — see
    # test_one_day_written_twice_on_one_line_is_one_row below, which pins both
    # directions.
    "秋会席_原価表.csv|2|2026/7/31|2026-07-31",
    "税理士より.md|22|令和8年8月31日|2026-08-31",
    "税理士より.md|27|8月20日|2026-08-20",
    "税理士より.md|33|8月17日|2026-08-17",
    "税理士より.md|4|令和8年8月3日|2026-08-03",
    "退職届_受理メモ.md|14|8月16日|2026-08-16",
    "退職届_受理メモ.md|35|8月15日|2026-08-15",
    "退職届_受理メモ.md|3|2026年8月4日|2026-08-04",
    "退職届_受理メモ.md|6|2026年8月31日|2026-08-31",
    "退職届_受理メモ.md|6|8月15日|2026-08-15",
)


def _estate_rows():
    out = []
    for path in sorted((FIXTURES / "dated-estate").iterdir()):
        rows, _meta = salience.file_clocks(
            path.read_text(encoding="utf-8").splitlines(), now=NOW, cite=_cite)
        out.extend(
            f'{path.name}|{row["line_no"]}|{row["raw"]}|{row["iso"] or ""}'
            for row in rows
        )
    return sorted(out)


def test_estate_emits_no_clock_that_is_not_a_date_statement():
    assert _estate_rows() == sorted(ESTATE_ROWS)


def test_the_estates_previous_year_file_produces_no_forward_clock():
    """The distractor the nearest-future rule would have resurrected.

    Its own two dates are last year's; if either read as ahead of the run, a
    briefing would put a festival that already happened on the operator's
    forward list.
    """
    text = (FIXTURES / "dated-estate" / "昨年の灯籠流し反省.md").read_text("utf-8")
    rows = _rows(text.splitlines())
    assert rows and all(row["direction"] == "past" for row in rows)


def test_the_estates_undated_printing_schedule_keeps_its_text():
    text = (FIXTURES / "dated-estate" / "パンフレット印刷.md").read_text("utf-8")
    rows = _rows(text.splitlines())
    assert rows and all(row["iso"] is None and row["raw"] for row in rows)


# ── cross-fixture ──────────────────────────────────────────────────────────


def test_the_employee_estates_two_iso_dates_derive():
    found = {}
    for path in sorted((FIXTURES / "enterprise-employee").rglob("*")):
        if not path.is_file():
            continue
        for row in _rows(path.read_text(encoding="utf-8", errors="replace").splitlines()):
            found.setdefault(row["iso"], row)
    assert "2026-09-30" in found and "2026-10-14" in found
    assert found["2026-09-30"]["year_from"] == "clause"


# ── A4 — degenerate ends, counted ──────────────────────────────────────────


def test_degenerate_ends():
    empty_rows, empty_meta = salience.file_clocks([], now=NOW, cite=_cite)
    assert empty_rows == [] and empty_meta["lines"] == 0
    assert empty_meta["spine"] is False and empty_meta["anchor_year"] is None

    blank_rows, blank_meta = salience.file_clocks(["", "   ", ""], now=NOW, cite=_cite)
    assert blank_rows == [] and blank_meta["lines"] == 0

    none_rows, _m = salience.file_clocks(["no dates here at all"], now=NOW, cite=_cite)
    assert none_rows == []

    one_rows, one_meta = salience.file_clocks(["due 2026-08-12"], now=NOW, cite=_cite)
    assert len(one_rows) == 1 and one_meta["anchor_year"] == 2026

    same = ["2026-08-12"] * 12
    same_rows, same_meta = salience.file_clocks(same, now=NOW, cite=_cite)
    assert len(same_rows) == 12 and same_meta["spine"] is True
    assert {row["iso"] for row in same_rows} == {"2026-08-12"}


def test_a_window_of_only_spine_files_aggregates_and_says_what_it_withheld(tmp_path):
    source = tmp_path / "rota"
    source.mkdir()
    (source / "shifts.csv").write_text(
        "\n".join(f"2026年8月{day}日,通,早" for day in range(1, 25)), encoding="utf-8")
    result = _ratify(tmp_path / "cab", source)
    clocks = result["state"]["window_clocks"]
    assert clocks["rows_found"] == 24
    assert len(clocks["rows"]) == journey._SPINE_ROWS_KEPT
    assert clocks["rows_omitted"] == 24 - journey._SPINE_ROWS_KEPT
    assert clocks["undated_rows"] == 0, "the trim must not hide unresolved rows"
    assert clocks["spine_files"][0]["earliest"] == "2026-08-01"
    assert clocks["spine_files"][0]["latest"] == "2026-08-24"
    assert "summarised rather than listed" in result["card"]["body"]


def test_an_aggregated_file_still_reports_the_dates_it_could_not_resolve(tmp_path):
    """The number must count what was FOUND, not what survived the trim.

    A rota written in bare month-days with no letterhead resolves to nothing.
    Every one of its rows is a date the operator can see and the cabinet
    cannot place, and the spine trim keeps forward rows only — so counting
    over the survivors would report zero unresolved dates for a file that is
    entirely unresolved.
    """
    source = tmp_path / "rota"
    source.mkdir()
    (source / "shifts.csv").write_text(
        "\n".join(f"8月{day}日,通,早" for day in range(1, 25)), encoding="utf-8")
    clocks = _ratify(tmp_path / "cab", source)["state"]["window_clocks"]
    assert clocks["rows_found"] == 24
    assert clocks["rows"] == [], "nothing resolved, so nothing is ahead"
    assert clocks["undated_rows"] == 24
    assert clocks["spine_files"][0]["earliest"] is None


def test_a_window_with_no_dates_renders_exactly_what_it_rendered_before(tmp_path):
    source = tmp_path / "plain"
    source.mkdir()
    (source / "notes.md") .write_text("# Notes\n\nNothing here is dated.\n", "utf-8")
    result = _ratify(tmp_path / "cab", source)
    assert result["state"]["window_clocks"]["rows"] == []
    assert journey._clocks_note(result["state"]) == ""
    assert "Dates your files state" not in result["card"]["body"]


# ── E2E — the real journey ─────────────────────────────────────────────────


def _ratify(root: Path, source: Path) -> dict:
    proposed = journey.act(
        {
            "action": "propose_window",
            "ownership": "self",
            "authority_basis": "my own machine, my own folder",
            "action_id": "propose-clocks",
            "surface": "dashboard",
            "source": str(source),
            "purpose": "Show me what my own files say is coming.",
            "relationship_destination": "reversible",
        },
        root,
        now=NOW,
    )
    return journey.act(
        {
            "action": "ratify_charter",
            "action_id": "ratify-clocks",
            "surface": "dashboard",
            "charter_hash": proposed["state"]["charter"]["hash"],
            "expected_revision": proposed["state"]["revision"],
        },
        root,
        now=NOW,
    )


def _dated_source(tmp_path: Path) -> Path:
    source = tmp_path / "sources" / "dated-estate"
    shutil.copytree(FIXTURES / "dated-estate", source)
    return source


def test_the_journey_persists_clocks_bound_to_the_manifest_it_read(tmp_path):
    root = tmp_path / "cabinet"
    result = _ratify(root, _dated_source(tmp_path))
    path = root / "instance/onboarding/v2" / journey.CLOCKS_NAME
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema"] == journey.CLOCKS_SCHEMA
    assert payload["manifest_hash"] == result["state"]["source"]["manifest_hash"]
    assert payload["rows_found"] == len(ESTATE_ROWS)
    for row in payload["rows"]:
        assert set(row) == set(salience.CLOCK_ROW_FIELDS)
        assert row["ref"]["path"] and row["ref"]["sha256"]


def test_the_dividend_card_prints_a_bounded_forward_window(tmp_path):
    result = _ratify(tmp_path / "cabinet", _dated_source(tmp_path))
    body = result["card"]["body"]
    assert "Dates your files state that are still ahead:" in body
    assert "2026-08-08 — 改修工事のお知らせ.md:41" in body
    assert "more forward date(s) are in the folder and not printed here" in body
    assert "no year, and no file they sit in states one, so I did not guess" in body
    assert body.count(" — ") >= journey._CARD_CLOCKS_SHOWN


def test_a_superseded_window_leaves_no_clocks_behind(tmp_path):
    root = tmp_path / "cabinet"
    _ratify(root, _dated_source(tmp_path))
    path = root / "instance/onboarding/v2" / journey.CLOCKS_NAME
    assert path.is_file()
    other = tmp_path / "sources" / "other"
    other.mkdir(parents=True)
    (other / "a.md").write_text("nothing dated\n", encoding="utf-8")
    journey.act(
        {
            "action": "propose_window", "ownership": "self",
            "authority_basis": "mine", "action_id": "propose-2",
            "surface": "dashboard", "source": str(other),
            "purpose": "Another look.", "relationship_destination": "reversible",
        },
        root,
        now=NOW,
    )
    assert not path.exists()
    assert _estate.load_window_clocks(root) == {}


def test_the_estate_loader_refuses_clocks_from_a_different_manifest(tmp_path):
    root = tmp_path / "cabinet"
    _ratify(root, _dated_source(tmp_path))
    assert _estate.load_window_clocks(root)["rows"]
    path = root / "instance/onboarding/v2" / journey.CLOCKS_NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["manifest_hash"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert _estate.load_window_clocks(root) == {}


# ── genesis — the REAL operator order ──────────────────────────────────────
#
# THE ORDER PRODUCTION ACTUALLY RUNS, and the one the first landing of this
# capability did not test. An operator edits the answers, re-runs the
# generator (which re-derives the proposal rows — recall is live, so quotes
# and citations bake in), and only THEN grants a folder and ratifies a window.
# The rows correctly never re-derive afterwards: the answers digest has not
# moved, and a row the operator may have edited is not genesis's to rewrite.
# So anything derived from the window at derivation time is derived from
# nothing. Measured on a live hatch: zero clock lines reached the briefing
# while a perfect 37-row artifact sat on disk. The join is at RENDER time now,
# and these arms drive the real order rather than the convenient one.


def _hatch(tmp_path):
    """A cabinet root with answers on file and a recall seam over the estate."""
    from framework.sources.local import LocalNotesSource
    import yaml

    root = tmp_path / "cabinet"
    (root / "instance/config").mkdir(parents=True, exist_ok=True)
    source = _dated_source(tmp_path)
    (root / genesis.ANSWERS_REL).write_text(yaml.safe_dump({
        "cabinet": {"id": "yamagasumi", "org_shape": "solo"},
        "captain": {"name": "高橋 美咲"},
        "lanes": [{"slug": "lodging", "name": "宿泊（本館・東館）",
                   "task_system": "none", "repos": []}],
        "mission": {"purpose": "城崎温泉の旅館を続ける", "altitude": "company"},
    }, allow_unicode=True), encoding="utf-8")
    return root, source, LocalNotesSource(str(source))


def _briefing(root, notes):
    items = genesis.genesis_intake_items(root, now=NOW, source=notes)
    return "\n".join(item["payload"]["summary"] for item in items)


def test_the_real_order_puts_the_clocks_in_front_of_the_operator(tmp_path):
    """Derive FIRST with no window, ratify SECOND, read THIRD.

    This is the arm the first landing was missing. It fails against a build
    that joins clocks at derivation time, because at derivation time there is
    nothing to join.
    """
    root, source, notes = _hatch(tmp_path)

    derived = genesis.run_genesis_proposal(root, now=NOW, source=notes)
    assert derived["status"] == "written"
    assert derived["recall"]["hits_total"] > 0, "recall must be live for a cite"
    rows = genesis._load_proposal_rows(root)
    assert all("clocks" not in row for row in rows), (
        "nothing about the window may be baked into a persisted row"
    )
    assert _briefing(root, notes).count("DATES IN THOSE FILES") == 0

    _ratify(root, source)

    body = _briefing(root, notes)
    assert "DATES IN THOSE FILES:" in body
    # The fire-inspection filing cutoff — the date the 2/3 briefing missed.
    assert "2026-08-12" in body and "消防点検通知.md:43" in body
    # ...and the window's own forward list, on the briefing rather than only
    # on the approval card the operator has already dismissed.
    assert "Dates your files state that are still ahead:" in body
    assert "not printed here" in body


def test_a_recall_reference_names_a_heading_and_still_joins():
    """The shape recall ACTUALLY produces, which whole-basename matching missed.

    Measured on a live hatch: `消防点検通知.md#消防法第4条に基づく…`. Comparing
    the whole basename made the join silently empty on every real citation.
    """
    rows = [{"raw": "令和8年8月12日", "iso": "2026-08-12", "line_no": 43,
             "ref": {"path": "消防点検通知.md", "line": 43}, "direction": "future",
             "year_from": "clause", "spine": False}]
    with_heading = genesis._clock_lines(
        {"rows": rows}, ["消防点検通知.md#消防法第4条に基づく立入検査の実施について（通知）"])
    assert with_heading and "2026-08-12" in with_heading[0]
    assert genesis._clock_lines({"rows": rows}, ["消防点検通知.md"]) == with_heading
    assert genesis._clock_lines({"rows": rows}, ["別の通知.md#見出し"]) == []


def test_a_card_whose_cited_files_state_no_date_renders_unchanged(tmp_path):
    """The earned rule, at the surface that now applies it."""
    rows = [{"raw": "令和8年8月12日", "iso": "2026-08-12", "line_no": 43,
             "ref": {"path": "消防点検通知.md", "line": 43}, "direction": "future",
             "year_from": "clause", "spine": False}]
    assert genesis._clock_lines({"rows": rows}, ["引継ぎノート.md#7-16"]) == []
    assert genesis._clock_lines({"rows": rows}, []) == []
    assert genesis._clock_lines({}, ["消防点検通知.md"]) == []
    assert genesis._clock_lines(None, ["消防点検通知.md"]) == []


def test_a_superseded_window_takes_its_clock_lines_off_the_briefing(tmp_path):
    """Staleness impossible BY CONSTRUCTION, which is why the join moved.

    A baked line would survive the window it came from. A render-time join
    reads whatever is bound at read time, so replacing the window removes the
    dates in the same breath as it removes the artifact.
    """
    root, source, notes = _hatch(tmp_path)
    genesis.run_genesis_proposal(root, now=NOW, source=notes)
    _ratify(root, source)
    assert "DATES IN THOSE FILES:" in _briefing(root, notes)

    other = tmp_path / "sources" / "elsewhere"
    other.mkdir(parents=True)
    (other / "a.md").write_text("nothing dated in here\n", encoding="utf-8")
    journey.act(
        {"action": "propose_window", "ownership": "self",
         "authority_basis": "mine", "action_id": "propose-again",
         "surface": "dashboard", "source": str(other),
         "purpose": "Another look.", "relationship_destination": "reversible"},
        root, now=NOW)

    after = _briefing(root, notes)
    assert "DATES IN THOSE FILES:" not in after
    assert "2026-08-12" not in after
    assert "Dates your files state" not in after


def test_the_card_headline_says_which_clock_it_means(tmp_path):
    """"(undated)" is true of the NOTE and was read as true of the FILE.

    An operator saw "3 of your own notes (undated)" above three files, one of
    which states a filing cutoff seven days out. The headline is about when
    the notes were WRITTEN; the line below it is about what they SAY.
    """
    root, source, notes = _hatch(tmp_path)
    genesis.run_genesis_proposal(root, now=NOW, source=notes)
    _ratify(root, source)
    body = _briefing(root, notes)
    assert "(undated)" not in body
    assert "the notes carry no date of their own" in body
    headline = next(line for line in body.splitlines()
                    if line.startswith("📜 Proposed outcome: 宿泊"))
    dates = next(line for line in body.splitlines()
                 if line.startswith("DATES IN THOSE FILES:"))
    assert body.index(headline) < body.index(dates), "the answer follows the caveat"


def test_the_briefing_and_the_card_render_one_sentence(tmp_path):
    """Two surfaces, one renderer — a second copy drifts."""
    root, source, notes = _hatch(tmp_path)
    genesis.run_genesis_proposal(root, now=NOW, source=notes)
    card_body = _ratify(root, source)["card"]["body"]
    sentence = journey.clocks_note(_estate.load_window_clocks(root)).strip()
    assert sentence and sentence in card_body
    assert sentence in _briefing(root, notes)


def test_one_day_written_twice_on_one_line_is_one_row():
    """A cell that states the same day twice states one day.

    Measured on a real dated estate: `作成 2026/7/31 …,… 2026年7月31日時点 …`
    matched twice on one line and produced two rows resolving to the same day,
    so the forward-clock list carried a visible duplicate and `rows_found`
    over-counted. Both directions are pinned here, because a dedup that also
    collapses two DIFFERENT days on one line would hide one of them — which is
    a worse defect than the duplicate it removes.
    """
    same_day, _ = salience.file_clocks(
        ["created 2026/7/31, priced as of 2026年7月31日"], now=NOW
    )
    assert [(row["raw"], row["iso"]) for row in same_day] == [("2026/7/31", "2026-07-31")]

    two_days, _ = salience.file_clocks(
        ["- 退職日　2026年8月31日付（**最終出勤日 2026年8月15日**）"], now=NOW
    )
    assert [row["iso"] for row in two_days] == ["2026-08-31", "2026-08-15"]

    # Unresolved days are never collapsed. With no year anywhere in the file
    # there is no anchor, so neither date has a position in time — and a dedup
    # keyed on "no position" would erase one unknown with another.
    unresolved, _ = salience.file_clocks(["納品 8月15日 と 9月2日"], now=NOW)
    assert [row["iso"] for row in unresolved] == [None, None]
    assert [row["raw"] for row in unresolved] == ["8月15日", "9月2日"]
