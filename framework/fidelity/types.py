"""Dataclasses for the fidelity harness (Case, OfficerDecision).

Case mirrors docs/fidelity-harness-design-2026-06-18.md §96-98 plus the
retrodiction-derived context needed to drive + score the reply cell.
OfficerDecision is the captain-facing capture from officer_runner (§121-125).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Case:
    case_id: str
    lane: str
    decision_type: str
    situation_ref: str
    ground_truth: dict[str, Any]
    endorsement: str
    cutoff_ts: str
    source: str
    held_out: bool
    # retrodiction-derived context for the reply cell
    slug: str = ""
    person: str = ""
    channel: str = ""
    language: str = ""
    thread_before: list[dict] = field(default_factory=list)
    real_reply: str = ""
    # F4 §1.6: reconstructed as-of-cutoff intent (mission/goal × core). Default
    # "", computed lazily by intent_and_context at score time if empty. NEVER
    # populated from real_reply (the held-out ground truth) — anti-leak boundary.
    intent: str = ""

    @classmethod
    def from_retro_case(cls, rc: dict, lane: str = "send-1to1-reply",
                        decision_type: str = "reply") -> "Case":
        """Build a Case from a retrodiction extract_cases() dict. cutoff_ts is
        the held-out reply timestamp — the sacred anti-leakage boundary."""
        return cls(
            case_id=rc["case_id"],
            lane=lane,
            decision_type=decision_type,
            situation_ref=rc.get("reply_key", rc["case_id"]),
            ground_truth={"real_reply": rc["real_reply"]},
            endorsement="unknown",
            cutoff_ts=rc["reply_ts"],
            source="retrodiction",
            held_out=True,
            slug=rc.get("slug", ""),
            person=rc.get("person", ""),
            channel=rc.get("channel", ""),
            language=rc.get("language", ""),
            thread_before=rc.get("thread_before", []),
            real_reply=rc["real_reply"],
        )

    def to_retro_case(self) -> dict:
        """Project back to the dict shape retrodiction's score_case/judge expect."""
        return {
            "case_id": self.case_id,
            "reply_key": self.situation_ref,
            "slug": self.slug,
            "person": self.person,
            "channel": self.channel,
            "language": self.language,
            "reply_ts": self.cutoff_ts,
            "thread_before": self.thread_before,
            "real_reply": self.real_reply,
        }


@dataclass
class OfficerDecision:
    decision: dict | str
    rationale: str
    chain: list[dict] = field(default_factory=list)


@dataclass
class DecisionCase:
    """A held-out Captain DECISION case (the F3-intent cell,
    docs/fidelity-decision-cell-design-2026-06-20.md). Unlike the reply Case
    (a thread → a message), a decision case is a judgment call: a ``dilemma``
    (the decision point with the Captain's choice REMOVED — what the clone sees)
    and the held-out ground truth ``decision`` + ``why`` (the Captain's actual
    call + their rationale, the intent). ``detected_at`` is the real decision
    timestamp = the leak cutoff. The clone never sees ``decision``/``why``; the
    judge does."""
    case_id: str
    detected_at: str          # real decision timestamp = leak cutoff
    app: str
    dilemma: str              # decision point, the Captain's choice removed (clone input)
    decision: str             # GROUND TRUTH — what the Captain chose (held out from clone)
    why: str                  # GROUND TRUTH — the Captain's rationale / intent (held out)
    source: str = "decisions-corpus"
