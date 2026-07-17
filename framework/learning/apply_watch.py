"""Apply-watch [D15, sovereign spec §4 SOV-8] — 72h auto-rollback ledger for
the DARK germline apply lane.

When (and only when) the Captain has armed the DARK apply lane
(`cabinet/scripts/gate-apply.sh` via an explicit `sudo launchctl load` of
`com.cabinet.gate-apply` — never a setup script), every applied evidence pack
is recorded HERE and watched for 72h. This module is pure DECISION logic:
`evaluate()` returns `rollback | close | watch` rows; the ROOT DAEMON is the
only executor (it applies the recorded revert plan) — nothing in this module
mutates the tree, so it is safe to import and run unprivileged anywhere.

Red signals within the window (any one ⇒ rollback):
  * a kind FROZEN after the apply (the brakes fired — action_undo freeze
    mirror rows newer than applied_at),
  * a RED canary receipt after the apply,
  * any injected checker saying red (the daemon wires its own probes).

Ledger IO mirrors framework/authority/needs.py: O_APPEND JSONL at
shared/interfaces/gate-apply-watch.jsonl, ONE os.write per event,
last-write-wins per pack_id — concurrent appenders interleave without
corruption. DATA is runtime state (SKIP-class); this MODULE is Ring-0.

Evidence plane (Phase 2 Batch B, per-class recording contract):

  * APPLY (widening) is ACT-CLASS FAIL-CLOSED: the daemon calls
    ``evidence_before_apply()`` BEFORE ``git apply`` mutates the live tree;
    if the evidence plane cannot record the intent, the helper raises and
    the apply MUST refuse before any mutation (evidence-before-action).
  * ROLLBACK (tightening — the brake) is ACT-CLASS WITH THE BRAKE
    EXCEPTION: rollback intent is recorded before the decision releases,
    but a broken evidence plane degrades LOUD and the decision still
    releases — an evidence plane that can block the brake would leave a
    bad germline apply un-revertable (design §2.6 posture asymmetry, B10).
  * watch-open / watch-close / revert outcomes are RECEIPTS: degrade LOUD,
    never block the watch-ledger write (the domain write).  The per-pass
    ``watch`` (still-inside-window) decision is trigger exhaust and is
    NEVER recorded.

Evidence rows CITE the pack and the watch-ledger rows (pack_id-keyed);
they never enrich or rewrite them.  One trial per pack
(``gate-apply-<pack_id>``) carries the whole apply→watch→revert story.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

_FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]
if str(_FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(_FRAMEWORK_ROOT))

WATCH_WINDOW_H = 72

_STATUSES = frozenset({"watching", "rollback", "closed"})


def _root(root: str | Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(os.environ.get("CABINET_ROOT") or str(_FRAMEWORK_ROOT))


def watch_path(root: str | Path | None = None) -> Path:
    return _root(root) / "shared" / "interfaces" / "gate-apply-watch.jsonl"


def _now(now: str | None = None) -> str:
    if now:
        return now
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(ts: Any) -> datetime | None:
    try:
        return datetime.strptime(str(ts or ""), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _append(path: Path, row: dict[str, Any]) -> None:
    """ONE os.write on an O_APPEND fd — same concurrency posture as needs.py."""
    line = (json.dumps(row, default=str) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)


def _merged(path: Path) -> dict[str, dict[str, Any]]:
    """Compacted view: last written row wins per pack_id. Torn lines skipped."""
    state: dict[str, dict[str, Any]] = {}
    try:
        if not path.exists():
            return {}
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("pack_id"):
                state[str(row["pack_id"])] = row
    except OSError:
        return {}
    return state


# ---------------------------------------------------------------------------
# Evidence plane — Phase 2 Batch B direct producer (design §3 Ph2 item 2b)
# ---------------------------------------------------------------------------

# Store root is explicit: <cabinet root>/ + the journey producer's
# EVIDENCE_REL — the ONE canonical store constant, imported lazily at the
# recorder seam (the evidence_mirror._production_store_root idiom; keeps
# this module 3.9-importable and the layer boundary in one place) — never
# CABINET_EVIDENCE_DIR-derived (A10).
_EVIDENCE_SURFACE = "system"
# Process-constant fallback identity (the evidence-mirror fixed-identity
# pattern): never payload-derived, never env-derived.  When the hosting
# process attested via framework.evidence.identity the attested identity
# wins and events carry ``attestation_mode: process``.
_EVIDENCE_ACTOR = {"kind": "system", "id": "gate-apply-watch"}
_EVIDENCE_COMPONENT = {"name": "gate-apply-watch", "version": "1",
                       "commit": "unset"}


class GateApplyEvidenceError(RuntimeError):
    """Evidence-plane refusal for the apply lane's act-class seams.

    Raised by :func:`evidence_before_apply` when the evidence plane cannot
    record — the caller must refuse the apply BEFORE any tree mutation.
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _warn(msg: str) -> None:
    print(f"gate-apply-watch: WARN {msg}", file=sys.stderr)


def _evidence_identity() -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """(actor, component, attestation detail) for this producer's events."""
    try:
        from framework.evidence import identity
        if identity.is_attested():
            return (identity.attested_actor(), identity.attested_component(),
                    identity.attestation_detail())
    except Exception:
        pass
    return dict(_EVIDENCE_ACTOR), dict(_EVIDENCE_COMPONENT), {}


def _pack_trial_id(pack_id: str) -> str:
    """One evidence trial per pack: ``gate-apply-<pack_id>`` (id-validated —
    an id the recorder would refuse must never fork the two planes)."""
    from framework.evidence.lifecycle import valid_id_or_none
    trial_id = f"gate-apply-{pack_id}"
    if valid_id_or_none(trial_id) is None:
        raise GateApplyEvidenceError(
            "evidence_id_invalid",
            f"pack id {pack_id!r} cannot name an evidence trial")
    return trial_id


def _evidence_lifecycle(pack_id: str, root: str | Path | None, *,
                        degrade: bool):
    """Recorder + ActLifecycle on the explicit store root (lazy import — the
    sanctioned producer seam; framework/evidence is Ring-0)."""
    if os.geteuid() == 0:
        # Root-ownership poisoning guard (the grant-apply sudo -u law): a
        # root-minted store/trial file breaks every later user-context
        # append.  Refused BEFORE any store byte exists — the fail-closed
        # apply arm refuses, receipt/brake arms degrade loud.
        raise GateApplyEvidenceError(
            "evidence_root_refused",
            "evidence appends never run as root — drop to the invoking user")
    from framework.evidence.lifecycle import ActLifecycle
    from framework.evidence.recorder import EvidenceRecorder
    from framework.onboarding.journey import EVIDENCE_REL
    trial_id = _pack_trial_id(pack_id)
    recorder = EvidenceRecorder(_root(root) / EVIDENCE_REL)
    actor, component, attest = _evidence_identity()

    def _remint(purged: str) -> str:
        # Deterministic per-pack trial naming has no producer state to CAS a
        # fresh trial onto: a purged live trial refuses (fail-closed arm) or
        # degrades loud (receipt/brake arm) — never a silent fork.
        raise GateApplyEvidenceError(
            "evidence_trial_purged",
            f"evidence trial {purged} was tombstoned mid-action")

    lifecycle = ActLifecycle(
        recorder,
        trial_id=trial_id,
        surface=_EVIDENCE_SURFACE,
        actor_policy=lambda phase: dict(actor),
        component=component,
        producer_error=GateApplyEvidenceError,
        unavailable_error=lambda: GateApplyEvidenceError(
            "evidence_unavailable", "the evidence plane cannot record"),
        integrity_error=lambda: GateApplyEvidenceError(
            "evidence_integrity", "the evidence chain needs review"),
        remint=_remint,
        producer_purged_code="gate-producer-never-purged",
        degrade_on_failure=degrade,
    )
    return lifecycle, attest


def _pack_links(pack_id: str) -> list[str]:
    from framework.evidence.lifecycle import valid_id_or_none
    return [ref for ref in (f"gate-pack:{pack_id}", f"gate-watch:{pack_id}")
            if valid_id_or_none(ref)]


def _context_ids(context: dict[str, Any] | None) -> dict[str, Any]:
    """Validated trace/action/correlation ids from a cross-process handoff
    (the ``evidence_before_apply`` return) — invalid/missing ids mint fresh."""
    from framework.evidence.lifecycle import valid_id_or_none
    context = context if isinstance(context, dict) else {}
    return {
        "trace_id": valid_id_or_none(context.get("trace_id")),
        "action_id": valid_id_or_none(context.get("action_id")),
        "correlation_id": valid_id_or_none(context.get("correlation_id")),
    }


def evidence_before_apply(
    pack_id: str,
    *,
    sha256: str | None = None,
    root: str | Path | None = None,
) -> dict[str, str]:
    """ACT-CLASS FAIL-CLOSED pre-flight for the gate-apply lane.

    Call BEFORE ``git apply`` touches the live tree: appends
    ``intent/started`` + ``policy/proposed`` to the pack's evidence trial.
    ANY evidence failure raises :class:`GateApplyEvidenceError` and the
    caller MUST refuse (exit non-zero) before any mutation — the
    evidence-before-action law.  Root daemons must drop to the invoking
    user for this call (``sudo -u "$SUDO_USER"``): a root-minted store file
    poisons every later user-context append, so euid 0 refuses by
    construction (``evidence_root_refused``).

    Returns ``{trial_id, trace_id, action_id, correlation_id}`` for the
    post-apply completion (:func:`record_apply` ``evidence_context=``).
    """
    try:
        lifecycle, attest = _evidence_lifecycle(str(pack_id), root,
                                                degrade=False)
        lifecycle.recover_interrupted()
        context = lifecycle.begin()
        lifecycle.intent(detail={
            "action": "gate_apply",
            "pack_id": str(pack_id),
            "sha256": sha256,
            **attest,
        })
        lifecycle.record(
            phase="policy", status="proposed",
            detail={
                "action": "gate_apply",
                "pack_id": str(pack_id),
                "reason_code": "pack_verdict_pass_hash_matched",
                **attest,
            },
            links=_pack_links(str(pack_id)),
        )
        return {
            "trial_id": lifecycle.trial_id,
            "trace_id": context.trace_id,
            "action_id": context.action_id,
            "correlation_id": context.correlation_id,
        }
    except GateApplyEvidenceError:
        raise
    except Exception as exc:  # noqa: BLE001 — fail closed, typed
        raise GateApplyEvidenceError(
            "evidence_unavailable",
            f"the evidence plane cannot record: {type(exc).__name__}: {exc}",
        ) from exc


def _record_watch_open_evidence(
    row: dict[str, Any],
    root: str | Path | None,
    context: dict[str, Any] | None,
) -> None:
    """RECEIPT: the apply committed and its 72h watch opened (degrade LOUD,
    never raises — the watch row is the domain write and already landed)."""
    try:
        pack_id = str(row.get("pack_id"))
        lifecycle, attest = _evidence_lifecycle(pack_id, root, degrade=True)
        lifecycle.recover_interrupted()
        lifecycle.begin(**_context_ids(context))
        base = {"action": "gate_apply", "pack_id": pack_id, **attest}
        lifecycle.record(
            phase="execution", status="succeeded",
            detail={**base, "sha256": row.get("sha256")})
        lifecycle.record(
            phase="receipt", status="succeeded",
            detail={
                "action": "gate_apply_watch_open",
                "pack_id": pack_id,
                "applied_at": row.get("applied_at"),
                "watch_until": row.get("watch_until"),
                "applied_by": row.get("applied_by"),
                **attest,
            },
            links=_pack_links(pack_id),
        )
        lifecycle.record(phase="outcome", status="succeeded", detail=base)
    except Exception as exc:  # noqa: BLE001 — degrade LOUD, never block
        _warn(f"watch-open evidence not recorded "
              f"({type(exc).__name__}: {exc})")


def _record_rollback_intent(
    pack_id: str,
    reason: str,
    revert_plan: Any,
    root: str | Path | None,
) -> None:
    """ACT-CLASS with the BRAKE EXCEPTION: record the rollback intent before
    the decision releases, but NEVER block it — a broken evidence plane must
    never make a bad germline apply un-revertable (degrade LOUD instead)."""
    try:
        lifecycle, attest = _evidence_lifecycle(pack_id, root, degrade=True)
        lifecycle.recover_interrupted()
        lifecycle.begin()
        lifecycle.intent(detail={
            "action": "gate_revert",
            "pack_id": pack_id,
            "reason": reason,
            "revert_plan": str(revert_plan or ""),
            **attest,
        })
        lifecycle.record(
            phase="policy", status="proposed",
            detail={
                "action": "gate_revert",
                "pack_id": pack_id,
                "reason_code": "red_signal_in_watch_window",
                **attest,
            },
            links=_pack_links(pack_id),
        )
    except Exception as exc:  # noqa: BLE001 — the brake stays unblockable
        _warn(f"rollback-intent evidence not recorded; rollback decision "
              f"releases anyway ({type(exc).__name__}: {exc})")


def _record_watch_close_evidence(pack_id: str,
                                 root: str | Path | None) -> None:
    """RECEIPT: the 72h window elapsed clean — the apply is verified held
    (degrade LOUD, never raises)."""
    try:
        lifecycle, attest = _evidence_lifecycle(pack_id, root, degrade=True)
        lifecycle.recover_interrupted()
        lifecycle.begin()
        lifecycle.record(
            phase="verification", status="verified",
            detail={
                "action": "gate_apply_watch_close",
                "pack_id": pack_id,
                "reason": f"{WATCH_WINDOW_H}h clean",
                **attest,
            },
            links=_pack_links(pack_id),
        )
    except Exception as exc:  # noqa: BLE001 — degrade LOUD, never block
        _warn(f"watch-close evidence not recorded "
              f"({type(exc).__name__}: {exc})")


def evidence_revert_outcome(
    pack_id: str,
    *,
    ok: bool,
    reason: str | None = None,
    root: str | Path | None = None,
) -> None:
    """RECEIPT for the daemon's post-revert wiring: the revert executed
    (``outcome/undone``) or failed (``outcome/failed``).  Degrade LOUD,
    never raises — the revert already happened; recording must not block
    Captain-attention paths."""
    try:
        lifecycle, attest = _evidence_lifecycle(str(pack_id), root,
                                                degrade=True)
        lifecycle.recover_interrupted()
        lifecycle.begin()
        detail: dict[str, Any] = {"action": "gate_revert",
                                  "pack_id": str(pack_id), **attest}
        if reason:
            detail["reason"] = reason
        lifecycle.record(
            phase="execution", status="succeeded" if ok else "failed",
            detail=detail, links=_pack_links(str(pack_id)))
        lifecycle.record(
            phase="outcome", status="undone" if ok else "failed",
            detail=detail)
    except Exception as exc:  # noqa: BLE001 — degrade LOUD, never block
        _warn(f"revert-outcome evidence not recorded "
              f"({type(exc).__name__}: {exc})")


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def record_apply(
    pack_id: str,
    *,
    applied_at: str | None = None,
    revert_plan: str,
    sha256: str | None = None,
    applied_by: str = "gate-apply",
    root: str | Path | None = None,
    evidence_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Open a 72h watch on an applied pack. `revert_plan` is the EXACT revert
    the daemon would execute (recorded at apply time from the LOCKED live
    tree, e.g. `git -c core.hooksPath=/dev/null apply -R <variant.patch>`).

    ``evidence_context`` is the :func:`evidence_before_apply` handoff (the
    daemon threads it across processes) so the completion receipt carries
    the SAME trace/action ids as the recorded intent; absent or invalid ids
    mint fresh ones.  The receipt degrades LOUD and never blocks the watch
    row — the row bytes themselves are unchanged (evidence cites, never
    enriches)."""
    row = {
        "pack_id": str(pack_id),
        "status": "watching",
        "applied_at": _now(applied_at),
        "watch_until": (
            (_parse_ts(_now(applied_at)) or datetime.now(timezone.utc))
            + timedelta(hours=WATCH_WINDOW_H)
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "revert_plan": str(revert_plan),
        "sha256": sha256,
        "applied_by": applied_by,
    }
    _append(watch_path(root), row)
    _record_watch_open_evidence(row, root, evidence_context)
    return row


def mark(
    pack_id: str,
    status: str,
    *,
    reason: str | None = None,
    root: str | Path | None = None,
    now: str | None = None,
) -> dict[str, Any] | None:
    """Transition a watch row (the daemon stamps `rollback`/`closed` after it
    acts). Unknown pack_id / bad status ⇒ None, never raises."""
    try:
        if status not in _STATUSES:
            return None
        prev = _merged(watch_path(root)).get(str(pack_id))
        if prev is None:
            return None
        row = dict(prev, status=status, marked_at=_now(now))
        if reason is not None:
            row["reason"] = reason
        _append(watch_path(root), row)
        return row
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Red-signal probes (defaults read the SOV-5 brakes; all injectable)
# ---------------------------------------------------------------------------

def _default_red_signals(applied_at: str, now: str) -> list[str]:
    """Red signals since `applied_at`: new freeze mirror rows or red canary
    receipts. Fail-SAFE toward rollback is wrong here — a broken probe must
    not roll back a healthy apply — so probe errors read as no-signal; the
    daemon layers its own hard probes on top."""
    reds: list[str] = []
    try:
        from framework.frontdoor import action_undo
        for kind, _ in _frozen_since(action_undo, applied_at, now):
            reds.append(f"kind frozen after apply: {kind}")
        for r in action_undo.canary_receipts():
            ts = str(r.get("ts") or "")
            if not r.get("green") and applied_at <= ts <= now:
                reds.append(f"red canary receipt {r.get('kind')}@{ts}")
    except Exception:
        pass
    return reds


def _frozen_since(action_undo: Any, applied_at: str, now: str):
    """(kind, ts) for freeze mirror rows in (applied_at, now] — last-op-wins
    per kind (an unfrozen kind is not a red signal)."""
    try:
        path = action_undo._frozen_mirror()  # noqa: SLF001 — read-only mirror peek
        if not path.exists():
            return
        last: dict[str, dict[str, Any]] = {}
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("kind"):
                last[str(row["kind"])] = row
        for kind, row in last.items():
            ts = str(row.get("ts") or "")
            if row.get("op") != "unfreeze" and applied_at <= ts <= now:
                yield kind, ts
    except Exception:
        return


# ---------------------------------------------------------------------------
# evaluate — decisions only; the (dark) root daemon executes
# ---------------------------------------------------------------------------

def evaluate(
    *,
    now: str | None = None,
    root: str | Path | None = None,
    red_signals_fn: Optional[Callable[[str, str], list[str]]] = None,
) -> list[dict[str, Any]]:
    """One watch pass over every `watching` row. Returns decision rows:

      {pack_id, decision: rollback|close|watch, reason, revert_plan}

    * red signal inside the 72h window ⇒ `rollback` (+ the recorded plan);
    * window elapsed with no red ⇒ `close` (apply survived) — the red scan is
      capped at `watch_until`, so a red signal arriving AFTER the window
      (e.g. daemon downtime past window end) can never roll back a
      window-survived pack;
    * otherwise ⇒ `watch` (still inside the window, clean so far).

    Marks `rollback`/`closed` transitions in the ledger so re-runs are
    idempotent, but EXECUTES NOTHING — the dark daemon owns execution.
    Never raises.
    """
    ts = _now(now)
    reds_of = red_signals_fn or _default_red_signals
    decisions: list[dict[str, Any]] = []
    try:
        for pack_id, row in sorted(_merged(watch_path(root)).items()):
            if row.get("status") != "watching":
                continue
            applied_at = str(row.get("applied_at") or "")
            watch_until = str(row.get("watch_until") or "")
            # Cap the red scan at the window end: signals after watch_until
            # belong to the post-window world, not this watch.
            scan_end = watch_until if watch_until and watch_until < ts else ts
            try:
                reds = list(reds_of(applied_at, scan_end))
            except Exception:
                reds = []
            if reds:
                reason = "; ".join(reds)[:500]
                # ACT-class with the brake exception: intent recorded BEFORE
                # the transition/decision release; a broken evidence plane
                # degrades LOUD and never blocks the rollback (§2.6/B10).
                _record_rollback_intent(pack_id, reason,
                                        row.get("revert_plan"), root)
                mark(pack_id, "rollback", reason=reason, root=root, now=ts)
                decisions.append({"pack_id": pack_id, "decision": "rollback",
                                  "reason": reason,
                                  "revert_plan": row.get("revert_plan")})
            elif watch_until and ts >= watch_until:
                mark(pack_id, "closed",
                     reason=f"{WATCH_WINDOW_H}h clean", root=root, now=ts)
                # RECEIPT: window elapsed clean (degrade LOUD, never block).
                _record_watch_close_evidence(pack_id, root)
                decisions.append({"pack_id": pack_id, "decision": "close",
                                  "reason": f"{WATCH_WINDOW_H}h clean",
                                  "revert_plan": None})
            else:
                # Still inside the window: trigger exhaust — NEVER recorded.
                decisions.append({"pack_id": pack_id, "decision": "watch",
                                  "reason": "inside window, no red signal",
                                  "revert_plan": None})
    except Exception:
        return decisions
    return decisions


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI
    import argparse
    try:
        # Daemon-writer identity, fixed at process start from constants —
        # never payload-derived, never env-derived (A6/A10).  Best-effort:
        # a host that already attested keeps its own identity.
        from framework.evidence import identity as _identity
        _identity.attest_process_identity(
            "system", "gate-apply-watch", "gate-apply-watch")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="Gate apply-watch — 72h rollback DECISIONS (executes nothing).")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    decisions = evaluate()
    if args.json:
        print(json.dumps(decisions, indent=2, default=str))
    else:
        for d in decisions:
            print(f"{d['pack_id']}: {d['decision']} — {d['reason']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
