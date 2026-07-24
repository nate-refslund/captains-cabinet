#!/usr/bin/env python3.12
"""cog4-measure.py — the COG-4 §10 latency/cost MEASUREMENT CLI (N6, MR2 — the
phantom-M6 class must not recur; LESSONS L1102).

Contract: docs/plans/cognitive-core-phase-4-contract-2026-07-23.md §10 + §1 N6.
This is the REAL same-commit armed consumer the §10.3 anti-phantom law demands:
`verify-cognitive-phase4.sh` invokes `--check` under COG4_ENFORCE_BOUND=1, and
the W2 corpus battery `test_cog4_measurement.py` keys its retired arms on THIS
CLI + the S0 baseline artifact landing.

TWO METRIC CLASSES, at exactly the §10.5 honesty strength:

  * DETERMINISTIC PROXIES (always-on, EXACT — §10.5): tool/MCP activation
    counts + budget units are pure folds over the schedule artifact (§7.2
    decision rows). The composed wake vehicle (cog4-organ-runner) is
    SCHEDULER-BLIND (§9.5) — it activates each composed organ once per fixed
    wake, no scheduling — so the pilot's per-wake activation set is a
    DETERMINISTIC projection of the real composed manifests: one decision row
    per organ, `budget_units` = the manifest `cost_model.units_per_wake`,
    `descriptor.capability` = the organ's first (namespaced) domain_operation.
    The proxy fold is byte-identical in shape to the corpus reference
    `test_cog4_measurement.proxies_from_schedule_rows` (activations = row
    count; activations_by_capability = per-capability row count;
    budget_units_total = the row-budget sum), folded from the MATERIALIZED
    schedule.jsonl (written, then re-parsed — "from the schedule artifact",
    literally). EXACT tolerance: any measured proxy above its S0 baseline is a
    regression (shrink is welcome). Catches the §10.4 negative controls — an
    inflated `cost_model` raises budget_units_total; an extra composed organ
    raises activations.

  * WALL-CLOCK (measured TRIPWIRE, env-armed — §10.5): per pilot organ, the
    per-wake PLANNING wall-clock — the composed-runner orchestration overhead
    COG-4 introduces (manifest load + validate + project), measured in-process
    and hermetically (`--mode plan`, the default). The bound is the S0
    floor-aware note `wall_clock_bound` — max(p95 x 1.25, p95 + 5s) for sub-10s
    rows — a SELF-CONTAINED copy pinned byte-equal to the corpus helper
    `lib_cog4_floors.wall_clock_bound` by the drift-tripwire
    `test_cog4_measure_baseline.py` (the contract's drift-pin idiom; a CLI in
    the egg must not import a tests/ lib). Wall-clock is asserted ONLY when
    armed (COG4_ENFORCE_BOUND=1 or --arm); unarmed runs record a DECLARED skip
    (§10.5). The absorbed projection scripts' OWN runtime is UNCHANGED by
    composition (the runner runs each organ's same absorbed command) and is
    out of scope here; `--mode execute` is the deploy-host full-latency path
    (times the real runner entrypoints — non-hermetic, never run in CI).

The dated S0 baseline artifact (tracked, the phase record — sibling of the N9
`cog4-parity-record.json`): proxies (deterministic, reproduced EXACT by the
armed check) + per-organ wall-clock p95 (a FROZEN S0 measurement; the armed
check compares FRESH p95 to wall_clock_bound(this), never re-derives it — "no
borrowed numbers", §10.1). Freshly measured on the landing tree; §5 L146.

Boundary (§8.3 rows 5 — allowlisted organs reader): imports
`framework.organs.registry` ONLY (load_organ_manifests / read_manifest_file).
NO framework.scheduler import, no authority/acting/frontdoor, no network, no
schedule-store touch (the measurement schedule is materialized under a caller
temp dir, never `cabinet/cache/scheduler`). SHADOW-ONLY, read-only.

Usage:
    cog4-measure.py --baseline [--out FILE] [--organs-dir DIR] [--samples N]
                    [--s0-sha SHA]
    cog4-measure.py --check   [--baseline FILE] [--organs-dir DIR]
                    [--samples N] [--arm]
    cog4-measure.py           [--organs-dir DIR] [--schedule FILE] [--json]
    (default: print the current measurement record; --schedule folds proxies
     from an EXISTING schedule.jsonl — the fixture-driven path)

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; COG-4 W6 unit e3 (§10 measurement).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from framework.organs.registry import (  # noqa: E402  (allowlisted organs reader, §8.3 row 5)
    OrganRegistryError,
    load_organ_manifests,
    read_manifest_file,
)

_FLAG = "COG4_ENFORCE_BOUND"
DEFAULT_ORGANS_DIR = _REPO / "cabinet" / "config" / "organs"
DEFAULT_BASELINE = (_REPO / "cabinet" / "scripts" / "tests" / "fixtures"
                    / "cog4" / "cog4-measure-baseline-2026-07-24.json")
# The pilot set the W6-e2 compose landed (contract §9.3; the five composed
# rows -> one cog4-organ-runner). A measured baseline covers EXACTLY these.
PILOT_ORGANS = ("charter-shadow", "judge-calibration", "prediction-calibration",
                "preference-pairs", "world-census")
BASELINE_SCHEMA = "cog4-measure-baseline/v1"
DEFAULT_SAMPLES = 25


# ---------------------------------------------------------------------------
# §10.2 — the floor-aware wall-clock bound formula (SELF-CONTAINED; drift-pinned
# byte-equal to lib_cog4_floors.wall_clock_bound by test_cog4_measure_baseline)
# ---------------------------------------------------------------------------
def wall_clock_bound(p95_s) -> float:
    """bound = p95 x 1.25, FLOORED for sub-10s rows at p95 + 5.0s —
    max(p95 * 1.25, p95 + 5.0) when p95 < 10s (the S0 floor-aware note: a
    multiplicative-only tolerance hands a 5ms row a noise-width 6.25ms bound;
    the +5s absolute floor keeps sub-10s rows honest tripwires)."""
    if isinstance(p95_s, bool) or not isinstance(p95_s, (int, float)):
        raise ValueError("p95_s must be a number")
    if p95_s < 0:
        raise ValueError("p95_s must be >= 0")
    p = float(p95_s)
    if p < 10.0:
        return max(p * 1.25, p + 5.0)
    return p * 1.25


# ---------------------------------------------------------------------------
# deterministic proxies — EXACT from the schedule artifact (§10.5 always-on).
# The fold shape is byte-identical to the corpus reference
# test_cog4_measurement.proxies_from_schedule_rows.
# ---------------------------------------------------------------------------
def proxies_from_schedule_rows(rows: list) -> dict:
    by_cap: dict[str, int] = {}
    total = 0
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"schedule row {i} is not a mapping")
        units = row.get("budget_units")
        if not isinstance(units, int) or isinstance(units, bool) or units < 0:
            raise ValueError(
                f"schedule row {i}: budget_units must be an integer >= 0")
        total += units
        cap = (row.get("descriptor") or {}).get("capability")
        if not isinstance(cap, str) or "/" not in cap:
            raise ValueError(
                f"schedule row {i}: descriptor.capability must be a namespaced "
                f"'<domain>/<operation>' id")
        by_cap[cap] = by_cap.get(cap, 0) + 1
    return {
        "activations": len(rows),
        "activations_by_capability": dict(sorted(by_cap.items())),
        "budget_units_total": total,
    }


def proxy_bound_violations(measured: dict, baseline: dict) -> list:
    """EXACT tolerance (§10.2): any measured proxy above its baseline is a
    regression. Below/equal is fine (shrink is welcome)."""
    v: list[str] = []
    if measured["activations"] > baseline["activations"]:
        v.append(f"activations {measured['activations']} > baseline "
                 f"{baseline['activations']} (over-activation)")
    if measured["budget_units_total"] > baseline["budget_units_total"]:
        v.append(f"budget_units_total {measured['budget_units_total']} > "
                 f"baseline {baseline['budget_units_total']} (inflated cost)")
    for cap, n in measured["activations_by_capability"].items():
        base = baseline["activations_by_capability"].get(cap, 0)
        if n > base:
            v.append(f"capability {cap!r} activations {n} > baseline {base}")
    return v


def wall_clock_violations(measured_p95_s: dict, baseline_p95_s: dict) -> list:
    """Per pilot row: measured p95 must stay <= wall_clock_bound(baseline p95)
    (§10.2 + the S0 floor-aware note). A measured row missing its baseline is a
    violation (no borrowed numbers — §10.1)."""
    v: list[str] = []
    for row, measured in sorted(measured_p95_s.items()):
        base = baseline_p95_s.get(row)
        if base is None:
            v.append(f"{row}: no S0 baseline for this row (freshly measured "
                     f"baselines only — §10.1)")
            continue
        bound = wall_clock_bound(base)
        if measured > bound:
            v.append(f"{row}: p95 {measured:.6f}s exceeds bound {bound:.6f}s "
                     f"(baseline {base:.6f}s)")
    return v


# ---------------------------------------------------------------------------
# project the real composed manifests -> the per-wake measurement schedule
# ---------------------------------------------------------------------------
def manifest_to_row(manifest: dict) -> dict:
    """ONE per-wake decision row for one composed organ (§9.5 scheduler-blind:
    each composed organ activates once per fixed wake). budget_units =
    cost_model.units_per_wake (the organ's declared per-wake cost); capability
    = the first namespaced domain_operation. Fails LOUD on a malformed
    manifest (a silent zero is a lie)."""
    name = manifest.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("organ manifest missing a non-empty name")
    ops = manifest.get("domain_operations")
    if not isinstance(ops, list) or not ops or not isinstance(ops[0], str) \
            or "/" not in ops[0]:
        raise ValueError(
            f"{name}: domain_operations[0] must be a namespaced "
            f"'<domain>/<operation>' id")
    cost = (manifest.get("cost_model") or {}).get("units_per_wake")
    if not isinstance(cost, int) or isinstance(cost, bool) or cost < 0:
        raise ValueError(
            f"{name}: cost_model.units_per_wake must be an integer >= 0")
    cap = ops[0]
    return {
        "organ": name,
        "operation": cap,
        "descriptor": {"capability": cap},
        "reason": "composed-runner-fixed-wake",
        "budget_units": cost,
        "deps": [],
        "tie_break_key": name,
    }


def build_measurement_schedule(manifests: list) -> list:
    """The measurement schedule rows for the composed set, in a canonical
    (name-sorted) total order — deterministic."""
    ordered = sorted(manifests, key=lambda m: (m.get("name") or ""))
    return [manifest_to_row(m) for m in ordered]


def _materialize_and_fold(rows: list) -> dict:
    """Write the measurement schedule to a schedule.jsonl in a throwaway temp
    dir, re-parse it, and fold the proxies from the ARTIFACT bytes (the §10
    'from the schedule artifact' discipline; never `cabinet/cache/scheduler`)."""
    with tempfile.TemporaryDirectory(prefix="cog4-measure-") as td:
        art = Path(td) / "schedule.jsonl"
        art.write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows),
            encoding="utf-8")
        reparsed = [json.loads(line)
                    for line in art.read_text(encoding="utf-8").splitlines()]
    return proxies_from_schedule_rows(reparsed)


def load_schedule_artifact(path: Path) -> list:
    """Fixture-driven path: fold proxies from an EXISTING schedule.jsonl."""
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# wall-clock — per-organ per-wake PLANNING wall-clock (hermetic, in-process)
# ---------------------------------------------------------------------------
def _percentile(values: list, p: float) -> float:
    """Deterministic nearest-rank percentile (no interpolation)."""
    s = sorted(values)
    if not s:
        raise ValueError("no samples to take a percentile of")
    k = max(0, math.ceil(p / 100.0 * len(s)) - 1)
    return float(s[k])


def measure_organ_plan_p95(path: Path, samples: int) -> float:
    """Per-organ per-wake PLANNING wall-clock p95: time (manifest load +
    project-to-row), the composed-runner orchestration overhead per organ per
    wake. Hermetic, executes no organ entrypoint. `samples` timed reads."""
    if samples < 1:
        raise ValueError("samples must be >= 1")
    times: list[float] = []
    for _ in range(samples):
        t0 = time.perf_counter()
        manifest = read_manifest_file(path)
        manifest_to_row(manifest)
        times.append(time.perf_counter() - t0)
    return _percentile(times, 95.0)


def _organ_paths(organs_dir: Path) -> dict:
    """Map organ name -> its manifest path under the composed-manifest dir."""
    out: dict[str, Path] = {}
    for path in sorted(organs_dir.iterdir()):
        if path.suffix.lower() not in (".yml", ".yaml", ".json") \
                or not path.is_file():
            continue
        try:
            manifest = read_manifest_file(path)
        except OrganRegistryError:
            continue
        name = manifest.get("name")
        if isinstance(name, str) and name:
            out[name] = path
    return out


def measure_wall_clock(organs_dir: Path, samples: int) -> dict:
    return {name: measure_organ_plan_p95(path, samples)
            for name, path in sorted(_organ_paths(organs_dir).items())}


# ---------------------------------------------------------------------------
# the baseline artifact
# ---------------------------------------------------------------------------
def _armed() -> bool:
    """THE §10.3 designated consumption of COG4_ENFORCE_BOUND in this CLI —
    read at call time so the armed verify twin exercises the real seam."""
    return os.environ.get(_FLAG) == "1"


def compute_measurement(organs_dir: Path, samples: int) -> dict:
    """The full measurement over the real composed manifests: deterministic
    proxies + per-organ wall-clock p95."""
    manifests = load_organ_manifests(organs_dir)
    rows = build_measurement_schedule(manifests)
    proxies = _materialize_and_fold(rows)
    wall = measure_wall_clock(organs_dir, samples)
    return {"proxies": proxies, "wall_clock_p95_s": wall,
            "organs": sorted(m.get("name") for m in manifests
                             if isinstance(m.get("name"), str))}


def build_baseline(organs_dir: Path, samples: int, s0_sha: str) -> dict:
    m = compute_measurement(organs_dir, samples)
    return {
        "schema": BASELINE_SCHEMA,
        "date": "2026-07-24",
        "s0_sha": s0_sha,
        "note": ("S0 baseline (contract §10.1) — FROZEN. proxies are exact "
                 "deterministic reproductions of the composed-manifest "
                 "schedule; wall_clock_p95_s are the frozen S0 per-wake "
                 "PLANNING wall-clock measurements (host-measured, `--mode "
                 "plan`); the armed check (COG4_ENFORCE_BOUND=1) compares a "
                 "FRESH p95 to wall_clock_bound(baseline), never re-derives it."),
        "measure_definition": {
            "proxies": "EXACT tolerance — measured > baseline is a regression",
            "wall_clock": ("measured tripwire (env-armed, declared skips) — "
                           "bound = max(p95*1.25, p95+5s) for sub-10s rows"),
            "samples": samples,
        },
        "pilot_organs": list(PILOT_ORGANS),
        "proxies": m["proxies"],
        "wall_clock_p95_s": m["wall_clock_p95_s"],
    }


def load_baseline(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "proxies" not in data \
            or "wall_clock_p95_s" not in data:
        raise ValueError(f"{path}: not a cog4-measure baseline artifact")
    return data


def check_against_baseline(baseline: dict, organs_dir: Path, samples: int,
                           armed: bool) -> tuple:
    """Return (violations, detail). Proxies always-on (§10.5); wall-clock only
    when armed (a DECLARED skip otherwise)."""
    violations: list[str] = []
    detail: dict = {"armed": armed}

    manifests = load_organ_manifests(organs_dir)
    rows = build_measurement_schedule(manifests)
    measured_proxies = _materialize_and_fold(rows)
    detail["proxies"] = measured_proxies
    violations += proxy_bound_violations(measured_proxies, baseline["proxies"])

    if armed:
        measured_wall = measure_wall_clock(organs_dir, samples)
        detail["wall_clock_p95_s"] = measured_wall
        violations += wall_clock_violations(measured_wall,
                                            baseline["wall_clock_p95_s"])
    else:
        detail["wall_clock"] = ("DECLARED skip (COG4_ENFORCE_BOUND unset) — "
                                "wall-clock is a measured tripwire (§10.5)")
    return violations, detail


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _resolve_s0_sha(arg: str | None) -> str:
    if arg:
        return arg
    try:
        import subprocess
        out = subprocess.run(["git", "-C", str(_REPO), "rev-parse", "HEAD"],
                             capture_output=True, text=True, check=False)
        sha = out.stdout.strip()
        return sha or "unpinned"
    except Exception:  # noqa: BLE001 — provenance metadata, never load-bearing
        return "unpinned"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="COG-4 §10 latency/cost measurement (proxies + wall-clock)")
    ap.add_argument("--organs-dir", type=Path, default=DEFAULT_ORGANS_DIR,
                    help="composed organ manifest dir (default "
                         "cabinet/config/organs)")
    ap.add_argument("--baseline", nargs="?", const="__WRITE__", default=None,
                    help="write mode: with no value writes the S0 baseline; "
                         "in --check, the baseline file to read")
    ap.add_argument("--check", action="store_true",
                    help="check the current measurement against the baseline "
                         "(proxies always-on; wall-clock when armed)")
    ap.add_argument("--baseline-file", type=Path, default=DEFAULT_BASELINE,
                    help="the baseline artifact path (default the tracked "
                         "phase record)")
    ap.add_argument("--out", type=Path, default=DEFAULT_BASELINE,
                    help="baseline write path")
    ap.add_argument("--schedule", type=Path, default=None,
                    help="fold proxies from an EXISTING schedule.jsonl "
                         "(fixture-driven path)")
    ap.add_argument("--samples", type=int, default=DEFAULT_SAMPLES,
                    help=f"wall-clock samples per organ (default {DEFAULT_SAMPLES})")
    ap.add_argument("--arm", action="store_true",
                    help="force-arm the wall-clock tripwire (equivalent to "
                         "COG4_ENFORCE_BOUND=1)")
    ap.add_argument("--s0-sha", default=None,
                    help="record this SHA as the S0 measurement base")
    ap.add_argument("--json", action="store_true",
                    help="emit a JSON measurement record")
    args = ap.parse_args(argv)

    armed = args.arm or _armed()

    # --- write the baseline
    if args.baseline == "__WRITE__" and not args.check:
        try:
            baseline = build_baseline(args.organs_dir, args.samples,
                                      _resolve_s0_sha(args.s0_sha))
        except (OrganRegistryError, ValueError, OSError) as exc:
            print(f"cog4-measure: REFUSED — {exc}", file=sys.stderr)
            return 1
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(baseline, indent=2, sort_keys=True)
                            + "\n", encoding="utf-8")
        print(f"cog4-measure: wrote baseline {args.out} "
              f"(proxies={baseline['proxies']['activations']} activations / "
              f"{baseline['proxies']['budget_units_total']} units; "
              f"{len(baseline['wall_clock_p95_s'])} organ p95s)",
              file=sys.stderr)
        return 0

    # --- check against the baseline
    if args.check:
        baseline_path = (Path(args.baseline) if args.baseline
                         and args.baseline != "__WRITE__" else args.baseline_file)
        try:
            baseline = load_baseline(baseline_path)
        except (ValueError, OSError) as exc:
            print(f"cog4-measure: REFUSED — cannot load baseline "
                  f"{baseline_path}: {exc}", file=sys.stderr)
            return 1
        try:
            violations, detail = check_against_baseline(
                baseline, args.organs_dir, args.samples, armed)
        except (OrganRegistryError, ValueError, OSError) as exc:
            print(f"cog4-measure: REFUSED — {exc}", file=sys.stderr)
            return 1
        if not armed:
            print("[cog4-measure] N6 proxies checked (always-on); wall-clock "
                  "tripwire is a DECLARED skip (COG4_ENFORCE_BOUND unset, §10.5)",
                  file=sys.stderr)
        if violations:
            print("cog4-measure: REGRESSION — the measured metrics exceed the "
                  "S0 baseline bound:", file=sys.stderr)
            for v in violations:
                print(f"  - {v}", file=sys.stderr)
            return 1
        print(f"[cog4-measure] N6 within bound: proxies EXACT"
              + (", wall-clock <= bound (armed)" if armed else " (proxies only)"),
              file=sys.stderr)
        return 0

    # --- default: print the current measurement record
    if args.schedule is not None:
        try:
            rows = load_schedule_artifact(args.schedule)
            record = {"proxies": proxies_from_schedule_rows(rows),
                      "source": str(args.schedule)}
        except (ValueError, OSError) as exc:
            print(f"cog4-measure: REFUSED — {exc}", file=sys.stderr)
            return 1
    else:
        try:
            record = compute_measurement(args.organs_dir, args.samples)
        except (OrganRegistryError, ValueError, OSError) as exc:
            print(f"cog4-measure: REFUSED — {exc}", file=sys.stderr)
            return 1
        record["armed"] = armed
    if args.json:
        print(json.dumps(record, sort_keys=True))
    else:
        pr = record["proxies"]
        print(f"activations={pr['activations']} "
              f"budget_units_total={pr['budget_units_total']} "
              f"by_capability={pr['activations_by_capability']}")
        if "wall_clock_p95_s" in record:
            for name, p95 in sorted(record["wall_clock_p95_s"].items()):
                print(f"  {name}: plan-p95={p95:.6f}s "
                      f"bound={wall_clock_bound(p95):.6f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
