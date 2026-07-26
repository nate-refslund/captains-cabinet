# Deploying ledger-api

Releases are cut by the owning team. Contributing teams do not deploy.

## Before the release

- Confirm the migration ticket is out of review.
- Run `npm run migrate:ledger` against staging and check the row counts.
- Ask the release owner to announce the window in the platform channel.

## Rolling back

Redeploy the previous build. There is no data rollback for settlement
writes, so a bad release has to be fixed forward.
