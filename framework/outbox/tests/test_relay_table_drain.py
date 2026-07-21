"""COG-1 W3 — relay table-drain crash/concurrency sims (§6.1, §9.1, §12.2 item 4).

Tests-first (foundry.md:137 — every gate ships a mutant proving it detects its
defect). The relay sims this file owns:

  * sim 2  — crash after state+outbox commit: the durable outbox row is picked
             up next cycle and dispatched EXACTLY once (M1=0).
             mutant: invert the claim pending-filter (dispatched_at IS NULL ->
             IS NOT NULL — semantic, not the index drop) -> the pending row is
             never claimed (loss), detected.
  * sim 3  — relay death BEFORE send, at BOTH kill points: (a) before the
             event_id backfill commit -> event_id rolls back, redelivery mints
             + dispatches once; (b) after the backfill commit -> the SAME
             committed id is reused on redelivery (id-stability, §6.1).
             mutant: claim WITHOUT the TTL -> the killed row is stuck forever,
             detected.
  * sim 4  — external success before ACK: kill between adapter success and the
             dispatched_at record -> the counting UPSERT adapter shows external
             effect count == 1 after redelivery (C2 idempotency).
             mutant: non-idempotent adapter (append, not upsert) -> count 2.
  * sim 5  — duplicate delivery: both deliveries carry the IDENTICAL committed
             event_id (consumer dedupe key); no duplicated effect.
             mutant: re-mint event_id per dispatch -> id-stability fails.
  * sim 8  — transport partition held PAST MAX_ATTEMPTS x claim-TTL: transient
             classification only, NO terminal quarantine (M1 preserved), full
             recovery on restart; + the pg-twin (record fails after a
             successful XADD -> duplicate stream entry absorbed by the stable
             event_id).
             mutant: classify transport as terminal -> the row wrongly dies.
  * sim 9  — poison payload -> validation-class terminal quarantine; the drain
             continues (per-row isolation).
             mutant: poison propagates out of the per-row guard -> the batch
             starves, detected.
  * sim 10b — relay-side cabinet spoof BACKSTOP: a hand-planted foreign
             cabinet_id row is terminal-refused, never dispatched; per-row
             isolation keeps a legit row flowing.
             mutant: backstop removed -> the foreign row is dispatched.

S0: harness/CI pin PostgreSQL MAJOR 17 (production work store is 17.10; the
plan text's "16" is superseded — see lib_cog1_harness.py). Interpreter
python3.12. Skips without a PG17 toolchain (or COG1_PG_DSN) + psycopg2 + a
redis binary.
"""
from __future__ import annotations

import importlib.util as _ilu
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_ROOT = str(_HERE.parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_spec = _ilu.spec_from_file_location("lib_relay_harness", _HERE / "lib_relay_harness.py")
HR = _ilu.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(HR)

from framework.outbox import relay

CTX = HR.CTX
CAB_ID = HR.CAB_ID
SHADOW = relay.SHADOW_STREAM

_PG_SKIP = pytest.mark.skipif(not HR.pg_available(), reason=HR.PG_SKIP_REASON)
_REDIS_SKIP = pytest.mark.skipif(not HR.redis_available(), reason=HR.REDIS_SKIP_REASON)


# ===========================================================================
# Fixtures — one module cluster (base chain + identity + 047); clean per test
# ===========================================================================

@pytest.fixture(scope="module")
def cluster(tmp_path_factory):
    if not HR.pg_available():
        pytest.skip(HR.PG_SKIP_REASON)
    c = HR.EphemeralPG17(tmp_path_factory.mktemp("cog1relay"), cabinet_id=CAB_ID)
    try:
        c.start()
    except Exception as e:  # noqa: BLE001
        tail = c.logfile.read_text()[-800:] if c.logfile.exists() else ""
        pytest.skip(f"could not start ephemeral PG17: {e}\n{tail}")
    try:
        c.apply_base_chain()
        c.apply_identity_guc(CAB_ID)
        c.apply_047()
        yield c
    finally:
        c.stop()


@pytest.fixture
def dsn(cluster):
    """A clean-slate scratch DSN: truncate the pilot tables so row/pending
    counts are unambiguous per test."""
    conn = HR.connect(cluster.conninfo())
    with conn.cursor() as cur:
        cur.execute("TRUNCATE officer_tasks_outbox, officer_task_history, "
                    "officer_tasks RESTART IDENTITY CASCADE;")
    conn.close()
    return cluster.conninfo()


@pytest.fixture
def redis_sbx():
    if not HR.redis_available():
        pytest.skip(HR.REDIS_SKIP_REASON)
    sb = HR.RedisSandbox().start()
    try:
        yield sb
    finally:
        sb.stop()


@pytest.fixture
def redis_env(redis_sbx, monkeypatch):
    for k, v in redis_sbx.env().items():
        monkeypatch.setenv(k, v)
    return redis_sbx


def _seed_row(cluster, verb="start", officer="cos", **kw):
    """Drive a real capture-trigger transition; return (task_id, outbox_row)."""
    tid = HR.seed_transition(cluster, verb, officer, **kw)
    rows = HR.rows_for_task(cluster.conninfo(), tid)
    assert rows, "capture trigger minted no outbox row"
    return tid, rows[-1]


# ===========================================================================
# Executable mutants (module-level so tests monkeypatch relay internals)
# ===========================================================================

def _claim_rows_inverted(conn, batch, claim_ttl_seconds):
    """MUTANT (sim 2): the pending filter is inverted — dispatched_at IS NOT
    NULL. Semantic defect (not an index drop): the pending row is invisible."""
    import psycopg2.extras
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "UPDATE officer_tasks_outbox SET claimed_at=NOW(), attempts=attempts+1 "
            "WHERE id IN (SELECT id FROM officer_tasks_outbox "
            "  WHERE dispatched_at IS NOT NULL AND failed_terminal_at IS NULL "
            "  AND (claimed_at IS NULL OR claimed_at < NOW() - %s * INTERVAL '1 second') "
            "  ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED) RETURNING *",
            (claim_ttl_seconds, batch))
        rows = [dict(r) for r in cur.fetchall()]
    conn.commit()
    return rows


def _claim_rows_no_ttl(conn, batch, claim_ttl_seconds):
    """MUTANT (sim 3): claim without the TTL branch — a killed row whose
    claimed_at is already set is never re-claimable (stuck forever)."""
    import psycopg2.extras
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "UPDATE officer_tasks_outbox SET claimed_at=NOW(), attempts=attempts+1 "
            "WHERE id IN (SELECT id FROM officer_tasks_outbox "
            "  WHERE dispatched_at IS NULL AND failed_terminal_at IS NULL "
            "  AND claimed_at IS NULL "
            "  ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED) RETURNING *",
            (batch,))
        rows = [dict(r) for r in cur.fetchall()]
    conn.commit()
    return rows


def _backfill_remint(conn, row, fault_hook=None):
    """MUTANT (sim 5): re-mint event_id on every dispatch (no WHERE event_id
    IS NULL) — strips id-stability across redelivery."""
    new_id = relay._mint_ulid()
    with conn.cursor() as cur:
        cur.execute("UPDATE officer_tasks_outbox SET event_id=%s WHERE id=%s",
                    (new_id, row["id"]))
    conn.commit()
    row["event_id"] = new_id
    return new_id


def _unsafe_process(conn, row, ctx, counts):
    """MUTANT (sim 9): no per-row isolation — a poison row's exception
    propagates out of the batch loop (the drain starves)."""
    relay._process_row(conn, row, ctx)
    counts["dispatched"] += 1


# ===========================================================================
# Sim 2 — crash after state+outbox commit -> relay picks up exactly once
# ===========================================================================

@_PG_SKIP
@_REDIS_SKIP
class TestSim2CommittedRowRedelivered:
    def test_committed_row_dispatched_exactly_once(self, cluster, dsn, redis_env):
        tid, row = _seed_row(cluster)
        # "crash after commit, before any relay cycle": the durable row survives
        assert row["dispatched_at"] is None and row["event_id"] is None
        counts = relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID, batch=50)
        assert counts["dispatched"] == 1
        after = HR.fetch_row(dsn, row["id"])
        assert after["dispatched_at"] is not None
        assert after["event_id"] is not None
        # M1=0: exactly one dispatched event for the committed mutation
        assert redis_env.xlen(SHADOW) == 1
        assert after["event_id"] in redis_env.raw(SHADOW)
        # a second cycle dispatches nothing (idempotent drain)
        counts2 = relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID)
        assert counts2["dispatched"] == 0
        assert redis_env.xlen(SHADOW) == 1

    def test_mutant_inverted_claim_filter_loses_the_row(self, cluster, dsn,
                                                        redis_env, monkeypatch):
        tid, row = _seed_row(cluster)
        monkeypatch.setattr(relay, "_claim_rows", _claim_rows_inverted)
        counts = relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID)
        assert counts["dispatched"] == 0, \
            "inverted filter never claims the pending row (acknowledged mutation lost)"
        assert HR.fetch_row(dsn, row["id"])["dispatched_at"] is None
        assert redis_env.xlen(SHADOW) == 0


# ===========================================================================
# Sim 3 — relay death before send, dual kill points + id-stability
# ===========================================================================

@_PG_SKIP
@_REDIS_SKIP
class TestSim3RelayDeathBeforeSend:
    def test_kill_before_backfill_commit_redelivers_once(self, cluster, dsn,
                                                         redis_env):
        tid, row = _seed_row(cluster)

        def fh(point):
            if point == "before_backfill_commit":
                raise relay._RelayCrash()

        with pytest.raises(relay._RelayCrash):
            relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID, fault_hook=fh)
        killed = HR.fetch_row(dsn, row["id"])
        assert killed["event_id"] is None, "backfill rolled back on the crash"
        assert killed["dispatched_at"] is None
        assert redis_env.xlen(SHADOW) == 0
        # redelivery (claim-TTL expired) mints + dispatches exactly once
        HR.age_claims(dsn)
        counts = relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID)
        assert counts["dispatched"] == 1
        recovered = HR.fetch_row(dsn, row["id"])
        assert recovered["event_id"] is not None
        assert recovered["dispatched_at"] is not None
        assert redis_env.xlen(SHADOW) == 1
        assert recovered["event_id"] in redis_env.raw(SHADOW)

    def test_kill_after_backfill_commit_reuses_same_id(self, cluster, dsn,
                                                       redis_env):
        tid, row = _seed_row(cluster)

        def fh(point):
            if point == "after_backfill_commit":
                raise relay._RelayCrash()

        with pytest.raises(relay._RelayCrash):
            relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID, fault_hook=fh)
        killed = HR.fetch_row(dsn, row["id"])
        committed = killed["event_id"]
        assert committed is not None, "event_id committed durably before the kill"
        assert killed["dispatched_at"] is None
        assert redis_env.xlen(SHADOW) == 0
        # redelivery reuses the SAME committed id (WHERE event_id IS NULL no-op)
        HR.age_claims(dsn)
        counts = relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID)
        assert counts["dispatched"] == 1
        recovered = HR.fetch_row(dsn, row["id"])
        assert recovered["event_id"] == committed, "id STABLE across redelivery (§6.1)"
        assert redis_env.xlen(SHADOW) == 1
        assert committed in redis_env.raw(SHADOW)

    def test_mutant_claim_without_ttl_strands_the_killed_row(self, cluster, dsn,
                                                             redis_env, monkeypatch):
        tid, row = _seed_row(cluster)

        def fh(point):
            if point == "after_backfill_commit":
                raise relay._RelayCrash()

        with pytest.raises(relay._RelayCrash):
            relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID, fault_hook=fh)
        # MUTANT: no TTL -> the killed (claimed_at-set) row never re-claims
        monkeypatch.setattr(relay, "_claim_rows", _claim_rows_no_ttl)
        HR.age_claims(dsn)
        counts = relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID)
        assert counts["dispatched"] == 0, "no-TTL claim strands the killed row"
        assert HR.fetch_row(dsn, row["id"])["dispatched_at"] is None


# ===========================================================================
# Sim 4 — external success before ACK -> redelivery, C2 effect==1
# ===========================================================================

@_PG_SKIP
class TestSim4ExternalSuccessBeforeAck:
    @staticmethod
    def _counting_upsert(effects, seen):
        def adapter(fields, *, idempotency_key):
            if idempotency_key in seen:      # C2: upsert-by-canonical-id
                return
            seen.add(idempotency_key)
            effects.append(idempotency_key)
        return adapter

    def _seed_external(self, cluster, dsn):
        tid, row = _seed_row(cluster)
        conn = HR.connect(dsn)
        with conn.cursor() as cur:
            cur.execute("UPDATE officer_tasks_outbox SET destination='external' "
                        "WHERE id=%s", (row["id"],))
        conn.close()
        return tid, row

    def test_effect_once_across_ack_crash(self, cluster, dsn):
        effects, seen = [], set()
        adapter = self._counting_upsert(effects, seen)
        tid, row = self._seed_external(cluster, dsn)

        def fh(point):
            if point == "after_effect":
                raise relay._RelayCrash()

        with pytest.raises(relay._RelayCrash):
            relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID, fault_hook=fh,
                                     adapters={"external": adapter})
        assert len(effects) == 1, "external effect applied once before the crash"
        assert HR.fetch_row(dsn, row["id"])["dispatched_at"] is None, "ACK never recorded"
        # redelivery re-invokes the idempotent adapter + records the ACK
        HR.age_claims(dsn)
        counts = relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID,
                                          adapters={"external": adapter})
        assert counts["dispatched"] == 1
        assert len(effects) == 1, "no externally duplicated effect after redelivery"
        assert HR.fetch_row(dsn, row["id"])["dispatched_at"] is not None

    def test_mutant_non_idempotent_adapter_double_applies(self, cluster, dsn):
        effects = []

        def non_idem(fields, *, idempotency_key):
            effects.append(idempotency_key)   # MUTANT: INSERT, not upsert

        tid, row = self._seed_external(cluster, dsn)

        def fh(point):
            if point == "after_effect":
                raise relay._RelayCrash()

        with pytest.raises(relay._RelayCrash):
            relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID, fault_hook=fh,
                                     adapters={"external": non_idem})
        assert len(effects) == 1
        HR.age_claims(dsn)
        relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID,
                                 adapters={"external": non_idem})
        assert len(effects) == 2, "non-idempotent adapter double-applies (detected)"


# ===========================================================================
# Sim 5 — duplicate delivery -> identical committed event_id
# ===========================================================================

@_PG_SKIP
@_REDIS_SKIP
class TestSim5DuplicateDelivery:
    def test_duplicate_delivery_carries_same_event_id(self, cluster, dsn, redis_env):
        tid, row = _seed_row(cluster)
        relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID)
        eid = HR.fetch_row(dsn, row["id"])["event_id"]
        assert eid is not None and redis_env.xlen(SHADOW) == 1
        # force a duplicate delivery of the SAME row (event_id retained)
        HR.reset_dispatch(dsn, row["id"])
        relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID)
        assert HR.fetch_row(dsn, row["id"])["event_id"] == eid
        assert redis_env.xlen(SHADOW) == 2
        assert redis_env.raw(SHADOW).count(eid) == 2, \
            "both deliveries carry the IDENTICAL committed event_id (dedupe key)"

    def test_mutant_reminted_id_breaks_stability(self, cluster, dsn, redis_env,
                                                 monkeypatch):
        tid, row = _seed_row(cluster)
        relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID)
        eid = HR.fetch_row(dsn, row["id"])["event_id"]
        monkeypatch.setattr(relay, "_backfill_event_id", _backfill_remint)
        HR.reset_dispatch(dsn, row["id"])
        relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID)
        assert HR.fetch_row(dsn, row["id"])["event_id"] != eid, \
            "mutant re-mints -> id-stability assertion fails (detected)"


# ===========================================================================
# Sim 8 — transport partition past MAX_ATTEMPTS x TTL -> NO terminal (M1)
# ===========================================================================

@_PG_SKIP
@_REDIS_SKIP
class TestSim8TransportPartition:
    def test_partition_never_terminal_recovers(self, cluster, dsn, redis_env):
        tid, row = _seed_row(cluster)
        redis_env.kill()                       # partition
        cap = 2
        for _ in range(cap + 3):               # run PAST the attempt cap
            relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID, max_attempts=cap)
            HR.age_claims(dsn)                  # simulate claim-TTL expiry
        held = HR.fetch_row(dsn, row["id"])
        assert held["dispatched_at"] is None
        assert held["failed_terminal_at"] is None, \
            "a transport partition must NOT terminal-quarantine (repeals M1)"
        assert int(held["attempts"]) > cap, "row was retried past the attempt cap"
        # recover: restart redis -> next cycle dispatches, no loss
        redis_env.restart()
        counts = relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID, max_attempts=cap)
        assert counts["dispatched"] == 1
        assert redis_env.xlen(SHADOW) == 1
        assert HR.fetch_row(dsn, row["id"])["dispatched_at"] is not None

    def test_pgtwin_record_fails_after_xadd_duplicate_absorbed(self, cluster, dsn,
                                                               redis_env):
        tid, row = _seed_row(cluster)

        def fh(point):
            if point == "after_effect":       # XADD done; record step errors
                raise relay.RelayTransportError("record step failed after XADD")

        relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID, fault_hook=fh, max_attempts=5)
        held = HR.fetch_row(dsn, row["id"])
        assert held["dispatched_at"] is None and held["failed_terminal_at"] is None
        eid = held["event_id"]
        assert eid is not None and redis_env.xlen(SHADOW) == 1
        # redelivery re-XADDs (duplicate) + records
        HR.age_claims(dsn)
        counts = relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID, max_attempts=5)
        assert counts["dispatched"] == 1
        assert HR.fetch_row(dsn, row["id"])["dispatched_at"] is not None
        assert redis_env.xlen(SHADOW) == 2
        assert redis_env.raw(SHADOW).count(eid) == 2, \
            "the duplicate stream entry carries the SAME event_id (effect idempotency absorbs it)"

    def test_mutant_transport_classified_terminal_loses_row(self, cluster, dsn,
                                                            redis_env, monkeypatch):
        tid, row = _seed_row(cluster)
        redis_env.kill()
        monkeypatch.setattr(relay, "_classify_failure", lambda exc: "validation")
        cap = 1
        for _ in range(cap + 2):
            relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID, max_attempts=cap)
            HR.age_claims(dsn)
        dead = HR.fetch_row(dsn, row["id"])
        assert dead["failed_terminal_at"] is not None, \
            "mutant: mis-classified transport hits the attempt cap and dies"
        assert dead["dispatched_at"] is None, "acknowledged mutation lost (detected)"


# ===========================================================================
# Sim 9 — poison payload -> validation-class terminal; per-row isolation
# ===========================================================================

@_PG_SKIP
@_REDIS_SKIP
class TestSim9PoisonPayload:
    @staticmethod
    def _plant_poison(dsn, task_id=8001):
        """A row that passes the cabinet backstop but fails validate_v2 (an
        illegal effective new_status is not in the tasks/task-event@1 enum)."""
        conn = HR.connect(dsn)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO officer_tasks_outbox "
                "(idempotency_key, task_id, new_status, actor, cabinet_id, "
                " correlation_id, payload) VALUES "
                "(%s, %s, '__poison__', 'cos', %s, "
                " replace(gen_random_uuid()::text,'-',''), "
                " jsonb_build_object('task_id', %s)) RETURNING id",
                (f"cog1:poison:{task_id}", task_id, CAB_ID, task_id))
            pid = int(cur.fetchone()[0])
        conn.close()
        return pid

    def test_poison_terminal_and_batch_continues(self, cluster, dsn, redis_env):
        pid = self._plant_poison(dsn)             # lower id -> claimed first
        tid, legit = _seed_row(cluster)           # higher id -> after the poison
        counts = relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID, max_attempts=0)
        poison = HR.fetch_row(dsn, pid)
        assert poison["failed_terminal_at"] is not None, "poison -> validation-class terminal"
        assert poison["dispatched_at"] is None
        assert (poison["last_error"] or "") != ""
        # per-row isolation: the healthy row still dispatched
        assert HR.fetch_row(dsn, legit["id"])["dispatched_at"] is not None
        assert counts["dispatched"] == 1 and counts["terminal"] == 1
        assert redis_env.xlen(SHADOW) == 1

    def test_mutant_no_isolation_starves_the_batch(self, cluster, dsn, redis_env,
                                                   monkeypatch):
        pid = self._plant_poison(dsn)
        tid, legit = _seed_row(cluster)
        monkeypatch.setattr(relay, "_safe_process", _unsafe_process)
        with pytest.raises(relay.RelayValidationError):
            relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID, max_attempts=0)
        # the healthy row (claimed after the poison) never dispatched -> starved
        assert HR.fetch_row(dsn, legit["id"])["dispatched_at"] is None


# ===========================================================================
# Sim 10b — relay-side cabinet spoof backstop (terminal) + isolation
# ===========================================================================

@_PG_SKIP
@_REDIS_SKIP
class TestSim10bSpoofBackstop:
    def test_foreign_cabinet_row_terminal_refused(self, cluster, dsn, redis_env):
        fid = HR.insert_foreign_row(dsn, task_id=999, cabinet_id="cog1-evil")
        counts = relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID, max_attempts=0)
        foreign = HR.fetch_row(dsn, fid)
        assert foreign["dispatched_at"] is None, "foreign-cabinet row never dispatched"
        assert foreign["failed_terminal_at"] is not None, "relay backstop terminal-refuses"
        assert "cabinet" in (foreign["last_error"] or "").lower()
        assert counts["terminal"] == 1
        assert redis_env.xlen(SHADOW) == 0

    def test_isolation_legit_row_flows_past_the_spoof(self, cluster, dsn, redis_env):
        fid = HR.insert_foreign_row(dsn, task_id=999, cabinet_id="cog1-evil")
        tid, legit = _seed_row(cluster)
        counts = relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID, max_attempts=0)
        assert HR.fetch_row(dsn, fid)["failed_terminal_at"] is not None
        assert HR.fetch_row(dsn, legit["id"])["dispatched_at"] is not None
        assert counts["dispatched"] == 1 and counts["terminal"] == 1

    def test_mutant_backstop_removed_dispatches_foreign(self, cluster, dsn,
                                                        redis_env, monkeypatch):
        fid = HR.insert_foreign_row(dsn, task_id=999, cabinet_id="cog1-evil")
        monkeypatch.setattr(relay, "_cabinet_backstop", lambda row, host_id: None)
        counts = relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID)
        assert HR.fetch_row(dsn, fid)["dispatched_at"] is not None, \
            "mutant: backstop removed -> foreign row DISPATCHED (detected)"
        assert counts["dispatched"] == 1
