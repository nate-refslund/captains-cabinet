"""Self-extension loop — capability gaps → auto-skill or propose-then-approve.

When an officer hits a wall it can't solve with current tools (or the loop
infers a recurring manual workaround), that's a *capability gap*. This module
records gaps, dedups recurring ones, classifies them, and gates what the
Cabinet may do on its own:

  - procedure  → auto-skilled (draft → eval gate → promote). Human never asked.
  - tool       → proposal DM'd to Captain. Nothing installs without approval.
  - integration→ same as tool.
  - skill / authority / information → SURFACE ONLY. Recorded, projected and
    rendered; never auto-skilled, never proposed, never DM'd. These name a
    missing holder, a missing permission and a missing fact — none of them is
    a thing the loop can build for itself, so a proposal would be an ask the
    Captain cannot approve into existence. Reading them off the gaps surface
    is the whole behaviour.

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

import fcntl
import hashlib
import os
import re
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_FRAMEWORK_ROOT = str(Path(__file__).parent.parent.parent)
if _FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_ROOT)

from framework.events.emitter import emit, replay, _event_log_dir  # noqa: E402

try:
    from yaml import safe_load as _yaml_load
except ImportError:  # pragma: no cover - yaml present in cabinet runtime
    _yaml_load = None


# ---------------------------------------------------------------------------
# Kinds + status
# ---------------------------------------------------------------------------

# The kinds the self-extension lane may ACT on: `procedure` is the only
# auto-skillable one, `tool`/`integration` reach the Captain as proposals.
ACTIONABLE_KINDS = ("procedure", "tool", "integration")

# Structural kinds — recorded SURFACE-ONLY (see the module docstring). Held as
# a code-level constant, not a config knob: widening it widens what the loop is
# allowed to stay silent about.
STRUCTURAL_KINDS = frozenset({"skill", "authority", "information"})

VALID_KINDS = ACTIONABLE_KINDS + ("skill", "authority", "information")

# The kinds an ambiguous classification may resolve to — both are *propose*
# kinds. `procedure` (the auto lane) and every structural kind are refused
# here: an ambiguous need that resolved to a structural kind would go quiet
# instead of reaching the Captain, which is the opposite of erring toward
# human-in-loop.
_AMBIGUOUS_RESOLVES_TO = ("tool", "integration")

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
    # Tie or both zero → ambiguous → safe default (propose). Never 'procedure'
    # (the auto-skill lane) and never a structural kind (the silent lane) —
    # enforced here, not just documented.
    if ambiguous_default not in _AMBIGUOUS_RESOLVES_TO:
        ambiguous_default = "tool"
    return "integration" if integ_signal else ambiguous_default


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

    @property
    def ambiguous_kind(self) -> str:
        """classify()'s `ambiguous_default` under this policy — the vocabulary
        map from the autonomy.yml knob ('propose' → 'tool', a propose kind).
        `auto` is REFUSED at load time and anything unexpected reads as 'tool'
        here too: an ambiguous gap must never default into 'procedure' (the
        auto-skill lane)."""
        return "tool"


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
    # ACTIONABLE_KINDS, not VALID_KINDS: a structural kind has no auto lane to
    # configure, so `defaults: {skill: auto}` in the file is read as nothing.
    for k in ACTIONABLE_KINDS:
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
    # Only 'propose' is honored. 'auto' is REFUSED (kept at the safe default):
    # an ambiguous gap defaulting into the auto-skill lane would invert the
    # module's err-toward-human-in-loop invariant, so the file cannot ask for it.
    if clf.get("ambiguous_defaults_to") == "propose":
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
        # Structural kinds are surface-only in every posture and under every
        # autonomy.yml — the veto sits ahead of the policy lookup so a file
        # cannot grant an auto lane that does not exist.
        if kind in STRUCTURAL_KINDS:
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

    Posture-aware extension [sovereign spec §4 SOV-8, §3 "capability install"]:
    when NO Captain decision exists at all, a SOVEREIGN posture plus a passing
    Evidence-Gate pack for this gap (gate.ratify verdict "pass") also allows.
    The ceiling-touch veto stays ABSOLUTE (checked first, both postures), and
    an explicit Captain decline beats machine evidence in every posture.
    Guardian with no decision is today's exact answer: False.

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
        if latest == "approved":
            return True
        if latest == "declined":
            return False
        # No Captain decision on record — sovereign + gate evidence may allow.
        return _sovereign_gate_evidence_allows(gap_id)
    except Exception:
        return False


def _sovereign_gate_evidence_allows(gap_id: str) -> bool:
    """True only when the posture resolves sovereign AND the Evidence Gate
    holds a passing pack for this gap. Lazy imports + blanket except: any
    failure (module absent, posture unreadable, no pack) answers False, so
    the guardian world stays bit-identical [D15]."""
    try:
        from framework.authority.posture import resolve_posture
        if resolve_posture() != "sovereign":
            return False
        from framework.learning.gate import evidence_verdict
        return evidence_verdict(gap_id=gap_id) == "pass"
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


def gap_id_for_key(dedup_key: str) -> str:
    """Gap id for a caller-supplied dedup key — identity, not similarity.

    Case is PRESERVED (unlike `gap_id_for`, which lowercases a free-text need):
    a key is built from ids, and ids that differ only in case are different
    subjects, so folding case here would silently merge two of them.
    """
    return "gap-" + hashlib.sha1(dedup_key.strip().encode()).hexdigest()[:8]


_GAPS_LOCK_NAME = ".capability-gaps.lock"


@contextmanager
def _gaps_lock():
    """Serialize keyed gap records across processes.

    The critical section is read-then-emit. Without it, N observers of the same
    key each replay a ledger that does not yet hold the gap and each emit, so
    one subject lands N times — the exact failure a keyed dedupe exists to
    prevent, and one that only appears under concurrency (the officer hook runs
    a fresh process per tick).

    The lock file lives beside the JSONL ledger the projection replays, so the
    lock's scope is exactly the dedupe's scope. Advisory `flock`, POSIX only —
    the same premise framework/attention/feed.py records. Ordering is always
    gaps-lock → ledger-lock (emitter), never the reverse.

    ORDERING FOR THE LOCK THAT HAS NOT LANDED YET. A3.1 says keyed records are
    taken "under the claims lock"; `framework/missions/claims.py` does not
    exist at this commit, so this purpose-built lock beside the ledger provides
    the atomicity A3.1 exists for. When U2 lands its claims lock, the pull path
    will hold it while calling into here (U3b's `observe_holder_gaps` runs
    inside `get_next_task`), so the acquisition order is fixed now, in the only
    direction that is deadlock-free with a single writer path:

        claims-lock → gaps-lock → ledger-lock

    Nothing in this module ever takes a claims lock, so this module cannot
    invert it on its own; the rule binds whoever adds a call in the other
    direction, and belongs in claims.py's docstring too when it lands.
    """
    log_dir = _event_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(log_dir / _GAPS_LOCK_NAME), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _live_gap_with_id(gap_id: str, product_slug: str) -> dict[str, Any] | None:
    """The gap carrying this id if it is still live (not resolved/declined).

    A closed one answers None on purpose: the condition recurring after it was
    closed is a NEW observation and re-opens the gap, which the projection
    already handles (a second `capability_gap_recorded` rebuilds the row).

    RECORDED, so U3b's producer does not surprise the Captain: for a KEYED gap
    this makes a decline non-final in the projection. A Captain declines a
    standing condition; the next observer tick re-records it and `/gaps` shows
    it open again — occasional for a free-text gap, continuous for a keyed one
    whose subject persists. The decline still BINDS where it matters:
    `can_install` reads the decision out of the event ledger
    (`_latest_decision_for`), not out of the projected status, so a re-opened
    row grants nothing. The behaviour predates keys (`gap_id_for(need)` is
    equally stable); keys only make it regular. If the Captain should be able
    to silence a standing condition, that is a `resolve`/mute decision for
    U3b's producer, not a change to this projection.
    """
    for g in project_gaps(product_slug=product_slug):
        if g["gap_id"] != gap_id:
            continue
        if g["status"] in (STATUS_RESOLVED, STATUS_DECLINED):
            return None
        return g
    return None


def _emit_recorded(gap_id: str, need: str, kind: str | None, evidence: str,
                   recorded_by: str, touches: list[str] | None,
                   product_slug: str, actor: str,
                   dedup_key: str | None) -> dict[str, Any]:
    """Emit `capability_gap_recorded` and return the projected-shape gap."""
    inferred_kind = kind if kind in VALID_KINDS else classify(
        need, evidence, load_autonomy().ambiguous_kind)
    inferred_touches = sorted(infer_touches(need, evidence, touches))
    emit("capability_gap_recorded", actor=actor, payload={
        "gap_id": gap_id, "product_slug": product_slug, "need": need,
        "kind": inferred_kind, "evidence": evidence, "recorded_by": recorded_by,
        "touches": inferred_touches, "dedup_key": dedup_key,
    })
    return {
        "gap_id": gap_id, "product_slug": product_slug, "need": need,
        "kind": inferred_kind, "status": STATUS_OPEN, "hit_count": 1,
        "evidence": evidence, "recorded_by": recorded_by,
        "touches": inferred_touches, "resolution": None,
        "dedup_key": dedup_key,
    }


def record_gap(need: str, kind: str | None = None, evidence: str = "",
               recorded_by: str = "unknown", touches: list[str] | None = None,
               product_slug: str | None = None, actor: str | None = None,
               dedup_threshold: float = 0.6,
               dedup_key: str | None = None) -> dict[str, Any]:
    """Record a capability gap.

    Two dedupe modes, and a keyed record uses ONLY its key:

      * `dedup_key` given — IDENTITY. `gap_id = gap_id_for_key(key)`; a live gap
        with that id is returned as-is and NOTHING is emitted, so re-observing
        the same subject on every pass costs one row in total instead of one
        `capability_gap_merged` per pass. The whole check-then-emit runs under
        `_gaps_lock()`, so N concurrent observers of one subject record once.
      * no key — SIMILARITY, unchanged: near-identical recurring free-text needs
        merge by Jaccard over content tokens and increment hit_count
        (frequency = priority).

    The two modes never cross. The similarity scan skips keyed gaps entirely: a
    keyed gap is not a merge TARGET (two subjects whose needs read alike —
    `…task-001` and `…task-002` — would otherwise collapse into one) and a keyed
    record never runs the scan, so it cannot be merged INTO one either.

    RECORDED CONSEQUENCE (A3.1 mandates no emit on re-observation, so this is
    the contract's shape, not a defect): a keyed gap's `hit_count` stays 1 for
    its whole life. `project_gaps` ranks by `-hit_count` — frequency = priority
    for free-text gaps — so a standing condition observed on every tick sorts
    BELOW a free-text gap seen twice. Nothing keyed is emitted today; when
    U3b's producer starts emitting keyed gaps, the `/gaps` ranking is the call
    to make then (rank keyed rows by `last_seen`/age, or accept the order).
    Deliberately not pre-empted here: a ranking rule with no producer is a
    guess about a surface nobody has looked at yet.

    Returns the gap dict (new, keyed-existing, or merged-into).
    """
    need = (need or "").strip()
    if not need:
        raise ValueError("record_gap: need is required")
    actor = actor or recorded_by
    product_slug = product_slug or os.environ.get("CABINET_PRODUCT_SLUG") or "default"
    dedup_key = (dedup_key or "").strip() or None

    if dedup_key:
        gid = gap_id_for_key(dedup_key)
        with _gaps_lock():
            live = _live_gap_with_id(gid, product_slug)
            if live is not None:
                return live
            return _emit_recorded(gid, need, kind, evidence, recorded_by,
                                  touches, product_slug, actor, dedup_key)

    # Dedup against open gaps.
    existing = project_gaps(product_slug=product_slug)
    new_tokens = _tokens(need + " " + evidence)
    for g in existing:
        if g["status"] in (STATUS_RESOLVED, STATUS_DECLINED):
            continue
        if g.get("dedup_key"):
            continue  # keyed gaps are identity-deduped; never a merge target
        if _jaccard(new_tokens, _tokens(g["need"] + " " + (g.get("evidence") or ""))) >= dedup_threshold:
            emit("capability_gap_merged", actor=actor, payload={
                "gap_id": g["gap_id"], "product_slug": product_slug,
                "need": need, "recorded_by": recorded_by, "evidence": evidence,
            })
            g["hit_count"] = g.get("hit_count", 1) + 1
            return g

    return _emit_recorded(gap_id_for(need), need, kind, evidence, recorded_by,
                          touches, product_slug, actor, None)


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
                "dedup_key": p.get("dedup_key"),
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
      STRUCTURAL_KINDS           → counted under "surfaced" and otherwise left
                                   alone: no proposal, no notify_fn, no status
                                   change, nothing installable. They are already
                                   where they belong the moment they are recorded.

    dry_run = compute + return the plan without emitting anything.
    notify_fn(gap, summary) optional — used to DM the Captain (best-effort).
    Returns a summary dict. Never raises on a single gap (isolates failures).
    """
    product_slug = product_slug or os.environ.get("CABINET_PRODUCT_SLUG") or "default"
    policy = policy or load_autonomy()
    routed = {"auto_skilling": [], "proposed": [], "surfaced": [], "skipped": []}

    for g in project_gaps(product_slug=product_slug):
        if g["status"] != STATUS_OPEN:
            continue
        gid = g["gap_id"]
        kind = g.get("kind") or classify(g["need"], g.get("evidence", ""),
                                         policy.ambiguous_kind)
        if kind in STRUCTURAL_KINDS:
            # Surface-only. Kept out of "skipped", which means a gap the pass
            # could not route — a distinct thing that must stay countable.
            routed["surfaced"].append(gid)
            continue
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
