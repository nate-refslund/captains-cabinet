# Germline amendment proposal — INSTANCE-EXTRACT (E4) — 2026-07-05

**Status:** AWAITING CAPTAIN. Every germline file named below is
Captain-applied only. Reply **"apply instance-extract"** and the session
executes the apply ritual (§5) exactly: unlock → merge `feat/instance-extract`
→ re-lock → verify. Nothing in this package changes live behavior at all — it
is a pure DATA-source extraction whose entire correctness proof is that, on
THIS instance, every resolver returns the SAME value the hardcode had, so the
three files render byte-identical to today.

**Branch of record:** `feat/instance-extract` (worktree
`.claude/worktrees/instance-extract`, base `fa6c3032`). The branch is the diff;
this document is its Captain-readable contract for the **germline** subset
(3 files). The branch also carries the NON-germline half of this run (the three
`framework.env` resolvers, their consumer in `decision_cell.py`, the
`instance/config/platform.yml` keys, the `framework/autoreply/` →
`instance/flavor-a/autoreply/` move, and the ratchet-allowlist shrink) — all of
which merge with **no unlock** and are recorded in
`docs/plans/instance-extract-e4-2026-07-05.md`, not here.

**Encodes (already-ruled, logged live in
`shared/interfaces/captain-decisions.md` on 2026-07-05 — reference only, do NOT
re-paste):**

- **FOUNDATION-FIRST + EVOLUTION ENGINE GO (2026-07-05 ~00:45, Captain-ruled,
  in-session)** — the target artifact is the FRAMEWORK: universal,
  launcher-agnostic, for any captain, either flavor; Nate's deployment is the
  first instance and proving ground, not the product. Clause (a): *"anything
  Nate-specific (vault paths, screenpipe, Monday board IDs, officer names)
  belongs in `instance/` or adapters, never `framework/`."* Clause (4):
  *"launcher genericization is IN-SCOPE core work … not deferred
  productization."* The DE-NATE sweep (germline amendment `apply de-nate`,
  2026-07-05) parameterized the captain NAME and deliberately LEFT these three
  data couplings in place, FLAGGED for a follow-up
  (`docs/plans/de-nate-foundation-2026-07-05.md` §4, flags 1/2/5). **This
  amendment discharges those flags for the germline subset.**

## §0 · What this changes, in one paragraph

Three `framework/` files that carried a launcher-specific DATA CONSTANT (the
org's internal email-domain list, the Monday tasks-board id) now read that
constant from `instance/config/platform.yml` through a `framework.env`
resolver, exactly as `env.captain_name()` already does. No classifier
predicate, no board-routing branch, no cap, no canary step, no verdict table,
authority path, threshold, or event vocabulary is touched — only the SOURCE of
two constants moved from a Python literal to instance config. Because the
resolvers return the SAME values on this deployment
(`org_domains()` → the same six domains, `tasks_board()` → `"5091706356"`),
every runtime byte the three files emit is identical to `fa6c3032` — which is
the correctness proof: the existing tests that pin classification and
board-routing stay green unchanged (§3), and the resolvers fail closed to
generic values (empty domain list ⇒ every recipient external; empty board ⇒
`isdigit()` refuses the create) so a clean-room / Flavor-B deployment inherits
no launcher data.

## §1 · Per-file inventory (the branch is the diff)

Export the exact germline diff set for review:

```bash
git -C /Users/nate/captains-cabinet/.claude/worktrees/instance-extract \
  diff fa6c3032 -- \
  framework/authority/classifier.py \
  framework/frontdoor/action_exec.py \
  framework/frontdoor/actfirst_canary.py
```

| file | change (data-source extraction only, NO classification/verdict/board-routing logic change) | germline |
|---|---|---|
| `framework/authority/classifier.py` | `_INTERNAL_DOMAINS = ("stepnetwork.dk", …six…)` → `_INTERNAL_DOMAINS = env.org_domains()` (`+from framework import env`). The `_is_internal_recipient` predicate was UNCHANGED BY THIS AMENDMENT — only the domain SOURCE moved to config. (SUPERSEDED 2026-07-27 by the `recipient-all-internal-quantifier` landing: the predicate now requires EVERY address in a recipient field to be at an org domain, not just the last one. Strictly narrowing; the domain source is still this resolver.) `org_domains()` returns the same six on this instance ⇒ internal/external classification byte-identical; fails closed to `()` (every recipient external — the conservative comms ceiling). | yes |
| `framework/frontdoor/action_exec.py` | `DEFAULT_TASKS_BOARD = "5091706356"` → `DEFAULT_TASKS_BOARD = env.tasks_board()` (`+from framework import env`). `_resolve_board`'s `ACTION_LANE_DEFAULT_BOARD` env override and the `board_hint`/explicit-`board_id` routing are UNCHANGED; `tasks_board()` adds a `CABINET_TASKS_BOARD` env override upstream. Resolves `"5091706356"` here ⇒ byte-identical; fails closed to `""` so `_exec_monday_create`'s `isdigit()` guard refuses rather than leaking a board. | yes |
| `framework/frontdoor/actfirst_canary.py` | `board: str = "5091706356"` (×3 runners: `run_canary` / `run_weekly` / `run_unfreeze_canary`) + `--board` CLI default → a single module const `_DEFAULT_BOARD = env.tasks_board()` referenced by all four (`+from framework import env`). Cap/freeze/canary/unfreeze logic UNCHANGED; a caller may still pass `board=` explicitly. Resolves `"5091706356"` here ⇒ byte-identical; fails closed to `""`. | yes |

All three files add exactly one import line (`from framework import env`) and
change exactly one (classifier / action_exec) or one-plus-four-references
(canary, all pointing at one new module const) constant SOURCE. No file changes
a signature, a return type, a branch, a predicate, a cap, or a test's expected
value. `framework.env` is a leaf module (it imports only stdlib + a local
`yaml` at call time) so no import cycle is introduced.

## §2 · What this amendment does NOT do

- **No verdict / authority / threshold / classification change.** The
  action-classifier's internal-vs-external predicate, `action_exec`'s
  board-routing precedence, and the canary's cap/freeze/unfreeze logic are all
  untouched. Only two data CONSTANTS changed their SOURCE (literal → config).
- **Guardian, sovereign, AND earn_up stay byte-identical.** None of the three
  files reads a posture; the resolvers return the same value in every posture.
  The three autonomy levels resolve exactly as at `fa6c3032` (this extraction
  is orthogonal to the axes / sovereign amendments).
- **Golden evals unchanged.** No `memory/golden-evals/*` file is touched; every
  eval spine passes against identical rendered classification/board output (the
  resolvers yield the launcher's values here).
- **No new event types, no new framework control flow.** No branch is added;
  the two new instance-config KEYS (`org_domains`, `tasks_board`) live in
  `instance/config/platform.yml` — the INSTANCE layer, not germline (recorded
  in the plan). `framework/` gains no config key of its own.
- **No instance-specific data forced into a resolver's default.** The generic
  defaults are `()` and `""` — a deployment with no org / no board configured
  stays generic and fail-closed, never inheriting Nate's domains or board.

## §3 · The correctness proof (why byte-identical == changed no behavior)

On this deployment `env.org_domains()` returns exactly
`("stepnetwork.dk", "jfmedier.dk", "jysk-fynske-medier.dk", "polads.eu",
"refslund.ai", "step.dk")` and `env.tasks_board()` returns exactly
`"5091706356"` (both read from `instance/config/platform.yml`, both cached once
per process — same lifecycle as `captain_name()`). Therefore every runtime site
these three files touch renders the SAME bytes it did at `fa6c3032`. The proof
that no behavior changed is that **the tests which pin classification and
board-routing stay green with no edit** — a red pinned test would mean a value
moved, i.e. the extraction was done wrong. Verified in-worktree (scoped run, all
green):

```
python3.12 -m pytest \
  framework/authority/tests/test_classifier.py \
  framework/frontdoor/tests/test_action_exec.py \
  framework/frontdoor/tests/test_actfirst_canary.py \
  framework/fidelity/tests/test_decision_cell.py \
  -q -p no:cacheprovider
# → 242 passed
```

The `env` resolvers themselves are pinned by 17 new tests in
`framework/tests/test_env.py` (`TestOrgDomains` / `TestTasksBoard` /
`TestCaptainRole`), including byte-identity guards that assert this worktree's
`platform.yml` yields the six domains and `5091706356` with `CABINET_ROOT`
unset (`22 passed`). The forward-looking guarantee is the ratchet + fail-closed
defaults.

## §4 · CI proofs

| Proof | Where it lives | Asserts |
|---|---|---|
| R1 | `framework/tests/test_env.py::TestOrgDomains` / `::TestTasksBoard` | the resolvers read config, strip/lowercase domains, honor `CABINET_TASKS_BOARD`, and **fail closed** (`()` / `""`) on absent config; byte-identity guards pin this instance's six domains + `5091706356` |
| R2 | `framework/authority/tests/test_classifier.py`, `framework/frontdoor/tests/test_action_exec.py`, `framework/frontdoor/tests/test_actfirst_canary.py` | byte-identical classification / board-routing on this instance — green with NO edit is the §3 proof |
| R3 | `framework/tests/test_no_launcher_hardcode.py` (the clean-room ratchet) | `framework/` stays launcher-agnostic; the whole-file allowlist entry for the now-moved `kristoffer_uat.py` is dropped (non-germline, in the branch — see the plan) so the ratchet scans a smaller `framework/` tree with no dead cover |

## §5 · APPLY-GATE evidence pack (all green before you reply) + apply ritual

**a. Suites green — run the three roots SEPARATELY.** A combined
`framework/ cabinet/scripts/lib/tests cabinet/scripts/gates/tests` invocation
errors at collection (`lib/tests` and `gates/tests` both claim the top-level
`tests` package — **NEVER use the combined form**). Reference baseline:
framework/ 3361 passed / 17 skipped · lib 470 · gates 6. The only `pytest
framework/` collection delta from this run is the **46 autoreply tests that
relocated** to `instance/flavor-a/autoreply/tests/` (run there, still green) and
the **+17 new resolver tests** in `test_env.py`; no test regresses.

```bash
python3.12 -m pytest framework/ -q -p no:cacheprovider
python3.12 -m pytest cabinet/scripts/lib/tests -q -p no:cacheprovider
python3.12 -m pytest cabinet/scripts/gates/tests -q -p no:cacheprovider
```

**b. Ratchet strict-fire probe** — `python3.12
framework/tests/test_no_launcher_hardcode.py` prints every offender and exits
non-zero on any leak; on the complete branch it prints
`OK: framework/ is launcher-agnostic` and exits 0. (This is green only once the
branch's non-germline ratchet-allowlist shrink is included — the autoreply move
and its one-line allowlist deletion are the same unit of work; see the plan.)

**c. Concurrent-germline reconciliation — MANDATORY re-check before merge.**
A separate agent is editing the LIVE repo's germline in parallel (de-nate /
axes / sovereign waves touch `authority/` and `frontdoor/`). Before the merge in
step (d), re-diff these three files against live `HEAD` and reconcile:

```bash
git -C /Users/nate/captains-cabinet fetch --all
git -C /Users/nate/captains-cabinet/.claude/worktrees/instance-extract \
  diff origin/main -- framework/authority/classifier.py \
  framework/frontdoor/action_exec.py framework/frontdoor/actfirst_canary.py
```

The extraction is a MINIMAL diff by design (one import + one const-source swap
per file) specifically so it rebases cleanly onto whatever the concurrent
germline agent lands. If live has moved a line this touches, reconcile
surgically (keep live's logic, re-apply only the literal→`env.<resolver>()`
swap) — never re-hardcode the value to dodge a conflict.

**d. Apply ritual (one sitting):**

```bash
sudo bash cabinet/scripts/germline-lock.sh unlock
git merge feat/instance-extract   # the 3 germline files above are why the
                                  # unlock is needed. The non-germline half
                                  # (resolvers, decision_cell, platform.yml,
                                  # autoreply move, ratchet-allowlist shrink)
                                  # merges in the same commit, no special
                                  # handling.
sudo bash cabinet/scripts/germline-lock.sh lock
bash cabinet/scripts/germline-lock.sh status && bash cabinet/scripts/germline-lock.sh verify
# re-run §5a suites post-merge; all three roots green, no count regression.
```

**One-revert rollback:** revert the merge commit. Because every germline change
is a byte-identical literal→`env.<resolver>()` source swap (plus one import
line), reverting restores all three files to `fa6c3032` verbatim; there is no
state file to delete, no config to unwind, and nothing was ever behaviorally
live to quiesce. (The instance-config keys added to `platform.yml` become inert
once the resolvers are gone — harmless to leave or revert with the merge.)

## §6 · captain-decisions.md — ledger state + the ONE paste-ready apply record

**Already logged live (2026-07-05, reference only — do NOT re-paste):**
`## FOUNDATION-FIRST + EVOLUTION ENGINE GO (2026-07-05 ~00:45, Captain-ruled,
in-session)` in `shared/interfaces/captain-decisions.md`. On apply, add one line
under it: *"Realized (clause a / clause 4, three germline data couplings:
org-domains + tasks-board) by: germline amendment instance-extract 2026-07-05
(`apply instance-extract`); discharges de-nate flags 1/2/5."*

**Apply record — paste-ready** (paste when you apply):

```markdown
## INSTANCE-EXTRACT (E4) APPLIED (2026-07-05, Captain apply token: `apply instance-extract`)

**What:** Applied the instance-extract germline amendment
(docs/proposals/germline-amendment-instance-extract-2026-07-05.md): 3 germline
framework files lifted a launcher DATA CONSTANT to instance config —
classifier.py reads the internal org-domain list via framework.env.org_domains(),
action_exec.py + actfirst_canary.py read the Monday tasks-board id via
framework.env.tasks_board(). Data-source extraction only; NO
classification/verdict/board-routing logic change. Guardian, sovereign, and
earn_up byte-identical; golden evals unchanged. Correctness proof:
org_domains()==the six domains and tasks_board()=="5091706356" here ⇒
byte-identical render ⇒ pinned classification/board tests green unchanged
(242 passed); resolvers fail closed to ()/"" for a clean-room deployment. The
non-germline half (the framework.env resolvers, decision_cell captain_role
consumer, platform.yml keys, framework/autoreply → instance/flavor-a/autoreply
move, ratchet-allowlist shrink) merged in the same commit.

**Why:** Realizes clause (a) + clause (4) of FOUNDATION-FIRST (2026-07-05) and
discharges de-nate flags 1/2/5 — the org's domains, board ids, and the Flavor-A
autoreply cell belong in instance/, never in framework/. Reference only, full
text in that entry.

**Captain:** Nate.
```

Reply **"apply instance-extract"** to apply exactly the above.
