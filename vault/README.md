# vault — the cabinet's knowledge vault

This directory is the cabinet's **default vault** (Captain-ratified
2026-07-16; formerly `product-brain/`, plan-B B4.14/B4.15): the org's own
durable knowledge about the products it builds, the decisions it makes, and
the way it operates. On a clean-room org box there is no personal captain
vault at all — **this folder is what the action lane perceives** and what the
memory index recalls.

## What belongs here

Knowledge, designs, plans — **any captain/org document** that should compound:

| Path | Holds |
|------|-------|
| `architecture.md` | Per-product architecture: stack, boundaries, key seams (template in this dir) |
| `decisions/` | One note per durable decision — what was decided, why, what it supersedes |
| `incidents/` | One note per incident — symptom, root cause, fix, follow-ups |
| `deploy-notes/` | Deploy-state notes — what shipped, where, rollback handles |
| `customers/` | Customer/partner facts the org must not re-learn |
| `designs/`, `plans/`, … | Any other org knowledge — create folders freely; the walkers recurse |

Officers and the Captain write here via **normal file writes** — no special
API, no ceremony. Sub-folders beyond the table are created on first write.

## Conventions

- **Plain markdown.** No proprietary formats, no databases — a note you can
  read in any editor in ten years.
- **`[[wikilinks]]` welcome.** Link notes to each other with
  `[[note-name]]`-style wikilinks (or ordinary relative markdown links —
  both are fine; wikilinks keep prose readable and graph tools happy).
- **Frontmatter `date:` encouraged.** A `date: YYYY-MM-DD` frontmatter field
  (or a dated filename) gives the memory index an honest content timestamp —
  content time, never file mtime.
- **Obsidian-compatible, never required.** Point the Obsidian app at this
  folder as a vault and you get the graph view, backlinks, and search for
  free. This is purely optional — nothing in the cabinet needs Obsidian, and
  plain files remain the source of truth.
- **git is not GitHub.** This folder is versioned because it lives in the
  repo's **local git tree**: every edit is history you can diff and restore
  **entirely on this machine**. No remote, no GitHub account, and no network
  are ever required for the vault to work. Pushing the repo anywhere is a
  separate, optional choice the Captain makes.

## Where a document lives (the placement one-pager)

| Put it in… | When it is… | Examples |
|---|---|---|
| **`vault/`** (here) | Org/captain **knowledge** — anything the org should recall and build on | product architecture, decisions, incident post-mortems, deploy notes, customer facts, designs, plans of your own |
| **`docs/`** | **Framework** reference that ships with the cabinet itself — how the machinery works | specs, framework plans/proposals, Captain-ceremony runbooks |
| **`memory/skills/`** | An **officer-executable procedure** — steps an officer runs when a trigger matches | deploy-and-verify, world-qa-verify, retro procedures |
| **`instance/`** | **This deployment's** config and captain-personal material — never framework, scrubbed from the public egg | `instance/config/*.yml`, lane contexts, captain-personal notes |
| `shared/interfaces/` captain ledgers | Standing **captain law** — append-only via `cabinet/scripts/append-interface.sh`, never direct writes | decisions/patterns/intents ledgers |

**Runbooks vs skills (policy).** If a procedure is something an **officer
executes** when a trigger condition matches, it belongs in `memory/skills/`
(SKILL.md format — discoverable, improvable by the learning loops, embedded
for recall). If it is a **Captain ceremony** — sudo unlock windows, germline
amendments, one-time bring-up — it stays a runbook under `docs/runbooks/`.
Graduating a runbook = convert it to the skill format preserving content and
leave a pointer stub at the old path (exemplar: `memory/skills/world-qa-verify.md`,
graduated from `docs/runbooks/world-qa-verify.md`).

When in doubt: knowledge → `vault/`, framework reference → `docs/`,
executable procedure → `memory/skills/`, deployment-specific → `instance/`.

## How it is consumed

- **The action lane.** `framework/acting/run_action_lane.py:gather_signals`
  carries `CORPUS` sections in both profiles (operational: newest 4 within
  the recency window; strategic: newest 6, unwindowed). The scan is
  file-only, mtime-fenced to the gather's `as_of` clock, capped and excerpted
  like every vault section. Content here is provenance-fenced
  world-description for the proposer — it is never executed as instructions.
- **Evidence refs are namespaced `vault/<relpath>`.** Ref-namespace decision
  (2026-07-17): refs MIGRATED with the rename rather than keeping the old
  prefix — a gather ref is a per-run evidence handle, not a durable foreign
  key, so fresh gathers should not carry a ghost name forever. Ledger rows
  written before the rename keep their old `product-brain/<relpath>` strings
  as immutable provenance; nothing rewrites history.
- **The memory index.** Vault writes are embedded into `cabinet_memory`
  (source_type `product_brain` — the DB row-taxonomy name predates the
  rename and is kept so existing rows' upsert identity survives) by the
  post-file-write hook, the nightly `memory-reconcile` walk, and
  `backfill-memory.sh`. The hook lives in the schg-locked germline hooks dir:
  its `vault/` pattern lands via
  `patches/germline-vault-hook-watch-2026-07-17.patch` (until that ceremony,
  the nightly reconcile is the coverage netting).

## Where the resolver looks

The directory resolves via `framework.env.org_vault_dir()`:
`CABINET_ORG_VAULT_DIR` env override → legacy `CABINET_PRODUCT_BRAIN_DIR`
alias → the `org_vault_dir:` key in `instance/config/platform.yml` (legacy
`product_brain_dir:` honored after it; relative values resolve against the
repo root, existence-gated) → `<repo>/vault` when it exists → legacy
`<repo>/product-brain` → `""` (fail-closed — no corpus, no sections).
`framework.env.product_brain_dir()` remains as a deprecated working alias.
The name `vault_dir()` was already taken by the **captain's personal** vault
resolver — the two are deliberately distinct seams.
