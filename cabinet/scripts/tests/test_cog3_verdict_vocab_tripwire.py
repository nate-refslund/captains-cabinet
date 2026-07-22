"""COG-3 §3 consequence row + §6.4 — the VERDICT-VOCABULARY DRIFT TRIPWIRE.

THE ONE SUITE IN THE COG-3 SET THAT IS RUNNABLE **AND GREEN TODAY.** It pins no
future graph surface — it tests the ALREADY-SHIPPED consequence vocabulary the
graph's promotion rule depends on, so that any drift in that domain vocabulary
surfaces in CI *before* it can silently loosen (or fail-open) the graph's
`verdict_human`-only promotion discriminator.

WHY THIS LIVES HERE (and imports the fidelity tree, which the graph never may):
  The graph (`framework/objectives/`) is FORBIDDEN from importing
  `framework.fidelity.consequence` — its module import loads the action plane
  (attack C-B1, `consequence.py:33`). So the graph pins the literal
  `"verdict_human"` as a GRAPH-OWNED frozen constant and evaluates the
  discriminator over SERVED claim bytes (§6.4). That decoupling means a rename
  or set-change in the consequence domain's `_REVIEW_SOURCES` would NOT break
  the graph at import time — it would silently make every promotion attempt
  fail-closed (edges stop promoting). Honest, but invisible. THIS TEST is the
  bridge: it lives in `cabinet/scripts/tests/` (OUTSIDE the objectives import
  pin — a TEST importing fidelity is fine; only `framework/objectives/**` is
  banned), imports the domain's `_REVIEW_SOURCES` + `compute_ratios`, and pins
  BOTH the vocabulary set AND the fail-closed absent-source behavior — so drift
  is a RED CI job, not a silent capability change (§3 disposition row; §6.4
  "drift tripwire: §3 consequence row").

FAILURE SIGNATURE: none — this suite is GREEN today. It tests shipped code
(`framework.fidelity.consequence`, byte-verified at S0). If it ever goes RED,
the consequence domain vocabulary or its fail-closed doctrine DRIFTED, and the
graph's promotion rule (`verdict_human`-only) must be reconciled consciously.

S0: interpreter python3.12. No DSN, no postgres — `compute_ratios` accepts an
explicit in-memory `ledger` list (`consequence.py:820`), so every row here is a
hand-built dict, no file seeding, no fold.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; Fable-5 two-tier law (test-authoring).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_ROOT = str(_HERE.parents[2])
for _p in (str(_HERE), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# The DELIBERATE fidelity import (§3 tripwire — the graph itself may NOT do
# this; a test in cabinet/scripts/tests/ may, and MUST, to catch domain drift).
from framework.fidelity import consequence  # noqa: E402

# The graph-owned frozen constant (§5.2 P3 / §6.4): the ONLY promotion-fuel
# source. The graph pins THIS literal; the tripwire binds it to the domain set.
GRAPH_PROMOTION_SOURCE = "verdict_human"

# The exact vocabulary the graph's §5.2 discriminator was written against
# (`consequence.py:126`). A drift here is exactly what this suite must catch.
EXPECTED_REVIEW_SOURCES = frozenset(
    {"verdict_human", "verdict_judge", "system", "verdict_gate"})


def _cell_of(ledger):
    """Run the SHIPPED `compute_ratios` over an explicit in-memory ledger and
    return the single graduation cell (every row here keys to ONE cell)."""
    cells = consequence.compute_ratios(ledger=ledger)
    assert len(cells) == 1, "fixture invariant: all rows share one graduation cell"
    return next(iter(cells.values()))


def _row(verdict, source, *, actor_id="cos", action="ship", subject="release/1"):
    """One consequence-ledger row carrying a review.{verdict[,source]}. `source`
    None => the review omits `source` (the absent-source / legacy case)."""
    review = {"verdict": verdict}
    if source is not None:
        review["source"] = source
    return {"ts": "2026-07-20T08:00:00Z",
            "actor": {"kind": "officer", "id": actor_id},
            "lane": "acting", "action": action, "subject": subject,
            "review": review}


# ===========================================================================
# (1) VOCABULARY MEMBERSHIP + EXACT SET — the drift catch
# ===========================================================================

def test_review_sources_membership_covers_the_graph_discriminator():
    # §6.4: the graph's promotion discriminator source=='verdict_human' must be a
    # member of the domain's `_REVIEW_SOURCES`; the machine sources the graph
    # refuses (verdict_judge/verdict_gate) and the non-judgment `system` are the
    # other members. Missing membership => the discriminator drifted.
    for src in ("verdict_human", "verdict_judge", "system", "verdict_gate"):
        assert src in consequence._REVIEW_SOURCES, \
            f"§6.4: '{src}' vanished from consequence._REVIEW_SOURCES (drift)"


def test_review_sources_is_EXACTLY_the_pinned_set():
    # §3 tripwire: the set is EXACTLY these four. A NEW source (e.g. a future
    # 'verdict_panel') added upstream lands here RED — forcing a conscious
    # decision on whether the graph's verdict_human-only rule (§5.2 P3) should
    # admit it, rather than the graph silently treating it as promotion-inert.
    assert frozenset(consequence._REVIEW_SOURCES) == EXPECTED_REVIEW_SOURCES, (
        "§3: consequence._REVIEW_SOURCES drifted from the set the graph's §5.2 "
        f"discriminator was pinned against ({sorted(EXPECTED_REVIEW_SOURCES)})")


def test_graph_promotion_source_literal_is_the_human_verdict_token():
    # §5.2 P3 / Captain resolution 2026-07-22: the graph-owned frozen constant is
    # the literal 'verdict_human' — human judgment (Captain OR any other person,
    # incl. via comms), NEVER machine/LLM. Bind the graph's literal to the domain.
    assert GRAPH_PROMOTION_SOURCE == "verdict_human"
    assert GRAPH_PROMOTION_SOURCE in consequence._REVIEW_SOURCES


# ===========================================================================
# (2) FAIL-CLOSED ABSENT-SOURCE DOCTRINE — the shipped RUNTIME behavior
#     (consequence.py:110-125 / compute_ratios:899-941) still holds
# ===========================================================================

def test_verdict_human_confirm_is_the_ONLY_promotion_fuel():
    # consequence.py:929 — a HUMAN confirm is the promotion fuel (confirmed++).
    # This is the exact leg the graph's §5.2 P3 mirrors (strictly narrower).
    cell = _cell_of([_row("confirmed", "verdict_human")])
    assert cell.confirmed == 1, "§6.4: a verdict_human confirm must count as fuel"
    assert cell.wrong == 0


def test_verdict_judge_confirm_is_promotion_INERT():
    # consequence.py:110-113 + :928-939 — a verdict_judge (LLM) confirm never
    # increments the promotion fuel. This is the fail-closed behavior the graph
    # relies on so an LLM's confident confirm can NEVER mint intervention_supported
    # (attack C-B2). If this goes RED, machine judgment became promotion fuel.
    cell = _cell_of([_row("confirmed", "verdict_judge")])
    assert cell.confirmed == 0, "§6.4: a verdict_judge confirm must stay inert"


def test_verdict_gate_confirm_is_inert_while_the_A3_label_floor_is_absent():
    # consequence.py:800-816 (_label_floor_met == False until A3 ships) +
    # :931-939 — a verdict_gate (machine) confirm fuels promotion ONLY inside a
    # label-floor-met period; none exist today, so it stays inert. The graph
    # refuses verdict_gate CATEGORICALLY (§6.4) regardless, but this pins the
    # DOMAIN's own fail-closed posture that the graph's rule is narrower than.
    cell = _cell_of([_row("confirmed", "verdict_gate")])
    assert cell.confirmed == 0, "§6.4: verdict_gate confirm inert (A3 floor absent)"


def test_system_source_confirm_is_promotion_inert():
    # consequence.py:114-115 — 'system' = non-judgment closure; never fuel.
    cell = _cell_of([_row("confirmed", "system")])
    assert cell.confirmed == 0, "§6.4: a 'system' confirm must stay inert"


def test_absent_source_confirm_is_fail_closed_inert():
    # consequence.py:114-116 — an ABSENT review.source (legacy/unattributed) is
    # treated as NOT human: fail-closed, never promotion fuel. This is THE
    # absent-source doctrine the §3 row names (:110-125); the graph's §5.2
    # human-confirm predicate depends on it (absent source => promotion-inert).
    cell = _cell_of([_row("confirmed", None)])
    assert cell.confirmed == 0, "§6.4: an absent-source confirm must fail closed"


def test_label_floor_is_fail_closed_False_until_the_A3_sensor_exists():
    # consequence.py:800-816 — the A3 sensor does not exist yet; NO period is
    # label-floor-met, so machine (gate) confirms fuel promotion in exactly zero
    # periods. Absence NARROWS from zero — wiring A3 can only ever widen, under a
    # later explicit change. If this returns True, the fail-closed floor drifted.
    assert consequence._label_floor_met("2026-07-20T08:00:00Z") is False


def test_wrong_from_ANY_source_counts_as_demotion_grade():
    # consequence.py:940-941 — `wrong` counts from ANY source (human OR machine).
    # The graph MIRRORS this as a CAP, not a refutation (§5.2 machine-contested):
    # machine-wrong demotes/holds (P4), only human-wrong falsifies (P2). This
    # pins the domain's wrong-from-any-source rule the graph's asymmetry rests on.
    for src in ("verdict_human", "verdict_judge", "verdict_gate", "system", None):
        cell = _cell_of([_row("wrong", src)])
        assert cell.wrong == 1, f"§5.2: a '{src}' wrong must be demotion-grade"
        assert cell.confirmed == 0


def test_the_promotion_asymmetry_is_intact_end_to_end():
    # §5.2/§6.4 the whole doctrine in one assertion: over a mixed ledger, ONLY
    # the human confirm fuels promotion; every machine/absent confirm is inert;
    # every wrong (any source) demotes. This is the exact shape the graph's
    # verdict_human-only promotion + wrong-caps rule is the strict narrowing of.
    ledger = [
        _row("confirmed", "verdict_human", subject="release/h"),   # +1 fuel
        _row("confirmed", "verdict_judge", subject="release/j"),   # inert
        _row("confirmed", "verdict_gate", subject="release/g"),    # inert (no floor)
        _row("confirmed", "system", subject="release/s"),          # inert
        _row("confirmed", None, subject="release/n"),              # inert (fail-closed)
        _row("wrong", "verdict_judge", subject="release/w"),       # +1 demotion
    ]
    cell = _cell_of(ledger)
    assert cell.confirmed == 1, "§6.4: exactly one (human) confirm is fuel"
    assert cell.wrong == 1, "§5.2: the machine wrong is demotion-grade"
