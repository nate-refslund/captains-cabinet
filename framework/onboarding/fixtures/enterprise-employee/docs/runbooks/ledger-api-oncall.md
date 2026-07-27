# ledger-api on-call runbook

Last reviewed 2026-03-11.

## Paging

Page @payments-platform for anything that touches settlement. If nobody
answers within fifteen minutes, escalate to the platform duty manager.

## The reconcile job is behind

1. Check the reconcile lag dashboard.
2. If lag is above thirty minutes, set `ledger_dual_write=false` in the
   feature config and redeploy. That stops the second write and lets the job
   catch up.
3. If that does not help, replay the affected batches by hand.

## Access

You need a read-only login for the settlement database. Ask the owning team.
