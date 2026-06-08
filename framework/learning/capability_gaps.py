"""Self-extension loop — capability gaps → auto-skill or propose-then-approve.

When an officer hits a wall it can't solve with current tools (or the loop
infers a recurring manual workaround), that's a *capability gap*. This module
records gaps, dedups recurring ones, classifies them, and gates what the
Cabinet may do on its own:

  - procedure  → auto-skilled (draft → eval gate → promote). Human never asked.
  - tool       → proposal DM'd to Captain. Nothing installs without approval.
  - integration→ same as tool.

SAFETY — the two invariants that make "build it and iterate" responsible:

  1. The INSTALL GATE FAILS CLOSED. `can_install()` returns True only when a
     verified `capability_gap_approved` event exists for that gap AND nothing
     it touches is on the hard ceiling. Any exception / missing data / ambiguity
     → False. No approval, no install, ever — even on a bug.

  2. EVERYTHING ELSE FAILS HARMLESS. A bad gap is a ledger row. A misclassified
     gap is one extra Captain tap (we err toward propose) or a skill draft that
     fails its eval. Worst case minus the gate = a need goes unmet, i.e. today.

Event-sourced (no new table): gap state is projected by replaying
capability_gap_* events from framework.events.

Usage:
    from framework.learning.capability_gaps import (
        record_gap, classify, project_gaps, load_autonomy, can_auto_apply,
        can_install, propose_gap, approve_gap, decline_gap, resolve_gap,
    )
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_FRAMEWORK_ROOT = str(Path(__file__).parent.parent.parent)
if _FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_ROOT)

from framework.events.emitter import emit, replay  # noqa: E402

try:
    from yaml import safe_load as _yaml_load
except ImportError:  # pragma: no cover - yaml present in cabinet runtime
    _yaml_load = None


# ---------------------------------------------------------------------------
# Kinds + status
# ---------------------------------------------------------------------------

VALID_KINDS = ("procedure", "tool", "integration")

# Status lifecycle (projected from events):
#   open → classified → (procedure) auto_skilling → skilled → resolved
#                     → (tool|integration) pending_captain → approved → resolved
#                                                          → declined
STATUS_OPEN = "open"
STATUS_CLASSIFIED = "classified"
STATUS_AUTO_SKILLING = "auto_skilling"
STATUS_SKILLED = "skilled"
STATUS_PENDING = "pending_captain"
STATUS_APPROVED = "approved"
STATUS_DECLINED = "declined"
STATUS_RESOLVED = "resolved"


# ---------------------------------------------------------------------------
# Hard ceiling — the non-negotiable safety floor
# ---------------------------------------------------------------------------

# These can never auto-apply, regardless of autonomy.yml. Mirrored from
# autonomy.yml.example → hard_ceiling.always_propose_if_touches. Kept here as
# the code-level backstop so a misconfigured / missing autonomy.yml CANNOT
# weaken the floor (fail-closed defense in depth).
HARD_CEILING_TOUCHES = frozenset({
    "secrets",
    "spending",
    "external_comms",
    "production",
    "network_write",
    "credentials_grant",
})

# Keyword → touch inference. Used when a gap/proposal doesn't declare `touches`
# explicitly. Conservative: a hit means we assume the touch is present.
_TOUCH_KEYWORDS: dict[str, tuple[str, ...]] = {
    "secrets": ("secret", "api key", "api-key", "token", "credential", "password", "auth key"),
    "spending": ("payment", "billing", "charge", "purchase", "spend", "invoice", "stripe charge", "subscription"),
    "external_comms": ("send email", "send message", "post to", "tweet", "publish", "notify customer", "outbound"),
    "production": ("production", "prod ", "prod deploy", "live deploy", "prod db", "production database"),
    "network_write": ("post ", "put ", "delete ", "write to api", "create resource", "mutate", "upload to"),
    "credentials_grant": ("oauth", "grant scope", "new permission", "authorize app", "access token grant"),
}


# ---------------------------------------------------------------------------
# Classification (safe-default: propose)
# ---------------------------------------------------------------------------

# A gap is a PROCEDURE (auto-skillable) when it's about how-to / process /
# sequence with no new external capability. It needs a TOOL/INTEGRATION when
# it references code, APIs, external systems, data sources, credentials, etc.
_PROCEDURE_HINTS = (
    "how to", "how do", "process for", "checklist", "steps to", "workflow",
    "procedure", "convention", "remember to", "best way to", "standard for",
)
_TOOL_HINTS = (
    "api", "integration", "connect to", "credential", "auth", "fetch from",
    "pull from", "query the", "scrape", "external", "webhook", "mcp", "sdk",
    "database", "service", "platform", "endpoint", "token",
)


def classify(need: str, evidence: str = "", ambiguous_default: str = "tool") -> str:
    """Classify a gap into procedure | tool | integration.

    Safe default: when signals are mixed/absent, return a *propose* kind
    (tool), never *auto* (procedure). Erring toward human-in-loop.
    """
    text = f"{need} {evidence}".lower()
    proc = sum(1 for h in _PROCEDURE_HINTS if h in text)
    tool = sum(1 for h in _TOOL_HINTS if h in text)

    # "integration" if it names an external system hookup AND auth/config.
    integ_signal = ("integration" in text or "connect to" in text) and (
        "auth" in text or "oauth" in text or "credential" in text or "token" in text
    )

    if tool > proc:
        return "integration" if integ_signal else "tool"
    if proc > tool:
        return "procedure"
    # Tie or both zero → ambiguous → safe default (propose). Never 'procedure'.
    if ambiguous_default not in VALID_KINDS:
        ambiguous_default = "tool"
    return "integration" if (integ_signal and ambiguous_default != "procedure") else ambiguous_default


def infer_touches(need: str, evidence: str = "", declared: list[str] | None = None) -> set[str]:
    """Infer which hard-ceiling categories a gap/proposal touches.

    Union of explicitly declared touches + keyword-inferred ones. Conservative
    by design — a keyword hit counts as a touch (false positives just add a
    Captain tap; false negatives would be unsafe).
    """
    touches: set[str] = set(declared or [])
    text = f"{need} {evidence}".lower()
    for touch, kws in _TOUCH_KEYWORDS.items():
        if any(kw in text for kw in kws):
            touches.add(touch)
    return touches


# ---------------------------------------------------------------------------
# Autonomy policy
# ---------------------------------------------------------------------------

@dataclass
class AutonomyPolicy:
    defaults: dict[str, str] = field(default_factory=lambda: {
        "procedure": "auto", "tool": "propose", "integration": "propose",
    })
    graduation_enabled: bool = False
    auto_after_clean_approvals: int = 10
    ambiguous_defaults_to: str = "propose"
    # The hard ceiling is ALWAYS HARD_CEILING_TOUCHES regardless of file — the
    # file can only widen it, never narrow it.
    extra_ceiling: frozenset[str] = field(default_factory=frozenset)

    @property
    def ceiling(self) -> frozenset[str]:
        return HARD_CEILING_TOUCHES | self.extra_ceiling


def load_autonomy(cabinet_root: str | Path | None = None) -> AutonomyPolicy:
    """Load instance/config/autonomy.yml, or conservative defaults if absent.

    Crucially, a missing/broken file yields the SAFE default policy
    (tool/integration = propose), never an unsafe one.
    """
    policy = AutonomyPolicy()
    root = Path(cabinet_root or os.environ.get("CABINET_ROOT") or _FRAMEWORK_ROOT)
    cfg = root / "instance" / "config" / "autonomy.yml"
    if not cfg.exists() or _yaml_load is None:
        return policy
    try:
        data = _yaml_load(cfg.read_text()) or {}
    except Exception:
        return policy  # fail safe → conservative defaults

    d = data.get("defaults") or {}
    for k in VALID_KINDS:
        v = d.get(k)
        if v in ("auto", "propose", "off"):
            policy.defaults[k] = v

    grad = data.get("graduation") or {}
    policy.graduation_enabled = bool(grad.get("enabled", False))
    try:
        policy.auto_after_clean_approvals = int(grad.get("auto_after_clean_approvals", 10))
    except (TypeError, ValueError):
        policy.auto_after_clean_approvals = 10

    clf = data.get("classifier") or {}
    if clf.get("ambiguous_defaults_to") in ("propose", "auto"):
        policy.ambiguous_defaults_to = clf["ambiguous_defaults_to"]

    hc = (data.get("hard_ceiling") or {}).get("always_propose_if_touches") or []
    policy.extra_ceiling = frozenset(str(x) for x in hc if isinstance(x, str))
    return policy


# ---------------------------------------------------------------------------
# The gates (FAIL CLOSED)
# ---------------------------------------------------------------------------

def can_auto_apply(kind: str, touches: set[str] | None, policy: AutonomyPolicy | None = None) -> bool:
    """May the cabinet build + apply this gap WITHOUT asking the Captain?

    True only when ALL hold:
      - policy.defaults[kind] == 'auto'
      - the gap touches NOTHING on the hard ceiling
    Anything else → False (propose / off / unknown kind / any ceiling touch).
    Fails closed on bad input.
    """
    try:
        policy = policy or load_autonomy()
        if kind not in VALID_KINDS:
            return False
        if policy.defaults.get(kind) != "auto":
            return False
        if touches and (set(touches) & policy.ceiling):
            return False
        return True
    except Exception:
        return False


def can_install(gap_id: str, touches: set[str] | None = None,
                policy: AutonomyPolicy | None = None,
                product_slug: str | None = None) -> bool:
    """May an installer ACTUALLY install/build the thing for this gap NOW?

    The hard gate guarding every code/MCP/plugin install. Returns True only if:
      - a verified `capability_gap_approved` event exists for gap_id that has
        NOT been superseded by a `capability_gap_declined`, AND
      - nothing it touches is on the hard ceiling (defense in depth — even an
        approval can't override the ceiling; if it touches the ceiling, the
        approval should never have been auto-eligible, and a human re-confirm
        is required at install time too).

    FAILS CLOSED: any exception, missing approval, or ceiling touch → False.
    """
    try:
        if not gap_id:
            return False
        policy = policy or load_autonomy()
        # Hard ceiling: never install ceiling-touching capability automatically,
        # even with an approval event (belt + suspenders).
        if touches and (set(touches) & policy.ceiling):
            return False
        # Require a live approval: latest of approved/declined for this gap must
        # be 'approved'.
        latest = _latest_decision_for(gap_id, product_slug)
        return latest == "approved"
    except Exception:
        return False


def _latest_decision_for(gap_id: str, product_slug: str | None) -> str | None:
    """Return 'approved' | 'declined' | None — the latest Captain decision."""
    events = replay(event_types=["capability_gap_approved", "capability_gap_declined"])
    decision: str | None = None
    for ev in events:
        payload = ev.get("payload") or {}
        if payload.get("gap_id") != gap_id:
            continue
        if product_slug and payload.get("product_slug") not in (None, product_slug):
            continue
        decision = "approved" if ev["event_type"] == "capability_gap_approved" else "declined"
    return decision


# ---------------------------------------------------------------------------
# Record + dedup
# ---------------------------------------------------------------------------

_STOP = frozenset({
    "the", "a", "an", "to", "of", "for", "and", "or", "in", "on", "with",
    "i", "we", "it", "is", "need", "needs", "want", "cant", "can't", "no",
})


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP and len(w) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def gap_id_for(need: str) -> str:
    return "gap-" + hashlib.sha1(need.strip().lower().encode()).hexdigest()[:8]


def record_gap(need: str, kind: str | None = None, evidence: str = "",
               recorded_by: str = "unknown", touches: list[str] | None = None,
               product_slug: str | None = None, actor: str | None = None,
               dedup_threshold: float = 0.6) -> dict[str, Any]:
    """Record a capability gap. Dedups near-identical recurring gaps by Jaccard
    over content tokens — a recurring gap increments hit_count instead of
    creating a duplicate (frequency = priority).

    Returns the gap dict (new or merged-into).
    """
    need = (need or "").strip()
    if not need:
        raise ValueError("record_gap: need is required")
    actor = actor or recorded_by
    product_slug = product_slug or os.environ.get("CABINET_PRODUCT_SLUG") or "default"

    # Dedup against open gaps.
    existing = project_gaps(product_slug=product_slug)
    new_tokens = _tokens(need + " " + evidence)
    for g in existing:
        if g["status"] in (STATUS_RESOLVED, STATUS_DECLINED):
            continue
        if _jaccard(new_tokens, _tokens(g["need"] + " " + (g.get("evidence") or ""))) >= dedup_threshold:
            emit("capability_gap_merged", actor=actor, payload={
                "gap_id": g["gap_id"], "product_slug": product_slug,
                "need": need, "recorded_by": recorded_by, "evidence": evidence,
            })
            g["hit_count"] = g.get("hit_count", 1) + 1
            return g

    gid = gap_id_for(need)
    inferred_kind = kind if kind in VALID_KINDS else classify(need, evidence)
    inferred_touches = sorted(infer_touches(need, evidence, touches))
    emit("capability_gap_recorded", actor=actor, payload={
        "gap_id": gid, "product_slug": product_slug, "need": need,
        "kind": inferred_kind, "evidence": evidence, "recorded_by": recorded_by,
        "touches": inferred_touches,
    })
    return {
        "gap_id": gid, "product_slug": product_slug, "need": need,
        "kind": inferred_kind, "status": STATUS_OPEN, "hit_count": 1,
        "evidence": evidence, "recorded_by": recorded_by,
        "touches": inferred_touches, "resolution": None,
    }


# ---------------------------------------------------------------------------
# State transitions (each emits an event; status is projected)
# ---------------------------------------------------------------------------

def propose_gap(gap_id: str, summary: str, approach: str, touches: list[str] | None = None,
                actor: str = "cabinet", product_slug: str | None = None) -> dict[str, Any]:
    product_slug = product_slug or os.environ.get("CABINET_PRODUCT_SLUG") or "default"
    return emit("capability_gap_proposed", actor=actor, payload={
        "gap_id": gap_id, "product_slug": product_slug,
        "summary": summary, "approach": approach, "touches": touches or [],
    })


def approve_gap(gap_id: str, actor: str = "captain", note: str = "",
                product_slug: str | None = None) -> dict[str, Any]:
    product_slug = product_slug or os.environ.get("CABINET_PRODUCT_SLUG") or "default"
    return emit("capability_gap_approved", actor=actor, payload={
        "gap_id": gap_id, "product_slug": product_slug, "note": note,
    })


def decline_gap(gap_id: str, reason: str = "", actor: str = "captain",
                product_slug: str | None = None) -> dict[str, Any]:
    product_slug = product_slug or os.environ.get("CABINET_PRODUCT_SLUG") or "default"
    return emit("capability_gap_declined", actor=actor, payload={
        "gap_id": gap_id, "product_slug": product_slug, "reason": reason,
    })


def resolve_gap(gap_id: str, resolution: str, actor: str = "cabinet",
                product_slug: str | None = None) -> dict[str, Any]:
    """Close a gap. `resolution` e.g. 'skill: stripe-mrr-pull' or 'mcp: stripe'."""
    product_slug = product_slug or os.environ.get("CABINET_PRODUCT_SLUG") or "default"
    return emit("capability_gap_resolved", actor=actor, payload={
        "gap_id": gap_id, "product_slug": product_slug, "resolution": resolution,
    })


# ---------------------------------------------------------------------------
# Projection (event replay → current gap state)
# ---------------------------------------------------------------------------

_GAP_EVENTS = [
    "capability_gap_recorded", "capability_gap_merged", "capability_gap_classified",
    "capability_gap_proposed", "capability_gap_approved", "capability_gap_declined",
    "capability_gap_resolved",
]


def project_gaps(product_slug: str | None = None) -> list[dict[str, Any]]:
    """Replay capability_gap_* events into the current set of gaps."""
    events = replay(event_types=_GAP_EVENTS)
    gaps: dict[str, dict[str, Any]] = {}
    for ev in events:
        p = ev.get("payload") or {}
        gid = p.get("gap_id")
        if not gid:
            continue
        if product_slug and p.get("product_slug") not in (None, product_slug):
            continue
        et = ev["event_type"]
        ts = ev.get("created_at", "")
        if et == "capability_gap_recorded":
            gaps[gid] = {
                "gap_id": gid, "product_slug": p.get("product_slug", "default"),
                "need": p.get("need", ""), "kind": p.get("kind", "tool"),
                "status": STATUS_OPEN, "hit_count": 1, "evidence": p.get("evidence", ""),
                "recorded_by": p.get("recorded_by", "unknown"),
                "touches": p.get("touches", []), "resolution": None,
                "first_seen": ts, "last_seen": ts,
            }
        elif gid not in gaps:
            continue
        elif et == "capability_gap_merged":
            gaps[gid]["hit_count"] = gaps[gid].get("hit_count", 1) + 1
            gaps[gid]["last_seen"] = ts
        elif et == "capability_gap_classified":
            gaps[gid]["kind"] = p.get("kind", gaps[gid]["kind"])
            gaps[gid]["status"] = p.get("status", STATUS_CLASSIFIED)
            gaps[gid]["last_seen"] = ts
        elif et == "capability_gap_proposed":
            gaps[gid]["status"] = STATUS_PENDING
            gaps[gid]["proposal"] = {"summary": p.get("summary", ""), "approach": p.get("approach", "")}
            gaps[gid]["last_seen"] = ts
        elif et == "capability_gap_approved":
            gaps[gid]["status"] = STATUS_APPROVED
            gaps[gid]["last_seen"] = ts
        elif et == "capability_gap_declined":
            gaps[gid]["status"] = STATUS_DECLINED
            gaps[gid]["decline_reason"] = p.get("reason", "")
            gaps[gid]["last_seen"] = ts
        elif et == "capability_gap_resolved":
            gaps[gid]["status"] = STATUS_RESOLVED
            gaps[gid]["resolution"] = p.get("resolution")
            gaps[gid]["last_seen"] = ts
    return sorted(gaps.values(), key=lambda g: (-g.get("hit_count", 1), g.get("first_seen", "")))


# ---------------------------------------------------------------------------
# Routing — what the self-improvement loop does with open gaps each cycle
# ---------------------------------------------------------------------------

def route_open_gaps(product_slug: str | None = None, policy: AutonomyPolicy | None = None,
                    dry_run: bool = False, notify_fn=None) -> dict[str, Any]:
    """Route every OPEN gap by kind. Called by the self-improvement loop.

      procedure (auto-eligible)  → mark auto_skilling (the induction pass +
                                   eval gate then draft/validate/promote the skill)
      tool / integration         → emit a proposal (status → pending_captain) and
                                   best-effort notify the Captain. NOTHING installs
                                   here — install waits for can_install() == True
                                   (a Captain approval), guarded by the fail-closed
                                   gate.

    dry_run = compute + return the plan without emitting anything.
    notify_fn(gap, summary) optional — used to DM the Captain (best-effort).
    Returns a summary dict. Never raises on a single gap (isolates failures).
    """
    product_slug = product_slug or os.environ.get("CABINET_PRODUCT_SLUG") or "default"
    policy = policy or load_autonomy()
    routed = {"auto_skilling": [], "proposed": [], "skipped": []}

    for g in project_gaps(product_slug=product_slug):
        if g["status"] != STATUS_OPEN:
            continue
        gid = g["gap_id"]
        kind = g.get("kind") or classify(g["need"], g.get("evidence", ""))
        touches = set(g.get("touches") or [])
        try:
            if kind == "procedure" and can_auto_apply(kind, touches, policy):
                routed["auto_skilling"].append(gid)
                if not dry_run:
                    emit("capability_gap_classified", actor="self-improvement-loop", payload={
                        "gap_id": gid, "product_slug": product_slug,
                        "kind": kind, "status": STATUS_AUTO_SKILLING,
                    })
            else:
                # tool / integration / ceiling-touching procedure → propose
                summary = f"Capability gap ({kind}): {g['need']}"
                approach = (
                    "Build a read-only MCP for this need (mcp-builder), declare it in "
                    "instance/config/extensions.yml, grant the requesting officer via an "
                    "instance/agents overlay. Read-only unless this proposal says otherwise."
                )
                if touches & policy.ceiling:
                    approach += f"  ⚠ touches hard-ceiling: {sorted(touches & policy.ceiling)} — Captain approval REQUIRED, never auto."
                routed["proposed"].append(gid)
                if not dry_run:
                    propose_gap(gid, summary=summary, approach=approach,
                                touches=sorted(touches), actor="self-improvement-loop",
                                product_slug=product_slug)
                    if notify_fn:
                        try:
                            notify_fn(g, summary)
                        except Exception:
                            pass  # best-effort; never block routing on a failed DM
        except Exception:
            routed["skipped"].append(gid)  # isolate: one bad gap can't break the pass
    return routed
