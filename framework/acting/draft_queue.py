"""framework.acting.draft_queue — withdraw / supersede on the queued-draft path.

THE GAP THIS CLOSES (captain-surface master prompt §3.6, 2026-07-10): the draft
queue had NO withdraw path — once a draft was presented and stored
(``cabinet:draft:<id>``), a stale draft could only be left untapped, which is
the root of the worked Casey confusion (the captain replied himself and the
queued draft kept dangling, ready to fire). This module is the foundation
primitive the safety rails share:

  * ``withdraw(id, reason)``   — remove a queued draft with an honest reason.
  * ``supersede(old, new)``    — withdraw an old draft in favor of a newer one.
  * ``withdrawal_of(id)``      — why a draft is gone (so a later 'send' tap gets
                                 the real reason, never a generic miss).
  * ``pending()``              — the queued-draft records still awaiting fire.
  * ``journal_fire_cancel(..)``— the verify-at-fire gate's cancel record
                                 (``framework.acting.fire_gate``).

Every removal is journaled append-only (JSONL, flock-serialized, user-only
file perms) and the journal row retains the FULL record — that is the undo
trail: a wrongly-withdrawn draft can be re-queued verbatim from its row.

Store: the queued-draft records live in Redis under ``cabinet:draft:<id>``
(written by ``chair_drafts.present_draft`` and ``run_draft_lane._store_draft``).
Redis access is an injectable KV (``kv=``) so tests run against a dict-backed
fake; the default is the repo's dependency-light ``redis-cli`` argv-list
subprocess (never a shell string). Launcher-neutral: no captain name, no
absolute home literal — the journal dir resolves from
``CABINET_DRAFT_QUEUE_DIR`` else ``~/Library/Application Support/cabinet/drafts``.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# Draft ids are short hex/word tokens minted by the writers (sha1[:6] /
# proposal ids). Validate before any id reaches a Redis key or a journal row —
# fail-closed on anything else (Corridor: allow-list inputs used in key
# construction).
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

_KEY_PREFIX = "cabinet:draft:"

_JOURNAL_NAME = "draft-queue-journal.jsonl"


def valid_id(pid: str) -> bool:
    return bool(pid) and bool(_ID_RE.match(str(pid)))


# ---------------------------------------------------------------------------
# KV — injectable Redis layer (argv-list redis-cli by default; tests inject a
# dict-backed fake with the same three methods).
# ---------------------------------------------------------------------------

class RedisKV:
    """The default live store: ``redis-cli`` subprocess per verb (argv list,
    no shell), same dependency-light pattern as ``chair_drafts._r``. Any
    subprocess failure degrades to empty/none — the callers treat that as
    "nothing queued", never a crash."""

    def __init__(self, host: "str | None" = None):
        self.host = host or os.environ.get("REDIS_HOST", "localhost")

    def _run(self, *args: str) -> str:
        try:
            return subprocess.run(
                ["redis-cli", "-h", self.host, *args],
                capture_output=True, text=True, timeout=10,
            ).stdout.strip()
        except Exception:
            return ""

    def get(self, key: str) -> "str | None":
        out = self._run("GET", key)
        return out or None

    def delete(self, key: str) -> None:
        self._run("DEL", key)

    def keys(self, prefix: str) -> list:
        try:
            out = subprocess.run(
                ["redis-cli", "-h", self.host, "--scan",
                 "--pattern", prefix + "*"],
                capture_output=True, text=True, timeout=15,
            ).stdout
        except Exception:
            return []
        return [ln.strip() for ln in out.splitlines() if ln.strip()]


def _kv(kv=None):
    return kv if kv is not None else RedisKV()


# ---------------------------------------------------------------------------
# Journal — append-only JSONL, flock-serialized, user-only perms
# ---------------------------------------------------------------------------

def journal_dir() -> Path:
    return Path(os.environ.get("CABINET_DRAFT_QUEUE_DIR") or
                os.path.expanduser("~/Library/Application Support/cabinet/drafts"))


def journal_path() -> Path:
    return journal_dir() / _JOURNAL_NAME


def _now_iso(now: "datetime | None" = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append(row: dict) -> None:
    """flock-serialized append of one JSON line. Draft rows carry private
    message content, so the dir is 0700 and the file 0600 (user-only)."""
    d = journal_dir()
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    fd = os.open(str(journal_path()),
                 os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.write(fd, (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def journal_rows(limit: int = 1000) -> list:
    """The most recent journal rows (oldest→newest within the tail). A missing
    or partially-corrupt journal returns what parses — honest best-effort."""
    p = journal_path()
    if not p.exists():
        return []
    rows = []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for ln in lines[-int(limit):]:
        try:
            row = json.loads(ln)
        except (ValueError, TypeError):
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def withdrawal_of(pid: str, limit: int = 2000) -> "dict | None":
    """The most recent removal row for ``pid`` (withdraw / supersede /
    fire-cancel), or None. This is how a later 'send' tap on a gone draft gets
    the honest reason instead of a generic miss."""
    if not valid_id(pid):
        return None
    for row in reversed(journal_rows(limit=limit)):
        if row.get("pid") == pid and row.get("kind") in (
                "withdraw", "supersede", "fire-cancel"):
            return row
    return None


# ---------------------------------------------------------------------------
# The primitive — withdraw / supersede / pending
# ---------------------------------------------------------------------------

def withdraw(pid: str, reason: str, *, actor: str = "system",
             superseded_by: "str | None" = None, kv=None,
             now: "datetime | None" = None) -> dict:
    """Remove a queued draft with an honest reason. Journals the FULL record
    (the undo trail) before returning. ``superseded_by`` links the newer draft
    id when this withdraw is a supersede.

    Returns ``{"ok": True, ...}`` on removal; ``{"ok": False, "error": ...}``
    when the id is invalid or nothing is queued under it (idempotent — a
    second withdraw of the same id reports the prior row, removes nothing)."""
    if not valid_id(pid):
        return {"ok": False, "error": "invalid draft id"}
    if superseded_by is not None and not valid_id(superseded_by):
        return {"ok": False, "error": "invalid superseding draft id"}
    store = _kv(kv)
    raw = store.get(_KEY_PREFIX + pid)
    if not raw:
        prior = withdrawal_of(pid)
        if prior:
            return {"ok": False, "already_withdrawn": True,
                    "error": f"draft {pid} was already withdrawn",
                    "prior": {"kind": prior.get("kind"),
                              "reason": prior.get("reason"),
                              "ts": prior.get("ts")}}
        return {"ok": False, "error": f"no queued draft {pid}"}
    try:
        record = json.loads(raw)
        if not isinstance(record, dict):
            record = {"_raw": raw}
    except (ValueError, TypeError):
        record = {"_raw": raw}
    store.delete(_KEY_PREFIX + pid)
    kind = "supersede" if superseded_by else "withdraw"
    row = {"kind": kind, "ts": _now_iso(now), "pid": pid,
           "reason": str(reason or "").strip() or "withdrawn",
           "actor": actor, "superseded_by": superseded_by, "record": record}
    _append(row)
    return {"ok": True, "pid": pid, "kind": kind, "reason": row["reason"],
            "superseded_by": superseded_by}


def supersede(old_pid: str, new_pid: str, reason: str = "", *,
              actor: str = "system", kv=None,
              now: "datetime | None" = None) -> dict:
    """Withdraw ``old_pid`` in favor of ``new_pid`` (a fresher draft for the
    same thread). The journal row links both ids."""
    return withdraw(old_pid,
                    reason or "replaced by a newer draft",
                    actor=actor, superseded_by=new_pid, kv=kv, now=now)


def journal_fire_cancel(pid: str, record: dict, verdict: dict,
                        now: "datetime | None" = None) -> None:
    """Journal a verify-at-fire self-cancel (the caller already removed the
    record from the store — this is the audit row). ``verdict`` is the
    ``fire_gate.verify_at_fire`` result."""
    if not valid_id(pid):
        pid = ""
    _append({"kind": "fire-cancel", "ts": _now_iso(now), "pid": pid,
             "reason": (verdict or {}).get("reason") or "cancelled-at-fire",
             "captain_reason": (verdict or {}).get("captain_reason") or "",
             "checks": (verdict or {}).get("checks") or {},
             "actor": "fire-gate",
             "superseded_by": None,
             "record": record if isinstance(record, dict) else {}})


def pending(kv=None, limit: int = 500) -> list:
    """The queued-draft records still in the store, each as
    ``{"pid": <id>, ...record fields...}``. Unparseable records are skipped
    (honest best-effort — never a crash, never a fabricated row)."""
    store = _kv(kv)
    out = []
    for key in store.keys(_KEY_PREFIX)[: int(limit)]:
        pid = key[len(_KEY_PREFIX):] if key.startswith(_KEY_PREFIX) else key
        if not valid_id(pid):
            continue
        raw = store.get(key)
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if isinstance(rec, dict):
            out.append({"pid": pid, **rec})
    return out
