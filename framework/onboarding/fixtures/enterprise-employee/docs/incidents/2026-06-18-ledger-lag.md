# Incident 2026-06-18 — settlement reconcile fell four hours behind

Severity 2. Delayed settlement reporting, no data loss.

## What happened

A retried batch caused the reconcile job to skip rows. Nobody noticed for
three hours, because the job has no lag alerting.

## What we did

The on-call engineer followed the runbook and tried to set
`ledger_dual_write=false`. That flag no longer exists, so the step did
nothing and cost about twenty minutes.

## Action items

- Add lag alerting for the reconcile job. Owner: @eng-kestrel.
- Write down the manual replay procedure. Owner: @eng-kestrel.
- BLOCKED: the alerting work needs a metrics pipeline change that the
  observability team has not scheduled.
