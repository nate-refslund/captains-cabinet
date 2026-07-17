"""Spec 041 due-at reminder tick — the worker + its fleet-manifest clock.

The schema (cabinet/sql/041-tasks-due-at.sql) and worker
(cabinet/scripts/due-at-reminder-tick.sh) shipped, but the worker was
SCHEDULED NOWHERE (its header still carried a convergence-era /opt crontab
suggestion) and it sourced lib/triggers.sh from a /opt path that does not
exist on the Mac box — so trigger_send was undefined and every fire silently
failed. This test pins the repair on BOTH layers:

STRUCTURAL (no DB / no redis):
  * the cabinet/services.yml row exists, kind cron, interval_s 300, a SINGLE
    command (the generated-plist wrapper ``exec``s the command, so a ``&&``
    chain would die at the first program — pinned fleet-wide by
    test_no_enabled_service_chains_past_the_exec_wrapper);
  * generate-plists.render() wraps it as ``... && source cabinet/.env ... &&
    exec <command>`` — the .env source is what feeds NEON_CONNECTION_STRING to
    the worker under launchd, and nothing trails the exec'd command;
  * the worker carries no ``/opt/founders-cabinet`` string anywhere and sources
    the trigger lib SCRIPT-relative (code beside code; a CABINET_ROOT override
    only relocates the runtime root).

BEHAVIORAL (fake-bin PATH shim — mirrors test_backup_freshness.py /
test_triggers_stream_durability.py; the REAL lib/triggers.sh runs, psql +
redis-cli + tmux are stubbed):
  * idempotency — the atomic claim marks reminder_fired_at, so a re-run after a
    fire produces ZERO new triggers (a quiet re-run only heartbeats);
  * re-arm — clearing reminder_fired_at (what the 041 re-arm trigger does on a
    due_at bump) refires the row;
  * injection — a task title carrying quotes / semicolons / ``$( )`` /
    backticks / backslashes survives BYTE-FOR-BYTE as DATA through the jq
    payload and the trigger_send XADD message (valid JSON, title unchanged,
    the ``$(touch …)`` side effect never runs).

Run: python3.12 -m pytest cabinet/scripts/tests/test_due_at_reminder_tick.py -q
"""
from __future__ import annotations

import importlib.util as _ilu
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

# A sibling test patches the global subprocess.Popen and the patch can leak
# across modules in a whole-repo run — restore the real one around our spawns
# (same guard as test_retrieval_eval.py / test_bootstrap_memory_chain.py).
_REAL_POPEN = subprocess.Popen

_REPO = Path(__file__).resolve().parents[3]
SCRIPT = _REPO / "cabinet" / "scripts" / "due-at-reminder-tick.sh"
TRIGGERS_LIB = _REPO / "cabinet" / "scripts" / "lib" / "triggers.sh"


def _load(name: str, fname: str):
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    spec = _ilu.spec_from_file_location(
        name, _REPO / "cabinet" / "scripts" / fname)
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _services():
    return yaml.safe_load((_REPO / "cabinet" / "services.yml").read_text())["services"]


def _row():
    rows = [s for s in _services() if s.get("name") == "due-at-reminder-tick"]
    assert len(rows) == 1, "due-at-reminder-tick row missing — worker unscheduled again"
    return rows[0]


# ---------------------------------------------------------------------------
# STRUCTURAL — the row + the render + the source-path fix
# ---------------------------------------------------------------------------

def test_row_is_a_single_command_cron_at_300s():
    r = _row()
    assert r["label"] == "com.cabinet.due-at-reminder-tick"
    assert r["kind"] == "cron"
    assert r["command"] == "bash cabinet/scripts/due-at-reminder-tick.sh"
    assert r["schedule"] == {"interval_s": 300}
    assert not r.get("disabled")
    # ONE command per row — the exec wrapper kills a && tail (paid 2026-07-15).
    assert "&&" not in r["command"]
    # the notes must tell the whole story
    assert "Spec 041" in r["notes"]
    assert "exec" in r["notes"] and "&&" in r["notes"]


def test_render_execs_the_single_command_and_sources_env():
    """Render-level pin through the REAL generate-plists.render(): the wrapper
    must SOURCE cabinet/.env (how the conn string reaches the worker under
    launchd) and END with ``exec <command>`` — nothing may trail the exec'd
    command (a ``&& second-prog`` tail is the silent-dead-organ bug)."""
    gp = _load("generate_plists", "generate-plists.py")
    r = _row()
    pl = gp.render(r, Path("/repo"), Path("/home/x"))
    assert pl["ProgramArguments"][:2] == ["/bin/bash", "-lc"]
    wrapper = pl["ProgramArguments"][2]
    assert "source cabinet/.env" in wrapper, "conn string never reaches the worker"
    assert wrapper.endswith("exec " + r["command"])
    assert "&&" not in wrapper.split(" exec ", 1)[1]
    assert pl["StartInterval"] == 300


def test_worker_has_no_stale_opt_path_and_sources_triggers_from_root():
    txt = SCRIPT.read_text()
    # the convergence-era absolute path is GONE everywhere (code AND prose) —
    # grep the old name before declaring done.
    assert "/opt/founders-cabinet" not in txt
    # the trigger lib is sourced SCRIPT-relative, not from an absolute path —
    # this is the line whose absence left trigger_send undefined. (Not
    # $CABINET_ROOT-relative: a CABINET_ROOT override relocates the RUNTIME
    # root for isolation, never the code beside this script.)
    assert '. "$SCRIPT_DIR/lib/triggers.sh"' in txt
    # conn resolution + LOUD degrade (one stderr line, exit 0)
    assert "NEON_CONNECTION_STRING" in txt
    assert "DATABASE_URL" in txt


def test_worker_and_lib_parse():
    for path in (SCRIPT, TRIGGERS_LIB):
        p = _run(["bash", "-n", str(path)])
        assert p.returncode == 0, f"bash -n {path.name}: {p.stderr}"


# ---------------------------------------------------------------------------
# BEHAVIORAL — fake-bin harness (real lib/triggers.sh; psql/redis-cli/tmux stubbed)
# ---------------------------------------------------------------------------

# A stubbed psql that MODELS the atomic claim over a JSON fixture "table" + a
# fired-ids state file: it returns due rows whose id is not yet fired, appends
# their ids (so a re-run claims nothing), and emits TSV + the trailing
# ``UPDATE N`` status line the worker must filter. It ALSO asserts the received
# -c SQL still carries the load-bearing guards — teeth on the query itself: a
# worker that drops ``reminder_fired_at IS NULL`` (or the SKIP LOCKED claim)
# exits 3 here, so idempotency can never silently regress. The claim RETURNING
# is the Captain-arm P2 shape — MACHINE fields only (id, officer_slug, due_at,
# type); the untrusted title never rides the claim TSV. The worker re-reads the
# title by id with a :'id' bind, which psql only interpolates for STDIN/-f
# input — so that call (and the snooze bump) arrives here WITHOUT -c and is
# dispatched on the STDIN SQL body instead.
_PSQL_STUB = r'''
import json, os, re, sys
argv = sys.argv[1:]
sql = ""
for i, a in enumerate(argv):
    if a == "-c" and i + 1 < len(argv):
        sql = argv[i + 1]
        break
table = json.load(open(os.environ["CABINET_TEST_TABLE"]))
if not sql:
    # No -c => a :'var'-bound statement on STDIN (by-id title re-read or the
    # snooze bump). Serve the title from the fixture row; no snoozed verdicts
    # exist in this harness, so the bump returns nothing.
    body = sys.stdin.read()
    tid = ""
    for i, a in enumerate(argv):
        if a == "-v" and i + 1 < len(argv) and argv[i + 1].startswith("id="):
            tid = argv[i + 1][3:]
    if "SELECT title FROM officer_tasks" in body:
        for r in table:
            if str(r["id"]) == tid:
                sys.stdout.write(str(r["title"]) + "\n")
                break
    sys.exit(0)
norm = re.sub(r"\s+", " ", sql).strip().lower()
required = [
    "from officer_tasks",
    "due_at is not null",
    "due_at <= now()",
    "status in ('queue', 'wip')",
    "reminder_fired_at is null",
    "for update skip locked",
    "set reminder_fired_at = now()",
    "returning id, officer_slug, due_at, type",
]
missing = [g for g in required if g not in norm]
if missing:
    sys.stderr.write("FAKE-PSQL: claim query lost guards: %r\n" % missing)
    sys.exit(3)
fired_path = os.environ["CABINET_TEST_FIRED"]
fired = set()
if os.path.exists(fired_path):
    fired = {ln.strip() for ln in open(fired_path) if ln.strip()}
due = [r for r in table if str(r["id"]) not in fired]
with open(fired_path, "a") as fh:
    for r in due:
        fh.write(str(r["id"]) + "\n")
lines = ["%s\t%s\t%s\t%s" % (r["id"], r["officer_slug"], r["due_at"],
                             r.get("type", "task"))
         for r in due]
lines.append("UPDATE %d" % len(due))  # psql -tA emits this on RETURNING UPDATE
sys.stdout.write("\n".join(lines) + "\n")
'''

# fake redis-cli: capture the XADD ``message`` field (one line per fire) into
# FAKE_XADD_LOG; no-op (empty output, exit 0) for everything else — so
# trigger_wake_officer's killswitch GET / lock SET both read empty and the wake
# never send-keys.
_REDIS_STUB = r'''
log="${FAKE_XADD_LOG:-/dev/null}"
args=("$@"); n=${#args[@]}; i=0
while [ "$i" -lt "$n" ]; do
  if [ "${args[$i]}" = "XADD" ]; then
    j="$i"
    while [ "$j" -lt "$n" ]; do
      if [ "${args[$j]}" = "message" ]; then
        k=$((j + 1))
        [ "$k" -lt "$n" ] && printf '%s\n' "${args[$k]}" >> "$log"
        break
      fi
      j=$((j + 1))
    done
    printf '1-1\n'   # a plausible XADD id (discarded by trigger_send's redirect)
    exit 0
  fi
  i=$((i + 1))
done
exit 0
'''


def _run(cmd, env=None, timeout=30):
    patched = subprocess.Popen
    subprocess.Popen = _REAL_POPEN
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              env=env, timeout=timeout)
    finally:
        subprocess.Popen = patched


def _fakebin(tmp_path: Path) -> Path:
    b = tmp_path / "bin"
    b.mkdir()
    psql = b / "psql"
    psql.write_text("#!" + sys.executable + "\n" + _PSQL_STUB)
    psql.chmod(0o755)
    redis = b / "redis-cli"
    redis.write_text("#!/bin/bash\n" + _REDIS_STUB)
    redis.chmod(0o755)
    # tmux always fails has-session → trigger_wake_officer no-ops deterministically
    tmux = b / "tmux"
    tmux.write_text("#!/bin/bash\nexit 1\n")
    tmux.chmod(0o755)
    return b


@pytest.fixture()
def harness(tmp_path):
    fakebin = _fakebin(tmp_path)
    table_path = tmp_path / "table.json"
    fired_path = tmp_path / "fired.txt"
    xadd_log = tmp_path / "xadd.log"

    def write_table(rows):
        table_path.write_text(json.dumps(rows))

    def rearm(reset_fired=""):
        fired_path.write_text(reset_fired)

    def env():
        e = dict(os.environ)
        e.update({
            "CONN": "postgres://fake/tasks",       # non-empty → skip the degrade path
            "CABINET_ROOT": str(_REPO),            # source the REAL lib/triggers.sh
            "CABINET_TEST_TABLE": str(table_path),
            "CABINET_TEST_FIRED": str(fired_path),
            "FAKE_XADD_LOG": str(xadd_log),
            "OFFICER_NAME": "due-at-reminder",
            "PATH": f"{fakebin}:/opt/homebrew/bin:/usr/bin:/bin",
        })
        # only CONN should decide the conn string in-test
        for k in ("NEON_CONNECTION_STRING", "DATABASE_URL"):
            e.pop(k, None)
        return e

    def run():
        return _run(["bash", str(SCRIPT)], env=env())

    def fires():
        if not xadd_log.exists():
            return []
        return [ln for ln in xadd_log.read_text().splitlines() if ln.strip()]

    def payloads():
        out = []
        for ln in fires():
            out.append(json.loads(ln[ln.index("{"):]))  # strip "[ts] From x: " prefix
        return out

    return type("H", (), {
        "write_table": staticmethod(write_table),
        "rearm": staticmethod(rearm),
        "run": staticmethod(run),
        "fires": staticmethod(fires),
        "payloads": staticmethod(payloads),
        "tmp": tmp_path,
    })()


def test_fires_each_due_row_once_and_is_idempotent_on_rerun(harness):
    harness.write_table([
        {"id": 101, "officer_slug": "cos", "title": "Renew the TLS cert",
         "due_at": "2026-07-16T09:00:00Z"},
        {"id": 102, "officer_slug": "cto", "title": "Review PR #42",
         "due_at": "2026-07-16T09:05:00Z"},
    ])

    r1 = harness.run()
    assert r1.returncode == 0, r1.stderr
    assert len(harness.fires()) == 2, f"expected 2 fires, got {harness.fires()}"
    p = harness.payloads()
    assert {x["title"] for x in p} == {"Renew the TLS cert", "Review PR #42"}
    assert {x["task_id"] for x in p} == {101, 102}
    assert all(x["type"] == "task_reminder" for x in p)
    assert "fired=2" in r1.stdout

    # RE-RUN: the claim marked reminder_fired_at, so nothing is due now.
    r2 = harness.run()
    assert r2.returncode == 0, r2.stderr
    assert len(harness.fires()) == 2, "idempotency broken — a fired reminder refired"
    # quiet-tick heartbeat: the summary line is written EVERY run (the
    # watchdog freshness floor), zeros across the board on a quiet tick.
    assert "fired=0" in r2.stdout and "carded=0" in r2.stdout
    assert "elapsed_at=" in r2.stdout


def test_rearm_refires_after_due_at_bump(harness):
    harness.write_table([
        {"id": 101, "officer_slug": "cos", "title": "Sign the DPA",
         "due_at": "2026-07-16T09:00:00Z"},
    ])
    assert harness.run().returncode == 0
    assert len(harness.fires()) == 1                 # first fire
    assert harness.run().returncode == 0
    assert len(harness.fires()) == 1                 # idempotent re-run (still 1)

    # The 041 re-arm trigger clears reminder_fired_at when due_at changes.
    harness.rearm(reset_fired="")
    harness.write_table([
        {"id": 101, "officer_slug": "cos", "title": "Sign the DPA",
         "due_at": "2026-07-16T11:00:00Z"},   # bumped
    ])
    r3 = harness.run()
    assert r3.returncode == 0
    fires = harness.fires()
    assert len(fires) == 2, "a re-armed reminder must fire again"
    assert all(json.loads(f[f.index("{"):])["task_id"] == 101 for f in fires)
    assert "fired=1" in r3.stdout


def test_injection_title_survives_as_data_through_sql_and_trigger_json(harness):
    """Untrusted task title with quotes / ; / $() / backticks / backslashes
    stays DATA: valid JSON, byte-identical title, and the $(touch …) never
    executes. Teeth: string-interpolated JSON breaks on the double-quote;
    an eval'd title creates the PWNED file."""
    pwned = harness.tmp / "PWNED"
    inj = (
        "O'Brien said \"ship it\"; DROP TABLE officer_tasks; -- "
        f"$(touch {pwned}) `id` back\\slash 100% & <=>"
    )
    harness.write_table([
        {"id": 777, "officer_slug": "cos", "title": inj,
         "due_at": "2026-07-16T09:00:00Z"},
    ])

    r = harness.run()
    assert r.returncode == 0, r.stderr
    fires = harness.fires()
    assert len(fires) == 1, f"expected exactly 1 fire, got {fires}"

    payload = json.loads(fires[0][fires[0].index("{"):])   # valid JSON or ValueError
    assert payload["title"] == inj, "title mangled — jq --arg discipline broken"
    assert payload["task_id"] == 777
    assert payload["type"] == "task_reminder"
    assert not pwned.exists(), "command substitution in the title EXECUTED"
