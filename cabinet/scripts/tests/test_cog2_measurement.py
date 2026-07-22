"""COG-2 M6 — latency / rebuild / storage envelope measurement gate (§8 M6, O-B4).

Plan: docs/plans/cognitive-core-phase-2-contract-2026-07-22.md §8 "Measurement
gate (M6, exit :172) — CI-safe" (~:191) and §1 M6. This is the REAL consumer of
the M6 ceilings — the phantom the review claimed "enforced" had none. It is the
exact COG1_ENFORCE_P95 precedent (cabinet/scripts/tests/test_cog1_outbox_capture.py
::TestB1B2Baselines, the gate at ~:912): measure ALWAYS, assert ceilings ONLY
under the enforce flag on a quiet host.

WHAT M6 MEASURES over a BOUNDED history (the CI-safe run, O-B4):
  * full-rebuild wall time  — driving the real cabinet/scripts/cog2-rebuild.py
    CLI to a temp cache-dir (best of a few trials); the runtime-inverse's own
    `reversible_by` command, so this IS "the full rebuild".
  * store bytes / source bytes ratio — the disposable projection (beliefs.jsonl
    + fold-manifest.json) over the PRODUCTION-FAITHFUL WHOLE-ROW source basis.
  * as-of p50/p95 — over ≥200 framework/cortex/query.py as_of() queries on the
    RESIDENT VERIFIED projection (load_beliefs_verified — the C-F15 serve path).

SOURCE-BYTES BASIS (pinned, DOCUMENTED — the review pins ~3.95× on it):
  the source denominator is  SUM(octet_length(row_to_json(row)::text))  over the
  ELIGIBLE (folded, behind-frontier, non-NULL event_id) outbox rows — the
  production-faithful WHOLE-ROW logical row WITH the jsonb `payload` column
  INCLUDED. A captured outbox row ALWAYS carries its payload (047 DDL:
  `payload JSONB NOT NULL`; the capture trigger's jsonb_build_object), so the
  honest source basis includes it — the same basis the review's 3.95× uses. It
  is the whole row (every column, bookkeeping + payload), which maximizes the
  denominator; excluding payload would inflate the ratio artificially.

CEILINGS (contract §8 / exit :172), asserted ONLY under COG2_ENFORCE_P95=1:
  as-of p95 ≤ 250 ms · full rebuild ≤ 60 s · store ≤ 5× source bytes.

ENFORCE GATING — the exact COG1 precedent, with the one contract-pinned
difference: the contract says the ceilings are "asserted ONLY under
COG2_ENFORCE_P95=1 on a quiet host", so this sim keys enforcement PURELY on the
flag (COG1 additionally enforced on any non-CI host via `or not CI`). Without the
flag the bounded run is MEASUREMENT-ONLY (numbers recorded, ceilings NOT
asserted) — the 15-min-budget CI-safe path (O-B4). verify-cognitive-phase2.sh
exports COG2_ENFORCE_P95=1, so UNDER THE GATE this sim asserts the ceilings on
the bounded run — the real tripwire the phantom lacked.

SIZE: default/CI = 5,000 outbox + 500 consequence; COG2_FULL_HISTORY=1 opts into
the full pinned history (50,000 outbox + 5,000 consequence, the nightly path).

DETERMINISM (the M1 hash) is NOT this sim's job — test_cog2_rebuild_determinism.py
owns it (the C-F3 subprocess triple). This sim is the M6 latency/rebuild/store
envelope, nothing else.

S0: harness/CI pin PostgreSQL MAJOR 17. Interpreter python3.12. Skips without a
PG17 toolchain + psycopg2 (the DB-plane idiom).

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant.
"""
from __future__ import annotations

import importlib.util as _ilu
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_ROOT = str(_HERE.parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from framework.cortex import adapters, engine, query  # noqa: E402
from framework.fidelity import consequence  # noqa: E402


def _load(path: str, name: str):
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


# The relay harness re-exports EphemeralPG17 + pg_available + CAB_ID (the DB-plane
# idiom, loaded by path exactly as test_cog2_rebuild_determinism.py does).
HR = _load(_ROOT + "/framework/outbox/tests/lib_relay_harness.py",
           "lib_relay_harness_cog2m6")
_PG_SKIP = pytest.mark.skipif(not HR.pg_available(), reason=HR.PG_SKIP_REASON)
_FORBIDDEN = set(HR.H.FORBIDDEN_CHILD_ENV)

_REBUILD = _HERE.parent / "cog2-rebuild.py"
# the SHIPPED trust table (cabinet/config/cortex-source-trust.v1.yml) — the same
# production-faithful fold input cog2-rebuild.py loads by default; carries both
# the outbox-relay and consequence producers.
_TRUST_TABLE_FILE = _HERE.parents[1] / "config" / "cortex-source-trust.v1.yml"


# --- run shape -------------------------------------------------------------
_ENFORCE = os.environ.get("COG2_ENFORCE_P95") == "1"
_FULL = os.environ.get("COG2_FULL_HISTORY") == "1"
_OUTBOX_N = 50_000 if _FULL else 5_000
_CONSEQ_N = 5_000 if _FULL else 500

# ceilings (contract §8 / foundry exit :172)
_CEIL_ASOF_P95_MS = 250.0
_CEIL_REBUILD_S = 60.0
_CEIL_STORE_RATIO = 5.0

_REBUILD_TRIALS = 3          # best-of-N min (noise floor); the CLI overwrites atomically
_ASOF_QUERIES = 250         # ≥ 200 as-of queries (nearest-rank p95 => 238th sorted)
_CONSEQ_DAYS = 5            # spread the consequence rows across a few day-files


def _load_trust() -> dict:
    import yaml
    tt = yaml.safe_load(_TRUST_TABLE_FILE.read_text(encoding="utf-8")) or {}
    tt.setdefault("producers", {})
    return tt


# ---------------------------------------------------------------------------
# Seeding — direct bulk INSERTs (cog2-rebuild reads officer_tasks_outbox
# directly, agnostic to arrival). The outbox rows match the 047 schema + the
# capture trigger's jsonb_build_object payload shape; event_id is backfilled so
# every row is eligible (frontier == max(id)); cabinet_id == the DB identity.
# ---------------------------------------------------------------------------

def _seed_outbox(cluster, n: int) -> None:
    """Bulk-seed n eligible outbox rows via ONE generate_series INSERT. Each row
    is a distinct task (its own subject tasks/<g>) → the adapter emits its entity
    + observation pair, so n rows → 2n beliefs. The payload column is populated
    to the trigger's shape (whole-row payload-included source basis)."""
    cluster.psql(
        "INSERT INTO officer_tasks_outbox "
        "  (idempotency_key, event_id, task_id, old_status, new_status, "
        "   old_blocked, new_blocked, blocked_reason, actor, context_slug, "
        "   cabinet_id, correlation_id, occurred_at, payload) "
        "SELECT "
        "  'task:' || g::text || ':0:wip:false', "          # SQL-unique idempotency_key
        "  'evt-' || lpad(g::text, 12, '0'), "               # backfilled event_id => eligible
        "  g, 'queue', 'wip', false, false, NULL, 'cos', 'cog1', "
        "  :'cab', replace(gen_random_uuid()::text, '-', ''), "
        "  TIMESTAMPTZ '2026-07-20 08:00:00+00' + make_interval(secs => g), "
        "  jsonb_build_object("
        "    'task_id', g, 'old_status', 'queue', 'new_status', 'wip', "
        "    'old_blocked', false, 'new_blocked', false, 'blocked_reason', NULL, "
        "    'actor', 'cos', 'context_slug', 'cog1') "
        "FROM generate_series(1, :'n'::int) AS g;",
        vars={"cab": HR.CAB_ID, "n": str(n)})


def _seed_consequence(ledger_dir: Path, n: int) -> None:
    """Seed n distinct consequence rows across a few consequence-events-<date>
    .jsonl day-files (the append-only ledger consequence.iter_ledger_rows reads).
    Distinct subjects → distinct identity tuples → no dedupe collapse, so n rows
    → n consequence beliefs."""
    ledger_dir.mkdir(parents=True, exist_ok=True)
    per_day = -(-n // _CONSEQ_DAYS)          # ceil
    written = 0
    for day in range(_CONSEQ_DAYS):
        if written >= n:
            break
        date = f"2026-07-{10 + day:02d}"
        path = ledger_dir / f"consequence-events-{date}.jsonl"
        with open(path, "a") as fh:
            for _ in range(min(per_day, n - written)):
                row = {
                    "ts": f"{date}T08:00:00Z",
                    "actor": {"kind": "officer", "id": "cos"},
                    "lane": "acting",
                    "action": "task_status_move",
                    "subject": f"task/{written}",     # distinct => distinct belief
                    "refs": [],
                }
                fh.write(json.dumps(row) + "\n")
                written += 1


# ---------------------------------------------------------------------------
# Rebuild driver — the REAL cog2-rebuild.py CLI (DB/redis env stripped, exactly
# as the determinism subprocess does; the DSN is passed explicitly).
# ---------------------------------------------------------------------------

def _sub_rebuild(dsn: str, cache: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _FORBIDDEN}
    env.pop("COG2_OUTBOX_DSN", None)
    r = subprocess.run(
        ["python3.12", str(_REBUILD), "--dsn", dsn,
         "--cache-dir", str(cache), "--json"],
        capture_output=True, text=True, env=env)
    assert r.returncode == 0, f"cog2-rebuild rc={r.returncode}\n{r.stderr}"
    return json.loads(r.stdout)


def _du(*paths: Path) -> int:
    """Logical file bytes (os.path.getsize) — matched to the logical whole-row
    source-bytes basis (a logical/logical ratio, never block-rounded)."""
    return sum(p.stat().st_size for p in paths)


def _asof_percentiles(beliefs, n_outbox: int, cabinet_id: str, *, n_queries: int):
    """p50/p95 seconds over n_queries as_of() calls against the resident verified
    projection, rotating across evenly-spread outbox subjects."""
    scope = {"cabinet_id": cabinet_id}
    step = max(1, n_outbox // n_queries)
    samples: list[float] = []
    for i in range(n_queries):
        tid = ((i * step) % n_outbox) + 1
        t0 = time.perf_counter()
        result = query.as_of(beliefs, f"tasks/{tid}", scope=scope)
        samples.append(time.perf_counter() - t0)
        assert not result.is_unknown(), f"tasks/{tid} must resolve on the projection"
    return HR.H.pctl(samples, 50), HR.H.pctl(samples, 95)


# ---------------------------------------------------------------------------
# Consequence stream (§5.4 seam) — NO DB: iter_ledger_rows → build_consequence_
# protos → engine.fold (the TestConsequenceRebuildDeterminism seam). Recorded
# alongside the outbox so the bounded history spans BOTH streams (5k + 500).
# ---------------------------------------------------------------------------

def _measure_consequence(tmp: Path, n: int, trust: dict) -> dict:
    ledger = tmp / "events"
    _seed_consequence(ledger, n)
    prev = os.environ.get("CABINET_EVENT_LOG_DIR")
    os.environ["CABINET_EVENT_LOG_DIR"] = str(ledger)   # iter_ledger_rows reads this
    try:
        t0 = time.perf_counter()
        rows = list(consequence.iter_ledger_rows())
        protos = adapters.build_consequence_protos(rows, local_cabinet_id="main")  # D1 §6.1
        beliefs = engine.fold(protos, trust_table=trust)
        fold_s = time.perf_counter() - t0
    finally:
        if prev is None:
            os.environ.pop("CABINET_EVENT_LOG_DIR", None)
        else:
            os.environ["CABINET_EVENT_LOG_DIR"] = prev
    cache = tmp / "conseqcache"
    manifest = engine.build_manifest(beliefs, trust_table=trust,
                                     frontier=None, max_id=None)
    engine.write_projection(beliefs, manifest, cache)
    store_bytes = _du(cache / "beliefs.jsonl", cache / "fold-manifest.json")
    # consequence source basis = the whole day-file JSONL bytes (a consequence
    # row's whole JSON line IS its payload — the same whole-row logical basis).
    # No standalone ratio is reported: the minimal seam fixture's rows are tiny
    # (~150 B) beside a full belief record, so a consequence-only ratio is an
    # artifact of the fixture, not a store-envelope signal. The asserted store
    # ceiling is the OUTBOX whole-row basis (the review's 3.95x basis); the honest
    # whole-projection number is `combined_store_over_source_x` below.
    source_bytes = _du(*sorted(ledger.glob("consequence-events-*.jsonl")))
    return {
        "rows": n,
        "beliefs": len(beliefs),
        "fold_s": round(fold_s, 4),
        "store_bytes": store_bytes,
        "source_bytes": source_bytes,
        "source_basis": "whole day-file JSONL bytes (consequence row == its payload)",
    }


# ---------------------------------------------------------------------------
# The measurement — run ONCE per pytest invocation, shared across the ceilings.
# ---------------------------------------------------------------------------

def _measure(cluster, tmp: Path) -> dict:
    trust = _load_trust()

    # --- OUTBOX: seed -> rebuild (best-of-N) -> store/source/ratio -> as-of p95
    _seed_outbox(cluster, _OUTBOX_N)
    dsn = cluster.conninfo()
    cache = tmp / "cortexcache"
    rebuild_trials: list[float] = []
    manifest = None
    for _ in range(_REBUILD_TRIALS):
        t0 = time.perf_counter()
        manifest = _sub_rebuild(dsn, cache)          # overwrites cache atomically
        rebuild_trials.append(time.perf_counter() - t0)
    rebuild_s = min(rebuild_trials)
    frontier = manifest["frontier"]

    store_bytes = _du(cache / "beliefs.jsonl", cache / "fold-manifest.json")
    # SOURCE-BYTES BASIS (documented above): whole-row, payload-included logical
    # row over exactly the eligible (folded) rows the frontier admitted.
    source_bytes = int(cluster.one(
        "SELECT COALESCE(SUM(octet_length(row_to_json(t)::text)), 0) "
        "FROM officer_tasks_outbox t "
        "WHERE event_id IS NOT NULL AND id <= :'f';",
        vars={"f": str(frontier)}))
    store_ratio = store_bytes / source_bytes

    # as-of p95 over the RESIDENT VERIFIED projection (C-F15 serve path).
    beliefs = query.load_beliefs_verified(cache)
    p50_s, p95_s = _asof_percentiles(beliefs, _OUTBOX_N, HR.CAB_ID,
                                     n_queries=_ASOF_QUERIES)

    # --- CONSEQUENCE stream (no DB) — recorded alongside; bounded history spans both
    conseq = _measure_consequence(tmp, _CONSEQ_N, trust)

    # honest whole-projection number (both streams, both stores over both sources)
    # — outbox-dominated, so it tracks the asserted outbox-basis ratio closely.
    combined_ratio = ((store_bytes + conseq["store_bytes"])
                      / (source_bytes + conseq["source_bytes"]))

    return {
        "history": {"outbox_rows": _OUTBOX_N, "consequence_rows": _CONSEQ_N,
                    "full_history": _FULL},
        "enforced": _ENFORCE,
        "ceilings": {"asof_p95_ms": _CEIL_ASOF_P95_MS,
                     "full_rebuild_s": _CEIL_REBUILD_S,
                     "store_over_source_x": _CEIL_STORE_RATIO},
        "store_envelope": {
            "asserted_basis": "outbox whole-row (payload-included) — the review's 3.95x basis",
            "outbox_store_over_source_x": round(store_ratio, 4),
            "combined_store_over_source_x": round(combined_ratio, 4),
            "ceiling_x": _CEIL_STORE_RATIO,
        },
        "outbox": {
            "belief_count": manifest["belief_count"],
            "frontier": frontier,
            "rebuild_s_bestof": round(rebuild_s, 4),
            "rebuild_trials_s": [round(x, 4) for x in rebuild_trials],
            "store_bytes": store_bytes,
            "source_bytes": source_bytes,
            "source_basis": ("SUM(octet_length(row_to_json(row))) over eligible "
                             "rows — whole-row, payload-included"),
            "store_over_source_x": round(store_ratio, 4),
            "asof_queries": _ASOF_QUERIES,
            "asof_p50_ms": round(p50_s * 1000, 3),
            "asof_p95_ms": round(p95_s * 1000, 3),
        },
        "consequence": conseq,
    }


def _record(report: dict) -> None:
    """ALWAYS record the measured numbers — a CI reader sees them (the COG1
    precedent prints the blob; on an ENFORCE failure pytest surfaces this stdout,
    and COG2_MEASUREMENT_OUT mirrors it to a file, the COG1_BASELINE_OUT idiom)."""
    blob = json.dumps(report, indent=2, sort_keys=True)
    print("\nCOG2-M6-MEASUREMENT " + blob)
    out = os.environ.get("COG2_MEASUREMENT_OUT")
    if out:
        Path(out).write_text(blob + "\n")


@_PG_SKIP
class TestM6Measurement:
    """§8 M6 (O-B4): measure the as-of/rebuild/store envelope on a bounded
    history; assert the ceilings ONLY under COG2_ENFORCE_P95=1 (the gate sets it)."""

    @pytest.fixture(scope="class")
    def m6(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("cog2m6")
        cluster = HR.EphemeralPG17(tmp / "pg", cabinet_id=HR.CAB_ID)
        try:
            cluster.start()
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"could not start ephemeral PG17: {exc}")
        try:
            cluster.apply_base_chain()
            cluster.apply_identity_guc(HR.CAB_ID)
            cluster.apply_047()
            report = _measure(cluster, tmp)
            _record(report)          # numbers recorded regardless of enforcement
            yield report
        finally:
            cluster.stop()

    # -- always-on: the numbers are recorded + structurally sane (never a ceiling)

    def test_measured_numbers_recorded(self, m6):
        ob = m6["outbox"]
        assert ob["belief_count"] == 2 * m6["history"]["outbox_rows"], \
            "each eligible outbox row folds to exactly 2 beliefs (entity+observation)"
        assert m6["consequence"]["beliefs"] == m6["history"]["consequence_rows"], \
            "each distinct consequence row folds to exactly 1 belief"
        assert ob["frontier"] == m6["history"]["outbox_rows"]   # all rows backfilled
        assert ob["store_bytes"] > 0 and ob["source_bytes"] > 0
        assert ob["asof_queries"] >= 200                        # the M6 p95 sample floor
        assert ob["asof_p95_ms"] >= ob["asof_p50_ms"] >= 0

    # -- the three M6 ceilings — asserted ONLY under COG2_ENFORCE_P95=1 ---------

    def test_asof_p95_ceiling(self, m6):
        p95 = m6["outbox"]["asof_p95_ms"]
        if not _ENFORCE:
            pytest.skip(f"M6 measure-only (COG2_ENFORCE_P95 unset): "
                        f"as-of p95={p95:.3f}ms recorded, ceiling not asserted")
        assert p95 <= _CEIL_ASOF_P95_MS, \
            f"as-of p95 {p95:.3f}ms exceeds the {_CEIL_ASOF_P95_MS}ms ceiling"

    def test_full_rebuild_ceiling(self, m6):
        rebuild_s = m6["outbox"]["rebuild_s_bestof"]
        if not _ENFORCE:
            pytest.skip(f"M6 measure-only (COG2_ENFORCE_P95 unset): "
                        f"full rebuild={rebuild_s:.3f}s recorded, ceiling not asserted")
        assert rebuild_s <= _CEIL_REBUILD_S, \
            f"full rebuild {rebuild_s:.3f}s exceeds the {_CEIL_REBUILD_S}s ceiling"

    def test_store_envelope_ceiling(self, m6):
        ratio = m6["outbox"]["store_over_source_x"]
        if not _ENFORCE:
            pytest.skip(f"M6 measure-only (COG2_ENFORCE_P95 unset): "
                        f"store={ratio:.3f}x source recorded, ceiling not asserted")
        assert ratio <= _CEIL_STORE_RATIO, \
            f"store {ratio:.3f}x source-bytes exceeds the {_CEIL_STORE_RATIO}x ceiling"
