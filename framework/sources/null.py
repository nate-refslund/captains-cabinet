"""framework/sources/null.py — the fail-closed generic default adapter.

Binds when no ``sources.yml`` is configured (or it fails to parse / import) —
the same fail-closed doctrine as ``env.captain_name()`` → ``"Captain"`` and the
axes contract → ``guardian``. Generic, empty, NEVER crashes, NEVER leaks another
launcher's data: every gather returns thin honest empties (the officer sees
"(no admissible context)" lines, never a stack trace), ``read_note`` raises a
clear ``FileNotFoundError``, and every dispatch no-ops (the acting loop degrades
to draft-capture-only). A Flavor-B org deployment that wants real sensing binds
an ORG source implementing the SAME Protocol instead; one that wants none keeps
this. stdlib + typing ONLY — it does not import ``base`` (it satisfies the
Protocol structurally, via ``runtime_checkable``).
"""
from __future__ import annotations

from typing import Optional


class NullPersonalSource:
    """Fail-closed ``PersonalSource``: structurally satisfies
    ``base.PersonalSource`` (``runtime_checkable``) without importing it. Every
    read returns a generic empty; ``read_note`` raises (there is no note)."""

    def available(self) -> bool:
        return False

    def search(self, handle: str, *, topic: Optional[str] = None) -> dict:
        return {"hits": [], "topic_terms": None}

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

    def read_note(self, path: str) -> str:
        raise FileNotFoundError("no personal source configured")

    # --- ACTING / BRIEFING SURFACE (T1 protocol widen) -----------------------
    # Fail-closed: no estate ⇒ nothing awaits, nothing gathers, nothing drafts,
    # nothing is KNOWN. The two tri-state probes return None (honest unknown) —
    # a fabricated False from captain_replied_since would pin the draft lane's
    # stale proposals open past their age backstop, and a fabricated False from
    # still_awaiting would silently drop a just-drafted reply; None lets both
    # callers take their documented fail-safe path instead.
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
        return {}    # reads as healthy/quiet — a null box never alarms

    def briefing_commitments(self, direction: str = "owed_by_captain") -> list:
        return []


class NullPersonalDispatch:
    """Fail-closed ``PersonalDispatch``: every write no-ops (returns ``None``). A
    clean-room box has no dispatch backend, so the acting loop degrades to
    draft-capture-only — exactly today's behavior when ``env.allow_sends()`` is
    ``False``. Never raises, never sends, never writes."""

    def queue_draft(self, *args, **kw):
        return None

    def deliver(self, *args, **kw):
        return None

    def append_note(self, rel: str, body: str):
        return None

    def log_reasoning(self, **kw):
        return None

    # --- OUTBOUND PREP + VAULT NOTE WRITE (fail-closed) ---------------------
    def ensure_signature(self, text: str, channel: str) -> str:
        # No captain signature configured → return the draft unchanged.
        return text

    def write_daily_note(self, date: str, content: str) -> dict:
        # No vault on a clean-room box → skip (never create a stray note).
        return {"action": "skipped", "path": "", "reason": "no dispatch configured"}

    def daily_note_path(self, date: str) -> str:
        # A generic, vault-less path (endswith the canonical daily-note leaf so a
        # dry preview still renders a sensible target on a null deployment).
        return "1-Daily/" + str(date) + ".md"

    # --- Flavor-A backend accessors (concrete extras, not in the Protocol) --
    # The daily-recap pipe reaches the captain's board client + synthesis model
    # through these; a clean-room / Flavor-B box has neither, so they fail-close
    # (None / "") and the recap degrades to "nothing to recap".
    def monday(self):
        return None

    def llm_model(self) -> str:
        return ""
