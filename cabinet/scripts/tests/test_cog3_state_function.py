"""COG-3 §12.2 STEP 3 — the exhaustive mixed-evidence fixture over §5.2.

This is the step-3 deliverable of the tests-first order (contract §12.2): the
EXHAUSTIVE map of every predicate combination of the §5.2 ordered TOTAL
transition function to its pinned expected outcome, authored BEFORE the
implementation exists so the later `framework/objectives/states.py` must satisfy
these cells UNMODIFIED. The DATA TABLE (`CELLS`) below IS the deliverable; every
cell carries the §5.2 rule id it pins.

THE §5.2 ORDERED TOTAL FUNCTION (first matching rule wins; P1>P2>P3>P4>P5>P6):
  P1  any bound view has a non-empty conflict_set, OR human-confirm AND
      human-wrong coexist                          -> hypothesized  [contested]
  P2  >=1 human-wrong (P1 missed)                   -> falsified
  P3  >=1 human-confirm AND edge assumptions non-empty (P1/P2 missed)
                                                     -> intervention_supported
  P4  >=1 direction-contradicting OR machine-contested
                                                     -> hypothesized  [direction_contested]
  P5  >=1 direction-supporting                      -> observationally_supported
  P6  otherwise (authored; zero admissible bindings / only purged)
                                                     -> hypothesized
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
  * a claim carrying `observed_effect` (no verdict) reads it directly:
      supporting iff observed_effect in {expected_effect, "maintain"};
      contradicting iff observed_effect is the strict opposite.

ASSUMPTIONS GATE ONLY P3 (pinned; see the report's interpretation note): the
precise ordered function gates `assumptions non-empty` ONLY at P3
(intervention_supported). P2/P4/P5/P6 do not require assumptions. (§4.2's blanket
"required non-empty for any edge deriving above hypothesized" is read as the
schema-honesty intent; the authoritative precise rule set gates it at P3, which
is also what lets a machine/absent-source confirm land in P5 without declaring
causal assumptions.)

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

    # ---- P3's gates fail -> the confirm CANNOT reach intervention_supported -
    ("P5-human-confirm-WITHOUT-assumptions",
     Cell(assumptions=False, bindings=(
         BS(role="verdict", verdict="confirmed", source="verdict_human", tag="hc"),)),
     L.expect_state(L.STATE_OBSERVATIONALLY_SUPPORTED),
     "§5.2 P3 requires non-empty assumptions. Walk: P1 no (no conflict, no "
     "human-wrong) -> P2 no (no human-wrong) -> P3 NO (assumptions empty) -> P4 no "
     "(a confirm is not contradicting/ machine-contested) -> P5 YES (a confirmed "
     "verdict is direction-supporting). => observationally_supported, NOT P6."),

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

    # ---- P5: direction-supporting observations (no verdict) ----------------
    ("P5-direction-supporting-observation",
     Cell(expected_effect="increase", bindings=(
         BS(role="observation", observed_effect="increase", tag="ds"),)),
     L.expect_state(L.STATE_OBSERVATIONALLY_SUPPORTED),
     "§5.2 P5: a direction-supporting observation -> observationally_supported."),

    ("P5-direction-supporting-VOLUME-100-still-P5",
     Cell(expected_effect="increase", bindings=_VOL_SUPPORTING),
     L.expect_state(L.STATE_OBSERVATIONALLY_SUPPORTED),
     "§5.2 P5 cap: NO observational VOLUME promotes — 100 supporting observations "
     "stay observationally_supported (SIM-4 volume mutant)."),

    ("P5-direction-neutral-maintain-supports",
     Cell(expected_effect="increase", bindings=(
         BS(role="observation", observed_effect="maintain", tag="mt"),)),
     L.expect_state(L.STATE_OBSERVATIONALLY_SUPPORTED),
     "§5.2 direction-supporting is 'consistent-OR-NEUTRAL' — a 'maintain' reading "
     "supports (not contradicting)."),

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
