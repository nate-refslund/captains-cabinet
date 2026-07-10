# Contributing

## Pre-release status — external PRs not yet accepted

Captain's Cabinet is **pre-release and private**. Until the public cut ships,
we are **not accepting external pull requests** — there is no public repo to
fork yet, and pre-publication history may still be rewritten by the export
pipeline. This document exists so the workflow is ready (and honest) on day
one; everything below is the discipline the repo already enforces on itself.

If you're reading this after publication: welcome — file an issue first for
anything non-trivial so the design conversation happens before the diff.

## Dev setup

```bash
git clone <your-fork-url> captains-cabinet && cd captains-cabinet

# Preflight only — checks prerequisites, changes nothing:
bash cabinet/scripts/setup-mac.sh --check

# See the full hatch plan without executing any of it:
bash cabinet/scripts/hatch.sh --dry-run

# Activate the in-tree git hooks (one-time, idempotent):
bash cabinet/scripts/install-git-hooks.sh
```

`hatch.sh --dry-run` prints the numbered plan plus the human-only errand
notes; nothing runs, nothing touches launchd. The full flag table lives in
[`docs/runbooks/hatch-v0-2026-07-09.md`](./docs/runbooks/hatch-v0-2026-07-09.md).

## Test suites

Run what you touched; CI runs all of it. From the repo root:

```bash
# Framework suite (~4069 tests at the time of writing):
python3 -m pytest framework/ -q

# Scripts suite:
python3 -m pytest cabinet/scripts/tests -q

# Dashboard (vitest; ~1484 tests):
cd cabinet/dashboard && npm ci && npm test

# Hook regression harnesses:
bash cabinet/scripts/run-hook-regression.sh

# Golden evals (behavioral judges):
bash cabinet/scripts/run-golden-evals.sh
```

Shell changes must pass `bash -n` and `shellcheck --severity=error` (CI
enforces this for hooks, lib, and the scripts root). Match the surrounding
style: `set -euo pipefail` in bash, `python3` for Python.

## Commit conventions

As visible in `git log`:

- **Scoped prefix:** `area(TAG): summary` — e.g. `hatch(PC-A): …`,
  `dashboard(PC-B): …`, `ledger(…): …`, `ci: …`. The area names the surface,
  the optional TAG names the program/wave.
- **Body:** what changed and why, including evidence (suite results, gate
  outcomes) for anything non-trivial.
- **Trailer:** agent-authored commits carry a `Co-Authored-By:` trailer
  identifying the model.

## Gates you will hit

These are in-tree git hooks (activated by `install-git-hooks.sh`) plus CI —
fix root causes, never bypass a red gate:

- **FW-019 — checkpoint review (pre-commit).** Commits over **300 changed
  lines** require a fresh review artifact at
  `shared/interfaces/reviews/<branch>-<sha>.md` — a real second-context review
  of the diff, not a rubber stamp. `COMMIT_NO_REVIEW=1` exists strictly for
  docs-only / trivial commits.
- **FW-007 — force-push refusal (pre-push).** No force-push to `master`;
  history rewrites need an announced, logged exception.
- **FW-025 — golden evals on push (pre-push).** The behavioral eval suite runs
  over the working tree before a push lands.

## Docs must track the code

Repo law (see `CLAUDE.md` → "Docs Must Track the Code"): if you rename, move,
add, or delete a script, config, skill, command, MCP server, or feature,
**update every doc that names it in the same change** — runbooks, READMEs,
count claims in `.claude-plugin/*.json`, and skill bodies. Grep the old name
before you call it done. Stale docs are treated as defects, exactly like
broken tests.

## Germline etiquette

Some enforcement/judgment paths (the policy engine, authority matrix, golden
evals, enforcement hooks, and this list's keeper) are **germline**: locked
system-immutable via `cabinet/scripts/germline-lock.sh` so no autonomous
session can edit its own judge. Never edit or work around a germline path.
The route is: write a proposal under `docs/proposals/` (see the existing
`germline-*` amendment docs for the shape) and let the Captain apply it in a
sudo unlock window. Check what is locked with:

```bash
bash cabinet/scripts/germline-lock.sh status
```

A recorded handback always beats a workaround.
