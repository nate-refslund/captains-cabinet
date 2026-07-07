# product-brain — the org's own knowledge corpus

This directory is the **product-brain markdown corpus** (plan-B B4.14/B4.15):
the org's OWN durable knowledge about the products it builds and operates. It
is the flavor-B twin of the captain's personal vault — on clean-room org boxes
there is no vault at all, and this corpus is what the action lane perceives.

## What belongs here

| Path | Holds |
|------|-------|
| `architecture.md` | Per-product architecture: stack, boundaries, key seams (template below) |
| `decisions/` | One note per durable decision — what was decided, why, what it supersedes |
| `incidents/` | One note per incident — symptom, root cause, fix, follow-ups |
| `deploy-notes/` | Deploy-state notes — what shipped, where, rollback handles |
| `customers/` | Customer/partner facts the org must not re-learn |

Officers write here via **normal file writes** — no special API, no ceremony.
Frontmatter with a `date:` field is encouraged (future `content_ts` fencing);
plain markdown is fine. Post-file-write hooks may later embed this corpus into
the semantic index automatically — writing the file stays the only step an
officer performs.

## How it is consumed

`framework/acting/run_action_lane.py:gather_signals` carries `CORPUS` sections
in both profiles (operational: newest 4 within the recency window; strategic:
newest 6, unwindowed). The scan is file-only, mtime-fenced to the gather's
`as_of` clock, capped and excerpted like every vault section, and refs are
namespaced `product-brain/<relpath>`. Content here is provenance-fenced
world-description for the proposer — it is never executed as instructions.

The directory resolves via `framework.env.product_brain_dir()`: the
`CABINET_PRODUCT_BRAIN_DIR` env override wins, else `<repo>/product-brain`
when it exists, else `""` (fail-closed — no corpus, no sections).
