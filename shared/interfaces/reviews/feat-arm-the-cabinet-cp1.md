# feat/arm-the-cabinet — cp1 review artifact (FW-019)

**Branch** `feat/arm-the-cabinet` · **Date** 2026-07-26 · **Model** Opus 5
**Scope** four Captain rulings of 2026-07-26, landed as ONE unit because all
four touch the service manifest and the census.

## What landed

| ruling | outcome |
|---|---|
| 1 — raise the services cap ONCE, then pin it | `services_enabled` 40→**50**, `services_total` 52→**54**, both at observed==max with ZERO slack. One bump for the whole batch; no per-service bump; no `temporary_allowances` row. |
| 2 — enable the parked seven (+ the work-first four) | **8 rows armed + 2 new rows**. `mission-supervisor` and `memory-curator-health` NOT armed — both proved off for a real reason (below). |
| 3 — arm self-improvement auto-apply AND recompute, together | `REPORT_ONLY` `"1"`→`"0"`; the shadow recompute row armed. Both Captain-ordered safeguards built and proven end-to-end. |
| 4 — drafting to act-then-tell | **NOT SHIPPED — germline.** Filed as CG-35 + a complete amendment doc. No lying setting shipped. |

## Rows armed (8) + new (2)

`research-sweep` · `backlog-refine` · `killswitch-watchdog` ·
`healthchecks-drill` (after the re-point) · `officer-lifecycle-transitions` ·
`authority-transitions` · the shadow detector row · the shadow recompute row ·
**new:** `cog3-verdict-inbox` (daily 07:10) · `cog3-shadow-dividend`
(Sundays 09:30).

Post-batch: **54 rows / 50 enabled / 4 parked**, census PASS at the new pins.
All 10 render: `generate-plists.py --output-dir` goes 40→50 plists, `plutil
-lint` OK on each, schedules and commands verified by loading the plists back.

## Two rows deliberately NOT armed (false premises in the brief)

**`mission-supervisor`** — not class-(b). Arming the push router while officers
also PULL double-dispatches the same task, and there is no claim primitive
anywhere: `git grep -n 'def claim\|claim_task\|work_item_claimed' framework/
cabinet/` returns 0 hits. Wiring one reaches
`cabinet/scripts/hooks/session-task-inject.sh`, inside the schg-locked hooks
dir — a Captain unlock, not a small change. Second defect found and recorded in
the row: its wrapper invokes `python3 -m framework.missions.supervisor`
unpinned (3.9 under launchd; the framework is 3.12).

**`memory-curator-health`** — not class-(b). The proposed ~20-line re-point
lands on `cabinet/logs/retrieval-eval-history.jsonl`, which the **already
enabled** `retrieval-eval` row writes nightly and which **cabinet-doctor check
11 already reads** (`cabinet-doctor.sh:828-858`, breach or >48h stale =
WARN/AMBER). Arming it ships a second pager on an already-watched signal.

## Ruling 3 — what arming actually bought, measured before arming

The loop **cannot reach code**: `_is_code_diff_proposal` routes every
`code_change`/`code_diff` proposal (and anything with a non-empty `diff`) to
`framework.learning.gate.ratify`, which produces an evidence pack and applies
nothing. It CAN mutate: role capability lists; a role's **descriptive**
`authority_level` (read by officers as roster context,
`cabinet/scripts/lib/officer-boot.sh:143` — not by the enforcement plane, which
stays matrix × posture × lane); skill-draft `status:` flips under sovereign
posture; proposal-YAML status stamps.

**Safeguard (a)** — `_journal_application` in
`framework/learning/self_improvement_loop.py` appends one row per application
(what changed · why · evidence cited · the exact inverse) to
`cabinet/logs/self-improvement-applications.jsonl`;
`cabinet/scripts/self-improvement-journal.py --undo <id>` is the one-command
revert. Journalling is best-effort-LOUD: a write failure prints and never
aborts an application (a half-applied loop is worse than an unlogged one).
Proven in a sandbox: capability add → undo → gone; authority widen → undo →
pre-image restored; double-undo refused; no-pre-image refused rather than
guessed.

**Safeguard (b)** — the weekly shadow-dividend report carries a
"Self-improvement — applied to itself" section. Proven end-to-end against a
real built objectives graph. The dividend CLI stays byte-pure (serve-surface
only, no clock, no env, no shelling) — the wrapper appends afterwards.

## Ruling 4 — why nothing shipped, and a correction of record

`framework/policies` is a whole locked DIRECTORY, so `authority-matrix.yml` is
germline; the ceremony is a non-grantable Captain unlock. Filed as **CG-35**
(ledger + plan-doc parity green) with
`docs/proposals/germline-amendment-draft-only-act-then-tell-2026-07-26.md`
carrying the complete edit, validator analysis and the exact test pins to move.

**The brief's fix location was the wrong plane.** It said to make the
`act_then_tell` rung real in `framework/authority/posture.py`. `POSTURES` is
the whole-cabinet ladder — adding the token would widen every risk class at
once, not drafting, and that file is germline too. In the MATRIX plane,
"act-then-tell" is the already-implemented `notify_after` verdict that
`read_only_dispatch` rides today; the ruling needs the `draft_only` row moved
onto it and nothing else. No config naming `act_then_tell` shipped —
deliberately: it resolves to `guardian`, which would be a setting that lies.

## Tests: none weakened; two guards strengthened

Five tests pinned pre-ceremony staging and were re-pinned to the post-ceremony
state, exactness preserved in both directions (the two shadow-evidence test modules ×3, `test_registry.py` ×2). The shadow-law
zero-consumer proofs were **not** touched and **no allowlist was widened** —
when my prose tripped them, I reworded the prose.

`test_wrapper_spof_and_monitor_gating.py`: `healthchecks-drill` left
`_SCREENPIPE_MONITORS` (it is no longer personal-source-coupled) and gained two
strictly stronger executable guards — an AST check that its default target
constants can never point back at a personal source while the row is enabled,
and a behavioral proof that a credless box exits 0 with `DRILL_SKIP`. Both
mutation-tested RED.

New: `cabinet/scripts/tests/test_self_improvement_journal.py`, 14 tests,
mutation-tested (a no-op `--undo` REDs 2 of them).

## Gates (this session, on this branch)

framework `6531 passed / 25 skipped / 1 failed` — the single known
pre-existing red `test_retro_shim.py::test_reexports_constants`, identical to
the pre-change baseline · `cabinet/scripts/tests` 4686/28 (was 4670/28; +16 =
the new file + the 2 new drill guards) · lib 306 · task_adapters 38 ·
world-aesthetic 87/5 · layer-sep new=0 · cog2-import-gate OK · census PASS at
54/50 zero-headroom · A13 parity exit 0 · golden evals 29/29 · null-hatch PASS ·
`verify-cognitive-phase4` PASS · `hatch.sh --defaults --clean-room` GREEN ·
plist render 50/50 `lint=OK`.

## Deploy steps this commit does NOT perform

Nothing was loaded into launchd and no fleet was touched (read-only against the
live tree throughout). On the target: `generate-plists.py`, copy to
`~/Library/LaunchAgents`, rename the two `.plist.disabled` files
(`research-sweep`, `backlog-refine`) back to `.plist`, and bootstrap the ten
labels. `self-improvement-loop` needs a re-render + reload for the
`REPORT_ONLY=0` env to take effect, and the weekly chain needs `REPORT_ONLY=0`
in its environment too.
