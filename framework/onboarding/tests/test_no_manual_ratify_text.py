"""THE DEAD INSTRUCTION IS GONE, and the live one is present.

"Ratify by moving the row into instance/config/outcomes.yml" is a control
nobody can reach from a phone, and it was the ONLY thing three shipped
surfaces said about ratification: the proposals-file header genesis writes,
the advisor's aging-drafts action, and the first briefing's propose-only line.

TWO ARMS, deliberately, because one of them alone is a disabled sensor:

  * the NEGATIVE arm greps the shipped surfaces for the dead sentence, and
    would pass just as well on an empty tree or a renamed directory;
  * the POSITIVE arm asserts the sanctioned phrase is present on each of those
    same surfaces, so deleting a file or breaking a glob turns this file red
    rather than green.

The third arm is the artifact half (A1.4): a hatched instance already carries
the dead paragraph in a file on disk, and code that only stops WRITING it
leaves every existing instance instructing its operator forever. The rewrite
is asserted by OCCURRENCE COUNT — a programmatic replace that silently no-ops
is the class this repo has paid for more than once.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from framework.attention import advisor
from framework.frontdoor import run_briefing
from framework.onboarding import genesis

# The tap's own module is imported INSIDE the one arm that needs it. The
# invariant arms here — the dead sentence is gone, the live one is present —
# must fail because a shipped surface still says the wrong thing, never
# because a module they do not test is absent.

_REPO = Path(__file__).resolve().parents[3]

#: The sentence, in every wording the tree has ever carried it in.
_DEAD = re.compile(r"mov(?:e|ing) (?:the |a |it )?(?:row )?into +[`']?instance/config/outcomes\.yml",
                   re.IGNORECASE)

#: The three CODE surfaces that carried the sentence. The wider sweep over the
#: shipped documentation trees is the SECOND sensor (A1.4) and lives in
#: cabinet/scripts/tests/test_ratify_text_sweep.py — outside framework/, where
#: naming those trees is not a layer coupling.
_SWEEP_FILES = (
    "framework/onboarding/genesis.py",
    "framework/attention/advisor.py",
    "framework/frontdoor/run_briefing.py",
)


def _sweep_paths() -> list:
    paths = []
    for rel in _SWEEP_FILES:
        path = _REPO / rel
        assert path.is_file(), "%s left the tree — this sweep now checks nothing" % rel
        paths.append(path)
    return paths


def test_the_sweep_reaches_something():
    """The degenerate end: a scan that matches nothing reads as compliance."""
    assert len(_sweep_paths()) == len(_SWEEP_FILES) == 3


#: The ONLY sanctioned occurrence of the dead sentence in the tree: the
#: oracle the healer matches against. Exempted by exact line, so nothing else
#: can hide behind the exemption.
_ORACLE_LINES = frozenset(
    getattr(genesis, "_STALE_RATIFY_PARAGRAPH", "").splitlines())


def _is_the_oracle(line: str) -> bool:
    """True for a line of the oracle itself — either as it appears in a
    hatched artifact, or as the Python source literal that defines it. Matched
    by EXACT content, so no new sentence can hide behind the exemption."""
    stripped = line.strip()
    if stripped in _ORACLE_LINES:
        return True
    if stripped.startswith('"') and stripped.endswith('\\n"'):
        return stripped[1:-3] in _ORACLE_LINES
    return False


def test_the_healer_still_carries_its_oracle():
    """The exemption below is worthless if the thing it exempts has gone — a
    rewrite with no pattern heals nothing and this file would go green.

    Proved by RUNNING the healer, not by grepping for a constant: a pattern
    that exists but no longer matches is the same disabled sensor as a pattern
    that is gone."""
    assert len(_ORACLE_LINES) == 4, "the healer carries no pattern to match"
    healer = getattr(genesis, "rewrite_stale_proposals_header", None)
    assert healer is not None, "nothing heals the dead paragraph in an artifact"
    healed, count = healer(genesis._STALE_RATIFY_PARAGRAPH)
    assert count == 1 and genesis.RATIFY_HINT in healed


def test_no_manual_ratify_text():
    offenders = []
    for path in _sweep_paths():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _is_the_oracle(line):
                continue
            if _DEAD.search(line):
                offenders.append("%s:%d" % (path.relative_to(_REPO), lineno))
    assert offenders == [], (
        "these shipped surfaces still tell the operator to ratify by hand: %s"
        % offenders)


#: Adjacent string literals across a source-line break. Two of the three
#: surfaces wrote the dead sentence as `"… move the row into "` +
#: `"instance/config/outcomes.yml …"`, so a LINE-WISE grep sees neither half
#: and reads as compliance — the sensor would have stayed green through a
#: straight revert of either file. Collapsing the seam is what makes the arm
#: above able to fail for the reason it names.
_SEAM = re.compile(r'(["\'])[ \t]*\n[ \t]*\1')


def _seamless(text: str) -> str:
    return _SEAM.sub("", text)


def test_the_seam_collapse_actually_joins_a_split_sentence():
    """The degenerate end of the arm below: a collapse that joins nothing
    turns a real hit back into a silent pass."""
    split = '    "… move the row into "\n    "instance/config/outcomes.yml with"\n'
    assert _DEAD.search(split) is None, "the line-wise grep cannot see this"
    assert _DEAD.search(_seamless(split)), "the collapse must expose it"


def _oracle_joined() -> str:
    """The oracle as it looks AFTER the seam collapse — one source literal.

    The healer's own pattern is the single sanctioned copy of the dead
    sentence in the tree, and collapsing seams fuses its four literals into
    one, so the line-exact exemption above no longer recognises it. Rebuilt
    from the healer's constant rather than pasted, so a healer whose text
    drifts loses its exemption instead of silently keeping it.
    """
    para = getattr(genesis, "_STALE_RATIFY_PARAGRAPH", "")
    return '"' + para.replace("\n", "\\n") + '"' if para else ""


def test_no_manual_ratify_text_across_source_line_breaks():
    offenders = []
    exempted = 0
    for path in _sweep_paths():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        joined = _seamless(text)
        oracle = _oracle_joined()
        if oracle:
            exempted += joined.count(oracle)
            joined = joined.replace(oracle, "<the healer\'s own pattern>")
        for match in _DEAD.finditer(joined):
            fragment = joined[max(0, match.start() - 60):match.end() + 40]
            offenders.append("%s: …%s…" % (path.relative_to(_REPO), fragment))
    assert offenders == [], (
        "these shipped surfaces still tell the operator to ratify by hand "
        "(the sentence split across source lines): %s" % offenders)
    # The exemption must have been USED exactly once — the healer's pattern.
    # Zero would mean the exemption is inert and the arm is only passing
    # because the thing it exempts has drifted out of recognition.
    assert exempted == 1, (
        "the healer's pattern was exempted %d times, expected exactly 1"
        % exempted)


def test_no_rendered_surface_says_move_the_row():
    """The ARTIFACT half: what these surfaces actually produce.

    A source grep polices what is written down; this polices what an operator
    is handed. A surface that composed the dead sentence out of pieces, or
    from data, would pass every grep above and still tell them to open a file.
    """
    rendered = {
        "proposals header":
            genesis._PROPOSALS_HEADER.format(marker=genesis.GENERATED_MARKER),
        "advisor action":
            advisor.detect_aging_drafts(_hatched_with_old_draft(),
                                        now=None)[0]["action"],
        "briefing receipt": Path(
            run_briefing._run_local_render(genesis_fn=lambda: [])
            ["send"]["receipt_path"]).read_text(encoding="utf-8"),
    }
    assert len(rendered) == 3
    for label, text in rendered.items():
        assert text.strip(), "%s rendered nothing — this arm checks nothing" % label
        assert not _DEAD.search(text), "%s still says move the row: %r" % (
            label, text[:300])
        assert genesis.RATIFY_HINT in text, (
            "%s carries no ratify instruction at all" % label)


def test_the_sanctioned_phrase_is_present_on_each_surface():
    """POSITIVE arm — the half a negative grep can never supply."""
    hint = getattr(genesis, "RATIFY_HINT", None)
    assert hint, "no sanctioned ratify phrase exists to put on these surfaces"
    assert hint in genesis._PROPOSALS_HEADER

    finding = advisor.detect_aging_drafts(_hatched_with_old_draft(), now=None)
    assert finding, "the aging-drafts detector produced nothing to check"
    assert hint in finding[0]["action"]

    body = run_briefing._run_local_render(genesis_fn=lambda: [])
    written = Path(body["send"]["receipt_path"]).read_text(encoding="utf-8")
    assert hint in written


@pytest.fixture(autouse=True)
def _sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path / "root"))
    (tmp_path / "root").mkdir(exist_ok=True)
    return tmp_path


_OLD_DRAFT_DOC = {
    "schema": "cabinet.outcomes-proposed/v1",
    "proposed_at": "2020-01-01T00:00:00Z",
    "outcomes": [{"id": "acme-001", "name": "Card", "status": "draft",
                  "captain_ratified": False}],
}


def _hatched_with_old_draft() -> Path:
    root = Path(__import__("tempfile").mkdtemp(prefix="ratify-hint-"))
    path = root / genesis.PROPOSALS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(_OLD_DRAFT_DOC, sort_keys=False),
                    encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# A1.4 — the ARTIFACT half: a hatched root already carries the dead paragraph.
# ---------------------------------------------------------------------------
def _hatched_with_stale_header(root: Path) -> Path:
    """A proposals file exactly as an instance hatched before the tap has it."""
    stale_header = (
        "# instance/config/outcomes-proposed.yml — org-PROPOSED outcome cards (genesis).\n"
        "# %s (ONBOARD-1)\n"
        "#\n"
        "# PROPOSE-ONLY: every row is status: draft + captain_ratified: false. The\n"
        "# mission compiler reads ONLY instance/config/outcomes.yml (filename gate), so\n"
        % genesis.GENERATED_MARKER
    ) + _DEAD_PARAGRAPH
    doc = {
        "schema": "cabinet.outcomes-proposed/v1",
        "proposed_by": "onboarding-genesis",
        "proposed_at": "2026-08-01T00:00:00Z",
        "outcomes": [{
            "id": "acme-001", "name": "Card acme-001", "status": "draft",
            "captain_ratified": False, "what": "ship it", "why": "asked",
            "proof_expected": "a receipt",
            "measurable_criteria": ["a receipt"],
            "proposed_by": "onboarding-genesis",
        }],
    }
    path = root / genesis.PROPOSALS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stale_header + yaml.safe_dump(doc, sort_keys=False),
                    encoding="utf-8")
    return path


#: The dead paragraph EXACTLY as every instance hatched before the tap carries
#: it — written out here rather than imported, so these arms describe the
#: artifact on disk and cannot be silently weakened by editing the healer.
_DEAD_PARAGRAPH = (
    "# nothing in this file can activate itself. To ratify a card: review it, edit\n"
    "# freely, then move the row into instance/config/outcomes.yml with\n"
    "# status: active + captain_ratified: true. To reject: delete the row (a note\n"
    "# in the decisions ledger beats silence).\n"
)


def test_the_healer_matches_the_artifact_on_disk():
    """The oracle and the hatched artifact are the SAME bytes. A healer whose
    pattern has drifted from what instances carry heals nothing."""
    assert getattr(genesis, "_STALE_RATIFY_PARAGRAPH", None) == _DEAD_PARAGRAPH


def test_the_hatched_root_premise_holds(tmp_path):
    """Without this, the two arms below could pass over a file that never
    carried the dead sentence."""
    path = _hatched_with_stale_header(tmp_path)
    raw = path.read_text(encoding="utf-8")
    assert raw.count(_DEAD_PARAGRAPH) == 1
    assert _DEAD.search(raw)


def test_merge_proposals_heals_a_stale_header_on_a_hatched_root(tmp_path):
    path = _hatched_with_stale_header(tmp_path)
    before = path.read_text(encoding="utf-8").count(_DEAD_PARAGRAPH)
    genesis.merge_proposals(
        [{"id": "acme-002", "name": "Card acme-002", "lane": None,
          "what": "another", "why": "asked", "proof_expected": "a receipt",
          "proposed_by": "onboarding-genesis"}],
        tmp_path, answers={}, now="2026-09-01T00:00:00Z")
    after_raw = path.read_text(encoding="utf-8")
    after = after_raw.count(_DEAD_PARAGRAPH)
    assert (before, after) == (1, 0), "the occurrence count did not change"
    assert genesis.RATIFY_HINT in after_raw
    assert not _DEAD.search(after_raw)


def test_ratify_heals_a_stale_header_on_a_hatched_root(tmp_path):
    from framework.outcomes.ratify import ratify
    path = _hatched_with_stale_header(tmp_path)
    assert path.read_text(encoding="utf-8").count(_DEAD_PARAGRAPH) == 1
    res = ratify("acme-001", door="web", principal="s", root=tmp_path)
    assert res["status"] == "ratified", res
    after_raw = path.read_text(encoding="utf-8")
    assert after_raw.count(_DEAD_PARAGRAPH) == 0
    assert genesis.RATIFY_HINT in after_raw


def test_rewrite_is_a_no_op_on_a_healed_file():
    header = genesis._PROPOSALS_HEADER.format(marker=genesis.GENERATED_MARKER)
    healed, count = genesis.rewrite_stale_proposals_header(header)
    assert count == 0 and healed == header
