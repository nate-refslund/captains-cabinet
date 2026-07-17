"""Config-split fix (2026-07-17) — my-tasks.sh resolves its context on a
PORTFOLIO-shaped deployment (the live failure this lane fixes: preset
deployments declare lanes via instance/config/contexts/ and never write
active-project.txt, so every my-tasks call — and therefore the whole
officer_tasks board — used to die at the context gate).

End-to-end through the real script with a stub `psql` on PATH that records
its argv (and swallows stdin): the assertions read the recorded argv, so the
test also PINS the injection-safe transport — the context reaches psql as a
`-v ctx=<slug>` parameter (psql :'ctx' literal-quoting), never spliced into
SQL text.

Fixture vocabulary is synthetic Testburg (test_lanes_sh.py convention).
No network, no DB, no Redis (redis-cli absent from the stub PATH → the
broadcast helper's silent-skip path).
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]  # cabinet/scripts
MY_TASKS = SCRIPTS_DIR / "my-tasks.sh"

PSQL_STUB = """#!/bin/bash
# argv-recording psql stub — my-tasks.sh context tests.
for a in "$@"; do printf '%s\\n' "$a" >> "$PSQL_ARGV_LOG"; done
cat > /dev/null
exit 0
"""


def _portfolio_root(tmp_path: Path) -> Path:
    """A minimal portfolio-shaped CABINET_ROOT: active-preset present,
    NO active-project.txt, two declared lanes."""
    cfg = tmp_path / "instance" / "config"
    (cfg / "contexts").mkdir(parents=True)
    (cfg / "active-preset").write_text("portfolio\n", encoding="utf-8")
    (cfg / "contexts" / "bakery.yml").write_text(
        "slug: bakery\nactive: true\n", encoding="utf-8")
    (cfg / "contexts" / "newsletter.yml").write_text(
        "slug: newsletter\nactive: false\n", encoding="utf-8")
    return tmp_path


def _stub_bin(tmp_path: Path) -> Path:
    stub = tmp_path / "stubbin"
    stub.mkdir()
    psql = stub / "psql"
    psql.write_text(PSQL_STUB, encoding="utf-8")
    psql.chmod(psql.stat().st_mode | stat.S_IEXEC)
    return stub


def _run(root: Path, stub: Path, log: Path, officer: str,
         *args: str, extra_env: "dict[str, str] | None" = None
         ) -> subprocess.CompletedProcess:
    env = {
        "PATH": f"{stub}:/usr/bin:/bin",
        "CABINET_ROOT": str(root),
        "CABINET_OFFICER": officer,
        "NEON_CONNECTION_STRING": "postgresql://stub/stub",  # stub only — never a real DSN
        "PSQL_ARGV_LOG": str(log),
    }
    env.update(extra_env or {})
    return subprocess.run(
        ["bash", str(MY_TASKS), *args],
        capture_output=True, text=True, env=env,
    )


def _argv_lines(log: Path) -> "list[str]":
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def test_portfolio_lane_officer_resolves_and_lists(tmp_path):
    """THE acceptance case: a '<lane>-ceo' officer on a portfolio deployment
    (no active-project.txt) resolves its lane and reaches the DB."""
    root = _portfolio_root(tmp_path)
    stub = _stub_bin(tmp_path)
    log = tmp_path / "psql-argv.log"
    proc = _run(root, stub, log, "bakery-ceo", "list")
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    argv = _argv_lines(log)
    assert "ctx=bakery" in argv, (
        f"context must travel as a psql -v parameter; argv was: {argv}")
    assert "slug=bakery-ceo" in argv


def test_unmatched_officer_fails_loud_before_db(tmp_path):
    """No lane match, no lane_default → error BEFORE any psql call (Spec 038
    'errors before touching the DB'), with the remedy chain on stderr."""
    root = _portfolio_root(tmp_path)
    stub = _stub_bin(tmp_path)
    log = tmp_path / "psql-argv.log"
    proc = _run(root, stub, log, "cos", "list")
    assert proc.returncode == 1
    assert "context_slug required" in proc.stderr
    assert "CABINET_CONTEXT" in proc.stderr
    assert _argv_lines(log) == [], "psql must not be reached without a context"


def test_lane_default_covers_cross_lane_officers(tmp_path):
    root = _portfolio_root(tmp_path)
    (root / "instance" / "config" / "platform.yml").write_text(
        "lane_default: newsletter\n", encoding="utf-8")
    stub = _stub_bin(tmp_path)
    log = tmp_path / "psql-argv.log"
    proc = _run(root, stub, log, "cos", "list")
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    assert "ctx=newsletter" in _argv_lines(log)


def test_context_flag_still_overrides_everything(tmp_path):
    root = _portfolio_root(tmp_path)
    stub = _stub_bin(tmp_path)
    log = tmp_path / "psql-argv.log"
    proc = _run(root, stub, log, "bakery-ceo", "list",
                "--context", "newsletter")
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    assert "ctx=newsletter" in _argv_lines(log)


def test_malformed_context_flag_rejected_by_cli_gate(tmp_path):
    """Spec 038 §4.8: the CLI validates slug shape FIRST — a traversal-shaped
    --context never reaches the contexts/<slug>.yml probe or psql."""
    root = _portfolio_root(tmp_path)
    stub = _stub_bin(tmp_path)
    log = tmp_path / "psql-argv.log"
    proc = _run(root, stub, log, "bakery-ceo", "list",
                "--context", "../../etc/passwd")
    assert proc.returncode == 1
    assert "is invalid" in proc.stderr
    assert _argv_lines(log) == []


def test_poisoned_active_project_txt_never_executes(tmp_path):
    """Injection control: shell-metacharacter content in active-project.txt
    is skipped as data; the officer rung still resolves; nothing executes."""
    root = _portfolio_root(tmp_path)
    marker = tmp_path / "pwned"
    (root / "instance" / "config" / "active-project.txt").write_text(
        f"$(touch {marker})\n", encoding="utf-8")
    stub = _stub_bin(tmp_path)
    log = tmp_path / "psql-argv.log"
    proc = _run(root, stub, log, "bakery-ceo", "list")
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    assert "ctx=bakery" in _argv_lines(log)
    assert not marker.exists(), "poisoned config value was EXECUTED"


def test_missing_context_yaml_stays_fatal(tmp_path):
    """038.3: a resolved context whose YAML vanished is still FATAL — the
    resolver does not weaken the existence gate. (When bakery.yml is gone the
    enum shrinks to just newsletter, so unflagged runs land there via the
    single-declared-lane rung — same all-officers-share-the-only-context
    semantics as the old single active-project deployments.)"""
    root = _portfolio_root(tmp_path)
    os.remove(root / "instance" / "config" / "contexts" / "bakery.yml")
    stub = _stub_bin(tmp_path)
    log = tmp_path / "psql-argv.log"
    proc = _run(root, stub, log, "bakery-ceo", "list")
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    assert "ctx=newsletter" in _argv_lines(log)  # single remaining lane
    # an explicitly-passed context without YAML hits the 038.3 gate:
    log.unlink()
    proc = _run(root, stub, log, "bakery-ceo", "list", "--context", "bakery")
    assert proc.returncode == 1
    assert "no YAML" in proc.stderr
    assert _argv_lines(log) == []
