"""The FINDING PATH reads any script — one defect class across four modules.

WHAT WAS MEASURED, and why these arms live in one file rather than four. A
live agnostic-proof hatch on 2026-07-30 gave the cabinet a Japanese
operator's estate: seventeen ``.md``/``.csv``/``.txt`` files, a seed answered
in Japanese, lanes declared. The cabinet accepted every input and found
NOTHING — zero discovery probes from the seed, zero recall hits on every
subject, not one quoted line on any card. Four separate ASCII character
classes were the whole cause:

  * ``journey._SEED_TOKEN_RE``   ``[A-Za-z][A-Za-z0-9+#._/-]{1,39}``
  * ``journey._CONTENT_TOKEN_RE``  ``[A-Za-z][A-Za-z0-9._-]{3,}``
  * ``local._WORD_RE``           ``[A-Za-z0-9_]{3,}``
  * ``genesis._WORD_RE``         ``[A-Za-z][A-Za-z0-9_-]{2,}``

plus a fifth wall one step further along (``journey._PROBE_PATTERN_RE``,
which refused every pattern built from a non-Latin word as ``pattern_unsafe``)
and a sixth thing that was never a regex at all: recall's subjects came only
from lane DISPLAY NAMES, an ASCII romanisation appearing in none of the
operator's files. They are one class, they were fixed in one commit, and a
future reader deleting any one of them should see the class fail, not one arm.

EVERY ARM HERE GOES THROUGH A PUBLIC ENTRY POINT that existed BEFORE the fix
— ``seed_probes``, ``_execute_probes``, ``_untracked_commitment``,
``LocalNotesSource.search``, ``genesis._quote_of``, ``genesis.recall_probes``.
That is deliberate and is what makes the pre-change proof worth anything: run
this file against origin/master and each arm RUNS and fails on its assertion,
rather than erroring on an import of a function that does not exist yet. An
arm that cannot execute against the old code proves the code is old, not that
the sensor works.

THE ASCII PINS ARE THE OTHER HALF. Widening a tokenizer re-reads every estate
at once, so each consumer carries an arm asserting that English input yields
byte-identical output to the regex it replaced — the old pattern is written
out inline as the oracle, so the pin cannot drift with the code it grades.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from framework.onboarding import genesis, journey            # noqa: E402
from framework.sources.local import LocalNotesSource         # noqa: E402

# The four character classes this landing removed, kept HERE as the oracle for
# the English pins. They are dead in the tree and live in this file, which is
# the only place they can no longer rot into the thing they are grading.
_OLD_SEED_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#._/-]{1,39}")
_OLD_CONTENT_RE = re.compile(r"[A-Za-z][A-Za-z0-9._-]{3,}")
_OLD_LOCAL_RE = re.compile(r"[A-Za-z0-9_]{3,}")
_OLD_GENESIS_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")

_JA_PROSE = "請求書の移行が完了しました。次は入金の照合を進めます。"
_RU_PROSE = "Миграция счетов завершена, дальше сверка поступлений."
_EN_PROSE = "The billing migration completed and reconciliation is next."


# ── 1. the seed: a few words in any script become searchable terms ───────────


def test_a_japanese_seed_yields_terms_and_executable_probes():
    got = journey.seed_probes("請求書の移行を管理しています",
                              {"web": True, "local_files": True})
    assert got["terms"], "a seed in Japanese produced no terms at all"
    assert got["probes"] and got["executable"] is True
    assert any("請求" in term for term in got["terms"])


def test_a_cyrillic_seed_yields_terms():
    got = journey.seed_probes("я управляю платежными интеграциями",
                              {"local_files": True})
    assert "платежными" in got["terms"]
    assert got["executable"] is True


def test_a_mixed_script_seed_keeps_both_halves():
    """``APIの設計`` is one unbroken run of Letters. A splitter that only asks
    the Unicode CATEGORY returns it whole and loses both words inside it."""
    terms = journey.seed_probes("APIの設計 and payments", {"web": True})["terms"]
    assert "API" in terms, terms
    assert "payments" in terms, terms
    assert any("設計" in term for term in terms), terms


def test_a_single_ideograph_is_a_word_and_not_a_fragment():
    """Degenerate end. The two-character floor is an ALPHABET's floor; one
    ideograph is routinely a whole word, so the floor must not reach it."""
    assert journey.seed_probes("日", {"local_files": True})["terms"] == ["日"]


def test_an_english_seed_is_read_exactly_as_before():
    """ASCII PIN. Widening the alphabet must not move a Latin estate."""
    assert journey.seed_probes("payments integrations for a bank",
                               {"web": True})["terms"] == [
        "payments", "integrations", "bank",
    ]
    for sentence in (_EN_PROSE, "I look after payments releases",
                     "quarterly reporting for the northbay site"):
        expected = []
        for match in _OLD_SEED_RE.finditer(sentence):
            token = match.group(0).strip("._/-")
            if len(token) < 2 or token.lower() in journey._SEED_STOPWORDS:
                continue
            if not any(token.lower() == seen.lower() for seen in expected):
                expected.append(token)
        assert journey._seed_terms(sentence) == expected[:journey.MAX_SEED_TERMS]


def test_a_seed_of_nothing_is_still_nothing():
    """Degenerate ends: the widening must not invent a term out of punctuation
    — including punctuation that is itself non-Latin."""
    for seed in ("", "   ", "。。。 、、、", "!!! ---", None, 17):
        got = journey.seed_probes(seed, {"web": True, "local_files": True})
        assert got["terms"] == [] and got["probes"] == []
        assert got["executable"] is False


# ── 2. the executor: a pattern in the operator's own script is not "unsafe" ──


def test_a_probe_pattern_in_the_operators_own_script_is_executed(tmp_path):
    """The wall one step past the seed. Once the seed stopped losing the
    word, the pattern built from it arrived here and was refused as
    ``pattern_unsafe`` — the operator's own language reported back to them as
    dangerous, with the search silently not run."""
    window = tmp_path / "window"
    window.mkdir()
    (window / "請求書-移行.md").write_text("x\n", encoding="utf-8")
    result = journey._execute_probes(
        window, [{"kind": "local_name_match", "pattern": "*請求*"}])
    assert result["deferred"] == []
    assert result["executed"][0]["matches"] == ["請求書-移行.md"]


def test_every_traversal_refusal_still_refuses(tmp_path):
    """The allow-list was widened, so what it REFUSES has to be re-proven —
    a wider allow-list is the natural place to lose a containment rule."""
    window = tmp_path / "window"
    window.mkdir()
    (window / "safe.md").write_text("x\n", encoding="utf-8")
    hostile = ["../outside/*", "ci/cd*", "/etc/passwd", ".hidden*",
               "日本/../x", "́abc", "a b", "x\\y", "$(x)", "'x'",
               "a\nb", "x" * 65]
    result = journey._execute_probes(
        window, [{"kind": "local_name_match", "pattern": p} for p in hostile]
        + [{"kind": "local_name_match", "pattern": "safe*"}])
    assert [row["pattern"] for row in result["executed"]] == ["safe*"]
    assert {row["reason"] for row in result["deferred"]} == {"pattern_unsafe"}


# ── 3. the join detector: prose against a tracker export ────────────────────


def _entry(path: str, text: str) -> dict:
    return {"path": path, "sha256": "0" * 64, "lines": text.splitlines()}


def test_a_japanese_commitment_with_no_open_row_is_found():
    """The detector was STRUCTURALLY DEAD on non-Latin prose: the subject
    token set came back empty, the two-token floor dropped the line, and the
    run reported ``ran: True`` with nothing found."""
    prose = _entry("docs/計画.md", "TODO: 請求書の移行を完了する\n")
    export = _entry("tracker.csv",
                    "id,title,status\nENG-1,採用ページの更新,Open\n")
    findings, state = journey._untracked_commitment([prose, export])
    assert state["ran"] is True and state["open_rows_checked"] == 1
    assert [f["kind"] for f in findings] == ["untracked_commitment"]


def test_a_japanese_commitment_an_open_row_accounts_for_stays_quiet():
    prose = _entry("docs/計画.md", "TODO: 請求書の移行を完了する\n")
    tracked = _entry("tracker.csv",
                     "id,title,status\nENG-9,請求書の移行,Open\n")
    findings, state = journey._untracked_commitment([prose, tracked])
    assert state["ran"] is True
    assert findings == [], "a row saying the same thing must silence the claim"


def test_the_join_finds_the_same_english_words_without_the_punctuation():
    """ASCII PIN, against the retired character class — and the ONE place a
    pin here does not read "byte-identical". The old class carried ``.`` and
    ``-`` inside a token, so a sentence-final period was glued to the last
    word (``next.``). Same words, minus the punctuation; the arm below states
    the compound half of the same divergence."""
    for text in (_EN_PROSE, "Rotate the staging certificate before cutover",
                 "the storefront widget alignment drifts on mobile"):
        # ``.strip("._-")``: the old class carried a SENTENCE-final period
        # inside the token ("next."), which is the punctuation divergence the
        # arm below declares, not an alphabet difference. The pin grades the
        # alphabet.
        expected = {
            token.lower().strip("._-") for token in _OLD_CONTENT_RE.findall(text)
            if token.lower() not in journey._SEED_STOPWORDS
        }
        assert journey._content_tokens(text) == expected


def test_a_compound_joined_by_punctuation_now_splits_and_that_is_declared():
    """THE ONE DIVERGENCE from the retired classes, pinned rather than hidden.

    The old classes carried ``-``, ``_``, ``.`` and ``/`` INSIDE a token, so
    ``ENG-9`` was one word. The shared splitter ends a word at every one of
    them — a filing system writes an underscore where a person writes a space
    — so it is now two. The join is not weakened by it: the alphabetic half is
    below the floor on BOTH sides and the numeric half is shared on both, so a
    ticket id contributes the same single matching token it always did.
    """
    assert journey._content_tokens("ENG-4821 needs review") >= {"4821"}
    assert "eng-4821" not in journey._content_tokens("ENG-4821 needs review")


# ── 4. the local folder: index and query in any script ──────────────────────


def _folder(tmp_path: Path) -> LocalNotesSource:
    root = tmp_path / "notes"
    root.mkdir()
    (root / "seikyu.md").write_text("# 請求\n" + _JA_PROSE + "\n",
                                    encoding="utf-8")
    (root / "scheta.md").write_text("# Счета\n" + _RU_PROSE + "\n",
                                    encoding="utf-8")
    (root / "billing.md").write_text("# Billing\n" + _EN_PROSE + "\n",
                                     encoding="utf-8")
    return LocalNotesSource(str(root))


def test_a_japanese_query_answers_out_of_a_japanese_note(tmp_path):
    """The adapter read the folder in full and answered ``{"hits": []}`` to
    every query, while ``available()`` reported a live source — a folder that
    holds the answer, reported as a folder that holds nothing."""
    source = _folder(tmp_path)
    assert source.available() is True
    hits = source.search("請求書の移行")["hits"]
    assert [h["path"] for h in hits] == ["seikyu.md"]
    assert hits[0]["base_score"] > 0.0


def test_a_cyrillic_query_answers_out_of_a_cyrillic_note(tmp_path):
    hits = _folder(tmp_path).search("миграция счетов")["hits"]
    assert [h["path"] for h in hits] == ["scheta.md"]


def test_an_english_query_answers_exactly_the_note_it_always_did(tmp_path):
    """ASCII PIN, end to end: the widening must not move a Latin folder."""
    hits = _folder(tmp_path).search("billing migration")["hits"]
    assert [h["path"] for h in hits] == ["billing.md"]


def test_english_corpus_terms_are_byte_identical_to_the_retired_class(tmp_path):
    from framework.sources import local

    for text in (_EN_PROSE, "Q3 2026 revenue reconciliation",
                 "the northbay site went down twice"):
        expected = [w.lower() for w in _OLD_LOCAL_RE.findall(text)]
        assert local._terms(text) == expected


def test_an_empty_or_punctuation_only_query_finds_nothing(tmp_path):
    """Degenerate ends. A query that carries no term must return the honest
    empty rather than every chunk in the folder."""
    source = _folder(tmp_path)
    for query in ("", "   ", "。。。", "!!!"):
        assert source.search(query)["hits"] == []


# ── 5. the recall card: the operator's own sentence, quoted back ────────────


def test_a_japanese_note_can_be_quoted_on_a_card():
    """The "I did not ask you for this, I read it" line is the whole point of
    the surface. Every line of a non-Latin note failed the prose floor, so the
    card printed a citation with NO quote — for every operator on earth who
    does not write in Latin, silently."""
    assert genesis._quote_of({"text": _JA_PROSE, "heading": ""}) != ""
    assert genesis._quote_of({"text": _RU_PROSE, "heading": ""}) != ""


def test_a_two_character_fragment_is_still_not_prose():
    """The honest floor for a script with no spaces: an unspaced run is worth
    ``len // 2`` words, so ten characters clears the five-word bar and a
    two-character fragment does not. A floor that stopped biting would quote
    ``設計。`` at the operator as their own sentence."""
    assert genesis._quote_of({"text": "設計。", "heading": ""}) == ""
    assert genesis._quote_of({"text": "The:", "heading": ""}) == ""


def test_english_query_terms_are_byte_identical_to_the_retired_class():
    """ASCII PIN."""
    for text in (_EN_PROSE, "shared wording across three notes"):
        expected = {w.lower() for w in _OLD_GENESIS_RE.findall(text)}
        assert genesis._query_terms(text) == expected


# ── 6. recall subjects: the operator's own words, not only a lane label ─────


_LANES = {"lanes": [{"slug": "seikyu-migration", "name": "Seikyu Migration"}]}


def test_the_operators_own_words_become_a_recall_subject():
    """A lane's display name is chosen at hatch time and is frequently the
    cabinet's spelling of the subject, not the operator's. On the measured
    estate every lane label was an ASCII romanisation appearing in none of the
    seventeen files, so all four subjects asked recall about a word that was
    not in the folder."""
    answers = dict(_LANES, mission={"purpose": "請求書の移行を管理する"})
    labels = [p["label"] for p in genesis.recall_probes(answers)]
    assert labels[0] == "Seikyu Migration", "declared subjects come FIRST"
    assert len(labels) > 1, "the operator's own words reached no subject"
    assert any("請求" in label for label in labels[1:])


def test_the_journey_seed_reaches_the_subjects_from_either_side():
    """The seed lives in journey state, and genesis is called both by a
    caller that holds it and by one that only has the answers file."""
    passed = genesis.recall_probes(_LANES, seed="請求書の移行を管理する")
    carried = genesis.recall_probes(
        dict(_LANES, seed={"text": "請求書の移行を管理する"}))
    assert [p["key"] for p in passed] == [p["key"] for p in carried]
    assert len(passed) > 1


def test_own_word_subjects_are_capped_and_never_displace_a_declared_one():
    """They are a fallback, not a way to turn a sentence into a survey."""
    answers = {
        "lanes": [{"slug": f"lane-{n}", "name": f"Lane {n}"} for n in range(2)],
        "mission": {"purpose": "請求書の移行と入金の照合と採用ページの更新"},
    }
    probes = genesis.recall_probes(answers)
    assert [p["label"] for p in probes][:2] == ["Lane 0", "Lane 1"]
    assert len(probes) <= genesis._MAX_RECALL_PROBES
    assert len(probes) - 2 <= genesis._MAX_OWN_WORD_SUBJECTS


def test_a_full_slate_of_declared_subjects_is_unchanged():
    """ASCII PIN: an operator whose lanes already fill the band sees exactly
    the subjects they saw before."""
    answers = {
        "lanes": [{"slug": f"lane-{n}", "name": f"Lane {n}"} for n in range(4)],
        "mission": {"purpose": "I run payments integrations for a bank"},
    }
    assert [p["label"] for p in genesis.recall_probes(answers)] == [
        "Lane 0", "Lane 1", "Lane 2", "Lane 3",
    ]


def test_an_operator_who_said_nothing_still_gets_no_invented_subject():
    """Degenerate end, and the rule this whole direction rests on: no source,
    no declaration, no sentence ⇒ NO probe. A subject invented here would be
    the guessing the derivation exists to remove."""
    assert genesis.recall_probes({}) == []
    assert genesis.recall_probes({"mission": {"purpose": "   "}}) == []


@pytest.mark.parametrize("purpose", ["", "   ", "。、！", "a of to"])
def test_a_purpose_carrying_no_word_adds_no_subject(purpose):
    labels = [p["label"] for p in genesis.recall_probes(
        dict(_LANES, mission={"purpose": purpose}))]
    assert labels == ["Seikyu Migration"]
