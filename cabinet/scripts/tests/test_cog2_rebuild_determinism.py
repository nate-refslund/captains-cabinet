"""COG-2 UNIT 1 — deterministic-rebuild gate (§8 sim 1, tests-first).

Plan: docs/plans/cognitive-core-phase-2-contract-2026-07-22.md §8 sim 1. The
mechanical proof that the Cortex projection is a rebuildable, determinism-exact
function of source truth. Two tiers, exactly the cog1-replay-hash precedent:

  * PURE gates (no DB) — the fold + adapter proto-builder are pure (the adapter
    reuses relay.build_dispatch_fields, itself pure), so determinism, the
    frontier law, source-order supersession, the canonical dialect parity
    (G-F5), and every sim-1 mutant are provable with zero DB.
  * PG-backed gate (skips without a PostgreSQL 17 toolchain + psycopg2) — the
    literal exit instrument: THREE rebuilds run as THREE subprocesses under
    THREE distinct PYTHONHASHSEED values print an IDENTICAL belief-store hash
    (C-F3); a physical heap shuffle leaves the hash identical (C-F4); the
    frontier never advances past a NULL, and a late backfill is folded, never
    skipped (C-F1).

The three prompt-pinned negative-control mutants MUST fail: (a) a builder keyed
on ARRIVAL order; (b) a builder minting FRESH ids per build; (c) the
FRONTIER-PAST-NULL builder. Each rides a documented non-default seam.

S0: harness/CI pin PostgreSQL MAJOR 17. Interpreter python3.12.
"""
from __future__ import annotations

import copy
import importlib.util as _ilu
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_ROOT = str(_HERE.parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from framework.cortex import adapters, belief, engine  # noqa: E402
from framework.evidence import recorder  # noqa: E402


def _load(path: str, name: str):
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


# hyphenated scripts (importlib, the falsifier-test idiom)
c2bh = _load(str(_HERE.parent / "cog2-belief-hash.py"), "cog2_belief_hash")
_REBUILD = _HERE.parent / "cog2-rebuild.py"

# the relay harness re-exports EphemeralPG17 + seed_transition + pg_available
HR = _load(_ROOT + "/framework/outbox/tests/lib_relay_harness.py",
           "lib_relay_harness_cog2")
_PG_SKIP = pytest.mark.skipif(not HR.pg_available(), reason=HR.PG_SKIP_REASON)
_FORBIDDEN = set(HR.H.FORBIDDEN_CHILD_ENV)

# The UNIT-1 trust table (mirrors cabinet/config/cortex-source-trust.v1.yml).
TT = {"table_version": 1, "producers": {"officer_tasks/outbox-relay": 900000}}


# ---------------------------------------------------------------------------
# synthetic outbox rows (the shape read_outbox_rows returns)
# ---------------------------------------------------------------------------

def _orow(row_id, task_id, new_status, *, event_id, old_status=None,
          old_blocked=None, new_blocked=False, occurred_at=None,
          actor="cos", cabinet_id="cog1-harness"):
    return {
        "id": row_id,
        "event_id": event_id,
        "task_id": task_id,
        "old_status": old_status,
        "new_status": new_status,
        "old_blocked": old_blocked,
        "new_blocked": new_blocked,
        "blocked_reason": None,
        "actor": actor,
        "context_slug": "cog1",
        "cabinet_id": cabinet_id,
        "correlation_id": f"corr{row_id:032d}",
        "causation_id": None,
        "occurred_at": occurred_at or f"2026-07-20T08:00:{row_id % 60:02d}Z",
    }


def _sample_rows():
    """task 100: wip -> block -> unblock -> done; task 101: queue -> cancel."""
    return [
        _orow(1, 100, "wip", event_id="evt-1", old_status=None),
        _orow(2, 100, "wip", event_id="evt-2", old_status="wip",
              old_blocked=False, new_blocked=True),                # block
        _orow(3, 100, "wip", event_id="evt-3", old_status="wip",
              old_blocked=True, new_blocked=False),                # unblock
        _orow(4, 100, "done", event_id="evt-4", old_status="wip"),
        _orow(5, 101, "queue", event_id="evt-5", old_status=None),
        _orow(6, 101, "cancelled", event_id="evt-6", old_status="queue"),
    ]


def _fold_rows(rows, **kw):
    return engine.fold(adapters.build_proto_beliefs(rows), trust_table=TT, **kw)


def _hash_rows(rows, **kw):
    return belief.chained_hash(_fold_rows(rows, **kw))


# ===========================================================================
# canonical dialect parity (G-F5 — the standing recorder tripwire)
# ===========================================================================

class TestCanonicalDialectParity:
    def test_cortex_bytes_equal_recorder_bytes(self):
        for val in ({"b": 2, "a": [3, 1], "c": "æ"},
                    {"x": None, "y": [{"k": 1}, {"j": 2}]},
                    [1, "two", {"three": 3}]):
            assert belief.canonical_bytes(val) == recorder._canonical(val)

    def test_cortex_digest_equals_recorder_digest(self):
        val = {"kind": "entity", "subject_key": "tasks/1"}
        assert belief.digest(val) == recorder._digest(val)

    def test_canonical_bytes_are_sorted_compact_utf8(self):
        b = belief.canonical_bytes({"b": 1, "a": "æ"})
        assert b == '{"a":"æ","b":1}'.encode("utf-8")


# ===========================================================================
# identity (§4 — deterministic, claim-independent, never a build-time ULID)
# ===========================================================================

class TestBeliefIdentity:
    def test_belief_id_deterministic(self):
        a = belief.compute_belief_id("entity", "tasks/1", "status", "evt-9", 0)
        b = belief.compute_belief_id("entity", "tasks/1", "status", "evt-9", 0)
        assert a == b and len(a) == 64

    def test_belief_id_independent_of_claim(self):
        # identity survives a content purge because it never embeds claim bytes.
        rows = _sample_rows()
        beliefs = _fold_rows(rows)
        ids = {b.belief_id for b in beliefs}
        purged = copy.deepcopy(rows)
        purged[0]["new_status"] = "cancelled"      # change the claim of row 1
        beliefs2 = _fold_rows(purged)
        # the entity/observation ids for the OTHER rows are unchanged
        row1_events = {"evt-1"}
        stable_before = {b.belief_id for b in beliefs
                         if b.provenance["event_id"] not in row1_events}
        stable_after = {b.belief_id for b in beliefs2
                        if b.provenance["event_id"] not in row1_events}
        assert stable_before == stable_after
        assert ids  # sanity

    def test_adapter_ordinal_distinguishes_entity_and_observation(self):
        beliefs = _fold_rows([_sample_rows()[0]])
        ords = sorted(b.adapter_ordinal for b in beliefs)
        dims = sorted(b.dimension for b in beliefs)
        assert ords == [0, 1] and dims == ["occurrence", "status"]


# ===========================================================================
# frontier law (§5.3)
# ===========================================================================

class TestFrontierLaw:
    def test_no_null_frontier_is_max(self):
        assert engine.frontier_of(_sample_rows()) == 6

    def test_mid_null_frontier_stops_before_null(self):
        rows = [_orow(1, 100, "wip", event_id="evt-1"),
                _orow(2, 100, "wip", event_id=None, old_status="wip", new_blocked=True),
                _orow(3, 100, "done", event_id="evt-3", old_status="wip")]
        assert engine.frontier_of(rows) == 1              # min(null)-1
        assert engine.frontier_of(rows, past_null=True) == 3  # MUTANT: max(id)

    def test_eligible_excludes_behind_and_at_null(self):
        rows = [_orow(1, 100, "wip", event_id="evt-1"),
                _orow(2, 100, "wip", event_id=None, old_status="wip", new_blocked=True),
                _orow(3, 100, "done", event_id="evt-3", old_status="wip")]
        elig = engine.eligible_rows(rows)
        assert [r["id"] for r in elig] == [1]


# ===========================================================================
# pure fold determinism, shuffle + duplication invariance
# ===========================================================================

class TestPureFoldDeterminism:
    def test_double_fold_identical(self):
        rows = _sample_rows()
        assert _hash_rows(rows) == _hash_rows(copy.deepcopy(rows))

    def test_shuffle_invariant(self):
        rows = _sample_rows()
        shuffled = [rows[4], rows[0], rows[3], rows[5], rows[1], rows[2]]
        assert _hash_rows(rows) == _hash_rows(shuffled)

    def test_duplication_invariant(self):
        rows = _sample_rows()
        duped = rows + [copy.deepcopy(rows[1]), copy.deepcopy(rows[3])]
        assert _hash_rows(rows) == _hash_rows(duped)

    def test_shuffle_and_duplication_invariant(self):
        rows = _sample_rows()
        mixed = [rows[3], rows[0], copy.deepcopy(rows[3]), rows[5],
                 rows[1], rows[2], rows[4], copy.deepcopy(rows[0])]
        assert _hash_rows(rows) == _hash_rows(mixed)

    def test_content_change_changes_hash(self):
        rows = _sample_rows()
        base = _hash_rows(rows)
        changed = copy.deepcopy(rows)
        changed[3]["new_status"] = "cancelled"
        assert _hash_rows(changed) != base

    def test_hash_is_hex_sha256(self):
        h = _hash_rows(_sample_rows())
        assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)


# ===========================================================================
# supersession authority = source order, NOT observation_time (A-B4)
# ===========================================================================

def _head(beliefs, subject, dimension):
    heads = [b for b in beliefs if b.subject_key == subject
             and b.dimension == dimension and b.superseded_by is None]
    assert len(heads) == 1, f"expected one head, got {len(heads)}"
    return heads[0]


class TestSupersessionSourceOrder:
    def _long_tx_rows(self):
        # a late-id row with an EARLY occurred_at (a long transaction): source
        # order (id) makes it current; observation_time order would not.
        rows = _sample_rows()
        rows.append(_orow(7, 100, "queue", event_id="evt-7", old_status="done",
                          occurred_at="2026-07-20T07:00:00Z"))
        return rows

    def test_current_status_follows_id_not_occurred_at(self):
        beliefs = _fold_rows(self._long_tx_rows())
        head = _head(beliefs, "tasks/100", "status")
        assert head.provenance["intra_stream_seq"] == 7      # the late id wins
        assert head.claim["status"] == "queue"

    def test_observation_time_ordering_would_pick_the_wrong_head(self):
        # the MUTANT axis (observation_time) would crown id 4 (latest clock).
        rows = self._long_tx_rows()
        correct = _head(_fold_rows(rows), "tasks/100", "status")
        mutant = _head(_fold_rows(rows, supersession_order="observation_time"),
                       "tasks/100", "status")
        assert correct.provenance["intra_stream_seq"] == 7
        assert mutant.provenance["intra_stream_seq"] == 4
        assert correct.belief_id != mutant.belief_id

    def test_supersession_chain_is_linear_and_preserved(self):
        beliefs = {b.belief_id: b for b in _fold_rows(_sample_rows())}
        status_100 = [b for b in beliefs.values()
                      if b.subject_key == "tasks/100" and b.dimension == "status"]
        superseded = [b for b in status_100 if b.status == "superseded"]
        asserted = [b for b in status_100 if b.status == "asserted"]
        assert len(status_100) == 4 and len(asserted) == 1 and len(superseded) == 3
        # every non-head points forward; no history is erased (all 4 present)
        for b in superseded:
            assert b.superseded_by in beliefs


# ===========================================================================
# the three pinned negative-control mutants MUST fail
# ===========================================================================

class TestSim1Mutants:
    def test_mutant_arrival_order_is_not_shuffle_invariant(self):
        """(a) a builder keyed on ARRIVAL order — a shuffle changes the hash."""
        rows = _sample_rows() + [
            _orow(7, 100, "queue", event_id="evt-7", old_status="done",
                  occurred_at="2026-07-20T07:00:00Z")]
        shuffled = list(reversed(rows))
        # correct (source order): shuffle-invariant
        assert _hash_rows(rows) == _hash_rows(shuffled)
        # MUTANT (arrival order): the same set in a different arrival order hashes
        # differently -> the negative control bites.
        m1 = _hash_rows(rows, supersession_order="arrival")
        m2 = _hash_rows(shuffled, supersession_order="arrival")
        assert m1 != m2

    def test_mutant_fresh_ulid_is_nondeterministic(self):
        """(b) a builder minting FRESH ids per build — two builds differ."""
        rows = _sample_rows()
        # correct: deterministic across builds
        assert _hash_rows(rows) == _hash_rows(rows)
        # MUTANT: fresh id per build -> two builds of the SAME state differ.
        assert _hash_rows(rows, identity="fresh_ulid") != _hash_rows(rows, identity="fresh_ulid")

    def test_mutant_frontier_past_null_folds_stranded_rows(self):
        """(c) the FRONTIER-PAST-NULL builder — folds rows behind a NULL gap."""
        rows = [_orow(1, 100, "wip", event_id="evt-1"),
                _orow(2, 100, "wip", event_id=None, old_status="wip", new_blocked=True),
                _orow(3, 100, "done", event_id="evt-3", old_status="wip")]
        correct = _fold_rows(rows)
        mutant = engine.fold(adapters.build_proto_beliefs(rows, past_null=True),
                             trust_table=TT)
        # correct folds ONLY row 1 (2 beliefs); mutant reaches the stranded row 3.
        assert len(correct) == 2 and len(mutant) == 4
        assert belief.chained_hash(correct) != belief.chained_hash(mutant)
        # no correct belief references the stranded event
        assert all(b.provenance["event_id"] != "evt-3" for b in correct)
        assert any(b.provenance["event_id"] == "evt-3" for b in mutant)


# ===========================================================================
# schema registration + never-a-score producer latch (G-F4)
# ===========================================================================

class TestSchemaAndConfidence:
    def test_folded_beliefs_validate_against_registered_schema(self):
        for b in _fold_rows(_sample_rows()):
            assert belief.validate_belief(b) == ()

    def test_confidence_is_ppm_paired_with_source_trust(self):
        b = _fold_rows(_sample_rows())[0]
        assert b.confidence == 900000
        assert b.source_trust == {"table_version": 1,
                                  "producer_key": "officer_tasks/outbox-relay"}

    def test_absent_producer_yields_absent_confidence_never_zero(self):
        conf, st = engine.derive_confidence("unknown/producer", TT)
        assert conf is None and st["producer_key"] == "unknown/producer"

    def test_officer_producer_key_is_structurally_invalid(self):
        from framework.triggers import schema_registry
        good = schema_registry.validate_payload(
            {"table_version": 1, "producer_key": "officer_tasks/outbox-relay"},
            "cortex/source-trust@1")
        bad = schema_registry.validate_payload(
            {"table_version": 1, "producer_key": "cos"}, "cortex/source-trust@1")
        assert good == () and bad != ()


# ===========================================================================
# rows-not-bytes: write -> re-derive equals the fold-time hash (A-m11)
# ===========================================================================

class TestWriteAndRehash:
    def test_reread_hash_matches_manifest(self, tmp_path):
        beliefs = _fold_rows(_sample_rows())
        manifest = engine.build_manifest(beliefs, trust_table=TT, frontier=6, max_id=6)
        engine.write_projection(beliefs, manifest, tmp_path)
        rehash, count = c2bh.hash_jsonl(tmp_path / "beliefs.jsonl")
        assert rehash == manifest["belief_store_hash"] == belief.chained_hash(beliefs)
        assert count == len(beliefs)

    def test_byte_flip_is_detected(self, tmp_path):
        beliefs = _fold_rows(_sample_rows())
        manifest = engine.build_manifest(beliefs, trust_table=TT, frontier=6, max_id=6)
        engine.write_projection(beliefs, manifest, tmp_path)
        jsonl = tmp_path / "beliefs.jsonl"
        text = jsonl.read_text().replace("tasks/100", "tasks/999", 1)
        jsonl.write_text(text)
        rehash, _ = c2bh.hash_jsonl(jsonl)
        assert rehash != manifest["belief_store_hash"]


# ===========================================================================
# read-SELECT contract (§8 sim 1): ORDER BY id string-pin (C-F4) + the
# idempotency_key column fetched into provenance (F1)
# ===========================================================================

class TestReadSelectContract:
    def test_select_sql_pins_order_by_id(self):
        # contract §8 sim 1: the outbox read SELECT is string-pinned to carry
        # ORDER BY id — the C-F4 physical-shuffle determinism pin. Dropping it
        # reads in heap/physical order and loses shuffle-invariance.
        assert "ORDER BY id" in adapters._SELECT_SQL
        assert adapters._SELECT_SQL.rstrip().endswith("ORDER BY id")

    def test_select_sql_fetches_idempotency_key(self):
        # F1: the SELECT must fetch idempotency_key (047: NOT NULL UNIQUE) or it
        # never reaches build_dispatch_fields and provenance.idempotency_key is
        # silently NULL on every belief.
        assert "idempotency_key" in adapters._SELECT_SQL

    def test_idempotency_key_flows_into_provenance(self):
        # F1 end-to-end (proto level): a row's idempotency_key appears verbatim
        # in every proto's provenance (both the entity and observation belief).
        row = _orow(1, 100, "wip", event_id="evt-1")
        row["idempotency_key"] = "idem-000001"
        protos = adapters._row_to_protos(row)
        assert protos and all(
            p["provenance"]["idempotency_key"] == "idem-000001" for p in protos)


# ===========================================================================
# fold dedupe is content-checked, not first-arrival-wins (F3)
# ===========================================================================

def _proto(claim, *, event_id="evt-1", ordinal=0,
           producer="officer_tasks/outbox-relay", **over):
    """A minimal proto-belief with a fixed identity tuple (kind, subject_key,
    dimension, event_id, adapter_ordinal) — two calls collide by belief_id."""
    p = {
        "kind": "entity",
        "subject_key": "tasks/100",
        "dimension": "status",
        "adapter_ordinal": ordinal,
        "claim": claim,
        "source_time": "2026-07-20T08:00:00Z",
        "observation_time": "2026-07-20T08:00:00Z",
        "provenance": {"event_id": event_id, "producer": producer,
                       "stream_rank": 0, "intra_stream_seq": 1},
        "claim_completeness": "inline",
    }
    p.update(over)
    return p


class TestFoldDedupeFailLoud:
    def test_exact_duplicate_protos_collapse(self):
        # identical content under one identity tuple -> one belief, no raise
        # (the physical-duplication invariance the fold relies on).
        beliefs = engine.fold([_proto({"status": "wip"}), _proto({"status": "wip"})],
                              trust_table=TT)
        assert len(beliefs) == 1

    def test_divergent_content_identity_collision_raises(self):
        # same identity tuple, DIVERGENT claim -> fail loud, never keep-first.
        with pytest.raises(ValueError, match="divergent-content identity"):
            engine.fold([_proto({"status": "wip"}), _proto({"status": "done"})],
                        trust_table=TT)

    def test_divergent_collision_is_order_independent(self):
        # both arrival orders raise — the fold is deterministic, not order-keyed.
        with pytest.raises(ValueError):
            engine.fold([_proto({"status": "done"}), _proto({"status": "wip"})],
                        trust_table=TT)


# ===========================================================================
# confidence: malformed ppm for a PRESENT producer fails loud (F4)
# ===========================================================================

class TestConfidenceFailLoud:
    def test_malformed_ppm_for_present_producer_raises(self):
        # a producer IN the table with a non-int / bool / <= 0 ppm is a trust
        # table bug — fail loud, never silently degrade to unknown.
        for bad in (0.9, "900000", 0, -5, True, None):
            tt = {"table_version": 1, "producers": {"officer_tasks/outbox-relay": bad}}
            with pytest.raises(ValueError):
                engine.derive_confidence("officer_tasks/outbox-relay", tt)

    def test_absent_producer_still_returns_none(self):
        # the absent-producer path is unchanged: unknown, never a raise (F4).
        conf, st = engine.derive_confidence("not/in/table", TT)
        assert conf is None
        assert st == {"table_version": 1, "producer_key": "not/in/table"}


# ===========================================================================
# PG-backed exit instrument (skips without a PG17 toolchain + psycopg2)
# ===========================================================================

def _sub_rebuild(dsn, hashseed, *, extra=()):
    env = {k: v for k, v in os.environ.items() if k not in _FORBIDDEN}
    env.pop("COG2_OUTBOX_DSN", None)
    env["PYTHONHASHSEED"] = str(hashseed)
    r = subprocess.run(
        ["python3.12", str(_REBUILD), "--dsn", dsn, *extra],
        capture_output=True, text=True, env=env)
    assert r.returncode == 0, f"rc={r.returncode}\n{r.stderr}"
    return json.loads(r.stdout)


def _seed_full_history(pg):
    a = HR.seed_transition(pg, "start", "cos")            # INSERT (wip)
    HR.seed_transition(pg, "block", "cos", task_id=a)     # blocked transition (047 trigger)
    HR.seed_transition(pg, "unblock", "cos", task_id=a)
    HR.seed_transition(pg, "done", "cos", task_id=a)
    b = HR.seed_transition(pg, "queue", "cpo")            # INSERT (queue)
    HR.seed_transition(pg, "cancel", "cpo", task_id=b)
    return a, b


def _reset(pg):
    pg.psql("TRUNCATE officer_tasks_outbox RESTART IDENTITY;")


def _backfill(pg, *, skip_id=None):
    where = "event_id IS NULL"
    if skip_id is not None:
        where += f" AND id <> {int(skip_id)}"
    pg.psql(f"UPDATE officer_tasks_outbox "
            f"SET event_id = 'evt-' || lpad(id::text, 8, '0') WHERE {where};")


@_PG_SKIP
class TestRebuildDeterminismOverPostgres:
    @pytest.fixture(scope="class")
    def cluster(self, tmp_path_factory):
        c = HR.EphemeralPG17(tmp_path_factory.mktemp("cog2rebuild"),
                             cabinet_id=HR.CAB_ID)
        try:
            c.start()
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"could not start ephemeral PG17: {e}")
        try:
            c.apply_base_chain()
            c.apply_identity_guc(HR.CAB_ID)
            c.apply_047()
            yield c
        finally:
            c.stop()

    def test_three_subprocesses_distinct_hashseeds_identical(self, cluster):
        _reset(cluster)
        _seed_full_history(cluster)
        _backfill(cluster)
        dsn = cluster.conninfo()
        h0 = _sub_rebuild(dsn, 0)
        h1 = _sub_rebuild(dsn, 1)
        h2 = _sub_rebuild(dsn, 2)
        assert h0["hash"] == h1["hash"] == h2["hash"]
        assert len(h0["hash"]) == 64 and h0["beliefs"] == 12
        assert h0["frontier"] == 6

    def test_physical_heap_shuffle_invariant(self, cluster):
        _reset(cluster)
        _seed_full_history(cluster)
        _backfill(cluster)
        dsn = cluster.conninfo()
        before = _sub_rebuild(dsn, 0)["hash"]
        # scattered in-place UPDATEs to dispatch bookkeeping churn the heap
        # (new MVCC tuple versions) WITHOUT touching immutable content.
        cluster.psql("UPDATE officer_tasks_outbox SET claimed_at = NOW(), "
                     "attempts = attempts + 1;")
        cluster.psql("UPDATE officer_tasks_outbox SET dispatched_at = NOW() "
                     "WHERE id % 2 = 0;")
        cluster.psql("UPDATE officer_tasks_outbox SET attempts = attempts + 5 "
                     "WHERE id % 3 = 0;")
        assert _sub_rebuild(dsn, 7)["hash"] == before

    def test_belief_hash_instrument_matches_manifest(self, cluster, tmp_path):
        _reset(cluster)
        _seed_full_history(cluster)
        _backfill(cluster)
        cache = tmp_path / "cortexcache"
        manifest = _sub_rebuild(cluster.conninfo(), 0,
                                extra=("--cache-dir", str(cache), "--json"))
        out = subprocess.run(
            ["python3.12", str(_HERE.parent / "cog2-belief-hash.py"),
             str(cache / "beliefs.jsonl")], capture_output=True, text=True)
        assert out.returncode == 0, out.stderr
        assert out.stdout.strip() == manifest["belief_store_hash"]

    def test_frontier_past_null_end_to_end(self, cluster):
        _reset(cluster)
        _seed_full_history(cluster)              # outbox ids 1..6
        _backfill(cluster, skip_id=3)            # leave id 3 NULL (mid-sequence)
        dsn = cluster.conninfo()
        correct = _sub_rebuild(dsn, 0)
        mutant = _sub_rebuild(dsn, 0, extra=("--past-null",))
        assert correct["frontier"] == 2 and mutant["frontier"] == 6
        assert correct["beliefs"] < mutant["beliefs"]
        assert correct["hash"] != mutant["hash"]

    def test_backfill_then_refold_folds_the_late_row(self, cluster):
        _reset(cluster)
        _seed_full_history(cluster)
        _backfill(cluster, skip_id=3)            # id 3 stranded behind the frontier
        dsn = cluster.conninfo()
        before = _sub_rebuild(dsn, 0)
        assert before["frontier"] == 2 and before["beliefs"] == 4
        # the relay finally backfills id 3 -> the frontier advances and the
        # previously stranded rows are folded (a late backfill is never skipped).
        _backfill(cluster)
        after = _sub_rebuild(dsn, 0)
        assert after["frontier"] == 6 and after["beliefs"] == 12
        assert after["hash"] != before["hash"]


# ===========================================================================
# F4 (unit-3 review backlog): the CONSEQUENCE stream folds deterministically
# under the C-F3 hash-seed subprocess harness too — §8 sim 1's "consequence
# JSONL" seed, ALONGSIDE the outbox triple above. The consequence adapter has
# its own determinism-sensitive machinery (proto dedupe + supersession-chain
# building + the contradiction post-pass, all set/dict-backed), so a hash-seed
# leak there would be invisible to the outbox-only triple. Unlike that triple
# this needs NO DB (the ledger is local JSONL, the consequence-seam idiom), so
# it runs in the repo gate UNCONDITIONALLY — no PG17 toolchain required.
# ===========================================================================

# A pure fold-and-hash of the consequence stream, run as a subprocess so the
# PYTHONHASHSEED varies per child (the C-F3 harness). Mirrors cog2-rebuild's
# read -> fold -> chained_hash over consequence.iter_ledger_rows() instead of
# the outbox: cog2-rebuild.py is the OUTBOX entry (--dsn); the consequence
# stream is a separate legacy adapter with no DB, so the determinism proof
# drives the fold path directly. argv: repo_root, trust_table_path; the ledger
# dir rides CABINET_EVENT_LOG_DIR (the env consequence.py resolves).
_CONSEQUENCE_FOLD_PROG = r"""
import json, os, sys
sys.path.insert(0, sys.argv[1])
import yaml
from framework.cortex import adapters, belief, engine
from framework.fidelity import consequence
tt = yaml.safe_load(open(sys.argv[2], encoding="utf-8")) or {}
tt.setdefault("producers", {})
protos = adapters.build_consequence_protos(list(consequence.iter_ledger_rows()))
beliefs = engine.fold(protos, trust_table=tt)
print(json.dumps({"hash": belief.chained_hash(beliefs), "beliefs": len(beliefs)},
                 sort_keys=True))
"""

# the SHIPPED trust table (cabinet/config/cortex-source-trust.v1.yml) — a
# production-faithful fold input carrying the consequence producer's ppm.
_TRUST_TABLE_FILE = _HERE.parents[1] / "config" / "cortex-source-trust.v1.yml"


def _sub_consequence_fold(event_log_dir, hashseed):
    """Fold+hash the consequence ledger at `event_log_dir` in a child process
    under an explicit PYTHONHASHSEED (DB/redis env stripped, exactly as the
    outbox subprocess above does)."""
    env = {k: v for k, v in os.environ.items() if k not in _FORBIDDEN}
    env["PYTHONHASHSEED"] = str(hashseed)
    env["CABINET_EVENT_LOG_DIR"] = str(event_log_dir)
    env.pop("CABINET_SIM_MODE", None)          # env-free fold; explicit anyway
    r = subprocess.run(
        ["python3.12", "-c", _CONSEQUENCE_FOLD_PROG, _ROOT, str(_TRUST_TABLE_FILE)],
        capture_output=True, text=True, env=env)
    assert r.returncode == 0, f"rc={r.returncode}\n{r.stderr}"
    return json.loads(r.stdout)


def _crow(ts, action, subject, **extra):
    """A schema-valid consequence event (mirrors the consequence-seam _row
    pattern, test_cog2_consequence_seam.py)."""
    row = {"ts": ts, "actor": {"kind": "officer", "id": "cos"}, "lane": "acting",
           "action": action, "subject": subject, "refs": []}
    row.update(extra)
    return row


def _cwrite_day(ledger_dir, date, rows):
    """Append rows to consequence-events-<date>.jsonl (the consequence-seam
    _write_day pattern)."""
    path = Path(ledger_dir) / f"consequence-events-{date}.jsonl"
    with open(path, "a") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    return path


class TestConsequenceRebuildDeterminism:
    """§8 sim 1 for the consequence stream — pure, no DB, runs everywhere."""

    def _seed(self, ledger_dir):
        # a fixture that exercises the determinism-sensitive machinery: an
        # enrichment supersession (task/1 asserted-head over a superseded
        # original), a plain subject (task/2) PLUS its byte-identical
        # double-emit dup (proto dedupe, F1), a second-day file (task/3), and a
        # sim row (dropped unconditionally by the env-free fold).
        a = _crow("2026-07-20T08:00:00Z", "task_status_move", "task/1")
        a2 = _crow("2026-07-20T08:00:00Z", "task_status_move", "task/1",
                   outcome={"status": "ok", "evidence": "done"})   # enrichment
        b = _crow("2026-07-20T09:00:00Z", "label", "task/2")
        sim = _crow("2026-07-20T09:30:00Z", "label", "task/SIM")
        sim["sim"] = True
        _cwrite_day(ledger_dir, "2026-07-20", [a, a2, b, dict(b), sim])
        c = _crow("2026-07-21T08:00:00Z", "tier2_note", "task/3")
        _cwrite_day(ledger_dir, "2026-07-21", [c])

    def test_three_subprocesses_distinct_hashseeds_identical(self, tmp_path):
        ledger = tmp_path / "events"
        ledger.mkdir()
        self._seed(ledger)
        h0 = _sub_consequence_fold(ledger, 0)
        h1 = _sub_consequence_fold(ledger, 1)
        h2 = _sub_consequence_fold(ledger, 2)
        # C-F3 for the consequence stream: three distinct hash seeds, one hash.
        assert h0["hash"] == h1["hash"] == h2["hash"]
        assert len(h0["hash"]) == 64
        # task/1 (asserted head + superseded original) + task/2 + task/3 = 4:
        # the byte-identical task/2 dup collapses, the sim row is dropped.
        assert h0["beliefs"] == 4

    def test_empty_ledger_is_deterministic_too(self, tmp_path):
        # the degenerate frame (zero consequence files) still folds to a stable
        # hash across hash seeds — the empty chained_hash is a fixed constant,
        # never hash-seed sensitive.
        ledger = tmp_path / "events"
        ledger.mkdir()
        h0 = _sub_consequence_fold(ledger, 0)
        h1 = _sub_consequence_fold(ledger, 5)
        assert h0["hash"] == h1["hash"] and len(h0["hash"]) == 64
        assert h0["beliefs"] == 0
