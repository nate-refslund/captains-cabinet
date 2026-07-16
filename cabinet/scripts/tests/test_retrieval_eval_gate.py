"""Standing-gate locks for the retrieval REFINEMENT GATE (Lane D, 2026-07-15).

The R1 eval (retrieval-eval.sh, @960d4c4d) landed gating NOTHING and with a
named residual: rerank rescues pool damage, so a blended weight-swap passed
while rerank was live. This suite pins the wiring that closes both, ALL
OFFLINE (no Neon, no Voyage, no network — fixture trees + stub memory lib):

  * NO-RERANK ARM: retrieval-eval.sh --no-rerank exports the
    CABINET_MEMORY_RERANK=off seam and measures BLENDED order. Required
    negative control: an ascending-sort (worst-first) mutant of the blended
    order FAILS the no-rerank arm (MRR collapse) while the rerank arm still
    passes — a blended-arm breach is a real finding even when rerank is green.
  * NIGHTLY WRAPPER (retrieval-eval-nightly.sh): one verdict JSONL line per
    run (append-only, jq-composed), breach → exit 1, credless box → clean
    skip with NO fabricated verdict, harvest-empty → status=no-pairs,
    --stamp gated on a BOTH-ARM pass.
  * DOCTOR FEED (--probe): NOCREDS/NOFILE/OK/BREACH/NOTOK/BADLINE plus the
    48h staleness boundary (47h fresh / 49h stale), pure file+env inspection.
  * RANKING-CHANGE GUARD: the committed fingerprint fixture must equal the
    sha256 of the RANKING-BLOCK marker regions of lib/memory.sh — any ranking
    edit is a red build until a passing store-local eval re-stamps it
    (bash cabinet/scripts/retrieval-eval-nightly.sh --stamp). Mutant negative
    controls + an out-of-block control against over-breadth + a bash-awk /
    python extraction parity pin (stamper and CI must hash the same bytes).
  * services.yml row (03:50 cron) + cabinet-doctor check-11 wiring pins.

Run: python3 -m pytest cabinet/scripts/tests/test_retrieval_eval_gate.py -q
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import subprocess
from pathlib import Path

import yaml

# Captured at import time: a sibling test patches the global subprocess.Popen
# and the patch can leak across modules in a whole-repo run — restore the real
# one around our spawns (same guard as test_retrieval_eval.py).
_REAL_POPEN = subprocess.Popen

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
RUNNER = _SCRIPTS_DIR / "retrieval-eval.sh"
NIGHTLY = _SCRIPTS_DIR / "retrieval-eval-nightly.sh"
MEMORY_SH = _SCRIPTS_DIR / "lib" / "memory.sh"
DOCTOR = _SCRIPTS_DIR / "cabinet-doctor.sh"
FPRINT = _SCRIPTS_DIR / "tests" / "fixtures" / "memory-ranking.fingerprint"
SERVICES = _REPO_ROOT / "cabinet" / "services.yml"

N_PAIRS = 10

# Stub memory lib: serves canned rankings per query from $STUB_RANKDIR, picks
# the blended file when the CABINET_MEMORY_RERANK seam is off (mirroring the
# real seam's value set), records the seam value per call, and carries
# RANKING-BLOCK markers so --stamp is exercisable against the fixture tree.
STUB_MEMORY_SH = """#!/bin/bash
# stub memory library for offline retrieval-eval gate tests
memory_cabinet_scope() { printf '%s' "${CABINET_ID:-}"; }
# RANKING-BLOCK-BEGIN
STUB_RANK_WEIGHT="0.60"
# RANKING-BLOCK-END
memory_search() {
  local query="$1" limit="${4:-10}"
  printf '%s\\n' "${CABINET_MEMORY_RERANK:-unset}" >> "$STUB_RANKDIR/env_calls"
  local file="$STUB_RANKDIR/rerank.tsv"
  case "$(printf '%s' "${CABINET_MEMORY_RERANK:-on}" | tr '[:upper:]' '[:lower:]')" in
    off|0|no|false) file="$STUB_RANKDIR/blended.tsv" ;;
  esac
  awk -F'\\t' -v q="$query" '$1==q {print $2}' "$file" | tr ',' '\\n' | head -n "$limit" \\
    | awk '{printf "stub\\tn/a\\t2026-07-01 00:00\\t0.900\\t0.800\\tderived\\tpreview\\t%s\\n", $0}'
}
"""


def _run(cmd, timeout=60, env=None, cwd=None):
    patched = subprocess.Popen
    subprocess.Popen = _REAL_POPEN
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd
        )
    finally:
        subprocess.Popen = patched


def _rankings(bury_at=None, drop=False):
    """query -> ordered refs. Healthy default: expected ref first. bury_at=N
    puts it at rank N (1-based); drop=True evicts it from the pool entirely."""
    out = {}
    for i in range(1, N_PAIRS + 1):
        decoys = [f"decoy-{i}-{j}" for j in range(1, N_PAIRS)]
        if drop:
            refs = decoys + [f"decoy-{i}-extra"]
        elif bury_at is None:
            refs = [f"ref-{i}"] + decoys
        else:
            refs = decoys[:]
            refs.insert(bury_at - 1, f"ref-{i}")
        out[f"query topic {i}"] = refs
    return out


def _write_rankings(path: Path, rankings: dict) -> None:
    with open(path, "w") as f:
        for q, refs in rankings.items():
            f.write(f"{q}\t{','.join(refs)}\n")


def _mk_fixture(tmp_path, rerank=None, blended=None):
    """Fixture CABINET_ROOT tree + rankings dir + pairs file."""
    root = tmp_path / "cabroot"
    (root / "cabinet" / "logs").mkdir(parents=True)
    (root / "cabinet" / "scripts" / "lib").mkdir(parents=True)
    (root / "cabinet" / "scripts" / "tests" / "fixtures").mkdir(parents=True)
    (root / "cabinet" / "scripts" / "lib" / "memory.sh").write_text(STUB_MEMORY_SH)
    rankdir = tmp_path / "rank"
    rankdir.mkdir()
    _write_rankings(rankdir / "rerank.tsv", rerank or _rankings())
    _write_rankings(rankdir / "blended.tsv", blended or _rankings())
    pairs = tmp_path / "pairs.json"
    pairs.write_text(json.dumps({
        "recall_k": 10,
        "pairs": [{"query": f"query topic {i}", "expected_ref": f"ref-{i}"}
                  for i in range(1, N_PAIRS + 1)],
    }))
    return root, rankdir, pairs


def _env(root, rankdir, **extra):
    e = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "CABINET_ROOT": str(root),
        "STUB_RANKDIR": str(rankdir),
        "NEON_CONNECTION_STRING": "postgresql://placeholder",
    }
    e.update(extra)
    return e


def _hist(root: Path) -> Path:
    return root / "cabinet" / "logs" / "retrieval-eval-history.jsonl"


def _fprint(root: Path) -> Path:
    return root / "cabinet" / "scripts" / "tests" / "fixtures" / "memory-ranking.fingerprint"


def _iso(dt: datetime.datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


# ---------------------------------------------------------------------------
# scripts parse
# ---------------------------------------------------------------------------

def test_nightly_parses_and_helps():
    p = _run(["bash", "-n", str(NIGHTLY)])
    assert p.returncode == 0, f"bash -n failed: {p.stderr}"
    h = _run(["bash", str(NIGHTLY), "--help"],
             env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")})
    assert h.returncode == 0
    for token in ("--probe", "--stamp", "--pairs", "no-rerank"):
        assert token in h.stdout, f"--help lost {token}"


# ---------------------------------------------------------------------------
# the no-rerank arm (runner level)
# ---------------------------------------------------------------------------

def test_runner_no_rerank_arm_healthy_and_env_recorded(tmp_path):
    root, rankdir, pairs = _mk_fixture(tmp_path)
    p = _run(["bash", str(RUNNER), "--no-rerank", "--pairs", str(pairs),
              "--floor", "0.60", "--mrr-floor", "0.50", "--limit", "10",
              "--json", "--quiet"], env=_env(root, rankdir))
    assert p.returncode == 0, f"stdout={p.stdout} stderr={p.stderr}"
    v = json.loads(p.stdout)
    assert v["arm"] == "no-rerank"
    assert v["pass"] is True and v["recall_at_k"] == 1.0 and v["mrr"] == 1.0
    # The seam env reached every memory_search call.
    calls = (rankdir / "env_calls").read_text().split()
    assert calls and set(calls) == {"off"}, calls


def test_runner_default_arm_leaves_seam_unset(tmp_path):
    root, rankdir, pairs = _mk_fixture(tmp_path)
    p = _run(["bash", str(RUNNER), "--pairs", str(pairs), "--floor", "0.60",
              "--mrr-floor", "0.50", "--limit", "10", "--json", "--quiet"],
             env=_env(root, rankdir))
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["arm"] == "rerank"
    calls = (rankdir / "env_calls").read_text().split()
    assert calls and set(calls) == {"unset"}, calls


def test_runner_inherited_seam_env_labels_arm_honestly(tmp_path):
    """CABINET_MEMORY_RERANK=off inherited WITHOUT the flag must still label
    the verdict no-rerank — never a mislabeled rerank verdict."""
    root, rankdir, pairs = _mk_fixture(tmp_path)
    p = _run(["bash", str(RUNNER), "--pairs", str(pairs), "--json", "--quiet",
              "--floor", "0.60", "--mrr-floor", "0.50", "--limit", "10"],
             env=_env(root, rankdir, CABINET_MEMORY_RERANK="off"))
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["arm"] == "no-rerank"


def test_ascending_sort_blended_mutant_fails_no_rerank_arm_only(tmp_path):
    """THE required negative control (R1 residual): blended order sorted
    worst-first (expected ref buried at rank 10 of 10) keeps recall@10 = 1.0
    but collapses MRR to 0.10 — the no-rerank arm MUST fail on the MRR floor
    while the rerank arm (healthy) passes. Without the no-rerank arm this
    damage is invisible: rerank rescues the pool."""
    root, rankdir, pairs = _mk_fixture(tmp_path, blended=_rankings(bury_at=10))
    common = ["--pairs", str(pairs), "--floor", "0.60", "--mrr-floor", "0.50",
              "--limit", "10", "--json", "--quiet"]
    bad = _run(["bash", str(RUNNER), "--no-rerank"] + common, env=_env(root, rankdir))
    assert bad.returncode == 1, (
        f"ascending-sort blended mutant must FAIL the no-rerank arm "
        f"(stdout={bad.stdout})"
    )
    v = json.loads(bad.stdout)
    assert v["pass"] is False and v["arm"] == "no-rerank"
    assert v["recall_at_k"] == 1.0, "order damage must not look like pool damage"
    assert abs(v["mrr"] - 0.10) < 1e-6, v
    ok = _run(["bash", str(RUNNER)] + common, env=_env(root, rankdir))
    assert ok.returncode == 0, (
        "rerank arm must still pass — a blended-arm breach is a real finding "
        f"even when the rerank arm is green (stderr={ok.stderr})"
    )


def test_mrr_math_pin_rank4_burial(tmp_path):
    """Burying every expected ref at rank 4 must yield MRR exactly 0.25 with
    recall@10 still 1.0 — pins the reciprocal-rank arithmetic the floors gate."""
    root, rankdir, pairs = _mk_fixture(tmp_path, blended=_rankings(bury_at=4))
    p = _run(["bash", str(RUNNER), "--no-rerank", "--pairs", str(pairs),
              "--floor", "0.60", "--mrr-floor", "0.50", "--limit", "10",
              "--json", "--quiet"], env=_env(root, rankdir))
    assert p.returncode == 1
    v = json.loads(p.stdout)
    assert abs(v["mrr"] - 0.25) < 1e-6 and v["recall_at_k"] == 1.0, v


def test_eviction_mutant_trips_recall_floor(tmp_path):
    """Pool damage (expected refs evicted entirely) must trip the RECALL floor
    on the no-rerank arm — the other half of the two-floor design."""
    root, rankdir, pairs = _mk_fixture(tmp_path, blended=_rankings(drop=True))
    p = _run(["bash", str(RUNNER), "--no-rerank", "--pairs", str(pairs),
              "--floor", "0.60", "--mrr-floor", "0.50", "--limit", "10",
              "--json", "--quiet"], env=_env(root, rankdir))
    assert p.returncode == 1
    v = json.loads(p.stdout)
    assert v["recall_at_k"] == 0.0 and v["pass"] is False, v


# ---------------------------------------------------------------------------
# nightly wrapper — verdict ledger + exit contract + stamp gating
# ---------------------------------------------------------------------------

def test_nightly_pass_appends_schema_line_and_is_append_only(tmp_path):
    root, rankdir, pairs = _mk_fixture(tmp_path)
    env = _env(root, rankdir)
    for expected_lines in (1, 2):
        p = _run(["bash", str(NIGHTLY), "--pairs", str(pairs)], env=env)
        assert p.returncode == 0, f"stdout={p.stdout} stderr={p.stderr}"
        lines = _hist(root).read_text().splitlines()
        assert len(lines) == expected_lines, "one verdict line per run, append-only"
    v = json.loads(lines[-1])
    assert v["status"] == "ok" and v["pass"] is True
    assert v["arms"]["rerank"]["arm"] == "rerank"
    assert v["arms"]["blended"]["arm"] == "no-rerank"
    assert v["floors"]["recall"] == 0.6
    # ts is ISO-8601 Zulu (the probe's staleness clock parses exactly this).
    datetime.datetime.strptime(v["ts"], "%Y-%m-%dT%H:%M:%SZ")


def test_nightly_blended_breach_exits_1_and_records_arm_detail(tmp_path):
    root, rankdir, pairs = _mk_fixture(tmp_path, blended=_rankings(bury_at=10))
    p = _run(["bash", str(NIGHTLY), "--pairs", str(pairs)], env=_env(root, rankdir))
    assert p.returncode == 1, "a floor breach must surface to launchd (exit 1)"
    v = json.loads(_hist(root).read_text().splitlines()[-1])
    assert v["pass"] is False
    assert v["arms"]["rerank"]["pass"] is True
    assert v["arms"]["blended"]["pass"] is False, (
        "the ledger must show WHICH arm breached"
    )


def test_nightly_credless_box_skips_clean_without_fabricating_verdicts(tmp_path):
    root, rankdir, pairs = _mk_fixture(tmp_path)
    env = _env(root, rankdir)
    del env["NEON_CONNECTION_STRING"]  # stub lib never back-fills
    p = _run(["bash", str(NIGHTLY), "--pairs", str(pairs)], env=env)
    assert p.returncode == 0, p.stderr
    assert "Skipping clean" in p.stdout
    assert not _hist(root).exists(), "a credless box must not fabricate verdicts"


def test_nightly_empty_harvest_appends_no_pairs_line(tmp_path):
    root, rankdir, _pairs = _mk_fixture(tmp_path)
    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    (stub_bin / "psql").write_text("#!/bin/bash\nexit 0\n")  # harvest sees no rows
    (stub_bin / "psql").chmod(0o755)
    env = _env(root, rankdir)
    env["PATH"] = f"{stub_bin}:{env['PATH']}"
    p = _run(["bash", str(NIGHTLY)], env=env)  # no --pairs → harvest path
    assert p.returncode == 0, f"stdout={p.stdout} stderr={p.stderr}"
    v = json.loads(_hist(root).read_text().splitlines()[-1])
    assert v["status"] == "no-pairs" and v["pass"] is None, v


def test_nightly_stamp_gated_on_both_arm_pass(tmp_path):
    # Breach run: --stamp must REFUSE (no fingerprint written).
    root, rankdir, pairs = _mk_fixture(tmp_path, blended=_rankings(bury_at=10))
    p = _run(["bash", str(NIGHTLY), "--pairs", str(pairs), "--stamp"],
             env=_env(root, rankdir))
    assert p.returncode == 1
    assert "REFUSED" in p.stdout + p.stderr
    assert not _fprint(root).exists(), (
        "--stamp on a breach must never regenerate the fingerprint"
    )
    # Healthy run: stamps, and the hex equals the python-computed sha of the
    # stub lib's RANKING-BLOCK region (stamper/CI extraction agreement).
    _write_rankings(rankdir / "blended.tsv", _rankings())
    p2 = _run(["bash", str(NIGHTLY), "--pairs", str(pairs), "--stamp"],
              env=_env(root, rankdir))
    assert p2.returncode == 0, p2.stderr
    stamped = _read_fingerprint_hex(_fprint(root))
    stub_lib = root / "cabinet" / "scripts" / "lib" / "memory.sh"
    assert stamped == _sha256(_ranking_block(stub_lib.read_text()))


# ---------------------------------------------------------------------------
# --probe: the doctor feed (pure file+env inspection)
# ---------------------------------------------------------------------------

def _probe(root, extra_env=None):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "CABINET_ROOT": str(root)}
    env.update(extra_env or {})
    p = _run(["bash", str(NIGHTLY), "--probe"], env=env)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


def _probe_line(root, ts, pass_val, status="ok"):
    _hist(root).parent.mkdir(parents=True, exist_ok=True)
    _hist(root).write_text(json.dumps({
        "ts": ts, "status": status, "pass": pass_val,
        "arms": {"rerank": {"recall_at_k": 1.0, "mrr": 0.9},
                 "blended": {"recall_at_k": 0.9, "mrr": 0.7}},
    }) + "\n")


def test_probe_nocreds_then_creds_via_env_and_envfile(tmp_path):
    root = tmp_path / "cabroot"
    (root / "cabinet").mkdir(parents=True)
    assert _probe(root) == "NOCREDS"
    # env-provided creds flip it to NOFILE (no ledger yet)
    assert _probe(root, {"NEON_CONNECTION_STRING": "postgresql://x"}) == "NOFILE"
    # NAME present in cabinet/.env resolves too (value never surfaces)
    (root / "cabinet" / ".env").write_text('NEON_CONNECTION_STRING="secret-dsn"\n')
    out = _probe(root)
    assert out == "NOFILE"
    assert "secret-dsn" not in out


def test_probe_ok_breach_notok_badline(tmp_path):
    root = tmp_path / "cabroot"
    (root / "cabinet").mkdir(parents=True)
    creds = {"NEON_CONNECTION_STRING": "postgresql://x"}
    now = _iso(_utcnow())
    _probe_line(root, now, True)
    assert _probe(root, creds).startswith("OK ")
    _probe_line(root, now, False)
    out = _probe(root, creds)
    assert out.startswith("BREACH ")
    assert "blended" in out, "breach detail must name per-arm numbers"
    _probe_line(root, now, None, status="no-pairs")
    assert _probe(root, creds).startswith("NOTOK status=no-pairs")
    _hist(root).write_text("not json at all\n")
    assert _probe(root, creds) == "BADLINE"


def test_probe_staleness_boundary_48h(tmp_path):
    """49h-old verdict = STALE (gate not running); 47h-old = still OK. A
    PASSING but stale line must NOT read as healthy — staleness wins."""
    root = tmp_path / "cabroot"
    (root / "cabinet").mkdir(parents=True)
    creds = {"NEON_CONNECTION_STRING": "postgresql://x"}
    _probe_line(root, _iso(_utcnow() - datetime.timedelta(hours=49)), True)
    assert _probe(root, creds).startswith("STALE ")
    _probe_line(root, _iso(_utcnow() - datetime.timedelta(hours=47)), True)
    assert _probe(root, creds).startswith("OK ")


# ---------------------------------------------------------------------------
# ranking-change guard: fingerprint pins the live ranking code
# ---------------------------------------------------------------------------

def _ranking_block(text: str) -> str:
    """Python twin of the stamper's awk range extraction
    (awk '/RANKING-BLOCK-BEGIN/,/RANKING-BLOCK-END/'): inclusive of both
    marker lines, all regions concatenated."""
    out, inside = [], False
    for line in text.splitlines(keepends=True):
        if "RANKING-BLOCK-BEGIN" in line:
            inside = True
        if inside:
            out.append(line)
        if "RANKING-BLOCK-END" in line:
            inside = False
    return "".join(out)


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _read_fingerprint_hex(path: Path) -> str:
    lines = [l.strip() for l in path.read_text().splitlines()
             if l.strip() and not l.strip().startswith("#")]
    assert len(lines) == 1, f"fingerprint file must carry exactly one hex line: {lines}"
    return lines[0]


def test_fingerprint_matches_live_ranking_block():
    """THE ranking-change guard: editing the blended weights / vec floor /
    rerank stage / no-rerank seam in lib/memory.sh without re-stamping via a
    PASSING store-local eval run (retrieval-eval-nightly.sh --stamp) is a red
    build. This is deliberately a cheap honesty ratchet, not cryptographic
    proof — the stamper refuses to stamp on a breach, and hand-editing the
    fixture is visible in review."""
    committed = _read_fingerprint_hex(FPRINT)
    live = _sha256(_ranking_block(MEMORY_SH.read_text()))
    assert committed == live, (
        "cabinet/scripts/lib/memory.sh ranking block changed but the "
        "fingerprint was not regenerated by a passing eval run. Run "
        "`bash cabinet/scripts/retrieval-eval-nightly.sh --stamp` store-local "
        "(it stamps only when BOTH arms hold their floors) and commit the "
        "refreshed cabinet/scripts/tests/fixtures/memory-ranking.fingerprint "
        "with your ranking change."
    )


def test_fingerprint_extraction_parity_with_awk():
    """The stamper hashes awk-range output; CI hashes the python extraction.
    They must agree byte-for-byte or the guard splits into two truths."""
    p = _run(["awk", "/RANKING-BLOCK-BEGIN/,/RANKING-BLOCK-END/", str(MEMORY_SH)])
    assert p.returncode == 0
    assert hashlib.sha256(p.stdout.encode("utf-8")).hexdigest() == _sha256(
        _ranking_block(MEMORY_SH.read_text())
    )


def test_weight_mutant_changes_fingerprint():
    text = MEMORY_SH.read_text()
    assert "0.60 * s.vec_sim + 0.25 * s.lex + 0.15 * s.recency" in text
    mutant = text.replace("0.60 * s.vec_sim", "0.61 * s.vec_sim")
    assert mutant != text
    assert _sha256(_ranking_block(mutant)) != _sha256(_ranking_block(text)), (
        "a blended weight edit must change the fingerprint (else the guard is blind)"
    )


def test_rerank_and_seam_mutants_change_fingerprint():
    text = MEMORY_SH.read_text()
    rerank_mutant = text.replace(
        "sort_by(-(.relevance_score // 0))", "sort_by(.relevance_score // 0)"
    )
    assert rerank_mutant != text
    assert _sha256(_ranking_block(rerank_mutant)) != _sha256(_ranking_block(text))
    seam_mutant = text.replace("off|0|no|false)", "no-such-value)")
    assert seam_mutant != text
    assert _sha256(_ranking_block(seam_mutant)) != _sha256(_ranking_block(text)), (
        "disabling the no-rerank seam must change the fingerprint"
    )


def test_out_of_block_edit_does_not_change_fingerprint():
    """Anti-over-breadth control: a comment edit OUTSIDE the marker regions
    (e.g. the file header) must NOT invalidate the fingerprint — the guard
    gates ranking code, not every memory.sh touch."""
    text = MEMORY_SH.read_text()
    mutant = "# unrelated header comment\n" + text
    assert _sha256(_ranking_block(mutant)) == _sha256(_ranking_block(text))


def test_marker_integrity_covers_weights_floor_rerank_and_seam():
    """The markers must keep enclosing the load-bearing ranking surface —
    shrinking them to exclude the weights would silently neuter the guard."""
    text = MEMORY_SH.read_text()
    assert text.count("RANKING-BLOCK-BEGIN") == 2, "expected exactly 2 BEGIN markers"
    assert text.count("RANKING-BLOCK-END") == 2, "expected exactly 2 END markers"
    block = _ranking_block(text)
    for token in (
        "0.60 * s.vec_sim + 0.25 * s.lex + 0.15 * s.recency",   # blended weights
        "0.80 * s.vec_sim + 0.20 * s.recency",                  # degraded renorm
        "vec_sim >= (:'min_score')::float8",                     # vec floor
        "ORDER BY final_score DESC",                             # pool order
        "memory_rerank()",                                       # rerank stage
        "_memory_blended_topk()",                                # blended cut
        "CABINET_MEMORY_RERANK",                                 # no-rerank seam
    ):
        assert token in block, f"ranking block no longer covers: {token}"


# ---------------------------------------------------------------------------
# wiring: services.yml row + doctor check
# ---------------------------------------------------------------------------

def test_services_row_retrieval_eval():
    data = yaml.safe_load(SERVICES.read_text())
    rows = [s for s in data["services"] if s.get("name") == "retrieval-eval"]
    assert len(rows) == 1, "services.yml must carry exactly one retrieval-eval row"
    row = rows[0]
    assert row["kind"] == "cron"
    assert not row.get("disabled"), "the gate ships armed"
    cal = row["schedule"]["calendar"]
    assert cal == [{"hour": 3, "minute": 50}], (
        "03:50 slot is load-bearing: after the 03:30 memory-reconcile (gate "
        "must measure the post-consolidation store), before the 07:10 doctor"
    )
    assert "retrieval-eval-nightly.sh" in row["command"]
    script = _REPO_ROOT / "cabinet" / "scripts" / "retrieval-eval-nightly.sh"
    assert script.is_file(), "manifest row points at a missing script"
    for token in ("no-rerank", "retrieval-eval-history.jsonl", "exit 1"):
        assert token in row["expected"], f"expected contract lost: {token}"


def test_doctor_check_wired_and_offline():
    """Doctor check 11 must consume the --probe feed with the right verdict
    ladder (NOCREDS→skip, BREACH→warn, staleness→wake-grace-aware) and stay
    a pure file probe — no psql/curl in the check body."""
    text = DOCTOR.read_text()
    assert "retrieval-eval-nightly.sh --probe" in text
    start = text.index("11. retrieval-eval nightly verdict — the refinement gate")
    end = text.index("verdict + heartbeat", start)
    body = text[start:end]
    assert 'NOCREDS*) skip' in body
    assert 'BREACH*)  warn' in body
    assert 'NOTOK*)   warn' in body
    assert 'BADLINE*) warn' in body
    assert "re_stale_verdict" in body, "staleness must ride the grace helper"
    assert 'STALE*)   re_stale_verdict' in body
    assert 'NOFILE*)  re_stale_verdict' in body
    # grace helper mirrors stale_verdict's wake-grace inputs, one rung lower
    assert "SECS_SINCE_WAKE" in body and "WAKE_GRACE_S" in body
    # the check itself must never reach for the store or the network
    assert "psql" not in body and "curl" not in body


def test_runner_help_documents_no_rerank_arm():
    text = RUNNER.read_text()
    assert "--no-rerank" in text
    assert "CABINET_MEMORY_RERANK=off" in text
    assert "TWO ARMS" in text, "runner header lost the two-arm contract doc"
    assert 'arm:$arm' in text, "JSON verdict lost the arm label"
