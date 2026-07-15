"""Universal, local-first Cabinet Evidence Recorder.

The organizational event ledger remains the source of truth for org state.
This package is the tamper-evident join plane that explains how an intent
became a policy decision, execution, verification, receipt, error, undo, and
outcome across product surfaces.
"""

from .policy import RepairRequest, repair_verdict
from .recorder import (
    EvidenceError,
    EvidenceRecorder,
    TraceContext,
    new_action_id,
    new_correlation_id,
    new_trace_id,
    new_trial_id,
)
from .verifier import verify_store, verify_trial

__all__ = [
    "EvidenceError",
    "EvidenceRecorder",
    "RepairRequest",
    "TraceContext",
    "new_action_id",
    "new_correlation_id",
    "new_trace_id",
    "new_trial_id",
    "repair_verdict",
    "verify_store",
    "verify_trial",
]
