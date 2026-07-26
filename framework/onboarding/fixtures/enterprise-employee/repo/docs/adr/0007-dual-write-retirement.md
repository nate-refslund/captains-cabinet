# ADR-0007: retire the dual-write path

Status: accepted

## Decision

We removed the `ledger_dual_write` flag and the dual-write code path. The
settlement ledger is now written once, by the v2 router.

## Consequences

Any runbook, alert or dashboard that still refers to `ledger_dual_write` is
stale and will mislead whoever reads it during an incident.
