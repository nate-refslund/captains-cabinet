"""COG-3 §12.2 STEP 3 — the exhaustive mixed-evidence fixture over §5.2.

This is the step-3 deliverable of the tests-first order (contract §12.2): the
EXHAUSTIVE map of every predicate combination of the §5.2 ordered TOTAL
transition function to its pinned expected outcome, authored BEFORE the
implementation exists so the later `framework/objectives/states.py` must satisfy
these cells UNMODIFIED. The DATA TABLE (`CELLS`) below IS the deliverable; every
cell carries the §5.2 rule id it pins.

THE §5.2 ORDERED TOTAL FUNCTION (first matching rule wins; P1>P2>P3>P4>P5>P6;
the assumptions gate rides P3 AND P5 per ruling R-A — see the note below):
  P1  any bound view has a non-empty conflict_set, OR human-confirm AND
      human-wrong coexist                          -> hypothesized  [contested]
  P2  >=1 human-wrong (P1 missed)                   -> falsified
  P3  >=1 human-confirm AND edge assumptions non-empty (P1/P2 missed)
                                                     -> intervention_supported
  P4  >=1 direction-contradicting OR machine-contested
                                                     -> hypothesized  [direction_contested]
  P5  >=1 direction-supporting AND edge assumptions non-empty (R-A)
                                                     -> observationally_supported
  P6  otherwise (authored; incl. direction-support / confirm with EMPTY
      assumptions; zero admissible bindings; only purged leftovers; a
      direction-inert bare execution record) -> hypothesized
  (no edge authored) -> answer-level explicit `unknown` (never stored).

PREDICATES (all over an edge's bound views at the build cutoff, from SERVED
claim bytes — no fidelity import, §6.4):
  admissible(b)        := ref resolves in the as_of closure AND subject_key in
                          admissible_subjects AND view not source_purged.
  verified-join(b)     := consequence-stream (stream_rank==1) AND (i) the
                          identity digest recomputed from the claim's
                          (actor,action,subject,ts) equals the subject_key's
                          <identity-digest> suffix AND (ii) the claim's
                          (actor,action,subject) is in the edge's join_spec.
  human-confirm(b)     := admissible AND verified-join AND verdict=="confirmed"
                          AND source=="verdict_human".   [the ONLY promotion fuel]
  human-wrong(b)       := admissible AND verified-join AND verdict=="wrong"
                          AND source=="verdict_human".   [the ONLY refutation fuel]
  machine-contested(b) := admissible AND verified-join AND verdict=="wrong"
                          AND source!="verdict_human" (or absent).
  direction-*(b)       := admissible AND the adapter-pinned movement reading of
                          the claim on `dimension` is consistent-or-neutral /
                          opposite to the edge's expected_effect.

THE PER-ADAPTER DIRECTION READING — PINNED HERE (§5.2: "Per-adapter derivations
are pinned in the §12.2 step-3 exhaustive fixture — never implementer-invented"):
  * a claim carrying `review.verdict` reads its movement FROM the verdict:
      confirmed -> the expected effect (direction-SUPPORTING);
      wrong     -> the opposite       (direction-CONTRADICTING).
    This coupling is CONTRACT-FORCED: SIM-2/§5.2-P5 require a machine/absent-
    source CONFIRM (a confirmed verdict that fails P3's human discriminator) to
    "cap at observationally_supported" — i.e. to LAND in P5 — which is only
    reachable if a confirmed verdict is direction-supporting.
  * a claim carrying `observed_effect` (no verdict) reads it directly — a TOTAL
    rule over the closed movement enum {increase, decrease, maintain}:
      SUPPORTING     iff observed_effect in {expected_effect, "maintain"}
                     ("maintain" is the NEUTRAL reading — it never contradicts,
                     the §5.2 "consistent-OR-NEUTRAL" clause);
      CONTRADICTING  otherwise (every movement not in that set).
    Maintain semantics, pinned BOTH ways: an edge whose expected_effect is
    "maintain" is CONTRADICTED by ANY clear directional movement — observed
    increase AND observed decrease both contradict; only observed "maintain"
    supports. (Symmetrically, a "maintain" observation supports an increase- or
    decrease-expecting edge — neutral, never contradicting.)
  * a verified-join-eligible consequence claim carrying NEITHER a `review`
    sub-object NOR an `observed_effect` field has NO direction reading — it is
    direction-INERT, neither supporting nor contradicting (ruling R-B). "Neutral"
    in §5.2 means an affirmative maintain-consistent MOVEMENT reading, never the
    ABSENCE of a reading; an execution-happened record is not effect-evidence
    (else raw activity volume would mint support — Goodhart by the back door,
    SIM-4). Such a binding is admissible + verified-join-eligible yet yields no
    P4/P5 predicate, so an edge bound to ONLY such records lands at P6.

ASSUMPTIONS GATE P3 AND P5 (ruling R-A — STRICT; supersedes the rev-0 "only P3"
reading): the ordered function gates `edge.assumptions non-empty` at BOTH
promotion rungs that sit ABOVE hypothesized — P3 (intervention_supported) AND P5
(observationally_supported). Two evidence cites: (1) contract §4.2 assumptions
row — "REQUIRED non-empty for any edge deriving above hypothesized" (P5 IS above
hypothesized); (2) §11 SIM-4 negative-control mutant — "assumption-free promotion
above hypothesized" must FAIL, and observationally_supported is a promotion above
hypothesized. Consequence: an edge with a direction-supporting binding (or a
machine/absent-source confirm) but EMPTY assumptions does NOT reach P5 — it falls
through to P6 hypothesized. P2 (falsified — refutation, NOT above hypothesized)
and P4 (hypothesized itself — not above) keep their written conditions; the
assumptions conjunct is added to P5 ONLY (P3 already carried it). So the machine/
absent-source confirm cells SEED non-empty assumptions to exhibit the P5 cap
("caps AT observationally_supported for an otherwise-P5-eligible edge", never
"assumption-free promotion"); their assumptionless twins are pinned to P6 by
dedicated cells below.

THE PINNED API (THE surface `framework/objectives/states.py` must provide):
  states.derive_edge_state(edge, bound_views, cutoff)
        -> EdgeState(state: str, flags: frozenset[str])
     raises states.BuildFailure on out-of-admissible-subjects / dangling binding.
  `edge` exposes lib_cog3_fixtures.EdgeSpec's attributes; `bound_views` are real
  query.BeliefViews (which carry NO `kind` field — the state function
  STRUCTURALLY cannot key on belief kind, §5.2 header). See the wave report for
  the build-failure layering note.

FAILURE SIGNATURE (tests-first): `framework/objectives/` does NOT exist. Every
parametrized cell imports `framework.objectives.states` FIRST inside the test
body, so today it fails with `ModuleNotFoundError: No module named
'framework.objectives'` — the honest absence-of-implementation signature (never
a broken fixture, never a collection error — the import is in the body, and the
`TestFixtureSelfChecks` below prove the seeding is sound WITHOUT that import).

S0: interpreter python3.12. No DSN, no postgres — every seed is file-based
(jsonl belief protos + consequence ledger day files, §7.2).

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; Fable-5 two-tier law (test-authoring).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_ROOT = str(_HERE.parents[2])
for _p in (str(_HERE), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_cog3_fixtures as L  # noqa: E402  (NEVER framework.objectives — only the test body imports that)

BS = L.BindingSpec
Cell = L.EdgeCell


@pytest.fixture
def consequence_ledger(tmp_path, monkeypatch):
    """An isolated consequence-ledger dir wired through CABINET_EVENT_LOG_DIR
    (the operator-set env `consequence.py` reads), sim mode OFF — the exact D1
    idiom from `test_cog2_asof_fence.py`. Verdict bindings are file-seeded here;
    the reader picks them up via `read_consequence_protos`."""
    d = tmp_path / "events"
    d.mkdir()
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(d))
    monkeypatch.delenv("CABINET_SIM_MODE", raising=False)
    return d


# ===========================================================================
# THE DATA TABLE — every §5.2 predicate combination -> pinned (state, flags).
# Each row: (cell_id, EdgeCell seed-spec, ExpectedOutcome, pinning clause).
# ===========================================================================

_VOL_SUPPORTING = tuple(
    BS(role="observation", observed_effect="increase", tag=f"vol{i}")
    for i in range(100)
)

CELLS = [
    # ---- P3: promotion requires the FULL triple ----------------------------
    ("P3-human-confirm-triple",
     Cell(assumptions=True, bindings=(
         BS(role="verdict", verdict="confirmed", source="verdict_human", tag="hc"),)),
     L.expect_state(L.STATE_INTERVENTION_SUPPORTED),
     "§5.2 P3: intervention_supported reachable by EXACTLY this rule — the triple "
     "human-confirm (verdict_human confirm) + verified-join + non-empty assumptions."),

    ("P3-observation-kind-verdict-promotes",
     Cell(assumptions=True, bindings=(
         BS(role="verdict", verdict="confirmed", source="verdict_human", tag="ok"),)),
     L.expect_state(L.STATE_INTERVENTION_SUPPORTED),
     "§5.2 header: consequence beliefs ARE belief-kind 'observation' yet fuel "
     "promotion — NO rule keys on belief kind (A-M2); the view carries no kind field."),

    ("P3-beats-copresent-supporting-observation",
     Cell(assumptions=True, bindings=(
         BS(role="verdict", verdict="confirmed", source="verdict_human", tag="hc"),
         BS(role="observation", observed_effect="increase", tag="sup"))),
     L.expect_state(L.STATE_INTERVENTION_SUPPORTED),
     "§5.2 precedence P3>P5: promotion wins over a co-present direction-supporting "
     "observation (first matching rule wins)."),

    ("P3-purged-binding-inert-still-promotes",
     Cell(assumptions=True, bindings=(
         BS(role="verdict", verdict="confirmed", source="verdict_human", tag="hc"),
         BS(role="purged", tag="pg"))),
     L.expect_state(L.STATE_INTERVENTION_SUPPORTED),
     "§5.2 admissible(): a source_purged view is inert (neither support nor "
     "refutation) — it never blocks the human-confirm promotion."),

    # ---- R-A: assumptions gate P3 AND P5 -> assumptionless promotion = P6 -----
    ("P6-human-confirm-WITHOUT-assumptions",
     Cell(assumptions=False, bindings=(
         BS(role="verdict", verdict="confirmed", source="verdict_human", tag="hc"),)),
     L.expect_state(L.STATE_HYPOTHESIZED),
     "R-A (assumptions gate P3 AND P5). Walk: P1 no (no conflict, no human-wrong) "
     "-> P2 no (no human-wrong) -> P3 NO (assumptions empty) -> P4 no (a confirm is "
     "direction-supporting, not contradicting/machine-contested) -> P5 NO "
     "(direction-supporting BUT assumptions empty) -> P6 hypothesized. A "
     "human-confirm with no declared assumptions is an authored assertion with no "
     "ADMISSIBLE-above-hypothesized support (§4.2 'above hypothesized' + §11 SIM-4)."),

    ("P6-machine-confirm-verdict_judge-WITHOUT-assumptions",
     Cell(assumptions=False, bindings=(
         BS(role="verdict", verdict="confirmed", source="verdict_judge", tag="mj"),)),
     L.expect_state(L.STATE_HYPOTHESIZED),
     "R-A: the machine-confirm twin of the P5 cap — verdict_judge confirm is "
     "direction-supporting but assumptions are empty, so P5 does NOT fire -> P6. "
     "(Its assumptions-bearing sibling P5-machine-confirm-verdict_judge caps at "
     "observationally_supported; the ONLY difference is the assumptions gate.)"),

    ("P6-direction-supporting-observation-WITHOUT-assumptions",
     Cell(expected_effect="increase", assumptions=False, bindings=(
         BS(role="observation", observed_effect="increase", tag="ds0"),)),
     L.expect_state(L.STATE_HYPOTHESIZED),
     "R-A on the OBSERVATION path: a direction-supporting observation with EMPTY "
     "assumptions falls through P5 to P6 (catches an impl that gates P5-assumptions "
     "only for verdict bindings). Its assumptions-bearing twin below is P5."),

    ("P5-join-mismatch-confirm-never-promotes",
     Cell(assumptions=True, bindings=(
         BS(role="verdict", verdict="confirmed", source="verdict_human",
            join="mismatch", tag="jm"),)),
     L.expect_state(L.STATE_OBSERVATIONALLY_SUPPORTED),
     "§5.2b verified-join limb-(ii): a human confirm whose (actor,action,subject) "
     "misses the intervention's join_spec is NOT human-confirm -> P3 unreachable; "
     "direction-supporting -> P5. The mismatched-join seed NEVER promotes (SIM-4)."),

    # ---- machine / absent-source CONFIRM -> cap at P5 (never P3) ------------
    ("P5-machine-confirm-verdict_judge",
     Cell(assumptions=True, bindings=(
         BS(role="verdict", verdict="confirmed", source="verdict_judge", tag="mj"),)),
     L.expect_state(L.STATE_OBSERVATIONALLY_SUPPORTED),
     "§5.2 P3 discriminator source=='verdict_human' ONLY: a verdict_judge (LLM) "
     "confirm is promotion-inert -> caps at P5 (attack C-B2 / §6.4)."),

    ("P5-machine-confirm-verdict_gate",
     Cell(assumptions=True, bindings=(
         BS(role="verdict", verdict="confirmed", source="verdict_gate", tag="mg"),)),
     L.expect_state(L.STATE_OBSERVATIONALLY_SUPPORTED),
     "§6.4: the graph refuses verdict_gate CATEGORICALLY — a machine gate confirm "
     "caps at P5, floor-met or not (strictly narrower than the domain's rule)."),

    ("P5-machine-confirm-source_system",
     Cell(assumptions=True, bindings=(
         BS(role="verdict", verdict="confirmed", source="system", tag="ms"),)),
     L.expect_state(L.STATE_OBSERVATIONALLY_SUPPORTED),
     "§5.2 human-confirm: source 'system' != verdict_human -> promotion-inert, "
     "caps at P5."),

    ("P5-absent-source-confirm",
     Cell(assumptions=True, bindings=(
         BS(role="verdict", verdict="confirmed", source=None, tag="as"),)),
     L.expect_state(L.STATE_OBSERVATIONALLY_SUPPORTED),
     "§5.2 human-confirm fail-closed: an ABSENT review.source is promotion-inert "
     "(absent-source doctrine consequence.py:110-125) -> caps at P5."),

    # ---- P5: direction-supporting observations (no verdict; assumptions seeded
    #         so the edge is above-hypothesized-eligible per R-A) --------------
    ("P5-direction-supporting-observation",
     Cell(expected_effect="increase", assumptions=True, bindings=(
         BS(role="observation", observed_effect="increase", tag="ds"),)),
     L.expect_state(L.STATE_OBSERVATIONALLY_SUPPORTED),
     "§5.2 P5: a direction-supporting observation, edge assumptions non-empty (R-A) "
     "-> observationally_supported."),

    ("P5-direction-supporting-VOLUME-100-still-P5",
     Cell(expected_effect="increase", assumptions=True, bindings=_VOL_SUPPORTING),
     L.expect_state(L.STATE_OBSERVATIONALLY_SUPPORTED),
     "§5.2 P5 cap: NO observational VOLUME promotes — 100 supporting observations "
     "stay observationally_supported EVEN with assumptions satisfied (they never "
     "reach P3's human-confirm gate; SIM-4 volume mutant)."),

    ("P5-direction-neutral-maintain-supports",
     Cell(expected_effect="increase", assumptions=True, bindings=(
         BS(role="observation", observed_effect="maintain", tag="mt"),)),
     L.expect_state(L.STATE_OBSERVATIONALLY_SUPPORTED),
     "§5.2 direction-supporting is 'consistent-OR-NEUTRAL' — a 'maintain' reading "
     "supports (not contradicting); assumptions non-empty (R-A) -> P5."),

    # ---- P2: falsified requires human-wrong on a verified join -------------
    ("P2-human-wrong-falsified",
     Cell(assumptions=False, bindings=(
         BS(role="verdict", verdict="wrong", source="verdict_human", tag="hw"),)),
     L.expect_state(L.STATE_FALSIFIED),
     "§5.2 P2: falsified requires a human-wrong binding on a verified join — the "
     "SAME evidence bar as promotion (C-M8: 'refuted' earns the same gate as 'tested')."),

    ("P2-human-wrong-with-assumptions-still-falsified",
     Cell(assumptions=True, bindings=(
         BS(role="verdict", verdict="wrong", source="verdict_human", tag="hw"),)),
     L.expect_state(L.STATE_FALSIFIED),
     "§5.2 P2 does not gate on assumptions — falsified holds with them present too."),

    ("P2-human-wrong-beats-copresent-supporting-observation",
     Cell(bindings=(
         BS(role="verdict", verdict="wrong", source="verdict_human", tag="hw"),
         BS(role="observation", observed_effect="increase", tag="sup"))),
     L.expect_state(L.STATE_FALSIFIED),
     "§5.2 precedence P2>P5: a human-wrong refutation wins over a co-present "
     "direction-supporting observation."),

    # ---- P4: machine-contested / direction-contradicting -------------------
    ("P4-machine-wrong-verdict_judge",
     Cell(bindings=(
         BS(role="verdict", verdict="wrong", source="verdict_judge", tag="mw"),)),
     L.expect_state(L.STATE_HYPOTHESIZED, L.FLAG_DIRECTION_CONTESTED),
     "§5.2 P4: a machine-contested (non-human wrong) binding caps at "
     "hypothesized+direction_contested — machine judgment WEAKENS, never falsifies."),

    ("P4-machine-wrong-verdict_gate",
     Cell(bindings=(
         BS(role="verdict", verdict="wrong", source="verdict_gate", tag="mw"),)),
     L.expect_state(L.STATE_HYPOTHESIZED, L.FLAG_DIRECTION_CONTESTED),
     "§5.2 machine-contested: a verdict_gate wrong is demotion-grade, never "
     "refutation-grade -> P4."),

    ("P4-absent-source-wrong-is-machine-contested",
     Cell(bindings=(
         BS(role="verdict", verdict="wrong", source=None, tag="aw"),)),
     L.expect_state(L.STATE_HYPOTHESIZED, L.FLAG_DIRECTION_CONTESTED),
     "§5.2 machine-contested: 'source != verdict_human (or ABSENT)' — an "
     "absent-source wrong is machine-contested (P4), never P2."),

    ("P4-direction-contradicting-observation",
     Cell(expected_effect="increase", bindings=(
         BS(role="observation", observed_effect="decrease", tag="dc"),)),
     L.expect_state(L.STATE_HYPOTHESIZED, L.FLAG_DIRECTION_CONTESTED),
     "§5.2 P4: a direction-contradicting observation -> hypothesized+"
     "direction_contested (observation weakens to hypothesis; :108 mirror)."),

    ("P4-join-mismatch-wrong-never-falsifies",
     Cell(bindings=(
         BS(role="verdict", verdict="wrong", source="verdict_human",
            join="mismatch", tag="jw"),)),
     L.expect_state(L.STATE_HYPOTHESIZED, L.FLAG_DIRECTION_CONTESTED),
     "§5.2b: a human-wrong that FAILS verified-join is not human-wrong -> P2 "
     "unreachable; direction-contradicting -> P4 (falsified needs a verified join, C-M8)."),

    ("P4-machine-contested-beats-copresent-supporting",
     Cell(bindings=(
         BS(role="verdict", verdict="wrong", source="verdict_judge", tag="mw"),
         BS(role="observation", observed_effect="increase", tag="sup"))),
     L.expect_state(L.STATE_HYPOTHESIZED, L.FLAG_DIRECTION_CONTESTED),
     "§5.2 precedence P4>P5: machine-contested caps the edge even beside a "
     "direction-supporting observation."),

    # ---- P1: contested ground beats EVERYTHING -----------------------------
    ("P1-contested-conflict-set-only",
     Cell(bindings=(BS(role="observation", contested=True, tag="ct"),)),
     L.expect_state(L.STATE_HYPOTHESIZED, L.FLAG_CONTESTED),
     "§5.2 P1: a bound view carrying a non-empty conflict_set -> hypothesized+"
     "contested (query.py:269-286)."),

    ("P1-contested-beats-human-confirm-triple",
     Cell(assumptions=True, bindings=(
         BS(role="observation", contested=True, tag="ct"),
         BS(role="verdict", verdict="confirmed", source="verdict_human", tag="hc"))),
     L.expect_state(L.STATE_HYPOTHESIZED, L.FLAG_CONTESTED),
     "§5.2 P1 > P3: contested ground beats a would-be promotion — certainty is "
     "never manufactured over contradicted ground (SIM-2)."),

    ("P1-two-human-verdicts-disagree",
     Cell(assumptions=True, bindings=(
         BS(role="verdict", verdict="confirmed", source="verdict_human", tag="hc"),
         BS(role="verdict", verdict="wrong", source="verdict_human", tag="hw"))),
     L.expect_state(L.STATE_HYPOTHESIZED, L.FLAG_CONTESTED),
     "§5.2 P1 second clause: human-confirm AND human-wrong coexisting is "
     "contradicted ground -> hypothesized+contested (beats both P2 and P3)."),

    # ---- P6: authored, no support ------------------------------------------
    ("P6-zero-bindings-authored",
     Cell(bindings=()),
     L.expect_state(L.STATE_HYPOTHESIZED),
     "§5.2 P6: an authored edge with zero admissible bindings -> hypothesized "
     "(an authored assertion with no support)."),

    ("P6-only-purged-leftovers",
     Cell(bindings=(BS(role="purged", tag="pg"),)),
     L.expect_state(L.STATE_HYPOTHESIZED),
     "§5.2 P6: only purged leftovers (source_purged is inert) -> hypothesized."),

    # ---- answer-level unknown (never-authored edge) ------------------------
    ("ANSWER-never-authored-unknown",
     Cell(authored=False, bindings=()),
     L.expect_state(L.STATE_UNKNOWN),
     "§5.2: NO edge authored => answer-level explicit `unknown` — the fifth state "
     "lives in ANSWERS, never in storage (analog of query.py:247-249)."),

    # ---- human x machine verdict MIX cells (precedence pins; reviewer MF1) --
    #  Walk each: two verdict bindings sit on DISTINCT release/<tag> subjects, so
    #  their consequence identities differ -> NO conflict_set couples them (P1's
    #  first clause never fires here); only P1's SECOND clause (human-confirm AND
    #  human-wrong coexisting) can, and only when BOTH are human.
    ("MIX-human-confirm-beats-machine-wrong-P3",
     Cell(assumptions=True, bindings=(
         BS(role="verdict", verdict="confirmed", source="verdict_human", tag="hc"),
         BS(role="verdict", verdict="wrong", source="verdict_judge", tag="mw"))),
     L.expect_state(L.STATE_INTERVENTION_SUPPORTED),
     "MF1(a) precedence P3>P4. Walk: P1 no (distinct subjects=no conflict_set; the "
     "wrong is MACHINE so no human-confirm+human-wrong pair) -> P2 no (no "
     "human-wrong) -> P3 YES (human-confirm + assumptions). The co-present "
     "machine-wrong is P4-grade but P3 fires FIRST -> intervention_supported. "
     "Catches a P4-before-P3 impl (which would return hypothesized+direction_contested)."),

    ("MIX-human-wrong-beats-machine-confirm-P2",
     Cell(assumptions=False, bindings=(
         BS(role="verdict", verdict="wrong", source="verdict_human", tag="hw"),
         BS(role="verdict", verdict="confirmed", source="verdict_judge", tag="mc"))),
     L.expect_state(L.STATE_FALSIFIED),
     "MF1(b) P2, guarding P1's second clause. Walk: P1 no (distinct subjects; the "
     "confirm is MACHINE, so NOT a human-confirm+human-wrong pair) -> P2 YES "
     "(human-wrong) -> falsified. Catches a sloppy P1 that fires 'contested' on "
     "ANY confirm+ANY wrong regardless of source (it must not: machine-confirm is "
     "not human-confirm)."),

    ("MIX-machine-confirm-and-machine-wrong-no-human-P4",
     Cell(assumptions=True, bindings=(
         BS(role="verdict", verdict="confirmed", source="verdict_judge", tag="mc"),
         BS(role="verdict", verdict="wrong", source="verdict_gate", tag="mw"))),
     L.expect_state(L.STATE_HYPOTHESIZED, L.FLAG_DIRECTION_CONTESTED),
     "MF1(c) P4 with NO human verdicts -> P1 second clause must NOT fire. Walk: P1 "
     "no (distinct subjects=no conflict_set; neither verdict is human) -> P2 no (no "
     "human-wrong) -> P3 no (no human-confirm) -> P4 YES (verdict_gate wrong is "
     "machine-contested). The machine-confirm would be P5 (assumptions present) but "
     "P4 caps it -> hypothesized+direction_contested."),

    # ---- VARIED expected_effect: direction reading is not increase-only (MF2)
    ("P4-expect-decrease-observed-increase-contradicts",
     Cell(expected_effect="decrease", bindings=(
         BS(role="observation", observed_effect="increase", tag="di"),)),
     L.expect_state(L.STATE_HYPOTHESIZED, L.FLAG_DIRECTION_CONTESTED),
     "MF2: expected 'decrease', observed 'increase' is NOT in {decrease,maintain} "
     "-> direction-contradicting -> P4. Kills a direction-ignoring / increase-only "
     "impl."),

    ("P5-expect-decrease-observed-decrease-supports",
     Cell(expected_effect="decrease", assumptions=True, bindings=(
         BS(role="observation", observed_effect="decrease", tag="dd"),)),
     L.expect_state(L.STATE_OBSERVATIONALLY_SUPPORTED),
     "MF2: expected 'decrease', observed 'decrease' -> direction-supporting; "
     "assumptions non-empty (R-A) -> P5. The support reading tracks expected_effect, "
     "not a hardcoded 'increase'."),

    ("P5-expect-maintain-observed-maintain-supports",
     Cell(expected_effect="maintain", assumptions=True, bindings=(
         BS(role="observation", observed_effect="maintain", tag="mm"),)),
     L.expect_state(L.STATE_OBSERVATIONALLY_SUPPORTED),
     "MF2 maintain-way-A: expected 'maintain', observed 'maintain' -> supporting "
     "(the reading, :51-55); assumptions non-empty (R-A) -> P5."),

    ("P4-expect-maintain-observed-increase-contradicts",
     Cell(expected_effect="maintain", bindings=(
         BS(role="observation", observed_effect="increase", tag="mi"),)),
     L.expect_state(L.STATE_HYPOTHESIZED, L.FLAG_DIRECTION_CONTESTED),
     "MF2 maintain-way-B: a 'maintain' edge is CONTRADICTED by ANY clear directional "
     "movement (:51-55) — observed 'increase' -> direction-contradicting -> P4."),

    ("P4-expect-maintain-observed-decrease-contradicts",
     Cell(expected_effect="maintain", bindings=(
         BS(role="observation", observed_effect="decrease", tag="md"),)),
     L.expect_state(L.STATE_HYPOTHESIZED, L.FLAG_DIRECTION_CONTESTED),
     "MF2 maintain-way-B (mirror): observed 'decrease' ALSO contradicts a 'maintain' "
     "edge — BOTH movements break maintain (pins the symmetry, not just one side)."),

    # ---- R-B: a verified-join-eligible BARE consequence record is inert ------
    ("P6-consequence-executed-no-review-no-effect-inert",
     Cell(assumptions=True, bindings=(
         BS(role="verdict", verdict=None, source=None, tag="ex"),)),
     L.expect_state(L.STATE_HYPOTHESIZED),
     "R-B: a rank-1 consequence view that is verified-join-eligible but carries "
     "NEITHER review NOR observed_effect has NO direction reading -> direction-inert. "
     "Walk: P1 no -> P2 no (no human-wrong) -> P3 no (no human-confirm) -> P4 no "
     "(no contradicting/machine-contested reading) -> P5 no (no direction-supporting "
     "reading, even though assumptions are present) -> P6. Execution-happened is not "
     "effect-evidence — else activity volume mints support (Goodhart by back door)."),

    # ---- anti-preponderance: ONE contradicting binding caps (reviewer MF4) ---
    ("P4-anti-preponderance-100-support-1-contradict",
     Cell(expected_effect="increase", assumptions=True,
          bindings=_VOL_SUPPORTING + (
              BS(role="observation", observed_effect="decrease", tag="contra"),)),
     L.expect_state(L.STATE_HYPOTHESIZED, L.FLAG_DIRECTION_CONTESTED),
     "MF4: 100 direction-supporting observations + ONE direction-contradicting. "
     "Walk: P1 no (distinct subjects) -> P2/P3 no (no verdicts) -> P4 YES (>=1 "
     "direction-contradicting) -> hypothesized+direction_contested. ANY single "
     "contradicting binding caps the edge — no majority/preponderance vote (the "
     "P5 assumptions gate is satisfied, so the ONLY thing stopping P5 is the one "
     "contradicting binding)."),

    # ---- structural BUILD FAILURES (not states) ----------------------------
    ("BUILD-out-of-admissible-subjects",
     Cell(bindings=(
         BS(role="verdict", verdict="confirmed", source="verdict_human",
            admissible=False, tag="oa"),)),
     L.expect_build_failure(),
     "§4.2/§5.1(3): a binding whose subject_key is NOT in admissible_subjects is "
     "a structural build failure, never a silent skip (SIM-4 C-M3a)."),

    ("BUILD-dangling-binding",
     Cell(bindings=(
         BS(role="verdict", verdict="confirmed", source="verdict_human",
            resolve=False, tag="dg"),)),
     L.expect_build_failure(),
     "§5.1(3): an evidence ref that does not resolve inside the as_of closure is "
     "a structural build failure, never a silent empty set (P6 rev-0 §15 Q6)."),
]


# ===========================================================================
# TESTS-FIRST STATE FUNCTION — imports framework.objectives.states FIRST, so
# TODAY every cell fails with the absence-of-implementation signature.
# ===========================================================================

def _import_states():
    """The honest failure: `framework.objectives` does not exist this phase, so
    this raises `ModuleNotFoundError: No module named 'framework.objectives'` —
    the pinned absence signature. NO importorskip: this MUST fail, not skip."""
    from framework.objectives import states  # noqa: F401
    return states


@pytest.mark.parametrize(
    "cell_id,cell,expected,clause", CELLS, ids=[c[0] for c in CELLS])
def test_edge_state_derivation(consequence_ledger, cell_id, cell, expected, clause):
    # Import FIRST — every cell fails identically on the absence of the
    # implementation today; when it lands, the seeded reality below is asserted.
    states = _import_states()

    edge, bound_views = L.materialize(cell, consequence_ledger)

    if expected.kind == "build_failure":
        with pytest.raises(states.BuildFailure):
            states.derive_edge_state(edge, bound_views, L.CUTOFF)
        return

    result = states.derive_edge_state(edge, bound_views, L.CUTOFF)
    assert result.state == expected.state, f"{cell_id}: {clause}"
    assert frozenset(result.flags) == expected.flags, \
        f"{cell_id}: flags — {clause}"
    # the derived state is always one of the pinned five (no invented state).
    assert result.state in L.CAPTAIN_VOCAB, \
        f"{cell_id}: §5.2 state must be one of the five derived states"


def test_captain_vocabulary_is_bijective_over_the_derived_states():
    """§5.2: the internal states map BIJECTIVELY to the Captain vocabulary in one
    table in framework/objectives/query.py, round-trip-tested. This pins the
    round trip against the implementation's table."""
    from framework.objectives import query as obj_query  # absence signature today
    for internal, captain in L.CAPTAIN_VOCAB.items():
        # §5.2: internal -> Captain word -> internal is the identity (bijection).
        assert obj_query.to_captain_word(internal) == captain
        assert obj_query.to_internal_state(captain) == internal


# ===========================================================================
# FIXTURE SELF-CHECKS — pass TODAY (no framework.objectives import). They prove
# the step-3 seeds are REAL substrate output, so each cell is a meaningful
# contract the moment the implementation lands (a bad fixture would otherwise
# fail for the WRONG reason once framework.objectives exists).
# ===========================================================================

class TestFixtureSelfChecks:
    def test_human_confirm_seed_is_verified_join_eligible_verdict_human(self, consequence_ledger):
        # the P3 seed: a consequence-stream (rank 1) view whose claim carries a
        # verdict_human confirm, whose identity digest (limb i) matches its
        # subject_key, and whose identity is IN the edge join_spec (limb ii).
        cell = Cell(assumptions=True, bindings=(
            BS(role="verdict", verdict="confirmed", source="verdict_human", tag="hc"),))
        edge, views = L.materialize(cell, consequence_ledger)
        assert len(views) == 1
        v = views[0]
        assert v.provenance["stream_rank"] == 1              # consequence stream
        assert v.value["review"] == {"verdict": "confirmed", "source": "verdict_human"}
        # verified-join limb (i): recompute identity digest from the SERVED bytes.
        assert L.consequence_subject_key(v.value) == v.subject_key
        # verified-join limb (ii): identity IN join_spec.
        assert L.consequence_join_key(v.value) in edge.join_spec
        assert v.subject_key in edge.admissible_subjects
        assert edge.assumptions                              # non-empty -> P3 eligible

    def test_consequence_belief_kind_is_observation(self, consequence_ledger):
        # §5.2 header premise: consequence beliefs ARE kind 'observation' — proof
        # that a promotion-fueling belief is observation-kind (so no rule may key
        # on kind). The BeliefView carries no kind field, so the state function
        # structurally cannot discriminate; the underlying belief confirms it.
        L.seed_consequence_ledger(consequence_ledger, [
            L.consequence_row("ship", "release/k",
                              verdict="confirmed", source="verdict_human")])
        beliefs = L.fold_beliefs(L.consequence_protos())
        assert beliefs and all(b.kind == "observation" for b in beliefs)
        assert not hasattr(L.query.BeliefView, "kind")       # view cannot key on kind

    def test_contested_seed_yields_nonempty_conflict_set(self, consequence_ledger):
        cell = Cell(bindings=(BS(role="observation", contested=True, tag="ct"),))
        _edge, views = L.materialize(cell, consequence_ledger)
        assert len(views) == 2                                # two independent heads
        assert all(v.conflict_set for v in views)            # P1 seam is real

    def test_purged_seed_is_source_purged_and_inert(self, consequence_ledger):
        cell = Cell(bindings=(BS(role="purged", tag="pg"),))
        _edge, views = L.materialize(cell, consequence_ledger)
        assert len(views) == 1
        assert views[0].claim_completeness == L.belief.COMPLETENESS_PURGED
        assert views[0].value is None                        # purge erased the claim

    def test_machine_and_absent_source_seeds_are_not_human(self, consequence_ledger):
        for src in ("verdict_judge", "verdict_gate", "system", None):
            cell = Cell(assumptions=True, bindings=(
                BS(role="verdict", verdict="confirmed", source=src, tag="m"),))
            _edge, views = L.materialize(cell, consequence_ledger)
            got = views[0].value.get("review", {}).get("source")
            assert got != "verdict_human"                    # promotion-inert source

    def test_direction_observation_carries_effect_no_verdict(self, consequence_ledger):
        cell = Cell(bindings=(BS(role="observation", observed_effect="increase", tag="d"),))
        _edge, views = L.materialize(cell, consequence_ledger)
        assert views[0].value == {"observed_effect": "increase"}
        assert "review" not in views[0].value

    def test_join_mismatch_seed_fails_limb_ii_only(self, consequence_ledger):
        cell = Cell(assumptions=True, bindings=(
            BS(role="verdict", verdict="confirmed", source="verdict_human",
               join="mismatch", tag="jm"),))
        edge, views = L.materialize(cell, consequence_ledger)
        v = views[0]
        assert v.subject_key in edge.admissible_subjects            # admissible holds
        assert L.consequence_subject_key(v.value) == v.subject_key  # limb i holds
        assert L.consequence_join_key(v.value) not in edge.join_spec  # limb ii FAILS
        assert edge.join_spec                                       # but join_spec is non-empty

    def test_out_of_admissible_seed_serves_but_is_excluded(self, consequence_ledger):
        cell = Cell(bindings=(
            BS(role="verdict", verdict="confirmed", source="verdict_human",
               admissible=False, tag="oa"),))
        edge, views = L.materialize(cell, consequence_ledger)
        assert len(views) == 1                               # the view DID resolve
        assert views[0].subject_key not in edge.admissible_subjects  # yet excluded
        assert edge.evidence_bindings                        # the ref is authored

    def test_dangling_seed_has_ref_without_a_view(self, consequence_ledger):
        cell = Cell(bindings=(
            BS(role="verdict", verdict="confirmed", source="verdict_human",
               resolve=False, tag="dg"),))
        edge, views = L.materialize(cell, consequence_ledger)
        assert views == ()                                   # nothing resolved
        served_ids = {v.belief_id for v in views}
        assert any(b.belief_id not in served_ids for b in edge.evidence_bindings)

    def test_volume_seed_is_100_distinct_supporting_views(self, consequence_ledger):
        cell = Cell(expected_effect="increase", bindings=_VOL_SUPPORTING)
        _edge, views = L.materialize(cell, consequence_ledger)
        assert len(views) == 100
        assert all(v.value == {"observed_effect": "increase"} for v in views)

    def test_review_less_consequence_seed_is_verified_join_but_inert(self, consequence_ledger):
        # R-B seed shape: role='verdict' with verdict=None seeds a BARE consequence
        # execution record — a rank-1 consequence view, verified-join-eligible
        # (limb i + ii), yet carrying NEITHER review NOR observed_effect, so it has
        # NO direction reading (direction-inert). Proves the P6-inert cell is real.
        cell = Cell(assumptions=True, bindings=(
            BS(role="verdict", verdict=None, source=None, tag="ex"),))
        edge, views = L.materialize(cell, consequence_ledger)
        assert len(views) == 1
        v = views[0]
        assert v.provenance["stream_rank"] == 1              # consequence stream
        assert "review" not in v.value                       # no verdict axis
        assert "observed_effect" not in v.value              # no direction axis
        assert L.consequence_subject_key(v.value) == v.subject_key    # limb i holds
        assert L.consequence_join_key(v.value) in edge.join_spec      # limb ii holds
        assert v.subject_key in edge.admissible_subjects     # admissible
        assert not v.conflict_set                            # not contested
        assert edge.assumptions                              # assumptions present, yet P6

    def test_direction_observation_decrease_and_maintain_seed_shapes(self, consequence_ledger):
        # MF2: the observation seam carries the FULL movement enum, not just
        # 'increase' — each folds to a view whose value is exactly that effect.
        for effect in ("decrease", "maintain"):
            cell = Cell(bindings=(
                BS(role="observation", observed_effect=effect, tag=f"o-{effect}"),))
            _edge, views = L.materialize(cell, consequence_ledger)
            assert views[0].value == {"observed_effect": effect}
            assert "review" not in views[0].value

    def test_mixed_verdict_cell_seeds_two_distinct_noncolliding_views(self, consequence_ledger):
        # MF1: two verdict bindings on distinct subjects fold to TWO rank-1 views
        # that share NO conflict_set (distinct identities -> P1's first clause can
        # never fire), each carrying its own review verbatim so the state function
        # reads the two sources independently.
        cell = Cell(assumptions=True, bindings=(
            BS(role="verdict", verdict="confirmed", source="verdict_human", tag="hc"),
            BS(role="verdict", verdict="wrong", source="verdict_judge", tag="mw")))
        edge, views = L.materialize(cell, consequence_ledger)
        assert len(views) == 2
        assert len({v.subject_key for v in views}) == 2      # distinct identities
        assert all(v.provenance["stream_rank"] == 1 for v in views)
        assert all(not v.conflict_set for v in views)        # no cross-coupling
        reviews = {(v.value["review"]["verdict"], v.value["review"]["source"])
                   for v in views}
        assert reviews == {("confirmed", "verdict_human"), ("wrong", "verdict_judge")}
        assert len(edge.join_spec) == 2                      # each verdict => a matcher

    def test_anti_preponderance_seed_is_100_support_plus_one_contra(self, consequence_ledger):
        # MF4: 100 supporting + 1 contradicting observation, all on distinct
        # subjects (no conflict_set) — the single contra is really present.
        cell = Cell(expected_effect="increase", assumptions=True,
                    bindings=_VOL_SUPPORTING + (
                        BS(role="observation", observed_effect="decrease", tag="contra"),))
        _edge, views = L.materialize(cell, consequence_ledger)
        assert len(views) == 101
        effects = [v.value["observed_effect"] for v in views]
        assert effects.count("increase") == 100 and effects.count("decrease") == 1
        assert all(not v.conflict_set for v in views)        # distinct subjects

    def test_captain_vocab_table_is_bijective(self):
        # the vocabulary the DATA TABLE uses is a clean 5<->5 bijection.
        internal, captain = list(L.CAPTAIN_VOCAB), list(L.CAPTAIN_VOCAB.values())
        assert len(set(internal)) == len(set(captain)) == 5
        assert set(internal) == {
            L.STATE_UNKNOWN, L.STATE_HYPOTHESIZED, L.STATE_OBSERVATIONALLY_SUPPORTED,
            L.STATE_INTERVENTION_SUPPORTED, L.STATE_FALSIFIED}

    def test_graph_input_path_roundtrips_through_load_beliefs_verified(self, tmp_path, consequence_ledger):
        # (d) the graph-input assembly: persist a seeded store and re-read it via
        # the ONE cortex read path (load_beliefs_verified), plus assemble the
        # build-input tuple future suites hand to build_graph.
        L.seed_consequence_ledger(consequence_ledger, [
            L.consequence_row("ship", "release/g",
                              verdict="confirmed", source="verdict_human")])
        beliefs = L.fold_beliefs(L.consequence_protos())
        cache = tmp_path / "cortex"
        cache.mkdir()
        L.persist_cortex_store(cache, beliefs)
        reloaded = L.query.load_beliefs_verified(cache)      # C-F15 bound serve path
        assert {b.belief_id for b in reloaded} == {b.belief_id for b in beliefs}
        roots = L.write_roots_yml(tmp_path, [{"slug": "ship-fast",
                                              "statement": "ship reliably"}])
        gi = L.graph_inputs(roots, cache)
        assert gi.roots_path == roots and gi.cache_dir == Path(cache)
        assert gi.scope == L.SCOPE and gi.cutoff == L.CUTOFF
        assert "ship-fast" in roots.read_text(encoding="utf-8")
