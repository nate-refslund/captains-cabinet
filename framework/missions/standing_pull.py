"""Standing pull [sovereign spec §4 SOV-8] — R1-R6 ranked internal work
sources → `shared/interfaces/standing-missions.yml`.

Sovereign doctrine: the cabinet never idles waiting for a Captain outcome —
it PULLS standing work from its own ledgers, ranked by how directly the work
unblocks or protects the estate:

  R1  blocking/open needs        (needs-ledger: unblock the chain first)
  R2  capability gaps            (approved-then-open first, then hit_count)
  R3  integrity repair           (frozen kinds / red canary receipts)
  R4  verification debt          (stale falsifier telemetry — "a falsifier
                                  you cannot measure is theater")
  R5  hygiene                    (proposals parked pending_captain, draft
                                  skills awaiting validation)
  R6  label starvation           (prediction-calibration series: predictions
                                  flow but ground truth doesn't — the learning
                                  core runs on labels, so repair the supply)

The pull writes ONE file — `shared/interfaces/standing-missions.yml`, in the
outcomes-schema shape (`deployment:` + `outcomes:` list) so the mission
supervisor can compile it as its SECOND source when sovereign. It **never
touches the Captain's `instance/config/outcomes.yml`** — `_refuse_captain_
paths` raises on any write target named outcomes.yml or under instance/,
and the test suite pins that guarantee. Outcome ids are deterministic
(`standing-<src>-<sha8>`) so re-runs re-rank instead of duplicating, and the
supervisor's assignment replay stays idempotent.

`run()` is sovereign-gated: guardian resolves ⇒ NO write, no side effects —
the guardian world stays bit-identical (the supervisor also refuses to
compile the file in guardian; two independent gates).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

_FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]
if str(_FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(_FRAMEWORK_ROOT))

SOURCES = ("R1", "R2", "R3", "R4", "R5", "R6")
DEFAULT_CAP = 5           # standing outcomes written per pull (highest rank first)
FALSIFIER_STALE_DAYS = 3  # R4 fires when the series is silent this long
LABEL_RATIO_FLOOR = 0.2   # R6: below this ground-truthed/predictions = starved
LABEL_MIN_PREDICTIONS = 5  # R6 ratio only judged on a non-trivial sample
LABEL_STALE_DAYS = 3      # R6: series silent this long = supply unmeasured


def _root(root: str | Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(os.environ.get("CABINET_ROOT") or str(_FRAMEWORK_ROOT))


def _cabinet_id() -> str:
    return os.environ.get("CABINET_ID", "main")


def _now(now: str | None = None) -> str:
    if now:
        return now
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def standing_missions_path(root: str | Path | None = None) -> Path:
    return _root(root) / "shared" / "interfaces" / "standing-missions.yml"


def _sid(source: str, seed: str) -> str:
    return f"standing-{source.lower()}-" + hashlib.sha256(
        f"{source}|{seed}|{_cabinet_id()}".encode("utf-8")).hexdigest()[:8]


def _no_marker(s: str) -> str:
    return (s or "").replace("·", "")


# ---------------------------------------------------------------------------
# The Captain-file guard — standing_pull can NEVER write outcomes.yml
# ---------------------------------------------------------------------------

def _refuse_captain_paths(path: Path) -> Path:
    """Raise on any write target that is (or aliases) a Captain-owned file.
    The pull owns exactly one artifact: shared/interfaces/standing-missions.yml."""
    name = path.name.lower()
    parts = {p.lower() for p in path.parts}
    if name == "outcomes.yml" or "instance" in parts:
        raise PermissionError(
            f"standing_pull may never write Captain files: {path}")
    if name != "standing-missions.yml":
        raise PermissionError(
            f"standing_pull writes only standing-missions.yml, not {path}")
    return path


# ---------------------------------------------------------------------------
# R1-R5 collectors (each fail-harmless: an unreadable source yields nothing)
# ---------------------------------------------------------------------------

def _r1_needs(root: Path, now: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        from framework.authority import needs
        for row in needs.list_open(now, root=root):
            if row.get("status") != "open":
                continue
            blocking = row.get("cost_of_delay") == "blocking"
            nid = str(row.get("id"))
            out.append({
                "source": "R1",
                "rank": (0 if blocking else 1, -int(row.get("count") or 1)),
                "id": _sid("R1", nid),
                "name": f"Resolve open need {nid}",
                "description": _no_marker(
                    f"[standing/R1] {row.get('kind')}: {row.get('why') or ''}")[:300],
                "criteria": [
                    f"Need {nid} is granted, denied, or superseded in the needs ledger",
                ],
            })
    except Exception:
        return out
    return out


def _r2_gaps(root: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        from framework.learning.capability_gaps import (
            STATUS_APPROVED, STATUS_OPEN, project_gaps)
        for g in project_gaps():
            status = g.get("status")
            if status not in (STATUS_APPROVED, STATUS_OPEN):
                continue
            gid = str(g.get("gap_id"))
            out.append({
                "source": "R2",
                "rank": (0 if status == STATUS_APPROVED else 1,
                         -int(g.get("hit_count") or 1)),
                "id": _sid("R2", gid),
                "name": f"Close capability gap {gid}",
                "description": _no_marker(
                    f"[standing/R2] {status}: {g.get('need') or ''}")[:300],
                "criteria": [
                    f"Capability gap {gid} is resolved (or declined by the Captain)",
                ],
            })
    except Exception:
        return out
    return out


def _r3_integrity(now: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        from framework.frontdoor import action_undo
        seen: set[str] = set()
        # Frozen kinds (last-op-wins mirror) — repair work.
        try:
            mirror = action_undo._frozen_mirror()  # noqa: SLF001 — read-only peek
            last: dict[str, dict[str, Any]] = {}
            if mirror.exists():
                for line in mirror.read_text().splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(row, dict) and row.get("kind"):
                        last[str(row["kind"])] = row
            for kind, row in sorted(last.items()):
                if row.get("op") == "unfreeze":
                    continue
                seen.add(kind)
                out.append({
                    "source": "R3",
                    "rank": (0, kind),
                    "id": _sid("R3", f"frozen:{kind}"),
                    "name": f"Repair frozen kind {kind}",
                    "description": _no_marker(
                        f"[standing/R3] kind {kind} is frozen "
                        f"({row.get('reason') or 'no reason recorded'}) — "
                        "diagnose, green a canary, thaw or rearm")[:300],
                    "criteria": [f"Kind {kind} is unfrozen with a green canary receipt"],
                })
        except Exception:
            pass
        # Red canaries on unfrozen kinds still need a diagnosis.
        for r in action_undo.canary_receipts():
            kind = str(r.get("kind") or "")
            if r.get("green") or not kind or kind in seen:
                continue
            seen.add(kind)
            out.append({
                "source": "R3",
                "rank": (1, kind),
                "id": _sid("R3", f"red:{kind}"),
                "name": f"Diagnose red canary on {kind}",
                "description": _no_marker(
                    f"[standing/R3] newest canary work for kind {kind} includes a "
                    f"red receipt at {r.get('ts')}")[:300],
                "criteria": [f"A green canary receipt exists for {kind} newer than the red"],
            })
    except Exception:
        return out
    return out


def _r4_falsifier(root: Path, now: str) -> list[dict[str, Any]]:
    try:
        series = root / "shared" / "interfaces" / "falsifier-series.jsonl"
        nowdt = datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
        floor = (nowdt - timedelta(days=FALSIFIER_STALE_DAYS)).date().isoformat()
        newest = ""
        if series.exists():
            for line in series.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    newest = max(newest, str(row.get("date") or ""))
        if newest >= floor:
            return []
        detail = newest or "never"
        return [{
            "source": "R4",
            "rank": (0, detail),
            "id": _sid("R4", "stale-series"),
            "name": "Restore falsifier telemetry",
            "description": _no_marker(
                f"[standing/R4] falsifier-series.jsonl newest line is {detail} "
                f"(> {FALSIFIER_STALE_DAYS}d stale) — a falsifier you cannot "
                "measure is theater")[:300],
            "criteria": ["falsifier-series.jsonl carries a line dated within 1 day"],
        }]
    except Exception:
        return []


def _r5_hygiene(root: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        import yaml
        pdir = root / "instance" / "roles" / "proposals"
        if pdir.is_dir():
            for p in sorted(pdir.glob("*.yml"))[:10]:
                try:
                    data = yaml.safe_load(p.read_text()) or {}
                except Exception:
                    continue
                if data.get("status") != "pending_captain_approval":
                    continue
                out.append({
                    "source": "R5",
                    "rank": (0, p.stem),
                    "id": _sid("R5", f"proposal:{p.stem}"),
                    "name": f"Prepare decision brief for proposal {p.stem}",
                    "description": _no_marker(
                        "[standing/R5] a role proposal is parked "
                        f"pending_captain_approval ({p.name}) — assemble the "
                        "evidence brief so one Captain tap decides it")[:300],
                    "criteria": [f"Proposal {p.stem} carries a decision-ready brief"],
                })
        sdir = root / "memory" / "skills" / "evolved"
        if sdir.is_dir():
            for p in sorted(sdir.glob("induced-*.md"))[:10]:
                try:
                    text = p.read_text()
                except OSError:
                    continue
                if "status: draft" not in text:
                    continue
                out.append({
                    "source": "R5",
                    "rank": (1, p.stem),
                    "id": _sid("R5", f"skill:{p.stem}"),
                    "name": f"Validate draft skill {p.stem}",
                    "description": _no_marker(
                        f"[standing/R5] induced skill {p.name} awaits a "
                        "validation scenario + eval before promotion")[:300],
                    "criteria": [f"Skill {p.stem} passes its validation eval or is retired"],
                })
    except Exception:
        return out
    return out


def _r6_labels(root: Path, now: str) -> list[dict[str, Any]]:
    """Label-starvation repair (2026-07-09, report #1 priority): the learning
    core runs on labels, and the prediction-calibration series (W9/A10) is
    where the supply is measured. Fires when predictions flow but ground
    truth doesn't (ratio under LABEL_RATIO_FLOOR on a non-trivial sample, or
    zero labels at all), or when the supply is UNMEASURED (series absent /
    stale) — an unmeasured label economy is starvation you can't even see."""
    try:
        series = root / "shared" / "interfaces" / "prediction-calibration.jsonl"
        nowdt = datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
        floor = (nowdt - timedelta(days=LABEL_STALE_DAYS)).date().isoformat()
        newest: dict[str, Any] = {}
        if series.exists():
            for line in series.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and \
                        str(row.get("date") or "") >= str(newest.get("date") or ""):
                    newest = row
        newest_date = str(newest.get("date") or "")
        if not newest_date or newest_date < floor:
            detail = newest_date or "never"
            return [{
                "source": "R6",
                "rank": (1, detail),
                "id": _sid("R6", "unmeasured"),
                "name": "Restore label-supply telemetry",
                "description": _no_marker(
                    f"[standing/R6] prediction-calibration.jsonl newest line is "
                    f"{detail} (> {LABEL_STALE_DAYS}d stale) — the label economy "
                    "is unmeasured; get the prediction scorer emitting again")[:300],
                "criteria": [
                    "prediction-calibration.jsonl carries a line dated within 1 day",
                ],
            }]
        n_pred = int(newest.get("n_predictions") or 0)
        n_truth = int(newest.get("n_ground_truthed") or 0)
        starved = (n_pred > 0 and n_truth == 0) or (
            n_pred >= LABEL_MIN_PREDICTIONS
            and n_truth / n_pred < LABEL_RATIO_FLOOR)
        if not starved:
            return []
        return [{
            "source": "R6",
            "rank": (0, newest_date),
            "id": _sid("R6", "starved"),
            "name": "Repair label starvation",
            "description": _no_marker(
                f"[standing/R6] {newest_date}: {n_truth}/{n_pred} predictions "
                "ground-truthed — the org acts and predicts but barely learns. "
                "Grow verdict supply: reconcile acted rows past TTL, surface "
                "binder verdicts, widen F1 label mining")[:300],
            "criteria": [
                "newest prediction-calibration line shows n_ground_truthed/"
                f"n_predictions >= {LABEL_RATIO_FLOOR} (sample >= "
                f"{LABEL_MIN_PREDICTIONS})",
            ],
        }]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# collect / write / run
# ---------------------------------------------------------------------------

def collect(
    root: str | Path | None = None,
    now: str | None = None,
) -> list[dict[str, Any]]:
    """Every standing-work candidate, ranked: R1 before R2 … before R6, then
    each source's own rank tuple. Read-only; never raises."""
    rootp = _root(root)
    ts = _now(now)
    candidates: list[dict[str, Any]] = []
    for src, rows in (("R1", _r1_needs(rootp, ts)), ("R2", _r2_gaps(rootp)),
                      ("R3", _r3_integrity(ts)), ("R4", _r4_falsifier(rootp, ts)),
                      ("R5", _r5_hygiene(rootp)), ("R6", _r6_labels(rootp, ts))):
        for row in rows:
            row["_order"] = (SOURCES.index(src), *row.pop("rank"))
            candidates.append(row)
    candidates.sort(key=lambda r: tuple(str(x) if not isinstance(x, (int, float))
                                        else x for x in r["_order"]))
    for row in candidates:
        row.pop("_order", None)
    return candidates


def write_standing_missions(
    candidates: list[dict[str, Any]],
    *,
    root: str | Path | None = None,
    cap: int = DEFAULT_CAP,
    now: str | None = None,
) -> Path:
    """Render the top `cap` candidates into standing-missions.yml (outcomes
    schema, deployment-pinned so no other cabinet compiles them). Idempotent:
    deterministic ids + full rewrite each pull."""
    import yaml
    path = _refuse_captain_paths(standing_missions_path(root))
    doc = {
        "deployment": _cabinet_id(),
        "generated_by": "framework.missions.standing_pull",
        "generated_at": _now(now),
        "outcomes": [
            {
                "id": c["id"],
                "name": c["name"],
                "description": c["description"],
                "measurable_criteria": list(c.get("criteria") or []),
                "status": "active",
            }
            for c in candidates[:cap]
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc, sort_keys=False, default_flow_style=False))
    return path


def _resolve_posture_safe() -> str:
    try:
        from framework.authority.posture import resolve_posture
        return resolve_posture()
    except Exception:
        return "guardian"


def run(
    root: str | Path | None = None,
    *,
    now: str | None = None,
    cap: int = DEFAULT_CAP,
    dry_run: bool = False,
    posture: str | None = None,
) -> dict[str, Any]:
    """One pull. Sovereign-gated: guardian ⇒ NO write (bit-identical world).
    dry_run ⇒ collect + report only. Never raises."""
    eff = posture if posture is not None else _resolve_posture_safe()
    try:
        candidates = collect(root, now)
    except Exception:
        candidates = []
    report: dict[str, Any] = {
        "posture": eff,
        "candidates": len(candidates),
        "by_source": {s: sum(1 for c in candidates if c["source"] == s)
                      for s in SOURCES},
        "written": 0,
        "detail": candidates[:cap],
    }
    if eff != "sovereign":
        report["skipped"] = "posture"
        return report
    if dry_run:
        report["skipped"] = "dry_run"
        return report
    try:
        path = write_standing_missions(candidates, root=root, cap=cap, now=now)
        report["written"] = min(cap, len(candidates))
        report["path"] = str(path)
    except Exception as exc:  # noqa: BLE001
        report["error"] = str(exc)
    return report


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI
    import argparse
    parser = argparse.ArgumentParser(
        description="Standing pull — R1-R6 ranked sources → standing-missions.yml "
                    "(sovereign only; never touches outcomes.yml).")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cap", type=int, default=DEFAULT_CAP)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = run(dry_run=args.dry_run, cap=args.cap)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(f"standing-pull: posture={report['posture']} "
              f"candidates={report['candidates']} written={report['written']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
