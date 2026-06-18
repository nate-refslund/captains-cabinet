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
