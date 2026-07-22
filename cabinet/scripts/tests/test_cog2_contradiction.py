"""COG-2 UNIT 2 — contradiction + unknown gate (§8 sim 3, tests-first).

The mechanical proof that conflicting beliefs COEXIST (never LWW) and that a
zero-evidence query returns an EXPLICIT unknown (never a default/sentinel).

Honesty clause (§1 M3 / C-F10): no production event pair in this slice CAN
contradict (tasks is a single producer whose same-subject events supersede;
consequence subjects are ts-inclusive-unique; the streams share no subject
namespace). M3 is a declared FIXTURE-proof through production code — the
envelope-file adapter (§5.2a) — with two independent producers on one subject.
The first contradiction-capable production source pairing is a named obligation
of the next adapter phase.

Contradiction law (§5.5): same subject_key + dimension, INDEPENDENT lineages
(lineage = producer — "same producer = same lineage by definition here"),
neither superseding => both stored, symmetric SORTED cross-links, full conflict
set with per-side provenance + confidence.

Negative controls (MUST fail):
  * silent LWW (one merged chain per subject+dimension) — loses a side
  * lineage keyed on correlation_id — wrongly contradicts a same-producer
    disjoint-correlation pair whose PINNED verdict is "supersedes"
  * a per-event-unique dimension — never groups the pair (positive fixture)
  * a default/sentinel for a zero-evidence subject (unknown must be explicit)
  * a bare-scalar confidence accessor on query.py (the standing ratchet)
  * unknown returned for a scope-mismatch (denial masquerading as ignorance)

S0: interpreter python3.12. No DB — the envelope-file adapter reads a JSONL.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_ROOT = str(_HERE.parents[2])
for _p in (str(_HERE), _ROOT):          # tests/ is a package: put it on the path
    if _p not in sys.path:
        sys.path.insert(0, _p)

from framework.cortex import adapters, belief, engine, query  # noqa: E402
import lib_cog2_envelope as L  # noqa: E402

TT = L.TRUST_TABLE
MAIN = {"cabinet_id": "main"}
S1 = "2026-07-20T00:00:00Z"
O1 = "2026-07-20T01:00:00Z"
O2 = "2026-07-20T02:00:00Z"


def _fold_envs(tmp_path, envs, name="c.jsonl"):
    path = L.write_jsonl(tmp_path / name, envs)
    protos, receipts = adapters.read_envelope_file(path, local_cabinet_id="main")
    assert receipts == [], f"unexpected quarantine: {receipts}"
    return engine.fold(protos, trust_table=TT)


# ===========================================================================
# two producers, one subject, incompatible claims -> BOTH coexist, cross-linked
# ===========================================================================

class TestTwoProducerContradiction:
    def _conflict(self, tmp_path):
        envs = [
            L.envelope(seed=31, producer=L.PRIMARY, subject="widget-9",
                       state="hot", occurred_at=S1, recorded_at=O1),
            L.envelope(seed=32, producer=L.SECONDARY, subject="widget-9",
                       state="cold", occurred_at=S1, recorded_at=O2),
        ]
        return _fold_envs(tmp_path, envs)

    def test_both_beliefs_coexist_and_cross_link(self, tmp_path):
        beliefs = self._conflict(tmp_path)
        r = query.as_of(beliefs, "observations/widget-9", scope=MAIN)
        assert r.status == "contradicted"
        assert len(r.views) == 2                       # neither is dropped (no LWW)
        states = sorted(v.value["state"] for v in r.views)
        assert states == ["cold", "hot"]
        # symmetric cross-links: each names the other in its conflict set
        by_state = {v.value["state"]: v for v in r.views}
        assert by_state["hot"].conflict_set == (by_state["cold"].belief_id,)
        assert by_state["cold"].conflict_set == (by_state["hot"].belief_id,)
        assert all(v.status == "contradicted" for v in r.views)

    def test_per_side_provenance_and_confidence_surface(self, tmp_path):
        beliefs = self._conflict(tmp_path)
        r = query.as_of(beliefs, "observations/widget-9", scope=MAIN)
        by_producer = {v.provenance["producer"]: v for v in r.views}
        assert set(by_producer) == {L.PRIMARY, L.SECONDARY}
        # each side keeps its OWN provenance-weighted confidence (never collapsed)
        assert by_producer[L.PRIMARY].confidence == 800000
        assert by_producer[L.SECONDARY].confidence == 500000
        assert by_producer[L.PRIMARY].source_trust["producer_key"] == L.PRIMARY
        assert by_producer[L.SECONDARY].source_trust["producer_key"] == L.SECONDARY

    def test_positive_fixture_pair_shares_a_dimension(self, tmp_path):
        # the positive cross-link fixture (C-F10): the pair MUST share a
        # dimension to be groupable — a per-event-unique-dimension impl would
        # give them distinct dimensions and never contradict.
        beliefs = self._conflict(tmp_path)
        dims = {b.dimension for b in beliefs}
        assert dims == {"observations/observation"}    # one shared dimension
        r = query.as_of(beliefs, "observations/widget-9", scope=MAIN)
        assert len(r.views) == 2                        # therefore they DO cross-link

    def test_silent_lww_mutant_loses_a_side(self, tmp_path):
        # MUTANT (silent LWW): merge every belief of one subject+dimension into
        # ONE chain regardless of producer -> the last-by-source-order wins and
        # the other side vanishes. Contradiction is silently resolved.
        beliefs = self._conflict(tmp_path)
        correct = query.as_of(beliefs, "observations/widget-9", scope=MAIN)
        mutant = query.as_of(beliefs, "observations/widget-9", scope=MAIN,
                             lineage="merged")
        assert len(correct.views) == 2 and correct.status == "contradicted"
        assert len(mutant.views) == 1                   # a side was silently dropped
        assert mutant.status != "contradicted"


# ===========================================================================
# same producer, DISJOINT correlation chains -> supersedes (PINNED verdict)
# ===========================================================================

class TestSameProducerDisjointCorrelation:
    def _pair(self, tmp_path):
        # same producer, DIFFERENT correlation ids, same subject -> ONE lineage
        # (same producer = same lineage), so the later one SUPERSEDES.
        envs = [
            L.envelope(seed=41, producer=L.PRIMARY, subject="widget-5",
                       state="x", occurred_at=S1, recorded_at=O1, correlation_seed=901),
            L.envelope(seed=42, producer=L.PRIMARY, subject="widget-5",
                       state="y", occurred_at=S1, recorded_at=O2, correlation_seed=902),
        ]
        return _fold_envs(tmp_path, envs)

    def test_pinned_verdict_supersedes_not_contradicts(self, tmp_path):
        beliefs = self._pair(tmp_path)
        # disjoint correlation ids (proving the seed is what it claims)
        cids = {b.provenance["correlation_id"] for b in beliefs}
        assert len(cids) == 2
        r = query.as_of(beliefs, "observations/widget-5", scope=MAIN)
        assert r.status == "asserted" and len(r.views) == 1     # one current head
        assert r.views[0].value["state"] == "y"                 # later supersedes

    def test_correlation_keyed_lineage_mutant_wrongly_contradicts(self, tmp_path):
        # MUTANT (lineage keyed on correlation_id): the disjoint chains look like
        # independent lineages -> a spurious contradiction. The correct producer
        # keying supersedes.
        beliefs = self._pair(tmp_path)
        correct = query.as_of(beliefs, "observations/widget-5", scope=MAIN)
        mutant = query.as_of(beliefs, "observations/widget-5", scope=MAIN,
                             lineage="correlation")
        assert correct.status == "asserted" and len(correct.views) == 1
        assert mutant.status == "contradicted" and len(mutant.views) == 2  # bites


# ===========================================================================
# unknown stays unknown — EXPLICIT, never a default/sentinel
# ===========================================================================

class TestUnknownStaysUnknown:
    def test_zero_evidence_subject_is_explicit_unknown(self, tmp_path):
        beliefs = TestTwoProducerContradiction()._conflict(tmp_path)
        r = query.as_of(beliefs, "observations/does-not-exist", scope=MAIN)
        assert r.is_unknown() and r.status == "unknown"
        assert r.views == ()                           # no fabricated belief

    def test_default_for_unknown_mutant_is_not_unknown(self, tmp_path):
        # MUTANT (default-for-unknown): return a fabricated default belief for a
        # zero-evidence subject instead of an explicit unknown.
        beliefs = TestTwoProducerContradiction()._conflict(tmp_path)
        correct = query.as_of(beliefs, "observations/does-not-exist", scope=MAIN)
        mutant = query.as_of(beliefs, "observations/does-not-exist", scope=MAIN,
                             unknown_mode="default")
        assert correct.is_unknown()
        assert not mutant.is_unknown()                 # the mutant invents an answer


# ===========================================================================
# purged-only subject -> status-bearing answer, NEVER unknown (C-F11)
# ===========================================================================

def _purged_proto(subject, *, event_id, cabinet_id="main"):
    """A minimal source-purged proto (a tombstoned outbox stub — claim gone,
    identity intact). The fold marks purged=True -> status source_purged."""
    return {
        "kind": "entity", "subject_key": subject, "dimension": "status",
        "adapter_ordinal": 0, "claim": None, "purged": True,
        "source_time": S1, "observation_time": O1,
        "provenance": {"event_id": event_id, "producer": "officer_tasks/outbox-relay",
                       "stream_rank": 0, "intra_stream_seq": 1, "cabinet_id": cabinet_id},
        "claim_completeness": "purged",
    }


class TestPurgedNotUnknown:
    def test_purged_only_subject_returns_status_never_unknown(self):
        beliefs = engine.fold([_purged_proto("tasks/900", event_id="evt-900")],
                              trust_table=TT)
        r = query.as_of(beliefs, "tasks/900", scope=MAIN)
        assert not r.is_unknown()                      # purged != ignorant
        assert r.status == "source_purged"
        assert r.views[0].status == "source_purged"
        assert r.views[0].value is None                # the claim is gone, identity intact


# ===========================================================================
# scope fence — HARD ERROR, never empty-success (§7.4, denial != ignorance)
# ===========================================================================

class TestScopeMismatchDenied:
    def test_foreign_cabinet_scope_is_a_hard_error(self, tmp_path):
        beliefs = TestTwoProducerContradiction()._conflict(tmp_path)
        with pytest.raises(query.ScopeError):
            query.as_of(beliefs, "observations/widget-9",
                        scope={"cabinet_id": "some-other-cabinet"})

    def test_missing_scope_is_a_hard_error(self, tmp_path):
        beliefs = TestTwoProducerContradiction()._conflict(tmp_path)
        with pytest.raises(query.ScopeError):
            query.as_of(beliefs, "observations/widget-9", scope=None)

    def test_lenient_scope_mutant_masquerades_denial_as_ignorance(self, tmp_path):
        # MUTANT (lenient scope): return unknown for an unresolvable scope
        # instead of a hard error — denial dressed up as ignorance.
        beliefs = TestTwoProducerContradiction()._conflict(tmp_path)
        r = query.as_of(beliefs, "observations/widget-9", scope=None,
                        scope_mode="lenient")
        assert r.is_unknown()                          # the mutant's tell


# ===========================================================================
# NEVER-A-SCORE standing ratchet (G-F3): no bare-scalar confidence accessor
# ===========================================================================

_DENY_ACCESSOR_NAMES = frozenset({
    "confidence", "confidence_of", "get_confidence", "score", "as_score",
    "scalar_confidence", "confidence_scalar", "as_confidence"})


def _bare_scalar_confidence_accessors(source: str) -> list[str]:
    """Flag any function that is a bare-scalar confidence accessor: a denylisted
    name, or a function whose sole statement returns `<x>.confidence`."""
    tree = ast.parse(source)
    bad: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name in _DENY_ACCESSOR_NAMES:
            bad.append(node.name)
            continue
        body = [s for s in node.body if not isinstance(s, ast.Expr)
                or not isinstance(s.value, ast.Constant)]        # drop the docstring
        if len(body) == 1 and isinstance(body[0], ast.Return):
            val = body[0].value
            if isinstance(val, ast.Attribute) and val.attr == "confidence":
                bad.append(f"{node.name} (returns .confidence)")
    return bad


class TestNeverAScoreRatchet:
    def test_query_module_has_no_bare_scalar_confidence_accessor(self):
        src = Path(query.__file__).read_text(encoding="utf-8")
        assert _bare_scalar_confidence_accessors(src) == []

    def test_the_ratchet_itself_bites_a_synthetic_accessor(self):
        # prove the guard is not vacuous: a bare-scalar accessor is flagged.
        assert _bare_scalar_confidence_accessors(
            "def confidence(v):\n    return v.c\n") == ["confidence"]
        assert _bare_scalar_confidence_accessors(
            "def trust(v):\n    return v.confidence\n") == ["trust (returns .confidence)"]

    def test_beliefview_pairs_confidence_with_source_trust(self, tmp_path):
        # the SHAPE guard: confidence is only ever exposed bundled with
        # source_trust + provenance in the full view (never alone).
        beliefs = TestTwoProducerContradiction()._conflict(tmp_path)
        v = query.as_of(beliefs, "observations/widget-9", scope=MAIN).views[0]
        for field in ("value", "source_trust", "provenance", "status", "conflict_set"):
            assert hasattr(v, field)
        assert isinstance(v.source_trust, dict) and "producer_key" in v.source_trust


# ===========================================================================
# REVIEW FIX F2: a multi-DIMENSION subject (the outbox emits status + occurrence
# per task) queried dimension=None is ASSERTED, not contradicted — the result
# status is CONFLICT-driven, not head-COUNT-driven
# ===========================================================================

def _outbox_row(row_id, task_id, new_status, *, cabinet_id="main"):
    """A synthetic officer_tasks_outbox row (the shape read_outbox_rows returns).
    The tasks adapter expands it to TWO beliefs — entity(status) +
    observation(occurrence) — a multi-dimension subject with ONE producer."""
    return {
        "id": row_id, "idempotency_key": f"idem-{row_id:08d}",
        "event_id": f"evt-{row_id}", "task_id": task_id, "old_status": None,
        "new_status": new_status, "old_blocked": None, "new_blocked": False,
        "blocked_reason": None, "actor": "cos", "context_slug": "cog1",
        "cabinet_id": cabinet_id, "correlation_id": f"corr{row_id:032d}",
        "causation_id": None, "occurred_at": "2026-07-20T08:00:00Z",
    }


class TestMultiDimensionIsNotContradiction:
    def test_two_dimensions_one_task_dimensionless_query_is_asserted(self):
        # the tasks adapter emits status + occurrence for one task -> two
        # dimensions, one subject, one producer.
        protos = adapters.build_proto_beliefs([_outbox_row(1, 500, "wip")])
        beliefs = engine.fold(protos, trust_table=TT)
        assert sorted(b.dimension for b in beliefs) == ["occurrence", "status"]
        r = query.as_of(beliefs, "tasks/500", scope=MAIN)      # dimension=None
        assert r.status == "asserted"                          # NOT contradicted (F2)
        assert len(r.views) == 2
        assert all(v.status == "asserted" for v in r.views)
        assert all(v.conflict_set == () for v in r.views)      # no conflict => no contradiction

    def test_dimension_scoped_query_returns_that_facet_only(self):
        # the same shape, queried with an explicit dimension, returns the ONE
        # facet — asserted, single view (a facet is not a rival lineage).
        protos = adapters.build_proto_beliefs([_outbox_row(2, 501, "done")])
        beliefs = engine.fold(protos, trust_table=TT)
        r = query.as_of(beliefs, "tasks/501", scope=MAIN, dimension="status")
        assert r.status == "asserted" and len(r.views) == 1
        assert r.views[0].dimension == "status"

    def test_genuine_same_dimension_conflict_still_contradicts(self, tmp_path):
        # regression the OTHER way: a real independent-lineage conflict on ONE
        # dimension still aggregates to contradicted (the fix did not mute it).
        beliefs = TestTwoProducerContradiction()._conflict(tmp_path)
        r = query.as_of(beliefs, "observations/widget-9", scope=MAIN)
        assert r.status == "contradicted"
        assert any(v.conflict_set for v in r.views)
