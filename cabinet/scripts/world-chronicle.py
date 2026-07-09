#!/usr/bin/env python3.12
"""world-chronicle.py — the Cabinet World chronicle daemon (E0b, OBSERVER-CLASS).

Cabinet World kickoff step 2 (docs/plans/cabinet-world-build-kickoff-2026-07-07.md;
chassis ~/cabinet-world-design-2026-07-06.md E0): the org's unified event spine
for the world renderer. Merges

  * SQLite org_events — rowid cursor, READ-ONLY handle (mode=ro URI),
    busy-retry (journal_mode=delete on the live DB),
  * Redis presence/heartbeat/killswitch — plain GET/SCAN reads ONLY.
    NEVER consumer groups, never XREADGROUP: the chronicler is structurally
    unable to steal officer mail,
  * consequence/undo JSONL ledgers + memory/logs tool-call log — byte-offset
    tails with dated-file (midnight) rollover,

normalizes every row to a VERB-shaped chronicle record with MONOTONIC ingest
ids, and publishes three ways:

  1. append shared/interfaces/world/chronicle-YYYY-MM-DD.jsonl
     (flock'd, append-only; partitioned by SOURCE event date so identical
     inputs produce identical files — determinism is the render gate),
  2. XADD cabinet:world:chronicle (MAXLEN ~ 20000) + PUBLISH
     cabinet:world:updated poke (one per batch),
  3. SET cabinet:world:presence (EX 60) — the instant-client-join snapshot —
     and SET cabinet:world:chronicle:heartbeat (EX 900) every tick, the
     dead-man key the doctor/watchdog floor.

SECRET/PII SCRUB AT INGEST (binding — org_events payloads and tool logs carry
free text; the chronicle is a forever-file):
  * strict field ALLOWLIST per source — only identifier-shaped enum/id fields
    are lifted (event_type, actor, aggregate_type, action_type, risk_class,
    posture, verdict, decision, lane, tool, undo_index...). Payload free text
    (titles, subjects, objects, tool inputs/outputs, names) is NEVER copied.
  * every lifted value must pass the identifier guard (charset + length + no
    '@' + no credential-shaped substring) or the FIELD is dropped, fail-closed.
  * chronicle records carry NO wall-clock ingest time — content is a pure
    function of source rows (+ the persisted cursor), so re-chronicling the
    same rows yields byte-identical records (E0 determinism gate).

WRITE FENCE (observer-class doctrine, kickoff standing constraint): this
daemon's only writes are the cabinet:world:* Redis namespace and its own
output/state dirs (shared/interfaces/world/, ~/Library/Application
Support/cabinet/world/). It writes to no officer stream, no org ledger, no
org_events. Renderer-never-writes starts here.

KILLSWITCH: an ACTIVE killswitch halts ACTING; the chronicler is a pure
read-model and the killswitch moment is exactly what must stay observable
(honesty-floor: killswitch breaks through in every render). The daemon keeps
chronicling and flags killswitch=true in the presence snapshot; it takes no
acting path in any state.

CURSOR START: first run initializes the org_events cursor at the CURRENT
max(rowid) — the chronicle is the going-forward spine; deep history replays
from org_events + the E0a keyframes when E2 lands. CABINET_WORLD_BACKFILL=1
starts from 0 instead (deliberate, logged).

Run:       python3.12 cabinet/scripts/world-chronicle.py          (loop)
           python3.12 cabinet/scripts/world-chronicle.py --once   (one tick)
Scheduled: cabinet/services.yml row `world-chronicle` (keepalive daemon).
Tests:     cabinet/scripts/tests/test_world_chronicle.py.
Sunset:    see the services.yml row's `sunset:` field.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import glob
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

SCHEMA_VERSION = 1

_REPO_ROOT = Path(os.environ.get("CABINET_ROOT")
                  or Path(__file__).resolve().parents[2])

SQLITE_DB = Path(os.environ.get("CABINET_ORG_RUNTIME_DB")
                 or _REPO_ROOT / "cabinet" / "cache" / "org-runtime.sqlite3")
EVENT_LOG_DIR = Path(os.environ.get(
    "CABINET_EVENT_LOG_DIR",
    os.path.expanduser("~/Library/Application Support/cabinet/events")))
UNDO_DIR = Path(os.environ.get(
    "CABINET_UNDO_DIR",
    os.path.expanduser("~/Library/Application Support/cabinet/undo")))
TOOL_LOG_DIR = Path(os.environ.get("CABINET_TOOL_LOG_DIR")
                    or _REPO_ROOT / "memory" / "logs")
OUT_DIR = Path(os.environ.get("CABINET_WORLD_OUT_DIR")
               or _REPO_ROOT / "shared" / "interfaces" / "world")
STATE_DIR = Path(os.environ.get(
    "CABINET_WORLD_STATE_DIR",
    os.path.expanduser("~/Library/Application Support/cabinet/world")))
STATE_PATH = STATE_DIR / "chronicle-state.json"

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = os.environ.get("REDIS_PORT", "6379")
STREAM_KEY = "cabinet:world:chronicle"
STREAM_MAXLEN = int(os.environ.get("CABINET_WORLD_STREAM_MAXLEN", "20000"))
PUBSUB_CHANNEL = "cabinet:world:updated"
PRESENCE_KEY = "cabinet:world:presence"
HEARTBEAT_KEY = "cabinet:world:chronicle:heartbeat"
TICK_SECONDS = float(os.environ.get("CABINET_WORLD_TICK_S", "2.0"))
BATCH_LIMIT = 500

# ── the PII fence ────────────────────────────────────────────────────────────
# Identifier guard: closed charset, bounded length, no e-mail shape, no
# credential-shaped substring. A value failing the guard means the FIELD is
# dropped (fail-closed) — never truncated-through, never passed raw.
_IDENT_RE = re.compile(r"^[A-Za-z0-9_.:\/\\|-]{1,80}$")
_SECRET_RE = re.compile(
    r"(AKIA[0-9A-Z]{8,}|ghp_[A-Za-z0-9]{8,}|gho_[A-Za-z0-9]{8,}|"
    r"xox[baprs]-|sk-[A-Za-z0-9_-]{8,}|eyJ[A-Za-z0-9_-]{10,}|"
    r"-----BEGIN|(?i:bearer\s)|(?i:password)|(?i:secret))")
_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T[0-9:.]{8,15}Z?$")

# Per-source attr allowlists — the ONLY payload fields that may be lifted
# into the chronicle, and only when identifier-clean.
ORG_EVENT_ATTRS = ("action_type", "risk_class", "posture", "verdict",
                   "lane", "outcome", "state", "transition")
CONSEQUENCE_ATTRS = ("action_type", "lane", "kind")
UNDO_ATTRS = ("action_type", "kind")

# event_type → verb map (closed; unmapped types fall back to family verbs —
# nothing is ever invisible, the grammar-gap loop names them later).
VERB_MAP = {
    "policy.shadow_decision": "policy.shadowed",
    "session_started": "session.started",
    "session_ended": "session.ended",
    "work_item_completed": "work.completed",
    "work_item_assigned": "work.assigned",
    "work_item_unroutable": "work.unroutable",
    "subagent_completed": "crew.completed",
    "notification_received": "comms.notified",
    "claude_task.created": "task.created",
    "claude_task.completed": "task.completed",
    "fidelity_case_evaluated": "fidelity.evaluated",
    "fidelity_case_scored": "fidelity.scored",
    "graduation_transition": "trust.transition",
    "mission_created": "mission.created",
    "skill_promoted": "skill.promoted",
    "role.defined": "role.defined",
    "digest_published": "comms.digest",
    "kind_unfrozen": "trust.unfrozen",
    "self_improvement_loop_started": "loop.started",
    "self_improvement_loop_completed": "loop.completed",
    "world.grammar_gap": "world.grammar_gap",
}


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ident_ok(value: Any) -> bool:
    """True when a value is safe to lift into the forever-chronicle."""
    if not isinstance(value, str):
        return False
    if "@" in value:
        return False
    if not _IDENT_RE.match(value):
        return False
    if _SECRET_RE.search(value):
        return False
    return True


def clean_attrs(payload: Dict[str, Any], allowlist: Tuple[str, ...]) -> Dict[str, str]:
    """Lift ONLY allowlisted, identifier-clean fields. Everything else —
    including every free-text field — is structurally dropped."""
    out: Dict[str, str] = {}
    if not isinstance(payload, dict):
        return out
    for key in allowlist:
        v = payload.get(key)
        if isinstance(v, bool):
            continue
        if isinstance(v, int) and not isinstance(v, bool):
            out[key] = str(v)
            continue
        if ident_ok(v):
            out[key] = v
    return out


def _clean_ts(value: Any) -> Optional[str]:
    if isinstance(value, str) and _TS_RE.match(value):
        return value
    return None


def verb_for(event_type: str) -> str:
    if event_type in VERB_MAP:
        return VERB_MAP[event_type]
    # Family fallbacks keep unknown kinds visible without inventing grammar.
    if event_type.startswith("mail."):
        return "mail.family"
    if event_type.startswith("captain"):
        return "captain.family"
    if event_type.startswith("capability_gap"):
        return "gap.family"
    if event_type.startswith("role"):
        return "role.family"
    return "org.other"


# ── normalizers (pure functions — the determinism gate rides on this) ───────

def normalize_org_event(row: Tuple) -> Optional[Dict[str, Any]]:
    """(rowid, event_id, event_type, aggregate_type, actor, source,
    payload_json, created_at) → chronicle record (no iid yet)."""
    (_rowid, event_id, event_type, aggregate_type, actor, source,
     payload_json, created_at) = row
    if not (ident_ok(event_type) and ident_ok(str(actor or "unknown"))):
        return None
    payload: Dict[str, Any] = {}
    try:
        parsed = json.loads(payload_json or "{}")
        if isinstance(parsed, dict):
            payload = parsed
    except (json.JSONDecodeError, TypeError):
        payload = {}
    rec: Dict[str, Any] = {
        "v": SCHEMA_VERSION,
        "src": "org_events",
        "verb": verb_for(event_type),
        "kind": event_type,
        "actor": actor if ident_ok(actor) else "unknown",
        "ts": _clean_ts(created_at),
        "ref": event_id if ident_ok(event_id) else None,
    }
    if ident_ok(aggregate_type):
        rec["agg"] = aggregate_type
    if ident_ok(source):
        rec["esrc"] = source
    attrs = clean_attrs(payload, ORG_EVENT_ATTRS)
    if attrs:
        rec["attrs"] = attrs
    return rec


def normalize_consequence(line: str, ref: str) -> Optional[Dict[str, Any]]:
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(row, dict):
        return None
    actor = row.get("actor") or row.get("officer") or "unknown"
    decision = (row.get("proposal") or {}).get("decision") \
        if isinstance(row.get("proposal"), dict) else None
    verdict = (row.get("review") or {}).get("verdict") \
        if isinstance(row.get("review"), dict) else None
    rec: Dict[str, Any] = {
        "v": SCHEMA_VERSION,
        "src": "consequence",
        "verb": "consequence.acted" if (row.get("proposal") or {}).get("required") is False
                else "consequence.proposed",
        "kind": row.get("action") if ident_ok(row.get("action")) else "consequence",
        "actor": actor if ident_ok(actor) else "unknown",
        "ts": _clean_ts(row.get("ts")),
        "ref": ref,
    }
    attrs = clean_attrs(row, CONSEQUENCE_ATTRS)
    if ident_ok(decision):
        attrs["decision"] = decision
    if ident_ok(verdict):
        attrs["verdict"] = verdict
    if attrs:
        rec["attrs"] = attrs
    return rec


def normalize_undo(line: str, ref: str) -> Optional[Dict[str, Any]]:
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(row, dict):
        return None
    actor = row.get("actor") or row.get("officer") or "unknown"
    rec: Dict[str, Any] = {
        "v": SCHEMA_VERSION,
        "src": "undo",
        "verb": "undo.journaled",
        "kind": "undo_journal",
        "actor": actor if ident_ok(actor) else "unknown",
        "ts": _clean_ts(row.get("ts")),
        "ref": ref,
    }
    attrs = clean_attrs(row, UNDO_ATTRS)
    idx = row.get("undo_index")
    if isinstance(idx, int) and not isinstance(idx, bool):
        attrs["undo_index"] = str(idx)
    if attrs:
        rec["attrs"] = attrs
    return rec


def normalize_toollog(line: str, ref: str) -> Optional[Dict[str, Any]]:
    """memory/logs rows carry tool inputs/outputs (free text, secrets
    possible) — ONLY officer + tool name survive ingest."""
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(row, dict):
        return None
    officer = row.get("officer") or row.get("agent") or "unknown"
    tool = row.get("tool") or row.get("tool_name")
    rec: Dict[str, Any] = {
        "v": SCHEMA_VERSION,
        "src": "toollog",
        "verb": "tool.call",
        "kind": "tool_call",
        "actor": officer if ident_ok(officer) else "unknown",
        "ts": _clean_ts(row.get("ts") or row.get("timestamp")),
        "ref": ref,
    }
    if ident_ok(tool):
        rec["attrs"] = {"tool": tool}
    return rec


def assert_scrubbed(rec: Dict[str, Any]) -> bool:
    """Belt-and-suspenders: the serialized record must contain no e-mail
    shape and no credential shape anywhere. A failing record is DROPPED and
    counted — never written."""
    blob = json.dumps(rec, sort_keys=True)
    if re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", blob):
        return False
    if _SECRET_RE.search(blob):
        return False
    return True


# ── sources ──────────────────────────────────────────────────────────────────

def read_org_events_batch(cursor: int, limit: int = BATCH_LIMIT
                          ) -> Tuple[List[Tuple], int]:
    """Rowid-cursor batch from the READ-ONLY handle with busy-retry."""
    if not SQLITE_DB.exists():
        return [], cursor
    uri = f"file:{SQLITE_DB}?mode=ro"
    for attempt in range(3):
        try:
            con = sqlite3.connect(uri, uri=True, timeout=5)
            try:
                rows = con.execute(
                    "SELECT rowid, event_id, event_type, aggregate_type, "
                    "actor, source, payload_json, created_at "
                    "FROM org_events WHERE rowid > ? ORDER BY rowid LIMIT ?",
                    (int(cursor), int(limit))).fetchall()
            finally:
                con.close()
            new_cursor = rows[-1][0] if rows else cursor
            return rows, new_cursor
        except sqlite3.OperationalError as e:
            if "locked" in str(e) or "busy" in str(e):
                time.sleep(0.4 * (attempt + 1))
                continue
            return [], cursor
        except sqlite3.Error:
            return [], cursor
    return [], cursor


def max_rowid() -> int:
    rows, _ = [], None
    if not SQLITE_DB.exists():
        return 0
    try:
        con = sqlite3.connect(f"file:{SQLITE_DB}?mode=ro", uri=True, timeout=5)
        try:
            r = con.execute("SELECT COALESCE(MAX(rowid), 0) FROM org_events"
                            ).fetchone()
            return int(r[0] or 0)
        finally:
            con.close()
    except sqlite3.Error:
        return 0


def tail_jsonl(path: Path, offset: int) -> Tuple[List[Tuple[str, str]], int]:
    """New complete lines after byte `offset` → [(line, 'file:lineno'), ...].
    Never re-reads consumed bytes; partial trailing lines wait for the next
    tick."""
    out: List[Tuple[str, str]] = []
    try:
        size = path.stat().st_size
    except OSError:
        return out, offset
    if size < offset:          # truncated/rotated in place — restart honestly
        offset = 0
    if size == offset:
        return out, offset
    try:
        with open(path, "rb") as f:
            f.seek(offset)
            chunk = f.read(size - offset)
    except OSError:
        return out, offset
    consumed = offset
    lineno_base = 0            # provenance is offset-based, stable + cheap
    for raw in chunk.split(b"\n")[:-1]:
        consumed += len(raw) + 1
        text = raw.decode("utf-8", errors="replace").strip()
        if text:
            out.append((text, f"{path.name}:{consumed - len(raw) - 1}"))
        lineno_base += 1
    return out, consumed


def dated_paths() -> Dict[str, List[Path]]:
    """Today's + yesterday's dated ledger files (midnight rollover window)."""
    today = dt.date.today()
    days = [today.isoformat(), (today - dt.timedelta(days=1)).isoformat()]
    cons = [EVENT_LOG_DIR / f"consequence-events-{d}.jsonl" for d in days]
    undo = [UNDO_DIR / f"undo-journal-{d}.jsonl" for d in days]
    tool = [TOOL_LOG_DIR / f"{d}.jsonl" for d in days]
    return {"consequence": [p for p in cons if p.exists()],
            "undo": [p for p in undo if p.exists()],
            "toollog": [p for p in tool if p.exists()]}


# ── redis (subprocess redis-cli — fleet convention; no new deps) ────────────

def redis_cmd(*args: str, timeout: int = 10) -> Optional[str]:
    try:
        proc = subprocess.run(
            ["redis-cli", "-h", REDIS_HOST, "-p", REDIS_PORT, *args],
            capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _resp_encode(commands: List[List[str]]) -> bytes:
    """RESP-encode a command batch for `redis-cli --pipe` (payloads carry
    spaces/JSON — inline protocol would mangle them)."""
    buf = bytearray()
    for cmd in commands:
        buf += f"*{len(cmd)}\r\n".encode()
        for arg in cmd:
            data = arg.encode()
            buf += f"${len(data)}\r\n".encode() + data + b"\r\n"
    return bytes(buf)


def redis_pipe(commands: List[List[str]]) -> bool:
    if not commands:
        return True
    try:
        proc = subprocess.run(
            ["redis-cli", "-h", REDIS_HOST, "-p", REDIS_PORT, "--pipe"],
            input=_resp_encode(commands), capture_output=True, timeout=30)
        return proc.returncode == 0
    except Exception:
        return False


def scan_keys(pattern: str) -> List[str]:
    out = redis_cmd("--scan", "--pattern", pattern)
    if not out:
        return []
    return [k for k in out.splitlines() if k]


# ── presence snapshot (ephemeral overlay — EX 60, authed T2 consumers) ──────

def build_presence(activity: Dict[str, Optional[str]],
                   heartbeats: Dict[str, Optional[int]],
                   killswitch_active: bool,
                   iid_high: int,
                   now_iso: str) -> Dict[str, Any]:
    """Pure snapshot builder. Activity values are the raw JSON strings from
    cabinet:officer:activity:<slug>; object strings are TRUNCATED and
    secret-checked (ephemeral T2 surface — durable chronicle never carries
    them)."""
    officers: Dict[str, Any] = {}
    for slug, raw in sorted(activity.items()):
        # 'unknown' is the post-tool-use hook's fallback identity for
        # non-officer sessions (OFFICER_NAME unset) — ambient machine
        # noise, not an officer. It must never render as a world presence
        # (v1a review fix: an 'unknown' officer stood in the cutaway
        # interior). Chronicle ACTORS keep their honest 'unknown'; the
        # presence overlay drops it upstream of every renderer.
        if slug == "unknown":
            continue
        entry: Dict[str, Any] = {"present": raw is not None}
        if raw:
            try:
                a = json.loads(raw)
            except json.JSONDecodeError:
                a = {}
            verb = a.get("verb")
            since = a.get("since")
            obj = a.get("object")
            if ident_ok(verb):
                entry["verb"] = verb
            if _clean_ts(since):
                entry["since"] = since
            if isinstance(obj, str) and obj and not _SECRET_RE.search(obj) \
                    and "@" not in obj:
                entry["object"] = obj[:120]
        hb = heartbeats.get(slug)
        if hb is not None:
            entry["hb_ttl_s"] = hb
        officers[slug] = entry
    return {
        "v": SCHEMA_VERSION,
        "ts": now_iso,
        "killswitch": bool(killswitch_active),
        "iid_high": int(iid_high),
        "officers": officers,
    }


def gather_presence(iid_high: int) -> Dict[str, Any]:
    activity: Dict[str, Optional[str]] = {}
    heartbeats: Dict[str, Optional[int]] = {}
    for key in scan_keys("cabinet:officer:activity:*"):
        slug = key.rsplit(":", 1)[-1]
        if not ident_ok(slug):
            continue
        activity[slug] = redis_cmd("GET", key)
    for slug in list(activity):
        ttl = redis_cmd("TTL", f"cabinet:heartbeat:{slug}")
        try:
            heartbeats[slug] = int(ttl) if ttl is not None else None
        except ValueError:
            heartbeats[slug] = None
    ks = redis_cmd("GET", "cabinet:killswitch")
    killswitch_active = bool(ks) and ks not in ("", "0", "inactive", "(nil)")
    return build_presence(activity, heartbeats, killswitch_active,
                          iid_high, _now_iso())


# ── state + output ───────────────────────────────────────────────────────────

def load_state() -> Dict[str, Any]:
    try:
        state = json.loads(STATE_PATH.read_text())
        if isinstance(state, dict):
            return state
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def save_state(state: Dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, sort_keys=True))
    os.replace(tmp, STATE_PATH)


def chronicle_path_for(rec: Dict[str, Any]) -> Path:
    """Partition by SOURCE event date (deterministic); undated records land
    in the epoch partition rather than inventing a clock."""
    ts = rec.get("ts") or ""
    date = ts[:10] if _TS_RE.match(ts or "") else "undated"
    return OUT_DIR / f"chronicle-{date}.jsonl"


def append_records(records: List[Dict[str, Any]]) -> None:
    by_path: Dict[Path, List[str]] = {}
    for rec in records:
        by_path.setdefault(chronicle_path_for(rec), []).append(
            json.dumps(rec, sort_keys=True))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path, lines in by_path.items():
        with open(path, "a") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write("\n".join(lines) + "\n")
                f.flush()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


# ── the tick ─────────────────────────────────────────────────────────────────

def collect_batch(state: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any], int]:
    """One ingest pass. Returns (records-with-iids, new_state, dropped)."""
    records: List[Dict[str, Any]] = []
    dropped = 0

    cursor = int(state.get("org_events_rowid", 0))
    rows, new_cursor = read_org_events_batch(cursor)
    for row in rows:
        rec = normalize_org_event(row)
        if rec is None:
            dropped += 1
            continue
        records.append(rec)

    offsets: Dict[str, int] = dict(state.get("offsets", {}))
    normalizers = {"consequence": normalize_consequence,
                   "undo": normalize_undo,
                   "toollog": normalize_toollog}
    for family, paths in dated_paths().items():
        for path in paths:
            key = f"{family}:{path.name}"
            lines, new_off = tail_jsonl(path, int(offsets.get(key, 0)))
            offsets[key] = new_off
            for text, ref in lines:
                rec = normalizers[family](text, ref)
                if rec is None:
                    dropped += 1
                    continue
                records.append(rec)
    # Retire offsets for files outside the rollover window (state hygiene).
    live_keys = {f"{fam}:{p.name}"
                 for fam, ps in dated_paths().items() for p in ps}
    offsets = {k: v for k, v in offsets.items() if k in live_keys}

    # Scrub gate + monotonic iids (assigned only to records that will land).
    iid = int(state.get("iid", 0))
    final: List[Dict[str, Any]] = []
    for rec in records:
        if not assert_scrubbed(rec):
            dropped += 1
            continue
        iid += 1
        rec["iid"] = iid
        final.append(rec)

    new_state = dict(state)
    new_state.update({"org_events_rowid": new_cursor, "offsets": offsets,
                      "iid": iid, "schema_version": SCHEMA_VERSION})
    return final, new_state, dropped


def publish_batch(records: List[Dict[str, Any]]) -> None:
    commands: List[List[str]] = []
    for rec in records:
        commands.append(["XADD", STREAM_KEY, "MAXLEN", "~",
                         str(STREAM_MAXLEN), "*",
                         "line", json.dumps(rec, sort_keys=True)])
    if records:
        commands.append(["PUBLISH", PUBSUB_CHANNEL,
                         json.dumps({"iid_high": records[-1]["iid"],
                                     "n": len(records)})])
    redis_pipe(commands)


def tick(state: Dict[str, Any], *, presence: bool = True
         ) -> Tuple[Dict[str, Any], int, int]:
    records, new_state, dropped = collect_batch(state)
    if records:
        append_records(records)      # durable first, stream second
        publish_batch(records)
    if presence:
        snap = gather_presence(int(new_state.get("iid", 0)))
        redis_pipe([
            ["SET", PRESENCE_KEY, json.dumps(snap, sort_keys=True),
             "EX", "60"],
            ["SET", HEARTBEAT_KEY,
             f"{_now_iso()} iid={new_state.get('iid', 0)}", "EX", "900"],
        ])
    save_state(new_state)
    return new_state, len(records), dropped


def main(argv: List[str]) -> int:
    once = "--once" in argv
    state = load_state()
    if "org_events_rowid" not in state:
        if os.environ.get("CABINET_WORLD_BACKFILL") == "1":
            state["org_events_rowid"] = 0
            print(f"[{_now_iso()}] world-chronicle: BACKFILL from rowid 0 "
                  f"(CABINET_WORLD_BACKFILL=1)")
        else:
            state["org_events_rowid"] = max_rowid()
            print(f"[{_now_iso()}] world-chronicle: first run — cursor "
                  f"initialized at max rowid {state['org_events_rowid']} "
                  f"(going-forward spine; deep history stays in org_events)")
    total = 0
    last_log = 0.0
    while True:
        state, n, dropped = tick(state)
        total += n
        now = time.monotonic()
        if n or dropped or once or (now - last_log) > 300:
            print(f"[{_now_iso()}] world-chronicle: +{n} records "
                  f"(dropped={dropped}, iid_high={state.get('iid', 0)}, "
                  f"cursor={state.get('org_events_rowid')})")
            last_log = now
            sys.stdout.flush()
        if once:
            return 0
        time.sleep(TICK_SECONDS)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
