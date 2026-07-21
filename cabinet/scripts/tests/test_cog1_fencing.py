"""COG-1 W4 — outbox_* vocabulary fencing gate (§7, §12.2 item 6).

Three independent writers share the central `outbox_queued/dispatched/failed`
event vocabulary: (1) the relay proper; (2) task_sync_runner cycle telemetry;
(3) the channels send journal (self-discriminated `kind=='channel_send'`). Any
parity metric that counts `outbox_*` events double-counts until fenced. This
file pins the fence (payload discrimination + positive marker, NOT event-type
renames — no VALID_EVENT_TYPES edit):

  * discriminator — task_sync_runner stamps payload.kind='task_sync_telemetry'
                    on ALL THREE of its emits (event types UNCHANGED).
  * marker filter — the legacy ledger drain processes ONLY marker-bearing
                    (queued_by) rows; task_sync's adapter-less rows are fenced
                    to `foreign` and never drained.
  * zero central-ledger emits from the TABLE drain — the COG-1 table-drain path
                    emits ZERO `outbox_*` events (its only telemetry is the
                    parity JSONL); it must never become the fourth writer family.
                    mutant: an emit() inserted into a drain function is detected
                    by the AST scan.

Interpreter python3.12. The behavioral zero-emit confirmation skips without a
PG17 toolchain + redis.
"""
from __future__ import annotations

import ast
import importlib.util as _ilu
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_ROOT = str(_HERE.parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from framework.outbox import relay  # noqa: E402
from cabinet.scripts import task_sync_runner as tsr  # noqa: E402


# ===========================================================================
# discriminator — task_sync_runner stamps payload.kind='task_sync_telemetry'
# ===========================================================================

class _FakeAdapter:
    def __init__(self, *, healthy=True, destination="github-issues"):
        self.destination = destination
        self._healthy = healthy

    def health_check(self):
        return self._healthy

    def pull(self):
        return []


def _capture_emits(monkeypatch, *, healthy=True):
    calls = []
    monkeypatch.setattr(tsr, "emit",
                        lambda etype, **kw: calls.append((etype, kw)))
    monkeypatch.setattr(tsr, "_active_project_config", lambda *a, **k: {})
    monkeypatch.setattr(tsr, "get_adapter",
                        lambda cfg: _FakeAdapter(healthy=healthy))
    tsr.run_sync(actor="fence-test")
    return calls


class TestTaskSyncDiscriminator:
    def test_healthy_cycle_all_emits_carry_the_discriminator(self, monkeypatch):
        calls = _capture_emits(monkeypatch, healthy=True)
        etypes = [e for e, _ in calls]
        # event types are UNCHANGED (no VALID_EVENT_TYPES edit)
        assert "outbox_queued" in etypes and "outbox_dispatched" in etypes
        for etype, kw in calls:
            payload = kw.get("payload") or {}
            assert payload.get("kind") == "task_sync_telemetry", (
                f"{etype} emit missing the task_sync_telemetry discriminator")

    def test_health_fail_cycle_failed_emit_carries_the_discriminator(self, monkeypatch):
        calls = _capture_emits(monkeypatch, healthy=False)
        etypes = [e for e, _ in calls]
        assert "outbox_failed" in etypes
        for etype, kw in calls:
            assert (kw.get("payload") or {}).get("kind") == "task_sync_telemetry"

    def test_discriminator_excludes_telemetry_from_parity_arithmetic(self, monkeypatch):
        """The fence's purpose: parity tooling that counts outbox_* events must
        drop the three discriminated writer families (no double-count)."""
        calls = _capture_emits(monkeypatch, healthy=True)
        fenced = [(e, kw) for e, kw in calls
                  if (kw.get("payload") or {}).get("kind")
                  not in {"task_sync_telemetry", "channel_send"}]
        assert fenced == [], "every task_sync emit is discriminated out of parity"


# ===========================================================================
# marker filter — the legacy drain processes ONLY marker-bearing rows
# ===========================================================================

class TestMarkerFilter:
    def _fake_replay(self, queued):
        def _replay(event_types=None, **kw):
            if event_types == ["outbox_queued"]:
                return list(queued)
            return []  # nothing terminal-processed
        return _replay

    def test_pending_queue_keeps_marker_rows_only(self, monkeypatch):
        marker = {"id": "e1", "payload": {
            "queued_by": relay.QUEUED_BY_MARKER, "destination": "notion",
            "payload": {"x": 1}}}
        foreign = {"id": "e2", "payload": {
            "kind": "task_sync_telemetry", "destination": "github-issues"}}
        monkeypatch.setattr(relay, "replay",
                            self._fake_replay([marker, foreign]))
        pending = relay._pending_queue()
        foreign_rows = relay._foreign_ledger_rows()
        assert [e["id"] for e in pending] == ["e1"]
        assert [e["id"] for e in foreign_rows] == ["e2"]

    def test_task_sync_telemetry_row_is_fenced_not_drained(self, monkeypatch):
        """task_sync's discriminated telemetry rows lack the queued_by marker,
        so the legacy drain never dispatches them (the historical orphan
        `outbox_queued` neutralization, §7 item 3)."""
        ts_row = {"id": "e9", "payload": {
            "kind": "task_sync_telemetry", "destination": "linear"}}
        monkeypatch.setattr(relay, "replay", self._fake_replay([ts_row]))
        assert relay._pending_queue() == []
        assert not relay._is_marker_row(ts_row)
        assert [e["id"] for e in relay._foreign_ledger_rows()] == ["e9"]


# ===========================================================================
# zero central-ledger emits from the table drain (AST scan + mutant)
# ===========================================================================

# The COG-1 table-drain code path (§6.1 step 4: "emits ZERO central-ledger
# events"). The legacy event-ledger drain (dispatch_one/dispatch_pending/queue)
# is DELIBERATELY excluded — it is the classic outbox_* emitter.
_TABLE_DRAIN_FUNCS = {
    "_db_identity", "_claim_rows", "_backfill_event_id", "_cabinet_backstop",
    "_classify_failure", "_describe", "_process_row", "_mark_failure",
    "_safe_process", "_append_parity_sample", "drain_tasks_outbox",
    "build_dispatch_fields", "_stream_adapter", "register_table_adapter",
    "effective_old_status", "effective_new_status", "_utc_second", "_mint_ulid",
}


def _funcs_calling_emit(source: str, wanted: set[str]) -> set[str]:
    """Names of top-level functions in `source` (restricted to `wanted`) whose
    body contains a call to `emit` / `*.emit` — the executable fence scanner."""
    tree = ast.parse(source)
    hits: set[str] = set()
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in wanted:
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                fn = sub.func
                name = (fn.id if isinstance(fn, ast.Name)
                        else fn.attr if isinstance(fn, ast.Attribute) else None)
                if name == "emit":
                    hits.add(node.name)
    return hits


class TestTableDrainEmitsNothing:
    def test_no_table_drain_function_calls_emit(self):
        source = (Path(_ROOT) / "framework" / "outbox" / "relay.py").read_text()
        present = {n.name for n in ast.parse(source).body
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        # guard: the pinned drain-function set actually exists in relay.py
        missing = _TABLE_DRAIN_FUNCS - present
        assert not missing, f"drain funcs renamed/removed: {missing}"
        offenders = _funcs_calling_emit(source, _TABLE_DRAIN_FUNCS)
        assert offenders == set(), (
            f"table-drain functions emit central-ledger events: {offenders}")

    def test_mutant_emit_in_a_drain_function_is_detected(self):
        """The scanner must catch a regression that adds an emit() to the drain
        (else the fence is decorative)."""
        mutant = (
            "def drain_tasks_outbox(dsn):\n"
            "    counts = {}\n"
            "    emit('outbox_dispatched', actor='relay', payload={})\n"
            "    return counts\n")
        assert _funcs_calling_emit(mutant, _TABLE_DRAIN_FUNCS) == {
            "drain_tasks_outbox"}

    def test_legacy_drain_still_emits_scanner_is_not_vacuous(self):
        """Sanity: the scanner DOES see emits — the legacy dispatch_one path is
        the classic outbox_* emitter, so restricting to it must be non-empty."""
        source = (Path(_ROOT) / "framework" / "outbox" / "relay.py").read_text()
        assert _funcs_calling_emit(source, {"dispatch_one"}) == {"dispatch_one"}


# ===========================================================================
# behavioral zero-emit confirmation over a live drain (skips without PG+redis)
# ===========================================================================

def _load_relay_harness():
    p = _ROOT + "/framework/outbox/tests/lib_relay_harness.py"
    spec = _ilu.spec_from_file_location("lib_relay_harness_fence", p)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


HR = _load_relay_harness()
_PG_SKIP = pytest.mark.skipif(not HR.pg_available(), reason=HR.PG_SKIP_REASON)
_REDIS_SKIP = pytest.mark.skipif(not HR.redis_available(), reason=HR.REDIS_SKIP_REASON)


@_PG_SKIP
@_REDIS_SKIP
class TestLiveDrainEmitsNothing:
    @pytest.fixture(scope="class")
    def cluster(self, tmp_path_factory):
        c = HR.EphemeralPG17(tmp_path_factory.mktemp("cog1fence"),
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

    def test_drain_cycle_emits_zero_central_ledger_events(self, cluster,
                                                          monkeypatch):
        HR.seed_transition(cluster, "start", "cos")
        sb = HR.RedisSandbox().start()
        try:
            for k, v in sb.env().items():
                monkeypatch.setenv(k, v)
            seen = []
            monkeypatch.setattr(relay, "emit",
                                lambda *a, **k: seen.append(a[:1]))
            counts = relay.drain_tasks_outbox(cluster.conninfo(),
                                              cabinet_id=HR.CAB_ID, batch=50)
            assert counts["dispatched"] == 1
            assert seen == [], f"table drain emitted central-ledger events: {seen}"
        finally:
            sb.stop()
