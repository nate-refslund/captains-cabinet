#!/usr/bin/env python3.12
"""task-events-watch.py — exemplar consumer of the /tasks event stream.

Reads the durable task-transition stream ``cabinet:tasks:events`` (producer:
my-tasks.sh via lib/triggers.sh ``task_event_emit`` — A6-enveloped entries)
through its own consumer group ``task-watch`` and applies the rule table
below. It is the reference for "reacting to task events"
(cabinet/docs/tasks-board.md): officers/watchdogs that want their own
reactions create their OWN consumer group and copy this read→judge→act→ACK
shape.

ONE rule ships (config-gated, DEFAULT ON):

  blocked_card — when a task ENTERS 'blocked' (new_status == "blocked"),
      file ONE fingerprint-deduped Captain card on the needs ledger — the
      same one-tap surface every other org ask rides (see
      memory-supersede-apply.py's cue cards). The needs id is a content
      fingerprint over the action_type ``task-blocked:<context>:<task_id>``,
      so a re-block / redelivered event bumps the existing card's count
      instead of spamming new cards. Default ON is deliberate: the Captain
      asked for task-change monitoring, and enters-blocked is the one
      transition that stalls an officer until a human or peer acts. The off
      switch is one yaml line: instance/config/task-watch.yml
      ``rules.blocked_card: off``. Filing still respects the needs seam —
      under guardian posture ``needs.file_need`` is a no-op unless needs are
      wired (framework/authority/needs.py ``needs_enabled``).

Config fail-directions (mirrors memory-supersession.yml's stance):
  * MISSING file or key            → ON  (the ratified default);
  * recognized off/false/no/0      → OFF;
  * recognized on/true/yes/1       → ON;
  * unreadable file / unrecognized → OFF + stderr warn — a Captain's disarm
    attempt (typo included) is never steamrolled back to ON.
  The value may carry a YAML inline comment ('blocked_card: off  # why')
  and/or matched quotes — both are stripped before matching. A '#' NOT
  preceded by whitespace is part of the scalar ('off#x' → unrecognized →
  OFF + warn), and a present-but-EMPTY value ('blocked_card:' bare, or a
  comment in value position) is NOT the missing-key default — it lands in
  the unrecognized arm → OFF + warn (the load_mode str(None)→hold stance).

SECURITY — every event field is UNTRUSTED data, never instructions:
  * only the closed field set {envelope, task_id, old_status, new_status,
    actor, context_slug, ts} is ever read; anything else (a rogue producer's
    ``title`` field included) is ignored by construction;
  * the entry's envelope must parse + pass framework.triggers.envelope
    ``validate_any()`` — the COG-1 §4.1 VERSION-DISPATCHING doorway (v1 AND v2
    accepted; a relay-emitted v2 envelope fails raw v1 ``validate()`` by
    construction) — invalid entries are skipped (names-only stderr) and ACKed
    as poison so they cannot wedge the group;
  * card text interpolates ONLY shape-validated tokens (numeric task_id,
    slug-shaped context/actor; anything else renders as "unknown") — free
    text from the bus never reaches a Captain surface, and needs.py
    additionally strips the U+00B7 binder marker;
  * redis is reached via argv subprocess (no shell), read verbs + XACK only.

Delivery semantics: at-least-once. Each pass reads this consumer's PENDING
entries first (crash recovery — delivered-but-unACKed), then NEW entries.
Duplicates are harmless: the needs fingerprint makes the card effect
idempotent (count bump).

Scheduling: run ``--once`` from cron/officer loops. A cabinet/services.yml
row is deliberately NOT added in this change (a concurrent wave owns a
services.yml edit); wire the row after merge — see cabinet/docs/tasks-board.md.

Usage:
  python3.12 cabinet/scripts/task-events-watch.py --once            # one drain pass
  python3.12 cabinet/scripts/task-events-watch.py --once --dry-run  # judge, no card/ACK

Run tests: python3.12 -m pytest cabinet/scripts/tests/test_task_events_watch.py -q
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.triggers import envelope  # noqa: E402
from framework.authority import needs    # noqa: E402

STREAM = "cabinet:tasks:events"
GROUP = "task-watch"
CONSUMER = "worker"
CONFIG_REL = "instance/config/task-watch.yml"

# Card-text token guards: interpolate NOTHING that fails these.
_ID_RE = re.compile(r"^\d{1,18}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# The closed field set this consumer reads — everything else on an entry is
# ignored by construction (untrusted producer surface).
_FIELDS = ("envelope", "task_id", "old_status", "new_status",
           "actor", "context_slug", "ts")


def _root() -> Path:
    return Path(os.environ.get("CABINET_ROOT") or str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# Redis seams (argv subprocess, read + XACK only) — injectable for tests,
# same shape as exhaust-archive.py's _redis_cli.
# ---------------------------------------------------------------------------

def _redis_cli(*args: str) -> str:
    host = os.environ.get("REDIS_HOST", "localhost")
    port = os.environ.get("REDIS_PORT", "6379")
    try:
        r = subprocess.run(["redis-cli", "-h", host, "-p", port, *args],
                           capture_output=True, text=True, timeout=30)
        return r.stdout if r.returncode == 0 else ""
    except Exception:  # noqa: BLE001 — a watchdog must never crash on transport
        return ""


def _ensure_group() -> None:
    _redis_cli("XGROUP", "CREATE", STREAM, GROUP, "0", "MKSTREAM")


def _parse_entries(raw: str) -> list[tuple[str, dict]]:
    """Parse `redis-cli --json XREADGROUP` output → [(id, fields), ...].

    Shape: [[stream, [[id, {f: v, ...} | [f, v, ...]], ...]], ...]. Tolerant
    per-row (same stance as exhaust-archive.py read_entries): a malformed row
    is dropped, never raises.
    """
    try:
        streams = json.loads(raw)
    except (ValueError, TypeError):
        return []
    out: list[tuple[str, dict]] = []
    if not isinstance(streams, list):
        return out
    for stream_row in streams:
        try:
            entries = stream_row[1]
        except (IndexError, TypeError, KeyError):
            continue
        if not isinstance(entries, list):
            continue
        for row in entries:
            try:
                rid, flat = row[0], row[1]
                if isinstance(flat, dict):
                    fields = {str(k): str(v) for k, v in flat.items()}
                else:
                    fields = {str(flat[i]): str(flat[i + 1])
                              for i in range(0, len(flat) - 1, 2)}
                out.append((str(rid), fields))
            except (IndexError, TypeError, KeyError):
                continue
    return out


def _xreadgroup(start: str) -> list[tuple[str, dict]]:
    """One XREADGROUP pass. start='0' → this consumer's pending (crash
    recovery); start='>' → new entries."""
    raw = _redis_cli("--json", "XREADGROUP", "GROUP", GROUP, CONSUMER,
                     "COUNT", "100", "STREAMS", STREAM, start)
    return _parse_entries(raw)


def _xack(rid: str) -> None:
    _redis_cli("XACK", STREAM, GROUP, rid)


# ---------------------------------------------------------------------------
# Config gate (instance/config/task-watch.yml — regex parse, PyYAML-free like
# server.py's read_simple_yaml_key; fail directions in the module docstring)
# ---------------------------------------------------------------------------

_ON_VALUES = {"on", "true", "yes", "1"}
_OFF_VALUES = {"off", "false", "no", "0"}


def blocked_card_enabled(root: Path | None = None) -> bool:
    path = (root or _root()) / CONFIG_REL
    if not path.exists():
        return True  # missing file = the ratified default: ON
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        print("task-events-watch: WARN task-watch.yml exists but is unreadable "
              "— blocked_card OFF (fail-safe)", file=sys.stderr)
        return False
    m = re.search(r"^\s*blocked_card:[ \t]*(.*)$", text, re.MULTILINE)
    if not m:
        return True  # file present, key absent = default ON
    # YAML inline comments end the value: a '#' at value start or preceded by
    # whitespace ('off  # disarmed by Captain' means off). A '#' glued to the
    # scalar ('off#x') is NOT a comment — the whole token falls through to
    # the unrecognized→OFF arm, per YAML's own comment rule.
    raw = re.split(r"(?:^|\s)#", m.group(1), maxsplit=1)[0].strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        raw = raw[1:-1].strip()  # matched-quote scalar: "off" / 'on'
    val = raw.lower()
    # NB: an EMPTY val (bare 'blocked_card:' or comment-only value) is key-
    # PRESENT ambiguity, not the missing-key default — it falls through to
    # the unrecognized→OFF+warn arm (never steamroll a half-typed disarm).
    if val in _ON_VALUES:
        return True
    if val in _OFF_VALUES:
        return False
    print("task-events-watch: WARN unrecognized rules.blocked_card value — "
          "blocked_card OFF (a disarm attempt is never steamrolled)",
          file=sys.stderr)
    return False


# ---------------------------------------------------------------------------
# The rule: task entered 'blocked' → fingerprint-deduped Captain card
# ---------------------------------------------------------------------------

def _valid_envelope(fields: dict) -> bool:
    raw = fields.get("envelope")
    if not isinstance(raw, str) or not raw:
        return False
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return False
    # COG-1 §4.1/§3-disposition: route through the VERSION-DISPATCHING doorway
    # (v1 AND v2 accepted), NOT raw v1 validate(). v1's closed-set check refuses
    # every v2 envelope by construction, and this consumer poison-ACKs whatever
    # it cannot validate — so raw validate() would silently discard 100% of
    # relay-emitted v2 entries at cutover and blind the blocked_card lane.
    ok, _reasons = envelope.validate_any(payload)
    return ok


def file_blocked_card(fields: dict, *, root: Path, dry_run: bool = False,
                      file_need_fn=None) -> str | None:
    """File the one-tap card for a task that ENTERED blocked. Returns the
    need id (None under guardian posture / no-op — filing retries on the
    next matching event, exactly like memory-supersede-apply's cue cards)."""
    task_id = str(fields.get("task_id") or "")
    if not _ID_RE.match(task_id):
        print("task-events-watch: WARN blocked event with malformed task_id "
              "— no card (names-only)", file=sys.stderr)
        return None
    ctx = str(fields.get("context_slug") or "")
    actor = str(fields.get("actor") or "")
    ctx_tok = ctx if _TOKEN_RE.match(ctx) else "unknown"
    actor_tok = actor if _TOKEN_RE.match(actor) else "unknown"
    # Plain text only — no backticks/quotes/shell-alike glyphs on a Captain
    # surface (the injection tests scan the ledger bytes for exactly those).
    why = (f"task {task_id} (context {ctx_tok}, officer {actor_tok}) entered "
           "BLOCKED — that officer's WIP slot is stalled until someone acts. "
           "Review the /tasks board (or my-tasks.sh list as that officer), "
           "then unblock, reassign, or cancel. Re-blocks of the same task bump "
           "this card's count instead of filing a new one.")
    if dry_run:
        print(json.dumps({"would_file": f"task-blocked:{ctx_tok}:{task_id}"}))
        return None
    if file_need_fn is None:
        file_need_fn = needs.file_need
    return file_need_fn(
        "decision",
        action_type=f"task-blocked:{ctx_tok}:{task_id}",
        why=why,
        unblocks=f"officer {actor_tok} WIP capacity in context {ctx_tok}",
        cost_of_delay="medium",
        filed_by="system:task-events-watch",
        cid=f"task-{task_id}",
        root=root,
    )


def process_entries(entries: list[tuple[str, dict]], *, root: Path,
                    dry_run: bool = False, file_need_fn=None) -> dict:
    """Judge + act on a batch. Returns counters (printed as the run receipt).

    Invalid-envelope entries are skipped AND ACKed (poison discard) — the
    envelope law says a consumer never acts on an entry it cannot validate,
    and leaving it pending forever would wedge crash recovery."""
    stats = {"seen": 0, "invalid_envelope": 0, "blocked_cards": 0,
             "rule_off_skips": 0, "acked": 0}
    enabled = blocked_card_enabled(root)
    for rid, raw_fields in entries:
        stats["seen"] += 1
        fields = {k: str(raw_fields.get(k) or "") for k in _FIELDS}
        if not _valid_envelope(fields):
            stats["invalid_envelope"] += 1
            print(f"task-events-watch: WARN invalid/missing envelope on entry "
                  f"{rid} — skipped (names-only)", file=sys.stderr)
        elif fields["new_status"] == "blocked":
            if enabled:
                if file_blocked_card(fields, root=root, dry_run=dry_run,
                                     file_need_fn=file_need_fn) is not None:
                    stats["blocked_cards"] += 1
            else:
                stats["rule_off_skips"] += 1
        if not dry_run:
            _xack(rid)
            stats["acked"] += 1
    return stats


def run_once(*, dry_run: bool = False) -> dict:
    root = _root()
    _ensure_group()
    entries = _xreadgroup("0") + _xreadgroup(">")
    return process_entries(entries, root=root, dry_run=dry_run)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true",
                    help="one drain pass then exit (the only mode; explicit "
                         "for cron-line readability)")
    ap.add_argument("--dry-run", action="store_true",
                    help="judge only — no cards filed, nothing ACKed")
    args = ap.parse_args(argv)
    # --once is the only mode; the flag exists so cron lines read explicitly.
    _ = args.once
    stats = run_once(dry_run=args.dry_run)
    print(json.dumps(stats, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
