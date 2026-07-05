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
