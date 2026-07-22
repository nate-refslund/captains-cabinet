"""COG-2 UNIT 4 — corruption + gap gate (§8 sim 5, tests-first).

Plan: docs/plans/cognitive-core-phase-2-contract-2026-07-22.md §6 (serve-time
store-hash binding C-F15), §5.3 / §7.3 (frontier + retention → gap taxonomy),
§8 sim 5. The mechanical proof that a corrupt canonical store is NEVER served
from an intact index, and that a hole in the outbox id sequence is DETECTED and
classified (never bridged with fabricated beliefs).

Two proofs, both pure (no DB) plus a PG-backed realism arm:

  * SERVE-TIME HASH BINDING (C-F15): re-derive the chained hash from the
    re-parsed beliefs.jsonl ROWS (never file bytes — A-m11), compare to the
    fold-manifest belief_store_hash; a byte-flip / truncation / partial write
    ⇒ StoreCorruptError (REFUSE), no window where the corrupt store is served.
    Rebuild-from-zero over the (unchanged) source restores the pre-corruption
    hash.
  * GAP TAXONOMY (§8 sim 5, seen-set regression): the fold manifest records the
    outbox seen-set as intervals; a later fold's seen-set is regressed against
    the prior manifest. (a) a rollback-burned BIGSERIAL id = a benign hole;
    (b) a deleted row BELOW the frontier = a breach; (c) a genesis shift =
    a breach. Zero fabricated bridging beliefs.

The prompt-pinned negative-control mutants MUST fail: a SELF-HEALING store that
re-serves corrupted rows (verify=False); a gap SILENTLY BRIDGED; a HOLE-AS-BREACH
classifier (fails seed a); a FORWARD-WINDOW checker blind to below-frontier
deletion (fails seed b). Each rides a documented non-default seam.

S0: harness/CI pin PostgreSQL MAJOR 17. Interpreter python3.12.
"""
from __future__ import annotations

import copy
import importlib.util as _ilu
import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_ROOT = str(_HERE.parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from framework.cortex import adapters, belief, engine  # noqa: E402
from framework.cortex import query as cortex_query  # noqa: E402


def _load(path: str, name: str):
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


# hyphenated scripts (importlib, the falsifier-test idiom)
c2v = _load(str(_HERE.parent / "cog2-verifier.py"), "cog2_verifier")
c2bh = _load(str(_HERE.parent / "cog2-belief-hash.py"), "cog2_belief_hash")

# the relay harness re-exports EphemeralPG17 + seed_transition + pg_available
HR = _load(_ROOT + "/framework/outbox/tests/lib_relay_harness.py",
           "lib_relay_harness_cog2_corruption")
_PG_SKIP = pytest.mark.skipif(not HR.pg_available(), reason=HR.PG_SKIP_REASON)

# The UNIT-1 trust table (mirrors cabinet/config/cortex-source-trust.v1.yml).
TT = {"table_version": 1, "producers": {"officer_tasks/outbox-relay": 900000}}


def _orow(row_id, task_id, new_status, *, event_id, old_status=None,
          old_blocked=None, new_blocked=False, occurred_at=None,
          actor="cos", cabinet_id="cog1-harness"):
    return {
        "id": row_id, "event_id": event_id, "task_id": task_id,
        "old_status": old_status, "new_status": new_status,
        "old_blocked": old_blocked, "new_blocked": new_blocked,
        "blocked_reason": None, "actor": actor, "context_slug": "cog1",
        "cabinet_id": cabinet_id, "correlation_id": f"corr{row_id:032d}",
        "causation_id": None,
        "occurred_at": occurred_at or f"2026-07-20T08:00:{row_id % 60:02d}Z",
    }


def _sample_rows():
    """task 100: wip -> block -> unblock -> done; task 101: queue -> cancel."""
    return [
        _orow(1, 100, "wip", event_id="evt-1", old_status=None),
        _orow(2, 100, "wip", event_id="evt-2", old_status="wip",
              old_blocked=False, new_blocked=True),
        _orow(3, 100, "wip", event_id="evt-3", old_status="wip",
              old_blocked=True, new_blocked=False),
        _orow(4, 100, "done", event_id="evt-4", old_status="wip"),
        _orow(5, 101, "queue", event_id="evt-5", old_status=None),
        _orow(6, 101, "cancelled", event_id="evt-6", old_status="queue"),
    ]


def _fold(rows):
    return engine.fold(adapters.build_proto_beliefs(rows), trust_table=TT)


def _write(rows, cache_dir):
    beliefs = _fold(rows)
    ids = [int(r["id"]) for r in rows]
    manifest = engine.build_manifest(beliefs, trust_table=TT,
                                     frontier=max(ids), max_id=max(ids))
    engine.write_projection(beliefs, manifest, cache_dir)
    return manifest


# ===========================================================================
# serve-time store-hash binding (C-F15)
# ===========================================================================

class TestServeTimeHashBinding:
    def test_intact_store_verifies_and_serves(self, tmp_path):
        manifest = _write(_sample_rows(), tmp_path)
        verified = cortex_query.verify_store(tmp_path)
        assert verified == manifest["belief_store_hash"]
        beliefs = cortex_query.load_beliefs_verified(tmp_path)
        assert len(beliefs) == 12

    def test_byte_flip_refuses_to_serve(self, tmp_path):
        _write(_sample_rows(), tmp_path)
        jsonl = tmp_path / "beliefs.jsonl"
        # a content byte-flip that keeps the line valid JSON (the hardest case:
        # an intact index would happily serve it) — the re-derived hash diverges.
        jsonl.write_text(jsonl.read_text().replace("tasks/100", "tasks/999", 1))
        with pytest.raises(cortex_query.StoreCorruptError, match="hash mismatch"):
            cortex_query.verify_store(tmp_path)
        with pytest.raises(cortex_query.StoreCorruptError):
            cortex_query.load_beliefs_verified(tmp_path)

    def test_truncated_store_refuses_to_serve(self, tmp_path):
        _write(_sample_rows(), tmp_path)
        jsonl = tmp_path / "beliefs.jsonl"
        lines = jsonl.read_text().splitlines()
        jsonl.write_text("\n".join(lines[:-1]) + "\n")   # drop the last belief
        with pytest.raises(cortex_query.StoreCorruptError):
            cortex_query.verify_store(tmp_path)

    def test_malformed_json_line_refuses_to_serve(self, tmp_path):
        _write(_sample_rows(), tmp_path)
        jsonl = tmp_path / "beliefs.jsonl"
        jsonl.write_text(jsonl.read_text() + '{"belief_id": "x", not-json\n')
        with pytest.raises(cortex_query.StoreCorruptError):
            cortex_query.verify_store(tmp_path)

    def test_missing_manifest_hash_refuses(self, tmp_path):
        _write(_sample_rows(), tmp_path)
        mpath = tmp_path / "fold-manifest.json"
        m = json.loads(mpath.read_text())
        del m["belief_store_hash"]
        mpath.write_text(json.dumps(m))
        with pytest.raises(cortex_query.StoreCorruptError):
            cortex_query.verify_store(tmp_path)

    def test_rebuild_from_zero_restores_pre_corruption_hash(self, tmp_path):
        rows = _sample_rows()
        manifest = _write(rows, tmp_path)
        good = manifest["belief_store_hash"]
        jsonl = tmp_path / "beliefs.jsonl"
        jsonl.write_text(jsonl.read_text().replace("done", "cancelled", 1))
        with pytest.raises(cortex_query.StoreCorruptError):
            cortex_query.verify_store(tmp_path)
        # rebuild-from-zero over the UNCHANGED source overwrites the corrupt
        # store; the deterministic fold reproduces the exact pre-corruption hash.
        restored = _write(copy.deepcopy(rows), tmp_path)
        assert restored["belief_store_hash"] == good
        assert cortex_query.verify_store(tmp_path) == good

    def test_mutant_self_healing_serves_corrupt_rows(self, tmp_path):
        """SELF-HEALING mutant (verify=False): serves whatever bytes are on disk
        — the negative control the serve-time binding kills."""
        _write(_sample_rows(), tmp_path)
        jsonl = tmp_path / "beliefs.jsonl"
        jsonl.write_text(jsonl.read_text().replace("tasks/100", "tasks/999", 1))
        # correct path refuses...
        with pytest.raises(cortex_query.StoreCorruptError):
            cortex_query.load_beliefs_verified(tmp_path)
        # ...the mutant serves the corrupted rows (proves the binding is load-bearing).
        served = cortex_query.load_beliefs_verified(tmp_path, verify=False)
        assert any(b.subject_key == "tasks/999" for b in served)

    def test_verifier_cli_refuses_corrupt_store(self, tmp_path, capsys):
        _write(_sample_rows(), tmp_path)
        assert c2v.main(["verify", "--cache-dir", str(tmp_path)]) == 0
        jsonl = tmp_path / "beliefs.jsonl"
        jsonl.write_text(jsonl.read_text().replace("tasks/100", "tasks/999", 1))
        assert c2v.main(["verify", "--cache-dir", str(tmp_path)]) == 1
        assert "REFUSE" in capsys.readouterr().out


# ===========================================================================
# gap taxonomy — seen-set regression (§8 sim 5, A-M9/C-F14)
# ===========================================================================

def _seen(rows):
    """The manifest 'seen' block for a set of outbox rows (via the real fold)."""
    beliefs = _fold(rows)
    ids = [int(r["id"]) for r in rows]
    return engine.build_manifest(beliefs, trust_table=TT,
                                 frontier=max(ids), max_id=max(ids))["seen"]


class TestSeenSetRecorded:
    def test_manifest_records_outbox_seen_intervals(self):
        seen = _seen(_sample_rows())
        assert seen["stream_rank"] == 0
        assert seen["genesis"] == 1 and seen["max_seen"] == 6
        assert seen["intervals"] == [[1, 6]]            # contiguous
        assert seen["count"] == 6

    def test_seen_intervals_compress_a_hole(self):
        rows = [r for r in _sample_rows() if int(r["id"]) != 3]   # burn id 3
        seen = _seen(rows)
        assert seen["intervals"] == [[1, 2], [4, 6]]
        assert seen["genesis"] == 1 and seen["count"] == 5


class TestGapTaxonomy:
    def test_rollback_burned_hole_never_seen_is_benign(self):
        """(a) a BIGSERIAL id allocated then rolled back = a hole never seen in
        EITHER fold — benign, never a breach, never bridged."""
        rows = [r for r in _sample_rows() if int(r["id"]) != 3]   # id 3 burned pre-fold
        prior = _seen(rows)
        current = _seen(rows + [_orow(7, 102, "queue", event_id="evt-7")])
        verdict = c2v.classify_gaps(prior, current)
        assert verdict["status"] == "ok"
        assert verdict["regressions"] == []
        assert 3 in verdict["benign_holes"]

    def test_deleted_below_frontier_row_is_a_breach(self):
        """(b) a row that WAS folded is now gone (below the frontier) = a
        seen-set regression = breach."""
        prior = _seen(_sample_rows())                       # ids 1..6 seen
        current = _seen([r for r in _sample_rows() if int(r["id"]) != 2])  # id 2 deleted
        verdict = c2v.classify_gaps(prior, current, frontier=6)
        assert verdict["status"] == "breach"
        assert 2 in verdict["regressions"]

    def test_genesis_shift_is_a_breach(self):
        """(c) the earliest seen id moved up = source history truncated = breach."""
        prior = _seen(_sample_rows())                       # genesis 1
        current = _seen([r for r in _sample_rows() if int(r["id"]) not in (1, 2)])
        verdict = c2v.classify_gaps(prior, current)
        assert verdict["status"] == "breach"
        assert verdict["genesis_shift"] is True

    def test_no_fabricated_bridging_beliefs(self):
        # the classifier reports the gap; it never invents a belief to fill it.
        prior = _seen(_sample_rows())
        current = _seen([r for r in _sample_rows() if int(r["id"]) != 2])
        verdict = c2v.classify_gaps(prior, current, frontier=6)
        assert "bridged" not in verdict and "fabricated" not in verdict
        assert verdict.get("regressions")            # detected, not filled

    def test_mutant_hole_as_breach_flags_benign_hole(self):
        """HOLE-AS-BREACH mutant (fails seed a): any sequence hole => breach,
        so the benign rollback-burned hole is wrongly flagged."""
        rows = [r for r in _sample_rows() if int(r["id"]) != 3]
        prior = _seen(rows)
        current = _seen(rows + [_orow(7, 102, "queue", event_id="evt-7")])
        assert c2v.classify_gaps(prior, current)["status"] == "ok"
        assert c2v.classify_gaps(prior, current, mode="hole_as_breach")["status"] == "breach"

    def test_mutant_forward_window_misses_below_frontier_deletion(self):
        """FORWARD-WINDOW mutant (fails seed b): only ids >= frontier examined,
        so a deleted row below the frontier is invisible."""
        prior = _seen(_sample_rows())
        current = _seen([r for r in _sample_rows() if int(r["id"]) != 2])
        assert c2v.classify_gaps(prior, current, frontier=6)["status"] == "breach"
        mutant = c2v.classify_gaps(prior, current, frontier=6, mode="forward_window")
        assert mutant["status"] == "ok"     # the below-frontier deletion is missed


# ===========================================================================
# PG-backed realism: a real BIGSERIAL rollback burns an id (benign hole)
# ===========================================================================

@_PG_SKIP
class TestGapOverPostgres:
    @pytest.fixture(scope="class")
    def cluster(self, tmp_path_factory):
        c = HR.EphemeralPG17(tmp_path_factory.mktemp("cog2gap"), cabinet_id=HR.CAB_ID)
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

    def _read_seen(self, pg):
        protos, frontier, max_id = adapters.read_and_build(pg.conninfo())
        beliefs = engine.fold(protos, trust_table=TT)
        return engine.build_manifest(beliefs, trust_table=TT, frontier=frontier,
                                     max_id=max_id)["seen"]

    def test_real_rollback_burned_id_is_a_benign_hole(self, cluster):
        cluster.psql("TRUNCATE officer_tasks_outbox RESTART IDENTITY;")
        a = HR.seed_transition(cluster, "start", "cos")
        HR.seed_transition(cluster, "done", "cos", task_id=a)
        cluster.psql("UPDATE officer_tasks_outbox SET event_id = 'evt-' || id;")
        prior = self._read_seen(cluster)
        # a rolled-back INSERT burns the next BIGSERIAL id, leaving a hole.
        cluster.psql("BEGIN; "
                     "INSERT INTO officer_tasks_outbox (idempotency_key, task_id, "
                     "new_status, actor, cabinet_id, correlation_id, payload) VALUES "
                     "('burn', 999, 'wip', 'x', 'cog1-harness', "
                     "replace(gen_random_uuid()::text,'-',''), '{}'::jsonb); ROLLBACK;")
        b = HR.seed_transition(cluster, "queue", "cpo")
        cluster.psql("UPDATE officer_tasks_outbox SET event_id = 'evt-' || id "
                     "WHERE event_id IS NULL;")
        current = self._read_seen(cluster)
        assert current["genesis"] == prior["genesis"]        # no genesis shift
        verdict = c2v.classify_gaps(prior, current)
        assert verdict["status"] == "ok"                     # the burned id is benign
        assert verdict["regressions"] == []
