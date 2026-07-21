"""COG-1 W3 — relay-plane test harness (ephemeral Redis + PG helpers).

Plan: docs/plans/cognitive-core-phase-1-contract-2026-07-20.md §6 (relay and
idempotency), §9.1 sims 2-5 / 8 / 10b, §12.2 item 4.

Two throwaway substrates the relay sims drive:

  * the W2 ephemeral PostgreSQL 17 cluster (cabinet/scripts/tests/
    lib_cog1_harness.py::EphemeralPG17) — imported here so the relay drains a
    REAL 047 outbox on a REAL major-17 server (S0 pin: production work store
    is PostgreSQL 17.10, so every harness/CI pin is MAJOR 17 — the plan
    text's "16" is superseded);
  * an ephemeral localhost Redis (the evals-redis-sandbox discipline,
    cabinet/scripts/lib/evals-redis-sandbox.sh — NEVER a live endpoint): a
    random high port, no persistence, a private tmp dir, PING-verified before
    use, and killable mid-drain for the sim-8 transport partition.

psycopg2 is the relay's own driver (the sims connect the same way the drain
does — §9.4 CI adds psycopg2-binary + the postgres:17 service). It is imported
lazily inside the helpers so a driver-less collection never breaks (house
precedent: etl-common.py:20-23, intake.py:229).
"""
from __future__ import annotations

import importlib.util as _ilu
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# Reuse the W2 ephemeral PG17 cluster verbatim (imported by path, the same
# idiom test_cog1_outbox_capture.py uses to load its own harness).
_W2 = REPO_ROOT / "cabinet" / "scripts" / "tests" / "lib_cog1_harness.py"
_spec = _ilu.spec_from_file_location("lib_cog1_harness", _W2)
H = _ilu.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(H)

EphemeralPG17 = H.EphemeralPG17
pg17_bindir = H.pg17_bindir
ci_service_dsn = H.ci_service_dsn

CTX = "cog1"
CAB_ID = "cog1-harness"


# ---------------------------------------------------------------------------
# Availability — the relay sims need BOTH a PG17 toolchain and a Redis binary
# ---------------------------------------------------------------------------

def _redis_server_bin() -> str | None:
    found = shutil.which("redis-server")
    if found:
        return found
    for cand in ("/opt/homebrew/bin/redis-server", "/usr/local/bin/redis-server"):
        if os.path.exists(cand):
            return cand
    return None


def _psycopg2_available() -> bool:
    try:
        import psycopg2  # noqa: F401
        return True
    except Exception:
        return False


def pg_available() -> bool:
    return H.harness_available() and _psycopg2_available()


def redis_available() -> bool:
    return _redis_server_bin() is not None and shutil.which("redis-cli") is not None


PG_SKIP_REASON = (
    "COG-1 relay DB sims need a PostgreSQL 17 toolchain (or COG1_PG_DSN) AND "
    "psycopg2 — " + H.SKIP_REASON
)
REDIS_SKIP_REASON = "no redis-server/redis-cli — COG-1 relay stream sims skip"


# ---------------------------------------------------------------------------
# Ephemeral Redis sandbox (never a live endpoint)
# ---------------------------------------------------------------------------

class RedisSandbox:
    """A throwaway localhost redis-server on a random high port.

    Kept deliberately small: the relay's stream adapter shells `redis-cli`
    (the exact client task_event_emit uses), so the sandbox exposes cli()/
    xlen()/raw() and a kill()/restart() pair for the sim-8 partition. The
    server is spawned with no persistence and a private dir; the same
    EMPTY-start state CI's redis:7 service is in.
    """

    def __init__(self) -> None:
        self.host = "127.0.0.1"
        self.port: int | None = None
        self._proc: subprocess.Popen | None = None
        self._dir: str | None = None
        self._server = _redis_server_bin()

    def start(self) -> "RedisSandbox":
        if not self._server:
            raise RuntimeError(REDIS_SKIP_REASON)
        self._dir = tempfile.mkdtemp(prefix="cog1relay-redis-")
        last = ""
        for _ in range(12):
            port = random.randint(20000, 40000)
            if self._boot(port):
                self.port = port
                return self
            last = f"port {port} failed"
        raise RuntimeError(f"could not start redis sandbox ({last})")

    def _boot(self, port: int) -> bool:
        proc = subprocess.Popen(
            [self._server, "--port", str(port), "--bind", "127.0.0.1",
             "--save", "", "--appendonly", "no", "--dir", self._dir,
             "--logfile", os.path.join(self._dir, "redis.log")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(50):
            if proc.poll() is not None:
                return False  # died on bind (port held) — try another
            r = subprocess.run(
                ["redis-cli", "-h", "127.0.0.1", "-p", str(port), "PING"],
                capture_output=True, text=True)
            if "PONG" in r.stdout:
                self._proc = proc
                return True
            time.sleep(0.1)
        proc.kill()
        proc.wait(timeout=5)
        return False

    def env(self) -> dict[str, str]:
        """REDIS_HOST/REDIS_PORT pointing at THIS sandbox (the relay stream
        adapter + redis-cli read these — house convention)."""
        assert self.port is not None
        return {"REDIS_HOST": self.host, "REDIS_PORT": str(self.port)}

    def cli(self, *args: str) -> subprocess.CompletedProcess:
        assert self.port is not None
        return subprocess.run(
            ["redis-cli", "-h", self.host, "-p", str(self.port), *args],
            capture_output=True, text=True)

    def xlen(self, stream: str) -> int:
        out = self.cli("XLEN", stream).stdout.strip()
        return int(out) if out.isdigit() else 0

    def raw(self, stream: str) -> str:
        """XRANGE stdout — event_ids (26-char ULIDs) appear verbatim in the
        envelope JSON regardless of redis-cli quote-escaping, so substring/
        count assertions over this blob are robust."""
        return self.cli("XRANGE", stream, "-", "+").stdout

    def event_ids(self, stream: str) -> list[str]:
        return re.findall(r"[0-9A-HJKMNP-TV-Z]{26}", self.raw(stream))

    def kill(self) -> None:
        """Partition: stop the server, KEEP the dir (restart re-binds)."""
        if self._proc and self._proc.poll() is None:
            self._proc.kill()
            self._proc.wait(timeout=5)
        self._proc = None

    def restart(self) -> None:
        assert self.port is not None and self._dir is not None
        if self._proc and self._proc.poll() is None:
            return
        assert self._boot(self.port), "redis sandbox failed to restart"

    def stop(self) -> None:
        self.kill()
        if self._dir:
            shutil.rmtree(self._dir, ignore_errors=True)
            self._dir = None

    def __enter__(self) -> "RedisSandbox":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()


# ---------------------------------------------------------------------------
# psycopg2 query helpers (the relay's own driver — sims read/perturb rows)
# ---------------------------------------------------------------------------

def connect(dsn: str):
    import psycopg2
    import psycopg2.extras  # noqa: F401
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    return conn


def _dict_cur(conn):
    import psycopg2.extras
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def fetch_row(dsn: str, row_id: int) -> dict:
    conn = connect(dsn)
    try:
        with _dict_cur(conn) as cur:
            cur.execute("SELECT * FROM officer_tasks_outbox WHERE id = %s", (row_id,))
            r = cur.fetchone()
            return dict(r) if r else {}
    finally:
        conn.close()


def rows_for_task(dsn: str, task_id: int) -> list[dict]:
    conn = connect(dsn)
    try:
        with _dict_cur(conn) as cur:
            cur.execute(
                "SELECT * FROM officer_tasks_outbox WHERE task_id = %s ORDER BY id",
                (task_id,))
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def pending_count(dsn: str) -> int:
    conn = connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM officer_tasks_outbox "
                        "WHERE dispatched_at IS NULL AND failed_terminal_at IS NULL")
            return int(cur.fetchone()[0])
    finally:
        conn.close()


def age_claims(dsn: str, *, seconds: int = 3600) -> None:
    """Simulate a long-dead relay: push claimed_at past any claim-TTL so a
    fresh drain re-claims via the TTL branch (the correct code does; the
    no-TTL mutant does not — that is the sim-3 detection)."""
    conn = connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE officer_tasks_outbox SET claimed_at = NOW() - %s * INTERVAL '1 second' "
                "WHERE claimed_at IS NOT NULL AND dispatched_at IS NULL "
                "AND failed_terminal_at IS NULL", (seconds,))
    finally:
        conn.close()


def reset_dispatch(dsn: str, row_id: int) -> None:
    """Force a redelivery of an already-dispatched row (sim 5 duplicate):
    clear the dispatch/claim bookkeeping but LEAVE event_id (committed) so the
    stable-id reuse can be proven."""
    conn = connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE officer_tasks_outbox "
                        "SET dispatched_at = NULL, claimed_at = NULL WHERE id = %s",
                        (row_id,))
    finally:
        conn.close()


def insert_foreign_row(dsn: str, *, task_id: int, cabinet_id: str,
                       new_status: str = "wip") -> int:
    """Hand-INSERT a foreign-cabinet_id row (sim 10b rig (b)) — bypasses the
    capture trigger to plant exactly the cross-database misconfiguration the
    relay dispatch backstop must terminal-refuse."""
    conn = connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO officer_tasks_outbox "
                "(idempotency_key, task_id, new_status, actor, cabinet_id, "
                " correlation_id, payload) "
                "VALUES (%s, %s, %s, 'harness-direct', %s, "
                " replace(gen_random_uuid()::text, '-', ''), "
                " jsonb_build_object('task_id', %s, 'new_status', %s, "
                "                    'actor', 'harness-direct')) "
                "RETURNING id",
                (f"cog1:foreign:{task_id}:{new_status}", task_id, new_status,
                 cabinet_id, task_id, new_status))
            return int(cur.fetchone()[0])
    finally:
        conn.close()


def seed_transition(pg, verb: str, officer: str, task_id: int | None = None,
                    *, title: str = "relay-sim", reason: str = "blocked reason") -> int:
    """Drive a real my-tasks-shaped verb through the W2 rig so the capture
    trigger mints a genuine outbox row. Returns the task id."""
    if verb == "start":
        r = pg.verb_start(officer, title, CTX)
    elif verb == "queue":
        r = pg.verb_queue(officer, title, CTX)
    elif verb == "block":
        r = pg.verb_block(officer, task_id, reason)
    elif verb == "unblock":
        r = pg.verb_unblock(officer, task_id)
    elif verb == "done":
        r = pg.verb_done(officer, task_id)
    elif verb == "cancel":
        r = pg.verb_cancel(officer, task_id)
    else:
        raise ValueError(f"unknown verb {verb!r}")
    rows = pg.returned_rows(r)
    assert rows, f"seed {verb} failed: {r.stdout}\n{r.stderr}"
    return int(rows[0].split("|")[0])
