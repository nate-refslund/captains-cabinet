# Transparency — where the money goes

Captain's Cabinet runs on LLM tokens. If people fund this project, they are
mostly buying tokens, and the project's own receipts doctrine extends to
money: **every claim below is backed by an in-repo mechanism you can read and
run — and where a number is not attributed, the system says so instead of
inventing one.**

## How token costs are metered (today, in-tree)

1. **Per-action cost receipts.** Every externally visible action journals
   what/why/undo, and the journal row may carry an additive `cost` dict
   stamped at write time (input/output tokens + estimate). Receipts render a
   cost line from it; an action without attribution honestly renders
   `cost: unattributed` — never a made-up number
   (`framework/frontdoor/action_language.py`).
2. **Daily counters.** Per-officer input/output token counts accumulate in
   the Redis hash `cabinet:cost:tokens:daily:<date>` (stamped by the
   stop-hook as sessions run). `bash cabinet/scripts/cost-report.sh --daily`
   prints the day's totals; `cost-dashboard.sh` formats the daily summary,
   and `cost-delta.sh` tracks movement.

So "what did this org cost today?" has a mechanical answer on every
deployment, including yours.

## Donations: Open Collective

Donations flow through Open Collective (`.github/FUNDING.yml`): anyone can
donate, every donation is publicly attributed, and **every expense is on a
public ledger** — the fiscal host holds the funds, not a private account.
Host and payment-processing fees apply per the host's published fee
schedule (see the Open Source Collective docs for current numbers — this doc
deliberately does not restate figures it cannot keep fresh).

**Status: the collective does not exist yet.** The slug in `FUNDING.yml` is
a placeholder until the Captain completes the collective + fiscal-host
application; this document ships first so the loop is designed in the open.

## The monthly loop — manual at first, honestly so

Once the collective is live, each month the Captain:

1. pulls the month's token totals from the daily counters
   (`cost-report.sh`), and
2. mirrors them to the collective as an expense/update, so the public
   ledger tracks what the org actually burned.

This starts as a **manual, human-does-it-monthly ritual** — no automation
theater. The automated version (a monthly expense draft generated from cost
telemetry, filed as a propose-only draft for per-item approval) is deferred
follow-on work; when it lands, this document changes in the same commit.

## What funding does not buy

Donations pay the token bill and infrastructure. They do not buy roadmap
control, priority handling, or any say over the Captain's rulings. The
gratitude is real; the governance is unchanged.
