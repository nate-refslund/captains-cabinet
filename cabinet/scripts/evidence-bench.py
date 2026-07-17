#!/usr/bin/env python3.12
"""evidence-bench.py — measure the evidence recorder's performance envelope.

Evidence program Phase 2 Batch A (G3, observation-only). This harness
CHARACTERIZES the recorder so the envelope numbers (per-trial event cap,
store-growth ceiling, doctor thresholds) are measured, never invented
(design R-8: measured in Phase 1, enforced in Phase 2). It measures:

  * p95/p99 append latency, overall and as a function of trial length —
    ``EvidenceRecorder.append`` re-verifies the WHOLE trial before every
    write, so an N-event trial costs O(N^2) total hashing; the long-trial
    sweep makes that curve visible and prices the enforced cap;
  * per-day store-growth projection (bytes/event by event shape, projected
    against the live volumes measured in recon);
  * per-trial event-count distribution across a realistic mix
    (journey-shaped 8-event act trials + mirror-shaped day-bounded receipt
    trials + a consequence-mirror day trial);
  * the store-wide watermark axis: every append rewrites the signed
    anti-rollback index, which grows with the number of trials, not with
    trial length — the cap does NOT bound this axis (day-rolling and
    retention do);
  * a recommended enforced per-trial event cap with its measured basis.

SCRATCH-STORE ONLY. The harness creates its own throwaway store with
``tempfile.mkdtemp`` and refuses (``_refuse_live``) anything that resolves
into ``instance/evidence`` or the recorder's default home. It never reads
``CABINET_EVIDENCE_DIR`` — the store root is always explicit (the untrusted
env seam stays unconsulted, A10). It is NOT an emit CLI: it writes only to
the scratch store it just created, through the sanctioned recorder import
seam, and is not an officer surface (officers keep exactly one evidence
path, ``cabinet/scripts/evidence-read.sh``, which this file does not touch).

Recorded numbers live in docs/runbooks/evidence-recorder-v1.md
("Measured envelope"). Re-run with:

    python3.12 cabinet/scripts/evidence-bench.py --output /tmp/bench.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import shutil
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.evidence import EvidenceRecorder  # noqa: E402
from framework.evidence.recorder import PHASES, STATUSES, TRIAL_CLASS_RE  # noqa: E402
from framework.evidence.verifier import verify_store, verify_trial  # noqa: E402

# Fixed producer identity — never payload- or env-derived.
ACTOR = {"kind": "system", "id": "evidence-bench"}
COMPONENT = {"name": "evidence-bench", "version": "1", "commit": "unset"}

# Journey-shaped act choreography (8 events, the ActLifecycle-style shape).
JOURNEY_STEPS: tuple[tuple[str, str], ...] = (
    ("intent", "started"),
    ("policy", "allowed"),
    ("execution", "started"),
    ("transport", "succeeded"),
    ("verification", "verified"),
    ("receipt", "succeeded"),
    ("feedback", "useful"),
    ("outcome", "succeeded"),
)

# Live volumes from the Phase-2 recon (measured 2026-07-14..16): org events
# 1,313-2,372 rows/day of which ~94% is excluded exhaust; mirrored
# org-signal classes are tens-to-~142/day; consequence ledger 1-48 rows/day;
# journey-shaped acts assumed 20/day x 8 events. These are projection
# INPUTS recorded here for provenance — the bytes/event factors are measured.
LIVE_VOLUME_SCENARIOS: tuple[tuple[str, int, str], ...] = (
    ("org_signal_typical_day", 80, "mirror"),
    ("org_signal_worst_day", 142, "mirror"),
    ("consequence_worst_day", 48, "consequence"),
    ("journey_acts_20_per_day", 160, "journey"),
    ("combined_worst_day", 350, "mirror"),
)

CAP_CANDIDATES = (128, 192, 256, 384, 512, 768, 1024)
CAP_HEADROOM = 3.0
CAP_LATENCY_BUDGET_MS = 250.0


def _refuse_live(path: Path) -> Path:
    """Refuse any store root that could be (or shadow) a live store."""
    resolved = Path(path).resolve()
    text = str(resolved)
    if "instance/evidence" in text:
        raise ValueError(
            "evidence-bench refuses to touch anything under instance/evidence "
            f"(the live store): {text}"
        )
    default_home = Path(
        "~/Library/Application Support/cabinet/evidence"
    ).expanduser().resolve()
    if text == str(default_home) or text.startswith(str(default_home) + "/"):
        raise ValueError(
            "evidence-bench refuses the recorder's default store home: "
            f"{text}"
        )
    return resolved


def _scratch_store(base_dir: Path | str | None) -> Path:
    base = str(base_dir) if base_dir is not None else None
    root = Path(tempfile.mkdtemp(prefix="evidence-bench-", dir=base))
    return _refuse_live(root)


def _store_bytes(root: Path) -> int:
    total = 0
    for item in root.rglob("*"):
        try:
            if item.is_file() and not item.is_symlink():
                total += item.stat().st_size
        except OSError:
            pass
    return total


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))
    return round(ordered[index], 3)


def _stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "mean_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0,
                "p99_ms": 0.0, "max_ms": 0.0}
    return {
        "n": len(values),
        "mean_ms": round(sum(values) / len(values), 3),
        "p50_ms": _percentile(values, 0.50),
        "p95_ms": _percentile(values, 0.95),
        "p99_ms": _percentile(values, 0.99),
        "max_ms": round(max(values), 3),
    }


def _count_stats(counts: list[int]) -> dict[str, Any]:
    if not counts:
        return {"n": 0, "min": 0, "mean": 0.0, "p95": 0, "max": 0}
    ordered = sorted(counts)
    index = min(len(ordered) - 1, max(0, math.ceil(0.95 * len(ordered)) - 1))
    return {
        "n": len(counts),
        "min": ordered[0],
        "mean": round(sum(counts) / len(counts), 2),
        "p95": ordered[index],
        "max": ordered[-1],
    }


def _timed_append(
    recorder: EvidenceRecorder,
    latencies: list[tuple[str, int, float]],
    shape: str,
    sequence: int,
    trial_id: str,
    *,
    phase: str,
    status: str,
    detail: dict[str, Any],
) -> None:
    if phase not in PHASES or status not in STATUSES:
        raise AssertionError(f"bench vocabulary drifted: {phase}/{status}")
    context = recorder.trace(trial_id, surface="test")
    started = time.perf_counter()
    recorder.append(
        context,
        phase=phase,
        status=status,
        actor=ACTOR,
        component=COMPONENT,
        detail=detail,
    )
    latencies.append((shape, sequence, (time.perf_counter() - started) * 1000.0))


def _journey_detail(step: int) -> dict[str, Any]:
    return {
        "action": "bench_act",
        "result_code": "ok",
        "revision": f"r{step}",
        "file_count": 3,
        "total_bytes": 2048,
        "source_integrity": hashlib.sha256(f"bench-src-{step}".encode()).hexdigest(),
    }


def _mirror_detail(kind: str, index: int) -> dict[str, Any]:
    # Receipt about an already-happened org event: ids + digests only, never
    # payload copies; key names dodge the SECRET_KEY_RE / RAW_CONTENT_KEY_RE
    # redaction families so the measured bytes are the stored bytes.
    return {
        "action": f"{kind}_mirror_receipt",
        "org_event_id": uuid.uuid4().hex,
        "org_event_type": "need_created",
        "ledger_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "org_row_sha256": hashlib.sha256(f"{kind}-{index}".encode()).hexdigest(),
    }


def run_bench(
    *,
    journeys: int = 20,
    mirror_events: int = 150,
    consequence_events: int = 48,
    sweep_len: int = 512,
    watermark_trials: int = 120,
    base_dir: Path | str | None = None,
    keep_store: bool = False,
) -> dict[str, Any]:
    """Run every workload against a fresh scratch store; return the report."""
    root = _scratch_store(base_dir)
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    latencies: list[tuple[str, int, float]] = []
    trial_counts: dict[str, list[int]] = {
        "journey": [], "mirror_day": [], "watermark_axis": [],
    }
    try:
        recorder = EvidenceRecorder(root)
        size_fresh = _store_bytes(root)

        # 1) journey-shaped act trials (8-event choreography each)
        for i in range(journeys):
            trial_id = f"bench-journey-{i:04d}"
            for step, (phase, status) in enumerate(JOURNEY_STEPS, start=1):
                _timed_append(
                    recorder, latencies, "journey", step, trial_id,
                    phase=phase, status=status, detail=_journey_detail(step),
                )
            trial_counts["journey"].append(len(JOURNEY_STEPS))
        size_after_journeys = _store_bytes(root)

        # 2) mirror-shaped day-bounded receipt trials (the Phase-2 mirrors)
        mirror_trial = f"evt-benchorgmirror-{day}"
        if not TRIAL_CLASS_RE.fullmatch(mirror_trial):
            raise AssertionError("bench taxonomy id drifted")
        for i in range(mirror_events):
            _timed_append(
                recorder, latencies, "mirror", i + 1, mirror_trial,
                phase="system", status="succeeded",
                detail=_mirror_detail("org_event", i),
            )
        consequence_trial = f"evt-benchconsequence-{day}"
        for i in range(consequence_events):
            _timed_append(
                recorder, latencies, "consequence", i + 1, consequence_trial,
                phase="system", status="succeeded",
                detail=_mirror_detail("consequence", i),
            )
        if mirror_events:
            trial_counts["mirror_day"].append(mirror_events)
        if consequence_events:
            trial_counts["mirror_day"].append(consequence_events)
        size_after_mirrors = _store_bytes(root)

        # 3) long-trial latency sweep — the O(n^2) curve up to the cap zone
        sweep_trial = f"evt-benchsweep-{day}"
        for i in range(sweep_len):
            _timed_append(
                recorder, latencies, "sweep", i + 1, sweep_trial,
                phase="system", status="succeeded",
                detail=_mirror_detail("sweep", i),
            )
        size_after_sweep = _store_bytes(root)

        # 4) watermark axis — many 1-event trials; every append rewrites the
        # store-wide signed watermark index (O(#trials), NOT bounded by the
        # per-trial cap).
        for i in range(watermark_trials):
            _timed_append(
                recorder, latencies, "watermark_axis", i + 1,
                f"evt-benchwm{i:03d}-{day}",
                phase="system", status="succeeded",
                detail=_mirror_detail("watermark", i),
            )
            trial_counts["watermark_axis"].append(1)
        size_final = _store_bytes(root)

        # verification cost data (doctor bounded-runtime basis)
        started = time.perf_counter()
        sweep_verify = verify_trial(root, sweep_trial)
        verify_sweep_seconds = round(time.perf_counter() - started, 3)
        started = time.perf_counter()
        store_verify = verify_store(root)
        verify_store_seconds = round(time.perf_counter() - started, 3)
        watermark_path = root / ".verify-watermarks.json"
        watermark_bytes = watermark_path.stat().st_size if watermark_path.is_file() else 0
    finally:
        if not keep_store:
            shutil.rmtree(root, ignore_errors=True)

    by_shape = {
        shape: _stats([ms for s, _, ms in latencies if s == shape])
        for shape in ("journey", "mirror", "consequence", "sweep", "watermark_axis")
    }
    sweep_ms = [(seq, ms) for s, seq, ms in latencies if s == "sweep"]
    buckets = []
    for low, high in ((1, 8), (9, 64), (65, 128), (129, 256), (257, 384), (385, 512)):
        values = [ms for seq, ms in sweep_ms if low <= seq <= min(high, sweep_len)]
        if values:
            buckets.append({"bucket": f"{low}-{min(high, sweep_len)}", **_stats(values)})
        if high >= sweep_len:
            break

    wm_ms = [ms for s, _, ms in latencies if s == "watermark_axis"]
    half = max(1, min(10, len(wm_ms) // 2))
    watermark_axis = {
        "trials": watermark_trials,
        "first_appends_p95_ms": _percentile(wm_ms[:half], 0.95),
        "last_appends_p95_ms": _percentile(wm_ms[-half:], 0.95),
        "watermark_index_bytes_final": watermark_bytes,
    }

    def _per_event(size_delta: int, events: int) -> int:
        return int(size_delta / events) if events else 0

    bytes_per_event = {
        "journey": _per_event(size_after_journeys - size_fresh, journeys * len(JOURNEY_STEPS)),
        "mirror": _per_event(size_after_mirrors - size_after_journeys,
                             mirror_events + consequence_events),
        "sweep": _per_event(size_after_sweep - size_after_mirrors, sweep_len),
    }
    mirror_bpe = bytes_per_event["mirror"] or bytes_per_event["sweep"]
    journey_bpe = bytes_per_event["journey"] or mirror_bpe
    projections = []
    for scenario, events_per_day, shape in LIVE_VOLUME_SCENARIOS:
        factor = journey_bpe if shape == "journey" else mirror_bpe
        mb_day = round(events_per_day * factor / (1024 * 1024), 3)
        projections.append({
            "scenario": scenario,
            "events_per_day": events_per_day,
            "mb_per_day": mb_day,
            "mb_per_90d": round(mb_day * 90, 1),
        })

    worst_day = max(mirror_events, consequence_events, 1)
    needed = max(64, math.ceil(worst_day * CAP_HEADROOM))
    recommended = next((c for c in CAP_CANDIDATES if c >= needed), CAP_CANDIDATES[-1])
    deepest = buckets[-1] if buckets else _stats([])
    latency_at_depth = deepest.get("p95_ms", 0.0)
    cap_recommendation = {
        "recommended_max_trial_events": recommended,
        "headroom_factor": CAP_HEADROOM,
        "worst_simulated_day_trial_events": worst_day,
        "measured_depth": sweep_len,
        "p95_append_ms_at_measured_depth": latency_at_depth,
        "latency_within_budget": latency_at_depth <= CAP_LATENCY_BUDGET_MS,
        "latency_budget_ms": CAP_LATENCY_BUDGET_MS,
        "basis": (
            "smallest candidate >= headroom_factor x the worst simulated "
            "day-bounded mirror trial; act trials are ~8 events so the cap "
            "is sized by the day-bounded mirror volume, with recovery tails "
            "(+2), remint genesis (+1) and journey completion tails (+5) "
            "absorbed by the headroom"
        ),
    }

    all_counts = [c for counts in trial_counts.values() for c in counts]
    events_total = len(latencies)
    report = {
        "schema": "cabinet.evidence-bench-report/v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "machine": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
        },
        "params": {
            "journeys": journeys,
            "mirror_events": mirror_events,
            "consequence_events": consequence_events,
            "sweep_len": sweep_len,
            "watermark_trials": watermark_trials,
        },
        "events_total": events_total,
        "store": {
            "root": str(root),
            "kept": keep_store,
            "final_bytes": size_final,
            "verify_store_ok": bool(store_verify.get("ok")),
            "verify_store_trials": store_verify.get("trial_count", 0),
            "verify_store_seconds": verify_store_seconds,
            "verify_single_trial_seconds": verify_sweep_seconds,
        },
        "append_latency_ms": {
            "overall": _stats([ms for _, _, ms in latencies]),
            "by_shape": by_shape,
        },
        "sweep_latency_by_bucket": buckets,
        "watermark_axis": watermark_axis,
        "growth": {
            "bytes_per_event": bytes_per_event,
            "projection_inputs": "live volumes measured 2026-07-14..16 (recon)",
            "projections": projections,
        },
        "per_trial_event_counts": {
            "journey": _count_stats(trial_counts["journey"]),
            "mirror_day": _count_stats(trial_counts["mirror_day"]),
            "all": _count_stats(all_counts),
        },
        "cap_recommendation": cap_recommendation,
    }
    return report


def _summary(report: dict[str, Any]) -> str:
    overall = report["append_latency_ms"]["overall"]
    store = report["store"]
    cap = report["cap_recommendation"]
    lines = [
        f"evidence-bench: {report['events_total']} appends, "
        f"p50={overall['p50_ms']}ms p95={overall['p95_ms']}ms "
        f"p99={overall['p99_ms']}ms max={overall['max_ms']}ms",
        "sweep buckets: " + "; ".join(
            f"{b['bucket']}: p95={b['p95_ms']}ms" for b in report["sweep_latency_by_bucket"]
        ),
        f"bytes/event: {report['growth']['bytes_per_event']}",
        "projections: " + "; ".join(
            f"{p['scenario']}={p['mb_per_day']}MB/d ({p['mb_per_90d']}MB/90d)"
            for p in report["growth"]["projections"]
        ),
        f"watermark axis: first-p95={report['watermark_axis']['first_appends_p95_ms']}ms "
        f"last-p95={report['watermark_axis']['last_appends_p95_ms']}ms "
        f"index={report['watermark_axis']['watermark_index_bytes_final']}B "
        f"({report['watermark_axis']['trials']} trials)",
        f"verify: store({store['verify_store_trials']} trials)="
        f"{store['verify_store_seconds']}s ok={store['verify_store_ok']}; "
        f"single-trial={store['verify_single_trial_seconds']}s",
        f"recommended cap: {cap['recommended_max_trial_events']} "
        f"(worst simulated day trial {cap['worst_simulated_day_trial_events']} x "
        f"{cap['headroom_factor']}; p95@depth{cap['measured_depth']}="
        f"{cap['p95_append_ms_at_measured_depth']}ms, "
        f"within {cap['latency_budget_ms']}ms budget: {cap['latency_within_budget']})",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evidence-bench")
    parser.add_argument("--journeys", type=int, default=20)
    parser.add_argument("--mirror-events", type=int, default=150)
    parser.add_argument("--consequence-events", type=int, default=48)
    parser.add_argument("--sweep-len", type=int, default=512)
    parser.add_argument("--watermark-trials", type=int, default=120)
    parser.add_argument("--base-dir", type=Path, default=None,
                        help="Parent dir for the scratch store (default: system tmp)")
    parser.add_argument("--output", type=Path, default=None,
                        help="Write the full JSON report here")
    parser.add_argument("--keep-store", action="store_true",
                        help="Keep the scratch store for inspection")
    args = parser.parse_args(argv)
    report = run_bench(
        journeys=args.journeys,
        mirror_events=args.mirror_events,
        consequence_events=args.consequence_events,
        sweep_len=args.sweep_len,
        watermark_trials=args.watermark_trials,
        base_dir=args.base_dir,
        keep_store=args.keep_store,
    )
    print(_summary(report))
    if args.output:
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"report: {args.output}")
    if args.keep_store:
        print(f"scratch store kept: {report['store']['root']}")
    return 0 if report["store"]["verify_store_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
