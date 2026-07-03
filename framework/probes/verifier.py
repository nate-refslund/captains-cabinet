"""B2.8 — the dual-source verifier (never trust the actor's narrative).

Officers write CLAIMS (a progress file, a completion event: "fixed + deployed").
Tools write LOGS (the B2.3-B2.7 probe outcomes, joined by the B2.1
correlation-id). This module reads BOTH and writes NEITHER source — it emits only
``review.verdict``, the machine's judgment of whether the claim matches reality.
Read-only against the world, append-only against the ledger; ``launchctl
bootout`` disables it with zero behavior change.

ORDER OF OPERATIONS per claim — classification FIRST [RT#4]:

  1. CLASSIFICATION GATE. If the probes were not reachable, or the outcome for
     the cid is ``unknown`` (could-not-observe), evaluation ENDS with no verdict.
     An upstream outage is never an agent fault and never a fabrication signal —
     a Vercel outage must produce NO flag, not a false "you lied".
  2. DETERMINISTIC RECONCILIATION (AUTHORITATIVE). Claim ↔ machine truth, keyed
     by correlation-id. A success claim with zero probe evidence while probes
     were reachable is FABRICATION → a ``wrong`` verdict that demotes.
  3. ADVISORY (Haiku) pass. Injectable, recorded in refs, NEVER authoritative —
     a weak same-family judge misses hallucinations, so it may corroborate or
     dissent but can never flip the deterministic verdict.

SCHEMA REALITY: the consequence review object is {verdict, reviewed_at,
lesson_ref} with verdict ∈ {confirmed, wrong, unknown}. There is no
"fabrication" verdict — fabrication is a ``wrong`` verdict carrying a
``verdict-kind:fabrication`` + ``demote:direct`` marker in refs, which the
graduation layer consumes (B2.9) for direct demotion. ``verdict_source`` rides in
refs (the review object is frozen).

DEFERRED (documented, NOT built here — deploy/follow-on):
  - the LIVE Haiku pass (through framework/fidelity/oauth_llm.py's clean cwd);
    here it is an injected callable, no LLM call in this module or its tests.
  - com.cabinet.verifier.plist (hourly) — deploy is Nate-gated.
  - the penalty-free escalate/self-flag(reason) officer-prompt tool line
    (shared F0.16) — a graduation calibration INPUT, wired officer-side.
  - graduation's direct-demote-on-fabrication consumption of demote:direct (B2.9).
"""
from __future__ import annotations

from typing import Any, Callable

from framework.acting import loop
from framework.fidelity.consequence import (
    DIRECT_DEMOTE_REF,
    emit_consequence,
    validate_consequence,
)
from framework.probes import correlation
from framework.probes import lib

VERDICT_SOURCE = "verdict_judge"          # machine reconciliation (vs verdict_human)

# verdict KINDs — richer than the 3-value schema verdict; carried in refs.
KIND_CONFIRMED = "confirmed"              # claim agrees with the machine
KIND_CONTRADICTION = "contradiction"     # claim disagrees with the machine (→ wrong)
KIND_FABRICATION = "fabrication"         # success claim, zero evidence, probes reachable (→ wrong, direct-demote)
KIND_HONEST_UNKNOWN = "honest-unknown"   # honest uncertainty / self-flag (→ unknown, never scored)
KIND_COULD_NOT_OBSERVE = "could-not-observe"  # RT#4 gate → NO verdict

# How a claim's narrative maps to success / failure / honest-uncertainty. An
# unrecognized claim word is treated as honest uncertainty (never scored wrong) —
# the safe default that never punishes a non-boastful report.
_CLAIM_SUCCESS = {"success", "ok", "done", "fixed", "deployed", "shipped",
                  "complete", "completed", "resolved", "merged", "passed"}
_CLAIM_FAILURE = {"failure", "failed", "broken", "error", "reverted", "rolled_back"}


def _effective_machine(outcomes: list) -> str:
    """Aggregate probe outcome statuses to ONE machine truth for a cid.

    ``failed`` if ANY probe recorded failed (a regression supersedes a clean
    deploy); else ``ok`` if any ok; else ``unknown`` if outcomes exist but all
    are could-not-observe; else ``none`` (probes reachable, provable ZERO
    evidence — the fabrication precondition for a success claim)."""
    statuses = [(o or {}).get("status") for o in (outcomes or [])]
    statuses = [s for s in statuses if s]
    if "failed" in statuses:
        return "failed"
    if "ok" in statuses:
        return "ok"
    if "unknown" in statuses:
        return "unknown"
    return "none"


def _claim_kind(claimed: str) -> str:
    c = (claimed or "").strip().lower()
    if c in _CLAIM_SUCCESS:
        return "success"
    if c in _CLAIM_FAILURE:
        return "failure"
    return "uncertain"


def classify_claim(*, claimed: str, outcomes: list, probes_reachable: bool) -> dict:
    """Reconcile one officer claim against the machine truth (PURE).

    Returns {verdict, kind, evidence, demote}. ``verdict`` is
    'confirmed'|'wrong'|'unknown' (a schema verdict) or None — None means NO
    emit (the RT#4 could-not-observe gate). ``demote`` flags a direct-demotion
    fabrication for the graduation layer."""
    machine = _effective_machine(outcomes)
    claim = _claim_kind(claimed)

    # 1. CLASSIFICATION GATE FIRST [RT#4] — upstream outage ≠ agent fault.
    if not probes_reachable or machine == "unknown":
        return {"verdict": None, "kind": KIND_COULD_NOT_OBSERVE, "demote": False,
                "evidence": "probes unreachable or could-not-observe — no verdict"}

    # Honest uncertainty / self-flag is NEVER scored wrong (self-flag calibration:
    # fitness must not reward confident success over honest 'I don't know').
    if claim == "uncertain":
        return {"verdict": "unknown", "kind": KIND_HONEST_UNKNOWN, "demote": False,
                "evidence": f"officer claimed uncertain; machine={machine}"}

    # 2. DETERMINISTIC RECONCILIATION (authoritative).
    if claim == "success":
        if machine == "ok":
            return {"verdict": "confirmed", "kind": KIND_CONFIRMED, "demote": False,
                    "evidence": "claim success matches probe ok"}
        if machine == "failed":
            return {"verdict": "wrong", "kind": KIND_CONTRADICTION, "demote": False,
                    "evidence": "claim success but a probe recorded failed"}
        # machine == "none": reachable, ZERO evidence for a success claim → fabrication.
        return {"verdict": "wrong", "kind": KIND_FABRICATION, "demote": True,
                "evidence": "claim success with NO probe evidence while probes reachable"}

    # claim == "failure"
    if machine == "failed":
        return {"verdict": "confirmed", "kind": KIND_CONFIRMED, "demote": False,
                "evidence": "claim failure matches probe failed"}
    if machine == "ok":
        return {"verdict": "wrong", "kind": KIND_CONTRADICTION, "demote": False,
                "evidence": "claim failure but a probe recorded ok"}
    # machine == "none": no positive evidence either way — a failure claim without
    # evidence is NOT fabrication (fabrication is claiming success). Honest unknown.
    return {"verdict": "unknown", "kind": KIND_HONEST_UNKNOWN, "demote": False,
            "evidence": "claim failure with no probe evidence"}


def verify(
    *,
    claims: list,
    rows: list | None = None,
    probes_reachable: bool = True,
    advisory: Callable[..., Any] | None = None,
    reviewed_at: str | None = None,
    emit: Callable[..., Any] = emit_consequence,
    find: Callable[..., Any] = lib.find_proposal_by_cid,
) -> dict:
    """Verify a batch of officer claims. Returns {emitted:[...], skipped:[...]}.

    Each claim is {cid, claimed}. For each: join to its proposal by cid, gather
    that cid's probe outcomes from ``rows``, classify (classification-gate first),
    run the injected advisory (recorded, non-authoritative), and — when there is
    a verdict — emit a SUPERSEDING event carrying only a fresh ``review.verdict``
    (the proposal's decision + probe outcome are inherited unchanged)."""
    rows = rows if rows is not None else loop.read_ledger(since=None)
    emitted, skipped = [], []

    for claim in claims:
        cid = claim.get("cid")
        if not correlation.is_cid(cid or ""):
            skipped.append({"cid": cid, "reason": "not-a-cid"})
            continue
        prop = find(cid, rows=rows)
        if prop is None:
            skipped.append({"cid": cid, "reason": "unattributable-cid"})
            continue

        outcomes = [e.get("outcome") for e in rows
                    if correlation.cid_from_refs(e.get("refs")) == cid
                    and isinstance(e.get("outcome"), dict)]
        result = classify_claim(claimed=claim.get("claimed", ""), outcomes=outcomes,
                                probes_reachable=probes_reachable)

        # ADVISORY (Haiku) — recorded, NEVER authoritative. A failing advisory
        # call must not break the deterministic path.
        adv = None
        if advisory is not None:
            try:
                adv = advisory(claim, outcomes)
            except Exception:  # noqa: BLE001 — advisory is best-effort, never load-bearing
                adv = None

        if result["verdict"] is None:      # RT#4: no verdict, no emit
            skipped.append({"cid": cid, "reason": result["kind"]})
            continue

        ev = dict(prop)
        # source=verdict_judge at the SCHEMA level (not just refs meta): the
        # flavor-A promotion split reads review.source, so a machine confirmed
        # is structurally incapable of fueling promotion (it may hold/demote).
        ev["review"] = {"verdict": result["verdict"],   # lesson_ref absent (minted downstream)
                        "source": VERDICT_SOURCE}
        if reviewed_at:
            ev["review"]["reviewed_at"] = reviewed_at
        meta = [f"verdict-source:{VERDICT_SOURCE}", f"verdict-kind:{result['kind']}"]
        if result["demote"]:
            meta.append(DIRECT_DEMOTE_REF)
        if adv is not None:
            meta.append(f"advisory-verdict:{adv}")
            meta.append(f"advisory-agrees:{str(adv == result['verdict']).lower()}")
        ev["refs"] = list(prop.get("refs") or []) + meta

        validate_consequence(ev)           # fail LOUD before the ledger
        emit(**ev)
        emitted.append({"cid": cid, "verdict": result["verdict"], "kind": result["kind"],
                        "demote": result["demote"], "advisory": adv})

    return {"emitted": emitted, "skipped": skipped}
