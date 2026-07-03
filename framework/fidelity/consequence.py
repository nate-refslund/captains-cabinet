"""F0 — consequence-event emitter + ledger reader (shared fidelity infra).

Emits the normalized `consequence-event` shape
(framework/schemas/consequence-event.schema.json) to an append-only JSONL
ledger, validating every event against the real schema first. Graduation
math reads ONLY this ledger (see docs/consequence-ledger.md). This module is
the first consumer per docs/fidelity-harness-design-2026-06-18.md §5.

Storage mirrors framework/events/emitter.py BUT uses a DISTINCT filename
family so the two ledgers never collide in the shared dir: one file per UTC
day at $CABINET_EVENT_LOG_DIR/consequence-events-YYYY-MM-DD.jsonl,
json.dumps(event, default=str) + newline, append-only. (events/emitter.py
owns events-YYYY-MM-DD.jsonl in the same dir.) Enrichment (decision/outcome/
review landing later) is a SUPERSEDING event with the same
(actor, action, subject, ts) identity tuple; the reader takes the last write
per identity (last-write-wins).

System Python is 3.9.6 with no `jsonschema` dependency, so validation is
hand-rolled against this ONE schema (additionalProperties:false everywhere +
the three documented cross-field invariants).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from framework.authority.classifier import ACTION_TYPES


_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "schemas"
    / "consequence-event.schema.json"
)
SCHEMA: dict[str, Any] = json.loads(_SCHEMA_PATH.read_text())


class ConsequenceValidationError(ValueError):
    """Raised when a consequence event violates the schema or its invariants."""


def _consequence_log_dir() -> Path:
    """Resolve the JSONL consequence-ledger directory.

    Mirrors framework/events/emitter.py:_event_log_dir(): CABINET_EVENT_LOG_DIR
    wins; default is the durable per-user location (NOT /tmp, which is wiped).
    """
    return Path(os.environ.get(
        "CABINET_EVENT_LOG_DIR",
        os.path.expanduser("~/Library/Application Support/cabinet/events"),
    ))


_ACTOR_KINDS = {"pipe", "officer", "crew"}
_PROPOSAL_DECISIONS = {"approved", "edited", "rejected", "expired", None}
_OUTCOME_STATUSES = {"ok", "failed", "unknown"}
_REVIEW_VERDICTS = {"confirmed", "wrong", "unknown"}

# [B2.9] The refs directive a B2.8 verifier fabrication event carries. A single
# fresh occurrence demotes a cell DIRECTLY (no ≥2-divergent cluster wait) — a
# proven fabrication (success claimed while probes were reachable and recorded
# zero evidence; the verifier's RT#4 gate already excluded upstream-outage) is a
# one-sample demotion trigger. Owned here (the vocabulary module) so the verifier
# (emitter) and graduation (consumer) can never drift on the string.
DIRECT_DEMOTE_REF = "demote:direct"
# [T3] Optional F4 scorer-axis enums carried on the consequence event. They
# mirror scorer._DEC keys (decision) and scorer.judge_with_oauth (intent). A
# None / absent value is the unmeasured default. "" (intent layer did not run)
# and "error" are legal intent values — they mean decision-only, NOT a typo.
_DECISION_VERDICTS = {"match", "partial", "divergent", "error", "skipped", None}
_INTENT_VERDICTS = {"intent-aligned", "intent-partial", "intent-divergent",
                    "error", "", None}
# [FIX-1] The action_type enum is sourced from the ONE shared classifier
# (framework/authority/classifier.py) so the schema, this validator, the
# emit-time stamp, and the gate's verdict lookup can never drift apart. A None
# action_type is the unstamped/unmeasured default.
_ACTION_TYPES = set(ACTION_TYPES) | {None}

# Allowed keys per object (additionalProperties:false everywhere).
_ROOT_KEYS = {"ts", "actor", "lane", "action", "subject",
              "action_type", "refs", "proposal", "outcome", "review",
              # [T3] optional F4 scorer-axis fields.
              "decision_verdict", "intent_verdict", "intent_composite",
              "endorsement"}
_ROOT_REQUIRED = ("ts", "actor", "lane", "action", "subject")
_ACTOR_KEYS = {"kind", "id"}
_PROPOSAL_KEYS = {"required", "decision", "decided_at"}
_OUTCOME_KEYS = {"status", "evidence"}
_REVIEW_KEYS = {"verdict", "reviewed_at", "lesson_ref", "source"}
# review.source — WHO judged (flavor-A promotion split, 2026-07-03): only
# verdict_human confirms fuel promotion; verdict_judge (machine/LLM) and any
# other source can only hold or demote. "system" = non-judgment closures
# (auto-expiry / policy-only replies). Absent = legacy/unattributed — treated
# as NOT human by compute_ratios (fail-closed: an unattributed confirm can
# never fuel promotion).
_REVIEW_SOURCES = {"verdict_human", "verdict_judge", "system"}


def _reject_extra(obj: dict[str, Any], allowed: set[str], where: str) -> None:
    extra = set(obj) - allowed
    if extra:
        raise ConsequenceValidationError(
            f"{where}: additional properties not allowed: {sorted(extra)}"
        )


def validate_consequence(event: dict[str, Any]) -> None:
    """Validate a consequence event against the real schema + invariants.

    Raises ConsequenceValidationError on any violation; returns None on pass.
    Hand-rolled because system Python 3.9.6 has no jsonschema dependency.
    Enforces additionalProperties:false at every level + the three documented
    cross-field invariants (see docs/consequence-ledger.md).
    """
    if not isinstance(event, dict):
        raise ConsequenceValidationError("event must be an object")

    for key in _ROOT_REQUIRED:
        if key not in event:
            raise ConsequenceValidationError(f"missing required field: {key}")
    _reject_extra(event, _ROOT_KEYS, "root")

    # ts / action / subject: non-empty strings
    for key in ("ts", "action", "subject"):
        val = event[key]
        if not isinstance(val, str) or not val:
            raise ConsequenceValidationError(f"{key} must be a non-empty string")

    # lane: string | null
    if event["lane"] is not None and not isinstance(event["lane"], str):
        raise ConsequenceValidationError("lane must be a string or null")

    # action_type: optional enum string | null [FIX-1]. When present, it must
    # be a member of the shared classifier's ACTION_TYPES (or null). This is
    # the one source of truth — a value the classifier cannot emit is rejected.
    if "action_type" in event:
        at = event["action_type"]
        if at is not None and not isinstance(at, str):
            raise ConsequenceValidationError(
                "action_type must be a string or null"
            )
        if at not in _ACTION_TYPES:
            raise ConsequenceValidationError(
                f"action_type must be one of {sorted(a for a in _ACTION_TYPES if a)} or null"
            )

    # [T3] decision_verdict: optional enum string | null (scorer._DEC keys).
    if "decision_verdict" in event:
        dv = event["decision_verdict"]
        if dv is not None and not isinstance(dv, str):
            raise ConsequenceValidationError(
                "decision_verdict must be a string or null"
            )
        if dv not in _DECISION_VERDICTS:
            raise ConsequenceValidationError(
                "decision_verdict must be one of "
                f"{sorted(v for v in _DECISION_VERDICTS if v)} or null"
            )

    # [T3] intent_verdict: optional enum string | null. "" and "error" are
    # legal — they mean the intent layer did not run (decision-only path).
    if "intent_verdict" in event:
        iv = event["intent_verdict"]
        if iv is not None and not isinstance(iv, str):
            raise ConsequenceValidationError(
                "intent_verdict must be a string or null"
            )
        if iv not in _INTENT_VERDICTS:
            raise ConsequenceValidationError(
                "intent_verdict must be one of "
                f"{sorted(v for v in _INTENT_VERDICTS if v)}, '' or null"
            )

    # [T3] intent_composite: optional number in [0.0, 1.0] | null. bool is an
    # int subclass in Python — reject it explicitly so True/False can't pass.
    if "intent_composite" in event:
        ic = event["intent_composite"]
        if ic is not None:
            if isinstance(ic, bool) or not isinstance(ic, (int, float)):
                raise ConsequenceValidationError(
                    "intent_composite must be a number or null"
                )
            if not (0.0 <= float(ic) <= 1.0):
                raise ConsequenceValidationError(
                    "intent_composite must be within [0.0, 1.0]"
                )

    # [T3] endorsement: optional non-empty string | null. Loose string (not a
    # frozen enum) — the endorsement vocabulary is still being wired (design F4).
    if "endorsement" in event:
        en = event["endorsement"]
        if en is not None and (not isinstance(en, str) or not en):
            raise ConsequenceValidationError(
                "endorsement must be a non-empty string or null"
            )

    # actor
    actor = event["actor"]
    if not isinstance(actor, dict):
        raise ConsequenceValidationError("actor must be an object")
    for key in ("kind", "id"):
        if key not in actor:
            raise ConsequenceValidationError(f"actor: missing required field: {key}")
    _reject_extra(actor, _ACTOR_KEYS, "actor")
    if actor["kind"] not in _ACTOR_KINDS:
        raise ConsequenceValidationError(
            f"actor.kind must be one of {sorted(_ACTOR_KINDS)}"
        )
    if not isinstance(actor["id"], str) or not actor["id"]:
        raise ConsequenceValidationError("actor.id must be a non-empty string")

    # refs: array of strings (optional)
    if "refs" in event:
        refs = event["refs"]
        if not isinstance(refs, list) or not all(isinstance(r, str) for r in refs):
            raise ConsequenceValidationError("refs must be an array of strings")

    # proposal (optional)
    if "proposal" in event:
        prop = event["proposal"]
        if not isinstance(prop, dict):
            raise ConsequenceValidationError("proposal must be an object")
        if "required" not in prop:
            raise ConsequenceValidationError("proposal: missing required field: required")
        _reject_extra(prop, _PROPOSAL_KEYS, "proposal")
        if not isinstance(prop["required"], bool):
            raise ConsequenceValidationError("proposal.required must be a boolean")
        if prop.get("decision") not in _PROPOSAL_DECISIONS:
            raise ConsequenceValidationError(
                "proposal.decision must be one of "
                f"{sorted(d for d in _PROPOSAL_DECISIONS if d)} or null"
            )

    # outcome (optional)
    if "outcome" in event:
        outc = event["outcome"]
        if not isinstance(outc, dict):
            raise ConsequenceValidationError("outcome must be an object")
        if "status" not in outc:
            raise ConsequenceValidationError("outcome: missing required field: status")
        _reject_extra(outc, _OUTCOME_KEYS, "outcome")
        if outc["status"] not in _OUTCOME_STATUSES:
            raise ConsequenceValidationError(
                f"outcome.status must be one of {sorted(_OUTCOME_STATUSES)}"
            )

    # review (optional)
    if "review" in event:
        rev = event["review"]
        if not isinstance(rev, dict):
            raise ConsequenceValidationError("review must be an object")
        if "verdict" not in rev:
            raise ConsequenceValidationError("review: missing required field: verdict")
        _reject_extra(rev, _REVIEW_KEYS, "review")
        if rev["verdict"] not in _REVIEW_VERDICTS:
            raise ConsequenceValidationError(
                f"review.verdict must be one of {sorted(_REVIEW_VERDICTS)}"
            )
        if "source" in rev and rev["source"] not in _REVIEW_SOURCES:
            raise ConsequenceValidationError(
                f"review.source must be one of {sorted(_REVIEW_SOURCES)}"
            )

    _validate_invariants(event)


def _validate_invariants(event: dict[str, Any]) -> None:
    """The three cross-field rules the schema enum/required cannot express."""
    prop = event.get("proposal")
    if prop is not None:
        # decision may be non-null only when an approval gate exists.
        if prop.get("required") is False and prop.get("decision") is not None:
            raise ConsequenceValidationError(
                "proposal.decision must be null when proposal.required is false"
            )

    outc = event.get("outcome")
    if outc is not None:
        status = outc.get("status")
        evidence = outc.get("evidence")
        if status == "unknown" and evidence is not None:
            raise ConsequenceValidationError(
                "outcome.evidence must be null when status is 'unknown'"
            )
        if status in ("ok", "failed") and not evidence:
            raise ConsequenceValidationError(
                f"outcome.evidence must be present when status is '{status}'"
            )

    rev = event.get("review")
    if rev is not None:
        if rev.get("verdict") != "wrong" and rev.get("lesson_ref") is not None:
            raise ConsequenceValidationError(
                "review.lesson_ref must be null unless verdict is 'wrong'"
            )


def _write_to_log(event: dict[str, Any]) -> None:
    """Append one consequence event to the daily JSONL ledger (UTC date).

    Filename family is consequence-events-* (NOT events-*) so this ledger
    never collides with the org_events ledger written by events/emitter.py
    into the same CABINET_EVENT_LOG_DIR.

    Path safety (Corridor guardrail, minimal + consistent with
    framework/events/emitter.py's plain-env log-dir posture): the operator-set
    dir is resolved once with .resolve() and the ledger file is anchored under
    that resolved base, so the write always lands inside the intended dir. The
    basename is itself fixed and non-user-controlled — the only variable part is
    a strftime('%Y-%m-%d') date (digits + hyphens) — so no caller input can
    traverse out either. _consequence_log_dir()'s contract is unchanged (it
    still honors CABINET_EVENT_LOG_DIR verbatim); the resolve happens here, at
    the point of use.
    """
    log_dir = _consequence_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    base = log_dir.resolve()
    log_file = base / (
        "consequence-events-"
        + datetime.now(timezone.utc).strftime("%Y-%m-%d") + ".jsonl"
    )
    with open(log_file, "a") as f:
        f.write(json.dumps(event, default=str) + "\n")


_UNSET: Any = object()  # [T3] distinguishes "param not passed" from a falsy
# value the caller meant (intent_verdict="" / intent_composite=0.0): a real ""
# or 0.0 is WRITTEN, an unpassed param is DROPPED — see emit_consequence.


def emit_consequence(
    *,
    ts: str,
    actor: dict[str, Any],
    lane: str | None,
    action: str,
    subject: str,
    action_type: str | None = None,
    refs: list[str] | None = None,
    proposal: dict[str, Any] | None = None,
    outcome: dict[str, Any] | None = None,
    review: dict[str, Any] | None = None,
    decision_verdict: Any = _UNSET,
    intent_verdict: Any = _UNSET,
    intent_composite: Any = _UNSET,
    endorsement: Any = _UNSET,
) -> dict[str, Any]:
    """Validate then append-write ONE consequence event to the JSONL ledger.

    Keyword-only by design: the schema field set is wide and order-free, and
    every caller (F1 fidelity_events builder, live officers via the brain
    bridge, surviving pipes) must name fields explicitly. `refs` defaults to
    []. The optional objects (action_type/proposal/outcome/review) are emitted
    only when provided — a None value is dropped, not written as null, so the
    ledger carries exactly the lifecycle phase the caller has reached.
    Enrichment appends a SUPERSEDING event with the same
    (actor, action, subject, ts) identity; the reader takes the last write.

    `action_type` [FIX-1] is the first-class action-type enum the authority
    gate reads and graduation math keys on. It is STAMPED by the same shared
    `framework.authority.classifier.classify_action()` the gate uses, so the
    ledger and the verdict table can never disagree about what an action *is*.
    Stamp point: the live officer emit path is the external screenpipe
    brain-bridge governance hook (log_reasoning / record_run), which passes the
    raw tool call through `classify_action()` at emit time — that wiring lives
    outside this repo, in the screenpipe brain MCP. In-repo, the
    fidelity_events.py builders are the reachable emit surface and may pass
    `action_type` once the per-case raw tool call is available. When no caller
    supplies it, `action_type` is left ABSENT (the unstamped / unmeasured
    default) — never written as a literal null.

    [T3] The optional F4 scorer-axis scalars (decision_verdict / intent_verdict
    / intent_composite / endorsement) default to a private _UNSET sentinel, NOT
    None: a caller that genuinely means intent_verdict="" or intent_composite=
    0.0 has those WRITTEN, while a caller that omits them leaves them ABSENT.
    This keeps the unmeasured default visible (absent, never a silent null) and
    lets the F4 scoring-path emit carry the real falsy values when the intent
    layer ran but did not credit.
    """
    event: dict[str, Any] = {
        "ts": ts,
        "actor": actor,
        "lane": lane,
        "action": action,
        "subject": subject,
        "refs": list(refs) if refs is not None else [],
    }
    if action_type is not None:
        event["action_type"] = action_type
    if proposal is not None:
        event["proposal"] = proposal
    if outcome is not None:
        event["outcome"] = outcome
    if review is not None:
        event["review"] = review
    # [T3] Only the _UNSET sentinel is dropped; a real falsy value is written.
    if decision_verdict is not _UNSET:
        event["decision_verdict"] = decision_verdict
    if intent_verdict is not _UNSET:
        event["intent_verdict"] = intent_verdict
    if intent_composite is not _UNSET:
        event["intent_composite"] = intent_composite
    if endorsement is not _UNSET:
        event["endorsement"] = endorsement

    validate_consequence(event)  # raises before any write
    _write_to_log(event)
    return event


def _is_consequence_row(event: Any) -> bool:
    """True only for a row shaped like a consequence event (dict actor with a
    kind). Lets read_ledger skip a co-located org_events row (string actor)
    defensively, even though the distinct filename family makes a real
    collision impossible."""
    return (
        isinstance(event, dict)
        and isinstance(event.get("actor"), dict)
        and "action" in event
        and "subject" in event
    )


def _identity(event: dict[str, Any]) -> tuple[str, str, str, str]:
    """The last-write-wins identity tuple: (actor, action, subject, ts).

    actor is flattened to 'kind:id' so the full actor object participates in
    the identity exactly as docs/consequence-ledger.md specifies. Enrichment
    events carry the SAME tuple as the original; the reader keeps the last.
    """
    actor = event.get("actor")
    if isinstance(actor, dict):
        actor_id = f"{actor.get('kind')}:{actor.get('id')}"
    else:
        actor_id = f"{actor}:"  # defensive — non-dict actor never collides
    return (actor_id, event.get("action", ""), event.get("subject", ""),
            event.get("ts", ""))


def _safe_ledger_files(log_dir: Path) -> list[Path]:
    """Return the consequence-events-*.jsonl files inside log_dir, refusing any
    whose resolved real path escapes the resolved log dir.

    Corridor guardrail (beyond the plan, minimal + consistent with
    framework/events/emitter.py's plain-env log-dir posture): the log dir is
    operator-set, so we resolve it once and only read ledger files that
    genuinely live under it. A symlink planted in the dir that points outside
    the intended directory is skipped rather than followed — the glob never
    crosses the fence. We do not rewrite the _consequence_log_dir() contract
    (its return value still honors CABINET_EVENT_LOG_DIR verbatim); the fence
    is enforced here, at read time, where the untrusted file set is consumed.
    """
    base = log_dir.resolve()
    safe: list[Path] = []
    for log_file in sorted(log_dir.glob("consequence-events-*.jsonl")):
        try:
            real = log_file.resolve()
        except OSError:
            continue  # broken/cyclic symlink — skip, never crash
        # real must be base itself or strictly under it.
        if real == base or base in real.parents:
            safe.append(log_file)
    return safe


def read_ledger(since: str | None = None) -> list[dict[str, Any]]:
    """Read the consequence ledger, deduped by identity (last-write-wins).

    Reads every consequence-events-*.jsonl in $CABINET_EVENT_LOG_DIR, skips
    any non-consequence row, sorts chronologically by ts (ISO strings sort
    lexicographically), collapses each identity tuple to its LAST write, and
    returns the surviving events. `since` keeps only events with ts >= since
    (inclusive). Missing dir → []. The JSONL is the guaranteed record; this is
    the single read path graduation math uses.

    Symlinked ledger files that resolve outside the (resolved) log dir are
    skipped — relying on local file perms + the in-dir fence, never following a
    link that bypasses the intended directory (see _safe_ledger_files).
    """
    log_dir = _consequence_log_dir()
    if not log_dir.exists():
        return []

    rows: list[dict[str, Any]] = []
    for log_file in _safe_ledger_files(log_dir):
        with open(log_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if _is_consequence_row(ev):
                    rows.append(ev)

    # Stable sort by ts so last-write-wins respects chronology; equal-ts
    # writes keep file+line read order (a later enrichment line still wins).
    rows.sort(key=lambda e: e.get("ts", ""))

    collapsed: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for ev in rows:
        collapsed[_identity(ev)] = ev  # later assignment overwrites earlier

    events = list(collapsed.values())
    if since is not None:
        events = [e for e in events if e.get("ts", "") >= since]
    events.sort(key=lambda e: e.get("ts", ""))
    return events


# [FIX-1 step 3] Sentinel cell-key component for a ledger row that carries NO
# action_type (the unstamped / legacy default — action_type is an OPTIONAL
# schema field). Unstamped rows are keyed under this fixed, VISIBLE sentinel
# instead of falling back to their free-text `action`: a free-text string could
# literally equal an action_type enum value (e.g. "local_edit"), and a fallback
# would silently conflate an unstamped event into a MEASURED graduation cell —
# letting a cell light up autonomy on unstamped noise. The sentinel keeps
# unstamped data in one visible bucket that can NEVER graduate (the gate keys
# verdicts on real action_type enum values only), preserving the fail-closed
# spine and no-silent-caps (the bucket is visible, not silently 0/1). It is
# deliberately disjoint from the classifier's ACTION_TYPES enum (a leading
# "__" the classifier never emits), so the gate can never read it as a
# measurable cell.
UNSTAMPED_ACTION_TYPE = "__unstamped__"


@dataclass
class GraduationRatios:
    """The three graduation ratios for one (actor, lane, action_type) cell.

    The raw counts are dataclass FIELDS; the three rates are computed
    @property accessors (float | None) over them — a field and a same-named
    property cannot coexist. A rate is None when its denominator is 0 — an
    UNMEASURED dimension. Per docs/fidelity-harness-design-2026-06-18.md
    §"No-silent-caps", an unmeasured cell must read as a visible None, never a
    silent 0.0/1.0.
    """
    approved: int = 0
    edited: int = 0
    rejected: int = 0
    ok: int = 0
    failed: int = 0
    confirmed: int = 0
    wrong: int = 0
    sample_count: int = 0
    # [T3] F4 intent axis. intent_partial / error / "" / absent are EXCLUDED
    # from the denominator (like unknown verdicts are for review_confirmed_rate)
    # — only a credited (aligned) or a hard-divergent verdict scores the cell.
    intent_aligned: int = 0
    intent_divergent: int = 0

    @property
    def approval_unchanged_rate(self) -> float | None:
        denom = self.approved + self.edited + self.rejected
        return (self.approved / denom) if denom else None

    @property
    def outcome_held_rate(self) -> float | None:
        denom = self.ok + self.failed
        return (self.ok / denom) if denom else None

    @property
    def review_confirmed_rate(self) -> float | None:
        denom = self.confirmed + self.wrong
        return (self.confirmed / denom) if denom else None

    @property
    def intent_match_rate(self) -> float | None:
        """[T3] intent-aligned / (intent-aligned + intent-divergent).

        None when the denominator is 0 — an UNMEASURED intent dimension (no
        credited/divergent intent verdict yet). Per the no-silent-caps rule an
        unmeasured cell reads as a visible None, never a silent 0.0/1.0.
        intent-partial / error / "" are excluded from the denominator, exactly
        as unknown verdicts are excluded from review_confirmed_rate."""
        denom = self.intent_aligned + self.intent_divergent
        return (self.intent_aligned / denom) if denom else None


def compute_ratios(
    since: str | None = None,
    ledger: list[dict[str, Any]] | None = None,
) -> dict[tuple[str, str | None, str], GraduationRatios]:
    """Compute the three graduation ratios per (actor, lane, action_type) cell.

    [FIX-1 steps 3-4] Cells key on the `action_type` ENUM (stamped at emit time
    by the shared framework.authority.classifier.classify_action), NOT the
    free-text `action`. The matrix gate keys verdicts on action_type, so the
    ledger must agree — keying on the free text would forever miss the gate's
    lookup and autonomy could never light up. The raw `action` is retained on
    the event as a DESCRIPTIVE field but is no longer part of the cell key.

    Back-compat (the SAFE option): a row with NO action_type (the unstamped /
    legacy default) is keyed under the fixed visible sentinel
    UNSTAMPED_ACTION_TYPE — never under its free-text action. A fallback to the
    free text could collide with an action_type enum value and silently
    conflate unstamped noise into a measured cell that could then graduate; the
    sentinel keeps unstamped rows in one visible bucket that can never graduate
    (fail-closed + no-silent-caps).

    The consequence ledger is the ONLY input (no per-source special-casing).
    Events are read deduped via read_ledger() unless an explicit `ledger` is
    passed. Per cell:
      - approval-unchanged = approved / (approved + edited + rejected)
      - outcome-held       = ok / (ok + failed)
      - review-confirmed   = confirmed / (confirmed + wrong)
    Pending/expired proposals, unknown outcomes, and unknown verdicts are
    excluded from their denominators (not counted as failures).
    """
    events = ledger if ledger is not None else read_ledger(since=since)

    cells: dict[tuple[str, str | None, str], GraduationRatios] = {}
    for ev in events:
        actor = ev.get("actor") or {}
        actor_id = f"{actor.get('kind')}:{actor.get('id')}"
        # [FIX-1] Key on the action_type enum; an absent/None action_type (an
        # unstamped/legacy row) is bucketed under the sentinel, never its
        # free-text action — see UNSTAMPED_ACTION_TYPE for the fail-closed why.
        action_type = ev.get("action_type") or UNSTAMPED_ACTION_TYPE
        key = (actor_id, ev.get("lane"), action_type)
        cell = cells.setdefault(key, GraduationRatios())
        cell.sample_count += 1

        decision = (ev.get("proposal") or {}).get("decision")
        if decision == "approved":
            cell.approved += 1
        elif decision == "edited":
            cell.edited += 1
        elif decision == "rejected":
            cell.rejected += 1

        status = (ev.get("outcome") or {}).get("status")
        if status == "ok":
            cell.ok += 1
        elif status == "failed":
            cell.failed += 1

        # Flavor-A promotion split (2026-07-03): `confirmed` — the promotion
        # fuel — counts ONLY when a HUMAN judged it (review.source ==
        # "verdict_human"). A machine/LLM verdict (verdict_judge) or an
        # unattributed legacy row can never fuel promotion (fail-closed).
        # `wrong` counts from ANY source — machine evidence may demote/hold,
        # never promote. This asymmetry is the flavor-A contract.
        review = ev.get("review") or {}
        verdict = review.get("verdict")
        if verdict == "confirmed" and review.get("source") == "verdict_human":
            cell.confirmed += 1
        elif verdict == "wrong":
            cell.wrong += 1

        # [T3] Intent axis from the new optional field. intent-partial / error /
        # "" / absent score neither side (excluded from the denominator).
        intent_verdict = ev.get("intent_verdict")
        if intent_verdict == "intent-aligned":
            cell.intent_aligned += 1
        elif intent_verdict == "intent-divergent":
            cell.intent_divergent += 1

    return cells
