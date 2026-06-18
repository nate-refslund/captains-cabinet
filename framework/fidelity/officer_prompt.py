"""Eval-mode prompt assembly for the officer-under-test.

Builds the system prompt (officer role definition + decision-type context) and
the cutoff-safe situation text from a Case's thread_before. The held-out reply
(case.real_reply) is NEVER included anywhere in the prompt — that is the ground
truth the officer must reconstruct blind."""

from __future__ import annotations

import os
import re
from pathlib import Path

from framework.fidelity.types import Case

_REPO_ROOT = Path(
    os.environ.get("CABINET_ROOT", str(Path(__file__).resolve().parents[2]))
)
_AGENTS_DIR = _REPO_ROOT / ".claude" / "agents"


def role_definition(officer_role: str) -> str:
    """Read .claude/agents/<role>.md (the runtime-populated officer charter dir,
    set by load-preset.sh as $CABINET_ROOT/.claude/agents). If absent (eval
    running before the preset is loaded), return a minimal header — never crash
    the eval."""
    f = _AGENTS_DIR / f"{officer_role}.md"
    if f.exists():
        return f.read_text(errors="replace")
    return (f"# Officer: {officer_role}\n"
            "You are a Cabinet officer making a decision under the "
            "courses-of-action rule. (Role definition file not found; deciding "
            "from charter conventions.)")


def build_eval_system(case: Case, officer_role: str) -> str:
    """Role definition + a decision-type context block. No held-out reply."""
    ctx = (f"\n\n# DECISION CONTEXT\nlane: {case.lane}\n"
           f"decision_type: {case.decision_type}\n"
           f"counterparty: {case.person} (channel: {case.channel}, "
           f"language: {case.language})")
    return role_definition(officer_role) + ctx


def _clean(text: str) -> str:
    body = re.sub(r"<!--[^>]*-->", "", text or "")
    return re.sub(r"_\([^)]*\)_", "", body).strip()


def format_situation(case: Case, last_cap: int = 1500, cap: int = 600) -> str:
    """Oldest-first situation text from thread_before only. Sent → 'Nate:',
    received → the sender's display name. The last message keeps more body."""
    msgs = case.thread_before
    lines = [f"# HELD-OUT SITUATION (decide as-of {case.cutoff_ts})",
             "The conversation below ends just before Nate replied. Draft the "
             "reply Nate would have sent at that moment.\n"]
    for i, m in enumerate(msgs):
        who = "Nate" if m.get("direction") == "sent" else \
            (m.get("who") or "").split("<")[0].strip() or case.person
        body = _clean(m.get("text") or "")
        limit = last_cap if i == len(msgs) - 1 else cap
        lines.append(f"[{(m.get('date') or '')[:16]} {m.get('source', '')}] "
                     f"{who}: {body[:limit]}")
    return "\n".join(lines)
