"""COG-3 §11 row 2 — SIM-2: STALE EVIDENCE + VERDICT HONESTY (tests-first).

Pins the §5.2 revocation-is-free-by-construction law and the §6.4 verdict-source
honesty rules: an edge's epistemic state is a PURE function of cutoff-fenced
evidence re-derived at every build (the C-F7 re-derivation idiom lifted one
level, §4.2/§5.4), so superseded/purged evidence simply demotes the edge with NO
stored status and NO revocation API to get wrong; and NO machine/LLM/absent-
source confirm can ever mint `intervention_supported` — human verdict is the
only promotion fuel, capped otherwise at `observationally_supported`.

WHAT SIM-2 ASSERTS (contract §11 row 2 + §6.4 test set):
  * superseded evidence  => the edge RE-DERIVES from the fenced sub-history and
                            DEMOTES (state is never sticky).                [P5→P4]
  * a bound view carrying a non-empty conflict_set => P1 hypothesized+contested.
  * a purged human verdict => `tested` REVOKED, lineage intact (the purged view
    still present, value erased), NO graph-side mutation (derive is pure). [P3→P6]
  * a verdict_judge / verdict_gate / absent-source CONFIRM => caps at
    `observationally_supported`, NEVER `intervention_supported` (attack C-B2).
  * (ruling R-A, §4.2 "assumptions REQUIRED non-empty for any edge deriving
    above hypothesized") `observationally_supported` (P5) is itself a CEILING
    that requires the edge's `assumptions` non-empty: an assumptionless confirm/
    supporting edge derives P6 `hypothesized`, so every P5-landing seed here
    declares assumptions, and an assumptionless machine-confirm is pinned at P6.
  * staleness is the §5.1(7) instrument's TWO-FENCED-QUERY diff (bound cutoff vs
    a declared `--now`), never a cached-view checker.
  * serve REFUSES states re-derived against a refolded store (mixed-epoch, §5.4).

NEGATIVE-CONTROL MUTANTS these cells fail (contract §11 row 2):
  builder/server reading a STORED status (test_superseded / test_purged demote —
  a stored status would stay); cached-view staleness checker (the two-fenced
  diff self-check + CLI); sticky-`tested` (test_purged revokes); 'promotes-on-
  judge-verdict' — the C-B2 escape (the three machine/absent cap cells return P5,
  so a promoting impl returns P3 and REDs); serve-time re-derivation against a
  refolded store (the mixed-epoch REFUSE cell).

FAILURE SIGNATURE (tests-first — `framework/objectives/` does NOT exist):
  * every contract cell imports `framework.objectives.*` FIRST in its body, so
    today it fails with `ModuleNotFoundError: No module named
    'framework.objectives'` — the honest absence-of-implementation signature.
  * the staleness cell BUILDS the graph first (the instrument reads the built
    manifest for its bound-subject/bound-cutoff source), so today it too fails at
    the absent `framework.objectives` module; the absent CLI
    (`cabinet/scripts/cog3-staleness.py`) is documented separately by the
    `test_staleness_cli_is_absent_today` self-check (contract §12.2: a clearly-
    absent CLI is an accepted tests-first signature).
  * the `TestSim2SeedsAreReal` self-checks carry NO objectives import and PASS
    today — they prove every seed is real substrate output (a bad fixture would
    otherwise fail for the WRONG reason once the implementation lands).

PINNED API (the surface `framework/objectives/` must provide — flagged for the
T4 implementer; narrowest plausible):
  states.derive_edge_state(edge, bound_views, cutoff) -> EdgeState(state, flags)
        (reused from the T3 step-3 pin — THE ordered-total transition function).
  graph.build_graph(roots_path, objectives_cache_dir, scope, cutoff)
        -> writes objectives_cache_dir/{graph.jsonl,graph-manifest.json}; pure,
        reads the SIBLING cortex store (cache_dir/../cortex) per §5.1 (A-M6:
        every input declared — the cortex-store LOCATION is the one build input
        T4 confirms; the CLI cog3-rebuild.py owns the production default).
  query.serve_graph(objectives_cache_dir) -> served graph; REFUSES (raises
        query.ServeRefused, the C-F15 StoreCorruptError-shape clone, §5.4) when
        the manifest's cortex_belief_store_hash != the live store hash
        (mixed-epoch) — pinned here; the counterfactual-manifest REFUSE is in SIM-3.
  cabinet/scripts/cog3-staleness.py --now <canonical-ts> --cache <objectives
        cache dir> : prints JSON to stdout with a per-bound-subject two-fenced
        diff; a subject whose fenced head moved between the bound cutoff and
        --now is reported stale (§5.1(7)). Exact extra flags are implementer-
        defined; the CONTRACT pinned is the moved-subject-is-flagged behavior.

S0: interpreter python3.12. No DSN, no postgres — jsonl belief protos +
consequence ledger day files (§7.2), the D1 idiom from test_cog2_asof_fence.py.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; Fable-5 two-tier law (test-authoring).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_ROOT = str(_HERE.parents[2])
for _p in (str(_HERE), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_cog3_fixtures as L  # noqa: E402  (NEVER framework.objectives here)

_STALENESS_CLI = Path(_ROOT) / "cabinet" / "scripts" / "cog3-staleness.py"

# Two-cutoff fence points for the supersession + staleness scenarios: an early
# supporting head (obs_time EARLY) is superseded by a later contradicting head
# (obs_time LATE) on the SAME subject; a build fenced BEFORE_LATE sees the
# supporting head, a build fenced AFTER_LATE sees the contradicting head.
_TS_EARLY = "2026-07-10T00:00:00Z"
_TS_LATE = "2026-07-18T00:00:00Z"
_CUT_BEFORE_LATE = "2026-07-15T00:00:00Z"     # supporting head is the head here
_CUT_AFTER_LATE = "2026-07-21T00:00:00Z"      # contradicting head is the head here


@pytest.fixture
def consequence_ledger(tmp_path, monkeypatch):
    """An isolated consequence-ledger dir wired through CABINET_EVENT_LOG_DIR
    (the operator-set env `consequence.py` reads), sim mode OFF — the D1 idiom
    from `test_cog2_asof_fence.py`. Verdict bindings file-seed here."""
    d = tmp_path / "events"
    d.mkdir()
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(d))
    monkeypatch.delenv("CABINET_SIM_MODE", raising=False)
    return d


# ---------------------------------------------------------------------------
# Import indirection (the honest absence signature lives in the test bodies).
# ---------------------------------------------------------------------------

def _import_states():
    from framework.objectives import states  # noqa: F401
    return states


def _import_graph():
    from framework.objectives import graph  # noqa: F401
    return graph


def _import_query():
    from framework.objectives import query  # noqa: F401
    return query


# ---------------------------------------------------------------------------
# Local seed helpers (built ONLY from lib_cog3_fixtures primitives — the library
# is never edited; contract §7.2 + the brief's "missing API => local helper").
# ---------------------------------------------------------------------------

def _superseded_direction_store():
    """Two observations on ONE subject/dimension: an EARLY supporting head
    (increase, the edge's expected_effect) superseded by a LATE contradicting
    head (decrease). Returns (beliefs, subject_key). The fold's temporal
    re-derivation makes as_of pick the head as-of the cutoff — the §5.2/C-F7
    'fenced sub-history' the edge state re-derives against at each build."""
    sk = "observation/superseded"
    p0 = L.observation_proto(sk, L.DIMENSION, claim=L.observed_effect_claim("increase"),
                             seq=0, ts=_TS_EARLY, event_suffix="s0")
    p1 = L.observation_proto(sk, L.DIMENSION, claim=L.observed_effect_claim("decrease"),
                             seq=1, ts=_TS_LATE, event_suffix="s1")
    return L.fold_beliefs([p0, p1]), sk


def _direction_edge_bound_at(beliefs, sk, cutoff):
    """Build the SAME structural edge (expected_effect=increase) bound to
    whatever head resolves at `cutoff`, plus the served views at that cutoff.
    The structural fields are cutoff-INVARIANT; only the bound views (and their
    belief_id refs) change — the exact 'same edge, re-derived from the fenced
    sub-history' shape (§4.2 epistemic-state-is-derived-never-stored).

    `assumptions` is NON-EMPTY (ruling R-A, §4.2 'REQUIRED non-empty for any edge
    deriving above hypothesized'): observationally_supported (P5) is itself ABOVE
    hypothesized, so the early-cutoff supporting head lands at P5 only WITH
    declared assumptions — an assumptionless edge would derive P6 and this cell's
    P5→P4 demotion narrative would not hold against a correct implementation."""
    views = tuple(L.views_for(beliefs, sk, cutoff=cutoff))
    edge = L.EdgeSpec(
        authored=True, expected_effect="increase",
        assumptions=("declared-confounder-and-selection",),   # R-A: P5 needs assumptions
        admissible_subjects=frozenset({sk}),
        join_spec=(),                              # observation edge — no verdict join
        evidence_bindings=tuple(L.BindingRef(v.subject_key, v.belief_id) for v in views),
    )
    return edge, views


def _confirm_edge_two_conditions(log_dir):
    """Seed ONE human-confirm verdict; return the identical edge plus TWO served
    view-sets: `live` (the confirm view) and `purged` (the SAME belief with its
    claim cortex-purged). The edge's structural fields are built from the row's
    stable identity, so the two derivations differ ONLY in the served evidence's
    completeness — the 'purge => tested revoked, lineage intact, no graph-side
    mutation' shape (§6.4 test set). belief_id is stable across purge (verified in
    the self-check), so the edge's binding resolves to BOTH view-sets."""
    row = L.consequence_row("ship", "release/purgeverdict",
                            verdict="confirmed", source="verdict_human")
    L.seed_consequence_ledger(log_dir, [row])
    protos = L.consequence_protos()
    sk = L.consequence_subject_key(row)

    def _views(purged):
        clones = [dict(p) for p in protos]
        if purged:
            for p in clones:
                p["purged"] = True                 # cortex source-purge (top-level key)
        return tuple(L.views_for(L.fold_beliefs(clones), sk))

    live, purged = _views(False), _views(True)
    edge = L.EdgeSpec(
        authored=True, expected_effect="increase",
        assumptions=("declared-confounder-and-selection",),   # P3's third gate
        admissible_subjects=frozenset({sk}),
        join_spec=(L.consequence_join_key(row),),             # verified-join limb (ii)
        evidence_bindings=tuple(L.BindingRef(v.subject_key, v.belief_id) for v in live),
    )
    return edge, live, purged


def _persist_two_cutoff_cortex(cache_root):
    """Persist the supersession store under cache_root/cortex (the sibling the
    build reads, §5.1) and return (cortex_dir, objectives_dir, subject_key)."""
    beliefs, sk = _superseded_direction_store()
    cortex = cache_root / "cortex"
    cortex.mkdir(parents=True)
    L.persist_cortex_store(cortex, beliefs)
    objectives = cache_root / "objectives"
    objectives.mkdir(parents=True)
    return cortex, objectives, sk


# ===========================================================================
# CONTRACT CELLS — import framework.objectives FIRST => absence signature today.
# ===========================================================================

def test_superseded_evidence_redemotes_on_rebuild():
    # §5.2 revocation-by-construction / §4.2 state-derived-never-stored: the SAME
    # edge re-derived against the fenced sub-history DEMOTES when the supporting
    # head is superseded by a contradicting one — a stored/sticky status mutant
    # would keep observationally_supported at the later cutoff.
    states = _import_states()
    beliefs, sk = _superseded_direction_store()

    edge_early, views_early = _direction_edge_bound_at(beliefs, sk, _CUT_BEFORE_LATE)
    early = states.derive_edge_state(edge_early, views_early, _CUT_BEFORE_LATE)
    assert early.state == L.STATE_OBSERVATIONALLY_SUPPORTED  # §5.2 P5: supporting head

    edge_late, views_late = _direction_edge_bound_at(beliefs, sk, _CUT_AFTER_LATE)
    late = states.derive_edge_state(edge_late, views_late, _CUT_AFTER_LATE)
    # §5.2 P4: the superseding head contradicts => hypothesized+direction_contested
    # (the edge DEMOTED purely from the fenced sub-history — no revocation API).
    assert late.state == L.STATE_HYPOTHESIZED
    assert frozenset(late.flags) == frozenset({L.FLAG_DIRECTION_CONTESTED})


def test_contested_conflict_set_derives_hypothesized_contested(consequence_ledger):
    # §5.2 P1: a bound view carrying a non-empty conflict_set (query.py:269-286)
    # => hypothesized+contested — certainty is never manufactured over
    # contradicted ground, in either direction (SIM-2).
    states = _import_states()
    cell = L.EdgeCell(bindings=(L.BindingSpec(role="observation", contested=True, tag="ct"),))
    edge, views = L.materialize(cell, consequence_ledger)
    result = states.derive_edge_state(edge, views, L.CUTOFF)
    assert result.state == L.STATE_HYPOTHESIZED
    assert frozenset(result.flags) == frozenset({L.FLAG_CONTESTED})


def test_purged_human_verdict_revokes_tested_lineage_intact(consequence_ledger):
    # §6.4 test set + §5.2 admissible(): a human-confirm promotes to
    # intervention_supported; PURGING the verdict (cortex source-purge) makes the
    # view inert while KEEPING it in lineage, so the SAME edge re-derives to
    # hypothesized (P6) — 'tested' REVOKED, no graph-side mutation. Bites the
    # sticky-`tested` mutant and the stored-status mutant.
    states = _import_states()
    edge, live, purged = _confirm_edge_two_conditions(consequence_ledger)

    before = states.derive_edge_state(edge, live, L.CUTOFF)
    assert before.state == L.STATE_INTERVENTION_SUPPORTED   # §5.2 P3: the triple

    after = states.derive_edge_state(edge, purged, L.CUTOFF)
    assert after.state == L.STATE_HYPOTHESIZED              # §5.2 P6: support revoked
    assert after.flags == frozenset()
    # lineage intact: the purged view is STILL present (value erased, not dropped).
    assert len(purged) == len(live) == 1
    assert purged[0].value is None
    assert purged[0].claim_completeness == L.belief.COMPLETENESS_PURGED


@pytest.mark.parametrize("source", ["verdict_judge", "verdict_gate", "system", None],
                         ids=["verdict_judge", "verdict_gate", "system", "absent_source"])
def test_machine_or_absent_confirm_caps_at_observationally_supported(consequence_ledger, source):
    # §5.2 P5 cap / §6.4 (attack C-B2): a CONFIRMED verdict from a non-human
    # source (LLM judge, machine gate, system, or absent) is promotion-INERT — it
    # is direction-supporting, so it caps at observationally_supported and can
    # NEVER reach intervention_supported. This is the 'promotes-on-judge-verdict'
    # mutant catcher: a promoting impl returns P3 here and REDs.
    states = _import_states()
    cell = L.EdgeCell(assumptions=True, bindings=(
        L.BindingSpec(role="verdict", verdict="confirmed", source=source, tag="m"),))
    edge, views = L.materialize(cell, consequence_ledger)
    result = states.derive_edge_state(edge, views, L.CUTOFF)
    assert result.state == L.STATE_OBSERVATIONALLY_SUPPORTED, \
        f"§5.2 P5: a {source!r}-source confirm must cap, never mint tested"
    assert result.state != L.STATE_INTERVENTION_SUPPORTED    # the C-B2 escape


def test_assumptionless_machine_confirm_derives_p6_not_the_p5_ceiling(consequence_ledger):
    # Ruling R-A (§4.2 "assumptions REQUIRED non-empty for any edge deriving above
    # hypothesized" + §11 SIM-4 "assumption-free promotion above hypothesized"
    # mutant): `observationally_supported` (P5) is a CEILING, not a guaranteed
    # landing. A machine confirm (direction-supporting, never promotion fuel) with
    # EMPTY assumptions cannot reach P5 either — it derives P6 `hypothesized`. Pairs
    # with the cap cell above (assumptions=True => P5): assumptions gate the
    # ceiling. Robust to the direction-reading subtlety: whether or not a bare
    # confirm is read as direction-supporting, an assumptionless edge lands at P6.
    states = _import_states()
    cell = L.EdgeCell(assumptions=False, bindings=(
        L.BindingSpec(role="verdict", verdict="confirmed", source="verdict_judge",
                      tag="am"),))
    edge, views = L.materialize(cell, consequence_ledger)
    result = states.derive_edge_state(edge, views, L.CUTOFF)
    assert result.state == L.STATE_HYPOTHESIZED, \
        "R-A: an assumptionless machine confirm cannot reach the P5 ceiling => P6"
    assert result.state != L.STATE_OBSERVATIONALLY_SUPPORTED
    assert result.flags == frozenset()          # P6 carries no flag (not P1/P4)


def test_staleness_instrument_reports_a_moved_subject(tmp_path):
    # §5.1(7) + §11 row 2 ("staleness ... flagged in the manifest"): the staleness
    # instrument diffs TWO fenced as_of answers — each BOUND subject's bound cutoff
    # vs a declared --now — and reports a subject whose fenced head MOVED. It is a
    # separate CLI (never inside build_graph, never a cached view).
    #
    # It reads the BUILT graph-manifest for its (bound subject, bound cutoff)
    # source, so the graph MUST be built FIRST — a bare empty objectives cache
    # gives a correct instrument no bound subject to diff (it would error on the
    # missing manifest or report nothing; the pre-fix cell asserted staleness over
    # an unbuilt cache and could never pass a correct implementation). We build at
    # the EARLY cutoff (the subject's head is the supporting obs there), then run
    # staleness at a LATER --now (the superseding head is the head there) => the
    # bound subject moved => stale.
    #
    # [ADAPTER-DEPENDENT, flagged like the divergence cell: the build binds the
    #  superseded subject through the roots/adapter surface; if the final adapter
    #  schema differs, T4 aligns the SEED — the FIRM contract is that a moved BOUND
    #  subject is reported under `stale` AND named in the manifest staleness-flags
    #  surface.]
    #
    # TODAY: build_graph's module is ABSENT => _import_graph() raises
    # ModuleNotFoundError = the tests-first absence signature (the staleness CLI is
    # also absent — pinned by test_staleness_cli_is_absent_today below).
    graph = _import_graph()
    cortex, objectives, sk = _persist_two_cutoff_cortex(tmp_path / "cache")
    roots = L.write_roots_yml(tmp_path, [{"slug": "ship-fast",
                                          "statement": "ship reliably"}])
    graph.build_graph(roots, objectives, L.SCOPE, _CUT_BEFORE_LATE)   # binds sk at the early head

    proc = subprocess.run(
        [sys.executable, str(_STALENESS_CLI),
         "--now", _CUT_AFTER_LATE, "--cache", str(objectives)],
        capture_output=True, text=True)
    assert proc.returncode == 0, (
        f"§5.1(7) staleness instrument absent/failed (rc={proc.returncode}): "
        f"{proc.stderr.strip()[:200]}")
    report = json.loads(proc.stdout)

    # (b) the two-fenced diff OUTPUT names the moved bound subject.
    stale_subjects = {e.get("subject_key") for e in report.get("stale", [])}
    assert sk in stale_subjects, "§5.1(7): the moved bound subject must be flagged stale"

    # (c) §11 row 2 "flagged in the manifest": the staleness run records the flags
    # surface the contract names (§5.1(7) "the manifest staleness flags"). NARROWEST
    # PIN: a `staleness_flags` / `stale_subjects` entry naming the moved subject —
    # homed here in the instrument report (its output IS what feeds the manifest
    # flags; T4 may additionally mirror it into graph-manifest.json). Tolerant of a
    # [subject_key, …] or [{"subject_key": …}, …] shape.
    raw = report.get("staleness_flags")
    if raw is None:
        raw = report.get("stale_subjects")
    raw = raw or []
    flagged = {e for e in raw if isinstance(e, str)}
    flagged |= {e.get("subject_key") for e in raw if isinstance(e, dict)}
    assert sk in flagged, (
        "§11 row 2 / §5.1(7): the moved subject must appear in the manifest "
        "staleness-flags surface (`staleness_flags`/`stale_subjects`)")


def test_serve_refuses_states_derived_against_a_refolded_store(tmp_path):
    # §5.4 (attack A-M4): compile-time derivation is the ONLY production path; the
    # serve surface REFUSES when the manifest's cortex_belief_store_hash != the
    # live store hash (a refolded / mixed-epoch store). Mixed-epoch answers are
    # the dishonesty §5.5 forbids — serve must fail-closed, never re-derive.
    graph = _import_graph()
    query = _import_query()
    cortex, objectives, _sk = _persist_two_cutoff_cortex(tmp_path / "cache")

    roots = L.write_roots_yml(tmp_path, [{"slug": "ship-fast", "statement": "ship reliably"}])
    graph.build_graph(roots, objectives, L.SCOPE, L.CUTOFF)     # binds the store hash

    # Refold the SAME cortex path with an extra belief => the live store hash no
    # longer matches the manifest's recorded cortex_belief_store_hash.
    beliefs, sk = _superseded_direction_store()
    extra = L.observation_proto("observation/extra", L.DIMENSION,
                                claim=L.observed_effect_claim("increase"),
                                seq=0, event_suffix="epoch-drift")
    L.persist_cortex_store(cortex, L.fold_beliefs(
        [L.observation_proto(sk, L.DIMENSION, claim=L.observed_effect_claim("increase"),
                             seq=0, ts=_TS_EARLY, event_suffix="s0"),
         L.observation_proto(sk, L.DIMENSION, claim=L.observed_effect_claim("decrease"),
                             seq=1, ts=_TS_LATE, event_suffix="s1"),
         extra]))
    with pytest.raises(query.ServeRefused):
        query.serve_graph(objectives)               # C-F15 second binding, §5.4


# ===========================================================================
# SEED SELF-CHECKS — no framework.objectives import; PASS TODAY. They prove the
# SIM-2 seeds are real substrate output (so each contract cell is meaningful the
# moment the implementation lands).
# ===========================================================================

class TestSim2SeedsAreReal:
    def test_supersession_head_moves_between_the_two_cutoffs(self):
        # the demotion seed: the SAME subject's fenced head is direction-
        # supporting before the late obs and direction-contradicting after —
        # a real cutoff-driven supersession (§5.2/C-F7), not a hand-built diff.
        beliefs, sk = _superseded_direction_store()
        early = L.views_for(beliefs, sk, cutoff=_CUT_BEFORE_LATE)
        late = L.views_for(beliefs, sk, cutoff=_CUT_AFTER_LATE)
        assert [v.value for v in early] == [{"observed_effect": "increase"}]
        assert [v.value for v in late] == [{"observed_effect": "decrease"}]

    def test_purge_seed_erases_the_claim_but_keeps_the_belief(self, consequence_ledger):
        # the revocation seed: the confirm view carries a verdict_human confirm
        # LIVE, and the SAME belief_id survives the purge with an erased claim
        # (lineage intact) — so the edge binding resolves to both conditions.
        edge, live, purged = _confirm_edge_two_conditions(consequence_ledger)
        assert live[0].value["review"] == {"verdict": "confirmed", "source": "verdict_human"}
        assert purged[0].value is None
        assert purged[0].claim_completeness == L.belief.COMPLETENESS_PURGED
        assert live[0].belief_id == purged[0].belief_id           # stable across purge
        assert live[0].provenance["stream_rank"] == 1             # consequence stream
        # the edge's structural spec is purge-invariant (no graph-side mutation).
        assert edge.assumptions and edge.join_spec and edge.admissible_subjects

    def test_contested_seed_is_a_real_conflict_set(self, consequence_ledger):
        cell = L.EdgeCell(bindings=(L.BindingSpec(role="observation", contested=True, tag="ct"),))
        _edge, views = L.materialize(cell, consequence_ledger)
        assert len(views) == 2 and all(v.conflict_set for v in views)  # P1 seam real

    @pytest.mark.parametrize("source", ["verdict_judge", "verdict_gate", "system", None])
    def test_machine_confirm_seed_is_confirmed_but_not_human(self, consequence_ledger, source):
        cell = L.EdgeCell(assumptions=True, bindings=(
            L.BindingSpec(role="verdict", verdict="confirmed", source=source, tag="m"),))
        _edge, views = L.materialize(cell, consequence_ledger)
        assert views[0].value["review"]["verdict"] == "confirmed"      # a real confirm
        assert views[0].value["review"].get("source") != "verdict_human"  # yet not human

    def test_persisted_two_cutoff_store_roundtrips_through_the_one_read_path(self, tmp_path):
        # the mixed-epoch seed: the store persists + reloads via load_beliefs_
        # verified (the ONE cortex read path, §5.1) with the C-F15 hash binding —
        # so a later refold's hash change is a real epoch drift the serve REFUSEs.
        cortex, objectives, sk = _persist_two_cutoff_cortex(tmp_path / "cache")
        reloaded = L.query.load_beliefs_verified(cortex)
        assert any(sk == v for v in {b.subject_key for b in reloaded})
        assert (cortex / "beliefs.jsonl").exists()
        assert (cortex / "fold-manifest.json").exists()
        assert objectives.is_dir()

    def test_staleness_cli_is_absent_today(self):
        # documents the tests-first signature for the CLI cell above: the
        # instrument does not exist yet, so its cell fails on an absent CLI.
        assert not _STALENESS_CLI.exists()
