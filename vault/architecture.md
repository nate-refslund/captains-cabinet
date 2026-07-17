---
date: 2026-07-07
status: template
---

# Architecture — <product>

> TEMPLATE — copy this shape per product (or grow this file for a
> single-product deployment). Replace every `<placeholder>`; keep the
> frontmatter `date:` current on substantive edits.

## Stack

- Runtime / framework: <e.g. Next.js on Vercel>
- Data: <e.g. Neon Postgres — project id, schemas>
- Integrations: <e.g. payment provider, email sub-processor>

## Boundaries

- <the system's hard edges: what it owns, what it never touches>

## Key seams

- <the 3–5 seams a new officer must know before changing anything:
  deploy path, auth boundary, migration discipline, outbound gates>

## Known constraints

- <compliance, rate limits, contractual — the "why it is built this way" facts>
