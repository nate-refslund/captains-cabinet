# Germline addendum — Library retirement danglers (ceremony-only) — 2026-07-16

**Date:** 2026-07-16 (durable-surface + lock-state rev 2026-07-17, same
lane) · **Author:** library-retire lane (scratch clone off the GitHub
master tip; fix pass off `1cd84459`) · **Ledger row:** CG-29 (filed;
ROUTING REVISED 2026-07-17 to MASTER-FIRST — the git-side content lands on
master, the schg live inode syncs in the window via checkout-from-master,
per the CG-27 / CG-31 precedent; see "Ceremony items" below) ·
**Targets (three germline surfaces):** `cabinet/mcp-scope.yml`,
`.claude/settings.json`, `cabinet/scripts/start-officer-mac.sh` (all three
in `cabinet/scripts/germline-lock.sh`'s list; schg-locked on the live box) ·
**Patch artifact:**
`docs/proposals/germline-library-retirement-2026-07-16.patch` — a plain
FILE directly under `docs/proposals/` BY CONTRACT: the egg exporter's
`t_proposals_archive` `rm -f`'s each entry under `set -e`, so a
subdirectory here aborts the export (both package files carry
`expect-absent` manifest rows and archive out of the egg like every other
non-amendment proposal); it is kept as the comment-only PROOF (superseded
as an apply step by the master checkout) · **Provenance:** no schg live
inode is touched by the git-side land — the tree files (`mcp-scope.yml` /
`settings.json` / `start-officer-mac.sh`) are NOT schg in a clone, and
`cabinet/scripts/tests/test_library_retirement_ratchet.py::test_staged_ceremony_patch_stays_appliable_and_comment_only`
re-verifies the reference patch's comment-only-ness on every CI run (until
the mark lands, then it skips) without touching the locks.

## Why

The Library retirement (Captain-ratified 2026-07-16;
`docs/runbooks/library-retirement-2026-07-16.md`) deregistered the
`library` MCP server from both `.mcp.json` layers and removed every
non-germline `mcp__library` grant. Three germline surfaces still carry
dangling `library` references — harmless while the server is unregistered
(an unregistered server grants nothing; a comment misleads but executes
nothing), but they are resurrection bait and stale doctrine. The git-side
cleanup lands on master with the danglers diff; the schg LIVE inodes are
brought into line inside a Captain sudo unlock window.

## What lands on master (git side, no lock touched)

The danglers diff removes the three dangling references from the TRACKED
files — none of which is schg in a clone:

1. **`cabinet/mcp-scope.yml`** — `library` dropped from every officer /
   scaffold grant list and from `universal:`. Hygiene, not behavior.
2. **`.claude/settings.json`** — the `"mcp__library"` entry dropped from
   `permissions.allow`. Hygiene, not behavior.
3. **`cabinet/scripts/start-officer-mac.sh`** — the stale MCP deep-merge
   comment ("notion/linear/neon/library" named the deregistered `library`
   and the long-deleted `linear`) replaced by living-server text carrying
   the deregistration date. Comment-only — the ratchet enforces non-comment
   lines byte-identical and `bash -n` clean.

Landing is functionally inert: LIB-RETIRE-1 already deregistered the server
from both `.mcp.json` layers, so the grants/comment were no-ops. Post-land,
the two grant surfaces are ratcheted clean by
`test_germline_grant_surfaces_stay_library_free` (they are no longer
carried-until-ceremony).

## Ceremony — live-inode sync (one Captain sudo window, relock same day)

The window does NOT patch or commit; it syncs the schg live inodes to the
already-landed master content (the CG-27 / CG-31 checkout-from-master
precedent):

```bash
# Captain sudo window, from the repo root, relock the SAME session:
git fetch origin
sudo cabinet/scripts/germline-lock.sh unlock
git checkout origin/master -- cabinet/mcp-scope.yml \
    .claude/settings.json cabinet/scripts/start-officer-mac.sh
git diff --quiet origin/master -- cabinet/mcp-scope.yml \
    .claude/settings.json cabinet/scripts/start-officer-mac.sh   # blob-verify
sudo cabinet/scripts/germline-lock.sh lock
cabinet/scripts/germline-lock.sh status && cabinet/scripts/germline-lock.sh verify
python3.12 -m pytest cabinet/scripts/tests/test_library_retirement_ratchet.py -q
```

The staged-patch test detects the landed mark and skips; the grant-surface
ratchet stays green. Then flip CG-29 → done and tick the runbook follow-up.

## Lock-state provenance

All three target paths showed `schg` in fresh `ls -lO` checks on the live
box on 2026-07-17 (a 2026-07-16 evening unlock window had touched
`start-officer-mac.sh` — since relocked; one reviewer observed the
mid-window unlocked state, which is expected inside a ceremony and resolved
by the relock). Germline etiquette still applies: re-verify lock state
fresh (`germline-lock.sh status` / `verify`, `ls -lO`) IMMEDIATELY before
the ceremony — never trust this paragraph over a live check, and never
sync the live inode (checkout from master) outside a Captain window even if
a path happens to be writable.

## Also noted (not in this ceremony)

The `library` entry in `cabinet/scripts/lib/officer-env.py`'s per-server
env map (germline) is dangling-but-harmless — the server never boots, so
the map entry is never consulted. Drop it whenever that map is next opened
in a window of its own; it does not justify one.
