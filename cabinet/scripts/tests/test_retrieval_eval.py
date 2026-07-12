"""Retrieval-quality eval locks — recall@k + MRR gate for memory_search (R1,
2026-07-12 — org-memory study §5-R1).

Two layers, matching the study's "at minimum a runnable script + a doctor/CI
hook" bar:

  * OFFLINE (always run, no network/Neon/Voyage): the harvester + runner parse
    (``bash -n``), the committed seed is well-formed, the runner carries a floor
    + exit-code contract, and the default harvest set EXCLUDES the exhaust types
    (officer_trigger / trigger-archive / transcript-digest) — harvesting those
    would make the eval measure nervous-system noise, not knowledge (study C3).

  * LIVE GATE (skipped unless Neon is reachable): self-harvests a FRESH eval set
    from THIS cabinet's own cabinet_memory and asserts recall@k >= floor AND
    MRR >= mrr-floor. Two floors because they trip on different damage
    (R1-EVAL-NO-TEETH): recall@k catches pool damage (row evicted) but is
    order-blind at limit==k, while the MRR floor catches order damage — a
    worst-first rerank keeps recall@10 ~0.95 while MRR collapses to ~0.10.
    Run with --limit > k so the k-cut is order-sensitive too. It is
    store-agnostic (self-generating), so a fresh instance enforces the same gate
    on its own memory with no portable seed. Keyless/CI runs stay green (skip).

Run: python3 -m pytest cabinet/scripts/tests/test_retrieval_eval.py -q
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

# Captured at import time: a sibling test patches the global subprocess.Popen
# and the patch can leak across modules in a whole-repo run — restore the real
# one around our spawns (same guard as test_bootstrap_memory_chain.py).
_REAL_POPEN = subprocess.Popen

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
HARVEST = _SCRIPTS_DIR / "harvest-retrieval-eval.sh"
RUNNER = _SCRIPTS_DIR / "retrieval-eval.sh"
SEED = _SCRIPTS_DIR / "tests/fixtures/retrieval-eval-pairs.seed.json"

_EXHAUST_TYPES = ("officer_trigger", "trigger-archive", "transcript-digest")


def _run(cmd, timeout=60, env=None):
    patched = subprocess.Popen
    subprocess.Popen = _REAL_POPEN
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=env
        )
    finally:
        subprocess.Popen = patched


def _bash_n(path: Path) -> None:
    p = _run(["bash", "-n", str(path)])
    assert p.returncode == 0, f"bash -n {path.name} failed: {p.stderr}"


# ---------------------------------------------------------------------------
# offline — the scripts parse
# ---------------------------------------------------------------------------

def test_harvester_parses():
    _bash_n(HARVEST)


def test_runner_parses():
    _bash_n(RUNNER)


# ---------------------------------------------------------------------------
# offline — the committed seed is well-formed
# ---------------------------------------------------------------------------

def test_seed_is_valid_and_populated():
    data = json.loads(SEED.read_text())
    pairs = data.get("pairs")
    assert isinstance(pairs, list) and len(pairs) >= 15, (
        "seed must carry >=15 query->ref pairs (regression fixture)"
    )
    assert isinstance(data.get("recall_k"), int) and data["recall_k"] >= 1
    for p in pairs:
        assert p.get("query", "").strip(), f"empty query in seed pair: {p}"
        assert p.get("expected_ref", "").strip(), f"empty expected_ref: {p}"


def test_seed_has_no_secret_shaped_queries():
    """Queries are content-derived — guard against a future harvest accidentally
    baking a token/key/connection-string into the committed fixture."""
    data = json.loads(SEED.read_text())
    blob = "\n".join(p.get("query", "") for p in data["pairs"])
    for pat in (r"sk-[A-Za-z0-9]{8}", r"\bBearer\b", r"postgres(?:ql)?://",
                r"password\s*[:=]", r"[A-Za-z0-9_\-]{40,}"):
        assert not re.search(pat, blob, re.I), f"seed query matches secret-shape /{pat}/"


# ---------------------------------------------------------------------------
# offline — the runner carries the gate contract
# ---------------------------------------------------------------------------

def test_runner_has_floor_and_recall_contract():
    txt = RUNNER.read_text()
    assert "--floor" in txt, "runner lost the --floor gate arg"
    assert re.search(r'^FLOOR="?0', txt, re.M), "runner lost its default floor"
    assert "recall@" in txt, "runner no longer reports recall@k"
    # exit-code contract: pass -> 0, below floor -> 1
    assert "exit 1" in txt and "exit 0" in txt


def test_runner_has_mrr_floor_gate():
    """R1-EVAL-NO-TEETH: recall@k with limit==k is order-blind — a rerank
    sorted worst-first passed the old gate (recall 0.95) while MRR collapsed
    0.925 -> ~0.10. The MRR floor is the order-sensitivity teeth; losing it
    reopens the hole."""
    txt = RUNNER.read_text()
    assert "--mrr-floor" in txt, "runner lost the --mrr-floor gate arg"
    assert re.search(r'^MRR_FLOOR="?0\.5', txt, re.M), (
        "runner lost its default MRR floor (0.50 — baseline ~0.925, "
        "order-inverted ranker ~0.10)"
    )
    assert "MRR_PASS" in txt, "runner no longer gates on MRR in PASS logic"
    # recall HITs must honor the k-cut, or --limit > k silently inflates recall
    assert re.search(r'-le\s+"\$K"', txt), (
        "runner lost the rank<=k cut on recall hits"
    )


def test_harvester_excludes_exhaust_types():
    txt = HARVEST.read_text()
    m = re.search(r'^TYPES="([^"]+)"', txt, re.M)
    assert m, "harvester lost its default TYPES set"
    default_types = m.group(1)
    for exhaust in _EXHAUST_TYPES:
        assert exhaust not in default_types, (
            f"harvester default set must exclude exhaust type '{exhaust}' "
            f"(study C3 — harvesting noise measures noise)"
        )


# ---------------------------------------------------------------------------
# live gate — self-harvest from the current store, enforce recall floor
# ---------------------------------------------------------------------------

def _env_val(name: str) -> str:
    """Resolve a secret the way memory.sh does: env first, else cabinet/.env
    (regex-extracted, NEVER printed)."""
    v = os.environ.get(name, "").strip()
    if v:
        return v
    envf = _REPO_ROOT / "cabinet/.env"
    if envf.exists():
        for line in envf.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _neon_reachable(conn: str) -> bool:
    if not conn:
        return False
    p = _run(
        ["psql", conn, "-tAc", "SELECT 1;"],
        timeout=20,
        env={**os.environ, "PGCONNECT_TIMEOUT": "10"},
    )
    return p.returncode == 0 and "1" in p.stdout


def test_live_recall_gate_self_harvested():
    conn = _env_val("NEON_CONNECTION_STRING")
    if not _neon_reachable(conn):
        pytest.skip("Neon not reachable — live retrieval gate skipped (keyless/CI safe)")

    # Faithfully exercise the production hybrid+rerank path whenever creds exist
    # anywhere (env OR cabinet/.env); pass both into the child env.
    child_env = {**os.environ, "CABINET_ROOT": str(_REPO_ROOT),
                 "NEON_CONNECTION_STRING": conn}
    vkey = _env_val("VOYAGE_API_KEY")
    if vkey:
        child_env["VOYAGE_API_KEY"] = vkey
    cid = _env_val("CABINET_ID")
    if cid:
        child_env["CABINET_ID"] = cid

    fd, pairs_path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        h = _run(["bash", str(HARVEST), "--limit", "12", "--out", pairs_path],
                 timeout=180, env=child_env)
        assert h.returncode == 0, f"harvest failed: {h.stderr}"
        # floor 0.60 for the small self-harvested sample: absorbs sample variance
        # and a lone Voyage hiccup while still tripping on a real ranker break
        # (baseline recall@10 on durable-knowledge rows is ~0.9).
        # --mrr-floor 0.50 is the ORDER gate (R1-EVAL-NO-TEETH): recall@k alone
        # is order-blind at limit==k — a worst-first rerank kept recall at 0.95
        # while MRR collapsed 0.925 -> ~0.10; only the MRR floor trips on that.
        # --limit 20 > k=10 makes the k-cut order-sensitive as well (a found-
        # but-buried row now counts as a recall MISS instead of being invisible).
        r = _run(["bash", str(RUNNER), "--pairs", pairs_path, "--floor", "0.60",
                  "--mrr-floor", "0.50", "--limit", "20", "--json"],
                 timeout=240, env=child_env)
        assert r.returncode == 0, (
            f"retrieval gate FAILED — memory_search ranking regressed "
            f"(recall < floor OR MRR < mrr-floor). stdout={r.stdout} stderr={r.stderr}"
        )
        summary = json.loads(r.stdout)
        assert summary["pass"] is True
        assert summary["mrr_floor"] == 0.50, f"mrr floor not applied: {summary}"
        assert summary["mrr"] >= 0.50, f"MRR below floor yet pass=true: {summary}"
        assert summary["total"] >= 8, f"too few usable pairs: {summary}"
    finally:
        os.unlink(pairs_path)
