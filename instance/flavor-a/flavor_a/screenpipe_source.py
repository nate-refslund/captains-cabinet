"""``flavor_a.screenpipe_source`` — the Flavor-A personal-sensing adapter (SRC-1).

``ScreenpipeSource`` is the launcher-neutral ``PersonalSource`` for THIS deployment
(captain Nate, Flavor-A / screenpipe brain). It is a **thin delegator**: every
method forwards, one-to-one, to today's EXACT code —
``framework.fidelity.officer_runner.BrainAdapter`` methods and
``framework.acting.screenpipe_adapter`` thread-discovery — so on Nate's instance
every result is **byte-identical** to what runs today and every existing test
stays green (source-adapter-boundary spec §4 method-origin table, §5 Phase 1).
The shim adds NO logic; it only forwards. The ONE non-forwarding method is
``available()`` — the interface's cheap liveness probe (spec §4.1), which the
seam defines fresh (no single underlying call), mirroring
``framework.fidelity.retro.retro_available()``.

**Instance-scoped by construction.** This module MAY import ``framework`` and
(transitively, through those framework modules) the screenpipe ``_shared`` libs
— the coupling ``framework/`` CORE must not have. It is bound only through
``instance/config/sources.yml`` + ``framework.sources.get_source()``; framework
never imports it. It satisfies ``framework.sources.base.PersonalSource``
**structurally** (a ``runtime_checkable`` ``Protocol`` — no inheritance).

**Cheap + side-effect-free to construct.** The heavy backends
(``BrainAdapter`` / ``screenpipe_adapter``) are imported **lazily**, on first
method use — so ``get_source()`` → ``ScreenpipeSource()`` neither inserts
``~/.screenpipe`` on ``sys.path`` nor imports a lib nor crashes until a caller
actually gathers. The backends are also **injectable** (constructor), so tests
prove pass-through with fakes and no real brain is needed. Zero-arg constructible
— the ``sources.yml`` contract (``get_source()`` does ``cls()``).

py3.9-compatible: ``from __future__ import annotations`` + ``typing.Optional``,
no ``match``/``case``; module-load imports are stdlib only.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


class ScreenpipeSource:
    """Flavor-A ``PersonalSource`` — a thin delegator over today's ``BrainAdapter``
    + ``screenpipe_adapter`` (byte-identical; the shim only forwards).

    Injectable for tests, real by default:

      * ``brain``       — the ``BrainAdapter``-shaped backend for the 7 vault /
                          intel / commitment / priors / note methods. Default:
                          the real ``framework.fidelity.officer_runner.BrainAdapter``
                          (lazy).
      * ``threads_mod`` — the module exposing ``find_threads`` for reply-candidate
                          discovery. Default: the real
                          ``framework.acting.screenpipe_adapter`` (lazy).
      * ``pipes_dir``   — the screenpipe pipes root probed by ``available()``.
                          Default: ``~/.screenpipe/pipes``.
    """

    def __init__(self, brain=None, threads_mod=None, pipes_dir: Optional[str] = None):
        # Injected (tests) or lazily resolved to the real framework surfaces on
        # first use — never at construction, so binding the source is cheap and
        # side-effect-free (no sys.path insert, no lib import, no crash).
        self._brain = brain
        self._threads_mod = threads_mod
        # Liveness-probe root ONLY (available()). The delegated calls get their
        # own paths onto sys.path from the framework modules they forward into.
        self._pipes_dir = pipes_dir or os.path.expanduser("~/.screenpipe/pipes")

    # -- lazy backends (byte-identical: the SAME code that runs today) --------
    def _b(self):
        """Today's ``BrainAdapter`` (``framework.fidelity.officer_runner``). Lazy:
        the screenpipe imports live INSIDE its methods, fired only on real use."""
        if self._brain is None:
            from framework.fidelity.officer_runner import BrainAdapter
            self._brain = BrainAdapter()
        return self._brain

    def _threads(self):
        """Today's acting thread-discovery module
        (``framework.acting.screenpipe_adapter``). Lazy: importing it inserts
        ``~/.screenpipe`` on ``sys.path`` and prints a one-time token-preflight
        line, so we defer that to the first ``find_reply_candidates()``."""
        if self._threads_mod is None:
            from framework.acting import screenpipe_adapter
            self._threads_mod = screenpipe_adapter
        return self._threads_mod

    # -- liveness ------------------------------------------------------------
    def available(self) -> bool:
        """Cheap liveness probe (mirrors ``retro.retro_available()``): ``True`` iff
        the screenpipe ``_shared`` estate that backs the delegated methods is
        present on disk (``draft_lib`` backs ``person_intel`` / ``voice_profile`` /
        ``find_reply_candidates``; its presence is the honest "the brain is here"
        signal). ``False`` ⇒ the caller degrades exactly as it would against the
        null source. Never raises — any error is ``False``."""
        try:
            return (Path(self._pipes_dir) / "_shared" / "draft_lib.py").exists()
        except Exception:
            return False

    # -- OBSERVE / SEARCH (leak-scoped retrieval) ----------------------------
    def search(self, handle: str, *, topic: Optional[str] = None) -> dict:
        # → BrainAdapter.gather_vault (officer_runner.py:346):
        #   context_lib.gather(handle, sources=["vault"], topic=topic) — Tier-1
        #   vault ONLY (never the live sent/screen/monday tiers). The content-ts
        #   leak fence stays ABOVE this, in the caller (spec §6 fidelity row).
        return self._b().gather_vault(handle, topic)

    def find_reply_candidates(self, *, since: Optional[str] = None) -> list:
        # → screenpipe_adapter.find_threads (draft_lib.find_awaiting_threads +
        #   the skip-list / calendar-invite / chair-lock exclusions). PASS 1 is
        #   byte-identical: today's callers use find_threads() at its default
        #   window; ``since`` is accepted for interface parity (Flavor-A discovery
        #   is window-based — no since→hours remap would be byte-identical, so we
        #   forward today's exact default call).
        return self._threads().find_threads()

    # -- PERSON INTEL --------------------------------------------------------
    def person_intel(self, slug: str) -> str:
        # → BrainAdapter.person_intel (officer_runner.py:371): draft_lib.person_intel(slug)
        return self._b().person_intel(slug)

    # -- COMMITMENTS ---------------------------------------------------------
    def open_commitments(self, direction: str) -> list:
        # → BrainAdapter.open_commitments (officer_runner.py:377):
        #   commitments_lib.load_all() filtered to non-closed rows in ``direction``.
        return self._b().open_commitments(direction)

    # -- IDENTITY PRIORS (PRIVATE — inform HOW to draft, never emitted) -------
    def voice_profile(self) -> str:
        # → BrainAdapter.voice_profile (officer_runner.py:399): draft_lib.voice_profile()
        return self._b().voice_profile()

    def model_patterns(self) -> str:
        # → BrainAdapter.nate_model_patterns (officer_runner.py:405):
        #   me_signal.nate_model("patterns"). PATTERNS layer ONLY (the newer-signal
        #   leak gotcha). The launcher-neutral method name maps to the brain
        #   artifact kept VERBATIM (DE-NATE §3). PRIVATE: informs judgment, never
        #   emitted.
        return self._b().nate_model_patterns()

    def drafting_lessons(self, before_ts: str) -> str:
        # → BrainAdapter.drafting_lessons (officer_runner.py:414): raw lessons text,
        #   date-filtered STRICTLY before before_ts via retro.lessons_before.
        #   PRIVATE: informs, never emitted.
        return self._b().drafting_lessons(before_ts)

    # -- RAW NOTE READ (vault-jailed) ----------------------------------------
    def read_note(self, path: str) -> str:
        # → BrainAdapter.read_note (officer_runner.py:436): an OBSIDIAN_VAULT_PATH
        #   realpath-contained read (refuses any path escaping the vault). The
        #   path-traversal jail is UNCHANGED — this shim adds no path handling.
        return self._b().read_note(path)
