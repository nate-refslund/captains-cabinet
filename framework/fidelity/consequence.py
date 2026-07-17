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
import sys
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


class SimQuarantineError(RuntimeError):
    """[SIE-7] Raised when a write would cross the sim/live quarantine fence — a
    sim-marked event aimed at a live dir, or a live event aimed at a '-sim' dir.
    The two must always agree, so simulated consequences can never contaminate
    the live graduation/breaker/cell math the Captain's real verdicts feed."""


def _sim_mode() -> bool:
    """[SIE-7] True in a replay-simulation process (CABINET_SIM_MODE=1). Off by
    default, so every live emit/read behaves exactly as before."""
    return os.environ.get("CABINET_SIM_MODE") == "1"


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
              "endorsement",
              # [SIE-7] quarantine marker (present-and-true only on sim rows).
              "sim"}
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
# never fuel promotion). "verdict_gate" [D16, sovereign spec 2026-07-04] =
# the machine evidence-gate (stamped only for acted rows clearing its full
# 5-condition bar, framework/learning/gate.py run_gate_review); its confirms
# fuel promotion ONLY while the deployment posture resolves sovereign AT
# COMPUTE TIME — guardian ignores them (EARN-DEMOTION-safe), wrong from any
# source still demotes. [CG-1 Option B, ruled 2026-07-07] further scopes gate
# fuel to deterministic-inverse machine evidence in label-floor-met periods
# (see compute_ratios); the judge-calibration >=0.8 precondition attaches to
# verdict_judge (its confirms stay promotion-inert until CG-10 rules
# otherwise on calibration proof).
_REVIEW_SOURCES = {"verdict_human", "verdict_judge", "system", "verdict_gate"}


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

    # [SIE-7] sim: optional quarantine marker. When present it must be the bool
    # True — a row either carries sim:true or omits the key; sim:false / other
    # values are rejected so the marker is never ambiguous. (bool is checked
    # before value since isinstance(True, int) is a Python footgun.)
    if "sim" in event:
        if event["sim"] is not True:
            raise ConsequenceValidationError(
                "sim, when present, must be the boolean true (or omitted)"
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
    # [SIE-7] Quarantine fence — the ONE structural chokepoint. The event's sim
    # marker MUST agree with the target dir's '-sim' suffix. This refuses a
    # sim-marked row aimed at a live dir (sim can never write to live) AND a
    # non-sim row aimed at a '-sim' dir (the sim ledger stays unambiguously
    # all-sim). It reads no env — pure marker↔dir agreement — so no write path
    # can bypass it, and live writes (marker absent, dir not '-sim') are
    # untouched: False == False passes exactly as before.
    is_sim_dir = base.name.endswith("-sim")
    has_marker = bool(event.get("sim"))
    if has_marker != is_sim_dir:
        raise SimQuarantineError(
            f"quarantine fence: sim-marker={has_marker} but target dir "
            f"{base.name!r} is_sim={is_sim_dir} — refusing the write "
            f"(sim consequences must stay in a '-sim' dir; live rows must not)"
        )
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
    Stamp point: the live officer emit path is the external personal-source
    brain-bridge governance hook (log_reasoning / record_run), which passes the
    raw tool call through `classify_action()` at emit time — that wiring lives
    outside this repo, in the personal-source brain MCP. In-repo, the
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
    # [SIE-7] Stamp the quarantine marker in a sim process so validate + the
    # write chokepoint see it. Live emits (the default) never carry it.
    if _sim_mode():
        event["sim"] = True

    # Evidence mirror reservation (Phase 2, observation-only). Live
    # lifecycle rows (proposal/outcome/review present, no sim marker — see
    # framework/evidence_mirror.py doctrine) get ONE namespaced ref
    # ('evidence-trial:<day-trial-id>') appended here at the chokepoint —
    # never at call sites — so superseding enrichment rows, rebuilt fresh
    # from action records, re-carry the reverse-correlation ref. The ref is
    # identity-free for attention canonical_refs and never equals
    # DIRECT_DEMOTE_REF. The domain validate + write below KEEP raising:
    # act lanes rely on ledger-first fail-closed order.
    evidence_mirror = None
    mirror_slot = None
    try:
        from framework import evidence_mirror  # type: ignore
        mirror_slot = evidence_mirror.reserve_consequence(event)
        if mirror_slot:
            event["refs"] = list(event.get("refs") or []) + [mirror_slot["ref"]]
    except ImportError:
        pass
    except Exception as exc:  # reservation must never block the domain write
        mirror_slot = None
        print(f"consequence: WARN evidence mirror reserve failed: {exc}", file=sys.stderr)

    validate_consequence(event)  # raises before any write
    _write_to_log(event)

    # Evidence mirror receipt — strictly AFTER the domain append succeeded,
    # so refused rows (validation error, SimQuarantineError inside
    # _write_to_log) are never mirrored. Receipts are telemetry: recorder
    # failure degrades LOUD inside the module and never blocks this return.
    if mirror_slot and evidence_mirror is not None:
        try:
            evidence_mirror.mirror_consequence(event, mirror_slot)
        except Exception as exc:  # pragma: no cover — module degrades internally
            print(f"consequence: WARN evidence mirror failed: {exc}", file=sys.stderr)
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

    # [SIE-7] Defense in depth: a live consumer NEVER sees a sim row. The write
    # fence already keeps sim rows out of live dirs, but if a misconfigured or
    # legacy mixed dir ever held one, dropping it here guarantees it can't enter
    # graduation/breaker/cell math. A sim process (CABINET_SIM_MODE=1) keeps
    # them — the sim runner is the one legitimate reader of sim rows.
    if not _sim_mode():
        rows = [ev for ev in rows if not ev.get("sim")]

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


def _gate_confirms_now() -> bool:
    """[D16] True iff a verdict_gate confirm may fuel promotion RIGHT NOW —
    i.e. the deployment posture resolves sovereign at compute time.

    Lazy import + blanket except: on ANY failure (module absent, posture file
    unreadable, unexpected error) the answer is False ⇒ guardian ⇒ compute is
    bit-identical to the pre-posture world. Read at compute time (never cached
    across calls) so a sovereign→guardian flip only ever REDUCES confirmed
    counts — machine promotion fuel can be revoked, never grandfathered."""
    try:
        from framework.authority.posture import resolve_posture
        return resolve_posture() == "sovereign"
    except Exception:
        return False


def _det_inverse_gate_fuel_types() -> frozenset[str]:
    """[CG-1 Option B, ruled 2026-07-07] The action_types whose acted machine
    evidence is DETERMINISTIC-INVERSE-backed — the ONLY types whose
    `verdict_gate` confirms may mint promotion fuel.

    Derived from the EXISTING inverse representation (nothing new is invented):
    `action_undo.act_first_eligible(kind, backend)` — a registered, non-``none``
    inverse in `action_undo.inverse_for`'s registry, probed with the sanctioned
    kind-fallback backend (the same convention the policy-engine eligibility
    probe uses, see action_undo.py's GERMLINE WIDENING note). Two legs cover
    the whole stamping surface:

      1. classifier action_types that ARE inverse-registered step kinds
         themselves (the reversible kinds: task_status_move / label /
         tier2_note / local_edit);
      2. proposer-lane step kinds (action_lane.ACTION_TYPE_MAP) mapped to the
         action_type their acted rows stamp (e.g. monday_task_create →
         task_create). A kind whose inverse is op ``none`` (delegate_work,
         investigation_run) admits nothing.

    Note the kind-fallback probe deliberately ignores per-backend exclusions
    (e.g. apple_reminders): an excluded backend never acts unattended in the
    first place (act-time perimeter, ACT_FIRST_EXCLUDED_BACKENDS), so no
    ttl_ok row for it can exist to be counted here.

    Fail-closed: ANY import or probe failure yields the empty set — no
    deterministic-inverse proof, no gate fuel. Lazy imports keep the guardian
    world (and lib-less trust-path installs) from ever touching the frontdoor
    modules; by the time this runs, consequence is fully loaded, so the
    action_undo → consequence import cycle is inert.
    """
    try:
        from framework.acting.action_lane import ACTION_TYPE_MAP
        from framework.frontdoor.action_undo import act_first_eligible
    except Exception:
        return frozenset()
    admissible: set[str] = set()
    for at in ACTION_TYPES:
        try:
            if act_first_eligible(at, at):
                admissible.add(at)
        except Exception:
            continue
    for kind, at in ACTION_TYPE_MAP.items():
        try:
            if at in ACTION_TYPES and act_first_eligible(kind, kind):
                admissible.add(at)
        except Exception:
            continue
    return frozenset(admissible)


def _label_floor_met(ts: str) -> bool:
    """[CG-1 Option B, ruled 2026-07-07] True iff the period containing `ts`
    met the Captain attention-contract label floor (the A3 sensor: N
    stratified-random cards/day answered at 100%, per the operative egg plan).

    The A3 sensor DOES NOT EXIST YET. Until it lands and is wired through
    this seam, NO period is label-floor-met — so ttl_ok-derived machine
    confirms (every `verdict_gate` confirm rides a ttl_ok row by the gate's
    5-condition bar) count toward promotion in exactly zero periods. That is
    the ruling's intent: silence from an absent Captain is never promotion
    fuel; machine evidence may only fuel promotion inside periods where the
    human labeling channel was demonstrably alive. Fail-closed by
    construction — wiring A3 here can only ever WIDEN from zero under a
    later, explicit change; absence narrows.
    """
    return False


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

    [D16] `confirmed` counts review.source == "verdict_human" always, plus
    "verdict_gate" IFF the posture resolves sovereign at compute time (lazy,
    fail-closed to guardian — see _gate_confirms_now). `wrong` counts from any
    source, both postures.

    [CG-1 Option B, ruled 2026-07-07] The verdict_gate leg is further scoped:
    a gate confirm counts ONLY when its action_type is deterministic-inverse-
    backed (_det_inverse_gate_fuel_types — the existing undo registry) AND its
    period met the Captain label floor (_label_floor_met — the A3 seam,
    fail-closed False until the sensor exists). The judge-calibration >=0.8
    precondition attaches to verdict_judge, whose confirms remain promotion-
    inert here regardless (see the branch comment below).
    """
    events = ledger if ledger is not None else read_ledger(since=since)

    # [D16] Whether verdict_gate confirms count — resolved LAZILY on the first
    # gate-sourced confirm and memoized for THIS compute only (one posture read
    # per compute, at compute time). A ledger with no verdict_gate rows never
    # touches the posture module at all (guardian world bit-identical).
    gate_sovereign = None
    # [CG-1 Option B] The deterministic-inverse admissible set, same laziness:
    # derived only after sovereign resolves, memoized for THIS compute, so
    # guardian (and gate-row-less) computes never import the undo registry.
    gate_fuel_types = None

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
        # [D16] SOLE extension: a "verdict_gate" confirm (the machine evidence
        # gate) also fuels promotion, but ONLY while the posture resolves
        # sovereign at compute time — guardian keeps ignoring it, so a flip
        # back to guardian revokes gate fuel on the very next compute.
        #
        # [CG-1 Option B, ruled 2026-07-07 — captain-decisions.md] The D5/D16
        # promotion-fuel reconcile, strictly narrowing D16's branch:
        #   (b) a gate confirm counts ONLY for DETERMINISTIC-INVERSE machine
        #       evidence — the row's action_type must be admissible per the
        #       existing undo registry (_det_inverse_gate_fuel_types); any
        #       other machine evidence (internal_message etc.) is inert;
        #   (c) ttl_ok counts toward promotion ONLY in label-floor-met
        #       periods (_label_floor_met over the row's ts) — every gate
        #       confirm is ttl_ok-derived by run_gate_review's bar, so the
        #       floor gates the whole branch.
        # The judge-calibration >=0.8 precondition attaches to verdict_judge
        # (comment, not mechanism): verdict_judge confirms stay promotion-
        # inert here, and any future admission of calibrated judge confirms
        # (the separate CG-10 germline amendment) is preconditioned on
        # judge-calibration >=0.8 proven — never on this branch as-is.
        review = ev.get("review") or {}
        verdict = review.get("verdict")
        source = review.get("source")
        if verdict == "confirmed":
            if source == "verdict_human":
                cell.confirmed += 1
            elif source == "verdict_gate":
                if gate_sovereign is None:
                    gate_sovereign = _gate_confirms_now()
                if gate_sovereign:
                    if gate_fuel_types is None:
                        gate_fuel_types = _det_inverse_gate_fuel_types()
                    if action_type in gate_fuel_types and \
                            _label_floor_met(str(ev.get("ts") or "")):
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
