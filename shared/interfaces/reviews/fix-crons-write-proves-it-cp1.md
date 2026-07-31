# Checkpoint review — fix/crons-write-proves-it cp1

Reviewed-Scope-Digest: 0ed1d6968d333f2b32a1625fdaa1c80284daf0064ec2f17c64a91f311d88455a

## What this change is

The scheduler's write path reported `{ success: true }` from having ISSUED a
shell pipeline. A pipeline's exit status is its LAST stage's, and the last stage
was always `crontab -`, which cannot fail on input it was handed. Four
false-success shapes were reproduced against the real server actions, a real
/bin/sh and a real `crontab(1)` stand-in; the worst destroys the entire schedule
and reports the edit as saved.

This is the defect PR #330 closed for the emergency stop, on the surface that
decides when every scheduled thing on the machine runs.

## Reproduction (measured, not argued)

Driven through the exported server actions with `docker` and `crontab`
stand-ins on PATH — real programs, real exit codes, real file:

| # | injection | pre-change result | crontab after |
|---|---|---|---|
| R1 | `crontab -l` fails (permissions) | `{success:true}` | **EMPTIED — all 3 jobs gone** |
| R2 | `sed` matches nothing | `{success:true}` | unchanged |
| R3 | `crontab -l` fails, on add | `{success:true}` | **only the new job survives** |
| R4 | delete one 06:00 job | `{success:true}` | **also deleted an unrelated 06:00 job** |
| R5 | delete something absent | `{success:true}` | unchanged |
| R6 | `crontab -` accepts and keeps nothing | `{success:true}` | unchanged |
| R7 | demo posture | `{success:true}` | nothing written, nothing disclosed |
| R8 | Mac-native (launchd) deployment | `{success:true}` | wrote to a crontab nobody is looking at |

Photographed in the BUILT app: 3 scheduled jobs before the edit, "0 jobs" after,
no error anywhere. `designs/crons-false-success-2026-07-31/` in the meta
workspace.

## The fix

`lib/crontab.ts` — a plane, not three extra lines:

1. read the whole crontab FIRST; a failed read is a refusal to write (this alone
   turns R1/R3 from destruction into an error message)
2. transform in TypeScript over lines — no `sed`, no `grep`, no shell, so no
   delimiter collision, no BRE metacharacter (the old escaping was for
   JavaScript's dialect and was fed to sed, where `\|` is alternation), no
   interpolation of a form field into a command line
3. write the new document to `crontab -` on stdin via `spawn`, argv array
4. read it back and compare full text AND the specific intent
5. on mismatch, restore the pre-image and VERIFY the restore; when the restore
   cannot be proven, say UNKNOWN and log the pre-image — never claim a rollback

Matching is on schedule AND command (R4). `no crontab for <user>` is an EMPTY
crontab, matched narrowly; every other read failure is a refusal (fail-closed).

`actions/crons.ts` — auth, then demo disclosure, then a launchd refusal, then the
verified commit. The officer-task timers get a POSTURE check as well as a
read-back, because with no `REDIS_URL` the in-process store echoes a write
straight back and a read-back alone passes while nothing was persisted.

`actions/officers.ts` — the same posture gate on start/stop/restart/delete. This
was the sweep's only other severity-5 row: with the store not live `dockerExec`
returns a sentinel without executing, so Stop All-adjacent per-officer Stop
reported success over an officer that was never contacted.

UI: `DeleteButton` destructured its action result away and the officer-task
buttons discarded theirs, so an honest error had nowhere to appear. Both now
render. An unreadable schedule renders "not readable" instead of "0 jobs".

## Evidence

- 48 new arms + 3 officer arms; full dashboard suite 3168 passed, tsc clean.
- 13 of 24 action arms are RED against `origin/master`'s `crons.ts`; every
  "inverse" arm (a write that genuinely lands) is GREEN both before and after,
  so this is not "make everything fail".
- 11 targeted mutations, each re-introducing exactly one defect the fences name;
  every one turns red the arm that names it, 0 false greens. The FIRST version of
  the launchd arm WAS a false green — `/launchd/` matched a different refusal —
  caught by the mutation run and narrowed.

## Known limits

- The reproduction uses a `crontab(1)` stand-in that implements vixie-cron's
  documented contract. A cron implementation with a different empty-state
  message is treated as unreadable (fail-closed) rather than empty.
- The remaining success-reporting paths in the app are enumerated with severities
  in the sweep table (PR body); this change fixes crons and officers and names
  the rest rather than half-fixing them.
