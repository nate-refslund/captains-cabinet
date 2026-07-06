"""framework/sources/base.py — the personal-sensing seam's INTERFACE.

The launcher-neutral Protocols framework CORE depends on to OBSERVE (read) and
DISPATCH (write) the captain's personal world. Framework CORE imports THESE,
never a screenpipe ``_shared`` lib: the Flavor-A deployment binds a screenpipe
adapter that satisfies them, a clean-room / Flavor-B box binds the null adapter
(``framework/sources/null.py``) or an org source. Structural (``Protocol``) so
any of those satisfies the contract WITHOUT inheritance.

stdlib + typing ONLY — this module must stay importable on a box with no
screenpipe, no vault, no ``~/.screenpipe``. It names no backend; each method's
docstring records the Flavor-A call it maps to (the method-origin ledger,
source-adapter-boundary spec §4.1), which lives in the ADAPTER, not here.
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class PersonalSource(Protocol):
    """The captain's personal-sensing (READ) surface. Framework CORE depends on
    THIS, never on screenpipe. Flavor-A binds the screenpipe adapter; a
    clean-room / Flavor-B box binds ``NullPersonalSource`` or an org source."""

    def available(self) -> bool:
        """Cheap liveness probe (mirrors
        ``framework.fidelity.retro.retro_available()``). ``False`` ⇒ the caller
        degrades gracefully rather than crashing."""
        ...

    # --- OBSERVE / SEARCH (leak-scoped retrieval) --------------------------
    def search(self, handle: str, *, topic: Optional[str] = None) -> dict:
        """Leak-scoped vault retrieval for ``handle`` (optionally topic-aware).
        Returns ``{"hits": [{text, path|ref|heading, content_ts, ...}],
        "topic_terms": ...}``. Flavor-A: ``BrainAdapter.gather_vault``
        (officer_runner.py:346) / ``screenpipe_adapter.gather`` →
        ``context_lib.gather(handle, sources=["vault"], topic=topic)`` — Tier-1
        vault ONLY (never fans out to the live sent/screen/monday tiers)."""
        ...

    def find_reply_candidates(self, *, since: Optional[str] = None) -> list:
        """Threads awaiting the captain's reply (noise-filtered, should-reply
        gated). Flavor-A: ``screenpipe_adapter.find_threads`` → ``draft_lib``
        thread discovery."""
        ...

    # --- PERSON INTEL ------------------------------------------------------
    def person_intel(self, slug: str) -> str:
        """Dossier markdown for a counterparty ``slug``. Flavor-A:
        ``BrainAdapter.person_intel`` (officer_runner.py:371) →
        ``draft_lib.person_intel(slug)``."""
        ...

    # --- COMMITMENTS -------------------------------------------------------
    def open_commitments(self, direction: str) -> list:
        """Open commitments in ``direction`` (owed_by / owed_to the captain),
        open only. Flavor-A: ``BrainAdapter.open_commitments``
        (officer_runner.py:377) → ``commitments_lib.load_all(...)`` filtered to
        non-closed rows."""
        ...

    # --- IDENTITY PRIORS (PRIVATE — inform HOW to draft, never emitted) -----
    def voice_profile(self) -> str:
        """The captain's recency-weighted voice profile (``voice.md``).
        Flavor-A: ``BrainAdapter.voice_profile`` (officer_runner.py:399) →
        ``draft_lib.voice_profile()``. PRIVATE: informs tone, never emitted."""
        ...

    def model_patterns(self) -> str:
        """The captain-model PATTERNS layer — launcher-neutral method name.
        Flavor-A: ``BrainAdapter.nate_model_patterns`` (officer_runner.py:405) →
        ``me_signal.nate_model("patterns")``. PATTERNS layer ONLY (never
        core/memory — the newer-signal leak gotcha, officer_runner.py:405).
        PRIVATE: informs judgment, never emitted."""
        ...

    def drafting_lessons(self, before_ts: str) -> str:
        """Drafting lessons date-filtered STRICTLY before ``before_ts`` (a
        same-day lesson could postdate the reply moment and leak). Flavor-A:
        ``BrainAdapter.drafting_lessons`` (officer_runner.py:414) →
        ``retro.lessons_before(before_ts, ...)``. PRIVATE: informs, never
        emitted."""
        ...

    # --- RAW NOTE READ (vault-jailed) --------------------------------------
    def read_note(self, path: str) -> str:
        """Path-validated, vault-jailed raw note read. Flavor-A:
        ``BrainAdapter.read_note`` (officer_runner.py:436) → an
        ``OBSIDIAN_VAULT_PATH`` realpath-contained read (refuses any path that
        escapes the vault)."""
        ...


@runtime_checkable
class PersonalDispatch(Protocol):
    """The captain's personal-dispatch (WRITE) surface — a SIBLING seam kept
    bindable/nullable, but its authority semantics are UNCHANGED: the
    brain-bridge rule governs and ``env.allow_sends()`` gates every outbound. A
    null deployment binds ``NullPersonalDispatch`` (no-op) and the acting loop
    degrades to draft-capture-only — exactly today's dev/test behavior when
    ``allow_sends()`` is ``False``. External recipients stay per-item
    captain-approved in every posture (ACT-AND-DRAFT)."""

    def queue_draft(self, *args, **kw):
        """The ONLY outbound path (human-approval gated). Flavor-A: the brain
        ``queue_draft`` tool."""
        ...

    def deliver(self, *args, **kw):
        """Post-approval egress (``email_lib`` / ``teams_graph_lib``). Gated by
        ``env.allow_sends()``; never sends in dev/test."""
        ...

    def append_note(self, rel: str, body: str):
        """Vault WRITE — append-only (``append_agent_inbox`` / daily-note), the
        sole sanctioned write path into the vault."""
        ...

    def log_reasoning(self, **kw):
        """Agent-reasoning-log write (the governance trail). Flavor-A:
        ``agent_reasoning.log(...)``."""
        ...
