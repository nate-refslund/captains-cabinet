"""framework/sources/org.py — the ORG (Flavor-B / clean-room) PersonalSource.

``OrgSource`` gives an org deployment REAL query-driven recall where the null
adapter has none: on a clean-room box with no screenpipe, no vault and no
``instance/flavor-a`` tree, everything previously fail-closed to
``NullPersonalSource`` and the draft/brief lanes (``run_draft_lane``,
``morning_synthesis``, the fidelity ``officer_runner``) got zero hits from
``get_source().search()``. This adapter backs ``search()`` with the CABINET's
own memory estate — the ``cabinet_memory`` pgvector table — via the exact same
embedding + query path ``cabinet/scripts/search-memory.sh`` uses
(``cabinet/scripts/lib/memory.sh`` → ``memory_get_embedding`` → ``psql -v``
parameterized SELECT), so there is ONE Voyage client and ONE ranking, not a
second Python re-implementation.

Everything the org box does NOT have stays an HONEST empty, mirroring
``null.py`` semantics method-for-method: no person dossiers, no
voice/patterns priors, no vault notes (``read_note`` raises), tri-state probes
return ``None`` (honest unknown). The adapter never pretends a capability —
``search()``, ``available()`` and (since W7 2026-07-09) ``open_commitments()``
are live: the org's open commitments are its Captain-ratified ACTIVE outcomes
(``instance/config/outcomes.yml``, direction ``owed_to_captain``) — real
config, read-only, so the CG-2 gather seam's per-commitment recall fires on
org deployments instead of running the decision path memory-blind.

Backend contract (defensive by design — the search-memory surface is being
upgraded in parallel):
  * subprocess with ``shell=False``: ``bash -c '<fixed snippet>' <name> <argv…>``
    — the query/types/limit/min-score travel ONLY as positional parameters
    (``$1``–``$5``), never string-interpolated; ``memory.sh`` passes them
    onward via ``psql -v`` and ``jq --arg`` (parameterized end-to-end).
  * fail-closed env: if ``NEON_CONNECTION_STRING`` is neither in the process
    env nor NAMED in ``<root>/cabinet/.env`` (checked by variable NAME only —
    the value is never read into logs or output), ``search()`` returns the
    honest empty without spawning anything, and ``available()`` is ``False``.
  * defensive output parse: ``memory_search`` emits TSV rows — the HYBRID
    (2026-07-07) 8-column layout ``source_type / who / when_at / similarity /
    score / trust / preview / ref`` or the legacy 6-column layout without
    ``score``/``trust``; BOTH parse (the upgrade landed in parallel with this
    adapter, and an org box may carry either). Malformed rows and the
    ``Embedding failed`` sentinel are skipped, never raised. The hybrid
    backend accepts a comma-separated source_type list natively, so
    multi-type search is ONE query (one embedding), not a fan-out.
  * a hit maps to the shape the framework callers consume
    (``officer_runner._content_ts`` / ``leakguard`` fencing):
    ``{source, ref, text, base_score, who, ts, content_ts}`` (+ ``similarity``
    / ``trust`` observability extras on hybrid rows) — ``base_score`` is the
    backend's RANKING score (blended ``score`` on hybrid rows, vector
    similarity on legacy rows); ``content_ts`` is ISO-8601 when derivable
    from the row, else ``None`` (honest un-fenceable → the leak fence
    excludes it; NEVER a fabricated timestamp).

Env knobs (all optional):
  * ``CABINET_ORG_MEMORY_TYPES`` — comma-separated ``cabinet_memory``
    source_type filters (e.g. ``captain_decision,product_spec``), normalized
    and passed through as ONE backend filter list; results deduped by
    ``(source, ref)`` and ranked by ``base_score``. Empty/absent ⇒ unfiltered.
  * ``CABINET_ORG_SEARCH_LIMIT`` — result cap (default 10).
  * ``CABINET_ORG_MIN_SCORE`` — passed through as the backend ``min_score``
    (vector-similarity floor; unset ⇒ the backend's own default) AND applied
    client-side to ``base_score`` (unset ⇒ 0.0, no client floor).

``library_records`` is deliberately NOT queried here: it has no shared shell
query path to reuse, and duplicating a second ranked SQL surface in this
adapter would violate the one-client rule above — fold it in when the
search-memory upgrade exposes it.

LAYER SEP: stdlib only, no screenpipe/_shared import, no bare quoted instance
token — this module lives in the FRAMEWORK tree (it senses cabinet-owned data,
not any launcher's personal estate) and is bound, like every adapter, only as
DATA via ``instance/config/sources.yml`` → ``get_source()``.

py3.9-compatible (``from __future__ import annotations``, ``typing.Optional``,
no ``match``/``case``).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

# The FIXED backend snippet — a constant, never built from untrusted text. The
# query / source_type(s) / officer-filter / limit / min-score arrive as bash
# positional parameters ($1–$5) from the subprocess argv list; CABINET_ROOT is
# set in the child env from the framework's own root resolver (trusted path,
# not input). An empty $5 lets memory_search's own ${5:-default} apply (the
# legacy 4-arg memory_search simply ignores the extra parameter).
_MEMORY_SEARCH_SNIPPET = (
    'source "$CABINET_ROOT/cabinet/scripts/lib/memory.sh" '
    '&& memory_search "$1" "$2" "$3" "$4" "$5"'
)

_SUBPROCESS_TIMEOUT = 60          # seconds — mirrors the flavor-a vault sidecar
_DEFAULT_LIMIT = 10

# memory_search's when_at column: to_char(source_created_at,'YYYY-MM-DD HH24:MI')
# rendered in the DB session timezone (Neon default UTC).
_WHEN_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")


def _cabinet_root() -> Path:
    """The deployment root — ``CABINET_ROOT`` env, else this file's repo root
    (``framework/sources/org.py`` → ``parents[2]``). Mirrors the resolver's
    ``_cabinet_root`` (no hardcoded absolute path)."""
    return Path(os.environ.get("CABINET_ROOT") or str(Path(__file__).resolve().parents[2]))


def _neon_configured(root: Path) -> bool:
    """Is the memory backend reachable in principle — ``NEON_CONNECTION_STRING``
    present in the process env, or NAMED in ``<root>/cabinet/.env`` (the file
    ``memory.sh`` itself sources)? Checked by variable NAME only; the secret
    VALUE is never captured, stored, or logged by this module."""
    if os.environ.get("NEON_CONNECTION_STRING"):
        return True
    env_file = root / "cabinet/.env"
    try:
        if not env_file.is_file():
            return False
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if stripped.startswith("NEON_CONNECTION_STRING=") \
                    or stripped.startswith("export NEON_CONNECTION_STRING="):
                return True
    except OSError:
        return False
    return False


def _iso_from_when_at(when_at: str) -> Optional[str]:
    """``"YYYY-MM-DD HH:MM"`` → ISO-8601 ``"YYYY-MM-DDTHH:MM:00+00:00"`` (the
    session timezone is UTC on the Neon default this row was rendered in), or
    ``None`` when the field does not look like that clock — an honest absence:
    the caller leaves ``content_ts=None`` and the leak fence EXCLUDES the hit
    rather than fencing it on a fabricated timestamp."""
    w = (when_at or "").strip()
    if not _WHEN_AT_RE.match(w):
        return None
    return w.replace(" ", "T") + ":00+00:00"


def _float_or(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except ValueError:
        return default


def _parse_rows(stdout: Optional[str]) -> List[dict]:
    """Defensively parse ``memory_search`` TSV output into framework hit dicts.

    Accepts BOTH row layouts (one row per line; preview is tab/newline-stripped
    by the SQL, so field counts are stable):
      * HYBRID (8 cols, 2026-07-07): ``source_type / who / when_at /
        similarity / score / trust / preview / ref`` — ``base_score`` = the
        blended ranking ``score``; ``similarity`` + ``trust`` kept as extras.
      * legacy (6 cols): ``source_type / who / when_at / similarity /
        preview / ref`` — ``base_score`` = ``similarity``.
    Skips blank lines, the ``Embedding failed`` sentinel, and any row with
    fewer than six fields. Never raises."""
    if not stdout:
        return []
    hits: List[dict] = []
    for line in stdout.splitlines():
        if not line.strip() or line.startswith("Embedding failed"):
            continue
        fields = line.split("\t")
        if len(fields) >= 8:      # hybrid layout
            source_type, who, when_at, similarity, score, trust, preview, ref = fields[:8]
            extras = {"similarity": _float_or(similarity),
                      "trust": trust.strip()}
            base_score = _float_or(score)
        elif len(fields) >= 6:    # legacy layout
            source_type, who, when_at, similarity, preview, ref = fields[:6]
            extras = {}
            base_score = _float_or(similarity)
        else:
            continue
        iso = _iso_from_when_at(when_at)
        hit = {
            "source": source_type.strip() or "cabinet_memory",
            "ref": ref.strip(),
            "text": preview,
            "base_score": base_score,
            "who": who.strip(),
            "ts": iso,           # same clock as content_ts (no wrong-clock mtime here)
            "content_ts": iso,   # ISO or honest None (un-fenceable ⇒ excluded)
        }
        hit.update(extras)
        hits.append(hit)
    return hits


def _run_memory_search(query: str, source_types: str, limit: int,
                       min_score: str = "") -> Optional[str]:
    """Shell to ``memory_search`` (via ``memory.sh``) and return its raw stdout,
    or ``None`` on any failure. ``shell=False``; untrusted text travels only in
    the argv list (bash positional parameters), never in the snippet.
    ``source_types`` may be a comma-separated list (hybrid backend contract);
    ``min_score`` empty ⇒ the backend's own default floor."""
    root = _cabinet_root()
    lib = root / "cabinet/scripts/lib/memory.sh"
    if not lib.is_file():
        return None
    try:
        proc = subprocess.run(
            ["bash", "-c", _MEMORY_SEARCH_SNIPPET, "orgsource-memory-search",
             query, source_types, "", str(int(limit)), min_score],
            capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT,
            env={**os.environ, "CABINET_ROOT": str(root)},
        )
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        sys.stderr.write("[org-source] memory_search subprocess failed: %s\n" % e)
        return None
    # memory_search exits 1 on embedding outage but still prints its sentinel;
    # parse whatever stdout there is — _parse_rows skips the sentinel.
    return proc.stdout or ""


def _lane_from_outcome_id(oid: str) -> str:
    """Best-effort lane from an ``outcome-<lane>-NNN`` id (e.g.
    ``outcome-polads-001`` → ``polads``); empty when the id has another
    shape — the caller falls back to the id itself, never fabricates."""
    m = re.match(r"^outcome-(.+)-\d+$", oid)
    return m.group(1) if m else ""


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


class OrgSource:
    """Org-deployment ``PersonalSource``: real ``search()`` over the cabinet's
    own memory estate (``cabinet_memory`` pgvector), honest ``null.py``-mirror
    empties for every personal-estate capability an org box does not have.
    Structurally satisfies ``base.PersonalSource`` (``runtime_checkable``)
    without importing it. Zero-arg constructible (the ``sources.yml`` /
    ``get_source()`` contract); the backend runner is injectable for tests."""

    def __init__(self, run_search=None):
        # Injectable backend seam (tests): callable(query, source_types_csv,
        # limit, min_score_str) -> raw memory_search stdout or None. Default:
        # the real subprocess.
        self._run_search = run_search or _run_memory_search

    # --- liveness -----------------------------------------------------------
    def available(self) -> bool:
        """Cheap config-presence probe — ``True`` iff the memory backend is
        configured (env-name check only, no network, no subprocess)."""
        return _neon_configured(_cabinet_root())

    # --- OBSERVE / SEARCH (the one live capability) --------------------------
    def search(self, handle: str, *, topic: Optional[str] = None) -> dict:
        """Ranked cabinet-memory retrieval for ``handle`` (topic-prepended when
        given, so retrieval is driven by what the message is ABOUT, anchored to
        the handle — same ordering rationale as the Flavor-A vault gather).
        Returns the framework hit contract ``{"hits": [...], "topic_terms":
        None}``; fail-closed empty on missing backend config, empty/NUL query,
        or ANY backend failure. ``topic_terms`` is honestly ``None`` — this
        adapter runs no term extractor."""
        empty = {"hits": [], "topic_terms": None}
        query = " ".join(
            part for part in ((topic or "").strip(), (handle or "").strip()) if part
        )
        if not query or "\x00" in query:
            return empty
        if not self.available():
            return empty  # fail-closed: behave like Null, never crash
        limit = max(1, _env_int("CABINET_ORG_SEARCH_LIMIT", _DEFAULT_LIMIT))
        min_score_raw = (os.environ.get("CABINET_ORG_MIN_SCORE", "") or "").strip()
        min_score = _env_float("CABINET_ORG_MIN_SCORE", 0.0)
        # Normalize the comma-separated type list; the hybrid backend takes it
        # natively in ONE query (one embedding). Empty ⇒ unfiltered.
        types_raw = os.environ.get("CABINET_ORG_MEMORY_TYPES", "") or ""
        types_csv = ",".join(t.strip() for t in types_raw.split(",") if t.strip())

        try:
            stdout = self._run_search(query, types_csv, limit, min_score_raw)
        except Exception as e:  # a hook-adjacent lane must never crash
            sys.stderr.write("[org-source] search backend raised: %s\n" % e)
            return empty
        hits: List[dict] = []
        seen = set()
        for hit in _parse_rows(stdout):
            key = (hit["source"], hit["ref"])
            if key in seen:      # defensive: refs are unique per (type, id) in
                continue         # cabinet_memory, but a changed backend must
            seen.add(key)        # never duplicate a hit into the officer lane
            if hit["base_score"] < min_score:
                continue
            hits.append(hit)
        hits.sort(key=lambda h: h["base_score"], reverse=True)
        return {"hits": hits[:limit], "topic_terms": None}

    # --- everything below mirrors null.py: HONEST no-ops, no pretending ------
    # An org box has no PERSONAL estate (no dossiers, voice, drafting lessons,
    # vault, threads, deploys-via-captain). Each method returns the same honest
    # empty NullPersonalSource returns, for the same documented reasons
    # (tri-states stay None; read_note raises). Exception: open_commitments —
    # an org DOES have commitments of its own (ratified active outcomes); see
    # its docstring (W7 2026-07-09).
    def find_reply_candidates(self, *, since: Optional[str] = None) -> list:
        return []

    def person_intel(self, slug: str) -> str:
        return ""

    def open_commitments(self, direction: str) -> list:
        """The ORG's open commitments — its Captain-ratified ACTIVE outcomes
        (W7, 2026-07-09: recall in the decision path).

        The CG-2 gather seam (run_action_lane._source_parts, flag
        ``CABINET_GATHER_VIA_SOURCE=1``) drives ALL of its memory recall off
        ``open_commitments()`` rows: each row is fenced as an OPEN COMMITMENT
        block and seeds a topic-anchored ``search()`` for content_ts-fenced
        CONTEXT. With the former honest-empty here, an org deployment ran the
        decision path MEMORY-BLIND even though ``search()`` was live — zero
        recall ever reached the proposer (the memory-audit P0).

        An org box genuinely HAS open commitments: the ratified ``status:
        active`` outcomes in ``instance/config/outcomes.yml`` — the same rows
        the mission compiler executes. They are the org's obligations to the
        Captain, so they answer ``owed_to_captain``; ``owed_by_captain``
        stays the honest empty (an org does not track the Captain's personal
        promises). This reads REAL config — nothing is fabricated.

        Row shape mirrors what the seam consumes (ref from path/id/slug,
        handle from person/slug, topic from text). Fail-closed: missing file,
        unparseable YAML, or an absent yaml module ⇒ ``[]``."""
        if direction != "owed_to_captain":
            return []
        # SINGLE JOINED string (layer-sep gate pattern, see env.py:87 — no
        # bare quoted instance path token in a Path(...) / <token> chain).
        path = _cabinet_root() / "instance/config/outcomes.yml"
        try:
            import yaml  # lazy — a clean-room box without PyYAML stays honest-empty
            data = yaml.safe_load(path.read_text(encoding="utf-8",
                                                 errors="ignore"))
        except Exception:  # noqa: BLE001 — fail-closed, never crash the lane
            return []
        outcomes = (data or {}).get("outcomes")
        if not isinstance(outcomes, list):
            return []
        rows: List[dict] = []
        for oc in outcomes:
            if not isinstance(oc, dict) or oc.get("status") != "active":
                continue
            oid = str(oc.get("id") or "").strip()
            text = str(oc.get("name") or "").strip()
            if not oid or not text:
                continue
            lane = str(oc.get("lane") or "").strip() or _lane_from_outcome_id(oid)
            rows.append({
                "id": oid,
                "path": f"instance/config/outcomes.yml#{oid}",
                "slug": lane or oid,
                "person": lane or oid,
                "text": text,
                "direction": "owed_to_captain",
                "status": "active",
            })
            if len(rows) >= 8:   # the seam caps at rows[:8]; stay bounded here too
                break
        return rows

    def voice_profile(self) -> str:
        return ""

    def model_patterns(self) -> str:
        return ""

    def drafting_lessons(self, before_ts: str) -> str:
        return ""

    def read_note(self, path: str) -> str:
        raise FileNotFoundError("org source has no vault notes")

    def find_threads(self, hours: int = 48) -> list:
        return []

    def gather(self, thread: dict, *, do_prep: bool = True) -> dict:
        return {}

    def draft_fn(self, thread: dict, ctx: dict,
                 *, min_confidence: float = 0.0) -> str:
        # Honest decline — falsy, so the draft lane skips the thread.
        return ""

    def captain_replied_since(self, slug: str, when) -> Optional[bool]:
        return None  # honest UNKNOWN — never a fabricated True/False

    def still_awaiting(self, slug: str, hours: int = 72) -> Optional[bool]:
        return None  # honest UNKNOWN — callers surface, never suppress

    def deploy_health(self, app: str, limit: int = 8) -> dict:
        return {}    # reads as healthy/quiet — an org box never alarms

    def briefing_commitments(self, direction: str = "owed_by_captain") -> list:
        return []
