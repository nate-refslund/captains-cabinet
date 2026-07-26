"""framework.attention.feed — the P3 feed journal + cursor-based reads.

WHY (spec §4.3, Captain directive 2026-07-09): every send/edit the org makes
to the Captain is journaled at the transport layer to an append-only JSONL
so it CANNOT be skipped by any caller — the receipts, undo handles, dedup
data, and the whole learning loop are made of these rows (invariant-core
floor 2). The introspection primitive is deliberately CURSOR-BASED, never a
re-read: the Captain's standing directive is that the same rows are never
re-judged turn after turn, so every consumer (T2 dossier assembly,
comms-retro, gate dedup, briefing composer) carries its OWN durable cursor
(``FEED_DIR/cursors/<id>.txt``) and reads only what is NEW since it. Rows are
monotonically sequenced at append time (``seq``), so cursoring is exact,
replayable, and cheap regardless of feed size; a lost/corrupt cursor falls
back to a bounded tail (``recent_feed``) ONCE and re-anchors.

Storage conventions mirror the consequence ledger
(``framework/fidelity/consequence.py``) and the undo journal
(``framework/attention/acted_overlay.py``): one append-only file per UTC day
at ``$CABINET_FEED_DIR/feed-YYYY-MM-DD.jsonl``, ``json.dumps(row) + "\\n"``,
skip-garbage loaders. Read order is by ``seq`` (never by file/line order),
so a burned seq (crash between allocation and line-write) or an out-of-order
line is harmless. This is a RAW log primitive: identity-tuple supersession
(schema §7) is a consumer concern — the journal returns every row.

Failure bias is asymmetric and deliberate:
  * WRITES raise. A transport that cannot journal must be HEARD, not silent
    (§4.10 floor 2) — a swallowed append would blind every downstream loop.
  * READS are total. Garbage lines, non-dict rows, non-int ``seq``, and even
    an unreadable feed file are skipped silently — an introspection read must
    never crash the consumer that depends on it.

POSIX only (``fcntl.flock``): the deployment targets are mac-native and
Linux/Docker, never Windows.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

# Env override + generic default (no launcher literal — the clean-room ratchet
# scans framework/*; ``~/Library/...`` is the same durable per-user location the
# consequence ledger and undo journal already use, NOT /tmp which is wiped).
_FEED_DIR_ENV = "CABINET_FEED_DIR"
_FEED_DIR_DEFAULT = "~/Library/Application Support/cabinet/feed"

_DIRECTIONS = ("out", "in")

# Path-traversal fence for a consumer id: the id becomes a filename, so it may
# only contain characters that cannot escape the cursors/ dir. Anchored + one
# char minimum, so ``""``, ``".."``, ``"a/b"``, ``"../x"`` all fail closed.
_CONSUMER_ID_RE = re.compile(r"^[a-z0-9_-]+$")


def _feed_dir() -> Path:
    """Resolve the feed dir fresh on every call (no cache) so concurrent
    processes and env changes both see the same on-disk truth."""
    return Path(os.environ.get(_FEED_DIR_ENV) or
                os.path.expanduser(_FEED_DIR_DEFAULT))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_seq(value: object) -> bool:
    """A real integer seq — excludes bool, which is an int subclass in Python
    (a garbage row ``{"seq": true}`` must not read as seq 1)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _read_all_rows() -> list:
    """Every dict row across all feed files, unsorted. Total on garbage: a bad
    line, a non-dict row, or an unreadable file is skipped, never raised (a
    consumer's introspection read must not crash on a corrupt journal)."""
    d = _feed_dir()
    if not d.exists():
        return []
    rows: list = []
    for f in sorted(d.glob("feed-*.jsonl")):
        try:
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    if isinstance(r, dict):
                        rows.append(r)
        except OSError:
            continue  # unreadable file — skip; reads stay total (§4.10)
    return rows


def _max_feed_seq() -> int:
    """The highest seq durably present in the feed files (0 if none). The
    recovery source when seq.txt is missing/corrupt — the files are the
    record, so re-deriving from them can never re-issue a live seq."""
    return max((r["seq"] for r in _read_all_rows() if _is_seq(r.get("seq"))),
               default=0)


def _next_seq_and_write(feed_dir: Path, write_row) -> int:
    """Allocate the next monotonic seq AND run ``write_row(seq)`` while STILL
    holding the exclusive flock on ``seq.txt``.

    Holding the lock across the row write (review cp3 M2) closes the
    allocate-then-stall gap: with allocation-only locking, a writer that
    stalls between allocating seq N and appending its line lets seq N+1 land
    first — a cursor consumer then advances past N, and when N's line finally
    appears it is PERMANENTLY invisible to never-re-read cursors. Serializing
    the whole allocate+append keeps every published seq visible in order;
    contention is trivial at this channel's volume (~1 msg/sec ceiling).

    A corrupt/missing high-water is RE-DERIVED from the durable feed files
    (never restarted at 0 — that would re-issue live seqs). fsync makes the
    bump crash-durable, so seq.txt is always >= the max seq any line carries.
    A crash AFTER the seq bump but BEFORE the row write burns that seq — a
    harmless gap, never a duplicate or an invisible row."""
    seq_path = feed_dir / "seq.txt"
    fd = os.open(str(seq_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        raw = os.read(fd, 64)
        try:
            current = int(raw.strip())
        except ValueError:
            # empty (fresh/just-created), whitespace, or corrupt -> recover
            current = _max_feed_seq()
        nxt = current + 1
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        os.write(fd, str(nxt).encode("ascii"))
        os.fsync(fd)
        write_row(nxt)
        return nxt
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def append_event(row: dict) -> dict:
    """Stamp ``seq`` + ``ts`` onto ``row`` and append it to today's feed file.

    Validates the minimal shape (``direction`` in {out,in}; non-empty str
    ``kind``) and RAISES ValueError otherwise — journaling is a floor, so a
    malformed row is a caller bug that must be heard, not dropped. Every other
    key passes through untouched. ``ts`` is a UTC-ISO stamp unless the caller
    pre-set a truthy one. The returned dict is the exact stamped row written.

    Any I/O failure (unwritable dir, disk error) PROPAGATES — a transport that
    cannot journal must never silently succeed (§4.10 floor 2)."""
    if not isinstance(row, dict):
        raise ValueError(f"feed row must be a dict, got {type(row).__name__}")
    if row.get("direction") not in _DIRECTIONS:
        raise ValueError(
            f"feed row 'direction' must be one of {_DIRECTIONS}, "
            f"got {row.get('direction')!r}")
    kind = row.get("kind")
    if not (isinstance(kind, str) and kind):  # empty kind carries no routing
        raise ValueError(f"feed row 'kind' must be a non-empty str, got {kind!r}")

    stamped = dict(row)
    if not stamped.get("ts"):
        stamped["ts"] = _utc_now_iso()

    feed_dir = _feed_dir()
    feed_dir.mkdir(parents=True, exist_ok=True)

    log_file = feed_dir / ("feed-" + datetime.now(timezone.utc)
                           .strftime("%Y-%m-%d") + ".jsonl")

    def _write(seq: int) -> None:
        stamped["seq"] = seq
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(stamped, default=str) + "\n")

    # Allocation AND append happen under ONE flock (see _next_seq_and_write):
    # a published seq is therefore always immediately visible in order —
    # required by the never-re-read cursor contract.
    _next_seq_and_write(feed_dir, _write)
    return stamped


def feed_since(cursor: int, max_n: int = 200) -> "tuple[list, int]":
    """Rows with ``seq > cursor``, ordered by seq, capped at ``max_n``, plus
    the new cursor.

    The new cursor is the LAST RETURNED row's seq (so a capped batch resumes
    exactly at the next call), or the input ``cursor`` unchanged when nothing
    is new — the same rows are never re-read (Captain directive 2026-07-09)."""
    newer = sorted((r for r in _read_all_rows() if _is_seq(r.get("seq"))
                    and r["seq"] > cursor),
                   key=lambda r: r["seq"])
    capped = newer[:max_n] if max_n is not None and max_n >= 0 else newer
    new_cursor = capped[-1]["seq"] if capped else cursor
    return capped, new_cursor


def recent_feed(n: int = 50) -> list:
    """The last ``n`` rows by seq — ONLY for cursor re-anchoring after a
    missing/corrupt cursor (§4.3), not a general read path (that is
    ``feed_since``, which never re-reads)."""
    if n <= 0:
        return []
    rows = sorted((r for r in _read_all_rows() if _is_seq(r.get("seq"))),
                  key=lambda r: r["seq"])
    return rows[-n:]


def situation_key_for_message(telegram_message_id, *, scan_limit: int = 2000):
    """The ``situation_key`` of the OUTBOUND row this Telegram message id was
    sent as, or None.

    WHY THIS EXISTS (2026-07-26). The Captain's TAPS — inline-keyboard
    callbacks, message reactions, poll answers — were journaled with a
    ``telegram_message_id`` and no ``situation_key``: measured on the live
    feed, 0 of 21 taps carried one. So the only way to ask "what did he
    actually engage with?" was to join taps back to sends through the message
    id, and that join is lossy in practice — only 16 of those 21 taps matched
    an outbound row at all, and only 6 of the matches carried a situation_key
    to inherit. Every unmatched tap is a Captain action the org cannot
    attribute to anything.

    Stamping the key AT JOURNAL TIME makes the measurement durable: the join
    is resolved once, while the sending row is still findable, instead of
    being re-attempted forever against a feed that rolls.

    Read-only and total: any failure returns None, because a tap must be
    journaled whether or not it can be attributed. ``scan_limit`` bounds the
    work — the newest rows are scanned first, and a send the Captain is
    plausibly tapping is recent by construction.
    """
    try:
        mid = int(telegram_message_id)
    except (TypeError, ValueError):
        return None
    if not mid:
        return None
    try:
        rows = [r for r in _read_all_rows() if _is_seq(r.get("seq"))]
    except Exception:
        return None
    rows.sort(key=lambda r: r["seq"], reverse=True)
    for row in rows[:max(0, int(scan_limit))]:
        if row.get("direction") != "out":
            continue
        if row.get("telegram_message_id") != mid:
            continue
        key = row.get("situation_key")
        if key:
            return key
        # An outbound row matched but carries no key: that send genuinely had
        # no situation identity, so neither does the tap. Stop — a further
        # match on the same id would be an edit of the same message.
        return None
    return None


def _cursor_path(consumer_id: str) -> Path:
    """The cursor file for ``consumer_id``, with the traversal fence enforced —
    the id is a filename component, so anything outside ``[a-z0-9_-]`` (dots,
    slashes, whitespace, empties) is refused before it can escape cursors/."""
    if not (isinstance(consumer_id, str) and _CONSUMER_ID_RE.match(consumer_id)):
        raise ValueError(
            f"consumer_id must match [a-z0-9_-]+ (path-traversal fence), "
            f"got {consumer_id!r}")
    return _feed_dir() / "cursors" / (consumer_id + ".txt")


def load_cursor(consumer_id: str) -> int:
    """The consumer's last-consumed seq, or 0 when absent OR corrupt — a
    missing/garbled cursor fails safe to 0 so the caller re-anchors from a
    bounded ``recent_feed`` tail rather than crashing (§4.3)."""
    path = _cursor_path(consumer_id)  # raises on a traversal-unsafe id
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0


def store_cursor(consumer_id: str, seq: int) -> None:
    """Persist the consumer's cursor atomically (temp + os.replace) so a
    concurrent ``load_cursor`` never observes a half-written value."""
    path = _cursor_path(consumer_id)  # raises on a traversal-unsafe id
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f"{path.name}.{os.getpid()}.tmp"
    tmp.write_text(str(int(seq)), encoding="utf-8")
    os.replace(tmp, path)
