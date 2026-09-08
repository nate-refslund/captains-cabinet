#!/usr/bin/env python3.12
"""worker.py — the scripted worker of the one-responsibility drill.

It is deliberately NOT a re-implementation of the pull path. It calls exactly
what the locked hook calls (cabinet/scripts/hooks/session-task-inject.sh:28-34):

    from framework.missions.session_bridge import get_next_task
    task = get_next_task(<slug>, cabinet_root=<root>)

with ``CABINET_WORKER_ID`` set to the holder, then records its result under
``<root>/evidence/<task_id>.txt`` and closes the item through
``framework.missions.claims.complete(...)`` — the function
``work-graph-complete.sh --claim`` calls.  A worker that emitted directly
would prove nothing about the path an officer actually walks.

MODES
  pull      one pull, print the result, exit.  No claim module needed, so it
            is the mode the claim race (P2) uses: on a tree with no claims
            module every puller still gets a task, which is the red the
            drill's P2 names.
  work      pull -> write ``claimed.<holder>`` -> (optionally renew on a tick
            and block on a ``proceed`` sentinel) -> write evidence -> complete.
  complete  close a task claimed by somebody else (the locked hook), with the
            holder and claim id the drill read back out of the ledger.

OUTPUT is one JSON object on stdout — the drill parses it; everything human
goes to stderr.  Exit codes:

  0   the mode ran (a pull that found nothing is a result, not a failure)
  4   the completion was REFUSED by the claim fence (stale/foreign/absent token)
  21  a module the pull path needs could not be imported — the measurement was
      impossible, which is a different fact from a measurement that failed
  1   anything else, with the reason in ``error``

Python 3.9 clean on purpose (A0.3): this file is not on the locked hook's
import path today, but it lives one edit away from it and the pull path it
drives is 3.9 law.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

EXIT_OK = 0
EXIT_REFUSED = 4
EXIT_NO_MODULE = 21
EXIT_ERROR = 1


def _emit(result: Dict[str, Any], code: int) -> int:
    sys.stdout.write(json.dumps(result, sort_keys=True, default=str) + "\n")
    sys.stdout.flush()
    return code


def _import(root: str, dotted: str):
    """Import *dotted* with *root* on sys.path, or raise ImportError."""
    if root not in sys.path:
        sys.path.insert(0, root)
    __import__(dotted)
    return sys.modules[dotted]


def _sleep(seconds: float) -> None:
    # Inline and bounded. macOS has no timeout(1) and this file must not grow
    # a waiter that outlives the run.
    if seconds > 0:
        time.sleep(seconds)


def _now() -> float:
    return time.time()


def _task_fields(task: Dict[str, Any]) -> Dict[str, Any]:
    """The fields the drill asserts on, absent-safe.

    ``claim_id``/``expires_at``/``holder`` appear only once the claim unit has
    landed; reading them with ``.get`` is what lets one worker measure both the
    pre-change and post-change pull path.
    """
    return {
        "task_id": task.get("task_id"),
        "outcome_id": task.get("outcome_id"),
        "assigned_role": task.get("assigned_role"),
        "task_description": task.get("task_description"),
        "claim_id": task.get("claim_id"),
        "expires_at": task.get("expires_at"),
        "holder": task.get("holder"),
    }


def _outcome_id_of(task: Dict[str, Any], task_id: str) -> Optional[str]:
    """The outcome a task belongs to.

    The pull path carries ``outcome_id`` once the claim unit lands.  Before it
    does, the compiler's own id grammar (``<outcome>-task-NNN``) is the only
    thing available, and reading it here keeps the worker usable against both.
    """
    explicit = task.get("outcome_id")
    if explicit:
        return str(explicit)
    marker = "-task-"
    if marker in task_id:
        return task_id.rsplit(marker, 1)[0]
    return None


def _write_evidence(root: str, task: Dict[str, Any], holder: str,
                    claim_id: Optional[str]) -> str:
    evidence_dir = Path(root) / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / ("%s.txt" % task["task_id"])
    lines = [
        "task: %s" % task.get("task_id"),
        "holder: %s" % holder,
        "claim: %s" % (claim_id or "<none>"),
        "recorded_at: %s" % time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "what was done: %s" % (task.get("task_description") or ""),
    ]
    for criterion in task.get("verification_criteria") or []:
        lines.append("criterion met: %s" % criterion)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def _pull(root: str, slug: str, holder: str) -> Dict[str, Any]:
    os.environ["CABINET_WORKER_ID"] = holder
    bridge = _import(root, "framework.missions.session_bridge")
    task = bridge.get_next_task(slug, cabinet_root=root)
    if not task:
        return {"task": None}
    return {"task": dict(task)}


def _renew_until(claims_mod, claim_id: str, holder: str, deadline: float,
                 every: float, proceed: Path, renewed_file: Path) -> int:
    """Renew on a tick until ``proceed`` appears or the deadline passes.

    The tick is the point (A2.1): a lease that only renews when it is nearly
    spent is not renewed by a real officer at all, because the officer's tick
    is fixed and the lease is long.  ``renewed_file`` is how the drill knows a
    tick has actually happened, so it can kill AFTER one rather than before.
    """
    renewals = 0
    while _now() < deadline:
        if proceed.exists():
            return renewals
        _sleep(every)
        renew = getattr(claims_mod, "renew", None)
        if renew is None:
            continue
        try:
            if renew(claim_id, holder):
                renewals += 1
                renewed_file.write_text(str(renewals) + "\n", encoding="utf-8")
        except Exception as exc:  # a renewal failure is data, not a crash
            sys.stderr.write("worker: renew failed: %r\n" % (exc,))
    return renewals


def mode_pull(args) -> int:
    try:
        pulled = _pull(args.root, args.slug, args.holder)
    except ImportError as exc:
        return _emit({"ok": False, "mode": "pull", "holder": args.holder,
                      "module_error": "framework.missions.session_bridge",
                      "error": str(exc)}, EXIT_NO_MODULE)
    task = pulled["task"]
    result = {"ok": True, "mode": "pull", "holder": args.holder,
              "task": None if task is None else _task_fields(task)}
    return _emit(result, EXIT_OK)


def mode_work(args) -> int:
    state = Path(args.state_dir) if args.state_dir else Path(args.root)
    state.mkdir(parents=True, exist_ok=True)
    try:
        pulled = _pull(args.root, args.slug, args.holder)
    except ImportError as exc:
        return _emit({"ok": False, "mode": "work", "holder": args.holder,
                      "module_error": "framework.missions.session_bridge",
                      "error": str(exc)}, EXIT_NO_MODULE)
    task = pulled["task"]
    if task is None:
        return _emit({"ok": True, "mode": "work", "holder": args.holder,
                      "task": None, "completed": False}, EXIT_OK)

    fields = _task_fields(task)
    claim_id = fields.get("claim_id")
    # The claimed sentinel is written AFTER the claim so a drill that kills on
    # it is killing a worker that already holds the item — killing before the
    # claim would test nothing.
    (state / ("claimed.%s" % args.holder)).write_text(
        json.dumps(fields, sort_keys=True, default=str) + "\n", encoding="utf-8")

    try:
        claims_mod = _import(args.root, "framework.missions.claims")
    except ImportError as exc:
        return _emit({"ok": False, "mode": "work", "holder": args.holder,
                      "task": fields, "completed": False,
                      "module_error": "framework.missions.claims",
                      "error": str(exc)}, EXIT_NO_MODULE)

    renewals = 0
    if args.pause_before_complete:
        proceed = Path(args.proceed_file) if args.proceed_file else (state / "proceed")
        deadline = _now() + args.pause_timeout
        renewals = _renew_until(claims_mod, claim_id, args.holder, deadline,
                                args.renew_every, proceed,
                                state / ("renewed.%s" % args.holder))
        if not proceed.exists():
            return _emit({"ok": False, "mode": "work", "holder": args.holder,
                          "task": fields, "completed": False, "renewals": renewals,
                          "error": "proceed sentinel never appeared within %ss"
                                   % args.pause_timeout}, EXIT_ERROR)

    return _complete(args, claims_mod, task, fields, claim_id, renewals)


def _complete(args, claims_mod, task, fields, claim_id, renewals) -> int:
    task_id = fields["task_id"]
    outcome_id = _outcome_id_of(task, task_id)
    evidence_path = _write_evidence(args.root, task, args.holder, claim_id)
    refused = getattr(claims_mod, "ClaimRefused", None)
    try:
        claims_mod.complete(task_id, outcome_id, args.holder,
                            claim_id=claim_id, status=args.status,
                            evidence_text="recorded by %s" % args.holder,
                            evidence_path=evidence_path)
    except Exception as exc:
        code = getattr(exc, "code", None) or str(exc)
        is_refusal = refused is not None and isinstance(exc, refused)
        return _emit({"ok": False, "mode": args.mode, "holder": args.holder,
                      "task": fields, "completed": False, "renewals": renewals,
                      "refused": code if is_refusal else None,
                      "evidence_path": evidence_path,
                      "error": repr(exc)},
                     EXIT_REFUSED if is_refusal else EXIT_ERROR)
    return _emit({"ok": True, "mode": args.mode, "holder": args.holder,
                  "task": fields, "completed": True, "renewals": renewals,
                  "evidence_path": evidence_path}, EXIT_OK)


def mode_complete(args) -> int:
    if not args.task_id:
        return _emit({"ok": False, "mode": "complete",
                      "error": "--task-id is required in complete mode"}, EXIT_ERROR)
    try:
        claims_mod = _import(args.root, "framework.missions.claims")
    except ImportError as exc:
        return _emit({"ok": False, "mode": "complete", "holder": args.holder,
                      "module_error": "framework.missions.claims",
                      "error": str(exc)}, EXIT_NO_MODULE)
    task = {"task_id": args.task_id, "outcome_id": args.outcome_id,
            "task_description": args.description or args.task_id,
            "verification_criteria": []}
    fields = _task_fields(task)
    fields["claim_id"] = args.claim_id
    return _complete(args, claims_mod, task, fields, args.claim_id, 0)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="scripted worker for the one-responsibility drill")
    p.add_argument("--root", required=True, help="cabinet root of the scratch hatch")
    p.add_argument("--slug", default="", help="role slug to pull for")
    p.add_argument("--holder", required=True, help="explicit holder id (CABINET_WORKER_ID)")
    p.add_argument("--lease", type=int, default=None,
                   help="lease seconds for this worker (exported as CABINET_CLAIM_LEASE_SECONDS)")
    p.add_argument("--mode", choices=("pull", "work", "complete"), default="work")
    p.add_argument("--pause-before-complete", action="store_true",
                   help="block on the proceed sentinel between claim and completion")
    p.add_argument("--proceed-file", default=None)
    # <= 30 s by contract (§4 Interface: "every wait a bounded inline poll
    # (<= 30 s)"). The drill's own polls inside this window are 10 s to the
    # claim and 15 s to the first renewal, so 30 s is the whole waiting budget
    # of the stage and not a number anyone has to reach.
    p.add_argument("--pause-timeout", type=float, default=30.0)
    p.add_argument("--renew-every", type=float, default=1.0,
                   help="renewal tick while paused (the officer's wake cadence, scaled)")
    p.add_argument("--state-dir", default=None, help="where claimed.<holder> is written")
    p.add_argument("--status", default="done", choices=("done", "failed"))
    p.add_argument("--task-id", default=None)
    p.add_argument("--outcome-id", default=None)
    p.add_argument("--claim-id", default=None)
    p.add_argument("--description", default=None)
    p.add_argument("--json", action="store_true",
                   help="accepted for symmetry; stdout is always one JSON object")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.lease is not None:
        os.environ["CABINET_CLAIM_LEASE_SECONDS"] = str(args.lease)
    os.environ["CABINET_WORKER_ID"] = args.holder
    if args.mode == "pull":
        return mode_pull(args)
    if args.mode == "complete":
        return mode_complete(args)
    return mode_work(args)


if __name__ == "__main__":
    sys.exit(main())
