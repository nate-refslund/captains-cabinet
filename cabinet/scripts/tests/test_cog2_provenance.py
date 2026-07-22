"""COG-2 UNIT 3 — provenance + purge gate (§8 sim 4, tests-first).

The mechanical proof that (a) EVERY belief carries the universal provenance
minimum and resolves to >=1 event_id, and (b) a SOURCE-side tombstone purge
(§5.4b) flips a belief to source_purged with its LINEAGE INTACT, and that this
survives projection delete + rebuild-from-zero (the purge->delete->rebuild pin,
A-B3/C-F12) — possible ONLY because belief_id never embeds claim bytes.

Purge model, pinned (§5.4b): purge = SOURCE-side tombstone ONLY. For the outbox,
the payload is NULL'd while id + event_id + occurred_at (+ task_id, correlation_id,
cabinet_id, idempotency_key) survive; every refold — including rebuild-from-zero
after deletion — deterministically regenerates the belief as a source_purged
stub (claim absent, identity intact). A consequence day-file DELETION is a GAP,
not a purge (sim 5, later unit); the consequence domain has no purge mechanism
this phase, so sim-4's purge arm runs on the OUTBOX stream only.

Negative-control mutants (MUST fail):
  * a builder DROPPING provenance on any path -> fail loud (never a silent belief)
  * an empty provenance ACCEPTED by validation (universal minimum breached)
  * a CLAIM-DERIVED belief_id -> diverges post-purge, breaking the lineage the
    rebuild depends on (A-B3: identity must survive content loss)

S0: interpreter python3.12. Pure (no DB): the purge arm rides synthetic outbox
rows through the SAME adapter + fold + write/rehash path as production.
"""
from __future__ import annotations

import copy
import sys
from dataclasses import replace
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_ROOT = str(_HERE.parents[2])
for _p in (str(_HERE), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from framework.cortex import adapters, belief, engine  # noqa: E402

# The UNIT-1 tasks trust table (mirrors cabinet/config/cortex-source-trust.v1.yml).
TT = {"table_version": 1, "producers": {"officer_tasks/outbox-relay": 900000}}


def _outbox_row(row_id, task_id, new_status, *, event_id, old_status=None,
                new_blocked=False, occurred_at=None, cabinet_id="main"):
    """A synthetic officer_tasks_outbox row (the shape read_outbox_rows returns).
    A tombstone is this row with new_status set to None (payload NULL'd, §5.4b)."""
    return {
        "id": row_id, "idempotency_key": f"idem-{row_id:08d}",
        "event_id": event_id, "task_id": task_id, "old_status": old_status,
        "new_status": new_status, "old_blocked": None, "new_blocked": new_blocked,
        "blocked_reason": None, "actor": "cos", "context_slug": "cog1",
        "cabinet_id": cabinet_id, "correlation_id": f"corr{row_id:032d}",
        "causation_id": None,
        "occurred_at": occurred_at or f"2026-07-20T08:00:{row_id % 60:02d}Z",
    }


def _task_history():
    """task 100: wip -> done (two status transitions, one lineage)."""
    return [
        _outbox_row(1, 100, "wip", event_id="evt-1"),
        _outbox_row(2, 100, "done", event_id="evt-2", old_status="wip"),
    ]


def _head(beliefs, subject, dimension):
    heads = [b for b in beliefs if b.subject_key == subject
             and b.dimension == dimension and b.superseded_by is None]
    assert len(heads) == 1, f"expected one head, got {len(heads)}"
    return heads[0]


def _fold(rows):
    return engine.fold(adapters.build_proto_beliefs(rows), trust_table=TT)


# ===========================================================================
# universal provenance minimum: every belief resolves to >=1 event_id (M4)
# ===========================================================================

class TestUniversalProvenanceMinimum:
    def test_every_belief_carries_the_minimum_and_validates(self):
        beliefs = _fold(_task_history())
        assert beliefs
        for b in beliefs:
            assert b.provenance.get("event_id")        # >=1 event_id
            assert b.provenance.get("producer")
            assert "stream_rank" in b.provenance
            assert belief.validate_belief(b) == ()     # cortex/belief@1 minimum

    def test_empty_provenance_is_a_validation_error(self):
        # a belief with empty provenance FAILS cortex/belief@1 — the universal
        # minimum (event_id + producer + stream_rank) is required on EVERY belief.
        good = _fold(_task_history())[0]
        broken = replace(good, provenance={})
        assert belief.validate_belief(broken) != ()

    def test_provenance_dropping_builder_fails_loud(self):
        # MUTANT: a proto with NO provenance must NOT silently fold into a
        # valid-looking belief — the fold reads provenance to mint identity and
        # confidence, so a dropped provenance fails loud (never a silent belief).
        proto = {"kind": "entity", "subject_key": "tasks/1", "dimension": "status",
                 "adapter_ordinal": 0, "claim": {"status": "wip"},
                 "source_time": "2026-07-20T08:00:00Z",
                 "observation_time": "2026-07-20T08:00:00Z",
                 "claim_completeness": "inline"}       # provenance ABSENT
        with pytest.raises((KeyError, ValueError, TypeError)):
            engine.fold([proto], trust_table=TT)


# ===========================================================================
# source-side tombstone purge (§5.4b): status flips, lineage + provenance intact
# ===========================================================================

class TestPurgeTombstone:
    def _purged_rows(self):
        # purge the LATEST status row (id 2): payload NULL'd, identity survives.
        rows = copy.deepcopy(_task_history())
        rows[1]["new_status"] = None                   # the source-side tombstone
        return rows

    def test_tasks_adapter_reads_the_tombstone_and_marks_it_purged(self):
        # the adapter (source-side reader) recognizes a payload-NULL'd row and
        # emits a purged proto — claim absent, identity + provenance intact.
        protos = adapters.build_proto_beliefs(self._purged_rows())
        tomb = [p for p in protos if p["provenance"]["event_id"] == "evt-2"]
        assert tomb and all(p.get("purged") for p in tomb)
        for p in tomb:
            assert p["claim"] is None
            assert p["claim_completeness"] == "purged"
            # provenance SURVIVES the purge (the universal minimum is preserved).
            assert p["provenance"]["event_id"] == "evt-2"
            assert p["provenance"]["producer"] == "officer_tasks/outbox-relay"
        # the un-purged predecessor is a normal inline proto.
        live = [p for p in protos if p["provenance"]["event_id"] == "evt-1"]
        assert live and all(not p.get("purged") for p in live)

    def test_purge_flips_status_lineage_intact(self):
        live = _fold(_task_history())
        purged = _fold(self._purged_rows())
        # identity SURVIVES content loss: the belief_id set is UNCHANGED.
        assert {b.belief_id for b in live} == {b.belief_id for b in purged}
        head = _head(purged, "tasks/100", "status")
        assert head.provenance["event_id"] == "evt-2"
        assert head.status == "source_purged"          # status flipped
        assert head.claim is None and head.claim_digest is None
        assert head.supersedes != ()                   # LINEAGE INTACT (no erase)
        # the predecessor is still present, superseded, its claim untouched.
        pred = next(b for b in purged if b.provenance["event_id"] == "evt-1"
                    and b.dimension == "status")
        assert pred.status == "superseded" and pred.claim is not None
        assert head.supersedes == (pred.belief_id,)
        # the purged head still validates (provenance minimum preserved).
        assert belief.validate_belief(head) == ()

    def test_purge_survives_projection_delete_and_rebuild_from_zero(self, tmp_path):
        rows = self._purged_rows()
        frontier = engine.frontier_of(rows)
        max_id = max(int(r["id"]) for r in rows)
        beliefs1 = _fold(rows)
        manifest1 = engine.build_manifest(beliefs1, trust_table=TT,
                                          frontier=frontier, max_id=max_id)
        engine.write_projection(beliefs1, manifest1, tmp_path)
        # DELETE the projection entirely (a lost cache).
        (tmp_path / "beliefs.jsonl").unlink()
        assert not (tmp_path / "beliefs.jsonl").exists()
        # REBUILD FROM ZERO: refold from the SAME source rows.
        beliefs2 = _fold(rows)
        manifest2 = engine.build_manifest(beliefs2, trust_table=TT,
                                          frontier=frontier, max_id=max_id)
        # EXACT reproduction — identical belief set AND identical hash (C-F12).
        assert belief.chained_hash(beliefs1) == belief.chained_hash(beliefs2)
        assert manifest1["belief_store_hash"] == manifest2["belief_store_hash"]
        # the purged stub is reproduced identically after rebuild-from-zero.
        head2 = _head(beliefs2, "tasks/100", "status")
        assert head2.status == "source_purged" and head2.claim is None
        assert head2.belief_id == _head(beliefs1, "tasks/100", "status").belief_id

    def test_non_purged_history_is_unaffected(self):
        # regression guard: a normal (non-tombstone) row never marks purged.
        beliefs = _fold(_task_history())
        assert all(b.status != "source_purged" for b in beliefs)
        assert all(b.claim is not None for b in beliefs)


# ===========================================================================
# MUTANT: a claim-derived belief_id breaks the lineage across a purge (A-B3)
# ===========================================================================

class TestClaimDerivedIdentityMutant:
    def test_real_identity_is_claim_independent_stable_across_purge(self):
        # the REAL identity tuple (kind, subject_key, dimension, event_id,
        # adapter_ordinal) excludes claim bytes -> stable across a content purge.
        live = belief.compute_belief_id("entity", "tasks/100", "status", "evt-2", 0)
        tomb = belief.compute_belief_id("entity", "tasks/100", "status", "evt-2", 0)
        assert live == tomb

    def test_mutant_claim_bytes_in_identity_diverges_post_purge(self):
        # MUTANT: an identity that FOLDS claim bytes in diverges once the claim
        # is purged -> the superseded_by pointer (which names the pre-purge id)
        # dangles and rebuild-from-zero cannot reproduce the stub. This is why
        # belief_id must never embed the claim (A-B3/C-F12).
        def _claim_id(status_value):
            return belief.digest({
                "kind": "entity", "subject_key": "tasks/100", "dimension": "status",
                "event_id": "evt-2", "adapter_ordinal": 0,
                "claim": {"status": status_value}})
        live_id = _claim_id("done")
        purged_id = _claim_id(None)                    # claim gone after purge
        assert live_id != purged_id                    # the mutant breaks the chain

    def test_purge_is_hash_stable_because_identity_excludes_claim(self):
        # end-to-end: fold live vs fold purged share the SAME belief_id set, so a
        # rebuild that folds either reproduces the pinned identities (the chain
        # never dangles). Only the claim/status/hash of the purged stub differ.
        rows_live = _task_history()
        rows_purged = copy.deepcopy(rows_live)
        rows_purged[1]["new_status"] = None
        ids_live = {b.belief_id for b in _fold(rows_live)}
        ids_purged = {b.belief_id for b in _fold(rows_purged)}
        assert ids_live == ids_purged                  # identity survives purge
        # the STORE hash legitimately differs (claim content changed) — a
        # within-unit content change, not a determinism regression.
        assert belief.chained_hash(_fold(rows_live)) != belief.chained_hash(_fold(rows_purged))


def test_row_missing_new_status_key_is_not_a_tombstone():
    """F2 (review): a row MISSING the new_status key must NOT read as purged —
    get() would coerce absence to None (a silent fabricated purge). Only an
    explicit present-null new_status is a source-side tombstone."""
    row = _outbox_row(1, "task-1", "done", event_id="evt-1")
    del row["new_status"]
    assert adapters._is_tombstone(row) is False
    assert adapters._is_tombstone(_outbox_row(2, "t2", None, event_id="evt-2")) is True
