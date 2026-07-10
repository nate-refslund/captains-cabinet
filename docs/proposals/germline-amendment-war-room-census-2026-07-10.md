# Germline amendment — WAR-ROOM CENSUS joins the germline plane (2026-07-10, command-center Stage 1)

**Status:** STAGED DARK on branch `feat/germline-window-3` (worktree from
`origin/master`; pattern: germline-window-2). Rides the SAME window-3
ceremony as H0 + candor + W4 + W8 (`WINDOW-RUNBOOK.md`, §W-WARROOM) — one
unlock → pull/merge → gates → relock, no extra Captain steps. Nothing below
is live until that window. The apply token for the window
(**"apply candor law"**) covers this rider; reply **"drop war-room lock"**
to have this rider's commit reverted off the branch before the window
instead.

**Ratification chain (already-ruled — reference only, do NOT re-paste):**

- **Command-center proposal 2026-07-10** (Captain-ratified rulings C2/C4–C7
  logged in `captain-decisions.md`): the war-room census — situations fold,
  admission law, ranked queue, closure verb, standing queue card — becomes
  the ONE surface deciding what the Captain sees. Room v1 read-only +
  deep-link; C4 charter N=7; C6 |Decisions| falsifier; C7 seed list.
- **Germline doctrine (window-2 pattern, 2026-07-07):** code that decides
  what the Captain sees or silently closes the org's own asks is
  judge-plane by construction → Ring-0, staged in a worktree, never edited
  live.

## What (the germline edit set — staged in commit `875416fd`)

All FOUR germline lists gain the same four war-room paths, in lockstep
(`test_germline_lockstep_consistency.py` proves the lists agree):

1. `framework/policies/immutable-core.yml` — new files-class entries:
   - `framework/attention/situations.py` — the situation fold: ledger +
     undo-journal + feed + standing → the ONE lifecycle view (open →
     surfaced → pending → acted/decided → resolved/dormant). It decides
     what counts as LIVE — i.e. what the Captain sees.
   - `framework/attention/queue.py` — admission law + ranked census +
     the two projections (private authed / shared PII-scrubbed artifact).
     It decides what reaches the Decisions shelf and what leaves the
     machine-shared plane.
   - `framework/attention/hygiene.py` — the closure VERB
     (`propagate_closure` + zombie/stream sweeps): one event retires
     ledger rows, parked Redis cards, standing-card state. An officer
     edit here could silently close its own asks.
   - `framework/attention/queue_card.py` — the ONE pinned standing
     Captain-DM queue card (a sender surface).
2. `cabinet/scripts/germline-lock.sh` FILES — same four (the lock skips
   absent paths until the master merge lands the files, then arms
   automatically).
3. `cabinet/scripts/hooks/pre-tool-use.sh` §5 arm + §5b `GERM_PATH_RE` —
   same four.
4. `framework/policies/base-safety.yml` germline-readonly — same four.

Rider in the same commit: `framework/acting/run_action_lane.py` card-expiry
sweep journals a first-class `demote` feed row per expiry (H5: expiry is
ROUTING, never a verdict; best-effort, no behavior change to the sweep).

**Why:** situations/queue/hygiene/queue_card decide WHAT THE CAPTAIN SEES —
the admission law, the census every skin renders, the closure verb, the
standing card. An officer edit to any of them re-weights its own visibility
or silently closes its own asks — judge-plane by construction, same class
as `channel.py` / `feed.py` in the transport-floor amendment.

## Non-entries (promises pinned)

- The four modules' CODE lands via the master merge (they live and evolve
  on `feat/fidelity-harness-design` until then); this amendment adds ONLY
  the Ring-0 lock entries. The copies carried on this branch exist so the
  lockstep typo-guard proves the paths on disk.
- No authority-matrix / posture / grants change; no admission-law flip
  (`CABINET_ADMISSION_LAW` stays default-OFF pending the Captain's C3
  word).
- `framework/frontdoor/surface.py` (the 300s drain that CALLS the census +
  hygiene sweeps) deliberately stays non-germline: it holds no judgment —
  fold/admission/closure all live in the four locked modules.
- The shared artifact `shared/interfaces/attention-queue.json` is derived,
  rebuildable runtime output — never lock-listed.

## Gates (run in the staging worktree, 2026-07-10)

- `python3.12 -m pytest framework/tests/test_germline_lockstep_consistency.py -q` — green (lockstep, all four lists agree).
- `python3.12 -m pytest framework/tests/test_amendment_doc_lint.py -q` — green (every immutable-core entry referenced; this doc names the four).
- `python3.12 -m pytest framework/attention/tests/ -q` — green on branch.

**One-revert rollback:** a single `git revert 875416fd` on
`feat/germline-window-3` (or of the window-3 merge commit, per runbook R2)
removes the four entries from all four lists at once — the lockstep test
keeps them from ever disagreeing — and drops the H5 demote row with them;
then relock. No half-state exists: the lock's skip-absent behavior means an
un-merged path is simply not armed.

---
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
