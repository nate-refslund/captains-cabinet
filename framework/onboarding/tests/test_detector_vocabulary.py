"""The detector labels are DATA — one defect, four detectors, two directions.

WHAT WAS MEASURED. A live agnostic-proof hatch on 2026-07-30 gave a fresh
First Window a Japanese operator's estate — seventeen ``.md``/``.csv``/``.txt``
files, a real folder, a ratified Charter — and the dividend came back
``orientation_map``: *"no contradiction, broken documented command, or explicit
urgent marker"*. The folder was full of them. Every detector LABEL was an
inline English literal in framework code, so 至急 (urgent), 期限 (deadline),
完了 (done) and a CSV headed 件名/状態 could not fire anything, and the
strongest negative this module can print was reached by being unreadable
rather than by being clean.

  journey._contradictions   launch|go-live|deadline|delivery date
  journey._risk_markers     urgent|blocked|overdue|needs action|action required
                            status|state|priority   ·   todo|fixme|xxx
  journey._untracked_…      todo|fixme|blocked|…|follow-up   ·  done|closed|…
  journey._tracker_rows     title|summary|name|…  ·  status|state|stage|…

EVERY DEFECT ARM HERE GOES THROUGH AN ENTRY POINT THAT PREDATES THE FIX, and
the deployment root is steered with ``CABINET_ROOT`` — an environment variable
this module already read — rather than with a new keyword. So this file RUNS
against origin/master and fails on its assertions rather than erroring on an
import: an arm that cannot execute against the old code proves the code is
old, not that the sensor works. Measured against origin/master (4fd9b2b4) with
every ``__pycache__`` removed: 30 failed, 23 passed — and the 23 that pass are
every English pin, which is what a pin is for.

FIVE ARMS CANNOT BE WRITTEN THAT WAY, named here rather than left for a reader
to discover: ``test_a_role_this_module_does_not_define_is_ignored``,
``test_an_empty_vocabulary_role_matches_nothing``,
``test_emptying_one_role_silences_exactly_what_that_role_feeds``,
``test_a_blank_or_whitespace_label_is_dropped_…`` and
``test_no_detector_carries_a_non_english_label_…``. Each grades a NAME that did
not exist, so pre-change they raise ``AttributeError`` — the weaker proof, and
the reason the defect arms above were written to avoid needing one.

THE ENGLISH PINS ARE THE OTHER HALF. Moving labels out of a regex re-reads
every estate at once, so each detector carries an arm that writes the RETIRED
pattern out inline as the oracle and asserts English input still reads
identically. The oracles are dead in the tree and live here, which is the one
place they can no longer rot into the thing they grade.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from framework.onboarding import journey  # noqa: E402

# The label sets this landing removed from the detector bodies, kept HERE as
# the oracle for the English pins.
_OLD_CONTRADICTION_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(launch(?:\s+date)?|go[- ]?live(?:\s+date)?|deadline"
    r"|delivery\s+date)\s*[:=-]\s*(.+?)\s*$",
    re.I,
)
_OLD_URGENT_RE = re.compile(
    r"^(?:(?:urgent|blocked|overdue|needs action|action required)\s*(?::|[-–—]\s|$)"
    r"|(?:status|state|priority)\s*:\s*"
    r"(?:urgent|blocked|overdue|needs action|action required)\b)",
    re.I,
)
_OLD_TODO_RE = re.compile(r"^(?:todo|fixme|xxx)\s*(?::|[-–—(]|$)", re.I)
_OLD_COMMITMENT_RE = re.compile(
    r"^(?:todo|fixme|blocked|blocker|action required|needs action|follow[- ]up)"
    r"\s*[:\-–—]\s*(.+)$",
    re.I,
)
_OLD_CLOSED_STATUSES = frozenset({
    "done", "closed", "complete", "completed", "resolved", "shipped", "merged",
    "cancelled", "canceled", "wontfix", "won't fix", "released", "archived",
})
_OLD_EXPORT_TITLE_COLUMNS = ("title", "summary", "name", "subject", "task", "issue")
_OLD_EXPORT_STATUS_COLUMNS = ("status", "state", "stage", "resolution")
_OLD_EXPORT_ID_COLUMNS = ("id", "key", "ticket", "number", "ref")


def _entry(path: str, text: str) -> dict:
    return {"path": path, "sha256": "0" * 64, "lines": text.splitlines()}


def _kinds(findings) -> list[str]:
    return [finding["kind"] for finding in findings]


@pytest.fixture
def framework_only(tmp_path, monkeypatch):
    """A deployment root with NO instance vocabulary, pinned by env.

    Without this the arms below would read whatever the checkout they run in
    happens to carry at ``instance/config/detector-vocabulary.yml``, which is
    the "the test environment guarantees something production does not"
    failure in its most literal form — an operator's own additions could make
    a framework-default arm pass. ``CABINET_ROOT`` is what ``journey`` already
    resolves the deployment root with, so steering it needs no new seam.
    """
    root = tmp_path / "deployment"
    root.mkdir()
    monkeypatch.setenv("CABINET_ROOT", str(root))
    return root


def _with_instance_vocabulary(root: Path, body: str) -> Path:
    # The module's own constant, never a re-spelling of it: a test that names
    # the path itself would keep passing after the production path moved.
    path = root / journey.INSTANCE_VOCABULARY_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


# ── 1. the measured defect: a Japanese estate is not an empty one ────────────


def test_a_japanese_attention_line_is_an_attention_marker(framework_only):
    """至急 IS "urgent". It could not fire any detector, so the card said the
    folder held nothing needing the Captain."""
    entry = _entry("docs/連絡.md", "至急: 保険証券の名義変更が必要です\n")
    findings = journey._risk_markers([entry])
    assert _kinds(findings) == ["attention_marker"]
    citation = findings[0]["citations"][0]
    assert citation["path"] == "docs/連絡.md" and citation["line"] == 1
    assert "至急" in citation["excerpt"]


def test_a_japanese_status_field_line_is_an_attention_marker(framework_only):
    """The second arm of the same detector: ``<field>: <label>``. Both halves
    were English literals, so a Japanese status line matched neither."""
    assert _kinds(journey._risk_markers([_entry("a.md", "状態：至急\n")])) == [
        "attention_marker"
    ]
    assert _kinds(journey._risk_markers([_entry("a.md", "優先度: 緊急\n")])) == [
        "attention_marker"
    ]


def test_a_bracketed_japanese_marker_is_read_like_a_bracketed_latin_one(
    framework_only,
):
    """【至急】 is [URGENT] written in another script — the same scaffolding
    role the Latin grammar already strips."""
    assert _kinds(journey._risk_markers([_entry("a.md", "【至急】名義変更\n")])) == [
        "attention_marker"
    ]


def test_a_japanese_open_work_marker_is_found(framework_only):
    for line in ("未対応: 名義変更", "要修正: 住所の誤り", "宿題: 遺産分割の確認"):
        assert _kinds(journey._risk_markers([_entry("a.md", line + "\n")])) == [
            "open_work_marker"
        ], line


def test_a_full_width_todo_folds_onto_the_latin_one(framework_only):
    """A Japanese keyboard writes ＴＯＤＯ and ：. Case folding is an ASCII
    habit; width folding is the half of it nobody remembers."""
    assert _kinds(journey._risk_markers([_entry("a.md", "ＴＯＤＯ：名義変更\n")])) == [
        "open_work_marker"
    ]


def test_two_japanese_deadlines_across_two_files_conflict(framework_only):
    """The contradiction detector's KEY was English and its VALUE is an opaque
    string. Only the key had to move — two differing dates still conflict
    without anything parsing a date."""
    findings = journey._contradictions([
        _entry("docs/計画.md", "期限: 2026-08-12\n"),
        _entry("docs/契約.md", "期限: 2026-08-25\n"),
    ])
    assert _kinds(findings) == ["conflicting_commitment"]
    assert {c["path"] for c in findings[0]["citations"]} == {
        "docs/計画.md", "docs/契約.md",
    }


def test_the_same_japanese_deadline_written_two_widths_is_not_a_contradiction(
    framework_only,
):
    """The value stays opaque, but it is NORMALISED opaque. ２０２６-０８-１２ and
    2026-08-12 are one date, and reporting them as a conflict would be a
    finding manufactured by the reader."""
    assert journey._contradictions([
        _entry("a.md", "期限: 2026-08-12\n"),
        _entry("b.md", "期限：２０２６-０８-１２\n"),
    ]) == []


def test_the_longer_japanese_key_wins_over_the_key_inside_it(framework_only):
    """提出期限 contains 期限. A shortest-first alternation would file both
    under the shorter key and invent a conflict between two unrelated dates."""
    assert journey._contradictions([
        _entry("a.md", "提出期限: 2026-08-12\n"),
        _entry("b.md", "期限: 2026-08-25\n"),
    ]) == []


def test_a_japanese_headed_export_parses_as_a_tracker(framework_only):
    """Recognised by SHAPE, never by filename — but "shape" was three English
    column vocabularies, so a Japanese export was not a tracker at all."""
    rows = journey._tracker_rows(
        _entry("t.csv", "番号,件名,状態\nENG-1,請求書の移行,対応中\nENG-2,採用ページ,完了\n")
    )
    assert rows == [
        {"id": "ENG-1", "title": "請求書の移行", "status": "対応中"},
        {"id": "ENG-2", "title": "採用ページ", "status": "完了"},
    ]


def test_a_japanese_export_written_as_json_parses_too(framework_only):
    rows = journey._tracker_rows(_entry(
        "t.json",
        json.dumps([{"番号": "T-1", "タイトル": "名義変更", "ステータス": "対応中"}],
                   ensure_ascii=False),
    ))
    assert rows == [{"id": "T-1", "title": "名義変更", "status": "対応中"}]


def test_a_japanese_commitment_no_open_row_accounts_for_is_found(framework_only):
    """The join, with BOTH halves in Japanese. Its content tokens already read
    any script (2026-07-30); its prefix vocabulary and its tracker columns did
    not, so it still could not run on this estate."""
    prose = _entry("docs/計画.md", "至急: 保険証券の名義変更を完了する\n")
    export = _entry("t.csv", "番号,件名,状態\nENG-1,採用ページの更新,対応中\n")
    findings, state = journey._untracked_commitment([prose, export])
    assert state["ran"] is True and state["open_rows_checked"] == 1
    assert _kinds(findings) == ["untracked_commitment"]
    assert {c["path"] for c in findings[0]["citations"]} == {"docs/計画.md", "t.csv"}


def test_a_japanese_open_row_saying_the_same_thing_silences_the_claim(
    framework_only,
):
    """Composes with the shared segmentation seam: in a script that writes no
    spaces the match is on the run and its character bigrams, so a row phrased
    the same way shares well over the two tokens the join requires."""
    prose = _entry("docs/計画.md", "至急: 保険証券の名義変更を完了する\n")
    tracked = _entry("t.csv", "番号,件名,状態\nENG-1,保険証券の名義変更,対応中\n")
    findings, state = journey._untracked_commitment([prose, tracked])
    assert state["ran"] is True and findings == []


def test_a_japanese_closed_status_suppresses_exactly_like_done(framework_only):
    """完了 closes a row. Until it did, every finished row in a Japanese
    tracker counted as open — the join's assertion ("no open row accounts for
    this") measured against a set that could never shrink."""
    tracked = _entry("t.csv", "番号,件名,状態\nENG-1,保険証券の名義変更,完了\n")
    _, state = journey._untracked_commitment([
        _entry("docs/計画.md", "至急: 採用ページの更新を完了する\n"), tracked,
    ])
    assert state["ran"] is True
    assert state["open_rows_checked"] == 0
    open_row = _entry("t.csv", "番号,件名,状態\nENG-1,保険証券の名義変更,対応中\n")
    _, open_state = journey._untracked_commitment([
        _entry("docs/計画.md", "至急: 採用ページの更新を完了する\n"), open_row,
    ])
    assert open_state["ran"] is True
    assert open_state["open_rows_checked"] == 1, (
        "the suppression arm proves nothing unless the same row counts as open "
        "when its status is not a closed label"
    )


def test_the_first_dividend_over_a_japanese_estate_is_not_an_orientation_map(
    tmp_path, framework_only,
):
    """THE MEASURED FAILURE, end to end through the real scan.

    This is the arm that reproduces what the live hatch returned: a folder
    carrying an urgent line, a contradiction and an open-work marker, read to
    the last file, reported as holding none of them.
    """
    source = tmp_path / "estate"
    source.mkdir()
    (source / "連絡.md").write_text(
        "# 連絡事項\n\n至急: 保険証券の名義変更が必要です\n", encoding="utf-8")
    (source / "計画.md").write_text("期限: 2026-08-12\n", encoding="utf-8")
    (source / "契約.md").write_text("期限: 2026-08-25\n", encoding="utf-8")
    manifest, entries = journey._scan_source(source, charter_hash="ja-estate")
    dividend = journey._first_dividend(manifest, entries, "2026-07-30T00:00:00Z")
    finding = dividend["finding"]
    assert finding["kind"] != "orientation_map", (
        "the measured failure: a folder read to the last file and reported as "
        "holding no contradiction and no urgent marker while carrying both"
    )
    # The scores are unchanged, so the contradiction (90) still outranks the
    # attention marker (80) — the point is that BOTH are now reachable.
    assert finding["kind"] == "conflicting_commitment"
    assert finding["quality"] == "strong"
    assert _kinds(journey._risk_markers(entries)) == ["attention_marker"]
    assert manifest["coverage"]["complete"] is True


# ── 2. the English pins: every retired pattern, written out as the oracle ────


_ENGLISH_MARKER_LINES = (
    "URGENT: the certificate expires on Friday",
    "- BLOCKED: finance approval is missing",
    "## Overdue — the vendor review",
    "Status: blocked",
    "priority: action required",
    "[ ] needs action: chase the survey",
    "TODO: rotate the staging certificate",
    "// FIXME(auth): the refresh path double-reads",
    "<!-- XXX -->",
    "the deploy hook-blocked on a stale lease",
    "we should probably prioritise this",
    "Statuses are tracked in the sheet",
    "*urgent*",
    "1. Blocked",
)


@pytest.mark.parametrize("line", _ENGLISH_MARKER_LINES)
def test_the_english_risk_markers_read_byte_identically(line, framework_only):
    """ASCII PIN against both retired patterns, run through the live detector.

    The oracle re-implements the OLD line preparation exactly — raw text, no
    fold — so a divergence in what gets stripped shows up here rather than in
    somebody's estate.
    """
    markdown_prefix = re.compile(r"^\s*(?:(?:#{1,6}|[-*+]|\d+[.)]|\[[ xX]\])\s+|[*_`]+)*")
    comment_prefix = re.compile(r"^\s*(?:(?://+|/\*+|<!--|#+|[-*+]|\[[ xX]\])\s*)+")
    meaningful = markdown_prefix.sub("", line).lstrip("*_`")
    open_work = comment_prefix.sub("", line).lstrip("*_`")
    expected: list[str] = []
    if _OLD_URGENT_RE.search(meaningful):
        expected.append("attention_marker")
    elif _OLD_TODO_RE.search(open_work):
        expected.append("open_work_marker")
    assert _kinds(journey._risk_markers([_entry("a.md", line + "\n")])) == expected


def test_hook_blocked_in_prose_is_still_not_a_blocked_work_item(framework_only):
    """The false positive the line-start grammar was introduced to kill. A
    vocabulary table that quietly became a substring search would revive it,
    and this arm is why that cannot happen silently."""
    assert journey._risk_markers([
        _entry("a.md", "the deploy hook-blocked on a stale lease\n")
    ]) == []


_ENGLISH_LABEL_LINES = (
    "Launch: 2026-09-30",
    "launch date: 2026-10-14",
    "Go-Live: 2026-09-30",
    "go live date = 2026-10-14",
    "golive: 2026-10-14",
    "- Deadline: 2026-09-30",
    "* delivery  date: 2026-10-14",
    "Launched the thing on Friday",
)


def test_the_english_contradiction_keys_read_byte_identically(framework_only):
    """Every spelling the retired optional groups reached, keyed the same way.

    The old key normalisation was ``re.sub(r"[^a-z]", "", label.lower())``;
    the new one keeps Unicode word characters. For these labels the two are
    the same string, which is what makes the go-live spellings still collapse
    onto one key and ``launch`` still NOT collapse onto ``launch date``.
    """
    entries = [_entry(f"f{i}.md", line + "\n")
               for i, line in enumerate(_ENGLISH_LABEL_LINES)]
    expected: dict[str, set[str]] = {}
    for entry in entries:
        match = _OLD_CONTRADICTION_RE.match(entry["lines"][0])
        if not match:
            continue
        key = re.sub(r"[^a-z]", "", match.group(1).lower())
        expected.setdefault(key, set()).add(
            " ".join(match.group(2).lower().split())
        )
    assert sorted(expected) == ["deadline", "deliverydate", "golive",
                                "golivedate", "launch", "launchdate"]
    conflicting = sum(1 for values in expected.values() if len(values) > 1)
    assert conflicting == 1, "the go-live spellings are one key with two dates"
    assert expected["golive"] == {"2026-09-30", "2026-10-14"}
    # ``launch`` and ``launch date`` are DIFFERENT keys and always were; the
    # arm would pass just as well if every key collapsed into one, so the key
    # set above is asserted before the count is trusted.
    assert expected["launch"] != expected["launchdate"]
    assert len(journey._contradictions(entries)) == conflicting


def test_the_english_commitment_prefixes_read_byte_identically(framework_only):
    """Including ``follow-up`` and ``follow up``, which the retired pattern
    reached through a character class and the table reaches as two rows."""
    export = _entry("t.csv", "id,title,status\nENG-1,Something else entirely,Open\n")
    for line in ("TODO: rotate the staging certificate before cutover",
                 "FIXME - the reconciliation double-counts refunds",
                 "BLOCKED: finance approval for the vendor renewal",
                 "Blocker — the survey needs a second signature",
                 "action required: confirm the handover schedule",
                 "needs action: chase the outstanding invoice",
                 "follow-up: confirm the completion date",
                 "follow up — confirm the completion date"):
        prose = _entry("docs/plan.md", line + "\n")
        assert _OLD_COMMITMENT_RE.match(line), line
        findings, state = journey._untracked_commitment([prose, export])
        assert state["ran"] is True
        assert _kinds(findings) == ["untracked_commitment"], line


def test_the_english_closed_statuses_still_close_a_row(framework_only):
    prose = _entry("docs/plan.md", "TODO: rotate the staging certificate\n")
    for status in sorted(_OLD_CLOSED_STATUSES):
        export = _entry(
            "t.csv", f'id,title,status\nENG-1,Rotate the staging certificate,"{status}"\n')
        _, state = journey._untracked_commitment([prose, export])
        assert state["open_rows_checked"] == 0, status


def test_the_english_export_columns_keep_their_preference_order(framework_only):
    """THE ORDER IS THE BEHAVIOUR, and it is the one thing a label table makes
    easy to lose: the first recognised header wins, so re-sorting the role —
    longest-first, alphabetically, by language — silently changes which column
    a multi-column export is read by. Every pair is asserted in declaration
    order rather than spot-checked.
    """
    for role, columns in (
        ("title", _OLD_EXPORT_TITLE_COLUMNS),
        ("status", _OLD_EXPORT_STATUS_COLUMNS),
        ("id", _OLD_EXPORT_ID_COLUMNS),
    ):
        for index, winner in enumerate(columns):
            for loser in columns[index + 1:]:
                header, row = _competing_export(role, winner, loser)
                rows = journey._tracker_rows(_entry("t.csv", f"{header}\n{row}\n"))
                # Lower case on both sides of the marker: the status CELL is
                # folded (it is the one compared against a label set); the
                # title and id cells are the operator's own bytes.
                assert rows and rows[0][role] == "winner", (
                    f"{role}: {winner} must outrank {loser}")


def _competing_export(role: str, winner: str, loser: str) -> tuple[str, str]:
    """A one-row CSV carrying BOTH candidate headers for one role, plus a
    fixed column for each of the other two roles so the export still parses."""
    fixed = {"title": ("title", "t"), "status": ("status", "open"), "id": ("id", "x")}
    headers, cells = [winner, loser], ["winner", "loser"]
    for other, (name, value) in fixed.items():
        if other != role:
            headers.append(name)
            cells.append(value)
    return ",".join(headers), ",".join(cells)


# ── 3. the extension point: ADD, never replace ──────────────────────────────


def test_an_instance_addition_fires(framework_only):
    """The point of the table. A deployment adds the words its own estate is
    written in and the detectors read them, with no framework change."""
    _with_instance_vocabulary(
        framework_only, "attention:\n  da:\n    - haster\n")
    assert _kinds(journey._risk_markers([_entry("a.md", "HASTER: skøde mangler\n")])) == [
        "attention_marker"
    ]


def test_an_instance_addition_may_be_a_plain_list(framework_only):
    """Both shapes the loader documents. A language tag is organisation, and
    an operator adding three words should not have to invent one."""
    _with_instance_vocabulary(
        framework_only, "open_work: [\"restance\"]\n")
    assert _kinds(journey._risk_markers([_entry("a.md", "restance: skødet\n")])) == [
        "open_work_marker"
    ]


def test_an_absent_instance_file_is_silently_the_framework_defaults(framework_only):
    """The ordinary case, and the one a fresh hatch is in. Absence is not an
    error and must not be reported as one."""
    assert not (framework_only / journey.INSTANCE_VOCABULARY_REL).exists()
    assert _kinds(journey._risk_markers([_entry("a.md", "URGENT: x y z\n")])) == [
        "attention_marker"
    ]
    assert _kinds(journey._risk_markers([_entry("a.md", "至急: 名義変更\n")])) == [
        "attention_marker"
    ]


def test_a_replacement_attempt_still_leaves_the_framework_defaults_active(
    framework_only,
):
    """EXTEND, NEVER REPLACE — structurally, not by convention. There is no
    shape this file can take that deletes a shipped label, and the arm is
    written as the attempt rather than as the invariant."""
    _with_instance_vocabulary(framework_only, "\n".join([
        "closed_status:",
        "  replace: true",
        "  en:",
        "    - færdig",
        "attention: [\"haster\"]",
    ]) + "\n")
    prose = _entry("docs/plan.md", "TODO: rotate the staging certificate\n")
    for status in ("done", "færdig"):
        export = _entry("t.csv", f"id,title,status\nENG-1,Something,{status}\n")
        _, state = journey._untracked_commitment([prose, export])
        assert state["open_rows_checked"] == 0, status
    assert _kinds(journey._risk_markers([_entry("a.md", "URGENT: x y z\n")])) == [
        "attention_marker"
    ]


@pytest.mark.parametrize("body", [
    "::: not yaml [\n",
    "- a\n- b\n",
    "attention: \"haster\"\n",
    "attention:\n  da: haster\n",
    "attention:\n  da:\n    - 17\n",
    "",
])
def test_a_malformed_instance_file_falls_back_to_the_defaults(body, framework_only):
    """FAIL-OPEN TO EMPTY. A config mistake must not take a Charter-ratified
    read down, and it must not silently empty a role either — every shape here
    lands on exactly the defaults."""
    _with_instance_vocabulary(framework_only, body)
    assert _kinds(journey._risk_markers([_entry("a.md", "URGENT: x y z\n")])) == [
        "attention_marker"
    ]
    assert _kinds(journey._risk_markers([_entry("a.md", "至急: 名義変更\n")])) == [
        "attention_marker"
    ]


def test_a_role_this_module_does_not_define_is_ignored(framework_only):
    """Honouring it would promise a detector that does not exist."""
    _with_instance_vocabulary(
        framework_only, "not_a_role: [\"x\"]\nattention: [\"haster\"]\n")
    vocabulary = journey.detector_vocabulary(framework_only)
    assert "not_a_role" not in vocabulary
    assert "haster" in vocabulary["attention"]


def test_an_instance_label_never_outranks_a_framework_column(framework_only):
    """The column roles are preference-ordered and additions land LAST, so a
    deployment cannot change how an export that already parsed is read."""
    _with_instance_vocabulary(framework_only, "export_title_column: [\"summary\"]\n")
    rows = journey._tracker_rows(
        _entry("t.csv", "title,summary,status\nWINNER,loser,open\n"))
    assert rows[0]["title"] == "WINNER"


# ── 4. the degenerate ends ──────────────────────────────────────────────────


def test_an_empty_vocabulary_role_matches_nothing(framework_only):
    """THE DANGEROUS END of a data-driven detector. The empty alternation
    ``(?:)`` matches the empty string, so a role nobody filled would fire on
    every line of every file — a detector that went from silent to screaming
    by losing its data."""
    assert journey._label_alternation([]) == r"(?!)"
    empty = {role: () for role in journey.DETECTOR_VOCABULARY}
    assert journey._risk_markers(
        [_entry("a.md", "URGENT: x\n: y\nordinary prose\n")], vocabulary=empty) == []
    assert journey._contradictions(
        [_entry("a.md", "deadline: 1\n"), _entry("b.md", "deadline: 2\n")],
        vocabulary=empty) == []


@pytest.mark.parametrize("role,fires,quiet", [
    ("attention", "URGENT: x y z", "TODO: x y z"),
    ("open_work", "TODO: x y z", "URGENT: x y z"),
])
def test_emptying_one_role_silences_exactly_what_that_role_feeds(
    role, fires, quiet, framework_only,
):
    """THE AGNOSTICISM SENSOR, and the sharpest one available: if any label
    were still inlined in a detector body, emptying its role would not silence
    it. A source grep cannot say this — a docstring may legitimately name a
    label — and this arm does not care where the literal is.

    One of the five arms this file's docstring names as unable to execute
    against pre-change code: it grades a keyword that did not exist.
    """
    partial = {name: () if name == role else labels
               for name, labels in journey.detector_vocabulary().items()}
    assert journey._risk_markers([_entry("a.md", fires + "\n")], vocabulary=partial) == []
    assert journey._risk_markers([_entry("a.md", quiet + "\n")], vocabulary=partial) != []


def test_a_single_character_label_matches_itself_and_not_a_word_containing_it(
    framework_only,
):
    """済 is a whole closed status on its own and a fragment of 未済 ("not
    done"). The status comparison is equality, never containment, and a
    one-character label is where that stops being obvious."""
    prose = _entry("docs/計画.md", "至急: 保険証券の名義変更を完了する\n")
    for status, open_rows in (("済", 0), ("未済", 1)):
        export = _entry("t.csv", f"番号,件名,状態\nENG-1,採用ページ,{status}\n")
        _, state = journey._untracked_commitment([prose, export])
        assert state["ran"] is True, status
        assert state["open_rows_checked"] == open_rows, status


def test_a_line_that_is_only_the_label_fires(framework_only):
    """No separator, no text after it. The retired patterns accepted this with
    ``$`` and the table must not quietly require a colon."""
    for line, kind in (("URGENT", "attention_marker"), ("至急", "attention_marker"),
                       ("TODO", "open_work_marker"), ("未対応", "open_work_marker")):
        assert _kinds(journey._risk_markers([_entry("a.md", line + "\n")])) == [kind], line


def test_a_blank_or_whitespace_label_is_dropped_rather_than_matching_everything(
    framework_only,
):
    """An empty label escaping into an alternation is the empty-role hazard
    one row at a time: ``urgent|`` matches every line ever written."""
    _with_instance_vocabulary(
        framework_only, "attention:\n  x:\n    - \"\"\n    - \"   \"\n    - \"\\u3000\"\n")
    assert journey.detector_vocabulary(framework_only)["attention"] == \
        journey.detector_vocabulary(framework_only / "absent")["attention"]
    assert journey._risk_markers([_entry("a.md", "ordinary prose\n")]) == []


def test_an_export_with_no_rows_and_a_japanese_header_is_still_not_a_tracker(
    framework_only,
):
    """Header-only: the shape is right and the content is absent. A file is
    not a connection, in any script."""
    assert journey._tracker_rows(_entry("t.csv", "番号,件名,状態\n")) == []


def test_no_detector_carries_a_non_english_label_as_a_code_literal(framework_only):
    """The cheap companion to the emptying arms: a label from any tag other
    than the first one may never appear as a STRING CONSTANT inside a detector
    (docstrings excluded, comments never reach the AST). Adding a language is
    adding rows to the table; the day it stops being, this goes red."""
    import ast
    import inspect

    # Minus the first tag's own labels: ``ID`` is a Japanese export header AND
    # an English one, and ``"id"`` is a legitimate field name in the row a
    # detector builds. What this grades is the labels only the LATER tags
    # carry — the ones a detector could only know by having them written in.
    first_tag = {
        label
        for by_tag in journey.DETECTOR_VOCABULARY.values()
        for label in list(by_tag.values())[0]
    }
    non_english = {
        label
        for by_tag in journey.DETECTOR_VOCABULARY.values()
        for labels in list(by_tag.values())[1:]
        for label in labels
    } - {label.casefold() for label in first_tag} - first_tag
    assert non_english, "the table ships more than one tag or this arm is vacuous"
    for detector in (journey._risk_markers, journey._contradictions,
                     journey._tracker_rows, journey._untracked_commitment,
                     journey._export_column):
        tree = ast.parse(inspect.getsource(detector).lstrip())
        body = tree.body[0].body
        constants = [
            node.value for node in ast.walk(ast.Module(body=body[1:], type_ignores=[]))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        for label in non_english:
            assert not any(label in constant for constant in constants), (
                f"{detector.__name__} carries the label {label!r} as a literal")
