"""Verdict-supply runner around the B2.8 verifier — the piece that WAKES it.

The 2026-07-03 re-review's core finding: the eval/probe/verifier stack was
"dead at runtime" — verifier.py had no __main__, no services.yml row, no plist;
CABINET_PROBES_ENABLED existed only in comments. This module (lane-supply,
2026-07-05) is the missing claims-derivation + orchestration shell:

  read the consequence ledger → derive the executed act-first action cards'
  implicit success claims → verifier.verify() reconciles each claim against
  the machine outcome its cid has accumulated (undo-sweep ttl_ok, probe
  ok/failed) → emit review{verdict, source: verdict_judge} SUPERSEDES on the
  SAME (actor, lane, action_type) cell the graduation gate reads
  (framework/fidelity/graduation.py::_cell_rows keys identically to
  consequence.compute_ratios — the verdict lands where the gate looks).

WHY claims come from acted cards (and only acted cards), dated 2026-07-05:
  - An acted act-first card (run_action_lane.py:931-936) is emitted with
    proposal {required: False, decision: None} + outcome {status: unknown} and
    a stamped action_type (the act-first gate refuses unstamped cards —
    run_action_lane.py:202). The act EXISTING is the executor's success claim
    ("done"): deliver_action returned ok or no acted row would exist.
  - An APPROVED card already carries review{verdict, source: verdict_human}
    from the Captain's decision (loop.outcome_event:214) — a human verdict is
    senior and must never be machine-overwritten, so approved cards are
    SKIPPED, not claimed.
  - A PENDING/EXPIRED/REJECTED card executed nothing — no claim exists.

FAIL-CLOSED map (every path that is NOT a clean reconciliation yields NO
verdict — Corridor invariant):
  outcome unknown  → verifier RT#4 could-not-observe → skip, no emit
                     (acted but not yet TTL-swept/probed — honest wait);
  outcome ok       → review confirmed / verdict_judge — structurally unable to
                     fuel promotion (flavor-A: compute_ratios counts confirmed
                     only from verdict_human — consequence.py:705);
  outcome failed   → review wrong / verdict_judge — legitimate demotion
                     evidence (wrong counts from ANY source);
  fabrication      → UNREACHABLE from this selection: every acted emit carries
                     outcome unknown, so machine=="none" (the fabrication
                     precondition) cannot occur; this runner can never mint a
                     false demote:direct from its own scope.

IDEMPOTENCE / SENIORITY (derive_claims):
  - review.source == verdict_human → skip forever (human wins, flavor-A);
  - review present but source absent → skip (unattributed legacy — fail-safe);
  - review.source == verdict_judge and the fresh classification equals the
    recorded verdict → skip (no ledger churn on the hourly cadence);
  - review.source == verdict_judge and the machine outcome CHANGED since (e.g.
    a probe superseded ok→failed after we confirmed) → re-claim: machine may
    correct machine, never a human.

Run:  python3.12 -m framework.probes.run_verifier [--dry-run] [--since TS]
  --dry-run: derive + classify + print the would-be verdict rows; the emit is
  an in-memory collector — ZERO ledger writes (the eyeball gate + the fenced
  proof mode). Live emits additionally require CABINET_PROBES_ENABLED=1 (the
  same one-knob guard the probe entrypoints honor).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from typing import Any, Callable

from framework.probes import correlation, lib, verifier

# The one action whose cards this runner reconciles (task scope 2026-07-05:
# executed act-first action cards). Widening to org_events completion claims is
# a later, separate decision — it would open the fabrication path and needs its
# own review.
ACTION_CARD = "action-card"
CLAIMED = "done"        # in verifier._CLAIM_SUCCESS — the acted card's implicit claim
HC_SLUG = "verifier"    # healthchecks liveness slug (check creation is Nate's step)


def _cell_of(row: dict) -> dict:
    """The graduation cell key of a ledger row, exactly as compute_ratios /
    graduation._cell_rows flatten it: actor 'kind:id', lane, action_type."""
    actor = row.get("actor") or {}
    return {"actor": f"{actor.get('kind')}:{actor.get('id')}",
            "lane": row.get("lane"),
            "action_type": row.get("action_type")}


def _outcomes_for(cid: str, rows: list) -> list:
    """All outcome objects the ledger holds for a cid — the same gather
    verifier.verify() does (verifier.py:171-173), reproduced here so the
    idempotence check classifies with EXACTLY the evidence verify() will see."""
    return [e.get("outcome") for e in rows
            if correlation.cid_from_refs(e.get("refs")) == cid
            and isinstance(e.get("outcome"), dict)]


def derive_claims(rows: list) -> dict:
    """PURE: split the ledger's action-card rows into claims + visible skips.

    Returns {"claims": [{cid, claimed}], "skipped": [{cid?, subject, reason}]}.
    Only executed act-first cards (proposal.required == False) become claims;
    everything else is skipped with a reason so the run log is an audit trail,
    never a silent filter (no-silent-caps spirit)."""
    claims: list[dict] = []
    skipped: list[dict] = []
    for row in rows:
        if row.get("action") != ACTION_CARD:
            continue
        subject = row.get("subject", "")
        cid = correlation.cid_from_refs(row.get("refs"))
        if not cid:
            # Pre-B2.1 cards (the 2026-07-03 first-night cohort) carry no cid —
            # nothing can ever join them; visible skip, never a guess [RT#3].
            skipped.append({"subject": subject, "reason": "no-cid"})
            continue

        prop = row.get("proposal") or {}
        if prop.get("required") is not False:
            # required=True ⇒ propose-first card: pending (decision None),
            # approved/edited (human verdict already landed at decision time),
            # rejected or expired — in every shape nothing act-first-executed
            # under THIS identity, so there is no machine claim to verify.
            decision = prop.get("decision")
            skipped.append({"cid": cid, "subject": subject,
                            "reason": f"not-acted (decision={decision})"})
            continue

        review = row.get("review") or {}
        if review:
            source = review.get("source")
            if source == "verdict_human":
                # Flavor-A seniority: a landed human verdict (👍/undo/never) is
                # never machine-overwritten. Permanent skip.
                skipped.append({"cid": cid, "subject": subject,
                                "reason": "human-reviewed (senior — never overwritten)"})
                continue
            if source != "verdict_judge":
                # Unattributed/legacy or system review — fail-safe: do not
                # supersede what we cannot attribute.
                skipped.append({"cid": cid, "subject": subject,
                                "reason": f"unattributed-review (source={source})"})
                continue
            # verdict_judge already recorded: re-claim ONLY if the machine
            # outcome moved since (probe superseded ok→failed or vice versa).
            fresh = verifier.classify_claim(
                claimed=CLAIMED, outcomes=_outcomes_for(cid, rows),
                probes_reachable=True)
            if fresh["verdict"] == review.get("verdict") or fresh["verdict"] is None:
                skipped.append({"cid": cid, "subject": subject,
                                "reason": "already-reconciled (verdict_judge, unchanged)"})
                continue
            # fall through: machine corrects machine (verdict changed).

        claims.append({"cid": cid, "claimed": CLAIMED})
    return {"claims": claims, "skipped": skipped}


def run(*, rows: list | None = None, dry_run: bool = False,
        since: str | None = None, now: str | None = None,
        emit: Callable[..., Any] | None = None,
        read: Callable[..., Any] | None = None) -> dict:
    """One verifier cycle. Injectable for tests; NO external systems touched —
    the ledger is the only input and (live mode) the only output."""
    from framework.fidelity.consequence import emit_consequence, read_ledger
    read = read or read_ledger
    rows = rows if rows is not None else read(since=since)
    now = now or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    derived = derive_claims(rows)
    collected: list[dict] = []
    if dry_run:
        # Collector emit: verify() still validates every event (fail LOUD),
        # but nothing reaches the ledger — the fenced proof path.
        def emit_fn(**ev):
            collected.append(ev)
    else:
        emit_fn = emit or emit_consequence

    res = verifier.verify(claims=derived["claims"], rows=rows,
                          probes_reachable=True, reviewed_at=now, emit=emit_fn)

    # Enrich emitted entries with their graduation cell — the proof that the
    # verdict lands on the exact key the gate reads.
    by_cid = {}
    for e in rows:
        c = correlation.cid_from_refs(e.get("refs"))
        if c:
            by_cid[c] = e      # last write wins (rows are ts-sorted, deduped)
    for em in res["emitted"]:
        em["cell"] = _cell_of(by_cid.get(em["cid"], {}))

    return {"mode": "dry-run" if dry_run else "live", "reviewed_at": now,
            "claims": len(derived["claims"]), "emitted": res["emitted"],
            "verify_skipped": res["skipped"], "card_skips": derived["skipped"],
            "would_write" if dry_run else "wrote": len(res["emitted"]),
            **({"collected_events": collected} if dry_run else {})}


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="classify + print; collector emit — zero ledger writes")
    ap.add_argument("--since", default=None,
                    help="optional ISO ts floor for the ledger read")
    args = ap.parse_args(argv)

    if not args.dry_run and os.environ.get("CABINET_PROBES_ENABLED") != "1":
        # The one-knob guard the deploy templates promised. Exit 0: a disabled
        # runner is a declared state, not a failure (no hc /fail, no page).
        print("verifier: disabled (CABINET_PROBES_ENABLED != '1') — no verdicts emitted")
        return 0

    try:
        result = run(dry_run=args.dry_run, since=args.since)
    except Exception as e:  # noqa: BLE001 — fail-closed: crash → NO verdict, loud log
        print(f"verifier: ERROR — no verdicts emitted ({e!r})", file=sys.stderr)
        if not args.dry_run:
            lib.hc_ping(HC_SLUG, fail=True)
        return 1

    printable = {k: v for k, v in result.items() if k != "collected_events"}
    print(json.dumps(printable, indent=2, sort_keys=False, default=str))
    if not args.dry_run:
        lib.hc_ping(HC_SLUG)   # liveness — fail-open helper (lib.py:130)
    return 0


if __name__ == "__main__":
    sys.exit(main())
