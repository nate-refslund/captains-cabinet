"""Shared act-class evidence recording lifecycle.

Extracted verbatim-in-behavior from the onboarding journey's ``act()`` (the
recorder's first production producer) so every future act-class producer
records the SAME lifecycle the same way:

    intent -> policy(proposed) -> [core action commits] -> policy(allowed) ->
    execution -> verification -> receipt -> outcome
    refusal branch:          policy(refused) -> outcome(refused)
    unexpected-error branch: error(failed)   -> outcome(failed)

plus the act-class laws this package enforces for producers:

- **Evidence before action, fail closed.** ``intent`` and ``policy/proposed``
  are appended BEFORE the producer's core runs; when they cannot be preserved
  the action never runs.  ``policy/allowed`` is deliberately recorded after
  the core has already committed — the fail-closed guarantee covers intent
  and proposal, and callers must not "fix" that ordering.
- **Id unification.** Caller-supplied trace/action/correlation ids are
  accepted only when they match the recorder id alphabet
  (:func:`valid_id_or_none`); the validated context ids are stamped back onto
  the producer's canonical request (:meth:`ActLifecycle.unify_ids`) so the
  producer plane and the evidence plane can never fork.
- **Re-mint lineage.** A live producer whose trial was tombstoned (retention
  or a Captain CLI purge) re-mints ONCE onto a fresh trial whose genesis
  event links the tombstone hash (:func:`remint_trial`); purge finality
  always wins — a purged producer is never re-minted.
- **Purge degradation.** Only for the producer's own destructive purge
  action, a broken evidence plane degrades (the failure is surfaced through
  :attr:`ActLifecycle.degraded_evidence` for the producer's receipt) instead
  of raising: a broken evidence plane must never make producer data
  undeletable.
- **One duration per terminal branch.** ``duration_ms`` is computed once per
  branch and the same rounded value rides every event in that branch's tail.

This module is an IMPORT SEAM for sanctioned producer code admitted to the
trusted core by ceremony.  It is deliberately NOT a generic emit surface:
there is no CLI, no ``__main__`` wiring, and no environment-derived store —
callers must pass an :class:`EvidenceRecorder` they constructed with an
explicit store root, and every payload still flows through
``EvidenceRecorder.append`` (sanitization, redaction, hash chain, signatures)
unchanged.  Producers supply their own actor mapping, component identity, and
error vocabulary; the recorder-owned fields (sequence, hashes, signatures,
timestamps, trust) remain impossible to supply from here.
"""
from __future__ import annotations

import hashlib
import time
from contextlib import AbstractContextManager
from typing import Any, Callable

from .recorder import ID_RE, EvidenceError, EvidenceRecorder, TraceContext

__all__ = ["ActLifecycle", "append_event", "remint_trial", "valid_id_or_none"]


def valid_id_or_none(value: Any) -> str | None:
    """Return ``value`` when it is a recorder-alphabet id string, else None.

    ONE id shape for both planes: a producer that accepts a caller id its
    evidence trail would refuse (or vice versa) forks the cross-plane
    correlation that makes the audit trail reviewable.  ``None`` means "mint
    a fresh id" to :meth:`EvidenceRecorder.trace`.
    """
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        return None
    return value


def append_event(
    recorder: EvidenceRecorder,
    context: TraceContext,
    *,
    phase: str,
    status: str,
    actor: dict[str, str],
    component: dict[str, str],
    unavailable_error: Callable[[], Exception],
    detail: dict[str, Any] | None = None,
    links: list[str] | None = None,
    duration_ms: float | None = None,
) -> dict[str, Any]:
    """Append one event, translating evidence failures to the producer error.

    The producer error is raised ``from`` the underlying
    :class:`EvidenceError` so callers (including the re-mint retry policy in
    :meth:`ActLifecycle.record`) can still read ``exc.__cause__.code``.
    """
    try:
        return recorder.append(
            context,
            phase=phase,
            status=status,
            actor=actor,
            component=component,
            detail=detail,
            links=links,
            duration_ms=duration_ms,
        )
    except EvidenceError as exc:
        raise unavailable_error() from exc


def remint_trial(
    recorder: EvidenceRecorder,
    purged_trial_id: str,
    *,
    surface: str,
    state_lock: Callable[[], AbstractContextManager[Any]],
    swap_live_trial: Callable[[str], tuple[str, bool]],
    actor_policy: Callable[[str], dict[str, str]],
    component: dict[str, str],
    unavailable_error: Callable[[], Exception],
) -> str:
    """Mint a fresh evidence trial for a live producer whose trial was purged.

    Retention or a Captain CLI purge can legitimately tombstone a producer's
    LIVE trial.  Without a re-mint path every later action — including the
    producer's own purge — would refuse forever, silently ending the
    record-everything mandate.  Purge FINALITY still wins: the producer's
    ``swap_live_trial`` must refuse (raise its own purged error) when the
    producer itself was purged.

    ``swap_live_trial(purged_trial_id)`` is the producer-state adapter: called
    under ``state_lock()``, it must load producer state, enforce purge
    finality, compare-and-swap the live trial id, persist, and return
    ``(live_trial_id, minted_fresh)``.  When a concurrent caller already
    re-minted it returns the adopted id with ``minted_fresh=False`` — the
    lineage never forks — and no second genesis event is written.

    The genesis event is appended ON THE FRESH TRIAL while the producer state
    lock is still held (the one place evidence is written under that lock —
    intentional, it serializes the swap): phase ``system`` / status
    ``recovered`` with the tombstone hash in both ``detail`` and a namespaced
    ``evidence-tombstone:`` link, so the audit trail shows exactly where (and
    why) the trial lineage restarted.
    """
    tombstone_hash = hashlib.sha256(purged_trial_id.encode("utf-8")).hexdigest()
    with state_lock():
        live_trial_id, minted_fresh = swap_live_trial(purged_trial_id)
        if not minted_fresh:
            return live_trial_id
        context = recorder.trace(live_trial_id, surface=surface)
        append_event(
            recorder,
            context,
            phase="system",
            status="recovered",
            actor=actor_policy("system"),
            component=component,
            unavailable_error=unavailable_error,
            detail={
                "action": "remint_evidence_trial",
                "reason_code": "prior_trial_tombstoned",
                "purged_trial_id_hash": tombstone_hash,
            },
            links=[f"evidence-tombstone:{tombstone_hash}"],
        )
    return live_trial_id


class ActLifecycle:
    """Fail-closed evidence recording for ONE act-class action.

    One instance covers one action attempt.  The producer owns its state
    machine, payload construction, and error vocabulary; this class owns the
    event ordering, the fail-closed policy, the re-mint-once retry, and the
    one-duration-per-branch rule.

    Producer contract:

    - ``producer_error`` is the producer's refusal exception TYPE; instances
      must carry a ``code`` attribute (and evidence-translated instances a
      ``__cause__`` with a ``code``), as :func:`append_event` guarantees.
    - ``unavailable_error`` / ``integrity_error`` build the producer's
      evidence-unavailable / evidence-integrity refusals.
    - ``remint`` maps a purged trial id to the live (fresh or adopted) trial
      id — normally a closure over :func:`remint_trial`.  It must raise the
      producer error carrying ``producer_purged_code`` when the producer
      itself was purged (purge finality).
    - ``degrade_on_failure`` is True ONLY for the producer's destructive
      purge action: evidence failures then set :attr:`degraded_evidence`
      (``{"error_code", "phase"}``) and recording goes silent instead of
      raising, so a broken evidence plane never blocks deletion.
    """

    def __init__(
        self,
        recorder: EvidenceRecorder,
        *,
        trial_id: str,
        surface: str,
        actor_policy: Callable[[str], dict[str, str]],
        component: dict[str, str],
        producer_error: type[Exception],
        unavailable_error: Callable[[], Exception],
        integrity_error: Callable[[], Exception],
        remint: Callable[[str], str],
        producer_purged_code: str,
        degrade_on_failure: bool = False,
    ) -> None:
        self.recorder = recorder
        self.trial_id = trial_id
        self.surface = surface
        self.context: TraceContext | None = None
        self.degraded_evidence: dict[str, Any] | None = None
        self.reminted = False
        self._actor_policy = actor_policy
        self._component = component
        self._producer_error = producer_error
        self._unavailable_error = unavailable_error
        self._integrity_error = integrity_error
        self._remint = remint
        self._producer_purged_code = producer_purged_code
        self._degrade_on_failure = degrade_on_failure
        self._started_monotonic_ns: int | None = None

    # ------------------------------------------------------------------
    # Pre-flight: evidence before action.
    # ------------------------------------------------------------------
    def recover_interrupted(self) -> None:
        """Reconcile an interrupted write BEFORE anything else runs.

        A ``trial_purged`` failure re-mints immediately (the live trial was
        tombstoned while the producer stayed live).  Any other evidence
        failure either degrades (purge action only) or refuses the whole
        action with the producer's integrity error — the evidence chain needs
        review before another action can run.
        """
        trial_path = self.recorder.root / "trials" / self.trial_id
        if not trial_path.exists():
            return
        try:
            self.recorder.recover_interrupted(self.trial_id)
        except EvidenceError as exc:
            if exc.code == "trial_purged":
                self.trial_id = self._remint(self.trial_id)
                self.reminted = True
            elif self._degrade_on_failure:
                self.degraded_evidence = {
                    "error_code": exc.code,
                    "phase": "recover_interrupted",
                }
            else:
                raise self._integrity_error() from exc

    def begin(
        self,
        *,
        trace_id: str | None = None,
        action_id: str | None = None,
        correlation_id: str | None = None,
    ) -> TraceContext:
        """Open the trace context on the live trial (after pre-flight)."""
        self.context = self.recorder.trace(
            self.trial_id,
            surface=self.surface,
            trace_id=trace_id,
            action_id=action_id,
            correlation_id=correlation_id,
        )
        return self.context

    def unify_ids(self, request: dict[str, Any]) -> None:
        """Stamp the validated context ids onto the producer's canonical request.

        Overwrite (never setdefault) trace/correlation so a malformed caller
        id cannot fork the two planes the audit correlates.  A caller-supplied
        ``action_id`` is KEPT even when malformed, so the producer core can
        refuse it deterministically (silently re-minting it would break
        idempotent replay) while the refusal evidence carries the minted id.
        """
        if self.context is None:
            raise RuntimeError("ActLifecycle.begin() must run before unify_ids().")
        request["trace_id"] = self.context.trace_id
        request["correlation_id"] = self.context.correlation_id
        if "action_id" not in request:
            request["action_id"] = self.context.action_id

    # ------------------------------------------------------------------
    # Recording policy (re-mint once, degrade only for purge).
    # ------------------------------------------------------------------
    def record(
        self,
        *,
        phase: str,
        status: str,
        detail: dict[str, Any] | None = None,
        links: list[str] | None = None,
        duration_ms: float | None = None,
    ) -> dict[str, Any] | None:
        """Append one evidence event for this action.

        A ``trial_purged`` failure re-mints ONCE (retention/CLI can tombstone
        the live trial between any two appends) and retries on the fresh
        trial with the same trace/action/correlation ids.  When
        ``degrade_on_failure`` is set (the producer's purge action) any
        remaining evidence failure degrades instead of raising: a broken
        evidence plane must never make producer data undeletable.
        """
        if self.degraded_evidence is not None:
            return None
        if self.context is None:
            raise RuntimeError("ActLifecycle.begin() must run before record().")
        try:
            return self._append(
                phase=phase, status=status, detail=detail,
                links=links, duration_ms=duration_ms,
            )
        except self._producer_error as exc:
            cause_code = getattr(exc.__cause__, "code", None)
            if cause_code == "trial_purged" and not self.reminted:
                self.reminted = True
                try:
                    self.trial_id = self._remint(self.trial_id)
                    self.context = self.recorder.trace(
                        self.trial_id,
                        surface=self.surface,
                        trace_id=self.context.trace_id,
                        action_id=self.context.action_id,
                        correlation_id=self.context.correlation_id,
                    )
                    return self._append(
                        phase=phase, status=status, detail=detail,
                        links=links, duration_ms=duration_ms,
                    )
                except self._producer_error as retry_exc:
                    if getattr(retry_exc, "code", None) == self._producer_purged_code:
                        # The producer itself was purged concurrently: purge
                        # finality wins and there is no trial left to record
                        # into — let the core's own purged refusal surface.
                        return None
                    if not self._degrade_on_failure:
                        raise
                    self.degraded_evidence = {
                        "error_code": getattr(retry_exc.__cause__, "code", None)
                        or getattr(retry_exc, "code", None),
                        "phase": phase,
                    }
                    return None
            if not self._degrade_on_failure:
                raise
            self.degraded_evidence = {
                "error_code": cause_code or getattr(exc, "code", None),
                "phase": phase,
            }
            return None

    def _append(
        self,
        *,
        phase: str,
        status: str,
        detail: dict[str, Any] | None,
        links: list[str] | None,
        duration_ms: float | None,
    ) -> dict[str, Any]:
        return append_event(
            self.recorder,
            self.context,
            phase=phase,
            status=status,
            actor=self._actor_policy(phase),
            component=self._component,
            unavailable_error=self._unavailable_error,
            detail=detail,
            links=links,
            duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------
    # The 8-event lifecycle choreography.
    # ------------------------------------------------------------------
    def intent(self, detail: dict[str, Any]) -> None:
        """Record ``intent/started`` and start the one-per-branch clock."""
        self._started_monotonic_ns = time.monotonic_ns()
        self.record(phase="intent", status="started", detail=detail)

    def proposed(self, detail: dict[str, Any]) -> None:
        """Record ``policy/proposed`` — the last event before the core runs."""
        self.record(phase="policy", status="proposed", detail=detail)

    def _elapsed_ms(self) -> float:
        if self._started_monotonic_ns is None:
            raise RuntimeError("ActLifecycle.intent() must run before a terminal branch.")
        return round((time.monotonic_ns() - self._started_monotonic_ns) / 1_000_000, 3)

    def refused(
        self,
        *,
        refusal_detail: dict[str, Any],
        outcome_detail: dict[str, Any],
    ) -> None:
        """Record the refusal tail: ``policy/refused`` then ``outcome/refused``."""
        elapsed = self._elapsed_ms()
        self.record(
            phase="policy", status="refused",
            detail=refusal_detail, duration_ms=elapsed,
        )
        self.record(
            phase="outcome", status="refused",
            detail=outcome_detail, duration_ms=elapsed,
        )

    def failed(
        self,
        *,
        error_detail: dict[str, Any],
        outcome_detail: dict[str, Any],
    ) -> None:
        """Record the unexpected-error tail: ``error/failed`` then ``outcome/failed``."""
        elapsed = self._elapsed_ms()
        self.record(
            phase="error", status="failed",
            detail=error_detail, duration_ms=elapsed,
        )
        self.record(
            phase="outcome", status="failed",
            detail=outcome_detail, duration_ms=elapsed,
        )

    def completed(
        self,
        *,
        result_status: str,
        allowed_detail: dict[str, Any],
        execution_detail: dict[str, Any],
        verification_detail: dict[str, Any],
        receipt_detail: dict[str, Any],
        receipt_links: list[str],
        outcome_detail: dict[str, Any],
    ) -> None:
        """Record the committed tail in canonical order.

        ``policy/allowed`` -> ``execution/<result_status>`` ->
        ``verification/verified`` -> ``receipt/succeeded`` ->
        ``outcome/<result_status>``, all carrying the ONE branch duration.
        ``policy/allowed`` lands after the core already committed by design.
        """
        elapsed = self._elapsed_ms()
        self.record(
            phase="policy", status="allowed",
            detail=allowed_detail, duration_ms=elapsed,
        )
        self.record(
            phase="execution", status=result_status,
            detail=execution_detail, duration_ms=elapsed,
        )
        self.record(
            phase="verification", status="verified",
            detail=verification_detail, duration_ms=elapsed,
        )
        self.record(
            phase="receipt", status="succeeded",
            detail=receipt_detail, links=receipt_links, duration_ms=elapsed,
        )
        self.record(
            phase="outcome", status=result_status,
            detail=outcome_detail, duration_ms=elapsed,
        )
