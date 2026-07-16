"""framework.attention.queue — ONE attention census → normalized decision-cards.

The war-room aggregator (command-center proposal 2026-07-10 §2 delta 2 +
decision-card-contract-v1). Folds:

  * the situations view (framework.attention.situations — §4.2, THE spine),
  * open needs (framework.authority.needs.list_open — dark under guardian),
  * pending T2 judgment requests (framework.attention.t2.pending_requests),

into normalized DECISION-CARDS (contract v1), stamps blast radius from the
authority matrix (read-only consumption via policy_engine.resolve_verdict),
computes presentation decay (H5 demote_path tiers), splits the two shelves
(Decisions = now/blocking, Directions = weekly), ranks Decisions with the
deterministic lexicographic tuple — NO producer priority field exists:

    (harm_class, time_to_harm, -blocked_leverage, -age)

and caps the Decisions shelf at charter data N (C4: 7). Overflow files ONE
consolidation need (fingerprint-deduped by the needs ledger itself) — never
a hidden backlog.

ADMISSION LAW (H3, C3 — ASKED of the Captain, so ENFORCEMENT is behind
``CABINET_ADMISSION_LAW`` default OFF): a chain the org can execute fully
autonomously (auto / act_with_undo / notify_after / auto_with_veto_window at
every step) is FORBIDDEN from the room — routed to the org, visible only as
acted digest lines. Only captain-gated chains (gate / always_gated /
propose_only / unsatisfied standing_grant / external per-item) may enter.
Taint (injection_suspect) forces propose-only ⇒ admits (D13-consistent).
The verdict per step comes ONLY from the resolved posture matrix (the
axes-contract seam) — replayable, un-gameable by producer phrasing. The
admission is ALWAYS computed and stamped on the card (``admission``); the
flag governs only whether org-decidable cards are dropped from the room.

Two artifacts per census (one computed truth, two projections):
  * PRIVATE full census → $CABINET_ATTENTION_DIR/queue.json — the authed
    dashboard/API source (free-text ``what`` lines + pids live HERE only).
  * SHARED scrubbed census → shared/interfaces/attention-queue.json —
    world-census PII discipline: opaque ids, counts, classes, id-grade refs
    ONLY (no subjects, no pids — pid embeds a subject slug —, no vault
    paths, no URLs). Opaque join handle ``h`` = sha256 of the pid (the
    shipped selHandle pattern) so an authed consumer can join without the
    shared plane ever carrying the pid itself.

Read-only by construction: this module never sends, never approves, never
executes. Verdicts stay 100% in the Telegram binder grammar.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional

from framework.attention import situations as sit_view

# ---------------------------------------------------------------------------
# Admission vocabulary (lens_admission.py prototype, validated 2026-07-10)
# ---------------------------------------------------------------------------

# Matrix verdicts the org may execute WITHOUT the Captain.
AUTONOMOUS = frozenset({"auto", "act_with_undo", "notify_after",
                        "auto_with_veto_window"})
# Admission verdicts that block on the Captain.
CAPTAIN_GATED = frozenset({"gate", "standing_grant_unsatisfied",
                           "external_per_item", "never_grant"})

# Matrix verdict string → admission verdict string.
_MATRIX_TO_ADMISSION = {
    "auto": "auto", "act_with_undo": "act_with_undo",
    "notify_after": "notify_after",
    "auto_with_veto_window": "auto_with_veto_window",
    "always_gated": "gate", "propose_only": "gate",
    "standing_grant": "standing_grant_unsatisfied",
    "classifier": "gate",     # deploy-classifier chains fail toward the room
}

_HARM_CLASS = {"external_deadline": 0, "value_decay": 1, "none": 2}

_ENV_FLAG = "CABINET_ADMISSION_LAW"

_ATTENTION_DIR_ENV = "CABINET_ATTENTION_DIR"
_ATTENTION_DIR_DEFAULT = "~/Library/Application Support/cabinet/attention"

# Opaque id grades allowed into the SHARED artifact (world-census PII
# discipline): commitment ids, correlation ids, NEED ids, monday ids, UUIDs.
# Vault paths and URLs are excluded (they can carry person/company names).
_SHARED_REF_PREFIXES = ("cmt-", "cabinet-proposal-id:", "need-", "monday:")
# Strict RFC-4122 shape — "36 chars + 4 hyphens" let uuid-SHAPED vault paths
# (e.g. 7-resources/my-prompts/2026-07-07.md) leak into the shared plane.
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _attention_dir() -> Path:
    return Path(os.environ.get(_ATTENTION_DIR_ENV) or
                os.path.expanduser(_ATTENTION_DIR_DEFAULT))


def admission_law_on() -> bool:
    """H3 enforcement flag — default OFF until the Captain rules C3."""
    return str(os.environ.get(_ENV_FLAG, "")).strip().lower() in (
        "1", "true", "on", "yes")


# ---------------------------------------------------------------------------
# The matrix seam — resolved posture verdict per step (axes-contract: tables
# + the one resolver chain; no axis branches here)
# ---------------------------------------------------------------------------

def _load_policy():
    from framework.authority.matrix import load_matrix, matrix_policy
    return matrix_policy(load_matrix())


def make_resolve_step(*, policy: "dict | None" = None,
                      posture: "str | None" = None,
                      cell_state: str = "unmeasured") -> Callable:
    """Build the injected ``resolve_step(step) -> admission verdict`` from the
    ONE authority matrix. Fail-toward-the-room: any resolution failure returns
    "gate" (the Captain sees it; the org never silently absorbs an unknown).

    ``cell_state`` defaults to "unmeasured" — the trust-first doctrine state.
    (P6 will thread live graduation states; the admission split is identical
    for every state except demote, which only NARROWS toward the room.)
    """
    try:
        pol = policy if policy is not None else _load_policy()
        verdicts = pol.get("verdicts") or {}
        postures = pol.get("postures")
        rc_of: dict = {}
        for rc, spec in (pol.get("risk_classes") or {}).items():
            for at in (spec or {}).get("action_types") or []:
                rc_of[str(at)] = str(rc)
        if posture is None:
            try:
                from framework.authority.policy_engine import resolve_gate_posture
                posture = resolve_gate_posture()
            except Exception:
                posture = None            # guardian root table
        from framework.authority.policy_engine import resolve_verdict
    except Exception:
        return lambda step: "gate"        # matrix unreadable → everything gates

    def resolve_step(step: dict) -> str:
        try:
            at = str((step or {}).get("action_type") or
                     (step or {}).get("kind") or "")
            rc = rc_of.get(at)
            if rc is None:
                return "gate"             # unclassifiable step never bypasses
            v = resolve_verdict(verdicts, rc, cell_state,
                                posture=posture, postures=postures)
            return _MATRIX_TO_ADMISSION.get(str(v), "gate")
        except Exception:
            return "gate"

    return resolve_step


def admit(item: dict, resolve_step: Callable) -> str:
    """→ 'org' | 'decisions' | 'directions' (lens_admission.py L1, verbatim
    semantics). Taint forces propose-only ⇒ admits regardless of the matrix
    (D13 floor). A fully-autonomous chain is FORBIDDEN from the room."""
    steps = item.get("steps") or []
    if item.get("injection_suspect"):
        return "decisions"
    verdicts = [resolve_step(s) for s in steps]
    if verdicts and all(v in AUTONOMOUS for v in verdicts):
        return "org"
    blocked = [v for v in verdicts if v in CAPTAIN_GATED]
    if not blocked and not item.get("harm_at"):
        return "directions"
    if item.get("harm_at") or blocked:
        if item.get("harm_at") or item.get("blocked_leverage", 0) > 0:
            return "decisions"
    return "directions"


# ---------------------------------------------------------------------------
# Ranking (lens_admission.py L2) — lexicographic, auditable, no weights soup
# ---------------------------------------------------------------------------

def rank_key(card: dict, now: datetime):
    hc = _HARM_CLASS.get(card.get("harm_class", "none"), 2)
    harm_at = sit_view.parse_iso(card.get("harm_at"))
    tth = (harm_at - now).total_seconds() if harm_at else float("inf")
    leverage = int(card.get("blocked_leverage") or 0)
    created = sit_view.parse_iso(card.get("created_ts")) or now
    age_s = max(0.0, (now - created).total_seconds())
    return (hc, tth, -leverage, -age_s)


def render_room(cards: list, now: datetime, cap: int = 7):
    ordered = sorted(cards, key=lambda c: rank_key(c, now))
    return ordered[:cap], ordered[cap:]


# ---------------------------------------------------------------------------
# Blast radius — derived from the matrix, never re-declared ad hoc
# ---------------------------------------------------------------------------

def blast_for(steps: Iterable, *, kind: str = "",
              policy: "dict | None" = None) -> dict:
    """{class: none|low|ceiling, reach: internal|external|germline|spend,
    worst_case} from the chain's action types against the matrix's
    risk-class map + hard ceiling. Fail-soft to the honest maximum-ignorance
    stamp (class low, reach internal) — never raises."""
    try:
        pol = policy if policy is not None else _load_policy()
        rc_of: dict = {}
        for rc, spec in (pol.get("risk_classes") or {}).items():
            for at in (spec or {}).get("action_types") or []:
                rc_of[str(at)] = str(rc)
        ceiling = set(pol.get("hard_ceiling") or [])
    except Exception:
        rc_of, ceiling = {}, set()

    classes = {rc_of.get(str((s or {}).get("action_type") or
                             (s or {}).get("kind") or ""))
               for s in (steps or [])}
    classes.discard(None)

    if kind in ("germline-handback",):
        return {"class": "ceiling", "reach": "germline",
                "worst_case": "a wrong approve amends the germline plane"}
    hit_ceiling = classes & ceiling
    if hit_ceiling:
        reach = ("spend" if "spend" in hit_ceiling else
                 "external" if "external_comms" in hit_ceiling else "internal")
        worst = {"spend": "money leaves the org",
                 "external": "a message reaches a human outside the machine",
                 "internal": "a ceiling-class artifact ships (prod/secret/net)"}
        return {"class": "ceiling", "reach": reach, "worst_case": worst[reach]}
    if not classes:
        return {"class": "low", "reach": "internal",
                "worst_case": "unclassified chain — treated as low, gated"}
    return {"class": "low", "reach": "internal",
            "worst_case": "a reversible internal artifact needs undoing"}


# ---------------------------------------------------------------------------
# H5 — expiry streaks → class demotion (wires budget.demote_after_expiries)
# ---------------------------------------------------------------------------

def expiry_streaks(ledger_rows: Iterable) -> dict:
    """Per card kind (the ledger ``action`` string), the CURRENT consecutive
    run of decision=='expired' closures, reset by any real Captain verdict.
    Rows folded in ts order; rows without a proposal are ignored."""
    ordered = sorted((r for r in ledger_rows if isinstance(r, dict)
                      and isinstance(r.get("proposal"), dict)),
                     key=lambda r: str(r.get("ts") or ""))
    streaks: dict = {}
    for row in ordered:
        action = str(row.get("action") or "")
        decision = (row.get("proposal") or {}).get("decision")
        if decision == "expired":
            streaks[action] = streaks.get(action, 0) + 1
        elif decision in sit_view._CAPTAIN_DECISIONS:
            # A real Captain verdict (approved/edited/rejected — the shared
            # constant, NOT the imperative reply verbs) resets the streak.
            streaks[action] = 0
    return streaks


def demoted_kinds(ledger_rows: Iterable, charter: "dict | None" = None) -> set:
    """Kinds whose expiry streak crossed their charter class's
    ``budget.demote_after_expiries`` bar — the producers that must stop
    regenerating pings (gate consumes this; spec §4.8 example bar = 5)."""
    try:
        if charter is None:
            from framework.attention import charter as charter_mod
            charter = charter_mod.load_charter()
    except Exception:
        return set()
    bars: dict = {}
    for cls in (charter or {}).get("classes") or []:
        bar = ((cls or {}).get("budget") or {}).get("demote_after_expiries")
        if not isinstance(bar, int) or bar <= 0:
            continue
        for kind in ((cls.get("matchers") or {}).get("kinds") or []):
            bars[str(kind)] = bar
    if not bars:
        return set()
    streaks = expiry_streaks(ledger_rows)
    return {k for k, bar in bars.items() if streaks.get(k, 0) >= bar}


# ---------------------------------------------------------------------------
# Card normalization (decision-card contract v1)
# ---------------------------------------------------------------------------

_KIND_BY_ACTION = {"action-card": "action-proposal",
                   "draft-reply": "draft-outbound",
                   "draft-card": "draft-outbound"}

_RITUAL_KINDS = frozenset({"germline-handback", "outcome-ratification"})


def _one_tap_for(kind: str) -> dict:
    approve = ("ritual-print" if kind in _RITUAL_KINDS
               else "per-item-approval" if kind == "draft-outbound"
               else "direct")
    return {"approve": {"semantics": approve},
            "veto": {"semantics": "direct"},
            "defer": {"semantics": "direct", "until": None},
            "delegate_back": {"semantics": "direct", "to": "cos", "note": ""}}


def _default_options(subject: str, reversible: bool) -> list:
    """The minimal honest 2-option set for producers that emit one course
    (contract gap #1 — adapters synthesize until producers author options)."""
    rev_class = "reversible_with_undo" if reversible else "irreversible"
    return [
        {"opt": "o1", "label": "approve as proposed",
         "predicted_consequence": f"the proposed chain for '{subject[:60]}' executes",
         "reversibility": {"class": rev_class,
                           "inverse_registered": reversible,
                           "undo_window": "48h" if reversible else None},
         "action_type": None, "steps": []},
        {"opt": "o2", "label": "veto",
         "predicted_consequence": "nothing executes; the producer records the veto",
         "reversibility": {"class": "reversible", "inverse_registered": True,
                           "undo_window": None},
         "action_type": None, "steps": []},
    ]


def _cost_of_delay(deadline_iso: "str | None", now: datetime) -> str:
    dl = sit_view.parse_iso(deadline_iso)
    if dl is None:
        return "medium"
    hours = (dl - now).total_seconds() / 3600.0
    if hours <= 24:
        return "blocking"
    if hours <= 72:
        return "high"
    return "medium"


def _decay_tier(demotions: int) -> dict:
    path = list(sit_view.DEMOTE_PATH)
    tier = min(max(int(demotions), 0), len(path) - 1)
    return {"mode": "stay-live-until-acted", "demote_path": path,
            "tier": tier, "stage": path[tier], "close_on_world_proof": True,
            "escalate_after": None}


def situation_card(sit: dict, *, now: datetime,
                   redis_record: "dict | None" = None) -> dict:
    """One live situation → one decision-card (H1: the unit is the SITUATION,
    never the raw proposal row). ``redis_record`` is the parked
    cabinet:action:<pid> chain when one exists (steps for admission/blast)."""
    rec = redis_record or {}
    kind = sit.get("kind") or _KIND_BY_ACTION.get(
        next((a for a in sit.get("actions") or [] if a in _KIND_BY_ACTION), ""),
        "action-proposal")
    steps = [s for s in (rec.get("steps") or []) if isinstance(s, dict)]
    deadline = sit.get("deadline_iso")
    age_h = 0.0
    created = sit_view.parse_iso(sit.get("created_ts"))
    if created:
        age_h = max(0.0, (now - created).total_seconds() / 3600.0)
    blast = blast_for(steps, kind=kind)
    reversible = blast["class"] != "ceiling"
    subject = str(rec.get("subject") or sit.get("subject") or "")
    return {
        "id": sit["key"], "pid": sit.get("pid"), "revision": 1,
        "kind": kind, "state": sit.get("state", "open"),
        "what": subject.replace("·", "")[:200],
        "why_now": {"cost_of_delay": _cost_of_delay(deadline, now),
                    "decay": f"waiting {age_h:.0f}h; "
                             f"{sit.get('demotions', 0)} demotions",
                    "deadline_iso": deadline},
        "evidence": [{"ref": r, "display": r.replace("·", ""), "taint": False}
                     for r in (sit.get("refs") or [])[:8]],
        "options": _default_options(subject, reversible),
        "recommended": {"opt": "o1",
                        "confidence": float(rec.get("confidence") or 0.0),
                        "why": "producer proposed one course"},
        "one_tap": _one_tap_for(kind),
        "expiry": _decay_tier(sit.get("demotions", 0)),
        "blast_radius": blast,
        "charter_class": sit.get("class_id"),
        "urgency": str(rec.get("urgency") or "batch"),
        "standing_message_id": sit.get("standing_message_id"),
        "created_ts": sit.get("created_ts") or "",
        "last_surfaced_ts": sit.get("last_surfaced_at"),
        "filed_by": sit.get("filed_by") or "officer:unknown",
        # ranking + admission inputs
        "harm_class": sit.get("harm_class", "none"),
        "harm_at": deadline,
        "blocked_leverage": int(sit.get("blocked_leverage") or 0),
        "steps": steps or None,
        "injection_suspect": bool(rec.get("injection_suspect")),
        "lane": sit.get("lane"),
        "aliases": sit.get("aliases") or [sit["key"]],
    }


def need_card(row: dict, *, now: datetime) -> dict:
    """Open needs-ledger row → decision-card (contract: closest fit — renames
    + expiry inversion; the needs 30d sweep stays park-not-expire HERE: a
    parked need still censuses via the ledger even after list_open ages it)."""
    nid = str(row.get("id") or "")
    kind = "need"
    cod = str(row.get("cost_of_delay") or "medium")
    approve_sem = ("ritual-print" if row.get("kind") == "standing_grant"
                   else "direct")
    grant_line = row.get("proposed_grant_line")
    card = {
        "id": nid.lower(), "pid": nid, "revision": int(row.get("count") or 1),
        "kind": kind, "state": "pending",
        "what": str(row.get("why") or "")[:200].replace("·", ""),
        "why_now": {"cost_of_delay": cod,
                    "decay": str(row.get("cost_note") or
                                 row.get("unblocks") or "")[:200],
                    "deadline_iso": None},
        "evidence": ([{"ref": str(row.get("cid")), "display": str(row.get("cid")),
                       "taint": False}] if row.get("cid") else []),
        "options": _default_options(str(row.get("why") or ""), True),
        "recommended": {"opt": "o1", "confidence": 0.0,
                        "why": grant_line or "grant as filed"},
        "one_tap": {**_one_tap_for(kind),
                    "approve": {"semantics": approve_sem}},
        "expiry": _decay_tier(0),
        "blast_radius": {"class": "ceiling" if row.get("kind") == "standing_grant"
                         else "low",
                         "reach": "internal",
                         "worst_case": "a standing grant widens org authority"
                         if row.get("kind") == "standing_grant"
                         else "a capability/resource is granted"},
        "charter_class": None, "urgency": "batch",
        "standing_message_id": None,
        "created_ts": str(row.get("first_seen") or ""),
        "last_surfaced_ts": str(row.get("last_seen") or "") or None,
        "filed_by": str(row.get("filed_by") or "system:needs"),
        "harm_class": "value_decay" if cod in ("blocking", "high") else "none",
        "harm_at": None, "blocked_leverage": 0,
        # a need is by definition something the org CANNOT self-serve:
        "steps": [{"action_type": row.get("action_type")}]
        if row.get("action_type") else None,
        "injection_suspect": False, "lane": row.get("lane"),
        "aliases": [nid.lower()],
    }
    if cod == "blocking":
        card["expiry"]["escalate_after"] = "7d"
    return card


def t2_card(req: dict, *, now: datetime) -> dict:
    """Pending T2 judgment request → escalation card (thin wrap: Chair-authored
    ask; one_tap = reply-only, so approve/veto both deep-link the binder)."""
    rid = str(req.get("request_id") or req.get("rid") or "")
    skey = str(req.get("situation_key") or rid)
    subject = str((req.get("item") or {}).get("subject") or "Chair escalation")
    return {
        "id": skey, "pid": rid, "revision": 1,
        "kind": "escalation", "state": "pending",
        "what": subject[:200].replace("·", ""),
        "why_now": {"cost_of_delay": "high",
                    "decay": "the Chair is holding a judgment open",
                    "deadline_iso": req.get("deadline")},
        "evidence": [], "options": _default_options("escalation", True),
        "recommended": {"opt": "o1", "confidence": 0.0, "why": "chair-authored"},
        "one_tap": _one_tap_for("escalation"),
        "expiry": _decay_tier(0),
        "blast_radius": {"class": "low", "reach": "internal",
                         "worst_case": "a Chair judgment lands without you"},
        "charter_class": None, "urgency": "ping-now",
        "standing_message_id": None,
        "created_ts": str(req.get("filed_at") or ""),
        "last_surfaced_ts": None,
        "filed_by": "officer:cos",
        "harm_class": "value_decay",
        "harm_at": req.get("deadline"), "blocked_leverage": 0,
        "steps": None, "injection_suspect": bool(req.get("taint")),
        "lane": None, "aliases": [skey],
    }


# ---------------------------------------------------------------------------
# Live loaders (all injectable, all best-effort)
# ---------------------------------------------------------------------------

def _redis_argv(*args: str) -> str:
    """redis-cli by argv (no shell). '' on any failure."""
    import subprocess
    host = os.environ.get("REDIS_HOST", "localhost")
    try:
        out = subprocess.run(["redis-cli", "-h", host, *args],
                             capture_output=True, text=True, timeout=10)
        return out.stdout
    except Exception:
        return ""


def load_redis_cards() -> dict:
    """{pid: parked chain record} from cabinet:action:* (7d-TTL executable
    records). Best-effort: {} when Redis is unreachable."""
    out: dict = {}
    scan = _redis_argv("--scan", "--pattern", "cabinet:action:*")
    for key in scan.splitlines():
        key = key.strip()
        if not key.startswith("cabinet:action:") or key.startswith(
                "cabinet:action:asks:"):
            continue
        raw = _redis_argv("GET", key).strip()
        if not raw or raw == "(nil)":
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            out[key[len("cabinet:action:"):]] = rec
    return out


def _default_needs():
    try:
        from framework.authority import needs
        return needs.list_open()
    except Exception:
        return []


def _default_t2():
    try:
        from framework.attention import t2
        return t2.pending_requests()
    except Exception:
        return []


# ---------------------------------------------------------------------------
# The census
# ---------------------------------------------------------------------------

def _charter_cap(charter: "dict | None") -> int:
    try:
        cap = ((charter or {}).get("attention_queue") or {}) \
            .get("decisions_render_cap")
        if isinstance(cap, int) and cap > 0:
            return cap
    except Exception:
        pass
    return 7      # C4-ratified default (charter data may override per class)


def build_queue(*, now: "datetime | None" = None,
                view: "dict | None" = None,
                needs_rows: "list | None" = None,
                t2_rows: "list | None" = None,
                redis_cards: "dict | None" = None,
                charter: "dict | None" = None,
                resolve_step: "Callable | None" = None,
                enforce_admission: "bool | None" = None,
                file_overflow_need: "Callable | None" = None) -> dict:
    """Fold every pending-on-Captain source into the ONE ranked census.

    Returns {decisions, directions, org_routed, parked, overflow,
    pending_captain_items, pending_total, by_class, cap, admission_enforced,
    generated_at}. Pure given injected inputs; live defaults otherwise.
    """
    now = now or _now()
    if view is None:
        view = sit_view.build_view()
    if needs_rows is None:
        needs_rows = _default_needs()
    if t2_rows is None:
        t2_rows = _default_t2()
    if redis_cards is None:
        redis_cards = load_redis_cards()
    if charter is None:
        try:
            from framework.attention import charter as charter_mod
            charter = charter_mod.load_charter()
        except Exception:
            charter = {}
    if resolve_step is None:
        resolve_step = make_resolve_step()
    if enforce_admission is None:
        enforce_admission = admission_law_on()

    cards: list = []
    parked: list = []
    for sit in view.values():
        if sit.get("state") == "dormant":
            parked.append(situation_card(sit, now=now))
            continue
        if not sit.get("live"):
            continue
        rec = redis_cards.get(sit.get("pid") or "")
        cards.append(situation_card(sit, now=now, redis_record=rec))
    for row in needs_rows or []:
        cards.append(need_card(row, now=now))
    for req in t2_rows or []:
        cards.append(t2_card(req, now=now))

    decisions_pool: list = []
    directions: list = []
    org_routed: list = []
    for card in cards:
        item = {"steps": card.get("steps") or [],
                "harm_at": card.get("harm_at"),
                "blocked_leverage": card.get("blocked_leverage", 0),
                "injection_suspect": card.get("injection_suspect", False)}
        # A binder/doc card whose parked chain is unavailable (TTL'd Redis
        # record, doc-shaped kind) is still, by construction, awaiting a
        # Captain verdict → synthesized gated step (resolves "gate": an
        # unclassifiable step never reads as org-decidable).
        if not item["steps"] and card.get("kind") in (
                "action-proposal", "draft-outbound", "escalation",
                "outcome-ratification", "germline-handback", "pipe-prompt",
                "founder-action"):
            item["steps"] = [{"action_type": "__captain_gated__"}]
        shelf = admit(item, resolve_step)
        card["admission"] = shelf
        if shelf == "org":
            if enforce_admission:
                org_routed.append(card)
                continue
            # law dark (C3 pending): org-decidable stays visible; shelf by clock
            shelf = "decisions" if card.get("harm_at") else "directions"
        if shelf == "decisions":
            decisions_pool.append(card)
        else:
            directions.append(card)

    cap = _charter_cap(charter)
    rendered, overflow = render_room(decisions_pool, now, cap=cap)
    directions.sort(key=lambda c: rank_key(c, now))

    if overflow:
        filer = file_overflow_need if file_overflow_need is not None \
            else _default_overflow_need
        try:
            filer(len(decisions_pool), cap)
        except Exception:
            pass

    by_class: dict = {}
    for card in rendered + overflow + directions:
        k = str(card.get("kind") or "?")
        by_class[k] = by_class.get(k, 0) + 1

    return {
        "generated_at": _iso(now),
        "decisions": rendered,
        "directions": directions,
        "overflow": len(overflow),
        "overflow_cards": overflow,
        "org_routed": [c["id"] for c in org_routed],
        "parked": [c["id"] for c in parked],
        "pending_captain_items": len(rendered) + len(overflow),
        "pending_total": len(rendered) + len(overflow) + len(directions),
        "by_class": by_class,
        "cap": cap,
        "admission_enforced": bool(enforce_admission),
    }


def _default_overflow_need(pool_size: int, cap: int) -> None:
    """ONE consolidation need on overflow (fingerprint-deduped by need_id —
    re-filing bumps count, never spams). Dark under guardian (file_need
    no-ops when the needs plane is unwired) — deliberately so."""
    from framework.authority import needs
    needs.file_need(
        "decision",
        lane=None, risk_class=None, action_type=None,
        why=(f"org has {pool_size} captain-blocked decisions for a render cap "
             f"of {cap}; Chair must merge, batch, resolve, or justify"),
        unblocks="the Decisions shelf",
        cost_of_delay="high",
        filed_by="system:attention-queue")


# ---------------------------------------------------------------------------
# Projections — one census, N skins (SURFACE-PARITY-LAW)
# ---------------------------------------------------------------------------

def opaque_handle(pid: "str | None") -> "str | None":
    """selHandle-pattern opaque join handle for a pid (pids embed subject
    slugs, so the shared plane never carries them raw)."""
    if not pid:
        return None
    return "q" + hashlib.sha256(
        f"cabinet-queue:{pid}".encode("utf-8")).hexdigest()[:12]


def _card_common(card: dict, now: datetime) -> dict:
    created = sit_view.parse_iso(card.get("created_ts"))
    age_h = round((now - created).total_seconds() / 3600.0, 1) if created else None
    return {
        "id": card["id"], "kind": card["kind"], "state": card["state"],
        "class": card.get("charter_class"),
        "urgency": card.get("urgency"),
        "deadline_iso": card.get("harm_at"),
        "harm_class": card.get("harm_class"),
        "age_h": age_h,
        "blast": {"class": card["blast_radius"]["class"],
                  "reach": card["blast_radius"]["reach"]},
        "decay_stage": card["expiry"]["stage"],
        "admission": card.get("admission"),
    }


def to_private_census(queue: dict) -> dict:
    """The FULL authed census (free text + pids) → the private artifact the
    dashboard/API serves behind the session cookie."""
    now = sit_view.parse_iso(queue["generated_at"]) or _now()

    def full(card: dict) -> dict:
        row = _card_common(card, now)
        row.update({
            "pid": card.get("pid"),
            "h": opaque_handle(card.get("pid")),
            "what": card.get("what"),
            "why_now": card.get("why_now"),
            "refs": [e["ref"] for e in card.get("evidence") or []],
            "one_tap": {k: v.get("semantics") if isinstance(v, dict) else v
                        for k, v in (card.get("one_tap") or {}).items()},
            "blast_worst_case": card["blast_radius"].get("worst_case"),
            "filed_by": card.get("filed_by"),
            "lane": card.get("lane"),
            "standing_message_id": card.get("standing_message_id"),
        })
        return row

    return {
        "v": 1,
        "generated_at": queue["generated_at"],
        "pending_captain_items": queue["pending_captain_items"],
        "pending_total": queue["pending_total"],
        "by_class": queue["by_class"],
        "overflow": queue["overflow"],
        "cap": queue["cap"],
        "admission_enforced": queue["admission_enforced"],
        "decisions": [full(c) for c in queue["decisions"]],
        "directions": [full(c) for c in queue["directions"]],
        "overflow_ids": [c["id"] for c in queue.get("overflow_cards") or []],
        "org_routed": queue.get("org_routed") or [],
        "parked": queue.get("parked") or [],
    }


def _shared_ref_ok(ref: str) -> bool:
    r = ref.lower()
    if "/" in r or "." in r:
        return False   # path/URL-shaped — never shared, even prefix-matched
    if any(r.startswith(p) for p in _SHARED_REF_PREFIXES):
        return True
    return bool(_UUID_RE.fullmatch(r))                  # bare uuid, strictly


def to_shared_census(queue: dict) -> dict:
    """The SHARED artifact projection — world-census PII discipline: opaque
    ids, counts, classes, id-grade opaque refs only. NO subjects, NO pids,
    NO vault paths, NO URLs."""
    now = sit_view.parse_iso(queue["generated_at"]) or _now()

    def scrubbed(card: dict) -> dict:
        row = _card_common(card, now)
        row["h"] = opaque_handle(card.get("pid"))
        row["refs"] = [e["ref"] for e in (card.get("evidence") or [])
                       if _shared_ref_ok(str(e.get("ref", "")))][:8]
        return row

    return {
        "v": 1,
        "generated_at": queue["generated_at"],
        "pending_captain_items": queue["pending_captain_items"],
        "pending_total": queue["pending_total"],
        "by_class": queue["by_class"],
        "overflow": queue["overflow"],
        "cap": queue["cap"],
        "admission_enforced": queue["admission_enforced"],
        "decisions": [scrubbed(c) for c in queue["decisions"]],
        "directions": [scrubbed(c) for c in queue["directions"]],
    }


def _repo_root() -> Path:
    return Path(os.environ.get("CABINET_ROOT") or
                Path(__file__).resolve().parents[2])


def write_artifacts(queue: dict, *, root: "Path | None" = None,
                    attention_dir: "Path | None" = None) -> dict:
    """Write both projections atomically (tmp + os.replace). Returns the two
    paths. Never raises past a loud stderr line — the census must not brick
    the surface drain."""
    import sys
    out = {"private": None, "shared": None}
    try:
        adir = attention_dir or _attention_dir()
        adir.mkdir(parents=True, exist_ok=True)
        p = adir / "queue.json"
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(to_private_census(queue), ensure_ascii=False,
                                  indent=0), encoding="utf-8")
        os.replace(tmp, p)
        out["private"] = str(p)
    except Exception as e:
        print(f"[queue] private census write failed: {e}", file=sys.stderr)
    try:
        r = root or _repo_root()
        sdir = r / "shared" / "interfaces"
        sdir.mkdir(parents=True, exist_ok=True)
        p = sdir / "attention-queue.json"
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(to_shared_census(queue), ensure_ascii=False,
                                  indent=0), encoding="utf-8")
        os.replace(tmp, p)
        out["shared"] = str(p)
    except Exception as e:
        print(f"[queue] shared census write failed: {e}", file=sys.stderr)
    return out
