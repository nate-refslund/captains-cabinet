"""load-preset.sh applies the work-store schemas even when the connection
string lives ONLY in cabinet/.env (fresh-hatch #57).

The Mac-native path (provision-local-postgres.sh) writes NEON_CONNECTION_STRING
into the cabinet/.env FILE and never exports it. Before the fix, the schema-
apply block gated on the PROCESS env var `${NEON_CONNECTION_STRING:-}`, so on a
Mac hatch it was silently skipped -> zero cabinet tables -> `relation
"officer_tasks" does not exist` days later. The fix derives the string from
.env (grep/cut, quote-tolerant, never `source`) and applies the schemas.

Hermetic: a scratch CABINET_ROOT fixture (mirrors test_load_preset_materialize
.py), a cabinet/.env carrying the string, NO such var in the process env, and a
PATH-shimmed fake `psql` that records every (connection-string, schema) it is
invoked with. We assert the block was NOT skipped and applied the framework
schemas with the .env-derived (quote-stripped) string.

Run: python3.12 -m pytest cabinet/scripts/tests/test_load_preset_workstore_schema.py -q
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
_LOAD_PRESET = _SCRIPTS_DIR / "load-preset.sh"
_POSTURE_EXAMPLE = _REPO_ROOT / "instance" / "config" / "posture.yml.example"
_LADDER_EXAMPLE = _REPO_ROOT / "instance" / "config" / "trust-ladder.yml.example"

# The connection string is written QUOTED in .env — the fix must strip the
# surrounding quotes before handing it to psql as a single argument.
_CONN = "postgresql://fixture:pw@localhost:5432/fixturedb"


def _scratch_root(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    (root / "framework").mkdir(parents=True)
    (root / "framework" / "constitution-base.md").write_text("# base\n", encoding="utf-8")
    (root / "framework" / "safety-boundaries-base.md").write_text("# base\n", encoding="utf-8")
    preset = root / "presets" / "work"
    preset.mkdir(parents=True)
    (preset / "preset.yml").write_text("name: work\n", encoding="utf-8")
    cfg = root / "instance" / "config"
    cfg.mkdir(parents=True)
    (cfg / "active-preset").write_text("work\n", encoding="utf-8")
    shutil.copy(_POSTURE_EXAMPLE, cfg / "posture.yml.example")
    shutil.copy(_LADDER_EXAMPLE, cfg / "trust-ladder.yml.example")
    # The connection string lives ONLY in the .env FILE (quoted), never exported.
    (root / "cabinet").mkdir(parents=True, exist_ok=True)
    (root / "cabinet" / ".env").write_text(
        f'NEON_CONNECTION_STRING="{_CONN}"\n', encoding="utf-8")
    # The two framework schemas we assert were applied; the block's `[ -f ]`
    # guard skips the others we do not stage.
    sqldir = root / "cabinet" / "sql"
    sqldir.mkdir(parents=True)
    (sqldir / "cabinet_memory.sql").write_text("-- fixture\n", encoding="utf-8")
    (sqldir / "038-officer-tasks.sql").write_text("-- fixture\n", encoding="utf-8")
    return root


def _psql_shim(tmp_path: Path) -> tuple[Path, Path]:
    """A fake `psql` on PATH that records its argv to a file and exits 0."""
    shim_dir = tmp_path / "shim"
    shim_dir.mkdir()
    record = tmp_path / "psql-invocations.txt"
    psql = shim_dir / "psql"
    psql.write_text(
        "#!/bin/bash\n"
        f'printf "%s\\n" "$*" >> "{record}"\n'
        "exit 0\n",
        encoding="utf-8")
    psql.chmod(0o755)
    return shim_dir, record


def _run(root: Path, tmp_path: Path, shim_dir: Path):
    env = dict(os.environ)
    env["CABINET_ROOT"] = str(root)
    env["CABINET_RUNTIME_DIR"] = str(tmp_path / "runtime")
    env["PATH"] = f"{shim_dir}{os.pathsep}{env['PATH']}"
    # The whole point: the string is ABSENT from the process env.
    for k in ("NEON_CONNECTION_STRING", "DATABASE_URL", "CABINET_ID", "CABINET_MODE"):
        env.pop(k, None)
    return subprocess.run(
        ["bash", str(_LOAD_PRESET)],
        cwd=_REPO_ROOT, env=env, capture_output=True, text=True, timeout=60)


def test_env_file_connection_string_applies_framework_schemas(tmp_path):
    root = _scratch_root(tmp_path)
    shim_dir, record = _psql_shim(tmp_path)
    p = _run(root, tmp_path, shim_dir)
    assert p.returncode == 0, p.stderr
    assert record.exists(), (
        "psql was NEVER invoked — the schema-apply block was skipped despite "
        "NEON_CONNECTION_STRING being present in cabinet/.env (the #57 bug)")
    invocations = record.read_text(encoding="utf-8")
    # the block ran and used the .env-derived string, with the surrounding
    # quotes stripped (passed to psql as one bare argument)
    assert _CONN in invocations, invocations
    assert f'"{_CONN}"' not in invocations, (
        "the surrounding quotes were not stripped from the .env value")
    # the framework schemas were actually applied
    assert "cabinet_memory.sql" in invocations, invocations
    assert "038-officer-tasks.sql" in invocations, invocations


def test_no_connection_anywhere_skips_cleanly(tmp_path):
    """Negative control: no env var AND no NEON_CONNECTION_STRING in .env ->
    the block skips (psql never called) and boot is not failed."""
    root = _scratch_root(tmp_path)
    (root / "cabinet" / ".env").write_text("SOME_OTHER_KEY=1\n", encoding="utf-8")
    shim_dir, record = _psql_shim(tmp_path)
    p = _run(root, tmp_path, shim_dir)
    assert p.returncode == 0, p.stderr
    assert not record.exists(), "psql must not be called with no work-store string"
    assert "skipping Neon schema application" in p.stderr
