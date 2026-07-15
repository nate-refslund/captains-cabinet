"""framework/sources/base.py — the personal-sensing seam's INTERFACE.

The launcher-neutral Protocols framework CORE depends on to OBSERVE (read) and
DISPATCH (write) the captain's personal world. Framework CORE imports THESE,
never a personal-source adapter's ``_shared`` lib: the Flavor-A deployment
binds a concrete personal-source adapter that satisfies them, a clean-room /
Flavor-B box binds the null adapter (``framework/sources/null.py``) or an org
source. Structural (``Protocol``) so any of those satisfies the contract
WITHOUT inheritance.

stdlib + typing ONLY — this module must stay importable on a box with no
personal-source adapter, no vault, no adapter-specific state dir. It names no
backend; each method's
docstring records the Flavor-A call it maps to (the method-origin ledger,
source-adapter-boundary spec §4.1), which lives in the ADAPTER, not here.
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class PersonalSource(Protocol):
    """The captain's personal-sensing (READ) surface. Framework CORE depends on
    THIS, never on any concrete adapter. Flavor-A binds a concrete
    personal-source adapter; a clean-room / Flavor-B box binds
    ``NullPersonalSource`` or an org source."""

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
        (officer_runner.py:346) / the adapter's ``gather`` →
        ``context_lib.gather(handle, sources=["vault"], topic=topic)`` — Tier-1
        vault ONLY (never fans out to the live sent/screen/monday tiers)."""
        ...

    def find_reply_candidates(self, *, since: Optional[str] = None) -> list:
        """Threads awaiting the captain's reply (noise-filtered, should-reply
        gated). Flavor-A: the adapter's ``find_threads`` → ``draft_lib``
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
        """Open commitments in ``direction`` — the CONTRACT values
        ``"owed_by_captain"`` / ``"owed_to_captain"`` (launcher-neutral; rows
        returned carry the same contract values in their ``direction`` field).
        Flavor-A: ``BrainAdapter.open_commitments`` (officer_runner.py:377) →
        ``commitments_lib.load_all(...)`` filtered to non-closed rows, the
        adapter mapping to/from its own internal storage values.
        Honest empty: ``[]``."""
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
        ``BrainAdapter.read_note`` (officer_runner.py:436) → a vault-root
        realpath-contained read (refuses any path that escapes the vault)."""
        ...

    # --- ACTING / BRIEFING SURFACE (T1 protocol widen, 2026-07-07) ----------
    # Every method the live lanes (run_draft_lane / morning_synthesis) call on
    # ``get_source()`` is IN the contract — no framework caller duck-types an
    # adapter extra. Each records its Flavor-A origin (the method-origin ledger,
    # source-adapter-boundary spec §4.1) and its HONEST-EMPTY contract: the
    # value a sourceless (null / clean-room) deployment returns — an empty that
    # degrades the caller gracefully, NEVER a fabricated observation.
    def find_threads(self, hours: int = 48) -> list:
        """Awaiting-reply threads from the last ``hours`` — noise-filtered
        thread dicts (person / slug / last / audience …), the live lanes'
        windowed sibling of ``find_reply_candidates``. Flavor-A:
        ``flavor_a.acting.find_threads(hours=…)`` (draft_lib thread discovery +
        skip-list / calendar-invite / chair-lock exclusions). Honest empty:
        ``[]`` — no estate ⇒ nothing awaits."""
        ...

    def gather(self, thread: dict, *, do_prep: bool = True) -> dict:
        """Investigate-then-draft context for one ``thread`` (intel / brain
        hits / commitments / gate / prep). Flavor-A: ``flavor_a.acting.gather``.
        Honest empty: ``{}`` — ``draft_fn`` declines on an empty context, so an
        empty gather can never seed a fabricated draft."""
        ...

    def draft_fn(self, thread: dict, ctx: dict,
                 *, min_confidence: float = 0.0) -> Optional[str]:
        """A ready-to-present draft reply in the captain's voice for ``thread``
        given ``ctx`` (from ``gather``), or ``''``/``None`` to decline (gate
        refused / thin context / below ``min_confidence``). Flavor-A:
        ``flavor_a.acting.draft_fn``. Honest empty: ``''`` (a decline — never a
        fabricated draft)."""
        ...

    def captain_replied_since(self, slug: str, when) -> Optional[bool]:
        """Did the CAPTAIN send an outbound message on the ``slug`` thread
        STRICTLY after ``when`` (tz-aware datetime, or ``None``)? Tri-state:
        ``True`` = positively saw a newer captain reply; ``False`` = the
        conversation was readable and positively showed none; ``None`` = cannot
        know. The launcher-neutral CONTRACT name — Flavor-A:
        ``flavor_a.acting.nate_replied_since`` (the adapter keeps that name as
        a back-compat alias). Honest empty: ``None`` — a sourceless deployment
        must never fabricate ``False`` (it would pin run_draft_lane's stale
        proposals open past their age backstop) nor ``True`` (it would expire
        real ones)."""
        ...

    def still_awaiting(self, slug: str, hours: int = 72) -> Optional[bool]:
        """Is the ``slug`` thread STILL awaiting the captain's reply right now
        (same authority as ``find_threads``, re-checked live)? Tri-state like
        ``captain_replied_since``; callers fail-safe on ``None`` (surface the
        draft, never suppress on uncertainty). Flavor-A:
        ``flavor_a.acting.still_awaiting``. Honest empty: ``None`` — never a
        fabricated ``False`` (would silently drop a just-drafted reply) nor
        ``True``."""
        ...

    def deploy_health(self, app: str, limit: int = 8) -> dict:
        """Deploy health for the captain's app ``app`` — latest deploy state +
        recent failures (e.g. ``{"latest_state": …, "failed": […]}``).
        Flavor-A: ``flavor_a.acting.deploy_health`` (Vercel via the captain's
        estate). Honest empty: ``{}`` — reads as healthy/quiet, so a sourceless
        deployment stays silent rather than alarming."""
        ...

    def briefing_commitments(self, direction: str = "owed_by_captain") -> list:
        """Open commitments for the BRIEFING lanes — the acting-surface
        ``status == "open"`` filter, distinct from ``open_commitments``'s
        closed-set filter. ``direction`` takes (and returned rows carry) the
        same CONTRACT values as ``open_commitments``. Flavor-A:
        ``flavor_a.acting.open_commitments``. Honest empty: ``[]``."""
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

    # --- OUTBOUND PREP + VAULT NOTE WRITE (the frontdoor egress seam) --------
    def ensure_signature(self, text: str, channel: str) -> str:
        """Close an outbound draft with the captain's default signature
        (idempotent — never double-signs; email only, never a Teams message).
        Flavor-A: ``draft_lib.ensure_signature``. A deployment with no signature
        (the null/clean-room dispatch) returns ``text`` unchanged."""
        ...

    def write_daily_note(self, date: str, content: str) -> dict:
        """Write the captain's daily note (``1-Daily/<date>.md``) **only when its
        bytes changed** (sha256 compare — the vault-sync hash-match invariant),
        under the deployment's vault root. Returns
        ``{"action": written|unchanged|skipped, "path": ...}``. The sole sanctioned
        full-note write path; a null/clean-room dispatch skips (no vault)."""
        ...

    def daily_note_path(self, date: str) -> str:
        """The path the daily note WOULD be written to for ``date`` (for a dry
        preview — no write). A null/clean-room dispatch returns a generic path."""
        ...
