# Review checkpoint 2 — feat/p1-update-path (round-1 review answered)

The independent reviewer REJECTED checkpoint 1 on four must-fixes and listed
six notes. This checkpoint closes all four must-fixes and four of the six
notes, each with a sensor that was RED before the change and GREEN after. The
design was not disputed and is unchanged.

Contract of record: `phase1-contracts-v2-2026-09-07.md` §5 plus amendments
A5.1–A5.13, A0.5, A0.7.

## The four must-fixes

### 1. A5.7 / A5.8 — the lock now comes BEFORE the self-copy

`reexec_detached` copied the updater AND its helper into `.updates/run/` before
any lock was taken. `cp` truncates its target in place, and that target is the
file a first updater is EXECUTING FROM: bash reads its next command from a byte
offset, so the running updater silently continued out of the second caller's
bytes. The reviewer reproduced it end to end — a successful apply, then
`line 840: way: command not found`, then exit 1, so the web door that spawned it
was told the update had FAILED after it had landed.

Two changes, either of which would be sufficient and both of which are cheap:

- The lock is taken in the dispatch, ahead of the copy, for `apply` and
  `rollback` alike. It rides the open file description through the `exec`
  (measured on this host), so the process on the other side is still the
  holder; `lock_is_inherited` re-asserts on the SAME descriptor rather than
  re-opening the file, because a second open is a second description and
  closing the first would drop the lock for exactly as long as it takes to take
  it again.
- Copies land by `rename(2)` (`install_run_copy`: unique temp, then `mv`), so a
  running process stays on the inode it already opened.

The door has to be known before the option parse that would normally find it,
so `preparse_door` / `preparse_bundle` read `--from` and `--bundle` ahead of the
lock. Both are deliberately forgiving — anything malformed keeps the default
here and is refused properly by the real parse a moment later.

Sensors: `test_a_second_caller_cannot_overwrite_the_bytes_a_running_updater_executes`
(a length-shifted second caller runs while the first holds inside
`CABINET_UPDATE_TEST_HOLD_SECONDS`; the run copy's bytes must be unchanged, the
second must exit busy, and the first must finish its apply) and a new assertion
on `test_a_second_updater_exits_busy` that a refused caller never created
`.updates/run/` at all. The shipped busy arm could not have caught this: it
holds the lock from Python, so no first updater is ever running out of RUN_DIR.

### 2. A5.7 — a busy ROLLBACK leaves a receipt

`cmd_apply` emitted `cabinet_update_refused{reason: busy}`; `cmd_rollback`
exited 4 in silence. The door the Captain reaches for when an update went wrong
was the only refusal on this path with no row in the ledger. Both now route
through one `refuse_busy`, which also carries the door.

Sensor: `test_a_busy_rollback_leaves_a_receipt_like_every_other_refusal`
(rc 4, reason `busy`, `door: web`, actor `captain`, and nothing rolled back).

### 3. A0.5 / §0 — the consumer claim is now true, and now checked

The three expansion rows named `framework/watchdog/receipts.py`, whose
`RECEIPT_CLASSES` frozenset holds four watchdog classes and whose
`emit_receipt` RAISES on anything else. It could not consume these types and
never will. The census cannot catch that and says so about itself: its
`consumer` field is "an EXISTENCE-AND-DISJOINTNESS check, never a USE check …
Any path that exists in the tree satisfies it — `.git/config` does, measured".
The label channel was closed while the evidence channel stayed open.

Corrected two ways:

- **True.** The rows name `framework/frontdoor/run_briefing.py`, which reads all
  three types back by name (`_update_receipt_for`, over
  `emitter.replay(event_types=…)`, selected on the bundle rather than on
  recency). It is load-bearing rather than decorative: a REFUSAL writes no state
  file at all — it is refused before the first write and leaves a receipt and
  nothing else — so before this read, a bundle refused for touching the
  constitutional set sat in the inbox for ever behind a sentence that said
  "ready to take — tap Apply", which did nothing every time he tapped it. The
  briefing now says REFUSED, or rolled back, with the reason.
- **Checked.**
  `test_an_event_type_expansion_names_a_consumer_that_actually_names_it` reads
  the LIVE contract and requires every `central_event_types` expansion row's
  consumer file to contain the member's name. An event type is a string, which
  makes this one class mechanically decidable. It is not a general use check —
  there cannot be one — but it is the difference between a claim and a grep.

The `framework_production_noncomment_lines` allowance moves 54 → 88 for the
lines that read costs, measured (79391 → 79479), with the reason text carrying
the fourth thing the lines buy.

### 4. A5.13 — the briefing half has sensors now

`_update_notice` was ~50 production lines ending in a blanket
`except Exception: return ""`, wired into `_plain_headline`, with zero coverage
anywhere. The reviewer exercised it by hand and found all four arms correct, so
this was an untested control rather than a broken one — and an unexercised
total fail-open is the exact shape this program has paid for repeatedly.

`framework/frontdoor/tests/test_card_update_notice.py` — 18 arms: waiting,
applied, rolled-back-with-reason, rolled-back-without-one, applying; the
degenerate end (no updater at all, a root that does not exist, an unreadable
state file, a manifest with no tarball beside it, a bundle of the installed
commit); newest-of-several; the three receipt arms; an unreadable ledger that
must not cost the notice; and the wiring into the headline in both directions.
Twelve of the eighteen fail against a mutated `_update_notice` that returns ""
unconditionally; the six that survive are the arms that pin the silence, which
is what they are for.

## The notes, and what happened to each

| Note | Disposition |
|---|---|
| stage tree never pruned | FIXED. `rm -rf $STAGE/$sha` after a green gate and on the no-op path. Sensor: `test_the_unpacked_stage_tree_does_not_outlive_a_green_apply`, which also asserts the snapshot survives — pruning the stage is not pruning the way back. |
| un-namespaced gate seams | FIXED. `CABINET_UPDATE_TEST_RECEIPTS_CMD` / `CABINET_UPDATE_TEST_PREFLIGHT_CMD`. The defaults arm now also refuses any `CABINET_UPDATE_*_CMD` / `_KILL_AFTER` / `_HOLD_SECONDS` name that is not `CABINET_UPDATE_TEST_`-prefixed. |
| `HEADER_ONLY_INTERFACES` pinned by a `captain-`-shaped regex | FIXED. The pin now reads the transform's own `_header_only` call targets and its fail-closed case arms, and asserts the emptied set equals the constant and is a subset of what may ship. Proved by mutation: a header-only path named `interface-notes.md` is caught by the new pin and was green under the old one. |
| fixture harness symlinks the live `framework/` | FIXED. `make_bundle` refuses a fixture bundle carrying any `framework/` path, with `test_a_fixture_bundle_may_not_ship_a_framework_path` as the inverted arm. |
| contract §0 says "register in VALID_EVENT_TYPES … and architecture-baseline-sets.yml" | RESIDUAL, and the reviewer agrees the deviation is right: the ratchet refuses a baseline addition in the same commit as the member it excuses. The contract lives in the orchestrator's gate artifact, not in this repo; carried to the PR comment for the next authoring pass. |
| the gate's receipts leg is the emitter replay, not `receipts --json` | UNCHANGED, as the reviewer accepted. Retires onto `framework/missions/receipts.py` when unit 1 lands; the census expansion row carries that deletion gate. |

## Found while fixing, and fixed: the lock outlived the updater

Not in the review. `A5.7` is "one updater at a time", not "one updater ever" —
and the unsupervised restart path starts a DETACHED dashboard, which inherits
every open descriptor, including the fd the lock lives on. The dashboard then
held the updater's lock for as long as it lived, so every later update from the
card would have refused itself as busy, for ever, on exactly the deployment
shape this leg exists for.

`restart_dashboard` now runs the restart inside `( exec 9>&-; unset … )`. The
subshell-with-`exec` form is not decoration: `cabinet_dash_restart … 9>&-` does
NOT work on the bash this ships against (3.2 on macOS), because a per-command
redirection SAVES the original descriptor by duping it to a high fd and the
detached child inherits that duplicate — measured, the child held the same lock
on fd 10. The env flag that says "the lock you inherited is yours" is unset with
the descriptor, so a process that no longer has it is never told it still holds
the lock.

Sensor: `test_the_restarted_dashboard_does_not_inherit_the_updater_lock` — a
stub restart that spawns a long-lived detached child, then an outsider must be
able to take the lock after the updater exits. RED on the pre-change bytes with
`[Errno 35] Resource temporarily unavailable`.

## Evidence

Local battery in a fresh clone of the pushed SHA (Actions is billing-locked; the
per-job-equivalent commands are the gate under A0.6). Per-test and per-harness
verdict lines, never counts, are on the PR. No locked path is touched: the
`germline-lock.sh` FILES/DIRS set is parsed programmatically (73 files, 7 dirs)
and intersected with the branch diff and the working tree — empty.
