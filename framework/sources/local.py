"""framework/sources/local.py — the LOCAL-FOLDER PersonalSource.

``LocalNotesSource`` is the recall adapter for an operator who has a folder of
notes and no org estate: no Neon, no Voyage, no pgvector, no personal-source
sidecar. It reads ONE declared directory of plain text/markdown and answers
``search()`` from it. That is the whole capability, and it is deliberately the
smallest thing that is actually LIVE — before this adapter existed, a
deployment with no ``sources.yml`` fail-closed to ``NullPersonalSource``
(``available() -> False``, ``search() -> {"hits": []}``), so the one preset
shaped for a non-company operator shipped with zero recall.

WHY A THIRD ADAPTER RATHER THAN A FLAG ON ONE OF THE TWO.
``NullPersonalSource`` is the honest empty and must stay empty — it is the
fail-closed default the resolver binds when config is absent or broken, and
teaching it to read a directory would make the FAILURE path read files.
``OrgSource`` is backed by ``cabinet_memory`` through ``memory.sh``: it needs a
connection string and an embedding provider, and on a box that has neither it
degrades to the same empty. Neither can serve a laptop with a notes folder, so
this is a third adapter bound the same way both of those are — as DATA in
``instance/config/sources.yml`` — and no framework code branches to select it.

STRUCTURALLY READ-ONLY, and this is a property, not a policy. There is no
``LocalNotesDispatch`` in this module and no write method anywhere in the
class: a deployment binding this adapter has a working READ seam and a
``dispatch:`` seam that stays ``NullPersonalDispatch`` (every write no-ops).
Material an operator points this at — which at low altitude is frequently
their employer's, not theirs — can therefore be recalled but never written
back, and no config flip in this module can change that, because there is
nothing here to flip.

WHAT IT READS, AND THE BOUNDS IT KEEPS.
  * ROOT: ``CABINET_LOCAL_SOURCE_ROOT`` (env) wins; else ``local_root:`` in
    ``instance/config/sources.yml``; else **NOTHING** — ``resolve_root()``
    returns ``None`` and the adapter reports ``available() -> False``. A
    relative value resolves under ``CABINET_ROOT``, never under the process
    cwd — a daemon's cwd is not a consented scope.

    THE ABSENT CASE FAILS HONESTLY (changed 2026-07-28, measured). It used to
    fall back to ``<CABINET_ROOT>/vault``, which on a fresh hatch is the
    CABINET'S OWN SHIPPED DOCS (``vault/README.md``, ``vault/architecture.md``
    are tracked in the repo). So an operator who declared no folder got
    ``available() -> True`` and recall answering out of the framework's own
    documentation as if it were their notes — a confident false positive,
    which is worse than an honest empty because nothing downstream can tell
    the two apart. Undeclared is now UNSET, and every caller sees the same
    fail-closed shape it already handles for ``NullPersonalSource``.
  * JAIL: every candidate path must ``os.path.realpath``-resolve INSIDE the
    realpath of the root. A symlink pointing out of the folder is SKIPPED, not
    followed — the same containment rule ``validate-extension.sh`` applies to
    entrypoints, for the same reason: entering a folder path is not consent to
    read what it links to.
  * CAPS: ``MAX_FILES`` files, ``MAX_FILE_BYTES`` per file, ``SUFFIXES``
    extensions. Bounded so a mistyped root (a home directory, a repo) costs a
    bounded walk instead of an unbounded one. A file over the byte cap is read
    TRUNCATED, never skipped silently.
  * NEVER a hidden directory (``.git``, ``.obsidian``, ``.venv`` …): a dotdir
    is machine state, not notes, and ``.git`` in particular would surface
    object files as "hits".

``content_ts`` IS DERIVED OR ABSENT — NEVER mtime. The leak fence
(``officer_runner._content_ts`` / ``leakguard``) EXCLUDES a hit with no
``content_ts``, so an honest ``None`` costs a hit while a fabricated timestamp
costs the fence. mtime is the wrong clock (a checkout, a sync or a backup
restore rewrites it wholesale), so it is never consulted. Two derivations
only: a frontmatter ``date:``/``created:`` value, and a ``YYYY-MM-DD`` prefix
in the filename.

RANKING is stdlib and deliberately unimpressive: per-term document frequency
over the scanned corpus gives an IDF weight, chunk term-frequency is
saturating (``tf / (tf + 1)``), and the score is normalised by the query's
total IDF mass so it lands in ``0.0..1.0`` and is comparable to the
``base_score`` OrgSource returns. It is not an embedding model and does not
pretend to be — it is exact-term recall over a folder, which is what a folder
supports.

LAYER SEP: stdlib only; instance paths appear ONLY as single joined string
literals (``"instance/config/sources.yml"``), the same construction
``framework/sources/__init__.py`` and ``framework/env.py`` use — the gate
greps for the bare quoted token, which a joined path never matches.

py3.9-compatible (``from __future__ import annotations``, ``typing.Optional``,
no ``match``/``case``).
"""
from __future__ import annotations

import math
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

#: Text-shaped extensions. Anything else in the folder is not a note.
SUFFIXES = (".md", ".markdown", ".txt")

#: Walk bound — a mistyped root costs a bounded walk, not an unbounded one.
MAX_FILES = 500

#: Per-file read bound. A larger file is read TRUNCATED (never skipped
#: silently: a truncated read is degraded recall, a silent skip is a lie).
MAX_FILE_BYTES = 256 * 1024

#: Chunks per file — a long note is many hits, but not unboundedly many.
MAX_CHUNKS_PER_FILE = 40

#: Default hits returned by ``search()``.
DEFAULT_LIMIT = 10

#: Tokens shorter than this carry no retrieval signal ("a", "of", "to").
MIN_TERM_LEN = 3

_WORD_RE = re.compile(r"[A-Za-z0-9_]{%d,}" % MIN_TERM_LEN)
_HEADING_RE = re.compile(r"^#{1,6}\s+\S")
_FRONTMATTER_DATE_RE = re.compile(
    r"^(?:date|created)\s*:\s*['\"]?(\d{4}-\d{2}-\d{2})", re.MULTILINE)
_FILENAME_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _cabinet_root() -> Path:
    """The deployment root — ``CABINET_ROOT`` env, else this file's repo root
    (``framework/sources/local.py`` -> ``parents[2]``). Mirrors the resolver's
    own ``_cabinet_root`` (no hardcoded absolute path)."""
    return Path(os.environ.get("CABINET_ROOT")
                or str(Path(__file__).resolve().parents[2]))


def _configured_root() -> Optional[str]:
    """``local_root:`` from ``instance/config/sources.yml``, or None.

    Read defensively and never raised from: this adapter must import and
    instantiate on a box whose config is absent or damaged, exactly like the
    resolver that binds it."""
    try:
        import yaml  # local import: pyyaml stays optional for this module
    except Exception:
        return None
    try:
        cfg = _cabinet_root() / "instance/config/sources.yml"   # joined literal
        if not cfg.is_file():
            return None
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            return None
        value = data.get("local_root")
        return value.strip() if isinstance(value, str) and value.strip() else None
    except Exception:
        return None


def resolve_root() -> Optional[Path]:
    """The declared notes folder, or ``None`` when nobody declared one.

    Env wins, then config. A relative value resolves under ``CABINET_ROOT`` —
    never under the process cwd, because a daemon's cwd is not a consented
    scope. THERE IS NO DEFAULT: see the module docstring — the former
    ``<CABINET_ROOT>/vault`` fallback bound the cabinet's own shipped docs and
    reported a live source, which is a lie an operator cannot detect."""
    base = _cabinet_root()
    declared = os.environ.get("CABINET_LOCAL_SOURCE_ROOT", "").strip() \
        or _configured_root()
    if not declared:
        return None
    path = Path(declared).expanduser()
    return path if path.is_absolute() else base / path


def _content_ts_for(path: Path, text: str) -> Optional[str]:
    """ISO-8601 content time, DERIVED or ``None``. Never mtime (see module
    docstring): a wrong timestamp defeats the leak fence, an absent one only
    costs the hit."""
    head = text[:2048]
    if head.startswith("---"):
        end = head.find("\n---", 3)
        if end != -1:
            m = _FRONTMATTER_DATE_RE.search(head[3:end])
            if m:
                return m.group(1) + "T00:00:00Z"
    m = _FILENAME_DATE_RE.search(path.name)
    if m:
        return m.group(1) + "T00:00:00Z"
    return None


def _strip_frontmatter(text: str) -> str:
    """Drop a leading YAML frontmatter block. NOT cosmetic — measured
    2026-07-28 on the shape this adapter is FOR (an Obsidian folder, where
    ``date:`` frontmatter is the primary ``content_ts`` derivation this module
    documents).

    A headingless note is ONE chunk, so its frontmatter was the first thing in
    the chunk body, and both operator-facing uses of that body then reported
    machinery as the operator's own material. Through the real
    ``first-briefing.sh --local`` chain, on five dated notes:

      * the card's quote — the "I did not ask you for this, I read it" line,
        the whole point of the surface — rendered
        ``"--- date: 2026-07-20 title: … tags: [notes] status: open --- The
        storefront widget alignment drifts…"``;
      * ``genesis._join_terms`` counted the KEY NAMES, and since every note
        carries them they scored above every real word: ``Shared wording:
        status, title, date, open``, with the genuinely shared domain term
        (``checkout``, in two of the three cited files) pushed out of all four
        slots.

    Stripped HERE rather than in either consumer because the chunk body is
    supposed to be the operator's prose, and every present and future reader of
    it inherits the same defect otherwise.

    Conservative by construction: strips ONLY when the file OPENS with a
    ``---`` line and a later line is exactly ``---`` or ``...``. An unterminated
    ``---`` is a thematic break and the text is returned untouched, so a note
    that merely starts with a horizontal rule keeps every word.

    ``_content_ts_for`` reads the RAW text and runs before this, so dating is
    unaffected — verified by the frontmatter-date arm in
    ``framework/sources/tests/test_local_source.py``."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            return "\n".join(lines[i + 1:])
    return text


def _chunks(text: str) -> List[Tuple[str, str]]:
    """``[(heading, body)]`` split on markdown headings. A note with no
    headings is ONE chunk (heading ``""``) — never zero, or a plain .txt file
    would be invisible to every query."""
    lines = _strip_frontmatter(text).splitlines()
    out: List[Tuple[str, str]] = []
    heading = ""
    buf: List[str] = []
    for line in lines:
        if _HEADING_RE.match(line):
            if buf or heading:
                out.append((heading, "\n".join(buf).strip()))
            heading = line.lstrip("#").strip()
            buf = []
            if len(out) >= MAX_CHUNKS_PER_FILE:
                break
        else:
            buf.append(line)
    if (buf or heading) and len(out) < MAX_CHUNKS_PER_FILE:
        out.append((heading, "\n".join(buf).strip()))
    return [c for c in out if c[0] or c[1]]


def _terms(text: str) -> List[str]:
    return [w.lower() for w in _WORD_RE.findall(text or "")]


class LocalNotesSource:
    """A ``PersonalSource`` over ONE local folder of notes.

    Structurally satisfies ``base.PersonalSource`` (``runtime_checkable``)
    without importing it, mirroring ``null.py``. Everything the folder cannot
    answer stays an honest empty — a notes directory holds no person dossiers,
    no reply threads and no deploy state, and inventing any of those is the
    failure this adapter exists to avoid, not the gap it exists to fill."""

    def __init__(self, root: Optional[str] = None) -> None:
        self._root_override = root
        self._corpus: Optional[List[dict]] = None

    # --- scope -------------------------------------------------------------
    def root(self) -> Optional[Path]:
        """The declared folder, or ``None`` when nothing is declared. Callers
        MUST treat ``None`` as "no scope was granted", never as a path."""
        return Path(self._root_override) if self._root_override else resolve_root()

    def binding_status(self) -> dict:
        """One honest description of this binding, for surfaces that report
        recall state to the operator (the genesis briefing does).

        ``{"declared": bool, "root": str|None, "exists": bool, "notes": int}``
        — ``declared`` False is the UNSET case: a folder was never named, so
        there is nothing to be unavailable ABOUT, and the fix is to name one.
        Distinguishing "you pointed me nowhere" from "the folder you named is
        empty" is the whole reason this returns a shape rather than a bool."""
        root = self.root()
        if root is None:
            return {"declared": False, "root": None, "exists": False, "notes": 0}
        return {"declared": True, "root": str(root), "exists": root.is_dir(),
                "notes": len(self._load())}

    def _in_jail(self, candidate: Path, jail: str) -> bool:
        """realpath containment — a symlink out of the folder is SKIPPED, never
        followed. Entering a folder path is not consent to read what it links
        to."""
        try:
            real = os.path.realpath(str(candidate))
        except OSError:
            return False
        return real == jail or real.startswith(jail + os.sep)

    def _files(self) -> List[Path]:
        root = self.root()
        if root is None or not root.is_dir():
            return []
        try:
            jail = os.path.realpath(str(root))
        except OSError:
            return []
        found: List[Path] = []
        for dirpath, dirnames, filenames in os.walk(str(root)):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            for name in sorted(filenames):
                if name.startswith(".") or not name.lower().endswith(SUFFIXES):
                    continue
                candidate = Path(dirpath) / name
                if not self._in_jail(candidate, jail):
                    continue
                found.append(candidate)
                if len(found) >= MAX_FILES:
                    return found
        return found

    def _read(self, path: Path) -> str:
        """Bounded read. Over the cap the file is TRUNCATED, not skipped."""
        try:
            with open(str(path), "r", encoding="utf-8", errors="replace") as fh:
                return fh.read(MAX_FILE_BYTES)
        except OSError:
            return ""

    def _load(self) -> List[dict]:
        """Scan once per instance: ``[{ref, heading, text, content_ts, tf}]``.
        Cached because an officer asks several questions of one folder in one
        run; a restart re-reads, exactly like the resolver's adapter cache."""
        if self._corpus is not None:
            return self._corpus
        root = self.root()
        if root is None:
            self._corpus = []
            return self._corpus
        corpus: List[dict] = []
        for path in self._files():
            text = self._read(path)
            if not text.strip():
                continue
            ts = _content_ts_for(path, text)
            try:
                rel = str(path.relative_to(root))
            except ValueError:
                rel = path.name
            for heading, body in _chunks(text):
                blob = (heading + "\n" + body).strip()
                if not blob:
                    continue
                tf: Dict[str, int] = {}
                for term in _terms(blob):
                    tf[term] = tf.get(term, 0) + 1
                corpus.append({
                    "ref": rel + (("#" + heading) if heading else ""),
                    "path": rel,
                    "heading": heading,
                    "text": blob,
                    "content_ts": ts,
                    "tf": tf,
                })
        self._corpus = corpus
        return corpus

    # --- OBSERVE / SEARCH --------------------------------------------------
    def available(self) -> bool:
        """True only when a folder was DECLARED, exists, AND holds at least
        one admissible note. A configured-but-empty folder is NOT available,
        and neither is an UNDECLARED one — the caller must degrade honestly
        rather than report a live source that can only ever answer nothing, or
        (before 2026-07-28) one answering out of the cabinet's own docs."""
        return bool(self._load())

    def search(self, handle: str, *, topic: Optional[str] = None) -> dict:
        """Exact-term recall over the folder, ranked IDF x saturating TF.

        Returns the shape framework callers consume:
        ``{"hits": [{source, ref, path, heading, text, base_score, who, ts,
        content_ts}], "topic_terms": [...]}``. ``who`` is empty and ``ts``
        mirrors ``content_ts`` — a folder records neither an author nor a
        send time, and both are honest absences rather than guesses."""
        corpus = self._load()
        query = _terms(handle) + _terms(topic or "")
        if not corpus or not query:
            return {"hits": [], "topic_terms": _terms(topic or "") or None}
        wanted = sorted(set(query))
        n_docs = len(corpus)
        df = {t: 0 for t in wanted}
        for doc in corpus:
            for t in wanted:
                if t in doc["tf"]:
                    df[t] += 1
        idf = {t: math.log(1.0 + (n_docs / (1.0 + df[t]))) for t in wanted}
        mass = sum(idf.values()) or 1.0
        scored: List[Tuple[float, dict]] = []
        for doc in corpus:
            score = 0.0
            for t in wanted:
                tf = doc["tf"].get(t, 0)
                if tf:
                    score += idf[t] * (tf / (tf + 1.0))
            if score <= 0.0:
                continue
            scored.append((score / mass, doc))
        scored.sort(key=lambda pair: (-pair[0], pair[1]["ref"]))
        hits = []
        for base_score, doc in scored[:DEFAULT_LIMIT]:
            hits.append({
                "source": "local",
                "ref": doc["ref"],
                "path": doc["path"],
                "heading": doc["heading"],
                "text": doc["text"],
                "base_score": round(base_score, 6),
                "who": "",
                "ts": doc["content_ts"],
                "content_ts": doc["content_ts"],
            })
        return {"hits": hits, "topic_terms": _terms(topic or "") or None}

    def read_note(self, path: str) -> str:
        """Read ONE note by folder-relative path. Jailed: anything resolving
        outside the folder raises ``FileNotFoundError`` rather than reading —
        the same refusal an absent file gets, so a traversal attempt learns
        nothing a miss would not tell it."""
        root = self.root()
        if root is None:
            raise FileNotFoundError(path)   # no scope granted — same refusal
        try:
            jail = os.path.realpath(str(root))
        except OSError:
            raise FileNotFoundError(path)
        candidate = (root / path).expanduser()
        if not self._in_jail(candidate, jail) or not candidate.is_file():
            raise FileNotFoundError(path)
        return self._read(candidate)

    # --- HONEST EMPTIES ----------------------------------------------------
    # A notes folder is not a mailbox, a dossier index, a commitment ledger or
    # a deploy log. Each of these returns the same shape null.py does, for the
    # same reason: a fabricated answer is worse than a missing one.
    def find_reply_candidates(self, *, since: Optional[str] = None) -> list:
        return []

    def person_intel(self, slug: str) -> str:
        return ""

    def open_commitments(self, direction: str) -> list:
        return []

    def voice_profile(self) -> str:
        return ""

    def model_patterns(self) -> str:
        return ""

    def drafting_lessons(self, before_ts: str) -> str:
        return ""

    def find_threads(self, hours: int = 48) -> list:
        return []

    def gather(self, thread: dict, *, do_prep: bool = True) -> dict:
        return {}

    def draft_fn(self, thread: dict, ctx: dict,
                 *, min_confidence: float = 0.0) -> str:
        return ""

    def captain_replied_since(self, slug: str, when) -> Optional[bool]:
        return None  # honest UNKNOWN — never a fabricated True/False

    def still_awaiting(self, slug: str, hours: int = 72) -> Optional[bool]:
        return None  # honest UNKNOWN — callers surface, never suppress

    def deploy_health(self, app: str, limit: int = 8) -> dict:
        return {}

    def briefing_commitments(self, direction: str = "owed_by_captain") -> list:
        return []
