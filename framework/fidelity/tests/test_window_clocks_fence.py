"""A MENTIONED date is not a WRITTEN-ON date — the fence stays where it was.

THE FAILURE THIS EXISTS TO PREVENT. Onboarding now extracts the dates a file
STATES. The retrodiction fence orders and excludes material by the date a file
was WRITTEN (``content_ts``, derived from frontmatter or a filename, never
mtime, and honestly absent when neither is available). Those are two different
clocks, and letting the first one reach the second would be the worst kind of
leak: a note written last June that says "the launch is 2026-12-31" would date
itself into the future, and every officer replay with a cutoff between the two
would silently drop a record it was entitled to see — or, in the mirror case,
admit one it was not.

Nothing here is a promise about intent. The arms below assert the mechanism:
the derivation is untouched, the ordering is by document time, and a clock row
carries no key any fence reads.
"""
from __future__ import annotations

from pathlib import Path

from framework.fidelity import leakguard
from framework.onboarding import salience
from framework.sources import local as local_source

CUTOFF = "2026-07-01T00:00:00Z"
NOW = "2026-08-05T09:00:00Z"

# A note WRITTEN in June that MENTIONS December. Both clocks are present and
# they disagree by six months, which is what makes the arms below able to fail.
NOTE = """---
date: 2026-06-01
title: Programme review
---

The regulator's filing deadline is 2026-12-31 and it cannot move.
契約更新日 2026年12月31日
"""


def _write(tmp_path: Path) -> Path:
    path = tmp_path / "2026-06-01-programme-review.md"
    path.write_text(NOTE, encoding="utf-8")
    return path


def test_content_ts_still_reads_the_document_clock(tmp_path):
    """The derivation is byte-for-byte the one that shipped: frontmatter first.

    If clock extraction had leaked into it, this would answer 2026-12-31.
    """
    path = _write(tmp_path)
    assert local_source._content_ts_for(path, NOTE) == "2026-06-01T00:00:00Z"


def test_the_future_dated_clause_is_extracted_and_changes_nothing(tmp_path):
    path = _write(tmp_path)
    rows, _meta = salience.file_clocks(
        NOTE.splitlines(), now=NOW, cite=lambda n, line: {"line": n})
    # BOTH clocks are extracted, including the frontmatter line — the
    # extractor reads a stated date wherever it is written and has no notion
    # of which one dates the document. That is exactly why the arms below
    # matter: the separation is the fence's, not the extractor's.
    assert {row["iso"] for row in rows} == {"2026-06-01", "2026-12-31"}
    forward = [row for row in rows if row["iso"] == "2026-12-31"]
    assert forward and all(row["direction"] == "future" for row in forward)
    # ...and the document clock is unmoved by the extraction having happened.
    assert local_source._content_ts_for(path, NOTE) == "2026-06-01T00:00:00Z"


def test_the_hit_is_fenced_by_when_it_was_written_not_by_what_it_mentions(tmp_path):
    """Ordered and admitted by document time, in BOTH directions.

    A pre-cutoff note survives even though it names a post-cutoff date, and
    the same note is dropped by a cutoff that precedes its own writing. One
    arm alone would pass against a fence that had stopped working.
    """
    _write(tmp_path)
    hit = {
        "ref": "2026-06-01-programme-review.md",
        "text": NOTE,
        "content_ts": "2026-06-01T00:00:00Z",
        "ts": "2026-06-01T00:00:00Z",
    }
    survived = leakguard.filter_mcp_result([dict(hit)], CUTOFF)
    assert survived == [hit], "a June note is as-of-cutoff knowledge in July"

    earlier = leakguard.filter_mcp_result([dict(hit)], "2026-05-01T00:00:00Z")
    assert earlier == [], "the same note is post-cutoff for a May cutoff"


def test_a_clock_row_carries_no_key_any_fence_reads(tmp_path):
    """STRUCTURAL, not behavioural: the fence keys and the row keys are disjoint.

    ``leakguard._TS_KEYS`` is the list of keys whose value the fence treats as
    a content-creation timestamp. A clock row shares none of them, so a row
    reaching a fenced payload by any future route cannot be mistaken for the
    document's own clock — and nor can the ``content_ts`` key the source
    adapters use.
    """
    rows, _meta = salience.file_clocks(
        NOTE.splitlines(), now=NOW, cite=lambda n, line: {"path": "n.md", "line": n})
    assert rows
    forbidden = set(leakguard._TS_KEYS) | {"content_ts"}
    for row in rows:
        assert set(row) == set(salience.CLOCK_ROW_FIELDS)
        assert not (set(row) & forbidden)
        assert leakguard._item_ts(row) is None
        assert not (set(row.get("ref") or {}) & forbidden)


def test_the_clock_artifact_writes_nothing_into_a_fenced_surface(tmp_path):
    """The onboarding artifact is not one of the source shapes a fence walks.

    Asserted over the whole persisted payload rather than over a row, because
    the envelope is what a future caller would hand onwards.
    """
    from framework.onboarding import journey

    source = tmp_path / "src"
    source.mkdir()
    (source / "note.md").write_text(NOTE, encoding="utf-8")
    root = tmp_path / "cab"
    proposed = journey.act(
        {"action": "propose_window", "ownership": "self",
         "authority_basis": "mine", "action_id": "p1", "surface": "dashboard",
         "source": str(source), "purpose": "Read what my files say.",
         "relationship_destination": "reversible"},
        root, now=NOW)
    result = journey.act(
        {"action": "ratify_charter", "action_id": "r1", "surface": "dashboard",
         "charter_hash": proposed["state"]["charter"]["hash"],
         "expected_revision": proposed["state"]["revision"]},
        root, now=NOW)
    payload = result["state"]["window_clocks"]
    forbidden = set(leakguard._TS_KEYS) | {"content_ts"}
    assert not (set(payload) & forbidden)
    assert leakguard._item_ts(payload) is None
    # The payload's own clock is the RUN's, and it is the only timestamp in it.
    assert payload["generated_at"] == NOW
