"""``flavor_a.screenpipe_source`` — the Flavor-A personal-sensing adapter (SRC-1/3).

``ScreenpipeSource`` is the launcher-neutral ``PersonalSource`` for THIS deployment
(captain Nate, Flavor-A / screenpipe brain). It OWNS the real screenpipe calls:
the former ``framework.fidelity.officer_runner.BrainAdapter`` method bodies are
INLINED here (SRC-3 re-home), so on Nate's instance every result is
**byte-identical** to what ran when those bodies lived in ``framework/`` and every
existing fidelity/acting test stays green (source-adapter-boundary spec §4
method-origin table, §5). Framework CORE now reaches this only through
``framework.sources.get_source()``; framework itself names no screenpipe lib.

The 7 vault/intel/commitment/priors/note methods are the inlined ``BrainAdapter``
bodies under the launcher-neutral ``PersonalSource`` names (search←gather_vault,
model_patterns←nate_model_patterns; the others keep their names). The vault search
still shells out to ``_vault_gather_runner.py`` under python3.12 (the py3.9/3.12
boundary the harness interpreter can't cross in-process) — that sidecar re-homed
to this package alongside the adapter. The screenpipe ACTING surface (find_threads
/ gather / draft_fn / deploy_health / ...) lives in the sibling
``flavor_a.acting`` module; the acting methods below delegate to it, so the acting
lanes reach it through ``get_source()`` too.

**Instance-scoped by construction.** This module MAY import ``framework`` and (in
its method bodies) the screenpipe ``_shared`` libs — the coupling ``framework/``
CORE must not have. It is bound only through ``instance/config/sources.yml`` +
``framework.sources.get_source()``; framework never imports it. It satisfies
``framework.sources.base.PersonalSource`` **structurally** (a ``runtime_checkable``
``Protocol`` — no inheritance).

**Cheap + side-effect-free to construct.** Every screenpipe lib is imported
**lazily**, inside the method that uses it (mirroring the original ``BrainAdapter``),
and the acting module is imported on first acting-method use — so ``get_source()``
→ ``ScreenpipeSource()`` neither inserts ``~/.screenpipe`` on ``sys.path`` nor
imports a lib nor crashes until a caller actually gathers. The backends are also
**injectable** (constructor: ``context_lib`` / ``server`` / ``vault_search`` for
the vault/intel methods, ``acting_mod`` for the acting surface), so tests prove
the real calls with fakes and no live brain is needed. Zero-arg constructible —
the ``sources.yml`` contract (``get_source()`` does ``cls()``).

py3.9-compatible: ``from __future__ import annotations`` + ``typing.Optional``,
no ``match``/``case``; module-load imports are stdlib only.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Vault-search subprocess seam (re-homed from framework.fidelity.officer_runner
# with the adapter, SRC-3). The in-process embedded vector search FAILS under the
# harness interpreter (system Python 3.9.6 has no loadable sqlite extension), so
# the DEFAULT adapter runs the SAME context_lib.gather(sources=["vault"]) under
# python3.12 via _vault_gather_runner.py (now this package's sibling). The
# content_ts leak-fence in framework's gather_cutoff_context still runs in-process
# on the returned hits — this only fixes WHERE the search executes. Bodies are
# byte-identical to the originals.
# ---------------------------------------------------------------------------
def _safe_handle(handle: str) -> bool:
    h = (handle or "").strip()
    return bool(h) and "\x00" not in h and "/" not in h and "\\" not in h \
        and ".." not in h


def _subprocess_vault_gather(handle: str, topic: str | None = None) -> dict:
    """Run context_lib.gather(sources=["vault"]) under the BRAIN interpreter
    (python3.12) via subprocess and return its {hits, topic_terms}.

    The in-process embedded search FAILS under the harness interpreter (system
    Python 3.9.6 has no loadable sqlite extensions -> the vector extension can't
    load -> context_lib._fetch_vault silently returns 0 hits). Running the SAME
    gather under 3.12 reuses every bit of its logic; the content_ts leak-fence
    in gather_cutoff_context still runs in the (3.9.6) framework process on the
    returned hits, so leak-safety is unchanged (this only fixes WHERE search
    executes).

    Graceful-degrade: any failure (interpreter/runner absent, unsafe handle,
    timeout, non-JSON) returns ``{"hits": [], "topic_terms": None}`` so the case
    is scored context-thin rather than aborting the batch — exactly the
    pre-fix behavior, just no longer the silent default for everyone."""
    if not _safe_handle(handle):
        sys.stderr.write(f"[vault-gather] refused unsafe handle {handle!r}\n")
        return {"hits": [], "topic_terms": None}
    python = (os.environ.get("CABINET_BRAIN_PYTHON")
              or shutil.which("python3.12") or "python3.12")
    runner = Path(__file__).with_name("_vault_gather_runner.py")
    try:
        proc = subprocess.run(
            [python, str(runner), handle, topic or ""],
            capture_output=True, text=True, timeout=60,
            env={**os.environ},
        )
        data = json.loads((proc.stdout or "").strip() or "{}")
    except (FileNotFoundError, OSError, subprocess.SubprocessError,
            ValueError) as e:  # ValueError covers json.JSONDecodeError
        sys.stderr.write(f"[vault-gather] subprocess gather failed: {e}\n")
        return {"hits": [], "topic_terms": None}
    if data.get("error"):
        sys.stderr.write(f"[vault-gather] runner error: {data['error']}\n")
    return {"hits": data.get("hits") or [],
            "topic_terms": data.get("topic_terms")}


# ---------------------------------------------------------------------------
# Commitment-direction CONTRACT mapping (T1 protocol widen, 2026-07-07). The
# PersonalSource CONTRACT speaks the launcher-neutral values owed_by_captain /
# owed_to_captain (base.PersonalSource.open_commitments); THIS adapter's storage
# estate (commitments_lib rows, the 6-Commitments/ dirs, the brain server) keeps
# its internal owed_by_nate / owed_to_nate values verbatim. The adapter maps a
# contract direction IN and remaps returned rows' ``direction`` field OUT (on
# shallow copies — storage rows are never mutated). A legacy internal value
# passes through byte-identical, so pre-contract instance callers/tests keep
# their exact prior behavior.
# ---------------------------------------------------------------------------
_DIRECTION_TO_INTERNAL = {"owed_by_captain": "owed_by_nate",
                          "owed_to_captain": "owed_to_nate"}
_DIRECTION_TO_CONTRACT = {v: k for k, v in _DIRECTION_TO_INTERNAL.items()}


def _rows_to_contract(rows):
    """Shallow-copy rows, remapping an internal ``direction`` value to its
    contract name (owed_by_nate → owed_by_captain). Rows without a direction
    field — or with an unknown value — pass through unchanged; the input rows
    themselves are never mutated."""
    out = []
    for r in rows:
        if isinstance(r, dict) and r.get("direction") in _DIRECTION_TO_CONTRACT:
            r = dict(r)
            r["direction"] = _DIRECTION_TO_CONTRACT[r["direction"]]
        out.append(r)
    return out


class ScreenpipeSource:
    """Flavor-A ``PersonalSource`` — the real screenpipe adapter (inlined
    ``BrainAdapter`` bodies + the acting surface, byte-identical to today).

    Injectable for tests, real by default:

      * ``context_lib`` / ``server`` — the in-process brain seams the vault /
        intel / commitment / priors / note methods honor (tests inject stubs;
        the leak-integrity seam ``sources=["vault"]`` is asserted there). With
        NEITHER injected, the DEFAULT real path runs (context_lib subprocess for
        the vault search; the ``_shared`` libs for the rest).
      * ``vault_search`` — the vault-search seam ``search`` uses when no
        context_lib/server is injected (default: the python3.12 subprocess).
      * ``acting_mod`` — the module exposing the acting surface (find_threads /
        gather / draft_fn / ...). Default: the sibling ``flavor_a.acting`` (lazy).
      * ``pipes_dir`` — the screenpipe pipes root probed by ``available()``.
        Default: ``~/.screenpipe/pipes``.
    """

    def __init__(self, context_lib=None, server=None, vault_search=None,
                 acting_mod=None, pipes_dir: Optional[str] = None):
        # Inlined BrainAdapter seams (in-process brain for tests; the default
        # real path routes the vault search through the py3.12 subprocess).
        self._context_lib = context_lib
        self._server = server
        self._vault_search = vault_search
        # Acting surface (flavor_a.acting), lazily resolved on first acting call.
        self._acting_mod = acting_mod
        # Liveness-probe root ONLY (available()). The method bodies get their own
        # ~/.screenpipe paths onto sys.path from the libs / acting module they use.
        self._pipes_dir = pipes_dir or os.path.expanduser("~/.screenpipe/pipes")

    # -- lazy backends -------------------------------------------------------
    def _ctx(self):
        if self._context_lib is None:
            import context_lib  # brain bridge dep (resolved on sys.path)
            self._context_lib = context_lib
        return self._context_lib

    def _acting(self):
        """The sibling ``flavor_a.acting`` module (the screenpipe acting surface).
        Lazy: importing it inserts ``~/.screenpipe`` on ``sys.path`` and prints a
        one-time token-preflight line, so we defer that to first acting use."""
        if self._acting_mod is None:
            from flavor_a import acting
            self._acting_mod = acting
        return self._acting_mod

    # -- liveness ------------------------------------------------------------
    def available(self) -> bool:
        """Cheap liveness probe (mirrors ``retro.retro_available()``): ``True`` iff
        the screenpipe ``_shared`` estate that backs the methods is present on
        disk (``draft_lib`` backs ``person_intel`` / ``voice_profile`` / the
        acting surface; its presence is the honest "the brain is here" signal).
        ``False`` ⇒ the caller degrades exactly as against the null source. Never
        raises — any error is ``False``."""
        try:
            return (Path(self._pipes_dir) / "_shared" / "draft_lib.py").exists()
        except Exception:
            return False

    # -- OBSERVE / SEARCH (leak-scoped retrieval) ----------------------------
    #    ← BrainAdapter.gather_vault (officer_runner.py:346), inlined verbatim.
    def search(self, handle, topic=None):
        # sources=["vault"] EXACTLY — Tier-1 only; brief is discarded upstream.
        # topic = the inbound message being replied to → topic-aware retrieval
        # (gather extracts EN+DA content nouns + folds them ahead of the person
        # terms, so the query is what the conversation is ABOUT, not just the
        # person slug). Without it, search("Sevan") hits the profile note, not
        # the thread; a 0.4 relevance floor returns 0 rather than noise.
        #
        # An INJECTED context_lib/server (tests) is delegated in-process,
        # preserving the leak-integrity seam (sources=["vault"] asserted there).
        # The DEFAULT real adapter routes through the python3.12 subprocess
        # (vault_search) because the in-process 3.9.6 sqlite can't load the
        # vector extension -> the in-process search silently returns 0 hits.
        if self._context_lib is not None or self._server is not None:
            return self._ctx().gather(handle, sources=["vault"], topic=topic)
        fn = self._vault_search or _subprocess_vault_gather
        return fn(handle, topic) or {"hits": [], "topic_terms": None}

    def find_reply_candidates(self, *, since: Optional[str] = None) -> list:
        # → flavor_a.acting.find_threads (draft_lib.find_awaiting_threads + the
        #   skip-list / calendar-invite / chair-lock exclusions) at its default
        #   window. ``since`` is accepted for interface parity (Flavor-A discovery
        #   is window-based — no since→hours remap would be byte-identical, so we
        #   forward today's exact default call). The acting lanes use
        #   ``find_threads(hours=…)`` directly instead of this.
        return self._acting().find_threads()

    # -- PERSON INTEL --------------------------------------------------------
    #    ← BrainAdapter.person_intel (officer_runner.py:371), inlined verbatim.
    def person_intel(self, slug):
        if self._server is not None:
            return self._server.person_intel(slug)
        import draft_lib
        return draft_lib.person_intel(slug)

    # -- COMMITMENTS ---------------------------------------------------------
    #    ← BrainAdapter.open_commitments (officer_runner.py:377), inlined verbatim.
    def open_commitments(self, direction):
        # CONTRACT surface (base.PersonalSource): direction takes owed_by_captain
        # / owed_to_captain and the returned rows' direction field carries the
        # same contract values. Storage + the brain server speak the internal
        # owed_by_nate values, so a contract direction maps IN and the returned
        # rows remap OUT (on copies, _rows_to_contract). A legacy internal value
        # is passed through byte-identical — the pre-contract behavior, kept for
        # back-compat instance callers/tests.
        internal = _DIRECTION_TO_INTERNAL.get(direction, direction)
        if self._server is not None:
            rows = self._server.open_commitments(internal)
        else:
            import commitments_lib
            all_rows = commitments_lib.load_all()
            _closed = {"closed", "done", "resolved", "dropped", "cancelled",
                       "fulfilled"}
            rows = [fm for fm in all_rows.values()
                    if fm.get("direction") == internal
                    and str(fm.get("status", "")).strip().lower() not in _closed]
        if direction in _DIRECTION_TO_INTERNAL:
            return _rows_to_contract(rows or [])
        return rows

    # -- IDENTITY PRIORS (PRIVATE — inform HOW to draft, never emitted) -------
    #    ← BrainAdapter.voice_profile (officer_runner.py:399), inlined verbatim.
    def voice_profile(self):
        if self._server is not None:
            return self._server.voice_profile()
        import draft_lib
        return draft_lib.voice_profile()

    #    ← BrainAdapter.nate_model_patterns (officer_runner.py:405), inlined; the
    #    launcher-neutral METHOD name maps to the brain artifact kept VERBATIM
    #    (me_signal.nate_model('patterns'), and the server's nate_model_patterns()
    #    on the injected path — DE-NATE §3: only the method name changed).
    def model_patterns(self):
        # PATTERNS layer ONLY — never core/memory (ground gotcha: patterns shape
        # how to write NOW; core/memory are less volatile and could leak newer
        # signal). me_signal wraps it in the PRIVATE fence.
        if self._server is not None:
            return self._server.nate_model_patterns()
        import me_signal
        return me_signal.nate_model("patterns")

    #    ← BrainAdapter.drafting_lessons (officer_runner.py:414), inlined verbatim.
    def drafting_lessons(self, before_ts):
        # Raw lessons text from the source, then date-filtered STRICTLY BEFORE
        # before_ts via retro.lessons_before (conservative: drops the whole
        # same-day block — a same-day lesson could postdate the reply). The
        # filter ALWAYS runs, so leak-safety holds for the real lib AND an
        # injected fake server alike.
        #
        # Cap-then-filter trap (fixed): draft_lib.drafting_lessons() returns only
        # the LAST max_chars (the MOST RECENT lessons). Feeding that pre-capped
        # tail to lessons_before means a case with a past cutoff sees a tail that
        # is entirely post-cutoff -> 0 lessons, even when earlier qualifying
        # lessons exist. So we pass the FULL corpus; lessons_before filters
        # strictly-before-cutoff THEN applies its own post-filter cap.
        from framework.fidelity import retro
        if self._server is not None:
            raw = self._server.drafting_lessons()
        else:
            import draft_lib
            raw = (draft_lib.LESSONS_FILE.read_text(errors="replace")
                   if draft_lib.LESSONS_FILE.exists() else "")
        return retro.lessons_before(before_ts, text=raw)

    # -- RAW NOTE READ (vault-jailed) ----------------------------------------
    #    ← BrainAdapter.read_note (officer_runner.py:436), inlined verbatim.
    def read_note(self, path):
        if self._server is not None:
            return self._server.read_note(path)
        import os
        from pathlib import Path
        # Source of truth is the pinned OBSIDIAN_VAULT_PATH (screenpipe's
        # embeddings plist now exports it); fall back to the TRUE on-disk
        # lowercase casing (verified: ~/obsidian/screenpipe-brain). Hardcoding
        # capital "Obsidian" only resolved via case-insensitive FS — the same
        # case-folding dependence we removed on the index side.
        vault = (os.environ.get("OBSIDIAN_VAULT_PATH")
                 or str(Path.home() / "obsidian" / "screenpipe-brain"))
        vreal = os.path.realpath(vault)
        resolved = os.path.realpath(os.path.join(vreal, path))
        if resolved != vreal and not resolved.startswith(vreal + os.sep):
            raise PermissionError(f"refused path outside vault: {path!r}")
        return Path(resolved).read_text(encoding="utf-8", errors="replace")

    # -- ACTING SURFACE (delegates to flavor_a.acting — byte-identical) ------
    # The acting lanes (run_draft_lane / run_action_lane / morning_synthesis)
    # reach these through get_source() (framework may not import instance). Each
    # forwards, one-to-one, to the re-homed screenpipe acting function with the
    # SAME signature, so behavior is byte-identical to the former
    # ``screenpipe_adapter.<fn>``. The module attribute is looked up at call time
    # so a test that patches ``flavor_a.acting.<fn>`` is honored.
    def find_threads(self, hours: int = 48) -> list:
        return self._acting().find_threads(hours=hours)

    def gather(self, thread, *, do_prep: bool = True) -> dict:
        return self._acting().gather(thread, do_prep=do_prep)

    def draft_fn(self, thread, ctx, *, min_confidence: float = 0.0):
        return self._acting().draft_fn(thread, ctx, min_confidence=min_confidence)

    def captain_replied_since(self, slug, when):
        # The PROTOCOL name (launcher-neutral, base.PersonalSource — T1 contract
        # rename 2026-07-07). The Flavor-A implementation stays the re-homed
        # acting fn, whose internal name keeps this launcher's form verbatim.
        return self._acting().nate_replied_since(slug, when)

    def nate_replied_since(self, slug, when):
        # Thin BACK-COMPAT alias (pre-contract name). New code — and all
        # framework core — calls captain_replied_since; this stays so instance
        # callers/tests that still speak the Flavor-A form keep working.
        return self.captain_replied_since(slug, when)

    def still_awaiting(self, slug, hours: int = 72):
        return self._acting().still_awaiting(slug, hours=hours)

    def deploy_health(self, app, limit: int = 8) -> dict:
        return self._acting().deploy_health(app, limit=limit)

    def briefing_commitments(self, direction: str = "owed_by_captain") -> list:
        # ← screenpipe_adapter.open_commitments (the ACTING status=="open" filter,
        #   distinct from the PersonalSource.open_commitments _closed-set filter).
        # CONTRACT direction values map to/from the internal storage values
        # exactly as in open_commitments above; a legacy internal value passes
        # through byte-identical (back-compat).
        internal = _DIRECTION_TO_INTERNAL.get(direction, direction)
        rows = self._acting().open_commitments(direction=internal)
        if direction in _DIRECTION_TO_INTERNAL:
            return _rows_to_contract(rows or [])
        return rows

    def normalize_voice(self, text):
        return self._acting().normalize_voice(text)
