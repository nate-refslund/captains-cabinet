"""B2.2 — the probe framework lib (the harness every outcome probe emits through).

An outcome probe (B2.3-B2.7) observes an external artifact, joins it to its
proposal via the B2.1 correlation-id, and records the RESULT as a schema-valid
consequence outcome. This module is that shared spine: the join, the emit, the
silent-source guard, and the healthcheck ping — so each probe is only its own
source-specific read-back rule on top.

Schema reality this encodes (framework/fidelity/consequence.py):
  - `outcome` carries ONLY {status, evidence}; status ∈ {ok, failed, unknown};
    evidence REQUIRED for ok/failed, MUST be absent for unknown.
  - So the probe's rich label (ci_green/reverted/regressed/…), its confidence,
    and its source live in `refs` (a validated string array), never in a
    confidence field that does not exist.
RT#3: an artifact whose id maps to no proposal is UNATTRIBUTABLE — we emit
nothing and credit no officer, rather than manufacture an attribution.
"""
from __future__ import annotations

import os
import urllib.request
from typing import Any, Callable

from framework.acting import loop
from framework.fidelity.consequence import emit_consequence, validate_consequence
from framework.probes import correlation

STATUSES = ("ok", "failed", "unknown")          # canonical outcome.status
CONFIDENCE = ("high", "medium", "low")          # deterministic=high, advisory=low

# refs metadata prefixes (queryable; kept out of the schema-frozen outcome object)
_SOURCE_PREFIX = "probe:"
_PROBE_STATUS_PREFIX = "probe-status:"
_CONFIDENCE_PREFIX = "confidence:"


def find_proposal_by_cid(cid: str, rows: list | None = None) -> dict | None:
    """The LAST ledger event whose refs carry cabinet-proposal-id:<cid>, else None.

    Last-write-wins: a proposal's identity tuple appears on the pending event and
    again on the decided/outcome event; the most recent carries the current state
    (decision, any prior outcome). ``rows`` injectable for tests."""
    if not correlation.is_cid(cid or ""):
        return None
    rows = rows if rows is not None else loop.read_ledger(since=None)
    found = None
    for e in rows:
        if isinstance(e, dict) and correlation.cid_from_refs(e.get("refs")) == cid:
            found = e
    return found


def emit_outcome(
    *,
    cid: str,
    status: str,
    probe_status: str,
    source: str,
    confidence: str,
    evidence: str | None = None,
    observed_at: str | None = None,
    extra_refs: list | None = None,
    rows: list | None = None,
    emit: Callable[..., Any] = emit_consequence,
    find: Callable[..., Any] = find_proposal_by_cid,
) -> dict:
    """Record a probe observation as a SUPERSEDING outcome event on the proposal
    the cid resolves to. Returns {emitted: bool, ...}.

    - status ∈ {ok, failed, unknown} (canonical); probe_status is the rich label.
    - Unattributable cid → no emit (RT#3). Unexecuted proposal → no emit: a
      pending propose-first ask (required=true, decision null) has no outcome to
      observe. Executed = approved (decision set) OR act-first ACTED
      (required=false — decision stays null forever on acted rows; guard
      updated lane-supply 2026-07-05, see the inline note below).
    - The rich label + confidence + source go in refs; the proposal's own refs
      (incl. the cid) are preserved so the join survives. A probe may pass
      ``extra_refs`` for source-specific metadata that also belongs in refs —
      e.g. the B2.6 CI probe's ``graduation-credit:false`` Goodhart guard (a
      green CI on a test-only diff is not evidence the feature works). These are
      appended verbatim; the frozen outcome object still carries only
      {status, evidence}.
    """
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}; got {status!r}")
    if confidence not in CONFIDENCE:
        raise ValueError(f"confidence must be one of {CONFIDENCE}; got {confidence!r}")

    prop = find(cid, rows=rows)
    if prop is None:
        return {"emitted": False, "reason": "unattributable-cid", "cid": cid}
    # Execution guard (updated lane-supply 2026-07-05): a probe outcome presumes
    # an EXECUTED proposal. Two executed shapes exist since the act-first ruling
    # (2026-07-03/04): (a) propose-first, approved by the Captain (decision set);
    # (b) act-first ACTED — proposal.required is False and decision stays None
    # FOREVER (an unattended act was never proposed; binder_wire.
    # acted_verdict_event:194 pins that shape). The original decision-only guard
    # predates act-first and silently blinded every probe to acted cards — the
    # exact rows the verdict-supply loop reconciles. required=True + decision
    # None (a live pending ask) is still refused: nothing executed yet.
    _p = prop.get("proposal") or {}
    if _p.get("decision") is None and _p.get("required") is not False:
        return {"emitted": False, "reason": "proposal-not-decided", "cid": cid}

    ev = dict(prop)
    # refs: preserve the proposal's (carries the cid) + append probe metadata
    meta = [f"{_SOURCE_PREFIX}{source}",
            f"{_PROBE_STATUS_PREFIX}{probe_status}",
            f"{_CONFIDENCE_PREFIX}{confidence}"]
    if observed_at:
        meta.append(f"observed-at:{observed_at}")
    if extra_refs:
        meta.extend(str(r) for r in extra_refs)   # source-specific refs (e.g. B2.10)
    ev["refs"] = list(prop.get("refs") or []) + meta

    if status == "unknown":
        ev["outcome"] = {"status": "unknown"}         # evidence MUST be absent
    else:
        ev["outcome"] = {"status": status,
                         "evidence": evidence or f"{source}:{probe_status}"}

    validate_consequence(ev)          # fail LOUD before the ledger, never after
    emit(**ev)
    return {"emitted": True, "event": ev, "cid": cid,
            "status": status, "probe_status": probe_status}


def freshness_guard(*, observed: Any, activity_expected: bool, source: str) -> dict:
    """The silent-source guard. If activity is expected (e.g. local git shows
    pushes in the window) but the source returned nothing, a probe must NOT read
    that silence as a clean zero — it emits ``unknown`` ('could-not-observe').

    Returns {fresh: True} to proceed, or {fresh: False, action: 'emit-unknown',
    reason, source} to force the honest unknown."""
    is_empty = observed is None or (hasattr(observed, "__len__") and len(observed) == 0)
    if activity_expected and is_empty:
        return {"fresh": False, "action": "emit-unknown",
                "reason": "source-silent-while-activity-expected", "source": source}
    return {"fresh": True}


def hc_ping(slug: str, fail: bool = False) -> str:
    """Register liveness/failure with healthchecks.io (off-machine dead-man).
    Fail-open: a missing key or a network error never breaks the probe."""
    key = os.environ.get("HEALTHCHECKS_PING_KEY", "")
    if not key:
        return "no-ping-key"
    url = f"https://hc-ping.com/{key}/{slug}" + ("/fail" if fail else "")
    try:
        urllib.request.urlopen(url, timeout=10).read()
        return "fail-pinged" if fail else "pinged"
    except Exception as e:  # noqa: BLE001 — liveness ping must never raise
        return f"ping-error: {e!r}"
