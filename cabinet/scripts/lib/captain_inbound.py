"""captain_inbound.py — READ side of the durable captain-inbound archive.

WRITE side: cabinet/scripts/officer-inbound-poller.py::archive_captain_dm
appends every relayed Captain utterance VERBATIM, one JSON row per line, to
UTC day files ``inbound-YYYY-MM-DD.jsonl`` under CABINET_CAPTAIN_INBOUND_DIR
(default ``~/Library/Application Support/cabinet/captain-inbound``). This
module is the matching reader. The 30-entry redis ring truncates to 280
chars and forgets (8 of 26 traced Captain messages were unrecoverable
verbatim by 2026-07-16) — so anything that needs what the Captain actually
said (the case ledger, attention-metric denominators, the Chair resolving
an earlier message) reads from HERE, never the ring.

Row schema v1 (pinned by cabinet/scripts/tests/
test_inbound_poller_inbound_archive.py): v, dm_id (``tg-<chat>-<mid>``),
chat_id, message_id, update_id, officer, kind (text|file|file-error|
onboarding), text (verbatim), quoted (verbatim), file_kind, file_name,
tg_date, ts.

Contracts this reader honours (poller header + write-side pins):

* DUPLICATES ARE NORMAL: the poller re-delivers a whole update after a
  crash-mid-deliver restart, so a dm_id MAY appear twice (content
  verbatim-identical by contract; the append-time ``ts`` can differ).
  Readers dedup by dm_id, LAST occurrence wins — for both the row kept
  and its position in recency orderings.
* TOTAL ON GARBAGE (the attention feed's loader discipline,
  framework/attention/feed.py::_read_all_rows): a corrupt line, a
  non-dict row, a row without a dm_id, or an unreadable file is skipped,
  never raised — an introspection read must not crash on a damaged
  journal.
* READ-ONLY: nothing in this module ever writes the archive.

SEMANTIC twin: cabinet/scripts/hooks/capture-captain-dm.sh queues the same
utterances to the cabinet_memory embed pipeline with
``source_id = tg-<chat_id>-<message_id>`` — byte-identical to this
archive's dm_id. ``semantic_search`` therefore shells out to the existing
cabinet/scripts/search-memory.sh entrypoint (embeddings are NEVER
reimplemented here) and joins result refs back to archive rows: memory
previews are LEFT(…,200)-truncated and whitespace-flattened, while this
archive is the untruncated truth, so the join is what restores verbatim.

Stdlib-only and py3.9-safe on purpose (no match/case, no X|Y unions at
runtime): officer boxes and the Docker CI image run the system python3.
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
from typing import Iterable, Iterator, Optional


def archive_dir() -> str:
    """The archive dir, resolved FRESH on every call (no cache) — same
    env-override contract as the writer's ``captain_inbound_archive_dir``
    and the feed/events/undo family, and the same reason: concurrent
    processes, tests (monkeypatch.setenv), and the repo-root conftest fence
    must all see the same on-disk truth the moment the env changes."""
    return os.environ.get("CABINET_CAPTAIN_INBOUND_DIR") or os.path.expanduser(
        "~/Library/Application Support/cabinet/captain-inbound")


def iter_rows(days=None) -> Iterator[dict]:
    """Yield parsed rows oldest→newest across day files.

    ``days``: an int restricts the read to the N most recent day files —
    day-file names are zero-padded ISO dates, so lexicographic file order
    IS chronological order and a tail slice is the cheap recency window.
    None reads everything; days <= 0 reads nothing.

    Raw stream: duplicates from crash-replay are yielded as-is (callers
    that want one-row-per-utterance go through ``latest``/``get``/
    ``search``, which dedup). Garbage tolerance per the module contract:
    blank/corrupt lines, non-dict rows, rows without a string dm_id, and
    unreadable files are skipped silently."""
    d = archive_dir()
    files = sorted(glob.glob(os.path.join(d, "inbound-*.jsonl")))
    if days is not None:
        n_files = int(days)
        files = files[-n_files:] if n_files > 0 else []
    for path in files:
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    if isinstance(row, dict) and isinstance(
                            row.get("dm_id"), str) and row["dm_id"]:
                        yield row
        except OSError:
            continue  # unreadable file — skip; reads stay total


def _dedup_rows(days=None) -> "dict[str, dict]":
    """Rows keyed by dm_id in append order, LAST occurrence winning both
    the value AND the position (pop-then-reinsert): a crash-replayed row
    re-ranks its dm at the replay position, so recency orderings follow
    the last physical append — the one observable difference duplicates
    can carry (their content is identical by contract, their append-time
    ``ts`` and file position are not)."""
    out = {}  # type: dict
    for row in iter_rows(days=days):
        out.pop(row["dm_id"], None)
        out[row["dm_id"]] = row
    return out


def _kind_set(kinds) -> Optional[set]:
    """Normalize a kinds filter: None (no filter), a single string, an
    iterable of strings — each value may itself be comma-separated (the
    CLI's repeatable ``--kind`` flag feeds through here unchanged)."""
    if kinds is None:
        return None
    if isinstance(kinds, str):
        kinds = [kinds]
    out = set()
    for k in kinds:
        for part in str(k).split(","):
            part = part.strip()
            if part:
                out.add(part)
    return out or None


def latest(n=30, kinds=None) -> "list[dict]":
    """The newest ``n`` archive rows, NEWEST FIRST, deduped by dm_id (last
    occurrence wins), optionally filtered to ``kinds`` (see ``_kind_set``
    for accepted shapes). The kind filter runs after dedup — replayed
    duplicates are verbatim-identical, so the order can't matter."""
    if n is None:
        n = 30
    n = int(n)
    if n <= 0:
        return []
    ks = _kind_set(kinds)
    rows = [r for r in _dedup_rows().values()
            if ks is None or r.get("kind") in ks]
    return rows[-n:][::-1]


def get(dm_id) -> Optional[dict]:
    """The archive row for ``dm_id`` (last occurrence wins), or None.

    Accepts BOTH id forms:

    * full ``tg-<chat>-<mid>`` — exact dm_id match;
    * a bare integer message_id (int or digit string) — message_id is
      CHAT-SCOPED in Telegram, so a bare mid can legitimately exist in
      several chats. Unambiguous → that row. Ambiguous → the NEWEST
      matching row (by archive order) with an extra ``"matches"`` key
      listing EVERY matching row newest-first (the newest itself
      included, so the list is the complete candidate set). ``matches``
      is present ONLY on ambiguity — ``"matches" in row`` is the
      caller's ambiguity test — and lives on a copy, never on the row
      other lookups return.

    Anything else (None, non-numeric junk) → None, never a raise."""
    if dm_id is None:
        return None
    s = str(dm_id).strip()
    rows = _dedup_rows()
    if s.startswith("tg-"):
        return rows.get(s)
    try:
        mid = int(s, 10)
    except ValueError:
        return None
    matches = [r for r in rows.values() if r.get("message_id") == mid]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    newest = dict(matches[-1])
    newest["matches"] = matches[::-1]
    return newest


def search(query, n=20, kinds=None) -> "list[dict]":
    """Lexical search: case-insensitive ALL-terms match over text + quoted
    + file_name, NEWEST FIRST, deduped, capped at ``n``.

    ``query`` splits on whitespace into independent terms; every term must
    appear (substring) somewhere across the three fields. An empty/blank
    query returns [] — "match everything" is ``latest``'s job, and a
    caller passing an empty query is almost always a bug upstream.
    ``kinds`` filters like ``latest``. For meaning-not-wording recall use
    ``semantic_search``."""
    terms = [t for t in str(query or "").lower().split() if t]
    if not terms:
        return []
    n = int(n)
    if n <= 0:
        return []
    ks = _kind_set(kinds)
    out = []
    for row in reversed(_dedup_rows().values()):
        if ks is not None and row.get("kind") not in ks:
            continue
        hay = "\n".join((str(row.get("text") or ""),
                         str(row.get("quoted") or ""),
                         str(row.get("file_name") or ""))).lower()
        if all(t in hay for t in terms):
            out.append(row)
            if len(out) >= n:
                break
    return out


# ── semantic layer (join against cabinet_memory via search-memory.sh) ────────

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

# One result-header line as search-memory.sh prints it:
#   [trust:%s] [%s] %s by %s @ %s (sim: %s, score: %s)
# followed by two-space-indented preview line(s). officer/when are
# non-greedy: memory officers are slugs (cos, captain) and when_at is
# "YYYY-MM-DD HH:MM", so the anchored " (sim: " tail disambiguates.
_HIT_RE = re.compile(
    r"^\[trust:(?P<trust>[^\]]*)\] \[(?P<source_type>[^\]]*)\] "
    r"(?P<ref>\S+) by (?P<officer>.*?) @ (?P<when_at>.*?) "
    r"\(sim: (?P<similarity>[^,]*), score: (?P<score>[^)]*)\)$")

# The archive dm_id shape, EXACTLY: tg-<chat>-<mid> with a numeric
# (possibly negative — Telegram group chats) chat id and numeric mid.
# CRITICAL narrowness: the telegram_dm memory type ALSO carries officer
# OUTBOUND replies (post-reply-memory.sh, ref tg-out-<ts>-<officer>) and an
# id-less inbound fallback (capture-captain-dm.sh, tg-in-<ts>-<officer>).
# A prefix check would label those as Captain dm_ids — misattributing
# OFFICER speech as Captain speech, the precise failure this archive
# exists to kill.
_DM_ID_RE = re.compile(r"tg--?\d+-\d+\Z")


def memory_search_entrypoint() -> str:
    """Path to the memory search entrypoint — CABINET_MEMORY_SEARCH_SH env
    override first (tests point it at stubs/nonexistent paths; a future
    packaging move can re-home it without touching callers), else the
    repo-relative cabinet/scripts/search-memory.sh next to this lib."""
    return os.environ.get("CABINET_MEMORY_SEARCH_SH") or os.path.join(
        _REPO_ROOT, "cabinet", "scripts", "search-memory.sh")


def _parse_memory_search_output(stdout: str) -> "list[dict]":
    """search-memory.sh's human output → structured hits. Tolerant: lines
    that aren't a hit header or its indented preview are ignored (the
    header banner, Type:/Officer: echo lines, "No results found.")."""
    hits = []
    for line in (stdout or "").splitlines():
        m = _HIT_RE.match(line)
        if m:
            hit = m.groupdict()
            hit["preview"] = ""
            hits.append(hit)
        elif hits and line.startswith("  "):
            prev = hits[-1]["preview"]
            prev = (prev + " " + line.strip()).strip() if prev else line.strip()
            hits[-1]["preview"] = prev
    return hits


def semantic_search(query, n=10, timeout=15.0) -> dict:
    """Meaning-level recall over Captain inbound: shell out to the memory
    search entrypoint (``--type telegram_dm`` — the source_type
    capture-captain-dm.sh ingests Captain DMs under), parse its output,
    and JOIN each hit whose ref is an archive dm_id back to the verbatim
    archive row.

    Returns a dict, NEVER raises (given sane argument types):

    * available — False when the ENTRYPOINT is absent/broken (missing
      file, spawn failure, timeout, non-zero exit, or recognizable
      output-format drift), with a ``reason`` string; True means the
      entrypoint ran and printed its zero-or-hits output. HONEST LIMIT:
      True does NOT prove the memory DB was reachable — the entrypoint
      discards psql stderr and prints "No results found." + exit 0 on a
      dead DB, indistinguishable from a genuine zero. ``stderr_tail``
      (last stderr lines, e.g. the embedding-degrade WARN) is surfaced
      on every available=True result so that signal is never eaten.
    * results — hit dicts: trust, source_type, ref, officer, when_at,
      similarity, score, preview (all strings, as printed), plus
      ``dm_id`` (the ref ONLY when it has the exact archive shape
      ``tg-<numeric chat>-<numeric mid>``, else "" — telegram_dm rows
      also include OFFICER outbound replies ref'd ``tg-out-…`` and
      id-less inbound fallbacks ``tg-in-…``, which are NOT Captain
      utterances) and ``archive`` (the verbatim archive row, or None —
      None with a real dm_id means the memory row predates the
      archive).

    The subprocess budget defaults far above pre-captain-dm.sh's 2s hook
    budget: this is offline tooling, and Neon cold-resume alone can eat
    seconds. Embeddings/SQL stay entirely inside the entrypoint — this
    function only parses and joins."""
    q = str(query or "").strip()
    if not q:
        return {"available": False, "query": q,
                "reason": "empty query", "results": []}
    limit = max(1, int(n))
    entry = memory_search_entrypoint()
    if not os.path.isfile(entry):
        return {"available": False, "query": q,
                "reason": "memory search entrypoint not found: %s" % entry,
                "results": []}
    # Query passed LAST as one argv element (no shell), mirroring the
    # pre-captain-dm.sh call shape into the same parser.
    cmd = ["bash", entry, "--type", "telegram_dm", "--limit", str(limit), q]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"available": False, "query": q,
                "reason": "memory search timed out after %.1fs" % timeout,
                "results": []}
    except Exception as exc:  # spawn failure — degrade, never raise
        return {"available": False, "query": q,
                "reason": "memory search failed to run (%s: %s)"
                          % (type(exc).__name__, exc),
                "results": []}
    if proc.returncode != 0:
        err_lines = (proc.stderr or "").strip().splitlines()
        reason = "memory search exited %d" % proc.returncode
        if err_lines:
            reason += ": " + err_lines[-1]
        return {"available": False, "query": q,
                "reason": reason, "results": []}
    hits = _parse_memory_search_output(proc.stdout)[:limit]
    stdout = proc.stdout or ""
    if (not hits and "=== Cabinet Memory Search" in stdout
            and "No results found." not in stdout):
        # The entrypoint prints its banner ONLY when hits exist — a banner
        # with zero parsed hits and no explicit no-results line means OUR
        # parser no longer matches the output format. Degrade loudly
        # instead of returning a silent (false) empty.
        return {"available": False, "query": q,
                "reason": "output format drift: banner present but no "
                          "hit lines parsed", "results": []}
    by_id = _dedup_rows()  # one archive pass joins every hit
    for hit in hits:
        ref = hit.get("ref") or ""
        hit["dm_id"] = ref if _DM_ID_RE.match(ref) else ""
        hit["archive"] = by_id.get(ref) if hit["dm_id"] else None
    err_lines = (proc.stderr or "").strip().splitlines()
    return {"available": True, "query": q, "results": hits,
            "stderr_tail": err_lines[-3:]}
