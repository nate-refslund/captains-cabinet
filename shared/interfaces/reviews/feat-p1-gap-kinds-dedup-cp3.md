# Checkpoint review — feat/p1-gap-kinds-dedup (cp3, the rejection fix)

Base: origin/master `c479b5f5`. Unit U3a — contract §3 (the `capability_gaps.py`
half), amendments A3.1, A3.2, A0.3. This checkpoint answers the independent
reviewer's REJECT of `f656d8dc` (PR #370 comment 5571996282): one must-fix and
four notes.

## The must-fix, and why the reviewer was right

A0.3 asks for "a grep sensor over bare `python3` in unlocked exec strings". cp2
pinned both `/gaps` exec strings in SOURCE but asserted only one of them
(`lib/capability-gaps.test.ts:61`). `actions/gaps.ts` was covered by
`expect(mockDockerExec).toHaveBeenCalled()`, which is true of every possible
command including the wrong one. The reviewer proved it by mutation: revert
`actions/gaps.ts` to master bytes and `tsc --noEmit` is rc=0 with 39/39 vitest
green. Worse than the hole was the cp2 residual calling both anchors "pinned by
a vitest assertion" — a partial fix relabelled as covered, which is the class
this program has paid for a dozen times.

Not disputed, and not fixed by adding one assertion either. The narrow fix would
have closed the one anchor a reviewer happened to look at and left the same
class open everywhere else.

## What landed instead

**1. A0.3's grep sensor, over a DERIVED scope** —
`framework/tests/test_interpreter_pin.py` (new). Not a hand-listed anchor set: a
file is in scope when it is tracked, unlocked (the locked set is PARSED from
`germline-lock.sh`, never copied), not a test, and mentions a gap/pull-plane
token in code rather than in a comment. Nine files today. Writing it found two
violations nobody had listed:

| found | why it matters |
|---|---|
| `cabinet/scripts/record-capability-gap.sh:49` | the officer's own gap recorder, importing the very module this unit widened, under the box's 3.9 |
| `cabinet/cron/briefing.sh:33` | the daily trigger tells an officer to run the gaps CLI — with a bare interpreter |

Both are pinned in this commit. The scanner's own arms (`TestTheDetector`) prove
it goes red on a bare token and stays green on `python3.12`, on the pinned form,
and on prose — so it cannot be a scanner that finds nothing and reports success.

**2. Per-anchor assertions on the WRITE path** —
`cabinet/dashboard/src/actions/gaps.test.ts` (new): the command string handed to
`dockerExec` by `approveGap` and `declineGap` is asserted as a string — contains
the pin, leads with it, matches no bare `python3` — plus the two guard arms
(unauthenticated, malformed id) that prove the shell is never reached at all.

**3. Two PENDING rows, self-retiring.** `work-graph-complete.sh` (A0.3 names
:182/277/291) and `cabinet/cron/mission-supervisor.sh` belong to U2/U3b's file
list. Each row names its owner AND is asserted to still be violating: the day
U2 lands the pin, `test_pending_entries_are_still_violating` goes red and says
"PINNED NOW, delete this PENDING row". A waiver that survives its own fix is how
an allowlist becomes a blanket; this one cannot.

**4. A coupling the fix would otherwise have hidden.**
`test_the_script_runs_under_the_box_python3_not_the_suite_interpreter` was A0.3's
LIVE 3.9 arm — and it only tested 3.9 because the script happened to exec a bare
`python3`. Pinning the script (correct under A0.3) would have silently turned it
into a 3.12 arm and left the suite green. The arm is now direct: a subprocess
`python3` (3.9.6 on this host and on the box) imports the widened module,
records a keyed structural gap and reads the row back. Mutation-checked — an
evaluated module-scope `str | None` gives `python3.9 could not run the widened
module: TypeError: unsupported operand type(s) for |`.

## The four notes, each recorded where the next reader hits it

| ref | disposition |
|---|---|
| A3.1 (claims-lock ordering) | `_gaps_lock` docstring now fixes the order `claims-lock → gaps-lock → ledger-lock` and states that nothing here takes a claims lock, so the rule binds whoever adds the other direction |
| §3 (keyed `hit_count` = 1 forever) | recorded in `record_gap`'s docstring with the `/gaps` ranking consequence, and the reason it is not pre-empted: a ranking rule with no producer is a guess |
| §3 (a DECLINED keyed gap re-opens) | recorded in `_live_gap_with_id`'s docstring, including why nothing is granted (`can_install` reads the event ledger, not the projected status) |
| §0 (private `_event_log_dir` import) | `emitter.py` is U2's file at this commit, and a `try/except` fallback would put the lock where the ledger is not — a silent fail-open on a concurrency control. The import stays hard and the coupling is pinned by two tests, one behavioural (the lock lands in the ledger directory) and one that fires in the silent case: the rename landed WITH its import fix and this record left stale |

## Red→green, run this session

| sensor | red arm | rc | green |
|---|---|---|---|
| `test_interpreter_pin.py` | `actions/gaps.ts` at master bytes | 1 — names `:26` and `:42`, plus "lost the pin" | 14/14 |
| `test_interpreter_pin.py` | `record-capability-gap.sh` at master bytes | 1 — names `:46` | 14/14 |
| `test_interpreter_pin.py` | `lib/capability-gaps.ts` at master bytes | 1 — names `:55` | 14/14 |
| `test_interpreter_pin.py` | `work-graph-complete.sh` pinned locally | 1 — "PINNED NOW, delete this PENDING row" | 14/14 |
| `actions/gaps.test.ts` | `actions/gaps.ts` at master bytes | 1 — 3 of 5 fail on the pin; the 2 guard arms stay green, correctly | 5/5 |
| live 3.9 arm | evaluated `str | None` at module scope | 1 — `TypeError` under python3.9 | 8/8 |
| emitter coupling | `_event_log_dir` renamed public + import fixed | 1 — "no longer exports `_event_log_dir`" | 52/52 |

## Battery

`framework/` **8297 passed / 31 skipped** rc=0 (cp2's 8281 + 16 new).
Everything else re-run and recorded on the PR comment. Two rc=1 commands, both
the documented pre-existing set on this host, unchanged by this branch:
`test_evidence_seam_bypass_replay.py::test_shipped_catalog_harness_still_green[evidence-access.sh]`
(harness PASS=10 FAIL=2) and `run-hook-regression.sh` 11/19 with the failing set
{fw040-hotfix5, fw040-h6-v2, fw056-baseline, fw056-adversary,
fw057-notify-officer-argv, fw076-pool-mode, evidence-access, captain-exceptions}.

Locked set: 0 of the changed paths intersect the 73 FILES + 7 DIRS parsed from
`germline-lock.sh`.

## Residuals (corrected — this is the line cp2 got wrong)

- **A0.3's grep sensor now EXISTS** (`framework/tests/test_interpreter_pin.py`)
  and covers the gap/pull plane. Asserted anchors: `actions/gaps.ts` (source
  scan + two vitest command-string arms), `lib/capability-gaps.ts` (source scan
  + its own vitest arm), `record-capability-gap.sh` (source scan + a script
  test), `cabinet/cron/briefing.sh` (source scan). NOT yet pinned, and named as
  PENDING with their owner: `work-graph-complete.sh` and
  `cabinet/cron/mission-supervisor.sh`, both U2/U3b's.
- Coverage bound, stated: the sensor's scope is the gap/pull plane, not the
  general `framework.events.emitter` exec surface (12 tracked files, mostly
  locked hooks) — admitting it would trade one enforced invariant for seven
  waivers. `.py` files are out of scope by design; their protection is the 3.9
  half.
- **A3.3** (an `authority`/`information` line on the briefing card) and the
  `missions/gaps.py` producer are **U3b's**; U3a records and renders only.
- The standing runtime-3.9 CI leg arrives with the drill (U4); here it is a live
  local subprocess arm plus the static grammar/union analysis.
