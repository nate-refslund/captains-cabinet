#!/usr/bin/env python3.12
"""framework.watchdog.receipts — typed org-event receipts for the
watchdog/doctor/officer-lifecycle lens (evidence program Phase 2 Batch B).

WHY THIS MODULE EXISTS
=============================================================================
The action surfaces in this lens are shell scripts (cabinet-doctor.sh,
cabinet/cron/heartbeat-watchdog.sh, cabinet/cron/limit-reset-watchdog.sh)
and the stdlib-only checker ``framework/watchdog/check.py``, whose
independence law ("imports NOTHING it watches") forbids importing the org
emitter or the evidence plane in-process.  Their receipts therefore ride
the lawful shell→evidence shape: a DOMAIN org-event emit whose signed
receipt is produced by the org→evidence mirror chokepoint
(``framework/events/emitter.py`` + ``framework/evidence_mirror.py``,
Batch A).

The one silent-failure mode of that shape is path-exec: running
``python3 framework/events/emitter.py …`` leaves the repo root off
``sys.path``, the chokepoint's ``from framework import evidence_mirror``
ImportErrors, and the receipt silently never exists.  This module pins the
working invocation for every caller in the lens::

    (cd "$REPO_ROOT" && python3.12 -m framework.watchdog.receipts \\
        <event_type> '<payload_json>')

MODULE-exec from the repo root on the house interpreter — the mirror import
fires inside this (sub)process and the receipt is signed.

NOT A GENERIC EMIT CLI (by law)
=============================================================================
Producers are code-level seams only — there is no "record this evidence"
CLI.  This module emits ORG events only (domain rows on the breadth
ledger), refuses every class outside its own hard-coded lens set
(``RECEIPT_CLASSES``), and pins a FIXED actor per class so argv can never
spoof identity.  Evidence content is never accepted here: the signed
receipt's content is fixed by the mirror (ids + digests only, redaction
doctrine).

RECORDING CLASS: RECEIPT (per-class contract, design §3 Phase 2 item 3)
=============================================================================
Everything in this lens observes something that ALREADY happened — a routed
watchdog failure, a computed doctor verdict, an attempted officer restart,
a fired limit wake.  Receipts degrade LOUD and never block: every caller
invokes this module best-effort (``|| true``), and the mirror inside the
emitter degrades loud (stderr + doctor marker ledger + best-effort
``evidence_mirror_degraded`` org event) on a broken evidence plane.
Fail-closed recording here would couple the org's recovery machinery
(restarts, wakes, escalations) to evidence-plane health — the self-deadlock
the design forbids (evidence down → no restarts → nobody can repair
evidence).  Restarts-as-act-class is the design's D7/Phase-6 lane, not
Batch B; that choice is named here on purpose.

Must stay importable on system Python 3.9 (a 3.9 caller still lands the
org row; the mirror degrades loud with ``recorder_unimportable`` — the
designed, named coverage gap for 3.9 contexts).
"""
from __future__ import annotations

import json
import sys

# Stdlib-safe at module level: evidence_mirror imports only stdlib top-level
# (its recorder coupling is lazy).  Imported for the allow-list self-check —
# a lens class dropped from the mirror allow-list would silently stop being
# signed; the check makes that LOUD instead of invisible.
from framework import evidence_mirror
from framework.events.emitter import emit

#: The ONLY classes this module may emit — the watchdog/doctor/officer
#: lifecycle lens.  Everything else is refused (exit 2): this is a typed
#: receipt seam, not a generic emit CLI.  Additions are reviewed vocabulary
#: changes (emitter VALID_EVENT_TYPES + mirror allow-list + here, together).
RECEIPT_CLASSES = frozenset({
    "watchdog_outcome_failed",
    "doctor_verdict",
    "officer_restarted",
    "officer_limit_wake",
})

#: Fixed producer identity per class — argv carries DATA only; the org actor
#: is pinned per class and can never be spoofed by a caller (A6-adjacent;
#: broker attestation for daemon writers is a separate ceremony wave).
RECEIPT_ACTORS = {
    "watchdog_outcome_failed": "outcome-watchdog",
    "doctor_verdict": "cabinet-doctor",
    "officer_restarted": "heartbeat-watchdog",
    "officer_limit_wake": "limit-reset-watchdog",
}


def unmirrored_classes() -> frozenset:
    """Lens classes missing from the mirror allow-list (should be empty)."""
    return frozenset(RECEIPT_CLASSES - evidence_mirror.MIRRORED_ORG_EVENT_TYPES)


def emit_receipt(event_type: str, payload: dict) -> dict:
    """Emit one lens receipt (an org row; the chokepoint mirror signs it).

    Raises ValueError on a class outside the lens set — a caller needing a
    new class registers it in the emitter + the mirror allow-list + this
    set (one reviewed vocabulary change), never bypasses.
    """
    if event_type not in RECEIPT_CLASSES:
        raise ValueError(
            "refused: %r is not a watchdog/officer-lifecycle receipt class "
            "(allowed: %s)" % (event_type, ", ".join(sorted(RECEIPT_CLASSES)))
        )
    missing = unmirrored_classes()
    if missing:
        # LOUD, never blocking: the org row still lands and the daily
        # digest-anchor still tamper-evidences the breadth ledger (R-13) —
        # but the per-event signed receipt is gone, which a human must see.
        print(
            "watchdog-receipts: WARN lens class(es) missing from the "
            "evidence-mirror allow-list — org rows land UNSIGNED: %s"
            % ", ".join(sorted(missing)),
            file=sys.stderr,
        )
    return emit(event_type, actor=RECEIPT_ACTORS[event_type], payload=payload)


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 1 or len(args) > 2:
        print(
            "usage: python3.12 -m framework.watchdog.receipts "
            "<event_type> [payload_json]   (MODULE-exec from the repo root "
            "— path-exec never reaches the evidence mirror)",
            file=sys.stderr,
        )
        return 2
    event_type = args[0]
    try:
        payload = json.loads(args[1]) if len(args) == 2 else {}
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
    except ValueError as exc:
        print("watchdog-receipts: bad payload: %s" % exc, file=sys.stderr)
        return 2
    try:
        emit_receipt(event_type, payload)
    except ValueError as exc:
        print("watchdog-receipts: %s" % exc, file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 — callers are `|| true`; be loud
        print("watchdog-receipts: emit failed: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
