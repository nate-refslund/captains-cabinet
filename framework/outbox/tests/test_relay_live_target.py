"""COG-1 F1 — relay live-stream retarget seam: end-to-end routing rig (§8.4).

Frozen review binding condition (b)
(shared/interfaces/reviews/cognitive-core-phase-1-review.md, F1): pointer=outbox
-> the relay XADDs the sandbox Redis's LIVE stream ``cabinet:tasks:events``
end-to-end; pointer=legacy/absent -> the SHADOW stream only; and a MUTANT proves
the rig DETECTS a shadow-stuck relay (one that ignores the passed target).

Layer law (§8.4): the framework relay NEVER reads the authority pointer file.
The cron WRAPPER (cabinet/cron/outbox-relay.sh) resolves the pointer VALUE and
passes the stream target DOWN. This rig passes ``stream_target`` directly —
exactly what the wrapper does — and SHADOW is the hard default (dark by
construction).

Tests-first (foundry.md:137 — every gate ships a mutant proving it detects its
defect). Written RED before the seam existed (no relay.COG1_LIVE_STREAM_TARGET,
no ``stream_target`` parameter); the red proof is in the build record.

S0 pin PostgreSQL MAJOR 17; interpreter python3.12; the routing sims skip without
a PG17 toolchain + psycopg2 + a redis binary. Run:
  python3.12 -m pytest framework/outbox/tests/test_relay_live_target.py -q
"""
from __future__ import annotations

import importlib.util as _ilu
import inspect
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

_PG_SKIP = pytest.mark.skipif(not HR.pg_available(), reason=HR.PG_SKIP_REASON)
_REDIS_SKIP = pytest.mark.skipif(not HR.redis_available(), reason=HR.REDIS_SKIP_REASON)


# ===========================================================================
# Static seam contract — runs WITHOUT the DB/redis toolchain (the fast red)
# ===========================================================================

def test_live_stream_target_constant_is_the_live_stream():
    # The §8.4 live tasks exhaust AND the landing-marker token the
    # cog1-authority-flip.sh interlock probes for (its presence self-releases
    # the fail-closed cutover interlock).
    assert relay.COG1_LIVE_STREAM_TARGET == "cabinet:tasks:events"
    # distinct from the shadow default — the whole point of the retarget seam.
    assert relay.COG1_LIVE_STREAM_TARGET != relay.SHADOW_STREAM


def test_drain_accepts_stream_target_with_shadow_hard_default():
    sig = inspect.signature(relay.drain_tasks_outbox)
    assert "stream_target" in sig.parameters, \
        "drain_tasks_outbox must accept the stream_target seam parameter"
    assert sig.parameters["stream_target"].default == relay.SHADOW_STREAM, \
        "SHADOW must be the HARD DEFAULT (dark by construction; only the wrapper retargets)"


# ===========================================================================
# Fixtures — one module cluster (base chain + identity + 047); clean per test
# (the test_relay_table_drain.py idiom — each relay file owns its fixtures)
# ===========================================================================

@pytest.fixture(scope="module")
def cluster(tmp_path_factory):
    if not HR.pg_available():
        pytest.skip(HR.PG_SKIP_REASON)
    c = HR.EphemeralPG17(tmp_path_factory.mktemp("cog1live"), cabinet_id=CAB_ID)
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
# The end-to-end routing RIG (§8.4 binding condition b) — the reusable teeth
# ===========================================================================

def _route_to_live_and_assert(dsn, cluster, redis_env):
    """pointer=outbox -> the wrapper resolves the LIVE target and passes it down;
    the relay XADDs the sandbox's ``cabinet:tasks:events`` (NOT the shadow
    stream). Returns the committed event_id. Raises AssertionError (the rig's
    teeth) if the row did not land LIVE — this is what the shadow-stuck mutant
    trips."""
    live = relay.COG1_LIVE_STREAM_TARGET
    shadow = relay.SHADOW_STREAM
    tid, row = _seed_row(cluster)
    counts = relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID, stream_target=live)
    assert counts["dispatched"] == 1, counts
    eid = HR.fetch_row(dsn, row["id"])["event_id"]
    assert eid is not None
    assert redis_env.xlen(live) == 1, \
        "pointer=outbox row did NOT land on the LIVE stream cabinet:tasks:events"
    assert eid in redis_env.raw(live), "committed event_id absent from the LIVE stream"
    assert redis_env.xlen(shadow) == 0, \
        "LIVE-target drain leaked to the shadow stream"
    return eid


@_PG_SKIP
@_REDIS_SKIP
class TestLiveTargetRouting:
    def test_pointer_outbox_lands_on_live_stream_end_to_end(self, cluster, dsn,
                                                            redis_env):
        _route_to_live_and_assert(dsn, cluster, redis_env)

    def test_default_target_stays_shadow_live_dark(self, cluster, dsn, redis_env):
        # The HARD DEFAULT (no stream_target passed) = what the wrapper does for
        # pointer=legacy/absent: shadow ONLY, the live stream stays dark.
        tid, row = _seed_row(cluster)
        counts = relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID)
        assert counts["dispatched"] == 1
        eid = HR.fetch_row(dsn, row["id"])["event_id"]
        assert redis_env.xlen(relay.SHADOW_STREAM) == 1
        assert eid in redis_env.raw(relay.SHADOW_STREAM)
        assert redis_env.xlen(relay.COG1_LIVE_STREAM_TARGET) == 0, \
            "the default drain must stay SHADOW — live is dark until cutover"

    def test_explicit_shadow_target_stays_shadow(self, cluster, dsn, redis_env):
        # What the wrapper passes for pointer=legacy: an EXPLICIT shadow target.
        tid, row = _seed_row(cluster)
        relay.drain_tasks_outbox(dsn, cabinet_id=CAB_ID,
                                 stream_target=relay.SHADOW_STREAM)
        assert redis_env.xlen(relay.SHADOW_STREAM) == 1
        assert redis_env.xlen(relay.COG1_LIVE_STREAM_TARGET) == 0


# ===========================================================================
# Shadow-stuck MUTANT (negative control §8.4 binding condition b) — the rig
# must DETECT a relay that ignores the passed target and stays on shadow
# ===========================================================================

def _resolve_shadow_stuck(stream_target):
    """MUTANT: broken target plumbing — the resolver IGNORES the passed
    stream_target and pins the stream adapter to the SHADOW stream (exactly the
    pre-seam bug F1 names: 'the relay keeps writing only shadow'). The routing
    rig above must detect this."""
    def stuck(fields, *, idempotency_key):
        relay._stream_adapter(fields, idempotency_key=idempotency_key,
                              stream_target=relay.SHADOW_STREAM)
    return stuck


@_PG_SKIP
@_REDIS_SKIP
class TestShadowStuckMutantIsDetected:
    def test_rig_detects_shadow_stuck_relay(self, cluster, dsn, redis_env,
                                            monkeypatch):
        # Break the target plumbing: the resolver now ignores the LIVE target.
        monkeypatch.setattr(relay, "_resolve_stream_adapter", _resolve_shadow_stuck)
        # The rig's LIVE assertion FAILS (its teeth) for the named reason.
        with pytest.raises(AssertionError, match="LIVE stream cabinet:tasks:events"):
            _route_to_live_and_assert(dsn, cluster, redis_env)
        # Prove WHERE the shadow-stuck relay actually wrote: shadow, never live.
        assert redis_env.xlen(relay.SHADOW_STREAM) == 1
        assert redis_env.xlen(relay.COG1_LIVE_STREAM_TARGET) == 0, \
            "shadow-stuck relay must NOT reach the live stream"
