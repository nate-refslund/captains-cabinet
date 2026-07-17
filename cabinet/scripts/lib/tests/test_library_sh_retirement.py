"""Library retirement — library.sh write-path surgery (2026-07-16).

Captain-ratified retirement (closes memory-study Q4/C7): library.sh
library_create_record / library_update_record no longer compute or write a
per-record vector. The cabinet_memory mirror queue (memory_queue_embed →
redis XADD) is the ONLY embed-adjacent side effect left on the write path.

Functional runs use PATH stubs (psql / redis-cli / curl) — no network, no
Neon, no Redis. curl is a TRIPWIRE: memory_get_embedding shells to curl, so
a create/update that still embeds fails these tests loudly. The tripwire is
ARMED by a dummy VOYAGE_API_KEY in _env(): memory_get_embedding returns 1
before curl when the key is unset, so without it a resurrected embed call
would silently no-op instead of touching the stub (network stays impossible
either way — curl resolves to the PATH stub).

Run: python3.12 -m pytest cabinet/scripts/lib/tests/test_library_sh_retirement.py -q
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

# Captured at import time — test_library_mcp_client patches subprocess.Popen
# globally and the patch can leak across modules (same guard as
# test_embed_seam_wiring.py).
_REAL_POPEN = subprocess.Popen

SCRIPTS_DIR = Path(__file__).resolve().parents[2]  # cabinet/scripts
REPO_ROOT = SCRIPTS_DIR.parents[1]
LIBRARY_SH = SCRIPTS_DIR / "lib" / "library.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None, reason="jq required by library.sh payloads"
)


def _run_bash(script: str, env: dict) -> "subprocess.CompletedProcess[str]":
    patched = subprocess.Popen
    subprocess.Popen = _REAL_POPEN
    try:
        return subprocess.run(
            ["bash", "-c", script],
            capture_output=True, text=True,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), **env},
        )
    finally:
        subprocess.Popen = patched


def _stub_dir(tmp_path: Path) -> Path:
    """psql: captures each stdin SQL to sql_NNN + answers by statement shape.
    redis-cli: captures argv (one arg per line, NUL-safe enough for asserts).
    curl: tripwire — touches a marker; a vector-embedding create would hit it."""
    stub = tmp_path / "bin"
    stub.mkdir()

    psql = stub / "psql"
    psql.write_text(
        "#!/bin/bash\n"
        f"cap_dir='{tmp_path}'\n"
        "n=$(ls \"$cap_dir\"/sql_* 2>/dev/null | wc -l | tr -d ' ')\n"
        "sql_file=\"$cap_dir/sql_$(printf '%03d' \"$n\")\"\n"
        "cat > \"$sql_file\"\n"
        "if grep -q 'BEGIN;' \"$sql_file\"; then echo 43\n"
        "elif grep -q 'INSERT INTO library_records' \"$sql_file\"; then echo 42\n"
        "elif grep -q 'SELECT space_id FROM library_records' \"$sql_file\"; then echo 7\n"
        "elif grep -q 'SELECT name FROM library_spaces' \"$sql_file\"; then echo 'Test Space'\n"
        "fi\n"
    )
    psql.chmod(0o755)

    redis = stub / "redis-cli"
    redis.write_text(
        "#!/bin/bash\n"
        f"printf '%s\\n' \"$@\" >> '{tmp_path}/redis_args'\n"
        "echo '1-1'\n"
    )
    redis.chmod(0o755)

    curl = stub / "curl"
    curl.write_text(f"#!/bin/bash\ntouch '{tmp_path}/curl_was_called'\nexit 1\n")
    curl.chmod(0o755)
    return stub


def _env(tmp_path: Path, stub: Path) -> dict:
    return {
        "PATH": f"{stub}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        "CABINET_ROOT": str(REPO_ROOT),
        "NEON_CONNECTION_STRING": "postgresql://placeholder",
        "OFFICER_NAME": "system",   # skips access-control psql round-trips
        "HOME": str(tmp_path),
        # ARMS the curl tripwire (see module docstring): clearly-fake value,
        # only ever consumed by the PATH-stub curl above — never dialed out.
        "VOYAGE_API_KEY": "test-dummy-never-dialed",
    }


def _captured_sql(tmp_path: Path) -> str:
    return "\n=====\n".join(
        p.read_text() for p in sorted(tmp_path.glob("sql_*"))
    )


def _redis_payload(tmp_path: Path) -> dict:
    args = (tmp_path / "redis_args").read_text().splitlines()
    assert "XADD" in args, args
    assert "cabinet:memory:embed_queue" in args, args
    # payload rides as the last value after the literal key 'payload'
    payload_idx = args.index("payload") + 1
    return json.loads(args[payload_idx])


# =========================================================================
# Syntax + structural pins
# =========================================================================

def test_bash_syntax_library_sh():
    patched = subprocess.Popen
    subprocess.Popen = _REAL_POPEN
    try:
        proc = subprocess.run(["bash", "-n", str(LIBRARY_SH)],
                              capture_output=True, text=True)
    finally:
        subprocess.Popen = patched
    assert proc.returncode == 0, proc.stderr


def _fn_body(text: str, name: str, next_name: str) -> str:
    start = text.index(f"{name}() {{")
    end = text.index(f"{next_name}()", start)
    return text[start:end]


def test_create_and_update_bodies_have_no_record_embed():
    text = LIBRARY_SH.read_text()
    create = _fn_body(text, "library_create_record", "library_update_record")
    update = _fn_body(text, "library_update_record", "library_get_record")
    for body, label in ((create, "create"), (update, "update")):
        assert "memory_get_embedding" not in body, f"{label}: embed call resurfaced"
        assert ":'embedding'" not in body, f"{label}: embedding psql bind resurfaced"
        assert "memory_queue_embed \"library_record\"" in body, (
            f"{label}: cabinet_memory mirror queue must stay")
    # INSERT column lists are vector-free
    assert ("INSERT INTO library_records (space_id, title, content_markdown,"
            " schema_data, labels, created_by_officer, created_at)") in create
    assert ("INSERT INTO library_records (space_id, title, content_markdown,"
            " schema_data, labels, created_by_officer, version)") in update


def test_search_keeps_legacy_query_embed_with_ilike_fallback():
    """library_search still ranks over LEGACY vectors (query-side embed) and
    falls back to ILIKE — deliberately untouched by the retirement."""
    text = LIBRARY_SH.read_text()
    search = _fn_body(text, "library_search", "library_list_records")
    assert "memory_get_embedding" in search
    assert "ILIKE" in search


# =========================================================================
# Functional: create — record id out, ONE redis queue push, no curl
# =========================================================================

def test_create_record_queues_memory_only(tmp_path):
    stub = _stub_dir(tmp_path)
    # Hostile content rides an ENV VAR into a quoted "$_T_CONTENT" expansion —
    # the same no-interpolation seam library-mcp uses (_LIB_ARG_n). Embedding
    # it into the bash -c text would let $(...)/backticks execute in the TEST,
    # masking what we're pinning: content stays data end-to-end.
    hostile = 'Body with $(boom) `tick` "quotes" <script>x</script>'
    env = _env(tmp_path, stub)
    env["_T_CONTENT"] = hostile
    proc = _run_bash(
        f'source "{LIBRARY_SH}" && '
        'library_create_record 7 "Title X" "$_T_CONTENT" \'{"k":"v"}\' "l1,l2"',
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().splitlines()[0] == "42"

    # Exactly one XADD, payload is the cabinet_memory mirror (source data intact)
    payload = _redis_payload(tmp_path)
    assert payload["source_type"] == "library_record"
    assert payload["source_id"] == "lib-42"
    assert payload["metadata"]["record_id"] == "42"
    assert "$(boom)" in payload["content"], "content must ride as DATA"
    assert (tmp_path / "redis_args").read_text().count("XADD") == 1

    # No vector path: curl tripwire silent, captured SQL vector-free
    assert not (tmp_path / "curl_was_called").exists(), (
        "create called curl — record-vector embed path resurfaced")
    sql = _captured_sql(tmp_path)
    assert "INSERT INTO library_records" in sql
    assert "embedding" not in sql
    assert "::vector" not in sql
    # Injection discipline: hostile content rides psql -v binds, never SQL text
    assert "$(boom)" not in sql


def test_create_refuses_whitespace_only(tmp_path):
    stub = _stub_dir(tmp_path)
    proc = _run_bash(
        f'source "{LIBRARY_SH}" && library_create_record 7 "   " "  " "{{}}" ""; echo "rc=$?"',
        env=_env(tmp_path, stub),
    )
    assert "rc=1" in proc.stdout
    assert not (tmp_path / "redis_args").exists()
    assert not list(tmp_path.glob("sql_*")), "whitespace-only must not hit psql"


# =========================================================================
# Functional: update — new version id out, mirror queue, no curl
# =========================================================================

def test_update_record_queues_memory_only(tmp_path):
    stub = _stub_dir(tmp_path)
    proc = _run_bash(
        f'source "{LIBRARY_SH}" && library_update_record 42 "Title Y" "New body"',
        env=_env(tmp_path, stub),
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().splitlines()[0] == "43"

    payload = _redis_payload(tmp_path)
    assert payload["source_id"] == "lib-43"
    assert payload["source_type"] == "library_record"

    assert not (tmp_path / "curl_was_called").exists(), (
        "update called curl — record-vector embed path resurfaced")
    sql = _captured_sql(tmp_path)
    assert "INSERT INTO library_records" in sql  # versioned-insert CTE
    assert "embedding" not in sql
    assert "::vector" not in sql
