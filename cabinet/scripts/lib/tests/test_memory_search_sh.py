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
