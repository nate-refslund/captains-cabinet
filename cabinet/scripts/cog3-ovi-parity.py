#!/usr/bin/env python3.12
"""cog3-ovi-parity.py — OVI per-instrument shadow-parity FALSIFIER (C-F17 analog,
contract rev-1 §6.6 P10 / N6, attack C-M4).

The legacy OVI is a weighted COMPOSITE scalar 0.0-1.0 (framework/ovi/compute.py).
The objectives graph refuses any composite, ever — its ovi_view emits a
PER-INSTRUMENT projection only. N6 pins the compatibility bar honestly: the
objectives per-instrument view must EXACTLY reproduce the legacy's per-instrument
NORMALIZED components over the SAME pinned window (the composite scalar is
DROPPED, never compared). A view that silently drops an instrument, mangles a
value, or grows a composite is invisible until an operator trusts it — so this
falsifier samples the LEGACY module as ground truth, obtains the objectives
projection as an EXTERNAL black box, and compares per-instrument, EXACT.

TWO anti-tautology pins (C-F17), mirroring cog2-parity-falsifier.py:

  1. LEGACY-module ground truth. Ground truth is the INDEPENDENT legacy module
     framework.ovi.compute (imported directly here), never the objectives view —
     reading ground truth back through the view's own answer is f(x)==f(x) and can
     never disagree with a mistranslation.

  2. IMPORT BAN. This file imports NO framework.objectives module at all: the
     per-instrument view is queried as an EXTERNAL black box (an operator-
     configurable command, COG3_OVI_VIEW_CMD, default a child python3.12 -c that
     imports framework.objectives.ovi_view IN THE CHILD), so the falsifier can
     neither reuse nor re-derive the view's projection in-process. The §6.5 import
     gate leaves cog3-ovi-parity.py OFF the objectives-reader allowlist, so any
     objectives import from here REDs as UNALLOWLISTED_OBJECTIVES_IMPORTER —
     enforcing the ban mechanically (test_cog3_import_gate.py + test_cog3_ovi_parity.py).

PINNED, NO CLOCK (A-M6 mirrored): the window is a DECLARED argument (--cutoff /
--window-days), never a datetime.now read — the legacy production gather is
datetime.now-windowed (compute.py), so this harness feeds BOTH sides a pinned raw
sample over the declared window (a fixed default, a --sample-data override, or the
COG3_OVI_PARITY_DATA_JSON test seam). Exact-only, no per-instrument tolerance
(rev-0 §15 Q7 CLOSED): a mismatch is a BREACH, not a tolerance case.

Verdict statuses / exit codes:
  ok       every legacy instrument matches the objectives projection      -> exit 0
  breach   >=1 instrument diverges / is absent on one side                -> exit 1
  error    the CONFIGURED view reader broke (non-zero / garbage / a
           forbidden composite emission — top-level OR a numeric aggregate
           smuggled inside an instrument cell under a non-listed key —
           attack C-M4)                                                   -> exit 1

Modes:
  (default)  one parity run, print the verdict JSON, exit per status above
  --json     machine-readable verdict on stdout

Tests: cabinet/scripts/tests/test_cog3_ovi_parity.py.

Provenance: authored + self-ratified per the 2026-07-07 full-autonomy grant +
the 2026-07-20 cognitive-masterplan continuous grant; wave-4 phase-complete.
"""
from __future__ import annotations

# Module top stays stdlib-only re: the phase under test — the import ban forbids
# reaching framework.objectives at all; framework.ovi.compute (the legacy ground
# truth) is a LAZY in-function import so this file never even transitively loads
# the objectives package.
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

# The five OVI instruments the legacy components.yml defines — every raw sample
# must carry them all (compute_ovi rejects a missing component).
_DEFAULT_SAMPLE = {
    "task_throughput": 30.0,
    "outcome_progress": 0.6,
    "captain_attention_cost": 4.0,
    "learning_rate": 2.0,
    "verification_pass_rate": 0.85,
}
# forbidden aggregate tokens — a per-instrument view may carry NONE (attack C-M4).
_FORBIDDEN_AGGREGATE = ("composite_score", "composite", "weights", "weight")
# the SOLE pinned per-instrument cell field: ovi_view.project emits
# {name: {"value": measure}}. A numeric value under ANY other key INSIDE a cell is
# an aggregate smuggled where the top-level token scan above can't name it (a
# non-listed key like "rollup"/"total"/"score") — a loud error, never a silent
# per-instrument match (attack C-M4).
_PINNED_CELL_FIELDS = frozenset({"value"})


def _is_number(value: object) -> bool:
    # bools are ints in Python; a smuggled aggregate is a real number, never a flag.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _repo_root() -> Path:
    return Path(os.environ.get("CABINET_ROOT") or _REPO_ROOT)


class _ViewFailed(RuntimeError):
    """The CONFIGURED objectives-view reader broke — a loud `error` verdict, never
    a silent green. Carries only an inert reason (exit code / class), never argv."""


# ---------------------------------------------------------------------------
# the pure parity core
# ---------------------------------------------------------------------------

_ABSENT = "\x00absent"


def parity_scan(*, ground_truth: dict, projection: dict) -> dict:
    """PURE: compare the legacy per-instrument components (ground truth) to the
    objectives view's per-instrument projection, EXACT per instrument (N6 exact-
    only — no tolerance). A missing instrument on either side or any value
    mismatch is a breach. Returns the verdict dict. No I/O."""
    mismatches = []
    for name in sorted(set(ground_truth) | set(projection)):
        legacy = ground_truth.get(name, _ABSENT)
        objectives = projection.get(name, _ABSENT)
        if legacy != objectives:
            reason = ("absent_objectives" if objectives == _ABSENT else
                      "absent_legacy" if legacy == _ABSENT else "value_mismatch")
            mismatches.append({"instrument": name, "reason": reason,
                               "legacy": None if legacy == _ABSENT else legacy,
                               "objectives": None if objectives == _ABSENT else objectives})
    return {"status": "breach" if mismatches else "ok",
            "instruments": sorted(ground_truth), "mismatches": mismatches}


# ---------------------------------------------------------------------------
# ground truth (legacy module) + projection (external black box)
# ---------------------------------------------------------------------------

def _legacy_components(raw: dict, components_path: str | None) -> dict:
    """GROUND TRUTH: the legacy per-instrument NORMALIZED components (the composite
    scalar is IGNORED — the graph refuses it). Lazy import of the INDEPENDENT
    legacy module framework.ovi.compute (never the objectives view — C-F17)."""
    repo = str(_repo_root())
    if repo not in sys.path:
        sys.path.insert(0, repo)
    from framework.ovi.compute import compute_ovi
    snapshot = compute_ovi(dict(raw), emit_event=False, components_path=components_path)
    return dict(snapshot["components"])   # {name: normalized}; composite_score dropped


def _default_view_cmd() -> list[str]:
    """The objectives per-instrument view as an EXTERNAL black box: a child
    python3.12 -c that imports framework.objectives.ovi_view IN THE CHILD (never
    this parent — the import ban) and projects the instruments read on stdin.
    Assembled as argv, never shell-interpolated."""
    driver = (
        "import json, sys\n"
        "from framework.objectives import ovi_view\n"
        "print(json.dumps(ovi_view.project(json.load(sys.stdin))))\n"
    )
    return [sys.executable, "-c", driver]


def _projection(instruments: dict, cmd: list[str]) -> dict:
    """The objectives per-instrument view, read as an EXTERNAL subprocess (the
    import ban, C-F17): {name: {"value": v}} -> {name: v}. A non-zero reader, a
    garbage payload, or a forbidden composite/aggregate key is a loud error."""
    try:
        proc = subprocess.run(cmd, input=json.dumps(instruments), capture_output=True,
                              text=True, cwd=str(_repo_root()), timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise _ViewFailed(f"ovi_view reader failed: {type(exc).__name__}") from None
    if proc.returncode != 0:
        raise _ViewFailed(f"ovi_view reader exited {proc.returncode}")
    try:
        data = json.loads(proc.stdout.strip() or "{}")
    except json.JSONDecodeError:
        raise _ViewFailed("ovi_view reader output is not JSON") from None
    if not isinstance(data, dict):
        raise _ViewFailed("ovi_view reader output is not a JSON object")
    blob = json.dumps(data).lower()
    for token in _FORBIDDEN_AGGREGATE:
        if token in blob:
            raise _ViewFailed(f"ovi_view emitted a forbidden aggregate {token!r} (attack C-M4)")
    out = {}
    for name, cell in data.items():
        if isinstance(cell, dict):
            # a numeric value under any key beyond the pinned per-instrument field
            # is a composite smuggled inside the cell (a non-listed key the token
            # scan above cannot name) — loud error (attack C-M4).
            smuggled = sorted(k for k, v in cell.items()
                              if k not in _PINNED_CELL_FIELDS and _is_number(v))
            if smuggled:
                raise _ViewFailed(
                    f"ovi_view smuggled a numeric aggregate under {smuggled!r} inside "
                    f"instrument {name!r}, beyond the pinned {sorted(_PINNED_CELL_FIELDS)} "
                    "field (attack C-M4)")
            out[name] = cell.get("value")
        else:
            out[name] = cell
    return out


def _resolve_raw(sample_data: str | None) -> dict:
    """Resolve the pinned raw sample_data for the declared window. Priority: the
    COG3_OVI_PARITY_DATA_JSON test seam, the --sample-data arg (inline JSON or
    @file), else the fixed default. NEVER a clock read (A-M6)."""
    seam = os.environ.get("COG3_OVI_PARITY_DATA_JSON", "").strip()
    if seam:
        return json.loads(Path(seam).read_text(encoding="utf-8"))
    if sample_data:
        text = (Path(sample_data[1:]).read_text(encoding="utf-8")
                if sample_data.startswith("@") else sample_data)
        return json.loads(text)
    return dict(_DEFAULT_SAMPLE)


def run(*, cutoff: str, window_days: int, sample_data: str | None = None,
        components_path: str | None = None, view_cmd: list[str] | None = None) -> dict:
    """One parity cycle: pinned raw over the DECLARED window -> legacy components
    (ground truth) -> objectives projection (external) -> per-instrument compare.
    Returns the verdict dict (adds the declared window provenance)."""
    raw = _resolve_raw(sample_data)
    ground_truth = _legacy_components(raw, components_path)
    cmd = view_cmd or _shell_view_cmd() or _default_view_cmd()
    try:
        # the per-instrument values the two views SHARE (inputs overlap, N6): the
        # legacy's normalized components, projected by the objectives view.
        projection = _projection(ground_truth, cmd)
    except _ViewFailed as exc:
        return {"status": "error", "note": str(exc), "cutoff": cutoff,
                "window_days": window_days, "instruments": sorted(ground_truth),
                "mismatches": []}
    verdict = parity_scan(ground_truth=ground_truth, projection=projection)
    verdict.update(cutoff=cutoff, window_days=window_days)
    return verdict


def _shell_view_cmd() -> list[str] | None:
    """An operator-configured objectives-view command (COG3_OVI_VIEW_CMD), split as
    argv — the external black-box seam the tests point at a perturbing reader."""
    import shlex
    raw = os.environ.get("COG3_OVI_VIEW_CMD", "").strip()
    return shlex.split(raw) if raw else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="COG-3 OVI per-instrument shadow-parity falsifier (C-F17, §6.6/N6)")
    parser.add_argument("--cutoff", default="2026-07-21T00:00:00Z",
                        help="the DECLARED window end (provenance only; never a clock read)")
    parser.add_argument("--window-days", type=int, default=7,
                        help="the DECLARED rolling window in days (provenance)")
    parser.add_argument("--sample-data", default=None,
                        help="pinned raw sample_data as inline JSON or @file (overrides the default)")
    parser.add_argument("--components", default=None,
                        help="path to the OVI components.yml (default: the legacy sibling)")
    parser.add_argument("--json", action="store_true", help="emit the verdict as JSON")
    args = parser.parse_args(argv)

    verdict = run(cutoff=args.cutoff, window_days=args.window_days,
                  sample_data=args.sample_data, components_path=args.components)

    if args.json:
        print(json.dumps(verdict, sort_keys=True))
    elif verdict["status"] == "ok":
        print(f"cog3-ovi-parity: ok — {len(verdict['instruments'])} instruments "
              "agree with the legacy per-instrument components (no composite)")
    elif verdict["status"] == "error":
        print(f"cog3-ovi-parity: ERROR {verdict.get('note', '')}", file=sys.stderr)
    else:
        print(f"cog3-ovi-parity: BREACH {len(verdict['mismatches'])} instrument(s) "
              "diverge from the legacy per-instrument components:", file=sys.stderr)
        for m in verdict["mismatches"]:
            print(f"  + {m['instrument']}: legacy={m['legacy']!r} "
                  f"objectives={m['objectives']!r} ({m['reason']})", file=sys.stderr)

    return 0 if verdict["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
