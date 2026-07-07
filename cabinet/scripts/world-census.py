#!/usr/bin/env python3.12
"""world-census.py — daily Cabinet World census keyframe (E0a, READ-ONLY).

Cabinet World build kickoff (docs/plans/cabinet-world-build-kickoff-2026-07-07.md
step 1; spec ~/cabinet-world-growth-design-2026-07-07.md §2 Stage 1): one
~45-int census line per day appended to shared/interfaces/world-chronicle.jsonl
— the keyframe series the world's growth morphology `world_at(T) = f_v(state_at(T))`
replays from. Every un-censused day is PERMANENT replay fog for the
file-count surfaces (evolved skills, tier2 notes, packs …), which have no
ledger to reconstruct from — that is why this writer exists and why it gets
its own services.yml row + windmill + doctor probe.

DISCIPLINE (falsifier-series discipline, inherited verbatim):
  * append-only, flock'd (fcntl LOCK_EX around the single write()),
  * idempotent per date (a re-fired launchd job never doubles a day),
  * PII-free BY SCHEMA: every value must be an int, None (honest
    unmeasured — an absent source is never faked as 0), or an enum string
    from a closed set. The validator REFUSES to append anything else —
    free text structurally cannot enter the chronicle.

CENSUS READS ARE FENCED LOCAL READS ONLY (kickoff step 1, binding):
  * `sqlite3 -readonly` subprocess over cabinet/cache/org-runtime.sqlite3
    with CONSTANT SQL (no user input ever reaches the SQL string; busy-retry;
    never the projection tables — missions/work_graph/ovi_weeks are 0 rows
    despite events, enforced as a schema rule in the growth doc),
  * line counts of the JSONL ledgers (consequence-events-*.jsonl,
    undo-journal-*.jsonl, canary-receipts.jsonl, falsifier-series.jsonl),
  * `git rev-list --count HEAD` (fixed argv),
  * file counts (ls-class reads) over the accretive dirs,
  * memory rows via the falsifier memory_ingestion block (LAST line of
    falsifier-series.jsonl) — deliberately NO DB creds in the census path.
  * NO Redis, NO network: live keys are Stage-5 overlay (E0b's job, never
    morphology).

Run:       python3.12 cabinet/scripts/world-census.py
Scheduled: cabinet/services.yml row `world-census` (daily 08:15, after the
           08:05 falsifier line so memory_ingestion is fresh for the day).
Watched:   manifest-derived log-freshness floor (outcome-watchdog) + the
           cabinet-doctor world-chronicle staleness probe (>2 days = DEAD —
           replay fog accruing).
Sunset:    see the services.yml row's `sunset:` field (apoptosis R10-class
           kill criteria).
"""
from __future__ import annotations

import datetime as dt
import fcntl
import glob
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

SCHEMA_VERSION = 1

_REPO_ROOT = Path(os.environ.get("CABINET_ROOT")
                  or Path(__file__).resolve().parents[2])

# Output series (env-overridable for tests only; production is the shared
# interface next to falsifier-series.jsonl).
SERIES_PATH = Path(os.environ.get("CABINET_WORLD_SERIES")
                   or _REPO_ROOT / "shared" / "interfaces" / "world-chronicle.jsonl")

SQLITE_DB = Path(os.environ.get("CABINET_ORG_RUNTIME_DB")
                 or _REPO_ROOT / "cabinet" / "cache" / "org-runtime.sqlite3")

# Ledger dirs — same env seams the framework uses (repo conftest.py redirects
# these away from the live audit ledger under pytest).
EVENT_LOG_DIR = Path(os.environ.get(
    "CABINET_EVENT_LOG_DIR",
    os.path.expanduser("~/Library/Application Support/cabinet/events")))
UNDO_DIR = Path(os.environ.get(
    "CABINET_UNDO_DIR",
    os.path.expanduser("~/Library/Application Support/cabinet/undo")))

# ── Closed sets (the PII fence) ──────────────────────────────────────────────
POSTURES = ("earn_up", "guardian", "sovereign")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ENUM_KEYS = {"org_posture": POSTURES}

# Censused org_events event_types (constant tuple — the SQL is built ONLY from
# these literals). Honest zeros are the point: a type with no rows yet still
# gets a key (dark lighthouse discipline).
EVENT_TYPES = (
    "policy.shadow_decision", "session_started", "session_ended",
    "work_item_completed", "subagent_completed", "notification_received",
    "claude_task.created", "claude_task.completed",
    "fidelity_case_evaluated", "fidelity_case_scored",
    "graduation_transition", "work_item_unroutable", "mission_created",
    "work_item_assigned", "self_improvement_loop_started",
    "self_improvement_loop_completed", "skill_promoted", "role.defined",
    "digest_published", "kind_unfrozen", "world.grammar_gap",
)
# Constant prefix families (LIKE patterns are literals, never interpolated
# from input).
PREFIX_FAMILIES = {
    "ev_capability_gap_family": "capability_gap%",
    "ev_captain_family": "captain%",
    "ev_mail_family": "mail.%",          # PO emitters — honest 0 until PO-1
    "ev_role_family": "role_%",          # role_created/retired — E1.5 emitters
}

GOLDEN_EVAL_SEED = 25   # genome case ships 25 evals; delta = grown-here


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _key_for(event_type: str) -> str:
    return "ev_" + re.sub(r"[^a-z0-9]+", "_", event_type.lower()).strip("_")


# ── fenced readers (each injectable for tests; each degrades to None) ───────

def _sqlite3_readonly(sql: str, timeout: int = 20) -> Optional[str]:
    """Run ONE constant SQL string through `sqlite3 -readonly` with busy-retry.
    Returns stdout or None (unmeasurable — never a crash, never a write)."""
    if not SQLITE_DB.exists():
        return None
    for attempt in range(3):
        try:
            proc = subprocess.run(
                ["sqlite3", "-readonly", "-batch", str(SQLITE_DB), sql],
                capture_output=True, text=True, timeout=timeout)
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


def read_org_events() -> Dict[str, Optional[int]]:
    """Grouped org_events census — one constant GROUP BY + totals + today +
    constant prefix families. All keys present; None when the DB is
    unreachable (honest fog, never fake zero)."""
    out: Dict[str, Optional[int]] = {"org_events_total": None,
                                     "actors_distinct": None,
                                     "events_today": None}
    for et in EVENT_TYPES:
        out[_key_for(et)] = None
    for key in PREFIX_FAMILIES:
        out[key] = None

    grouped = _sqlite3_readonly(
        "SELECT event_type, COUNT(*) FROM org_events GROUP BY event_type;")
    if grouped is None:
        return out
    counts: Dict[str, int] = {}
    for line in grouped.splitlines():
        parts = line.rsplit("|", 1)
        if len(parts) != 2:
            continue
        try:
            counts[parts[0]] = int(parts[1])
        except ValueError:
            continue
    for et in EVENT_TYPES:
        out[_key_for(et)] = counts.get(et, 0)
    out["org_events_total"] = sum(counts.values())
    for key, pattern in PREFIX_FAMILIES.items():
        out[key] = sum(n for et, n in counts.items()
                       if _like_match(et, pattern))

    totals = _sqlite3_readonly("SELECT COUNT(DISTINCT actor) FROM org_events;")
    if totals is not None:
        try:
            out["actors_distinct"] = int(totals.strip() or 0)
        except ValueError:
            pass
    today = _now().strftime("%Y-%m-%d")
    if _DATE_RE.match(today):   # constant-shaped literal, generated not input
        td = _sqlite3_readonly(
            f"SELECT COUNT(*) FROM org_events WHERE created_at >= '{today}T00:00:00';")
        if td is not None:
            try:
                out["events_today"] = int(td.strip() or 0)
            except ValueError:
                pass
    return out


def _like_match(s: str, pattern: str) -> bool:
    """SQL-LIKE prefix families only (trailing %%). Constant patterns."""
    return s.startswith(pattern[:-1]) if pattern.endswith("%") else s == pattern


def _count_lines(paths: list) -> Optional[int]:
    """Total line count over files; None when NO file exists (absent source),
    0 when files exist but are empty."""
    found = False
    total = 0
    for p in paths:
        try:
            with open(p, "rb") as f:
                found = True
                total += sum(1 for _ in f)
        except OSError:
            continue
    return total if found else None


def read_ledger_counts() -> Dict[str, Optional[int]]:
    return {
        "consequence_ledger_lines": _count_lines(
            sorted(glob.glob(str(EVENT_LOG_DIR / "consequence-events-*.jsonl")))),
        "undo_journal_lines": _count_lines(
            sorted(glob.glob(str(UNDO_DIR / "undo-journal-*.jsonl")))),
        "canary_receipt_lines": _count_lines([UNDO_DIR / "canary-receipts.jsonl"]),
        "falsifier_series_lines": _count_lines(
            [_REPO_ROOT / "shared" / "interfaces" / "falsifier-series.jsonl"]),
    }


def read_falsifier_block() -> Dict[str, Optional[int]]:
    """Ints lifted from the LAST falsifier-series line (already PII-free by
    that writer's contract). Memory rows come from its memory_ingestion block
    — the census path holds no DB creds, ever."""
    keys = ("cells_accumulating", "cells_graduated", "stamped_rows_total",
            "acted_7d", "approved_7d", "proactive_cards_7d")
    out: Dict[str, Optional[int]] = {k: None for k in keys}
    out["memory_rows_total"] = None
    out["memory_source_types"] = None
    path = _REPO_ROOT / "shared" / "interfaces" / "falsifier-series.jsonl"
    last: Optional[Dict[str, Any]] = None
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    last = row
    except OSError:
        return out
    if not last:
        return out
    for k in keys:
        v = last.get(k)
        if isinstance(v, int):
            out[k] = v
    ing = last.get("memory_ingestion")
    if isinstance(ing, dict):
        ns = [v.get("n") for v in ing.values()
              if isinstance(v, dict) and isinstance(v.get("n"), int)]
        out["memory_rows_total"] = sum(ns) if ns else 0
        out["memory_source_types"] = len(ing)
    return out


def read_git_commits() -> Optional[int]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "rev-list", "--count", "HEAD"],
            capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    try:
        return int(proc.stdout.strip())
    except ValueError:
        return None


def _count_files(pattern: str) -> Optional[int]:
    """Count files matching a repo-relative glob; None when the parent dir
    itself is absent (source doesn't exist ≠ source is empty)."""
    base = _REPO_ROOT / Path(pattern).parts[0]
    if not base.exists():
        return None
    return len([p for p in glob.glob(str(_REPO_ROOT / pattern))
                if os.path.isfile(p)])


def _count_id_rows(rel_path: str) -> Optional[int]:
    """Count '- id:' rows in a YAML registry (constant regex, no parse)."""
    path = _REPO_ROOT / rel_path
    try:
        text = path.read_text()
    except OSError:
        return None
    return len(re.findall(r"^\s*-\s+id:", text, re.M))


def read_file_censuses() -> Dict[str, Optional[int]]:
    evolved = _count_files("memory/skills/evolved/*.md")
    golden = _count_files("memory/golden-evals/eval-*.md")
    tier3 = None
    t3_base = _REPO_ROOT / "memory" / "tier3"
    if t3_base.exists():
        tier3 = sum(len(fs) for _, _, fs in os.walk(t3_base))
    tier2 = None
    t2_base = _REPO_ROOT / "instance" / "memory" / "tier2"
    if t2_base.exists():
        tier2 = sum(len([f for f in fs if f.endswith(".md")])
                    for _, _, fs in os.walk(t2_base))
    remember = None
    rem_base = _REPO_ROOT / ".remember"
    if rem_base.exists():
        remember = sum(len(fs) for _, _, fs in os.walk(rem_base))
    packs = None
    packs_base = _REPO_ROOT / "packs"
    if packs_base.exists():
        packs = len([d for d in packs_base.iterdir() if d.is_dir()])
    return {
        "evolved_skills": evolved,
        "golden_evals": golden,
        "golden_evals_delta_vs_seed": (golden - GOLDEN_EVAL_SEED
                                       if golden is not None else None),
        "tier2_note_files": tier2,
        "tier3_files": tier3,
        "remember_files": remember,
        "packs_dirs": packs,
        "captain_rules": _count_id_rows("shared/interfaces/captain-rules-index.yaml"),
        "captain_vetoes_total": _count_id_rows("shared/interfaces/captain-vetoes.yml"),
        "outcomes_total": _count_id_rows("instance/config/outcomes.yml"),
    }


def read_manifest_counts() -> Dict[str, Optional[int]]:
    path = _REPO_ROOT / "cabinet" / "services.yml"
    try:
        text = path.read_text()
    except OSError:
        return {"services_rows_total": None, "services_rows_disabled": None}
    return {
        "services_rows_total": len(re.findall(r"^  - name:", text, re.M)),
        "services_rows_disabled": len(re.findall(r"^\s+disabled:\s*true", text, re.M)),
    }


def read_org_posture() -> str:
    """FAIL-CLOSED posture census: absent/corrupt/unknown resolves guardian
    (axes-contract §3 — every ambiguity narrows). This is a render-only
    census enum; the authority resolver stays framework/authority/posture.py."""
    path = _REPO_ROOT / "instance" / "config" / "posture.yml"
    try:
        text = path.read_text()
    except OSError:
        return "guardian"
    m = re.search(r"^\s*(?:autonomy_level|posture)\s*:\s*([a-z_]+)\s*$",
                  text, re.M)
    if m and m.group(1) in POSTURES:
        return m.group(1)
    return "guardian"


def read_chronicle_prior() -> int:
    n = _count_lines([SERIES_PATH])
    return n if n is not None else 0


# ── the pure keyframe ────────────────────────────────────────────────────────

def compute_census(*,
                   now: Optional[dt.datetime] = None,
                   org_events: Optional[Dict[str, Optional[int]]] = None,
                   ledgers: Optional[Dict[str, Optional[int]]] = None,
                   falsifier: Optional[Dict[str, Optional[int]]] = None,
                   commits: Optional[int] = None,
                   files: Optional[Dict[str, Optional[int]]] = None,
                   manifest: Optional[Dict[str, Optional[int]]] = None,
                   posture: Optional[str] = None,
                   chronicle_prior: Optional[int] = None) -> Dict[str, Any]:
    """Assemble one keyframe. Every argument injectable so tests run fully
    fixtured; production passes live reads."""
    now = now or _now()
    line: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "date": now.strftime("%Y-%m-%d"),
    }
    line.update(org_events if org_events is not None else read_org_events())
    line.update(ledgers if ledgers is not None else read_ledger_counts())
    line.update(falsifier if falsifier is not None else read_falsifier_block())
    line["commits_total"] = (commits if commits is not None
                             else read_git_commits())
    line.update(files if files is not None else read_file_censuses())
    line.update(manifest if manifest is not None else read_manifest_counts())
    line["org_posture"] = posture if posture is not None else read_org_posture()
    line["world_chronicle_lines_prior"] = (
        chronicle_prior if chronicle_prior is not None
        else read_chronicle_prior())
    return line


class CensusSchemaError(ValueError):
    """A value violated the PII-free closed schema — the line is REFUSED."""


def validate_census(line: Dict[str, Any]) -> None:
    """Enforce the closed schema: int | None | enum-from-closed-set only.
    bool is rejected too (it is an int subclass — keep the series honest).
    Raises CensusSchemaError; the writer never appends an invalid line."""
    for key, value in line.items():
        if not re.fullmatch(r"[a-z0-9_]+", key):
            raise CensusSchemaError(f"non-conforming key {key!r}")
        if key == "date":
            if not (isinstance(value, str) and _DATE_RE.match(value)):
                raise CensusSchemaError(f"bad date {value!r}")
            continue
        if key in _ENUM_KEYS:
            if value not in _ENUM_KEYS[key]:
                raise CensusSchemaError(
                    f"{key}={value!r} not in closed set {_ENUM_KEYS[key]}")
            continue
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            raise CensusSchemaError(
                f"{key}={value!r} is not int/None/closed-enum — free values "
                f"cannot enter the world chronicle")


def _already_reported(path: Path, date: str) -> bool:
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    if json.loads(line).get("date") == date:
                        return True
                except json.JSONDecodeError:
                    continue
    except OSError:
        return False
    return False


def append_keyframe(line: Dict[str, Any], path: Path = None) -> bool:
    """Validate + flock + append. Returns False on idempotent no-op."""
    path = path or SERIES_PATH
    validate_census(line)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            # Re-check under the lock (two same-day runs racing).
            if _already_reported(path, line["date"]):
                return False
            f.write(json.dumps(line, sort_keys=True) + "\n")
            f.flush()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    return True


def main() -> int:
    now = _now()
    iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    date = now.strftime("%Y-%m-%d")
    if _already_reported(SERIES_PATH, date):
        print(f"[{iso}] world-census: {date} already censused — no-op")
        return 0
    line = compute_census(now=now)
    try:
        appended = append_keyframe(line)
    except CensusSchemaError as e:
        print(f"[{iso}] world-census: REFUSED — {e}", file=sys.stderr)
        return 1
    if appended:
        fogged = [k for k, v in line.items() if v is None]
        print(f"[{iso}] world-census: {json.dumps(line, sort_keys=True)}")
        if fogged:
            print(f"[{iso}] world-census: unmeasured (honest fog): "
                  f"{','.join(sorted(fogged))}")
    else:
        print(f"[{iso}] world-census: {date} already censused — no-op")
    return 0


if __name__ == "__main__":
    sys.exit(main())
