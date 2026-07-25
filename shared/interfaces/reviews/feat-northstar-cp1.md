# Checkpoint review — feat/northstar cp1 (FW-019)

**Scope:** the whole branch diff (1 new instrument, 1 config, 1 test suite, 1
runbook, 2 direction-config edits). **Class of evidence:** AUTHOR self-review
against the staged diff, not a fresh-context panel — weaker evidence, stated as
such. Landing is sequenced separately and should carry an independent pass.

Base: `origin/master` @ `05871f128da8e2be9e94e50ff531f35f6f9bd719`.

## What the change is

The stated north star `verified_outcomes_per_captain_minute` was computed
nowhere, and everything that WAS computed rewarded shrinking the Captain out of
his own loop. This branch re-words the metric as **attention well spent** — the
share of measured Captain minutes spent on decisions only he could make — and
makes it computable, with a must-ask floor that reads RED on under-asking.

## Premise check against current master (all four held)

| Claim | Verified at 05871f12 |
|---|---|
| `verified_outcomes_per_captain_minute` has zero implementations | 4 occurrences: `instance/config/directions.yml:71,97`, `instance/config/directions.yml.example:43`, `cabinet/dashboard/src/lib/world/directions.test.ts:115` |
| OVI weights Captain attention `inverse` | `framework/ovi/compute.py:145-147`; `framework/ovi/components.yml:29-35` `direction: inverse` |
| expiry streaks demote producers | `framework/attention/queue.py:256` `expiry_streaks`, `:276` `demoted_kinds` |
| "go quiet" instruction to officers | `framework/constitution-base.md:27` §5 "Minimize Captain interrupts" |
| the degenerate strategy is live | `--evidence` optional (`work-graph-complete.sh:38,203`); `--verified-value` declarable (`org_runtime.py:1904,1992`); all burden flags default 0 so `burden_index()` = 1.0 (`org_runtime.py:1721-1730,1904-1910`); `ovi = verified_value / burden` (`:1772`) |
| nothing counts unasked questions | no `must_ask` / floor construct anywhere outside preset agent prose |

## What I attacked, and what it found

1. **Can the floor be weakened from userland?** No. It is read at runtime from
   the `hard_ceiling` risk classes in `framework/policies/authority-matrix.yml`,
   and `framework/policies/` is an schg-locked germline directory. There is no
   local copy. An unreadable or empty matrix raises `LawUnreadable` (exit 2) —
   pinned by a mutation arm showing the guard's absence turns a breach green.
2. **Can going quiet still win?** No. Three independent defences: the unasked
   detector, the silent-window rule, and the expired-card price. Each has its
   own mutation arm; where two defences overlapped I added a benign approved
   row so the arm isolates the guard under test rather than passing on the
   other one's back.
3. **Can "just don't stamp it" evade the floor?** On the CLASS axis, no —
   `unclassified_executed` forces `unprovable`/AMBER. On the OUTCOME axis, YES,
   and it is NOT closed: a must-ask row with no recorded outcome is invisible.
   Named in the module docstring and the runbook rather than papered over; the
   fix needs a staleness clock, which is its own change and its own time-bomb
   risk.
4. **Can an officer mint Captain minutes?** No — `captain_*` events count only
   from actor ids in the config's captain list. Mutation arm proves the guard
   bites.
5. **Can a producer declare its own denominator?** No — behavioural arm (a row
   carrying `captain_attention_minutes`/`minutes`/`burden_index` changes
   nothing) plus a source-scan arm asserting the module reads none of those
   keys.
6. **Timestamp handling.** FOUND AND FIXED during review: window membership was
   a lexical ISO compare, so a `+02:00` stamp inside the window would be
   dropped. Now decided on parsed instants; unparseable stamps are honestly
   excluded. Mutation arm restores the string compare and shows the row vanish.
7. **ReDoS / path handling** (Corridor guardrails): probe refs are matched by
   LITERAL prefixes from config, never a config-supplied regex, over a
   4096-char clip. `--out` refuses any destination inside the repo tree.
8. **Never-a-score.** The module lives in `cabinet/`, not `framework/`, so
   officer-plane code cannot import it; it emits nothing; it cannot write into
   the tree; and a test fails if any file under `framework/`, `presets/`,
   `cabinet/dashboard/src/` or `.claude/` names it. EVAL-025 re-run green
   (12/12).

## Test-strength note

The module is brand new, so absence-failure would be worthless evidence. Every
guard is pinned by a TARGETED GUARD MUTATION: `_mutant()` copies the real
source, applies one replacement, **asserts the replacement actually bit** (a
no-op replace has certified false passes in this program), and the arm asserts
the property flips. 21/21 green; 8 of the arms are mutation pairs.

The headline arm runs one event corpus through BOTH engines: with the Captain
cut out, `framework.ovi.compute`'s `captain_attention_cost` component RISES
(4 → 0 raw, inverse-normalized score up) while this instrument goes green → red.

## Known contradiction — NOT resolved here, deliberately

`cabinet/dashboard/src/lib/world/directions.test.ts:115` asserts the literal
string `verified_outcomes_per_captain_minute` is present in the tracked apex
instruments. Deleting the superseded wording would red that test, and editing a
test to make a change pass is not allowed. So the token is RETAINED in
`instance/config/directions.yml` with a comment marking it superseded and
computed nowhere, and `attention_well_spent` is listed first. The `.example`
(which is what a fresh cabinet hatches with) carries only the new wording.
Retiring the string and that test line is one small follow-up change.

## Residual risk

- A single instance config now names two instruments for one idea until that
  follow-up lands. Mitigated by an explicit in-file comment, but it is real.
- No scheduled consumer yet: this is a CLI a human runs. That is deliberate
  (the "machinery outruns value" bias) — a fleet row can follow once the
  Captain has seen a reading he wants recurring.
