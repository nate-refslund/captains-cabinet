#!/usr/bin/env python3.12
"""transcript-digest.py — ORG-SENSES-1 transcript-digest organ.

Nightly digest of officer Claude Code session transcripts into Cabinet
Memory, so the org's own working sessions become retrievable organizational
knowledge (sister gap to the 2026-07-07 memory-audit verdict: session
exhaust was write-only — nothing digested it).

WHAT IT READS (all read-only):
  * Officer session JSONLs under the default Claude config home's project
    dir for this repo (~/.claude/projects/<slugified-repo-path> by
    default on the hq deployment) AND the isolated cabinet config home's
    projects tree (AUD-1 pilot: ~/Library/Application Support/cabinet/
    claude-config/projects/*) — override via CABINET_TRANSCRIPT_DIRS
    (colon-separated dirs; each is scanned non-recursively for *.jsonl,
    plus one level of project subdirs).
  * ORCHESTRATOR session JSONLs (ORCH-SESSION-DIGEST, 2026-07-09): the
    captain-side Claude Code project dirs — the default config home's
    project slugs for the captain's $HOME and for this repo (both DERIVED
    from Path.home()/_REPO_ROOT, never hardcoded) — override via
    CABINET_ORCH_TRANSCRIPT_DIRS (same colon-separated semantics). Digests
    from these dirs carry provenance source_kind=orchestrator-session; a
    session there that opens with an officer boot prompt keeps session-jsonl
    provenance, and each path is digested ONCE even though the repo's
    project dir sits in both source lists (per-path dedupe).
  * Flight-recorder script(1) typescripts (mini-hatch runbook §Flight
    recorder — the seed source named by the ORG-SENSES-1 ledger row):
    CABINET_FLIGHT_RECORDER_DIRS, default ~/hatch-logs, files *.typescript.

WHAT IT WRITES:
  * Digest rows queued onto cabinet:memory:embed_queue via the EXISTING
    append path — cabinet/scripts/lib/memory.sh::memory_queue_embed (the
    memory-worker drains the queue; keyless/outage stays fail-soft: the
    queue is durable and memory_search's lexical arm still retrieves once
    rows land). source_type=transcript-digest, source_id=td:<session_id>
    (stable → re-digesting a grown session UPSERTS via the existing
    ON CONFLICT lane, version bumps). Provenance + content_ts stamped:
    metadata carries source_path/source_kind/digest_version, and
    source_created_at = the session's last event timestamp.
  * Prompt-pattern LESSONS as structured experience records
    (framework.learning.experience.record, lesson_type=pattern,
    applicability_scope=this_role) — the evidence supply skill_induction /
    the self-improvement loop clusters. PROPOSE-ONLY by construction: this
    organ never calls induce_drafts and never writes memory/skills/**.
  * Its own state (~/.cabinet/state/transcript-digest.json, atomic
    tmp+rename) and a heartbeat line appended to
    ~/.cabinet/logs/transcript-digest.log ONLY after a completed sweep
    (dead-man semantics — same discipline as apoptosis-sweep). Retention:
    the log rides the existing hygiene/apoptosis class over ~/.cabinet/logs
    (instance/config/retention.yml, 45d rotate-then-archive).

REDACTION (names-not-values, mandatory — transcripts carry secrets-adjacent
output, per the ORG-SENSES-1 ledger note):
  * STRUCTURAL taint firewall: tool_result blocks and attachments are NEVER
    read into a digest — captain-model / voice-profile content only reaches
    a session via brain-MCP tool results, so digests structurally cannot
    carry it (brain-bridge taint rule). Only user prompt text, assistant
    text, tool NAMES, and timestamps are consumed.
  * BELT: any surviving line that mentions a captain-model/voice surface
    (captain-model, voice-profile, nate_model, me_signal, voice.md) is
    dropped whole.
  * SCRUB: secret-shaped values are redacted keeping the NAME — env-style
    assignments whose name smells like KEY/TOKEN/SECRET/PASSWORD/
    CREDENTIAL/CONNECTION_STRING/API, Authorization/Bearer values, URL
    userinfo, vendor token shapes (sk-/ghp_/github_pat_/xox?-/AKIA/JWT),
    and long hex/base64 runs.

sunset: condition — "supersede-on-redigest (stable source_id upsert); review
this organ if its services.yml row sits disabled >90d" (apoptosis reviews
long-disabled service rows; digest rows carry the same condition in
metadata.sunset so a future memory-retention sweep can consume it).

Usage:
  python3.12 cabinet/scripts/transcript-digest.py [--dry-run] [--json]
      [--state PATH] [--max-sessions N]

Scheduled via cabinet/services.yml row `transcript-digest` (daily 04:10
local) through cabinet/scripts/transcript-digest.sh; the cabinet-doctor
manifest probe and the outcome-watchdog registry derive coverage from that
row.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DIGEST_VERSION = 1
SOURCE_TYPE = "transcript-digest"
SUNSET_CONDITION = ("supersede-on-redigest; review organ if services.yml row "
                    "disabled >90d")
MAX_DIGEST_CHARS = 6000
MAX_LINE_CHARS = 300
MAX_MARKER_LINES = 12
MAX_PATTERNS = 10

_REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Source discovery — dirs come ONLY from defaults or controlled env vars;
# files are globbed inside them (no caller-supplied file paths → no traversal).
# ---------------------------------------------------------------------------

def transcript_dirs() -> list[Path]:
    env = os.environ.get("CABINET_TRANSCRIPT_DIRS")
    if env:
        return [Path(p).expanduser() for p in env.split(":") if p.strip()]
    home = Path.home()
    dirs = [home / ".claude" / "projects" /
            ("-" + str(_REPO_ROOT).strip("/").replace("/", "-"))]
    iso = (home / "Library" / "Application Support" / "cabinet" /
           "claude-config" / "projects")
    dirs.append(iso)
    return dirs


def orchestrator_transcript_dirs() -> list[Path]:
    """ORCH-SESSION-DIGEST sources: the captain-side (orchestrator) Claude
    Code project dirs — $HOME's and this repo's project slugs under the
    default config home. Same env-override semantics as transcript_dirs();
    defaults are DERIVED (clean-room discipline — no launcher literals)."""
    env = os.environ.get("CABINET_ORCH_TRANSCRIPT_DIRS")
    if env:
        return [Path(p).expanduser() for p in env.split(":") if p.strip()]
    home = Path.home()
    projects = home / ".claude" / "projects"

    def _slug(p: Path) -> str:
        return "-" + str(p).strip("/").replace("/", "-")

    return [projects / _slug(home), projects / _slug(_REPO_ROOT)]


def flight_recorder_dirs() -> list[Path]:
    env = os.environ.get("CABINET_FLIGHT_RECORDER_DIRS")
    if env:
        return [Path(p).expanduser() for p in env.split(":") if p.strip()]
    return [Path.home() / "hatch-logs"]


def discover_jsonls(dirs: list[Path]) -> list[Path]:
    """*.jsonl in each dir, plus ONE level of subdirs (the isolated config
    home's projects/ tree is projects/<project-slug>/*.jsonl)."""
    out: list[Path] = []
    for d in dirs:
        if not d.is_dir():
            continue
        out.extend(p for p in d.glob("*.jsonl") if p.is_file())
        for sub in d.iterdir():
            if sub.is_dir():
                out.extend(p for p in sub.glob("*.jsonl") if p.is_file())
    return sorted(set(out))


def discover_typescripts(dirs: list[Path]) -> list[Path]:
    out: list[Path] = []
    for d in dirs:
        if not d.is_dir():
            continue
        out.extend(p for p in d.glob("*.typescript") if p.is_file())
    return sorted(set(out))


# ---------------------------------------------------------------------------
# Redaction — names-not-values + captain-model/voice taint belt
# ---------------------------------------------------------------------------

_TAINT_RE = re.compile(
    r"(?i)(captain[-_ ]?model|voice[-_ ]?profile|nate_model|me_signal|"
    r"\bvoice\.md\b)")

_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # NAME=value / NAME: value where NAME smells secret — keep the name.
    (re.compile(
        r"(?i)\b([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|"
        r"CONNECTION_STRING|API)[A-Z0-9_]*)\s*[=:]\s*[^\s\"']+"),
     r"\1=<redacted>"),
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 <redacted>"),
    (re.compile(r"(?i)\b(authorization:)\s*\S+"), r"\1 <redacted>"),
    # URL userinfo — postgres://user:pass@host, https://token@host
    (re.compile(r"([a-z][a-z0-9+.-]*://)[^/@\s]+@"), r"\1<redacted>@"),
    (re.compile(r"\b(?:sk|rk)-[A-Za-z0-9_-]{16,}\b"), "<redacted>"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "<redacted>"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "<redacted>"),
    (re.compile(r"\bxox[a-z]-[A-Za-z0-9-]{10,}\b"), "<redacted>"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "<redacted>"),
    # JWT (three base64url segments)
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
                r"\.[A-Za-z0-9_-]{5,}\b"), "<redacted>"),
    # Long hex (≥48 — 40-hex git SHAs survive) and long base64 runs.
    (re.compile(r"\b[0-9a-fA-F]{48,}\b"), "<redacted>"),
    (re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b"), "<redacted>"),
]


def redact_text(text: str) -> tuple[str, int, int]:
    """(redacted_text, secret_hits, taint_lines_dropped). Line-oriented so
    the taint belt can drop whole lines."""
    secret_hits = 0
    taint_drops = 0
    out_lines: list[str] = []
    for line in text.splitlines():
        if _TAINT_RE.search(line):
            taint_drops += 1
            continue
        for rx, repl in _SECRET_PATTERNS:
            line, n = rx.subn(repl, line)
            secret_hits += n
        out_lines.append(line)
    return "\n".join(out_lines), secret_hits, taint_drops


# ---------------------------------------------------------------------------
# Session JSONL parsing — user prompt text + assistant text + tool names ONLY
# (tool_result blocks / attachments are structurally excluded — taint firewall)
# ---------------------------------------------------------------------------

_OFFICER_RE = re.compile(r"^\s*You are ([a-z0-9][a-z0-9-]{1,31})\b")
_SYSTEMISH_RE = re.compile(
    r"(?i)^\s*(caveat:|<command-name>|<local-command-stdout>|"
    r"<system-reminder>)")

_DECISION_RE = re.compile(
    r"(?i)\b(decision|decided|ruling|ratif\w+|approved|vetoe?d?|"
    r"captain[- ](says|said|ruled|gated))\b")
_LESSON_RE = re.compile(
    r"(?i)\b(lesson|gotcha|learned|root[- ]cause|anti[- ]?pattern|pitfall|"
    r"caveat)\b")

_WS_RE = re.compile(r"\s+")
_NUM_RE = re.compile(r"\d+")
_PATH_RE = re.compile(r"(~?/[\w.@/-]{8,})")
_URL_RE = re.compile(r"https?://\S+")

# Harness-generated first lines that recur by MACHINERY, not by prompt-craft
# — never pattern-lesson material (observed live 2026-07-07: compaction
# continuations, stop-hook feedback, malformed-tool retries dominate the
# multi-session signature list without these filters).
_MACHINE_PROMPT_RE = re.compile(
    r"(?i)^(this session is being continued|stop hook feedback|"
    r"your tool call was malformed|\[request interrupted)")


def prompt_signature(prompt: str) -> str | None:
    """Normalized signature of a user prompt's first line — the clustering
    key for prompt-pattern lessons. None for boot/system-ish prompts."""
    first = prompt.strip().splitlines()[0].strip() if prompt.strip() else ""
    if not first or _SYSTEMISH_RE.match(first):
        return None
    if not first[0].isalpha():
        return None  # tags/emoji/markdown-injected lines — machinery, not craft
    if _MACHINE_PROMPT_RE.match(first):
        return None
    if first.lower().startswith("you are "):
        return None  # officer boot prompt — recurs by design, not a lesson
    sig = _URL_RE.sub("<url>", first)
    sig = _PATH_RE.sub("<path>", sig)
    sig = _NUM_RE.sub("#", sig)
    sig = _WS_RE.sub(" ", sig).strip().lower()
    if len(sig) < 12:
        return None  # too short to be a meaningful pattern
    return sig[:96]


def _iter_text_blocks(content) -> list[str]:
    """Text from a message content field. Strings pass through; block lists
    yield ONLY type=text blocks (never tool_result, never thinking)."""
    if isinstance(content, str):
        return [content]
    texts: list[str] = []
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                t = b.get("text")
                if isinstance(t, str):
                    texts.append(t)
    return texts


def parse_session(path: Path) -> dict | None:
    """One session JSONL → structured extraction (pre-redaction). None when
    the file holds no usable conversation."""
    session_id = path.stem
    officer = ""
    first_ts = ""
    last_ts = ""
    user_prompts: list[str] = []
    assistant_texts: list[str] = []
    tool_counts: dict[str, int] = {}
    n_user = n_assistant = 0

    try:
        fh = path.open("r", encoding="utf-8", errors="replace")
    except OSError:
        return None
    with fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue  # torn tail line of a live session — skip
            ts = obj.get("timestamp")
            if isinstance(ts, str) and ts:
                if not first_ts:
                    first_ts = ts
                last_ts = ts
            sid = obj.get("sessionId")
            if isinstance(sid, str) and sid:
                session_id = sid
            otype = obj.get("type")
            msg = obj.get("message")
            if otype == "user" and isinstance(msg, dict):
                n_user += 1
                for text in _iter_text_blocks(msg.get("content")):
                    if _SYSTEMISH_RE.match(text):
                        continue
                    if not officer:
                        m = _OFFICER_RE.match(text)
                        if m:
                            officer = m.group(1)
                    user_prompts.append(text)
            elif otype == "assistant" and isinstance(msg, dict):
                n_assistant += 1
                content = msg.get("content")
                assistant_texts.extend(_iter_text_blocks(content))
                if isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "tool_use":
                            name = b.get("name")
                            if isinstance(name, str) and name:
                                tool_counts[name] = tool_counts.get(name, 0) + 1

    if not user_prompts and not assistant_texts:
        return None
    return {
        "session_id": session_id,
        "officer": officer,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "user_prompts": user_prompts,
        "assistant_texts": assistant_texts,
        "tool_counts": tool_counts,
        "n_user": n_user,
        "n_assistant": n_assistant,
    }


def _marker_lines(texts: list[str], rx: re.Pattern[str],
                  cap: int = MAX_MARKER_LINES) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for text in texts:
        for line in text.splitlines():
            line = line.strip()
            if not line or len(line) < 12:
                continue
            if not rx.search(line):
                continue
            key = line[:120].lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(line[:MAX_LINE_CHARS])
            if len(out) >= cap:
                return out
    return out


def build_digest(sess: dict, source_path: str,
                 source_kind: str = "session-jsonl") -> dict:
    """Session extraction → redacted digest payload (content + metadata)."""
    all_texts = sess["user_prompts"] + sess["assistant_texts"]
    decisions = _marker_lines(all_texts, _DECISION_RE)
    lessons = _marker_lines(all_texts, _LESSON_RE)

    sig_counts: dict[str, int] = {}
    for p in sess["user_prompts"]:
        sig = prompt_signature(p)
        if sig:
            sig_counts[sig] = sig_counts.get(sig, 0) + 1
    top_sigs = sorted(sig_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    top_sigs = top_sigs[:MAX_PATTERNS]

    tools = sorted(sess["tool_counts"].items(), key=lambda kv: (-kv[1], kv[0]))
    tools_str = ", ".join(f"{n}×{c}" for n, c in tools[:12]) or "(none)"
    officer = sess["officer"] or "unknown"

    first_prompt = ""
    for p in sess["user_prompts"]:
        if p.strip():
            first_prompt = p.strip().splitlines()[0][:MAX_LINE_CHARS]
            break

    parts = [
        f"# transcript digest — session {sess['session_id']} ({officer})",
        f"window: {sess['first_ts'] or '?'} → {sess['last_ts'] or '?'} · "
        f"turns: user {sess['n_user']} / assistant {sess['n_assistant']} · "
        f"tools: {tools_str}",
        f"opening prompt: {first_prompt}" if first_prompt else "",
    ]
    if decisions:
        parts.append("\n## decision-marked lines\n" +
                     "\n".join(f"- {ln}" for ln in decisions))
    if lessons:
        parts.append("\n## lesson-marked lines\n" +
                     "\n".join(f"- {ln}" for ln in lessons))
    if top_sigs:
        parts.append("\n## prompt patterns\n" +
                     "\n".join(f"- \"{s}\" ×{c}" for s, c in top_sigs))

    raw = "\n".join(p for p in parts if p)
    content, secret_hits, taint_drops = redact_text(raw)
    content = content[:MAX_DIGEST_CHARS]

    metadata = {
        "source_path": source_path,
        "source_kind": source_kind,
        "digest_version": DIGEST_VERSION,
        "content_ts": sess["last_ts"] or None,
        "redacted_secrets": secret_hits,
        "taint_lines_dropped": taint_drops,
        "apoptosis_class": "digest-exhaust",
        "sunset": SUNSET_CONDITION,
    }
    return {
        "source_id": f"td:{sess['session_id']}",
        "officer": officer if officer != "unknown" else "",
        "content": content,
        "metadata": metadata,
        "source_ts": sess["last_ts"] or "",
        "signatures": sig_counts,
    }


# ---------------------------------------------------------------------------
# Flight-recorder typescripts (seed source)
# ---------------------------------------------------------------------------

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][A-Z0-9]|[\x00-\x08\x0b-\x1f\x7f]")
_ERROR_RE = re.compile(r"(?i)\b(error|fatal|failed|refused|denied|panic)\b")


def digest_typescript(path: Path) -> dict | None:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    text = _ANSI_RE.sub("", raw)
    lines = [ln.rstrip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln.strip()]
    if not lines:
        return None
    head = lines[:60]
    errors = _marker_lines(["\n".join(lines)], _ERROR_RE)
    decisions = _marker_lines(["\n".join(lines)], _DECISION_RE)
    tail = lines[-30:]
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    content_ts = mtime.strftime("%Y-%m-%dT%H:%M:%SZ")

    parts = [
        f"# flight-recorder digest — {path.name}",
        f"captured: {content_ts} · lines: {len(lines)}",
        "\n## opening\n" + "\n".join(ln[:MAX_LINE_CHARS] for ln in head[:20]),
    ]
    if errors:
        parts.append("\n## error-marked lines\n" +
                     "\n".join(f"- {ln}" for ln in errors))
    if decisions:
        parts.append("\n## decision-marked lines\n" +
                     "\n".join(f"- {ln}" for ln in decisions))
    parts.append("\n## closing\n" +
                 "\n".join(ln[:MAX_LINE_CHARS] for ln in tail[-10:]))

    content, secret_hits, taint_drops = redact_text("\n".join(parts))
    content = content[:MAX_DIGEST_CHARS]
    sid = hashlib.sha256(path.name.encode()).hexdigest()[:12]
    return {
        "source_id": f"td:fr:{sid}",
        "officer": "",
        "content": content,
        "metadata": {
            "source_path": str(path),
            "source_kind": "flight-recorder",
            "digest_version": DIGEST_VERSION,
            "content_ts": content_ts,
            "redacted_secrets": secret_hits,
            "taint_lines_dropped": taint_drops,
            "apoptosis_class": "digest-exhaust",
            "sunset": SUNSET_CONDITION,
        },
        "source_ts": content_ts,
        "signatures": {},
    }


# ---------------------------------------------------------------------------
# Cabinet-memory queue (the existing append path — lib/memory.sh)
# ---------------------------------------------------------------------------

def queue_digest(digest: dict, repo_root: Path = _REPO_ROOT) -> bool:
    """Queue one digest onto cabinet:memory:embed_queue through
    memory_queue_embed. Args pass as ARGV (never interpolated into the
    command string — injection-safe by construction). Returns False on any
    failure (caller leaves the file un-digested so the next run retries)."""
    cmd = [
        "bash", "-c",
        'source "$0/cabinet/scripts/lib/memory.sh" && '
        'memory_queue_embed "$1" "$2" "$3" "$4" "$5" "$6" "$7"',
        str(repo_root),
        SOURCE_TYPE,
        digest["source_id"],
        digest["officer"],
        "",  # sender
        digest["content"],
        json.dumps(digest["metadata"]),
        digest["source_ts"] or datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=30)
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


# ---------------------------------------------------------------------------
# Prompt-pattern lessons → experience records (skill_induction evidence)
# ---------------------------------------------------------------------------

MAX_RECORDS_PER_SIG = 5     # induction clusters at 3; 5 leaves headroom
MAX_RECORDS_PER_SWEEP = 100  # backlog runs must not flood the store


def emit_pattern_records(digest: dict, state: dict, dry_run: bool,
                         sweep_budget: list[int] | None = None) -> int:
    """A signature becomes a lesson when it recurs — ≥2 uses inside one
    session, or seen across ≥2 sessions (state-tracked). One record per
    (session, signature), deduped in state; per-signature cap
    MAX_RECORDS_PER_SIG (a 300-session harness pattern must not mint 300
    identical records) + per-sweep budget. PROPOSE-ONLY evidence."""
    session_id = digest["source_id"]
    emitted = state.setdefault("emitted", {}).setdefault(session_id, [])
    signatures = state.setdefault("signatures", {})
    n = 0
    for sig, count in sorted(digest.get("signatures", {}).items()):
        entry = signatures.setdefault(sig, {"count": 0, "sessions": [],
                                            "records": 0})
        entry.setdefault("records", 0)
        if session_id not in entry["sessions"]:
            entry["sessions"] = (entry["sessions"] + [session_id])[-20:]
            entry["count"] += count
        recurring = count >= 2 or len(entry["sessions"]) >= 2
        if not recurring or sig in emitted:
            continue
        if entry["records"] >= MAX_RECORDS_PER_SIG:
            continue
        if sweep_budget is not None and sweep_budget[0] <= 0:
            break
        if not dry_run:
            try:
                sys.path.insert(0, str(_REPO_ROOT))
                from framework.learning.experience import record
                record(
                    actor=digest["officer"] or "transcript-digest",
                    lesson_type="pattern",
                    trigger_signal=f"prompt-pattern: {sig}",
                    body=(f"Recurring prompt pattern observed by the "
                          f"transcript-digest organ (×{count} this session; "
                          f"seen in {len(entry['sessions'])} session(s)). "
                          f"Digest ref: cabinet_memory {session_id}."),
                    applicability_scope="this_role",
                    evidence=f"cabinet_memory:{session_id}",
                )
            except Exception as e:  # noqa: BLE001 — evidence supply is best-effort
                print(f"[transcript-digest] WARN experience record failed: {e}",
                      file=sys.stderr)
                continue
        emitted.append(sig)
        entry["records"] += 1
        if sweep_budget is not None:
            sweep_budget[0] -= 1
        n += 1
    return n


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def default_state_path() -> Path:
    env = os.environ.get("CABINET_TD_STATE")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".cabinet" / "state" / "transcript-digest.json"


def load_state(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            data.setdefault("version", 1)
            data.setdefault("files", {})
            data.setdefault("signatures", {})
            data.setdefault("emitted", {})
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"version": 1, "files": {}, "signatures": {}, "emitted": {}}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1, sort_keys=True))
    tmp.replace(path)


def heartbeat(summary: dict) -> None:
    log_dir = Path(os.environ.get("CABINET_TD_LOG_DIR",
                                  str(Path.home() / ".cabinet" / "logs")))
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        line = (f"[transcript-digest {stamp}] DIGESTED "
                f"sessions={summary['sessions_digested']} "
                f"orch={summary['orchestrator_digested']} "
                f"flight={summary['flight_digested']} "
                f"queued={summary['queued']} "
                f"records={summary['pattern_records']} "
                f"skipped={summary['skipped_unchanged']} "
                f"failures={summary['queue_failures']}\n")
        with (log_dir / "transcript-digest.log").open("a") as fh:
            fh.write(line)
    except OSError as e:
        print(f"[transcript-digest] WARN heartbeat write failed: {e}",
              file=sys.stderr)


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------

def run_sweep(dry_run: bool = False, max_sessions: int = 200,
              state_path: Path | None = None) -> dict:
    state_path = state_path or default_state_path()
    state = load_state(state_path)
    summary = {
        "sessions_digested": 0, "orchestrator_digested": 0,
        "flight_digested": 0, "queued": 0,
        "pattern_records": 0, "skipped_unchanged": 0, "queue_failures": 0,
        "dry_run": dry_run,
    }

    # ORCH-SESSION-DIGEST: orchestrator/captain-side dirs claim first so
    # their sessions carry orchestrator provenance; the per-session officer
    # boot check below hands genuinely-officer sessions back to session-jsonl
    # provenance, so overlap files (the repo's own project dir is in both
    # lists) never flip an officer digest. Each path is digested ONCE.
    work: list[tuple[str, Path]] = []
    claimed: set[Path] = set()
    for p in discover_jsonls(orchestrator_transcript_dirs()):
        if p not in claimed:
            work.append(("orchestrator", p))
            claimed.add(p)
    for p in discover_jsonls(transcript_dirs()):
        if p not in claimed:
            work.append(("session", p))
            claimed.add(p)
    for p in discover_typescripts(flight_recorder_dirs()):
        work.append(("flight", p))

    sweep_budget = [MAX_RECORDS_PER_SWEEP]
    handled = 0
    for kind, path in work:
        if handled >= max_sessions:
            break
        key = str(path)
        try:
            st = path.stat()
        except OSError:
            continue
        prev = state["files"].get(key)
        if prev and prev.get("size") == st.st_size and \
                prev.get("digest_version") == DIGEST_VERSION:
            summary["skipped_unchanged"] += 1
            continue

        if kind in ("session", "orchestrator"):
            sess = parse_session(path)
            if sess is None:
                # unusable file — remember size so we don't re-parse nightly
                state["files"][key] = {"size": st.st_size, "mtime": st.st_mtime,
                                       "digest_version": DIGEST_VERSION,
                                       "unusable": True}
                continue
            source_kind = "session-jsonl"
            if kind == "orchestrator" and not sess["officer"]:
                source_kind = "orchestrator-session"
            digest = build_digest(sess, source_path=key,
                                  source_kind=source_kind)
        else:
            digest = digest_typescript(path)
            if digest is None:
                state["files"][key] = {"size": st.st_size, "mtime": st.st_mtime,
                                       "digest_version": DIGEST_VERSION,
                                       "unusable": True}
                continue

        handled += 1
        queued_ok = True
        if not dry_run:
            queued_ok = queue_digest(digest)
        if queued_ok:
            summary["queued"] += 1
            if kind == "flight":
                summary["flight_digested"] += 1
            elif digest["metadata"]["source_kind"] == "orchestrator-session":
                summary["orchestrator_digested"] += 1
            else:
                summary["sessions_digested"] += 1
            state["files"][key] = {
                "size": st.st_size, "mtime": st.st_mtime,
                "session_id": digest["source_id"],
                "digest_version": DIGEST_VERSION,
                "digested_at": datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"),
            }
        else:
            summary["queue_failures"] += 1
            continue  # not marked — retried next run

        summary["pattern_records"] += emit_pattern_records(
            digest, state, dry_run, sweep_budget)

    if not dry_run:
        save_state(state_path, state)
        heartbeat(summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="parse + report only; no queue, no records, no state")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--state", default=None,
                    help="state file override (default ~/.cabinet/state/"
                         "transcript-digest.json or $CABINET_TD_STATE)")
    ap.add_argument("--max-sessions", type=int, default=200)
    args = ap.parse_args(argv)

    summary = run_sweep(
        dry_run=args.dry_run,
        max_sessions=args.max_sessions,
        state_path=Path(args.state).expanduser() if args.state else None,
    )
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"[transcript-digest] sessions={summary['sessions_digested']} "
              f"orch={summary['orchestrator_digested']} "
              f"flight={summary['flight_digested']} queued={summary['queued']} "
              f"records={summary['pattern_records']} "
              f"skipped={summary['skipped_unchanged']} "
              f"failures={summary['queue_failures']}"
              f"{' (dry-run)' if summary['dry_run'] else ''}")
    # Queue failures are visible but non-fatal only when SOMETHING landed;
    # a fully-failed sweep exits nonzero so launchd surfaces it.
    if summary["queue_failures"] and not summary["queued"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
