"""Functional locks for the memory_rerank NO-RERANK seam (Lane D, 2026-07-15).

CABINET_MEMORY_RERANK=off must short-circuit memory_rerank to the BLENDED
top-k cut WITHOUT touching the network — the retrieval-eval no-rerank arm
rides this seam to measure blended ranking with the rerank rescue disabled
(the R1 landing's named residual: rerank hides pool/weight damage).

No network, no Neon, no Voyage: the real cabinet/scripts/lib/memory.sh is
sourced and memory_rerank is driven directly with a canned 9-column pool; a
PATH-shimmed `curl` records whether the rerank endpoint would have been hit
and returns a VALID inverted-order rerank response — so the control test
proves the shim is load-bearing, not vacuously green.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

# Same leak guard as test_memory_search_sh.py (a sibling test patches the
# global subprocess.Popen; restore the real one around our spawns).
_REAL_POPEN = subprocess.Popen

SCRIPTS_DIR = Path(__file__).resolve().parents[2]  # cabinet/scripts
MEMORY_SH = SCRIPTS_DIR / "lib" / "memory.sh"

# 3 pool rows, 9 tab columns each (col 8 = ref, col 9 = rerank_text).
POOL_ROWS = [
    "\t".join(["t", "who", "2026-07-01 00:00", "0.900", "0.800", "derived",
               f"preview {i}", f"ref-{i}", f"doc {i}"])
    for i in (1, 2, 3)
]


def _cols18(row: str) -> str:
    return "\t".join(row.split("\t")[:8])


def _run_rerank(tmp_path, env_extra, topk=2):
    """Source the REAL memory.sh, run memory_rerank over the canned pool with
    a sentinel-writing curl shim on PATH. Returns (proc, sentinel_hit)."""
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir(exist_ok=True)
    sentinel = tmp_path / "curl_was_called"
    # Valid Voyage-shaped response, deliberately INVERTED order (index 2 best)
    # so "rerank ran" and "rerank skipped" produce DIFFERENT output.
    (shim_dir / "curl").write_text(
        "#!/bin/bash\n"
        f"touch '{sentinel}'\n"
        'printf \'%s\' \'{"data":[{"index":2,"relevance_score":0.9},'
        '{"index":1,"relevance_score":0.5},{"index":0,"relevance_score":0.1}]}\'\n'
    )
    (shim_dir / "curl").chmod(0o755)
    pool_file = tmp_path / "pool.tsv"
    pool_file.write_text("\n".join(POOL_ROWS) + "\n")
    env = {
        "PATH": f"{shim_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        # NEON + CABINET_ID set so the lib never back-fills from cabinet/.env.
        "NEON_CONNECTION_STRING": "postgresql://placeholder",
        "CABINET_ID": "testcab",
        "VOYAGE_API_KEY": "dummy-key-never-sent",
    }
    env.update(env_extra)
    patched = subprocess.Popen
    subprocess.Popen = _REAL_POPEN
    try:
        proc = subprocess.run(
            ["bash", "-c",
             f'source "{MEMORY_SH}" && memory_rerank "q" {topk} "$(cat "{pool_file}")"'],
            capture_output=True, text=True, env=env,
        )
    finally:
        subprocess.Popen = patched
    return proc, sentinel.exists()


def test_seam_off_emits_blended_order_and_never_calls_curl(tmp_path):
    proc, curl_hit = _run_rerank(tmp_path, {"CABINET_MEMORY_RERANK": "off"})
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == [_cols18(POOL_ROWS[0]), _cols18(POOL_ROWS[1])]
    assert not curl_hit, (
        "CABINET_MEMORY_RERANK=off must short-circuit BEFORE any network call"
    )


def test_seam_off_is_case_insensitive(tmp_path):
    proc, curl_hit = _run_rerank(tmp_path, {"CABINET_MEMORY_RERANK": "OFF"})
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == [_cols18(POOL_ROWS[0]), _cols18(POOL_ROWS[1])]
    assert not curl_hit


def test_default_path_reranks_via_endpoint_negative_control(tmp_path):
    """Control proving the shim has teeth: with the seam UNSET the rerank
    stage runs, hits (shimmed) curl, and applies the inverted order — so the
    seam-off assertions above cannot pass vacuously."""
    proc, curl_hit = _run_rerank(tmp_path, {})
    assert proc.returncode == 0, proc.stderr
    assert curl_hit, "default path must exercise the rerank endpoint"
    assert proc.stdout.splitlines() == [_cols18(POOL_ROWS[2]), _cols18(POOL_ROWS[1])], (
        "shimmed inverted rerank order must be applied on the default path"
    )


def test_unknown_seam_value_keeps_rerank_on(tmp_path):
    """Fail-open-to-today contract: junk values are NOT off — only the
    documented off|0|no|false set disables rerank."""
    proc, curl_hit = _run_rerank(tmp_path, {"CABINET_MEMORY_RERANK": "banana"})
    assert proc.returncode == 0, proc.stderr
    assert curl_hit
    assert proc.stdout.splitlines()[0] == _cols18(POOL_ROWS[2])


def test_ranking_block_markers_present_in_memory_sh():
    """The fingerprint stamper/CI guard extract awk ranges over these marker
    tokens — losing them silently empties the ranking-change guard."""
    text = MEMORY_SH.read_text()
    assert text.count("RANKING-BLOCK-BEGIN") == 2
    assert text.count("RANKING-BLOCK-END") == 2
    assert "CABINET_MEMORY_RERANK" in text
