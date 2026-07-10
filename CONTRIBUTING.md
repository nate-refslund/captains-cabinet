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

## Sign-off (DCO) — required on every contribution

Every commit needs a `Signed-off-by:` trailer — use `git commit -s`. The
sign-off certifies the [Developer Certificate of Origin 1.1](./docs/DCO.txt):
a one-line statement that you have the right to contribute the change under
this repo's [MIT license](./LICENSE).

Why the DCO and not a CLA: it is the lightest honest mechanism available.
There is no paperwork, no copyright assignment, and no separate agreement to
sign — you keep your copyright, the certificate rides in the commit itself,
and provenance stays auditable in `git log` forever. Forgot the trailer?
`git commit --amend -s` fixes the tip; `git rebase --signoff` fixes a branch.

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

## Contribution flow

*(Describes the flow as it works from day one of the public cut; while the
repo is pre-release it binds the repo's own agents.)*

1. **Issue first, diff second.** For anything non-trivial, open an issue
   before writing code — bug / feature / hatch-report templates live in
   `.github/ISSUE_TEMPLATE/`. The design conversation happens on the issue.
2. **Diagnostics without leaks.** `bash cabinet/scripts/cabinet-feedback.sh
   --dry-run` gathers doctor output + the latest hatch flight-log tail +
   versions, scrubs every line through the leak-scrub suite, and prints the
   redacted bundle for your review. Run it without `--dry-run` and it can
   open the issue prefilled — only after an explicit interactive y/N
   consent; it never posts anything on its own.
3. **PRs.** Fork → branch → run the suites you touched → the PR template
   checklist: tests, docs-track-code, no germline edits, and DCO sign-off
   (see "Sign-off (DCO)" above).
4. **Labels.** `good first issue` = self-contained, shape already scoped by
   a maintainer, no doctrine context needed. `help wanted` = wanted and
   review-ready, but needs more context than a first issue. Both are
   maintainer-curated — ask on the issue before starting if unclear.
5. **Hatch reports are contributions.** A hatch report with a TTFR number
   tunes the onboarding path exactly like code does — file one even when
   nothing broke (`hatch-report` template).

**Discussions (planned):** GitHub Discussions is enabled at publication with
three categories — Q&A (setup + doctrine questions), Show and tell (hatch
reports, packs, worlds), and Ideas (pre-issue design talk). Until then,
issues carry everything; the issue-chooser config gains contact links in the
same change that enables Discussions.

**Funding:** donations run through Open Collective (`.github/FUNDING.yml` —
placeholder slug until the collective exists). How token costs are metered
and mirrored to the public ledger: `docs/TRANSPARENCY.md`.

<!-- PUBLISH-FLIP (staged, NOT live — contribution design 2026-07-10): when
     the public cut ships, replace the "Pre-release status" section at the
     top of this file with the block below, in the same change that flips
     the repo public.

## Status — contributions welcome

Captain's Cabinet is public. Issues, PRs, and hatch reports are all
welcome — start with "Contribution flow" below. For anything non-trivial,
file an issue first so the design conversation happens before the diff.

-->
