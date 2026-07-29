"""Offline static tests for the Cabinet Memory search surface.

Covers the P0a recall fix (multi-type filter) + hybrid ranking wiring in
cabinet/scripts/lib/memory.sh, the --as-of / --min-score flags in
cabinet/scripts/search-memory.sh, and the pre-captain-dm.sh recall budget +
drop telemetry. No network, no Neon, no Voyage — pure syntax + contract
greps, so they run anywhere the framework suite runs.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

# Captured at import (collection) time, BEFORE any test runs:
# test_library_mcp_client patches the global subprocess.Popen and the patch
# can leak into later-alphabetical modules — restore the real one around our
# spawns so a leaked FakePopen can't fail these tests.
_REAL_POPEN = subprocess.Popen

SCRIPTS_DIR = Path(__file__).resolve().parents[2]  # cabinet/scripts
MEMORY_SH = SCRIPTS_DIR / "lib" / "memory.sh"
SEARCH_SH = SCRIPTS_DIR / "search-memory.sh"
HOOK_SH = SCRIPTS_DIR / "hooks" / "pre-captain-dm.sh"


def _bash_n(path: Path) -> None:
    patched = subprocess.Popen
    subprocess.Popen = _REAL_POPEN
    try:
        proc = subprocess.run(
            ["bash", "-n", str(path)], capture_output=True, text=True
        )
    finally:
        subprocess.Popen = patched
    assert proc.returncode == 0, f"bash -n {path.name} failed: {proc.stderr}"


def test_bash_syntax_memory_sh():
    _bash_n(MEMORY_SH)


def test_bash_syntax_search_memory_sh():
    _bash_n(SEARCH_SH)


def test_bash_syntax_pre_captain_dm_sh():
    _bash_n(HOOK_SH)


def test_memory_search_multi_type_filter():
    """P0a: comma-separated --type lists must match via string_to_array,
    not exact equality (exact equality made the pre-captain-dm 6-type
    filter match nothing → 0% recall availability)."""
    text = MEMORY_SH.read_text()
    assert "ANY(string_to_array(:'st_filter', ','))" in text
    assert "source_type = :'st_filter'" not in text


def test_memory_search_hybrid_ranking_wired():
    text = MEMORY_SH.read_text()
    # Similarity floor (vec channel) with env override.
    assert "CABINET_MEMORY_MIN_SCORE" in text
    assert "vec_sim >= (:'min_score')::float8" in text
    # Blend weights documented + applied; degraded arm present.
    assert "0.60 * s.vec_sim + 0.25 * s.lex + 0.15 * s.recency" in text
    assert "0.80 * s.vec_sim + 0.20 * s.recency" in text
    # Recency: 90-day half-life, NULL → neutral 0.5.
    assert "THEN 0.5" in text
    assert "90.0 * 86400.0" in text
    # Lexical channel over the generated tsvector column.
    assert "content_tsv" in text
    assert "plainto_tsquery" in text
    # Fail-closed as-of fence: NULL timestamps excluded under a fence.
    assert "source_created_at IS NOT NULL" in text
    assert "NULLIF(:'as_of', '')::timestamptz" in text
    # Trust surfaced from metadata with 'derived' fallback.
    assert "metadata->>'trust'" in text
    assert "'derived'" in text


def test_search_memory_flags_and_help():
    text = SEARCH_SH.read_text()
    for flag in ("--as-of", "--min-score", "--type", "--officer", "--limit"):
        assert flag in text, f"missing flag {flag}"
    # Help documents the fail-closed fence semantics.
    assert "EXCLUDED under a fence" in text
    # min_score + as_of are forwarded positionally into memory_search.
    assert '"$MIN_SCORE" "$AS_OF"' in text
    # Result lines carry the trust prefix consumed by pre-captain-dm.
    assert "[trust:%s]" in text
    # Empty-result contract unchanged (callers bail on this string).
    assert "No results found." in text


def test_memory_search_cabinet_id_scoping():
    """Tenant fence: memory_search must scope to the resolved cabinet_id,
    keep the OR-'main' transition arm (live pre-scoping rows all carry the
    column default 'main' — a strict filter would zero out recall), and
    fall back to unscoped when resolution is empty (back-compat)."""
    text = MEMORY_SH.read_text()
    # Filter present in the candidates CTE, parameterized via psql -v.
    assert (
        "AND (:'cid' = '' OR m.cabinet_id = :'cid' OR m.cabinet_id = 'main')"
        in text
    )
    assert '-v cid="$cid_scope"' in text
    # Never string-interpolated into the SQL heredoc.
    assert "cabinet_id = '$" not in text
    # Transition rule documented next to the scope resolution.
    assert "TRANSITION RULE" in text


def test_memory_cabinet_id_resolvers():
    """Canonical resolution = env CABINET_ID (default 'main'), charset-
    validated like load-preset.sh's CP9b validator. Search-side scope is
    unscoped ONLY when genuinely unset; write-side id is never empty."""
    text = MEMORY_SH.read_text()
    assert "memory_cabinet_id()" in text
    assert "memory_cabinet_scope()" in text
    assert '"${CABINET_ID:-main}"' in text  # write-side default
    assert '"${CABINET_ID:-}"' in text  # search-side (unset = unscoped)
    assert "'^[A-Za-z0-9_-]+$'" in text  # charset validation
    # .env sourcing guard also fires when CABINET_ID is missing.
    assert '[ -z "${CABINET_ID:-}" ]' in text


def _run_bash(script: str, env: dict) -> "subprocess.CompletedProcess[str]":
    """Run a bash snippet with the REAL Popen (see _REAL_POPEN note above)."""
    import os

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


def test_memory_cabinet_resolvers_agree_on_invalid_id(tmp_path):
    """Review fix 2026-07-07: a charset-INVALID CABINET_ID (e.g. 'acme.eu')
    resolves 'main' on BOTH the write and search sides — never unscoped —
    so a misconfigured box stays self-consistent instead of silently reading
    every tenant's rows. A stderr warning makes the misconfig visible."""
    proc = _run_bash(
        f'source "{MEMORY_SH}" && '
        'printf "%s|%s" "$(memory_cabinet_id)" "$(memory_cabinet_scope)"',
        env={
            "CABINET_ID": "acme.eu",  # dot is outside [A-Za-z0-9_-]
            "NEON_CONNECTION_STRING": "postgresql://placeholder",  # skip .env
        },
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "main|main"
    assert "invalid charset" in proc.stderr
    # Genuinely-unset stays unscoped on the search side (back-compat) and
    # 'main' on the write side.
    proc2 = _run_bash(
        f'CABINET_ROOT="{tmp_path}" source "{MEMORY_SH}" && '
        'printf "%s|%s" "$(memory_cabinet_id)" "$(memory_cabinet_scope)"',
        env={"NEON_CONNECTION_STRING": "postgresql://placeholder"},
    )
    assert proc2.returncode == 0, proc2.stderr
    assert proc2.stdout == "main|"


def test_env_sourcing_backfills_but_never_clobbers_caller_env(tmp_path):
    """Review fix 2026-07-07: when the lib sources cabinet/.env to back-fill
    a MISSING variable, a caller-exported NEON_CONNECTION_STRING (scratch DB,
    test harness) must survive — .env fills only the gaps."""
    (tmp_path / "cabinet").mkdir()
    (tmp_path / "cabinet" / ".env").write_text(
        'NEON_CONNECTION_STRING="postgresql://live-hq"\nCABINET_ID="hq-live"\n'
    )
    proc = _run_bash(
        f'source "{MEMORY_SH}" && '
        'printf "%s|%s" "$NEON_CONNECTION_STRING" "$CABINET_ID"',
        env={
            "CABINET_ROOT": str(tmp_path),
            "NEON_CONNECTION_STRING": "postgresql://caller-scratch",
            # CABINET_ID deliberately unset → back-filled from .env
        },
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "postgresql://caller-scratch|hq-live"


def test_memory_embed_stamps_cabinet_id():
    """memory_embed stamps cabinet_id on insert (COALESCE to the 'main'
    column default) and restamps on upsert; optional 8th arg lets the
    worker pass the enqueuer's tenant through."""
    text = MEMORY_SH.read_text()
    assert "source_created_at, cabinet_id)" in text
    assert "COALESCE(NULLIF(:'cid', ''), 'main')" in text
    assert "cabinet_id = EXCLUDED.cabinet_id" in text
    assert 'local cabinet_id="${8:-$(memory_cabinet_id)}"' in text
    assert '-v cid="$cabinet_id"' in text


def test_memory_queue_embed_payload_carries_cabinet_id():
    """Queue payload stamps cabinet_id at ENQUEUE time (jq --arg, no eval)
    so the worker can preserve the enqueuer's tenant."""
    text = MEMORY_SH.read_text()
    assert '--arg cabinet_id "$(memory_cabinet_id)"' in text
    assert "cabinet_id: $cabinet_id}" in text


def test_pre_captain_dm_budget_and_telemetry():
    text = HOOK_SH.read_text()
    # 2s budget on all three arms (timeout, gtimeout, DIY poll).
    assert text.count("timeout 2 bash") >= 1  # `timeout 2` (gtimeout matches too)
    assert "gtimeout 2 bash" in text
    assert "$(seq 1 20)" in text
    assert "timeout 0.5" not in text and "gtimeout 0.5" not in text
    # Drop telemetry: monotonic Redis counter, best-effort.
    assert "cabinet:memory:recall_drops" in text
    assert "INCR cabinet:memory:recall_drops" in text
    # Hook must stay best-effort — the INCR is || true guarded.
    assert ">/dev/null 2>&1 || true" in text


def test_memory_search_keyless_degrade_contract():
    """EMBED-SEAM forward-guard (2026-07-07): with no embedding available
    (unset VOYAGE_API_KEY / Voyage outage) memory_search must DEGRADE to the
    lexical-only arm — never blank the result set with the old sentinel bail.
    The lexical arm keeps every fence of the hybrid arm (superseded, multi-
    type, officer, tenant OR-'main', fail-closed as-of) and the 8-col shape."""
    text = MEMORY_SH.read_text()
    assert "memory_search_lexical()" in text
    assert "DEGRADED to lexical-only search" in text
    # Degraded blend has no vec channel; indexed tsquery match is the gate.
    assert "0.80 * s.lex + 0.20 * s.recency" in text
    assert "m.content_tsv @@ p.tsq" in text
    assert "numnode(p.tsq) > 0" in text
    # Every fence appears in all THREE fence carriers: the hybrid arm, the
    # lexical arm, and (since 2026-07-28) memory_scope_count — the free COUNT
    # behind the empty-result diagnosis. The count is raised VISIBLY rather
    # than relaxed to >=: a fence dropped from any one carrier still takes the
    # number below the pin and reds this gate. memory_scope_count MUST stay
    # fence-identical or an empty store would be reported as "N rows were in
    # scope and none cleared the floor", which is the opposite diagnosis.
    assert text.count("ANY(string_to_array(:'st_filter', ','))") == 3
    assert text.count(
        "AND (:'cid' = '' OR m.cabinet_id = :'cid' OR m.cabinet_id = 'main')"
    ) == 3
    assert text.count("AND (:'as_of' = '' OR (m.source_created_at IS NOT NULL") == 3
    assert text.count("m.superseded_by IS NULL") == 3
    # 8-col output parity (same SELECT tail in both arms).
    assert text.count("COALESCE(source_id, id::text) as ref") == 2
    # min_score stays a vec-only floor: exactly the hybrid arm applies it.
    assert text.count("vec_sim >= (:'min_score')::float8") == 1


def test_memory_search_keyless_functional_lexical_fallback(tmp_path):
    """Functional keyless run: VOYAGE_API_KEY unset + a stub psql on PATH.
    memory_search must (1) not emit 'Embedding failed', (2) WARN on stderr,
    (3) run the LEXICAL SQL (tsquery match, no ::vector cast), (4) pass the
    query + tenant via parameterized -v args, (5) return the stub's TSV row
    on stdout with exit 0. No network, no Neon, no Voyage."""
    import os

    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    row = ("working_note\tcos\t2026-07-06 10:00\t0.910\t0.780\tderived\t"
           "Redis stream wiring note\t42")
    (tmp_path / "rows.tsv").write_text(row + "\n")
    psql = stub_dir / "psql"
    psql.write_text(
        "#!/bin/bash\n"
        f"printf '%s\\n' \"$@\" > '{tmp_path}/psql_args'\n"
        f"cat > '{tmp_path}/psql_sql'\n"
        f"cat '{tmp_path}/rows.tsv'\n"
    )
    psql.chmod(0o755)

    proc = _run_bash(
        f'source "{MEMORY_SH}" && memory_search "redis stream wiring" "" "" 5',
        env={
            # VOYAGE_API_KEY deliberately ABSENT (keyless scratch env);
            # NEON+CABINET_ID set so the lib never back-fills from cabinet/.env.
            "NEON_CONNECTION_STRING": "postgresql://placeholder",
            "CABINET_ID": "testcab",
            "PATH": f"{stub_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        },
    )
    assert proc.returncode == 0, proc.stderr
    assert "Embedding failed" not in proc.stdout
    assert row in proc.stdout
    assert "DEGRADED to lexical-only search" in proc.stderr
    sql = (tmp_path / "psql_sql").read_text()
    assert "m.content_tsv @@ p.tsq" in sql
    assert "::vector" not in sql
    args = (tmp_path / "psql_args").read_text().splitlines()
    assert "query=redis stream wiring" in args
    assert "cid=testcab" in args
    assert not any(a.startswith("embedding=") for a in args)


# ---------------------------------------------------------------------------
# WRITE CONFIRMATION (2026-07-28). memory_embed used to report SUCCESS for a
# row that never landed: psql WITHOUT ON_ERROR_STOP exits 0 even when the
# statement it ran ERRORed, and memory_embed suppresses psql's stderr. Measured
# against a live Postgres 17 + pgvector store: an `officer` past the column's
# VARCHAR(16) (and a `source_type` past VARCHAR(32), and content Postgres
# rejects as invalid UTF-8) each gave rc=0 with 0 rows stored, after which
# memory-worker.sh logged "processed: N ok, 0 failed" and XACKed the queue
# entry — the memory was gone with a green log line.
#
# The stubs below encode the MEASURED psql behaviour, not the fix's mechanism:
# the failure stub exits 0 and prints nothing (exactly what real psql does
# without ON_ERROR_STOP), so the arm passes only if the id check — not the
# exit code — is what refuses. memory_get_embedding is overridden to a
# constant vector, so these run with no network, no Voyage key and no jq
# dependency on the embed path.
# ---------------------------------------------------------------------------
_EMBED_STUB = 'memory_get_embedding() { printf "[0.1,0.2]"; }; '
_EMBED_CALL = (
    'memory_embed sometype some/id someofficer somesender '
    '"real content that must be stored" "{}" "2026-07-01T00:00:00Z"'
)


def _psql_stub(tmp_path, stdout_text: str):
    """A psql stub that always exits 0 (the measured no-ON_ERROR_STOP
    behaviour) and prints exactly what the real client printed."""
    import os

    stub_dir = tmp_path / "bin"
    stub_dir.mkdir(exist_ok=True)
    psql = stub_dir / "psql"
    psql.write_text(
        "#!/bin/bash\n"
        f"printf '%s\\n' \"$@\" > '{tmp_path}/psql_args'\n"
        "cat > /dev/null\n"
        f"cat '{tmp_path}/psql_stdout'\n"
        "exit 0\n"
    )
    psql.chmod(0o755)
    (tmp_path / "psql_stdout").write_text(stdout_text)
    return {
        "NEON_CONNECTION_STRING": "postgresql://placeholder",
        "CABINET_ID": "testcab",
        "PATH": f"{stub_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}",
    }


def test_memory_embed_refuses_success_when_no_row_landed(tmp_path):
    """Failed INSERT: psql exits 0 and prints nothing (measured). memory_embed
    must return NON-ZERO so memory-worker retries and eventually DLQs, instead
    of XACKing a lost write."""
    env = _psql_stub(tmp_path, "")
    proc = _run_bash(f'source "{MEMORY_SH}" && {_EMBED_STUB} {_EMBED_CALL}', env=env)
    assert proc.returncode != 0, (
        "memory_embed reported success for an INSERT that stored nothing "
        f"(stdout={proc.stdout!r} stderr={proc.stderr!r})"
    )


def test_memory_embed_reports_success_when_the_row_lands(tmp_path):
    """The other direction — the guard must not refuse a real write. Stdout is
    the real psql -q rendering of `RETURNING id` captured from a live store."""
    env = _psql_stub(tmp_path, "  id  \n-----\n 219\n(1 row)\n")
    proc = _run_bash(f'source "{MEMORY_SH}" && {_EMBED_STUB} {_EMBED_CALL}', env=env)
    assert proc.returncode == 0, f"stderr={proc.stderr!r}"
    assert "219" in proc.stdout


def test_memory_embed_passes_on_error_stop_to_psql(tmp_path):
    """Second, independent guard: psql is told to fail loudly (exit 3) rather
    than swallow a statement error. Asserted from the stub's captured argv."""
    env = _psql_stub(tmp_path, "  id  \n-----\n 219\n(1 row)\n")
    _run_bash(f'source "{MEMORY_SH}" && {_EMBED_STUB} {_EMBED_CALL}', env=env)
    args = (tmp_path / "psql_args").read_text().splitlines()
    assert "ON_ERROR_STOP=1" in args
