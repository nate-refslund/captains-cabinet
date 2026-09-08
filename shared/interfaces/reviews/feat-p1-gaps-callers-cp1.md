# Review artifact — feat/p1-gaps-callers, checkpoint 1 (FW-019)

Unit 3b of phase 1: the gap CALLERS. Contract of record
`phase1-contracts-v2-2026-09-07` §3 plus amendments A3.1 (keyed records under
the claims lock) and A3.3 (the briefing-card line). Base: origin/master
e34ff1b8, with U3a (the kinds + `dedup_key`) and U2 (the claim) landed.

## What changed

| File | Why |
|---|---|
| `framework/missions/gaps.py` (new) | `observe_holder_gaps` — one keyed row per ready work item with no holder; self-resolving |
| `framework/missions/supervisor.py` | the unowned branch's bare `continue` now has a recorded row behind it; the unroutable event is untouched |
| `framework/missions/session_bridge.py` | `get_next_task` observes once per invocation, after the pull, under the claims lock; never raises, never changes the answer |
| `framework/frontdoor/run_briefing.py` | `_gaps_notice` — one counted card line for the two kinds only the Captain can close (A3.3) |
| `framework/learning/capability_gaps.py` | the `/gaps` ranking call, now that a keyed producer exists (one docstring paragraph) |
| `.claude/skills/capability-gap/SKILL.md` | docs track code: the structural kinds now reach the card too, and self-recorded gaps are keyed, not merged |
| `cabinet/config/cognitive-architecture-contract.yml` | two visible `maximum` raises + the adjudicated expansion row for the new module |
| `docs/proposals/holder-gaps-expansion-2026-09-08.md` (new) | the expansion adjudication the registry row binds to |
| tests | `test_gaps.py` (new, 13), `test_card_gaps_notice.py` (new, 11), one sensor each in `test_session_bridge.py` and `test_supervisor.py`, two modules added to the 3.9 pin list |

## The three judgement calls the contract left open

1. **The need sentence names IDS, not descriptions.** A description is instance
   text this module does not control: it can carry a product noun and a
   skeleton `<TODO` marker, and both would then sit in a gap row. Arm A's
   invariant 5 ("no `<TODO` in a gap") therefore holds structurally instead of
   by filtering. The ids are the same identifiers the evidence carries.
2. **`evidence` is the four contract fields as compact sorted JSON**, not a
   mapping: `record_gap` types it as a string and concatenates it into the
   touch inference, and the dashboard renders `gap.evidence` as a React child —
   a raw mapping there is an object child, which throws.
3. **The `/gaps` ranking for keyed rows: the order STANDS.** `hit_count` 1 is
   the honest count for a row recorded once, and re-ranking would move every
   existing free-text row to fix an order nobody has yet found wrong on the
   page. Recorded in `record_gap`'s own docstring, which had left the call to
   this unit.

## Where the risk is, and what covers it

* **A deadlock, if the observation were wrapped AROUND the pull.** `flock` is
  per open file description, so `claims_lock()` taken twice in one process
  waits on itself; `claims.claim` takes it. The observation therefore runs
  after the pull returns. `test_the_pull_path_takes_the_locks_in_order` pins
  claims → gaps → ledger at the one call site that holds both, and goes red
  (`['gaps','ledger'] != ['claims','gaps','ledger']`) against a mutant with the
  claims lock removed.
* **A merge storm, if the key were dropped.** Two need sentences one id apart
  are over the 0.6 Jaccard threshold.
  `test_eight_concurrent_observers_of_two_subjects_record_twice` goes red
  (3 rows, `dedup_key` None) against a mutant that ignores the key.
* **The pull path dying on a gap.** Both call sites wrap the observation, and
  `observe_holder_gaps` wraps each record and each resolve.
  `test_a_record_failure_never_kills_the_pass` asserts the pass continues past
  the first failure rather than stopping at it.
* **The 3.9 floor.** `gaps.py` and `capability_gaps.py` are now reachable from
  the locked hook, so both are added to `PULL_PATH_MODULES`; the execution arm
  runs the hook's own import-and-call under a real 3.9 and is green.

## What this unit found and did not fix

`test_supervisor.py::test_unmatched_roles_skip_silently` read as the pin on the
unowned-node branch and was not: its fixture's second and third criteria are
non-root nodes, the work-graph validator refuses a non-root node with no owner,
so the compile raises and `find_unassigned_ready_tasks` answers `[]` before any
node is looked at. It is renamed to say what it actually pins, and a second
test now covers the real branch. The compile-refusal path itself — an outcome
that cannot compile at all leaves no trace either — is NOT closed here: it is
outside §3's anchor and belongs to whoever owns the compiler's error surface.

`PULL_PATH_MODULES` remains hand-maintained; the real transitive closure of
`session_bridge` is 17 first-party modules against the 9 listed. The limit is
now written into the file next to the tuple.
