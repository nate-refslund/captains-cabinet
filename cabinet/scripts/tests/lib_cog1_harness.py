"""COG-1 W2 — ephemeral PostgreSQL 17 harness for the officer_tasks outbox pilot.

Plan: docs/plans/cognitive-core-phase-1-contract-2026-07-20.md §5.3 (harness
spec), §9.1 (kill-injection rigs), §11.2 (B1/B2 baselines).

S0 GROUND PIN (2026-07-20, supersedes plan-text "postgres 16" mentions): the
production work store runs PostgreSQL 17.10, so every harness/CI pin here is
MAJOR 17 — local discovery targets /opt/homebrew/opt/postgresql@17/bin (plus
the Linux keg paths CI/land-battery boxes use), and a discovered toolchain or
service that is not major 17 is treated as ABSENT (skip, never silently run a
different major). Recorded per the 2026-07-07 full-autonomy grant.

Isolation discipline (the 1,969-row fixture-leak lesson, emitter.py:334-353,
and the evals-redis-sandbox precedent):
  * initdb-in-scratch-dir, unix-socket-only (listen_addresses=''), socket dir
    under a SHORT /tmp prefix (103-char sockaddr limit), trust auth on the
    throwaway cluster only, fsync=off, max_connections raised for sim 6a.
  * connection plumbing is BUILT here from the scratch socket path — it can
    NEVER resolve the live NEON_CONNECTION_STRING / DATABASE_URL: child
    process environments are constructed from an EMPTY dict (never
    os.environ.copy()) with a reduced PATH, and the fence test in
    test_cog1_outbox_capture.py asserts a live-var canary cannot leak into
    either the env or the DSN.
  * provision-local-postgres.sh is deliberately NOT reused: it early-exits
    when NEON_CONNECTION_STRING is already set and applies zero DDL
    (plan §5.3 names both reasons).

DDL chain applied (house NON-numeric load-preset order, load-preset.sh):
    038 -> 041 -> 039 -> 042 -> identity GUC -> 047
047 carries its own CREATE EXTENSION pgcrypto line, so 045 is not needed
(plan §5.3); pgcrypto 1.3 is present in production, making that line a no-op
there (S0).

CI mode: when COG1_PG_DSN is set (the future cabinet-ci.yml postgres:17
service — §9.4, its own commit/wave), the harness creates a scratch database
on that server instead of initdb'ing. The env name is harness-OWN by design;
the harness never reads the live store variables.
"""
from __future__ import annotations

import math
import os
import re
import secrets
import shutil
import signal
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# The explicit DDL chain (plan §5.3) — house non-numeric order.
BASE_DDL_CHAIN = (
    "cabinet/sql/038-officer-tasks.sql",
    "cabinet/sql/041-tasks-due-at.sql",
    "cabinet/sql/039-linear-to-tasks-schema.sql",
    "cabinet/sql/042-tasks-reminder-kind.sql",
)
DDL_047 = "cabinet/sql/047-officer-tasks-outbox.sql"

# Env vars that must NEVER reach harness children (live stores / live redis).
FORBIDDEN_CHILD_ENV = (
    "NEON_CONNECTION_STRING",
    "DATABASE_URL",
    "REDIS_URL",
    "REDIS_HOST",
    "REDIS_PORT",
    "PGHOST",
    "PGPORT",
    "PGDATABASE",
    "PGUSER",
    "PGPASSWORD",
    "PGSERVICE",
    "PGSERVICEFILE",
    "PGPASSFILE",
)

_IDENTITY_RE = re.compile(r"\A[A-Za-z0-9_.-]{1,64}\Z")


# ---------------------------------------------------------------------------
# Toolchain discovery — MAJOR 17 pinned (S0)
# ---------------------------------------------------------------------------

def pg17_bindir() -> Path | None:
    """Dir holding a full major-17 server toolchain, or None (=> skip).

    Mirrors test_captain_reminder_arm.py's _pg_toolchain() house pattern but
    pins major 17 per the S0 ground finding (production = 17.10). Order:
    COG1_PG17_BINDIR env override, then the Homebrew/Linux keg paths, then
    PATH — and every candidate must (a) carry postgres/initdb/pg_ctl/psql and
    (b) report major version 17.
    """
    cands: list[str] = []
    env_override = os.environ.get("COG1_PG17_BINDIR")
    if env_override:
        cands.append(env_override)
    cands += [
        "/opt/homebrew/opt/postgresql@17/bin",
        "/usr/local/opt/postgresql@17/bin",
        "/usr/lib/postgresql/17/bin",
        "/usr/pgsql-17/bin",
    ]
    on_path = shutil.which("postgres")
    if on_path:
        cands.append(str(Path(on_path).parent))
    seen: set[str] = set()
    for d in cands:
        if not d or d in seen:
            continue
        seen.add(d)
        p = Path(d)
        if not all((p / t).exists() for t in ("postgres", "initdb", "pg_ctl", "psql")):
            continue
        try:
            out = subprocess.run(
                [str(p / "postgres"), "--version"],
                capture_output=True, text=True, timeout=10,
            ).stdout
        except (OSError, subprocess.TimeoutExpired):
            continue
        m = re.search(r"\(PostgreSQL\)\s+(\d+)", out)
        if m and m.group(1) == "17":
            return p
    return None


def ci_service_dsn() -> str | None:
    """The CI postgres:17 service conninfo, when provided (COG1_PG_DSN)."""
    dsn = os.environ.get("COG1_PG_DSN", "").strip()
    return dsn or None


def harness_available() -> bool:
    return pg17_bindir() is not None or ci_service_dsn() is not None


SKIP_REASON = (
    "no PostgreSQL 17 toolchain (COG1_PG17_BINDIR / postgresql@17 keg) and no "
    "COG1_PG_DSN service — COG-1 DB-plane sims skip (S0 pins major 17)"
)


# ---------------------------------------------------------------------------
# Percentiles (nearest-rank; used for the §11.2 B1/B2 bound)
# ---------------------------------------------------------------------------

def pctl(values, p: float) -> float:
    s = sorted(values)
    if not s:
        raise ValueError("no samples")
    k = max(0, math.ceil((p / 100.0) * len(s)) - 1)
    return s[k]


# ---------------------------------------------------------------------------
# The ephemeral cluster
# ---------------------------------------------------------------------------

class EphemeralPG17:
    """One throwaway PostgreSQL 17 database, staged DDL, psql-subprocess API.

    Staged on purpose (never auto-applied): sims need pre-047 and
    pre-identity states (§11.2 baselines, sim 10a unset arm)::

        pg = EphemeralPG17(scratch_dir)
        pg.start()
        pg.apply_base_chain()          # 038 -> 041 -> 039 -> 042
        pg.apply_identity_guc("...")   # ALTER DATABASE ... SET app.cabinet_id
        pg.apply_047()
        ...
        pg.stop()

    psql subprocesses are the only client (the kill rigs spawn and kill psql;
    no psycopg2 — user-site deps vanish under hermetic HOME).
    """

    DBNAME = "cog1"

    def __init__(self, scratch: Path, *, cabinet_id: str = "cog1-harness"):
        self.scratch = Path(scratch)
        self.cabinet_id = cabinet_id
        self.bindir = pg17_bindir()
        self._ci_dsn = ci_service_dsn()
        self.pgdata = self.scratch / "pgdata"
        self.scratch_home = self.scratch / "home"
        self.logfile = self.scratch / "server.log"
        # 103-char unix sockaddr limit — short dir directly under /tmp.
        self.sockdir: Path | None = None
        self._started = False
        self._ci_db: str | None = None

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self.scratch_home.mkdir(parents=True, exist_ok=True)
        (self.scratch / "tmp").mkdir(parents=True, exist_ok=True)
        if self._ci_dsn:
            self._start_ci()
            return
        if self.bindir is None:
            raise RuntimeError(SKIP_REASON)
        self.sockdir = Path(tempfile.mkdtemp(prefix="cog1pg", dir="/tmp"))
        subprocess.run(
            [self._b("initdb"), "-D", str(self.pgdata), "-U", "postgres",
             "--auth=trust", "-E", "UTF8", "-N"],
            check=True, capture_output=True, text=True, env=self.child_env(),
        )
        # -l logfile + DEVNULL: the daemon must never inherit a captured pipe
        # (house lesson — a held pipe hangs subprocess.run forever).
        subprocess.run(
            [self._b("pg_ctl"), "-D", str(self.pgdata), "-l", str(self.logfile),
             "-w", "-t", "60", "-o",
             f"-c listen_addresses='' -c unix_socket_directories={self.sockdir} "
             f"-c fsync=off -c max_connections=250", "start"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=self.child_env(),
        )
        self._started = True
        self.psql("CREATE DATABASE " + self.DBNAME + ";", dbname="postgres")
        ver = self.one("SHOW server_version_num;")
        if not (170000 <= int(ver) < 180000):
            raise RuntimeError(f"ephemeral server is not major 17: {ver}")

    def _start_ci(self) -> None:
        self._ci_db = f"cog1_{secrets.token_hex(4)}"
        r = self._psql_raw("SELECT current_setting('server_version_num');",
                           conninfo=self._ci_dsn)
        ver = int(r.stdout.strip().splitlines()[-1])
        if not (170000 <= ver < 180000):
            raise RuntimeError(f"COG1_PG_DSN server is not major 17: {ver}")
        self._psql_raw(f'CREATE DATABASE "{self._ci_db}";', conninfo=self._ci_dsn)
        self._started = True

    def stop(self) -> None:
        if not self._started:
            if self.sockdir:
                shutil.rmtree(self.sockdir, ignore_errors=True)
            return
        if self._ci_dsn:
            self._psql_raw(
                f'DROP DATABASE IF EXISTS "{self._ci_db}" WITH (FORCE);',
                conninfo=self._ci_dsn, check=False)
            self._started = False
            return
        subprocess.run(
            [self._b("pg_ctl"), "-D", str(self.pgdata), "-w", "-t", "30",
             "stop", "-m", "immediate"],
            capture_output=True, env=self.child_env(),
        )
        self._started = False
        if self.sockdir:
            shutil.rmtree(self.sockdir, ignore_errors=True)

    def __enter__(self) -> "EphemeralPG17":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    # -- connection plumbing (scratch-only by construction) ----------------

    def _b(self, tool: str) -> str:
        if self.bindir is None:
            raise RuntimeError(SKIP_REASON)
        return str(self.bindir / tool)

    def _psql_bin(self) -> str:
        if self.bindir is not None:
            return self._b("psql")
        found = shutil.which("psql")
        if not found:
            raise RuntimeError("psql not found for COG1_PG_DSN mode")
        return found

    def conninfo(self, dbname: str | None = None, *, appname: str | None = None) -> str:
        """A libpq conninfo string targeting THIS scratch cluster only."""
        db = dbname or (self._ci_db if self._ci_dsn else self.DBNAME)
        if self._ci_dsn:
            parts = [self._ci_dsn, f"dbname={db}"]  # later keys override
        else:
            if self.sockdir is None:
                raise RuntimeError("cluster not started")
            parts = [f"host={self.sockdir}", f"dbname={db}", "user=postgres"]
        if appname:
            parts.append(f"application_name={appname}")
        return " ".join(parts)

    def child_env(self, **extra: str) -> dict[str, str]:
        """A from-scratch child environment. NEVER os.environ.copy().

        By construction it cannot carry the live store/redis variables
        (FORBIDDEN_CHILD_ENV); PATH is the pg17 bindir plus the base system
        dirs only (no /opt/homebrew/bin — so redis-cli stays unresolvable and
        my-tasks.sh's emit path degrades to its fast documented WARN + no-op).
        """
        path = "/usr/bin:/bin"
        if self.bindir is not None:
            path = f"{self.bindir}:{path}"
        env = {
            "PATH": path,
            "HOME": str(self.scratch_home),
            "TMPDIR": str(self.scratch / "tmp"),
            "LC_ALL": "C",
        }
        env.update(extra)
        # Invariant: a forbidden key can appear ONLY as a deliberate scratch
        # injection via `extra` (e.g. my_tasks_env's scratch conninfo) —
        # never inherited, because this dict never touches os.environ.
        for k in FORBIDDEN_CHILD_ENV:
            if k in env and k not in extra:
                raise AssertionError(f"forbidden env leaked into child env: {k}")
        return env

    # -- SQL runners -------------------------------------------------------

    def _psql_raw(self, sql: str, *, conninfo: str, vars: dict | None = None,
                  check: bool = True, timeout: float = 120.0,
                  env: dict | None = None) -> subprocess.CompletedProcess:
        args = [self._psql_bin(), conninfo, "-X", "-q", "-tA",
                "-v", "ON_ERROR_STOP=1"]
        for k, v in (vars or {}).items():
            args += ["-v", f"{k}={v}"]
        r = subprocess.run(args, input=sql, capture_output=True, text=True,
                           timeout=timeout, env=env or self.child_env())
        if check and r.returncode != 0:
            raise AssertionError(
                f"psql rc={r.returncode}\nSTDERR:\n{r.stderr}\n--SQL--\n{sql}")
        return r

    def psql(self, sql: str, *, vars: dict | None = None, check: bool = True,
             dbname: str | None = None, appname: str | None = None,
             timeout: float = 120.0) -> subprocess.CompletedProcess:
        return self._psql_raw(sql, conninfo=self.conninfo(dbname, appname=appname),
                              vars=vars, check=check, timeout=timeout)

    def one(self, sql: str, **kw) -> str:
        """First line of -tA output (single-value convenience)."""
        out = self.psql(sql, **kw).stdout.strip()
        return out.splitlines()[0] if out else ""

    def count(self, table: str, where: str = "") -> int:
        w = f" WHERE {where}" if where else ""
        return int(self.one(f"SELECT count(*) FROM {table}{w};"))

    def apply_sql_file(self, rel_path: str, *, strict: bool = True,
                       single_txn: bool = False) -> None:
        path = REPO_ROOT / rel_path
        if not path.exists():
            raise AssertionError(f"DDL file missing: {path}")
        args = [self._psql_bin(), self.conninfo(), "-X", "-q"]
        if strict:
            args += ["-v", "ON_ERROR_STOP=1"]
        if single_txn:
            args += ["-1"]
        args += ["-f", str(path)]
        r = subprocess.run(args, capture_output=True, text=True, timeout=120,
                           env=self.child_env())
        if r.returncode != 0:
            raise AssertionError(
                f"apply {rel_path} rc={r.returncode}\nSTDERR:\n{r.stderr}")

    # -- staged DDL --------------------------------------------------------

    def apply_base_chain(self) -> None:
        # PG17 ground finding (harness RED run, 2026-07-20): 038's
        # officer_tasks_status_check re-add DO block compares
        # pg_get_constraintdef() against a PG16-era exact string; PG17
        # deparses with double parens + ::text casts, so the guard misses and
        # the ADD collides with the CREATE-TABLE-minted constraint. In
        # production this is MASKED by load-preset.sh's fail-soft psql (no
        # ON_ERROR_STOP: psql continues past the statement, rc stays 0, the
        # rest of 038 lands). The harness mirrors that shipped apply posture
        # for 038 ONLY, then VERIFIES the load-bearing objects explicitly —
        # strict for every later file. (Fixing 038's guard is outside the W2
        # file-set; reported as a finding.)
        self.apply_sql_file(BASE_DDL_CHAIN[0], strict=False)
        self._verify_038_objects()
        for rel in BASE_DDL_CHAIN[1:]:
            self.apply_sql_file(rel)

    def _verify_038_objects(self) -> None:
        checks = {
            "officer_tasks": "SELECT to_regclass('officer_tasks') IS NOT NULL;",
            "officer_task_history":
                "SELECT to_regclass('officer_task_history') IS NOT NULL;",
            "trg_enforce_officer_wip":
                "SELECT EXISTS (SELECT 1 FROM pg_trigger "
                "WHERE tgname = 'trg_enforce_officer_wip');",
            "trg_log_officer_task_transition":
                "SELECT EXISTS (SELECT 1 FROM pg_trigger "
                "WHERE tgname = 'trg_log_officer_task_transition');",
            "trg_bump_officer_tasks_updated":
                "SELECT EXISTS (SELECT 1 FROM pg_trigger "
                "WHERE tgname = 'trg_bump_officer_tasks_updated');",
        }
        for name, sql in checks.items():
            assert self.one(sql) == "t", f"038 object missing after apply: {name}"

    def apply_identity_guc(self, value: str | None = None) -> None:
        """The §5.2 identity step: ALTER DATABASE ... SET app.cabinet_id.

        Same mechanism load-preset.sh deploys (DB-level GUC — survives
        pooling; applies at backend start, and every harness psql call is a
        fresh backend). Value is allowlist-validated BEFORE interpolation and
        quoted server-side via format(%I/%L).
        """
        v = value if value is not None else self.cabinet_id
        if not _IDENTITY_RE.match(v):
            raise ValueError(f"unsafe cabinet id for harness: {v!r}")
        self.psql(
            "DO $cog1id$ BEGIN "
            "EXECUTE format('ALTER DATABASE %I SET app.cabinet_id = %L', "
            f"current_database(), '{v}'); "
            "END $cog1id$;")

    def apply_047(self) -> None:
        # single_txn mirrors load-preset.sh's production apply mode
        # (`-v ON_ERROR_STOP=1 -1`): all-or-nothing, so a statement failure
        # can never leave a partial 047 (the capture trigger is
        # live-in-transaction from apply, §5.1). The green suite is the
        # evidence that 047 applies clean in EXACTLY that mode on PG17.
        self.apply_sql_file(DDL_047, single_txn=True)

    # -- verb rigs (my-tasks.sh SQL text, psql -v binds) -------------------
    #
    # The SQL below is the shipped my-tasks.sh transaction text (BEGIN;
    # set_config('app.cabinet_officer', ...); UPDATE ... FROM self-join ...
    # RETURNING; COMMIT) so the WHERE-guard refusal paths under contention are
    # the production ones. `extra_pre` injects SET LOCAL lines right after
    # BEGIN (suppression / spoof rigs). `set_officer=False` drops the officer
    # GUC line (the COALESCE 'unknown' rig).

    _SET_OFFICER = "SELECT set_config('app.cabinet_officer', :'slug', true);\n"

    def _verb(self, body: str, vars: dict, *, set_officer: bool = True,
              extra_pre: list[str] | None = None, check: bool = True,
              appname: str | None = None) -> subprocess.CompletedProcess:
        sql = "BEGIN;\n"
        if set_officer:
            sql += self._SET_OFFICER
        for line in (extra_pre or []):
            sql += line.rstrip() + "\n"
        sql += body
        sql += "COMMIT;\n"
        return self.psql(sql, vars=vars, check=check, appname=appname)

    def verb_queue(self, officer: str, title: str, ctx: str, **kw):
        body = (
            "INSERT INTO officer_tasks (officer_slug, title, status, "
            "linked_url, linked_kind, linked_id, context_slug)\n"
            "VALUES (:'slug', :'title', 'queue', NULLIF(:'lurl',''), "
            "NULLIF(:'lkind','')::text, NULLIF(:'lid',''), NULLIF(:'ctx','')) "
            "RETURNING id, title;\n")
        return self._verb(body, {"slug": officer, "title": title, "ctx": ctx,
                                 "lurl": "", "lkind": "", "lid": ""}, **kw)

    def verb_start(self, officer: str, title: str, ctx: str, **kw):
        body = (
            "INSERT INTO officer_tasks (officer_slug, title, status, "
            "linked_url, linked_kind, linked_id, started_at, context_slug)\n"
            "VALUES (:'slug', :'title', 'wip', NULLIF(:'lurl',''), "
            "NULLIF(:'lkind',''), NULLIF(:'lid',''), NOW(), NULLIF(:'ctx','')) "
            "RETURNING id, title;\n")
        return self._verb(body, {"slug": officer, "title": title, "ctx": ctx,
                                 "lurl": "", "lkind": "", "lid": ""}, **kw)

    def verb_done(self, officer: str, task_id: int, **kw):
        body = (
            "UPDATE officer_tasks t\n"
            "   SET status = 'done', completed_at = NOW(), blocked = false, "
            "blocked_reason = NULL\n"
            "  FROM officer_tasks o\n"
            " WHERE o.id = t.id\n"
            "   AND t.id = :'id'::bigint\n"
            "   AND t.officer_slug = :'slug'\n"
            "   AND t.status = 'wip'\n"
            "RETURNING t.id, o.status, o.blocked, t.title;\n")
        return self._verb(body, {"slug": officer, "id": str(task_id)}, **kw)

    def verb_cancel(self, officer: str, task_id: int, **kw):
        body = (
            "UPDATE officer_tasks t\n"
            "   SET status = 'cancelled', blocked = false, blocked_reason = NULL\n"
            "  FROM officer_tasks o\n"
            " WHERE o.id = t.id\n"
            "   AND t.id = :'id'::bigint\n"
            "   AND t.officer_slug = :'slug'\n"
            "   AND t.status NOT IN ('done','cancelled')\n"
            "RETURNING t.id, o.status, o.blocked, t.title;\n")
        return self._verb(body, {"slug": officer, "id": str(task_id)}, **kw)

    def verb_block(self, officer: str, task_id: int, reason: str, **kw):
        body = (
            "UPDATE officer_tasks t\n"
            "   SET blocked = true, blocked_reason = :'reason'\n"
            "  FROM officer_tasks o\n"
            " WHERE o.id = t.id\n"
            "   AND t.id = :'id'::bigint\n"
            "   AND t.officer_slug = :'slug'\n"
            "   AND t.status IN ('queue', 'wip')\n"
            "RETURNING t.id, o.status, o.blocked, t.title;\n")
        return self._verb(body, {"slug": officer, "id": str(task_id),
                                 "reason": reason}, **kw)

    def verb_unblock(self, officer: str, task_id: int, **kw):
        body = (
            "UPDATE officer_tasks t\n"
            "   SET blocked = false, blocked_reason = NULL\n"
            "  FROM officer_tasks o\n"
            " WHERE o.id = t.id\n"
            "   AND t.id = :'id'::bigint\n"
            "   AND t.officer_slug = :'slug'\n"
            "   AND t.status IN ('queue', 'wip')\n"
            "RETURNING t.id, o.status, o.blocked, t.title;\n")
        return self._verb(body, {"slug": officer, "id": str(task_id)}, **kw)

    # -- dashboard-lib verb rig (sim 6a cross-stack mix) -------------------
    #
    # tasks.ts cannot run under plain node in this tree (extensionless TS
    # imports, no tsx, node_modules not installed — same constraint as B2),
    # so the sim-6a dashboard half replays the lib's EXACT doneTask
    # transaction shape (tasks.ts:405-445) via psql WITH the lib's
    # rowcount-abort semantics emulated: tasks.ts:422-425 ROLLBACKs and
    # throws when the FOR UPDATE pre-check returns zero rows — the psql
    # replay must do the same (\gset + \if), never blind-update past a
    # zero-row pre-check. The count(*) wrapper takes the SAME row locks as
    # the lib's top-level FOR UPDATE and always returns exactly one row, so
    # \gset cannot error under ON_ERROR_STOP.

    DASH_WIN = "COG1_DASH_WIN"
    DASH_REFUSED = "COG1_DASH_REFUSED"

    def verb_dash_done(self, task_id: int, officer: str, *,
                       actor: str = "api", check: bool = True,
                       appname: str | None = None) -> subprocess.CompletedProcess:
        """Dashboard doneTask: pre-check lock -> rowcount-abort -> UPDATE."""
        sql = (
            "BEGIN;\n"
            "SELECT set_config('app.cabinet_officer', :'actor', true);\n"
            "SELECT (count(*) > 0) AS cog1_dash_hit FROM (\n"
            "  SELECT id, officer_slug FROM officer_tasks\n"
            "   WHERE id = :'id'::bigint AND officer_slug = :'slug'\n"
            "     AND status = 'wip' FOR UPDATE) cog1_pre \\gset\n"
            "\\if :cog1_dash_hit\n"
            "UPDATE officer_tasks\n"
            "   SET status = 'done', completed_at = NOW(), blocked = false, "
            "blocked_reason = NULL\n"
            "   WHERE id = :'id'::bigint\n"
            " RETURNING *;\n"
            "COMMIT;\n"
            f"\\echo {self.DASH_WIN}\n"
            "\\else\n"
            "ROLLBACK;\n"
            f"\\echo {self.DASH_REFUSED}\n"
            "\\endif\n"
        )
        return self.psql(sql, vars={"actor": actor, "slug": officer,
                                    "id": str(task_id)},
                         check=check, appname=appname)

    @staticmethod
    def returned_rows(proc: subprocess.CompletedProcess) -> list[str]:
        """RETURNING data lines (`^<digits>|`) — the my-tasks.sh anchor."""
        return [l for l in proc.stdout.splitlines() if re.match(r"^\d+\|", l)]

    # -- kill injection (sim 1) --------------------------------------------

    def open_txn_and_kill(self, statements: str, *, appname: str,
                          timeout: float = 15.0) -> None:
        """Open BEGIN + statements on a psql, confirm the txn is open server-
        side (pg_stat_activity by application_name), SIGKILL the client, and
        wait until the backend is gone (server rolls the txn back)."""
        proc = subprocess.Popen(
            [self._psql_bin(), self.conninfo(appname=appname), "-X", "-q",
             "-v", "ON_ERROR_STOP=1"],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, text=True, env=self.child_env(),
        )
        assert proc.stdin is not None
        proc.stdin.write("BEGIN;\n" + statements.rstrip() + "\n")
        proc.stdin.flush()
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                n = self.one(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE application_name = :'a' "
                    "AND state = 'idle in transaction';",
                    vars={"a": appname})
                if n == "1":
                    break
                time.sleep(0.05)
            else:
                raise AssertionError(
                    f"victim txn never reached idle-in-transaction ({appname})")
        finally:
            proc.send_signal(signal.SIGKILL)
            proc.wait(timeout=10)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            n = self.one(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE application_name = :'a';", vars={"a": appname})
            if n == "0":
                return
            time.sleep(0.05)
        raise AssertionError(f"victim backend lingered after SIGKILL ({appname})")

    # -- concurrency -------------------------------------------------------

    def run_concurrent(self, jobs, workers: int = 100):
        """jobs = list of zero-arg callables returning CompletedProcess."""
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(j) for j in jobs]
            return [f.result() for f in futs]

    # -- my-tasks.sh runner (B1 — real shipped script) ---------------------

    def make_scratch_cabinet_root(self, ctx: str) -> Path:
        root = self.scratch / "cabroot"
        (root / "instance" / "config" / "contexts").mkdir(parents=True,
                                                          exist_ok=True)
        (root / "instance" / "config" / "contexts" / f"{ctx}.yml").write_text(
            f"slug: {ctx}\nname: COG1 harness context\n")
        return root

    def my_tasks_env(self, *, officer: str, cabinet_root: Path) -> dict[str, str]:
        """Env for the real my-tasks.sh: the ONLY connection value present is
        this scratch cluster's conninfo (the §11.2 env seam — scratch value
        only, never the live string). Reduced PATH keeps redis-cli
        unresolvable, so emit_event/broadcast degrade to their documented
        fast no-op WARN paths post-commit."""
        return self.child_env(
            NEON_CONNECTION_STRING=self.conninfo(),
            CABINET_ROOT=str(cabinet_root),
            CABINET_OFFICER=officer,
        )

    def run_my_tasks(self, argv: list[str], *, officer: str, ctx: str,
                     cabinet_root: Path, timeout: float = 60.0,
                     ) -> subprocess.CompletedProcess:
        cmd = ["/bin/bash", str(REPO_ROOT / "cabinet" / "scripts" / "my-tasks.sh"),
               *argv, "--context", ctx]
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            env=self.my_tasks_env(officer=officer, cabinet_root=cabinet_root),
            cwd=str(self.scratch),
        )
