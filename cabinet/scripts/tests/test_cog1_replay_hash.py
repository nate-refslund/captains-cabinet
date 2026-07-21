"""COG-1 W4 — deterministic replay-hash gate (§9.3, sim 7, §12.2 item 5).

Tests-first (foundry.md:137 — every gate ships a mutant proving it detects its
defect). This file owns:

  * sim 7 — stale/out-of-order replay: the §9.3 immutable-content projection,
            ORDER BY id, Phase-0 §3.3 canonicalization (sorted keys, fixed-point
            integers, single UTC-second timestamp spelling, no clock/randomness),
            chained SHA-256. The hash is byte-identical across:
              (a) two independent runs over the same state (determinism);
              (b) input-order shuffle (ORDER BY id canonicalization);
              (c) redelivery churn (claimed_at/attempts/dispatched_at/... are
                  EXCLUDED — bookkeeping mutates every redelivery).
            mutant: hash over ARRIVAL ORDER (drop ORDER BY) -> a shuffle changes
            the hash, detected.
            control: a projection that INCLUDES bookkeeping -> churn changes the
            hash, detected (proves the exclusion is load-bearing).

S0: harness/CI pin PostgreSQL MAJOR 17 (production work store is 17.10; the plan
text's "16" is superseded). Interpreter python3.12. The core gates are PURE (no
DB); the PG-backed end-to-end confirmation skips without a PG17 toolchain.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util as _ilu
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_ROOT = str(_HERE.parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# hyphenated filename — load via importlib (same pattern as the falsifier test)
_SCRIPT = _HERE.parent / "cog1-replay-hash.py"
_spec = _ilu.spec_from_file_location("cog1_replay_hash", _SCRIPT)
crh = _ilu.module_from_spec(_spec)
sys.modules["cog1_replay_hash"] = crh
assert _spec and _spec.loader
_spec.loader.exec_module(crh)


# ---------------------------------------------------------------------------
# synthetic outbox rows (the shape read_outbox_rows returns: the 15 immutable
# columns + the excluded bookkeeping columns)
# ---------------------------------------------------------------------------

def _row(row_id, task_id, *, old_status=None, new_status="wip", old_blocked=None,
         new_blocked=False, actor="cos", event_id=None, occurred_at=None,
         payload=None, **book):
    base = {
        "id": row_id,
        "idempotency_key": f"task:{task_id}:{row_id}:{new_status}:{new_blocked}",
        "event_id": event_id,
        "task_id": task_id,
        "old_status": old_status,
        "new_status": new_status,
        "old_blocked": old_blocked,
        "new_blocked": new_blocked,
        # blocked_reason is EXCLUDED from the projection (travels in payload)
        "blocked_reason": book.pop("blocked_reason", None),
        "actor": actor,
        "context_slug": "cog1",
        "cabinet_id": "cog1-harness",
        "correlation_id": f"corr{row_id:032d}",
        "causation_id": None,
        "occurred_at": occurred_at or datetime(2026, 7, 20, 8, 0, row_id % 60,
                                               tzinfo=timezone.utc),
        "payload": payload if payload is not None else {
            "task_id": task_id, "old_status": old_status, "new_status": new_status,
            "old_blocked": old_blocked, "new_blocked": new_blocked,
            "blocked_reason": None, "actor": actor, "context_slug": "cog1"},
        # dispatch bookkeeping (EXCLUDED from the §9.3 projection)
        "destination": book.pop("destination", "stream"),
        "claimed_at": book.pop("claimed_at", None),
        "attempts": book.pop("attempts", 0),
        "dispatched_at": book.pop("dispatched_at", None),
        "failed_terminal_at": book.pop("failed_terminal_at", None),
        "last_error": book.pop("last_error", None),
    }
    base.update(book)
    return base


def _sample_rows():
    return [
        _row(1, 100, old_status=None, new_status="wip", new_blocked=False),
        _row(2, 100, old_status="wip", new_status="wip", old_blocked=False,
             new_blocked=True, payload={"task_id": 100, "new_status": "wip",
                                        "new_blocked": True, "blocked_reason": "x"}),
        _row(3, 101, old_status=None, new_status="queue"),
        _row(4, 100, old_status="wip", new_status="done", old_blocked=True,
             new_blocked=False, event_id="01J000000000000000000000AB"),
    ]


# ===========================================================================
# projection shape (§9.3 — exactly 15 columns; the excluded set is pinned)
# ===========================================================================

class TestProjectionShape:
    def test_immutable_columns_are_exactly_the_15_pinned(self):
        assert crh.IMMUTABLE_CONTENT_COLUMNS == (
            "id", "idempotency_key", "event_id", "task_id",
            "old_status", "new_status", "old_blocked", "new_blocked",
            "actor", "context_slug", "cabinet_id", "correlation_id",
            "causation_id", "occurred_at", "payload",
        )

    def test_blocked_reason_and_destination_and_bookkeeping_excluded(self):
        for excluded in ("blocked_reason", "destination", "claimed_at",
                         "attempts", "dispatched_at", "failed_terminal_at",
                         "last_error"):
            assert excluded not in crh.IMMUTABLE_CONTENT_COLUMNS

    def test_project_row_keeps_only_projection_keys(self):
        p = crh.project_row(_row(1, 100))
        assert set(p) == set(crh.IMMUTABLE_CONTENT_COLUMNS)


# ===========================================================================
# canonicalization (Phase-0 §3.3)
# ===========================================================================

class TestCanonicalization:
    def test_sorted_keys_top_and_nested_payload(self):
        js = crh.canonical_row_json(crh.project_row(_row(1, 100)))
        # canonical text must equal a re-dump with sort_keys (byte-stable);
        # both top-level AND nested payload keys are sorted by construction.
        parsed = json.loads(js)
        assert list(parsed) == sorted(parsed)
        assert list(parsed["payload"]) == sorted(parsed["payload"])
        assert js == json.dumps(parsed, sort_keys=True,
                                separators=(",", ":"), ensure_ascii=False)

    def test_occurred_at_single_utc_second_spelling(self):
        p = crh.project_row(_row(1, 100,
                                 occurred_at="2026-07-20T08:00:05.123456+02:00"))
        assert p["occurred_at"] == "2026-07-20T06:00:05Z"

    def test_utc_second_is_the_same_dialect_as_the_relay(self):
        from framework.outbox import relay
        for v in ("2026-07-20T08:00:05.999+02:00",
                  datetime(2026, 7, 20, 8, 0, 5, tzinfo=timezone.utc),
                  "2026-01-01T00:00:00Z"):
            assert crh._utc_second(v) == relay._utc_second(v)

    def test_no_clock_no_randomness_pure(self):
        rows = _sample_rows()
        assert crh.chained_hash(rows) == crh.chained_hash(rows)


# ===========================================================================
# sim 7 — determinism, shuffle, churn + the pinned mutant
# ===========================================================================

class TestSim7ReplayHash:
    def test_double_run_identical(self):
        rows = _sample_rows()
        assert crh.chained_hash(rows) == crh.chained_hash(copy.deepcopy(rows))

    def test_shuffle_invariant(self):
        rows = _sample_rows()
        shuffled = [rows[2], rows[0], rows[3], rows[1]]
        assert crh.chained_hash(rows) == crh.chained_hash(shuffled)

    def test_redelivery_churn_invariant(self):
        rows = _sample_rows()
        base = crh.chained_hash(rows)
        churned = copy.deepcopy(rows)
        for r in churned:
            r["claimed_at"] = datetime.now(timezone.utc)
            r["attempts"] = r["attempts"] + 7
            r["dispatched_at"] = datetime.now(timezone.utc)
            r["failed_terminal_at"] = None
            r["last_error"] = "[transport] redis flap"
        assert crh.chained_hash(churned) == base

    def test_predispatch_null_event_id_in_scope(self):
        # a pre-dispatch row (event_id NULL) is hashed WITH the NULL...
        row = _row(1, 100, event_id=None)
        h_null = crh.chained_hash([row])
        # ...and the hash is a function of content: backfilling the id changes it
        row2 = copy.deepcopy(row)
        row2["event_id"] = "01J000000000000000000000AB"
        assert crh.chained_hash([row2]) != h_null

    def test_content_change_changes_hash(self):
        rows = _sample_rows()
        base = crh.chained_hash(rows)
        changed = copy.deepcopy(rows)
        changed[0]["new_status"] = "cancelled"
        assert crh.chained_hash(changed) != base

    def test_mutant_arrival_order_hash_detected(self):
        """The pinned sim-7 mutant: hashing over ARRIVAL ORDER (no ORDER BY id)
        is NOT shuffle-invariant, so dropping the canonical ordering is caught."""
        rows = _sample_rows()
        shuffled = [rows[2], rows[0], rows[3], rows[1]]
        # correct (ORDER BY id): shuffle-invariant
        assert crh.chained_hash(rows) == crh.chained_hash(shuffled)
        # mutant (arrival order): a shuffle changes the hash -> detected
        mutant_a = crh.chained_hash(rows, order_by_id=False)
        mutant_b = crh.chained_hash(shuffled, order_by_id=False)
        assert mutant_a != mutant_b

    def test_control_bookkeeping_inclusion_would_break_churn(self):
        """Negative control for the exclusion: a projection that INCLUDES a
        bookkeeping column (attempts) is NOT churn-invariant — proving the
        §9.3 exclusion is load-bearing, not incidental."""
        rows = _sample_rows()

        def _hash_with_attempts(rs):
            acc = hashlib.sha256(b"ctl").digest()
            for r in sorted(rs, key=lambda x: x["id"]):
                proj = crh.project_row(r)
                proj["attempts"] = r.get("attempts", 0)  # leak bookkeeping in
                acc = hashlib.sha256(
                    acc + crh.canonical_row_json(proj).encode("utf-8")).digest()
            return acc.hex()

        base = _hash_with_attempts(rows)
        churned = copy.deepcopy(rows)
        for r in churned:
            r["attempts"] += 3
        assert _hash_with_attempts(churned) != base  # the leak breaks churn

    def test_chain_is_length_sensitive(self):
        rows = _sample_rows()
        assert crh.chained_hash(rows) != crh.chained_hash(rows[:-1])

    def test_hash_is_hex_sha256(self):
        h = crh.chained_hash(_sample_rows())
        assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)


# ===========================================================================
# PG-backed end-to-end confirmation (skips without a PG17 toolchain)
# ===========================================================================

def _load_relay_harness():
    p = _ROOT + "/framework/outbox/tests/lib_relay_harness.py"
    spec = _ilu.spec_from_file_location("lib_relay_harness_rh", p)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


HR = _load_relay_harness()
_PG_SKIP = pytest.mark.skipif(not HR.pg_available(), reason=HR.PG_SKIP_REASON)


@_PG_SKIP
class TestReplayHashOverPostgres:
    @pytest.fixture(scope="class")
    def cluster(self, tmp_path_factory):
        c = HR.EphemeralPG17(tmp_path_factory.mktemp("cog1hash"),
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

    def _seed(self, cluster):
        tid = HR.seed_transition(cluster, "start", "cos")
        HR.seed_transition(cluster, "block", "cos", task_id=tid)
        HR.seed_transition(cluster, "unblock", "cos", task_id=tid)
        HR.seed_transition(cluster, "done", "cos", task_id=tid)
        return tid

    def test_read_projection_matches_pinned_columns(self, cluster):
        self._seed(cluster)
        rows = crh.read_outbox_rows(cluster.conninfo())
        assert rows, "capture trigger minted rows"
        for r in rows:
            assert set(crh.IMMUTABLE_CONTENT_COLUMNS).issubset(set(r))

    def test_double_read_byte_identical(self, cluster):
        self._seed(cluster)
        assert crh.hash_dsn(cluster.conninfo()) == crh.hash_dsn(cluster.conninfo())

    def test_cli_double_run_identical(self, cluster):
        self._seed(cluster)
        out1 = subprocess.run(
            ["python3.12", str(_SCRIPT), "--dsn", cluster.conninfo()],
            capture_output=True, text=True)
        out2 = subprocess.run(
            ["python3.12", str(_SCRIPT), "--dsn", cluster.conninfo()],
            capture_output=True, text=True)
        assert out1.returncode == 0, out1.stderr
        assert out1.stdout.strip() and out1.stdout.strip() == out2.stdout.strip()

    def test_churn_invariant_over_postgres(self, cluster):
        self._seed(cluster)
        before = crh.hash_dsn(cluster.conninfo())
        # redelivery churn: age the claims + bump attempts on the live rows
        HR.age_claims(cluster.conninfo(), seconds=3600)
        assert crh.hash_dsn(cluster.conninfo()) == before
