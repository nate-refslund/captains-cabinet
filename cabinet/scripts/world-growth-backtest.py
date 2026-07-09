#!/usr/bin/env python3.12
"""world-growth-backtest.py — THE CALIBRATION GATE harness (WORLD-GROWTH-CALIBRATION)

Replays the org's REAL history through candidate growth-ladders.yml configs and
emits, per candidate: a per-day/per-week timeline JSON (era-basket maturity
index, era with hysteresis, per-element ladder rungs, visible-change story
metrics) and — optionally — a timelapse STRIP png (one row of small world
renders per fortnight of real history) via the proven compositor lineage.

Spec of record: docs/plans/world-unified-spec-v2-2026-07-09.md §15.2–15.4
(Captain addendum 2: calibration BEFORE build). Ledger row:
WORLD-GROWTH-CALIBRATION in docs/plans/operative-egg-ledger-2026-07-07.yml.

REAL history sources (all read-only; nothing invented, nothing back-filled):
  * org_events per-day per-type counts — cabinet/cache/org-runtime.sqlite3 via
    `sqlite3 -readonly` (same fenced pattern as world-census.py; constant SQL).
  * commits_total per day — this repo's `git log` committer dates.
  * outcomes ledger flips — every historical version of
    instance/config/outcomes.yml via `git log`/`git show` (status flip dates).
  * census keyframes — shared/interfaces/world-chronicle.jsonl (fields that
    exist ONLY as keyframes step at their real measurement dates and are
    honestly UNMEASURED before the first keyframe — never interpolated).
  * snapshot-only fields (e.g. memory_embed_queue_xlen, P-TANK) have no
    durable history yet: they replay as unmeasured (baseline rung, flagged).

Determinism: replay is a pure function of (history snapshot, config). No
wallclock, no random — strip painting seeds every variation fnv1a-style via
the compositor's LCG with stable string seeds.

Usage (calibration run):
  python3.12 cabinet/scripts/world-growth-backtest.py \
      --config <candidates>/conservative.yml --config <candidates>/balanced.yml \
      --config <candidates>/eager.yml --until 2026-07-09 --out <out-dir> \
      --render-strips [--compositor-dir <dir holding world-next/ + world-unified/>]

Without --render-strips the harness is pure JSON emission (repo-runnable, no
PIL/asset dependencies). The compositor lineage landed in-repo with WORLD-V1A
T1 at cabinet/scripts/world-compose/ (the --compositor-dir default); the
sibling cabinet/scripts/world-preview.py renders single-day stills off the
same replay + painter.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

import yaml

REPO = Path(__file__).resolve().parents[2]
DB_DEFAULT = REPO / "cabinet" / "cache" / "org-runtime.sqlite3"
CHRONICLE = REPO / "shared" / "interfaces" / "world-chronicle.jsonl"
OUTCOMES_RELPATH = "instance/config/outcomes.yml"

# org_events event_type -> series field (world-census.py naming)
EVENT_FIELDS = {
    "session_started": "ev_session_started",
    "session_ended": "ev_session_ended",
    "role.defined": "ev_role_defined",
    "subagent_completed": "ev_subagent_completed",
    "work_item_completed": "ev_work_item_completed",
    "self_improvement_loop_completed": "ev_self_improvement_loop_completed",
    "graduation_transition": "ev_graduation_transition",
    "skill_promoted": "ev_skill_promoted",
    "mission_created": "ev_mission_created",
}
# census-keyframe-only fields (step at real measurement dates; None before)
KEYFRAME_FIELDS = (
    "memory_rows_total", "tier2_note_files", "tier3_files", "evolved_skills",
    "golden_evals", "captain_rules", "captain_vetoes_total",
    "cells_accumulating", "cells_graduated", "services_rows_total",
    "services_rows_disabled", "packs_dirs", "outcomes_total",
)
# no durable history at all yet (P-TANK / P1 staged) — unmeasured whole window
SNAPSHOT_ONLY_FIELDS = ("memory_embed_queue_xlen", "pending_captain_items")

JUMP_DAY_THRESHOLD = 5   # >= this many growth changes in one day = jump-day


# ── fenced readers ──────────────────────────────────────────────────────────

def _run(cmd: List[str], timeout: int = 60) -> Optional[str]:
    """List-argv subprocess, never shell. None on any failure."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None
    return proc.stdout if proc.returncode == 0 else None


def _sqlite_ro(db: Path, sql: str) -> Optional[str]:
    """Constant SQL through `sqlite3 -readonly` (world-census.py pattern)."""
    if not db.exists():
        return None
    for attempt in range(3):
        try:
            proc = subprocess.run(
                ["sqlite3", "-readonly", "-batch", str(db), sql],
                capture_output=True, text=True, timeout=30)
        except Exception:
            return None
        if proc.returncode == 0:
            return proc.stdout
        if "locked" in (proc.stderr or "") or "busy" in (proc.stderr or ""):
            import time
            time.sleep(0.5 * (attempt + 1))
            continue
        return None
    return None


def _daterange(d0: dt.date, d1: dt.date) -> List[dt.date]:
    return [d0 + dt.timedelta(days=i) for i in range((d1 - d0).days + 1)]


# ── history extraction (REAL, read-only) ────────────────────────────────────

def _lane_of(outcome: dict) -> Optional[str]:
    lane = outcome.get("lane")
    if isinstance(lane, str) and lane:
        return lane
    oid = str(outcome.get("id", ""))
    if oid.startswith("outcome-"):
        parts = oid[len("outcome-"):].rsplit("-", 1)
        if len(parts) == 2:
            return parts[0]
    return None


def _outcome_deriveds(doc: dict) -> dict:
    outs = (doc or {}).get("outcomes") or []
    by_lane: Dict[str, dict] = {}
    counts = {"active": 0, "achieved": 0, "retired": 0, "draft": 0}
    sys_self_active = 0
    for o in outs:
        if not isinstance(o, dict):
            continue
        status = str(o.get("status", ""))
        lane = _lane_of(o) or "unknown"
        rec = by_lane.setdefault(lane, {"ever": 0, "active": 0, "achieved": 0, "retired": 0})
        rec["ever"] += 1
        if status in counts:
            counts[status] += 1
        if status in rec:
            rec[status] += 1
        if lane == "system-self" and status == "active":
            sys_self_active += 1
    return {
        "outcomes_active": counts["active"],
        "outcomes_achieved": counts["achieved"],
        "outcomes_retired": counts["retired"],
        "active_lanes": sum(1 for r in by_lane.values() if r["active"] > 0),
        "outcomes_active_system_self": sys_self_active,
        "outcomes_by_lane": by_lane,
    }


def extract_history(db: Path, repo: Path, until: dt.date) -> dict:
    # 1. org_events per-day per-type
    raw = _sqlite_ro(db, "SELECT substr(created_at,1,10), event_type, COUNT(*) "
                         "FROM org_events GROUP BY 1, 2 ORDER BY 1;")
    if raw is None:
        raise SystemExit("org_events sqlite unreadable — cannot replay real history")
    day_type: Dict[str, Dict[str, int]] = {}
    for line in raw.splitlines():
        parts = line.split("|")
        if len(parts) != 3:
            continue
        d, et, n = parts[0], parts[1], parts[2]
        try:
            day_type.setdefault(d, {})[et] = int(n)
        except ValueError:
            continue
    genesis_raw = _sqlite_ro(db, "SELECT MIN(substr(created_at,1,10)) FROM org_events;")
    genesis = dt.date.fromisoformat((genesis_raw or "").strip())
    days = [d for d in _daterange(genesis, until)]
    keys = [d.isoformat() for d in days]

    series: Dict[str, List[Optional[float]]] = {}
    # cumulative event counters + total + age
    cum: Dict[str, int] = {}
    total = 0
    ev_series: Dict[str, List[Optional[float]]] = {f: [] for f in EVENT_FIELDS.values()}
    tot_series: List[Optional[float]] = []
    age_series: List[Optional[float]] = []
    for i, k in enumerate(keys):
        for et, n in (day_type.get(k) or {}).items():
            cum[et] = cum.get(et, 0) + n
            total += n
        for et, field in EVENT_FIELDS.items():
            ev_series[field].append(cum.get(et, 0))
        tot_series.append(total)
        age_series.append(i)  # days since genesis
    series.update(ev_series)
    series["org_events_total"] = tot_series
    series["org_age_days"] = age_series
    # today's OWN event count (TEXTURE class driver — resets daily, honest)
    series["events_today"] = [float(sum((day_type.get(k) or {}).values())) for k in keys]

    # 2. commits per day (committer dates over full first-parent history)
    log = _run(["git", "-C", str(repo), "log", "--format=%cs"]) or ""
    per_day: Dict[str, int] = {}
    for line in log.splitlines():
        line = line.strip()
        if line:
            per_day[line] = per_day.get(line, 0) + 1
    at_genesis = sum(n for d, n in per_day.items() if d < keys[0])
    running = at_genesis
    commits: List[Optional[float]] = []
    for k in keys:
        running += per_day.get(k, 0)
        commits.append(running)
    series["commits_total"] = commits
    # commits anchored at ORG genesis (egg-honest: fresh deployment starts 0;
    # this retrofit subtracts the pre-runtime scaffolding commits)
    series["commits_since_genesis"] = [c - at_genesis for c in commits]

    # 3. outcomes ledger flips from git history (oldest -> newest)
    hashes_raw = _run(["git", "-C", str(repo), "log", "--follow",
                       "--format=%H %cs", "--", OUTCOMES_RELPATH]) or ""
    snapshots: Dict[str, dict] = {}   # date -> deriveds (last commit that day wins;
    revs = [ln.split() for ln in hashes_raw.splitlines() if len(ln.split()) == 2]
    for sha, date_s in reversed(revs):  # oldest first; later same-day overwrites
        blob = _run(["git", "-C", str(repo), "show", f"{sha}:{OUTCOMES_RELPATH}"])
        if blob is None:
            continue
        try:
            doc = yaml.safe_load(blob)
        except Exception:
            continue
        if isinstance(doc, dict):
            snapshots[date_s] = _outcome_deriveds(doc)
    out_fields = ("outcomes_active", "outcomes_achieved", "outcomes_retired",
                  "active_lanes", "outcomes_active_system_self")
    out_series: Dict[str, List[Optional[float]]] = {f: [] for f in out_fields}
    lane_daily: List[dict] = []
    current = {f: 0 for f in out_fields}
    current_lanes: dict = {}
    for k in keys:
        snap = snapshots.get(k)
        if snap is not None:
            current = {f: snap[f] for f in out_fields}
            current_lanes = snap["outcomes_by_lane"]
        for f in out_fields:
            out_series[f].append(current[f])
        lane_daily.append(current_lanes)
    series.update(out_series)

    # 4. census keyframes (step at real dates; None before first measurement)
    keyframes: Dict[str, dict] = {}
    if CHRONICLE.exists():
        for line in CHRONICLE.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            d = rec.get("date")
            if isinstance(d, str):
                keyframes[d] = rec
    kf_dates = sorted(keyframes)
    for f in KEYFRAME_FIELDS:
        col: List[Optional[float]] = []
        cur: Optional[float] = None
        for k in keys:
            if k in keyframes and f in keyframes[k]:
                cur = keyframes[k][f]
            col.append(cur)
        series[f] = col
    kf_count: List[Optional[float]] = []
    n = 0
    for k in keys:
        if k in keyframes:
            n += 1
        kf_count.append(n)
    series["world_chronicle_keyframes"] = kf_count
    for f in SNAPSHOT_ONLY_FIELDS:
        series[f] = [None] * len(keys)

    return {
        "schema": "cabinet.world.growth-backtest-history/v1",
        "sources": {"org_events_db": str(db), "repo": str(repo),
                    "chronicle": str(CHRONICLE), "outcomes": OUTCOMES_RELPATH},
        "genesis": keys[0], "until": until.isoformat(),
        "keyframe_dates": kf_dates,
        "outcome_flip_dates": sorted(snapshots),
        "days": keys,
        "series": series,
        "outcomes_by_lane_daily": lane_daily,
        "notes": [
            "keyframe-only fields are honestly unmeasured (null) before their "
            "first real keyframe — never interpolated, never back-filled",
            "snapshot-only fields (P-TANK/P1) replay unmeasured for the whole "
            "window; their ladders sit at baseline rung 0",
        ],
    }


# ── replay ──────────────────────────────────────────────────────────────────

def _norm(v: Optional[float], curve: str, cap: float) -> float:
    if v is None or v <= 0:
        return 0.0
    if curve == "linear":
        return min(v / cap, 1.0)
    if curve == "log2":
        return min(math.log2(v + 1) / math.log2(cap + 1), 1.0)
    if curve == "log10":
        return min(math.log10(v + 1) / math.log10(cap + 1), 1.0)
    raise ValueError(f"unknown curve {curve!r}")


def _raw_rung(lad: dict, v: Optional[float]) -> Optional[int]:
    if v is None:
        return None
    nr = len(lad["rungs"])
    mode = lad["mode"]
    if mode == "tier":
        if v <= 0:
            return 0
        return max(0, min(int(math.floor(math.log2(v / float(lad["base"]) + 1))), nr - 1))
    if mode == "count":
        return max(0, min(int(v), nr - 1))
    if mode == "flag":
        return 1 if v >= float(lad.get("at", 1)) else 0
    raise ValueError(f"unsupported mode {lad['mode']!r}")


def _lane_rung(lane_rec: Optional[dict]) -> int:
    """v1 isle rings from outcomes.yml only: reef 0 / dock r0=1 / warehouses r1=2.
    (r2/r3 need P3/P5 feeds — honestly unreachable in this backtest.)"""
    if not lane_rec or lane_rec.get("ever", 0) == 0:
        return 0
    if lane_rec.get("active", 0) == 0 and lane_rec.get("retired", 0) > 0:
        return 0   # retired lane -> reef buoy (Captain ruling 2026-07-09)
    return 2 if lane_rec.get("achieved", 0) >= 1 else 1


class _Hold:
    """Hysteresis holder: a candidate rung must persist `evals` consecutive
    days before the visible rung moves (up or down)."""

    def __init__(self, evals: int):
        self.evals = max(1, int(evals))
        self.visible: Optional[int] = None
        self.cand: Optional[int] = None
        self.streak = 0

    def step(self, raw: Optional[int]) -> Optional[int]:
        if raw is None:
            return self.visible
        if self.visible is None:          # first real measurement
            self.visible = raw
            self.cand, self.streak = None, 0
            return self.visible
        if raw == self.visible:
            self.cand, self.streak = None, 0
            return self.visible
        if raw == self.cand:
            self.streak += 1
        else:
            self.cand, self.streak = raw, 1
        if self.streak >= self.evals:
            self.visible = self.cand
            self.cand, self.streak = None, 0
        return self.visible


def replay(config: dict, history: dict) -> dict:
    days: List[str] = history["days"]
    series = history["series"]
    lane_daily = history["outcomes_by_lane_daily"]
    era_cfg = config["era"]
    names = era_cfg["names"]
    thresholds = era_cfg["thresholds"]
    hold_evals = int(era_cfg["hysteresis"]["advance_hold_evals"])
    demote_margin = float(era_cfg["hysteresis"]["demote_margin"])
    ladders: Dict[str, dict] = config["ladders"]

    era_idx = 0
    adv_streak = 0
    dem_streak = 0
    holders = {name: _Hold(lad.get("hysteresis_evals", 2))
               for name, lad in ladders.items()}
    lane_holders: Dict[str, _Hold] = {}
    prev_visible: Dict[str, object] = {}
    timeline_days: List[dict] = []
    era_transitions: List[dict] = []
    prev_weighted: Optional[Dict[str, float]] = None

    for i, day in enumerate(days):
        # era basket
        norms: Dict[str, float] = {}
        weighted: Dict[str, float] = {}
        for metric, spec in era_cfg["basket"].items():
            v = series[metric][i] if metric in series else None
            nv = _norm(v, spec["curve"], float(spec["cap"]))
            norms[metric] = round(nv, 6)
            weighted[metric] = nv * float(spec["weight"])
        index = sum(weighted.values())

        # era state machine (one step per day, mandatory hysteresis)
        if era_idx + 1 < len(names) and index >= float(thresholds[names[era_idx + 1]]):
            adv_streak += 1
        else:
            adv_streak = 0
        if era_idx > 0 and index < float(thresholds[names[era_idx]]) - demote_margin:
            dem_streak += 1
        else:
            dem_streak = 0
        if adv_streak >= hold_evals:
            frm = names[era_idx]
            era_idx += 1
            adv_streak = 0
            trigger = None
            if prev_weighted:
                deltas = {m: weighted[m] - prev_weighted.get(m, 0.0) for m in weighted}
                trigger = max(deltas, key=lambda m: deltas[m])
            era_transitions.append({"date": day, "from": frm, "to": names[era_idx],
                                    "index": round(index, 4),
                                    "top_contributor": trigger})
            prev_weighted = dict(weighted)
        elif dem_streak >= hold_evals:
            frm = names[era_idx]
            era_idx -= 1
            dem_streak = 0
            era_transitions.append({"date": day, "from": frm, "to": names[era_idx],
                                    "index": round(index, 4), "demotion": True})
        if prev_weighted is None:
            prev_weighted = dict(weighted)

        # ladders
        lads_out: Dict[str, dict] = {}
        changes: List[dict] = []
        for name, lad in ladders.items():
            if lad["mode"] == "per_lane":
                lanes_rec = lane_daily[i] or {}
                vis: Dict[str, int] = {}
                for lane in sorted(k for k in lanes_rec if k != "system-self"):
                    h = lane_holders.setdefault(lane, _Hold(lad.get("hysteresis_evals", 2)))
                    vis[lane] = h.step(_lane_rung(lanes_rec.get(lane))) or 0
                prev = prev_visible.get(name)
                prev_d = prev if isinstance(prev, dict) else {}
                for lane in vis:
                    if vis[lane] != prev_d.get(lane) and (vis[lane] > 0 or lane in prev_d):
                        # a lane's first dock IS growth — the lane was born on
                        # a real ratification, not on a measurement artifact
                        changes.append({"element": f"isle:{lane}",
                                        "to": lad["rungs"][vis[lane]],
                                        "kind": "growth"})
                prev_visible[name] = vis
                lads_out[name] = {"visible_by_lane": vis, "measured": True}
                continue
            v = series[lad["metric"]][i] if lad["metric"] in series else None
            raw = _raw_rung(lad, v)
            was_measured = holders[name].visible is not None
            visible = holders[name].step(raw)
            prev = prev_visible.get(name)
            if visible is not None and prev != visible:
                kind = "growth" if was_measured and prev is not None else "first_measurement"
                changes.append({"element": name,
                                "from": lad["rungs"][prev] if isinstance(prev, int) else None,
                                "to": lad["rungs"][visible], "kind": kind})
            if visible is not None:
                prev_visible[name] = visible
            lads_out[name] = {
                "v": v, "raw": raw, "visible": visible,
                "measured": v is not None,
                "stage": lad["rungs"][visible] if visible is not None else None,
            }
        ev_today = series["events_today"][i] if "events_today" in series else 0
        texture_tier = min(3, int(math.log10(ev_today + 1))) if ev_today else 0
        timeline_days.append({
            "date": day, "index": round(index, 4), "era": names[era_idx],
            "events_today": ev_today, "texture_tier": texture_tier,
            "norms": norms, "ladders": lads_out, "changes": changes,
        })

    # weekly + fortnight + story metrics
    weeks: Dict[str, dict] = {}
    for rec in timeline_days:
        d = dt.date.fromisoformat(rec["date"])
        wk = f"{d.isocalendar().year}-W{d.isocalendar().week:02d}"
        w = weeks.setdefault(wk, {"week": wk, "days": 0, "growth_changes": 0,
                                  "measurement_changes": 0, "changed_elements": [],
                                  "texture_days": 0, "index_end": 0.0, "era_end": ""})
        w["days"] += 1
        if rec.get("events_today"):
            w["texture_days"] += 1
        for c in rec["changes"]:
            if c["kind"] == "growth":
                w["growth_changes"] += 1
            else:
                w["measurement_changes"] += 1
            w["changed_elements"].append(f"{rec['date']}:{c['element']}→{c['to']}")
        w["index_end"] = rec["index"]
        w["era_end"] = rec["era"]
    week_list = [weeks[k] for k in sorted(weeks)]
    era_dates = {t["date"] for t in era_transitions}
    dead_weeks = [w["week"] for w in week_list
                  if w["days"] >= 4 and w["growth_changes"] == 0
                  and not any(dt.date.fromisoformat(rec["date"]).isocalendar().week ==
                              int(w["week"].split("-W")[1]) for rec in timeline_days
                              if rec["date"] in era_dates)]
    jump_days = [{"date": rec["date"],
                  "n": sum(1 for c in rec["changes"] if c["kind"] == "growth"),
                  "elements": [c["element"] for c in rec["changes"] if c["kind"] == "growth"]}
                 for rec in timeline_days
                 if sum(1 for c in rec["changes"] if c["kind"] == "growth") >= JUMP_DAY_THRESHOLD]
    burst = max(timeline_days,
                key=lambda r: sum(1 for c in r["changes"] if c["kind"] == "first_measurement"),
                default=None)
    egg_exit = next((t for t in era_transitions if t["from"] == "camp"), None)
    story = {
        "weeks_total": len(week_list),
        "weeks_with_growth": sum(1 for w in week_list if w["growth_changes"] > 0),
        "dead_weeks": dead_weeks,
        "jump_days": jump_days,
        "era_transitions": era_transitions,
        "egg_exit_days": ((dt.date.fromisoformat(egg_exit["date"]) -
                           dt.date.fromisoformat(history["genesis"])).days
                          if egg_exit else None),
        "first_measurement_burst": ({"date": burst["date"],
                                     "n": sum(1 for c in burst["changes"]
                                              if c["kind"] == "first_measurement")}
                                    if burst else None),
        "final": {"date": timeline_days[-1]["date"],
                  "index": timeline_days[-1]["index"],
                  "era": timeline_days[-1]["era"]},
    }
    return {
        "schema": "cabinet.world.growth-backtest-timeline/v1",
        "candidate": config.get("candidate", "unnamed"),
        "history_genesis": history["genesis"], "history_until": history["until"],
        "story": story, "weeks": week_list, "days": timeline_days,
    }


# ── timelapse strip rendering (compositor lineage; optional) ────────────────

def render_strip(timeline: dict, out_png: Path, compositor_dir: Path,
                 frame_dates: Optional[List[str]] = None) -> None:
    sys.path.insert(0, str(compositor_dir / "world-unified"))
    sys.path.insert(0, str(compositor_dir / "world-next"))
    import compose_growth as G          # noqa: E402  (imports compose_unified as U)
    from PIL import Image, ImageDraw    # noqa: E402
    U = G.U
    T = U.T

    ERA_HUE = {"camp": (150, 118, 76), "hamlet": (196, 168, 92),
               "town": (120, 158, 116), "beyond_bay": (108, 140, 188)}
    W_, H_ = 38, 29
    SEA0 = 23

    def paint_day(rec: dict, cand: str) -> Image.Image:
        lads = rec["ladders"]
        era = rec["era"]

        def vis(name: str) -> int:
            v = lads.get(name, {}).get("visible")
            return -1 if v is None else int(v)

        def pending(name: str) -> bool:
            e = lads.get(name, {})
            return (e.get("raw") is not None and e.get("visible") is not None
                    and e["raw"] > e["visible"])

        # seed = date only — world_at(T) = f(state_at(T)) doctrine: two configs
        # whose visible state agree on a day render byte-identical frames
        # (differences come from STATE, never from the candidate's name)
        seedbase = f"growth-{rec['date']}"
        sc = U.Scene(W_, H_)
        gd = ImageDraw.Draw(sc.ground)
        G.paint_grass(sc, 0, 0, W_ - 1, SEA0 - 1, seedbase + "-grass", daub_div=4)
        G.paint_sea(sc, 0, SEA0, W_ - 1, H_ - 1, seedbase + "-sea")
        G.shoreline_foam(gd, 0, W_ - 1, SEA0, seedbase + "-shore")
        G.tide_foam(gd, 0, W_ - 1, SEA0, seedbase + "-tide", n=46)
        # clearing dressing (egg-tile-plan §gate mitigation: felled logs, mulch,
        # rock — the clearing was CUT, worked earth breaks the flat field)
        sc.gtiles(U.autotile(U.rect(11, 8, 12, 9), U.MULCH, fillp=0.5))
        sc.gtiles(U.autotile(U.rect(20, 8, 22, 9), U.MULCH, fillp=0.4))
        sc.gtiles(U.autotile(U.rect(23, 13, 24, 14), U.MULCH, fillp=0.5))
        sc.ent(U.sh(U.P("Trunk_Big_1")), 11.5, 8.2, prop="prop")
        sc.ent(U.sh(U.P("Trunk_Big_2")), 24.4, 13.6, prop="prop")
        sc.ent(U.sh(U.P("Wood_Board_Load")), 20.6, 9.4, prop="prop")
        sc.ent(U.sh(U.P("Rock_Small")), 13.2, 15.8, prop="prop")

        # road: the egg's t0 dirt path always exists (ratified egg-tile-plan);
        # rung upgrades material density, era vocab gates the cobble look
        road_r = max(vis("road"), 0)
        path = U.carve_path([(17, 10), (17, 14), (18, 18), (17, 22)], wobble=False)
        sc.gtiles(U.autotile(path, U.TAN, fillp=0.55 + 0.1 * road_r))
        if road_r >= 2 and era in ("town", "beyond_bay"):
            for (tx, ty) in sorted(path):
                if (tx + ty) % 2 == 0:
                    gd.point((tx * T + 8, ty * T + 8), fill=G.ST_LT + (200,))
        G.tan_wear(sc, path, seedbase + "-wear")

        # great house (era vocabulary + rung size)
        gh = max(vis("great_house"), 0)
        if era == "camp":
            house = U.sh(U.P("Chicken_Coop"))
        else:
            house = U.sh(U.P("Farmer_House_1"))
        px, py = sc.ent(house, 15.0, 7.4, bias=-0.2)
        sc.shadow_blob(px + house.width // 2, int(8.4 * T) - 4, house.width - 10, 26)
        if gh >= 1 and era != "camp":
            G.fence_pen(sc, 14, 9, 16, 9)                      # porch rail
        if gh >= 2 and era != "camp":
            annex = U.sh(U.P("Front_Hayloft_Yellow"))
            sc.ent(annex, 17.3, 7.0, bias=-0.1)
        if gh >= 3 and era in ("town", "beyond_bay"):
            annex2 = U.sh(U.P("Front_Hayloft_Grey"))
            sc.ent(annex2, 13.0, 7.0, bias=-0.1)
        if pending("great_house"):
            sc.ent(G.scaffold_site(40, 40), 17.6, 6.6)
        # TEXTURE class (daily pulse — legal >1/day change): smoke on active
        # days, meadow tufts/flowers by today's real event volume tier
        tex = int(rec.get("texture_tier", 0))
        if rec.get("events_today"):
            G.smoke_at(sc, px + 6, py - 6, alpha=0.5 + 0.12 * tex)
        rngt = U.LCG(seedbase + "-tufts")
        for _ in range(122 + 18 * tex):
            tx, ty = rngt.ri(9, 28), rngt.ri(5, 20)
            if (tx, ty) in path:
                continue
            sc.gpaste(U.sh(U.CS("Grass_Tufts_Flowers_16x16_%d" % rngt.ri(1, 11))),
                      tx, ty)

        # flagpole + pennant, mailbox, water bucket (baseline rung 0)
        fp = G.flagpole(bare=vis("flagpole") < 1)
        sc.ent(fp, 19.6, 7.9)
        sc.ent(U.mailbox(False), 18.8, 11.8, bias=0.1, prop="prop")
        sc.ent(U.sh(U.P("Bucket_1_Single")), 14.35, 9.6, bias=0.1, prop="prop")

        # noticeboard
        if vis("noticeboard") >= 1:
            sc.ent(U.noticeboard(), 15.6, 11.6, bias=0.1)

        # officer dwellings (count; vocab: camp tents -> hamlet huts -> town cottages)
        slots = [(22.5, 6.5), (25.0, 7.5), (22.5, 9.2), (25.0, 10.2), (27.4, 8.6)]
        nd = max(vis("officer_dwellings"), 0)
        for k in range(min(nd, len(slots))):
            tx, ty = slots[k]
            if era == "camp":
                im = U.sh(U.P("Canopy_Small"))
            elif era == "hamlet":
                im = U.sh(U.P("Chicken_Coop"))
            else:
                im = U.sh(U.P(["Front_Hayloft_Green", "Front_Hayloft_Red",
                               "Front_Hayloft_Grey", "Front_Hayloft_Yellow",
                               "Front_Hayloft_Green"][k]))
            px, py = sc.ent(im, tx, ty, bias=-0.1)
            sc.shadow_blob(px + im.width // 2, int((ty + 1.0) * T) - 4, im.width - 8, 24)
        if pending("officer_dwellings") and nd < len(slots):
            sc.ent(G.scaffold_site(36, 36), slots[min(nd, len(slots) - 1)][0],
                   slots[min(nd, len(slots) - 1)][1])

        # workshop (rack -> shed) W of house
        ws = vis("workshop")
        if ws >= 0:
            if ws >= 2:
                sc.ent(U.sh(U.P("Canopy_Tools_Big")), 11.4, 10.2, bias=-0.1)
            elif ws >= 1:
                sc.ent(U.sh(U.P("DIY_Crafting_Table")), 11.8, 10.6, prop="prop")

        # library (crate -> leanto -> hall)
        lib = vis("library")
        if lib >= 2:
            lh = U.sh(U.P("Farmer_House_2"))
            px, py = sc.ent(lh, 10.6, 6.0, bias=-0.15)
            sc.shadow_blob(px + lh.width // 2, int(7.0 * T) - 4, lh.width - 10, 24)
        elif lib >= 1:
            sc.ent(U.sh(U.P("Canopy_Big")), 10.8, 6.4, bias=-0.1)
        elif lib >= 0:
            sc.ent(U.sh(U.P("Box_Single")), 11.4, 7.0, prop="prop")

        # well + firepit (civic)
        if vis("well") >= 1:
            wx, wy = int(19.6 * T), int(13.6 * T)
            gd.ellipse([wx, wy, wx + 12, wy + 9], fill=G.ST_DK + (255,),
                       outline=G.ST_LT + (255,))
            gd.ellipse([wx + 3, wy + 2, wx + 9, wy + 6], fill=(20, 22, 32, 255))
        fp_r = vis("firepit")
        if fp_r >= 1:
            fx, fy = int(20.6 * T), int(15.6 * T)
            gd.ellipse([fx, fy, fx + 10, fy + 8], outline=G.ASH_M + (255,))
            gd.point((fx + 5, fy + 4), fill=G.ASH_L + (255,))

        # field plots (system-self outcomes)
        for k in range(max(vis("field_plots"), 0)):
            sc.ent(U.plotbed(2, 1), 8.4 + 2.3 * k, 12.8, prop="prop")

        # outbuildings (none -> coop -> barn ladder) W midland; egg has none
        ob = vis("outbuildings")
        if ob >= 2:
            barn = U.sh(U.P("Barn_Small"))
            px, py = sc.ent(barn, 6.8, 15.4, bias=-0.2)
            sc.shadow_blob(px + barn.width // 2, int(16.4 * T) - 5, barn.width - 12, 28)
        elif ob >= 1:
            sc.ent(U.sh(U.P("Chicken_Coop")), 7.6, 15.8, bias=-0.1)
        if ob >= 3:
            sc.ent(U.sh(U.P("Hay_Dry_Pile")), 9.6, 16.6, prop="prop")
        if pending("outbuildings"):
            sc.ent(G.scaffold_site(36, 36), 9.4, 15.2)

        # pens (fence) + law plot (fence posts NW)
        if vis("pens") >= 1:
            G.fence_pen(sc, 5, 18, 8 + min(vis("pens"), 2), 20)
        if vis("law_plot") >= 1:
            G.fence_pen(sc, 6, 4, 8, 5, ghost=vis("law_plot") < 2)

        # quay ladder: rowboat jetty -> timber -> stone sections
        q = max(vis("quay"), 0)
        if q <= 1:
            jt = U.rect(17, SEA0, 18 if q == 0 else 20, SEA0 + (2 if q == 0 else 1))
            G.planks(sc, gd, jt)
            G.pier_posts(gd, [(17 * T - 2, (SEA0 + 2) * T + 6), (19 * T, (SEA0 + 1) * T + 6)])
        else:
            x0 = 15 - (q - 2)
            x1 = 21 + 2 * (q - 2)
            G.quay_stone(sc, gd, max(x0, 11), min(x1, 27), SEA0, SEA0 + 1,
                         seedbase + "-quay")
        # berths chalk + cargo
        nb = max(vis("berths"), 0)
        for k in range(min(nb, 5)):
            bx = (13 + 3 * k) * T
            gd.rectangle([bx, (SEA0 + 1) * T + 2, bx + 2 * T - 4, (SEA0 + 1) * T + 10],
                         outline=G.CHALK + (170,))
        cg = vis("cargo_stacks")
        if cg >= 1 and q >= 2:
            for k in range(min(cg, 3)):
                sc.ent(U.sh(U.P("Box_Load" if k % 2 == 0 else "Box_Single")),
                       13.5 + 3.1 * k, SEA0 - 0.9, prop="prop")

        # boat: rowboat -> packet
        if vis("harbor_boat") >= 1:
            sc.ent(G.cargo_boat("down"), 19.6, SEA0 + 1.6)
        else:
            sc.ent(U.sh(U.BOAT), 19.3, SEA0 + 1.3)

        # warehouse + harbormaster hut on quay
        wh = vis("warehouse")
        if wh >= 2:
            sc.ent(U.sh(U.P("Market_Stand_Blue_Big")), 23.2, SEA0 - 1.8, bias=-0.1)
        elif wh >= 1:
            sc.ent(U.sh(U.P("Canopy_Small")), 23.4, SEA0 - 1.6, bias=-0.1)
        if vis("harbormaster_hut") >= 1:
            sc.ent(U.sh(U.P("Market_Stand_Green_Small")), 26.0, SEA0 - 1.4, bias=-0.1)

        # lighthouse ladder on the shore rock + lamp
        lh_r = max(vis("lighthouse"), 0)
        lit = vis("lighthouse_lamp") >= 1
        if lh_r == 0:
            sc.ent(G.lantern_cairn(), 26.8, 21.0, bias=-0.1)
        elif lit:
            sc.ent(G.lighthouse_lit(), 26.6, 19.6, bias=-0.1)
        else:
            sc.ent(U.build_lighthouse(body_t=2 + lh_r, H_t=3 + 2 * lh_r), 26.7,
                   21.0 - 0.8 * lh_r, bias=-0.1)
        sc.ent(U.sh(U.P("Rock_Small")), 25.5, 22.1, prop="prop")

        # lantern posts along the road (erected dark; lit only per graduation)
        np_ = max(vis("lantern_posts"), 0)
        lit_n = max(vis("posts_lit"), 0)
        for k in range(min(np_, 4)):
            sc.ent(G.lantern_post(lit=k < lit_n), 16.0, 13.0 + 2.4 * k, prop="prop")

        # product isles offshore (per-lane rings) + retired reef buoy
        vbl = lads.get("lane_isles", {}).get("visible_by_lane", {}) or {}
        anchors = {"polads": (32, SEA0 + 2), "stephie": (2, SEA0 + 2),
                   "stepnetwork": (10, SEA0 + 3)}
        for lane, (ix, iy) in anchors.items():
            r = vbl.get(lane)
            if r is None:
                continue
            if r == 0:
                if lane == "stepnetwork" and rec["date"] >= "2026-07-02":
                    sc.ent(G.grey_buoy(), ix + 1.2, iy + 0.6, prop="prop")
                continue
            G.isle_blob(sc, ix, iy, ix + 3, iy + 1, seedbase + "-isle-" + lane)
            if r >= 1:
                G.planks(sc, gd, U.rect(ix + 1, iy + 1, ix + 1, iy + 1))
            if r >= 2:
                sc.ent(U.sh(U.P("Box_Single")), ix + 0.6, iy - 0.2, prop="prop")

        # forest ring: trees thin as the village earns lots (clearing = earned set)
        built = sum(1 for nm in ("workshop", "library", "outbuildings", "well")
                    if vis(nm) >= (2 if nm in ("workshop", "library", "outbuildings") else 1))
        built += min(max(vis("officer_dwellings"), 0), 4)
        G.ring_forest(sc, [
            (-2, 39, -1, "mix", 1.7), (-1, 39, 0.8, "mix", 1.8),
            (-2, 38, 2.2, "tall", 2.0),
            (-2, 9, 3.6, "mix", 1.8), (-1, 8, 5.4, "mix", 1.9),
            (-2, 7, 7.6, "mix", 2.0), (-1, 6, 9.8, "shore", 2.0),
            (-2, 6, 12.0, "mix", 2.0), (-1, 5, 14.2, "shore", 2.1),
            (-2, 4, 16.4, "mix", 2.0), (-1, 4, 18.6, "shore", 2.2),
            (30, 39, 3.6, "mix", 1.8), (31, 39, 5.4, "mix", 1.9),
            (31, 40, 7.6, "mix", 2.0), (32, 40, 9.8, "shore", 2.0),
            (32, 40, 12.0, "mix", 2.0), (33, 40, 14.2, "shore", 2.1),
            (33, 40, 16.4, "mix", 2.0), (34, 40, 18.6, "shore", 2.2),
        ], seedbase + "-ring")
        inner = [(8, 6, "oakM"), (7, 12, "pineM"), (9, 17, "oakS"),
                 (27, 7, "oakM"), (29, 12, "oakS"), (25, 17, "pineM"),
                 (12, 4, "oakS"), (22, 4, "oakM"), (28, 17.5, "oakS")]
        rng = U.LCG(seedbase + "-thin")
        keep = inner[min(built, len(inner)):]
        for (tx, ty, kind) in keep:
            im = U.tree(kind)
            px, py = sc.ent(im, tx, ty, bias=-0.05)
            sc.shadow_blob(px + im.width // 2, int((ty + 1) * T) - 5, im.width - 16, 22)
        # mist beyond (grey-unmeasured horizon) + corner pockets (egg recipe)
        G.mist_band(gd, 0, SEA0 + 2, W_ - 1, H_ - 1, seedbase + "-mist",
                    ramp="down", dens=(1, 9))
        G.mist_pocket(gd, 3, H_ - 2, 4, seedbase + "-mp1")
        G.mist_pocket(gd, 34, H_ - 3, 4, seedbase + "-mp2")
        _ = rng
        return sc.compose()

    days = timeline["days"]
    thumb_w, thumb_h = W_ * T // 2, H_ * T // 2      # 304 x 232 (integer NN /2)
    gut = 14
    per_row = 14
    rows = (len(days) + per_row - 1) // per_row
    header = 46
    label_w = 64
    strip = Image.new("RGB", (label_w + per_row * (thumb_w + 4) + 4,
                              header + rows * (thumb_h + gut + 6) + 6), (24, 26, 32))
    sd = ImageDraw.Draw(strip)
    cand = timeline["candidate"]
    sd.text((8, 6), f"growth backtest — {cand}   {timeline['history_genesis']} → "
                    f"{timeline['history_until']}   final: {timeline['story']['final']['era']} "
                    f"@ {timeline['story']['final']['index']:.3f}", fill=(230, 228, 220))
    # index sparkline across the header
    sx0, sy0, sw, shh = 8, 22, strip.width - 16, 18
    sd.rectangle([sx0, sy0, sx0 + sw, sy0 + shh], outline=(70, 74, 86))
    pts = []
    for i, rec in enumerate(days):
        x = sx0 + int(i * (sw - 2) / max(len(days) - 1, 1)) + 1
        y = sy0 + shh - 1 - int(rec["index"] * (shh - 2))
        pts.append((x, y))
        if rec["date"] in {t["date"] for t in timeline["story"]["era_transitions"]}:
            sd.line([x, sy0, x, sy0 + shh], fill=(250, 208, 120))
    if len(pts) > 1:
        sd.line(pts, fill=(120, 158, 116))
    for r, rec in enumerate(days):
        row, col = divmod(r, per_row)
        x = label_w + 4 + col * (thumb_w + 4)
        y = header + row * (thumb_h + gut + 6)
        if col == 0:
            sd.text((6, y + thumb_h // 2 - 5), "wk of\n" + rec["date"][5:],
                    fill=(180, 178, 170))
        frame = paint_day(rec, cand)
        if frame_dates and rec["date"] in frame_dates:
            # chrome-free world frame at up x2 — the aesthetic-gate unit, same
            # scale the ratified compose lineage gates at ("the gate judges
            # the world, not the chrome"; strip gutter = analysis chrome)
            native = out_png.parent / f"frame-{cand}-{rec['date']}.png"
            U.up(frame, 2).convert("RGB").save(native)
        frame = frame.resize((thumb_w, thumb_h), Image.NEAREST)
        strip.paste(frame, (x, y))
        n_growth = sum(1 for c in rec["changes"] if c["kind"] == "growth")
        n_meas = sum(1 for c in rec["changes"] if c["kind"] == "first_measurement")
        chip = ERA_HUE.get(rec["era"], (128, 128, 128))
        sd.rectangle([x, y + thumb_h + 2, x + 8, y + thumb_h + 10], fill=chip)
        label = f"{rec['date'][5:]} {rec['era'][:1].upper()}"
        if n_growth:
            label += f" +{n_growth}"
        if n_meas:
            label += f" m{n_meas}"
        sd.text((x + 12, y + thumb_h + 2), label, fill=(214, 212, 204))
    strip.save(out_png)
    print(f"strip: {out_png} ({strip.width}x{strip.height}, {len(days)} frames)")


# ── main ────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Backtest growth-ladders candidates over real org history")
    ap.add_argument("--config", action="append", required=True,
                    help="candidate growth-ladders yml (repeatable)")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--until", default=None, help="inclusive end date YYYY-MM-DD "
                    "(default: last date present in org_events)")
    ap.add_argument("--db", default=str(DB_DEFAULT))
    ap.add_argument("--repo", default=str(REPO))
    ap.add_argument("--history", default=None,
                    help="reuse a previously extracted history.json")
    ap.add_argument("--render-strips", action="store_true")
    ap.add_argument("--compositor-dir",
                    default=str(Path(__file__).resolve().parent / "world-compose"),
                    help="dir containing world-next/ + world-unified/ compositor "
                         "modules (default: the in-repo world-compose lineage)")
    ap.add_argument("--frame-dates", default=None,
                    help="comma list of YYYY-MM-DD dates to also emit as native "
                         "chrome-free frames (aesthetic-gate units)")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    if args.history:
        history = json.loads(Path(args.history).read_text())
    else:
        db = Path(args.db)
        repo = Path(args.repo)
        if args.until:
            until = dt.date.fromisoformat(args.until)
        else:
            raw = _sqlite_ro(db, "SELECT MAX(substr(created_at,1,10)) FROM org_events;")
            until = dt.date.fromisoformat((raw or "").strip())
        history = extract_history(db, repo, until)
        hpath = out / "history.json"
        hpath.write_text(json.dumps(history, indent=1, sort_keys=True))
        print(f"history: {hpath} ({len(history['days'])} days, "
              f"{len(history['series'])} series, genesis {history['genesis']})")

    # validate every candidate through the sibling validator first
    validator = Path(__file__).resolve().parent / "world-growth-validate.py"
    check = subprocess.run([sys.executable, str(validator), "--quiet", *args.config])
    if check.returncode != 0:
        raise SystemExit("candidate config(s) refused by world-growth-validate.py")

    for cfg_path in args.config:
        config = yaml.safe_load(Path(cfg_path).read_text())
        name = config.get("candidate") or Path(cfg_path).stem
        timeline = replay(config, history)
        tpath = out / f"timeline-{name}.json"
        tpath.write_text(json.dumps(timeline, indent=1, sort_keys=True))
        s = timeline["story"]
        print(f"[{name}] final {s['final']['era']} @ {s['final']['index']:.3f} | "
              f"weeks w/ growth {s['weeks_with_growth']}/{s['weeks_total']} | "
              f"dead weeks {len(s['dead_weeks'])} | jump days {len(s['jump_days'])} | "
              f"egg exit day {s['egg_exit_days']} | "
              f"transitions {[(t['date'], t['to']) for t in s['era_transitions']]}")
        if args.render_strips:
            if not args.compositor_dir:
                raise SystemExit("--render-strips needs --compositor-dir")
            render_strip(timeline, out / f"timelapse-{name}.png",
                         Path(args.compositor_dir),
                         frame_dates=(args.frame_dates.split(",")
                                      if args.frame_dates else None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
