"""COG-3 N1 — full-rebuild wall-time + serve p95 measurement gate (§8 N1, §1 N1).

Plan: docs/plans/cognitive-core-phase-3-contract-2026-07-22.md §1 N1 (rebuild
determinism + delete->rebuild-from-zero) and §8. The exact COG2_ENFORCE_P95
precedent (test_cog2_measurement.py): MEASURE the envelope ALWAYS on a bounded,
FILE-SEEDED graph (no DSN — §7.2), assert the ceilings ONLY under COG3_ENFORCE_P95
on a quiet host. verify-cognitive-phase3.sh exports COG3_ENFORCE_P95=1, so UNDER
THE GATE this sim asserts the ceilings.

WHAT N1 MEASURES over a CI-BOUNDED seeded graph (~80 objectives + 50 outcomes/
interventions/instruments + 60 cortex observation beliefs -> a few hundred graph
records):
  * full-rebuild wall time  — driving framework.objectives.graph.build_graph to a
    temp cache-dir (best of a few trials); the runtime-inverse's own rebuild path
    (cog3-rebuild.py wraps exactly this), so this IS "the full rebuild" (N1
    delete->rebuild-from-zero: each trial rebuilds into the same cache).
  * serve p95            — over >=200 framework.objectives.query.serve_objective()
    answers on the COMPILED graph (the per-objective answer path a consumer calls,
    §5.2 / §9 r5), after one serve_graph() bind (the C-F15 store-hash check).

DETERMINISM is NOT re-proven here: the C-F3 subprocess triple (3 distinct
PYTHONHASHSEED rebuilds) lives in test_cog3_sim1_objective_conflict.py. This sim
MEASURES a same-process rebuild-hash reproduction as an always-on SIGNAL (a cheap
regression tripwire), never the cross-seed triple.

CEILINGS (honest CI-scale, picked from the observed measurement with generous
headroom for CI noise; asserted ONLY under COG3_ENFORCE_P95=1):
  full rebuild (best-of-N) <= 2.0 s   (observed ~5 ms on the author host)
  serve p95                <= 150 ms  (observed ~0.35 ms on the author host)

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; wave-4 phase-complete.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = str(_HERE.parents[2])
for _p in (str(_HERE), _REPO):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_cog3_fixtures as F                        # noqa: E402  (file-seeded surface)
from framework.objectives import graph, query as oq  # noqa: E402


# --- run shape -------------------------------------------------------------
_ENFORCE = os.environ.get("COG3_ENFORCE_P95") == "1"

_N_OBJ = 80          # objectives (chained depends_on + periodic conflicts_with)
_N_OUT = 50          # outcomes + one intervention + one instrument each
_N_BEL = 60          # cortex observation beliefs (the fenced as_of source)
_REBUILD_TRIALS = 3  # best-of-N min (noise floor); build_graph overwrites atomically
_SERVE_QUERIES = 250  # >= 200 serve answers (nearest-rank p95 => 238th sorted)

# ceilings — apparatus-chosen CI-scale envelopes (the COG2_ENFORCE_P95 precedent),
# NOT contract numbers: contract §8/§1 N1 is DETERMINISM-ONLY (identical chained
# graph hash across the C-F3 seed triple + delete->rebuild-from-zero); it fixes no
# wall-time or p95 bound. The two bounds below are picked from the observed
# measurement with generous CI headroom and asserted ONLY under COG3_ENFORCE_P95=1.
_CEIL_REBUILD_S = 2.0
_CEIL_SERVE_P95_MS = 150.0


def _write_objectives_input(dir_path: Path) -> Path:
    """A CI-bounded cabinet-authored graph seed (the sim1 provisional JSON shape):
    one direction root, N chained/periodically-conflicting objectives, M outcomes
    each with a causal intervention edge + an indicates instrument edge."""
    directions = [{"slug": "d-north", "statement": "ship the compliant platform"}]
    objectives = []
    for i in range(_N_OBJ):
        obj = {"slug": f"obj-{i:03d}", "statement": f"objective {i}", "root_ref": "d-north"}
        if i > 0:
            obj["depends_on"] = [f"obj-{i - 1:03d}"]
        if i % 5 == 0 and i + 1 < _N_OBJ:
            obj["conflicts_with"] = [f"obj-{i + 1:03d}"]
        objectives.append(obj)
    outcomes = [{"slug": f"out-{i:03d}", "dimension": "cost"} for i in range(_N_OUT)]
    nodes = [{"kind": "intervention", "subject_key": f"intervention/iv-{i:03d}"}
             for i in range(_N_OUT)]
    causal_edges = [{"source": f"intervention/iv-{i:03d}", "target": f"outcome/out-{i:03d}",
                     "dimension": "cost", "expected_effect": "decrease"} for i in range(_N_OUT)]
    indicates_edges = [{"source": f"instrument/ins-{i:03d}", "target": f"outcome/out-{i:03d}",
                        "dimension": "cost"} for i in range(_N_OUT)]
    payload = {"directions": directions, "objectives": objectives, "outcomes": outcomes,
               "constraints": [], "nodes": nodes, "causal_edges": causal_edges,
               "indicates_edges": indicates_edges}
    path = Path(dir_path) / "objectives-input.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")
    return path


def _measure(tmp: Path) -> dict:
    cache = tmp / "objectives"
    cortex = tmp / "cortex"
    cache.mkdir(parents=True, exist_ok=True)
    cortex.mkdir(parents=True, exist_ok=True)

    # --- cortex store (the ONE read path, §5.1): file-seeded observations
    protos = [F.observation_proto(f"observation/s-{i}", F.DIMENSION,
                                  claim=F.observed_effect_claim("decrease"),
                                  seq=0, event_suffix=str(i)) for i in range(_N_BEL)]
    beliefs = F.fold_beliefs(protos)
    F.persist_cortex_store(cortex, beliefs)
    roots = _write_objectives_input(tmp)

    # --- full rebuild (best-of-N; delete->rebuild-from-zero each trial, N1)
    rebuild_trials = []
    for _ in range(_REBUILD_TRIALS):
        t0 = time.perf_counter()
        graph.build_graph(str(roots), str(cache), dict(F.SCOPE), F.CUTOFF)
        rebuild_trials.append(time.perf_counter() - t0)
    rebuild_s = min(rebuild_trials)
    manifest = json.loads((cache / "graph-manifest.json").read_text(encoding="utf-8"))

    # --- determinism SIGNAL (measure-only; the C-F3 triple lives in sim1): N1
    # delete->rebuild-from-zero reproduces the chained hash. The roots PATH is held
    # FIXED (the U2 adjudication: roots_path is a recorded manifest parameter, so
    # the hash is path-dependent — every N1 comparison holds the path fixed).
    import shutil
    hash_a = graph.chained_graph_hash(str(cache))
    shutil.rmtree(cache)
    cache.mkdir(parents=True, exist_ok=True)
    graph.build_graph(str(roots), str(cache), dict(F.SCOPE), F.CUTOFF)  # SAME roots path
    hash_b = graph.chained_graph_hash(str(cache))

    # --- serve p95 over the compiled graph (bind once, answer >=200)
    oq.serve_graph(str(cache))                       # C-F15 bind (store-hash check)
    subjects = [f"objective/obj-{i:03d}" for i in range(_N_OBJ)]
    samples = []
    for i in range(_SERVE_QUERIES):
        subject = subjects[i % len(subjects)]
        t0 = time.perf_counter()
        answer = oq.serve_objective(str(cache), subject)
        samples.append(time.perf_counter() - t0)
        assert answer.state, f"objective {subject} must resolve to a state"
    samples.sort()
    p50 = samples[len(samples) // 2] * 1000
    # nearest-rank p95 (the convention line _SERVE_QUERIES states): rank =
    # ceil(0.95*N), 0-indexed rank-1. For N=250 that is the 238th sorted sample
    # (index 237) — reconciled to the comment (the prior int()-1 gave the 237th,
    # off by one).
    p95 = samples[max(0, math.ceil(0.95 * len(samples)) - 1)] * 1000

    return {
        "enforced": _ENFORCE,
        "graph": {"nodes": manifest["node_count"], "edges": manifest["edge_count"],
                  "records": manifest["node_count"] + manifest["edge_count"],
                  "cortex_beliefs": len(beliefs)},
        "ceilings": {"full_rebuild_s": _CEIL_REBUILD_S, "serve_p95_ms": _CEIL_SERVE_P95_MS},
        "rebuild": {"best_of_s": round(rebuild_s, 5),
                    "trials_s": [round(x, 5) for x in rebuild_trials]},
        "determinism": {"hash_a": hash_a, "hash_b": hash_b, "reproduced": hash_a == hash_b},
        "serve": {"queries": _SERVE_QUERIES, "p50_ms": round(p50, 4), "p95_ms": round(p95, 4)},
    }


def _record(report: dict) -> None:
    """ALWAYS record the measured numbers (the COG1/COG2 precedent): on an ENFORCE
    failure pytest surfaces this stdout; COG3_MEASUREMENT_OUT mirrors it to a file."""
    blob = json.dumps(report, indent=2, sort_keys=True)
    print("\nCOG3-N1-MEASUREMENT " + blob)
    out = os.environ.get("COG3_MEASUREMENT_OUT")
    if out:
        Path(out).write_text(blob + "\n")


class TestN1Measurement:
    """§8 N1: measure the full-rebuild + serve envelope on a bounded FILE-SEEDED
    graph; assert the ceilings ONLY under COG3_ENFORCE_P95=1 (the gate sets it)."""

    @pytest.fixture(scope="class")
    def n1(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("cog3n1")
        report = _measure(tmp)
        _record(report)                          # numbers recorded regardless of enforcement
        return report

    # -- always-on: the numbers are recorded + structurally sane + reproducible ---

    def test_measured_numbers_recorded(self, n1):
        assert n1["graph"]["records"] > 200, "the bounded graph must be non-trivial"
        assert n1["graph"]["cortex_beliefs"] == _N_BEL
        assert n1["rebuild"]["best_of_s"] > 0
        assert n1["serve"]["queries"] >= 200                 # the p95 sample floor
        assert n1["serve"]["p95_ms"] >= n1["serve"]["p50_ms"] >= 0

    def test_rebuild_is_deterministic_signal(self, n1):
        # measure-only determinism SIGNAL (same-process rebuild-from-zero reproduces
        # the chained hash). The cross-seed C-F3 subprocess triple is sim1's job.
        assert n1["determinism"]["reproduced"], \
            f"rebuild hash not reproduced: {n1['determinism']}"

    # -- the two N1 ceilings — asserted ONLY under COG3_ENFORCE_P95=1 ------------

    def test_full_rebuild_ceiling(self, n1):
        rebuild_s = n1["rebuild"]["best_of_s"]
        if not _ENFORCE:
            pytest.skip(f"N1 measure-only (COG3_ENFORCE_P95 unset): "
                        f"full rebuild={rebuild_s:.5f}s recorded, ceiling not asserted")
        assert rebuild_s <= _CEIL_REBUILD_S, \
            f"full rebuild {rebuild_s:.5f}s exceeds the {_CEIL_REBUILD_S}s ceiling"

    def test_serve_p95_ceiling(self, n1):
        p95 = n1["serve"]["p95_ms"]
        if not _ENFORCE:
            pytest.skip(f"N1 measure-only (COG3_ENFORCE_P95 unset): "
                        f"serve p95={p95:.4f}ms recorded, ceiling not asserted")
        assert p95 <= _CEIL_SERVE_P95_MS, \
            f"serve p95 {p95:.4f}ms exceeds the {_CEIL_SERVE_P95_MS}ms ceiling"
