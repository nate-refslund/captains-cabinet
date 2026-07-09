#!/usr/bin/env python3.12
"""world-growth-validate.py — schema + truth validator for cabinet/world/growth-ladders.yml

Law family: morphology/show-grammar (world-data class, never germlined).
Spec of record: docs/plans/world-unified-spec-v2-2026-07-09.md §15.2–15.4
(ERA×RUNG two-axis growth; Captain addendum 2). Ledger: WORLD-GROWTH-CALIBRATION
(docs/plans/operative-egg-ledger-2026-07-07.yml).

What it refuses (the untruthful-config gate):
  * any ladder whose `metric` is NOT in the REAL_FIELDS registry below — every
    rung must cite a real, live-verified census/snapshot/ledger field
    ("validator refuses malformed/untruthful configs (rung must cite a real
    metric)" — captain-addendum-2 §3);
  * a ladder whose `source` disagrees with the registry's source of truth;
  * a ladder without a `verified: {value, date}` citation;
  * era baskets whose weights don't sum to 1.0, unknown curves, non-ascending
    thresholds, missing hysteresis (hysteresis is MANDATORY on era — no era
    flapping), era hold < 2 evals (the ratified 2-keyframe law);
  * unknown modes, rungs lists that are too short, tier ladders without a
    positive log2 base, vocab keys outside the era names.

Usage:
  python3.12 cabinet/scripts/world-growth-validate.py [path ...]
  (default path: cabinet/world/growth-ladders.yml)

Read-only. Exit 0 = every file valid; exit 1 = any refusal (reasons printed).
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
DEFAULT = REPO / "cabinet" / "world" / "growth-ladders.yml"

SCHEMA_ID = "cabinet.world.growth-ladders/v1"
ERA_NAMES = ["camp", "hamlet", "town", "beyond_bay"]
CURVES = {"linear", "log2", "log10"}
MODES = {"tier", "count", "flag", "per_lane"}
CLASSES = {"great", "quick", "texture"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# ── REAL_FIELDS registry ────────────────────────────────────────────────────
# Every entry is a REAL metric with a durable source of truth, live-verified
# read-only during the 2026-07-08/09 world-next tracks (growth-grammar.md §7,
# bestiary.md, spec v2 §11). `avail` notes what the calibration backtest can
# reconstruct per-day from durable history:
#   daily_db        — org_events sqlite (cabinet/cache/org-runtime.sqlite3)
#   daily_git       — this repo's commit dates (git log)
#   daily_outcomes  — instance/config/outcomes.yml status flips via git history
#   keyframe        — shared/interfaces/world-chronicle.jsonl daily census
#   snapshot        — live Redis snapshot (P-TANK staged; keyframe field later)
REAL_FIELDS = {
    # org_events sqlite census (world-census.py EVENT_TYPES) — keyframe fields
    "org_events_total":                  {"source": "census_keyframe", "avail": "daily_db",  "live": 168917, "date": "2026-07-09"},
    "ev_session_started":                {"source": "census_keyframe", "avail": "daily_db",  "live": 9961,   "date": "2026-07-09"},
    "ev_session_ended":                  {"source": "census_keyframe", "avail": "daily_db",  "live": 11987,  "date": "2026-07-09"},
    "ev_role_defined":                   {"source": "census_keyframe", "avail": "daily_db",  "live": 4,      "date": "2026-07-09"},
    "ev_subagent_completed":             {"source": "census_keyframe", "avail": "daily_db",  "live": 1783,   "date": "2026-07-09"},
    "ev_work_item_completed":            {"source": "census_keyframe", "avail": "daily_db",  "live": 6708,   "date": "2026-07-09"},
    "ev_self_improvement_loop_completed": {"source": "census_keyframe", "avail": "daily_db", "live": 14,     "date": "2026-07-09"},
    "ev_graduation_transition":          {"source": "census_keyframe", "avail": "daily_db",  "live": 15,     "date": "2026-07-09"},
    "ev_skill_promoted":                 {"source": "census_keyframe", "avail": "daily_db",  "live": 4,      "date": "2026-07-09"},
    "ev_mission_created":                {"source": "census_keyframe", "avail": "daily_db",  "live": 10,     "date": "2026-07-09"},
    "events_today":                      {"source": "census_keyframe", "avail": "daily_db",  "live": 3091,   "date": "2026-07-09"},
    # census keyframe fields with no per-day backtest series before 2026-07-07
    "commits_total":                     {"source": "census_keyframe", "avail": "daily_git", "live": 1032,   "date": "2026-07-09"},
    # repo commits anchored at ORG genesis (MIN(created_at) in org_events) —
    # the egg-honest growth metric: a fresh deployment starts at 0; this
    # retrofit deployment subtracts the 480 pre-runtime scaffolding commits.
    # Durable + replayable from git history; world snapshot computes it with
    # the same world-census git reader + the org_events genesis anchor.
    "commits_since_genesis":             {"source": "commits_ledger", "avail": "daily_git", "live": 554,    "date": "2026-07-09"},
    "memory_rows_total":                 {"source": "census_keyframe", "avail": "keyframe",  "live": 1291,   "date": "2026-07-09"},
    "tier2_note_files":                  {"source": "census_keyframe", "avail": "keyframe",  "live": 43,     "date": "2026-07-09"},
    "tier3_files":                       {"source": "census_keyframe", "avail": "keyframe",  "live": 39,     "date": "2026-07-09"},
    "evolved_skills":                    {"source": "census_keyframe", "avail": "keyframe",  "live": 9,      "date": "2026-07-09"},
    "golden_evals":                      {"source": "census_keyframe", "avail": "keyframe",  "live": 21,     "date": "2026-07-09"},
    "captain_rules":                     {"source": "census_keyframe", "avail": "keyframe",  "live": 39,     "date": "2026-07-09"},
    "captain_vetoes_total":              {"source": "census_keyframe", "avail": "keyframe",  "live": 0,      "date": "2026-07-09"},
    "cells_accumulating":                {"source": "census_keyframe", "avail": "keyframe",  "live": 18,     "date": "2026-07-09"},
    "cells_graduated":                   {"source": "census_keyframe", "avail": "keyframe",  "live": 0,      "date": "2026-07-09"},
    "services_rows_total":               {"source": "census_keyframe", "avail": "keyframe",  "live": 38,     "date": "2026-07-09"},
    "services_rows_disabled":            {"source": "census_keyframe", "avail": "keyframe",  "live": 2,      "date": "2026-07-09"},
    "packs_dirs":                        {"source": "census_keyframe", "avail": "keyframe",  "live": 5,      "date": "2026-07-09"},
    "outcomes_total":                    {"source": "census_keyframe", "avail": "keyframe",  "live": 10,     "date": "2026-07-09"},
    # outcomes ledger deriveds (instance/config/outcomes.yml; flip dates in git)
    "outcomes_active":                   {"source": "outcomes_yml", "avail": "daily_outcomes", "live": 6,  "date": "2026-07-09"},
    "outcomes_achieved":                 {"source": "outcomes_yml", "avail": "daily_outcomes", "live": 2,  "date": "2026-07-09"},
    "outcomes_retired":                  {"source": "outcomes_yml", "avail": "daily_outcomes", "live": 1,  "date": "2026-07-09"},
    "active_lanes":                      {"source": "outcomes_yml", "avail": "daily_outcomes", "live": 3,  "date": "2026-07-09"},
    "outcomes_active_system_self":       {"source": "outcomes_yml", "avail": "daily_outcomes", "live": 3,  "date": "2026-07-09"},
    "outcomes_by_lane":                  {"source": "outcomes_yml", "avail": "daily_outcomes", "live": 4,  "date": "2026-07-09"},
    # world chronicle (census keyframe ledger itself)
    "world_chronicle_keyframes":         {"source": "world_chronicle", "avail": "keyframe",  "live": 3,     "date": "2026-07-09"},
    # org genesis (MIN(created_at) over org_events — 2026-05-25T18:53:20Z)
    "org_age_days":                      {"source": "org_events_db", "avail": "daily_db",    "live": 45,    "date": "2026-07-09"},
    # live Redis snapshot fields (staged into keyframes later; real today)
    "memory_embed_queue_xlen":           {"source": "redis_snapshot", "avail": "snapshot",   "live": 1076,  "date": "2026-07-09"},  # P-TANK
    "pending_captain_items":             {"source": "redis_snapshot", "avail": "snapshot",   "live": 0,     "date": "2026-07-09"},  # P1
}


def _err(errors: list, path: str, msg: str) -> None:
    errors.append(f"{path}: {msg}")


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_basket(era: dict, errors: list) -> None:
    basket = era.get("basket")
    if not isinstance(basket, dict) or not basket:
        _err(errors, "era.basket", "missing or empty — the era index needs a weighted basket of real metrics")
        return
    total = 0.0
    for name, spec in basket.items():
        p = f"era.basket.{name}"
        reg = REAL_FIELDS.get(name)
        if reg is None:
            _err(errors, p, f"metric '{name}' is not a real field (not in REAL_FIELDS registry) — refused")
            continue
        if not isinstance(spec, dict):
            _err(errors, p, "must be a mapping {weight, curve, cap, source}")
            continue
        w = spec.get("weight")
        if not _num(w) or w <= 0 or w > 1:
            _err(errors, p, f"weight must be a number in (0,1], got {w!r}")
        else:
            total += float(w)
        if spec.get("curve") not in CURVES:
            _err(errors, p, f"curve must be one of {sorted(CURVES)}, got {spec.get('curve')!r}")
        cap = spec.get("cap")
        if not _num(cap) or cap <= 0:
            _err(errors, p, f"cap must be a positive number (value at which the metric saturates), got {cap!r}")
        if spec.get("source") != reg["source"]:
            _err(errors, p, f"source must cite the registry source of truth '{reg['source']}', got {spec.get('source')!r}")
    if not math.isclose(total, 1.0, abs_tol=1e-6):
        _err(errors, "era.basket", f"weights must sum to 1.0 (got {total:.6f})")


def validate_era(era: dict, errors: list) -> None:
    if not isinstance(era, dict):
        _err(errors, "era", "missing era block")
        return
    if era.get("names") != ERA_NAMES:
        _err(errors, "era.names", f"must be exactly {ERA_NAMES} (fixed v1 vocabulary order)")
    validate_basket(era, errors)
    th = era.get("thresholds")
    if not isinstance(th, dict) or set(th) != set(ERA_NAMES):
        _err(errors, "era.thresholds", f"must carry exactly the era names {ERA_NAMES}")
    else:
        vals = [th[n] for n in ERA_NAMES]
        if not all(_num(v) for v in vals):
            _err(errors, "era.thresholds", "all thresholds must be numbers")
        else:
            if vals[0] != 0.0:
                _err(errors, "era.thresholds", "camp must be 0.0 (the egg is era floor)")
            if any(b <= a for a, b in zip(vals, vals[1:])):
                _err(errors, "era.thresholds", f"must be strictly ascending, got {vals}")
            if any(v < 0 or v >= 1 for v in vals):
                _err(errors, "era.thresholds", f"must live in [0,1), got {vals}")
    hy = era.get("hysteresis")
    if not isinstance(hy, dict):
        _err(errors, "era.hysteresis", "MANDATORY (Captain addendum 2: no era flapping)")
    else:
        hold = hy.get("advance_hold_evals")
        if not isinstance(hold, int) or hold < 2:
            _err(errors, "era.hysteresis.advance_hold_evals",
                 f"must be an int >= 2 (the ratified 2-keyframe hysteresis law), got {hold!r}")
        margin = hy.get("demote_margin")
        if not _num(margin) or not (0 < margin <= 0.2):
            _err(errors, "era.hysteresis.demote_margin", f"must be a number in (0, 0.2], got {margin!r}")


def validate_ladder(name: str, lad: dict, errors: list) -> None:
    p = f"ladders.{name}"
    if not isinstance(lad, dict):
        _err(errors, p, "must be a mapping")
        return
    metric = lad.get("metric")
    reg = REAL_FIELDS.get(metric)
    if reg is None:
        _err(errors, p, f"metric {metric!r} is not a real field (not in REAL_FIELDS registry) — "
                        "every rung must cite a real census/snapshot/ledger metric; REFUSED")
        return
    if lad.get("source") != reg["source"]:
        _err(errors, p, f"source must cite the registry source of truth '{reg['source']}', got {lad.get('source')!r}")
    ver = lad.get("verified")
    if not isinstance(ver, dict) or not _num(ver.get("value")) or not (
            isinstance(ver.get("date"), str) and DATE_RE.match(ver["date"])):
        _err(errors, p, "verified: {value: <number>, date: 'YYYY-MM-DD'} citation is required "
                        "(the live-verified value this ladder was calibrated against)")
    mode = lad.get("mode")
    if mode not in MODES:
        _err(errors, p, f"mode must be one of {sorted(MODES)}, got {mode!r}")
        return
    rungs = lad.get("rungs")
    if not isinstance(rungs, list) or len(rungs) < 2 or not all(isinstance(r, str) and r for r in rungs):
        _err(errors, p, "rungs must be a list of >= 2 stage names")
        return
    if mode == "tier":
        base = lad.get("base")
        if not _num(base) or base <= 0:
            _err(errors, p, f"tier mode requires a positive log2 base "
                            f"(rung = clamp(floor(log2(v/base + 1)), 0, len(rungs)-1)), got {base!r}")
    if mode == "flag":
        if len(rungs) != 2:
            _err(errors, p, f"flag mode requires exactly 2 rungs, got {len(rungs)}")
        at = lad.get("at", 1)
        if not _num(at) or at < 1:
            _err(errors, p, f"flag 'at' threshold must be a number >= 1, got {at!r}")
    if mode == "per_lane" and not str(metric).endswith("_by_lane"):
        _err(errors, p, f"per_lane mode requires a *_by_lane metric, got {metric!r}")
    he = lad.get("hysteresis_evals")
    if not isinstance(he, int) or he < 1:
        _err(errors, p, f"hysteresis_evals must be an int >= 1, got {he!r}")
    if lad.get("class") not in CLASSES:
        _err(errors, p, f"class must be one of {sorted(CLASSES)}, got {lad.get('class')!r}")
    vocab = lad.get("vocab")
    if vocab is not None:
        if not isinstance(vocab, dict) or not set(vocab) <= set(ERA_NAMES):
            _err(errors, p, f"vocab keys must be a subset of the era names {ERA_NAMES}")
        elif not all(isinstance(v, str) and v for v in vocab.values()):
            _err(errors, p, "vocab values must be non-empty sprite-family tokens")


def validate(path: Path) -> list:
    errors: list = []
    try:
        doc = yaml.safe_load(path.read_text())
    except Exception as exc:  # malformed yaml = refused
        return [f"{path}: unparseable YAML — {exc}"]
    if not isinstance(doc, dict):
        return [f"{path}: top level must be a mapping"]
    if doc.get("schema") != SCHEMA_ID:
        _err(errors, "schema", f"must be '{SCHEMA_ID}', got {doc.get('schema')!r}")
    if not isinstance(doc.get("version"), int) or doc["version"] < 1:
        _err(errors, "version", f"must be an int >= 1, got {doc.get('version')!r}")
    validate_era(doc.get("era"), errors)
    ladders = doc.get("ladders")
    if not isinstance(ladders, dict) or not ladders:
        _err(errors, "ladders", "missing or empty — every bound element needs its ladder")
    else:
        for name, lad in ladders.items():
            validate_ladder(name, lad, errors)
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate growth-ladders.yml (schema + real-metric citations)")
    ap.add_argument("paths", nargs="*", default=[str(DEFAULT)],
                    help=f"config file(s) to validate (default: {DEFAULT})")
    ap.add_argument("--quiet", action="store_true", help="suppress the green summary")
    args = ap.parse_args()

    rc = 0
    for raw in (args.paths or [str(DEFAULT)]):
        path = Path(raw).resolve()
        if not path.is_file():
            print(f"REFUSED {raw}: file not found", file=sys.stderr)
            rc = 1
            continue
        errors = validate(path)
        if errors:
            rc = 1
            print(f"REFUSED {path} ({len(errors)} problem(s)):", file=sys.stderr)
            for e in errors:
                print(f"  - {e}", file=sys.stderr)
        elif not args.quiet:
            doc = yaml.safe_load(path.read_text())
            print(f"OK {path} — schema {SCHEMA_ID}, "
                  f"{len(doc.get('ladders') or {})} ladders, "
                  f"{len((doc.get('era') or {}).get('basket') or {})} basket metrics, "
                  "every rung metric cited from REAL_FIELDS")
    return rc


if __name__ == "__main__":
    sys.exit(main())
