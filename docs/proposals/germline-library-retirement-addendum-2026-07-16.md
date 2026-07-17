# Germline addendum — Library retirement danglers (ceremony-only) — 2026-07-16

**Date:** 2026-07-16 (durable-surface + lock-state rev 2026-07-17, same
lane) · **Author:** library-retire lane (scratch clone off the GitHub
master tip; fix pass off `1cd84459`) · **Ledger row:** not yet assigned — a
CG row is required before the unlock window (integrator files it) ·
**Targets (ONE ceremony, three germline surfaces):** `cabinet/mcp-scope.yml`,
`.claude/settings.json`, `cabinet/scripts/start-officer-mac.sh` (all three
in `cabinet/scripts/germline-lock.sh`'s list; schg-locked on the live box) ·
**Patch artifact:**
`docs/proposals/germline-library-retirement-2026-07-16.patch` — a plain
FILE directly under `docs/proposals/` BY CONTRACT: the egg exporter's
`t_proposals_archive` `rm -f`'s each entry under `set -e`, so a
subdirectory here aborts the export (both package files carry
`expect-absent` manifest rows and archive out of the egg like every other
non-amendment proposal) · **Provenance:** no locked file was ever edited —
the patch was built against pristine copies in a disjoint scratch tree and
`cabinet/scripts/tests/test_library_retirement_ratchet.py::test_staged_ceremony_patch_stays_appliable_and_comment_only`
re-verifies it on every CI run without touching the locks.

## Why

The Library retirement (Captain-ratified 2026-07-16;
`docs/runbooks/library-retirement-2026-07-16.md`) deregistered the
`library` MCP server from both `.mcp.json` layers and removed every
non-germline `mcp__library` grant. Three germline surfaces still carry
dangling `library` references — harmless while the server is unregistered
(an unregistered server grants nothing; a comment misleads but executes
nothing), but they are resurrection bait and stale doctrine, and they can
only be cleaned inside a Captain sudo unlock window.

## Ceremony items (one window, relock the same day)

1. **`cabinet/mcp-scope.yml`** — remove `library` from every officer grant
   list and from `universal:`. Hygiene, not behavior.
2. **`.claude/settings.json`** — remove the `"mcp__library"` entry from
   `permissions.allow`. Hygiene, not behavior.
3. **`cabinet/scripts/start-officer-mac.sh`** — apply the staged
   comment-only patch (the MCP deep-merge comment's example list
   "notion/linear/neon/library" names the deregistered `library` and the
   long-deleted `linear`; the new text names living servers and records the
   deregistration date):

   ```bash
   # inside the unlock window, from the repo root:
   git apply --3way docs/proposals/germline-library-retirement-2026-07-16.patch
   ```

   Zero executable-line changes — the ratchet test enforces comment-only
   (non-comment lines byte-identical) and `bash -n` cleanliness against a
   copy on every run.

After the window: relock (`cabinet/scripts/germline-lock.sh lock`), re-run
`python3.12 -m pytest cabinet/scripts/tests/test_library_retirement_ratchet.py -q`
(the staged-patch test detects the landed state and skips; everything else
stays green — germline surfaces are deliberately not scanned), and tick the
ceremony follow-up in the runbook.

## Lock-state provenance

All three target paths showed `schg` in fresh `ls -lO` checks on the live
box on 2026-07-17 (a 2026-07-16 evening unlock window had touched
`start-officer-mac.sh` — since relocked; one reviewer observed the
mid-window unlocked state, which is expected inside a ceremony and resolved
by the relock). Germline etiquette still applies: re-verify lock state
fresh (`germline-lock.sh status` / `verify`, `ls -lO`) IMMEDIATELY before
the ceremony — never trust this paragraph over a live check, and never
apply the patch outside a Captain window even if a path happens to be
writable.

## Also noted (not in this ceremony)

The `library` entry in `cabinet/scripts/lib/officer-env.py`'s per-server
env map (germline) is dangling-but-harmless — the server never boots, so
the map entry is never consulted. Drop it whenever that map is next opened
in a window of its own; it does not justify one.
