# Egg claim audit — 2026-07-28

The first deliberate sweep of the **public export's own claims**. Four false
claim surfaces had shipped in the egg in the preceding week, each found by
accident while doing something else. Nobody had ever swept the export on
purpose. This is that sweep.

**Method.** Cut the egg (`cabinet/scripts/egg-export.sh --out …`, 2362 files
from `49ed144e`), enumerate every **checkable** claim in what ships — a claim
is checkable when it asserts a *property of the system* ("this fails closed",
"X cannot be bypassed", "every X carries a Y"), not a quality ("this is fast")
— and verify each **by running the thing**, never by reading the code and
reasoning about whether it matches the sentence. Ranked by blast radius: a
false claim about a **safety** property outranks a stale path, because a
stranger trusting a safety sentence that is not true is the worst thing this
program can ship.

A claim that is true only because a feature is dormant is recorded as FALSE.

Scope swept: `README.md`, `SECURITY.md`, `captains-cabinet-guide.md`,
`docs/how-your-cabinet-is-governed.md`, the shipped `.claude/skills/*/SKILL.md`
set, `framework/docs/`, `docs/runbooks/`, and the enforcement code each of
those sentences names. **Not** swept (named here so the coverage claim is
bounded — see evidence-discipline class 4): dashboard/World UI copy,
`presets/*/agents/*.md` officer role text, `packs/*`, and the Telegram card
strings emitted at runtime.

---

## Findings — false claims, ranked by blast radius

### F1 — SAFETY. "Unmeasured means propose-only" is false at the shipped default

**Quoted, as shipped:**
* `README.md` — *"the **authority matrix** maps risk class × confidence to a
  verdict (auto / propose / gated), **with unmeasured always meaning
  propose-only**."*
* `README.md` — *"**Propose-first by default:** unmeasured action classes are
  propose-only by construction."*
* `README.md` — *"Every consequential action starts as a proposal."*
* `captains-cabinet-guide.md` §1 principle 6 — *"**Fail closed, degrade
  honestly.** Unmeasured means propose-only."*

**What is actually enforced.** The default posture is `guardian`
(`framework/authority/posture.py:resolve_posture()` returns `guardian` both as
shipped and with the config file absent). Under it, 5 of 13 risk classes
resolve to something **other** than propose-only at `unmeasured`:

| risk class | verdict @ unmeasured |
|---|---|
| `reversible`, `pm_write`, `calendar_write` | `act_with_undo` |
| `read_only_dispatch`, `draft_only` | `notify_after` |
| `internal_comms`, `deploy_nonprod` | `propose_only` |
| the six ceiling classes | `always_gated` |

This is deliberate — the earn-demotion ruling (2026-07-03/04) inverted the
trust-first rows, and `draft_only` crossed to act-and-tell on 2026-07-26. The
matrix even guards against re-introducing the old behaviour
(`matrix.py:_validate_act_first_floor` makes `propose_only@unmeasured` on a
trust-first row a hard validation error). The doctrine moved; these four
sentences did not. `docs/how-your-cabinet-is-governed.md` describes the current
behaviour correctly, so the egg **contradicted itself** on its central safety
promise.

**Verified by:** `matrix_policy(load_matrix())["verdicts"]` printed per class;
`posture.resolve_posture()` with the config present and absent.
**Corrected** in `README.md` and `captains-cabinet-guide.md` (this branch).

> **F1a — the correction was itself wrong, and this is the lesson of the sweep**
> (adversarial re-review, same day). The verification above read the matrix
> *table*; it never ran the lane. Executed inside a freshly cut export:
> `run_action_lane._act_first_on()` → `False` (no `instance/config/act-first-enabled`,
> no `CABINET_ACT_FIRST`), `posture.posture_config_present()` → `False`,
> `run_action_lane._load_posture_ctx()` → `None`,
> `policy_engine.authority_matrix_enforcing()` → `False`, and the shipped
> `instance/config/act-first-surfaces.yml` is the empty unratified twin. The
> lane's own gate says it plainly: *"DEFAULT OFF. The entire earn-demotion
> posture stays DARK until the Captain flips it … with it off, `main()` behaves
> byte-identically to the propose-only lane."* So **"the reversible classes act
> from day one" is false in the egg** — a stranger's hatch proposes everything,
> and the sentence F1 called false ("every consequential action starts as a
> proposal") was the behaviourally true one. Corrected a second time in
> `README.md` ×2, `captains-cabinet-guide.md` §1.6 and
> `docs/how-your-cabinet-is-governed.md`, which carried the same sentence and
> was wrongly cited above as the correct description. This is exactly the rule
> stated in the method note — *a claim that is true only because a feature is
> dormant is FALSE* — applied to the audit's own output.

### F2 — SAFETY. "Watchdogs are unwritable by officers" — no watchdog is germline

**Quoted, as shipped:**
* `README.md` — *"**Germline write-protection:** the policy engine, authority
  matrix, golden evals, **and watchdogs** are unwritable by officers — no loop
  may edit its own judge."*
* `captains-cabinet-guide.md` §5 — *"the policy engine, authority matrix,
  golden evals, graduation math, **the dead-man watchdogs**, the
  courses-of-action rule — are **germline**: write-protected against every
  officer and every loop, enforced at the hook."*

**What is actually enforced.** The germline set is the 73 files + 7 directories
in `cabinet/scripts/germline-lock.sh`. **No watchdog path is in it.** Driving a
`Write` through `cabinet/scripts/hooks/pre-tool-use.sh`:

| target | hook verdict |
|---|---|
| `framework/policies/authority-matrix.yml` | rc=2 BLOCKED |
| `framework/authority/policy_engine.py` | rc=2 BLOCKED |
| `memory/golden-evals/framework/fw-002-spending-limits.sh` | rc=2 BLOCKED |
| `framework/fidelity/graduation.py` | rc=2 BLOCKED |
| `.claude/rules/courses-of-action.md` | rc=2 BLOCKED |
| `framework/watchdog/check.py` | **rc=0 ALLOWED** |
| `framework/watchdog/{__init__,receipts,registry}.py` | **rc=0 ALLOWED** |
| `cabinet/scripts/killswitch-watchdog.py` | **rc=0 ALLOWED** |

The judge plane is held; the **alarm plane is not**. An officer can edit the
watchdog that is supposed to page on its own misbehaviour — including the
killswitch watchdog. This is the "no loop may edit its own judge" principle
holding for judges and failing for alarms.

**Corrected** in both surfaces, which now name the set and say plainly that the
watchdogs are outside it. **The underlying gap is not closed by this branch** —
moving watchdog paths into the germline set changes the germline *set*, which is
a Captain ceremony, not a doc fix. Recorded here as the honest state.

### F3 — SAFETY. "Evidence starvation revokes autonomy" — it pages, and only if configured

**Quoted, as shipped:**
* `README.md` — *"**Evidence starvation revokes autonomy:** a lane whose
  verdicts stop landing is **automatically demoted** and paged."*
* `README.md` — *"a starving ledger (a dead-man watchdog **pages and revokes
  autonomy** when evidence stops flowing)."*
* `captains-cabinet-guide.md` §1 principle 2 — *"Evidence starvation
  auto-revokes autonomy."*
* `captains-cabinet-guide.md` §3 — *"zero verdicts land on the ledger for N
  hours → critical page **AND automatic demotion to propose-only.** Evidence
  starvation revokes autonomy **by construction**."*

**What is actually enforced.** `cabinet/scripts/ledger-liveness-check.py`
contains **no demotion path** — grep for `demot|propose_only|posture|trust.ladder|grants`
returns only its own docstring line, which states the truth the four sentences
above contradict: *"Auto-demote wiring joins when graduation goes live (B2.9+);
until then **the page IS the response**."* Its entire starvation response is
`_ping(fail=True)` → `https://hc-ping.com/$HEALTHCHECKS_PING_KEY/ledger-liveness/fail`.

And the page is **conditional**: `_ping()` returns `"no-ping-key"` and does
nothing when `HEALTHCHECKS_PING_KEY` is unset. That variable is not in the
Quickstart requirements, so on a stranger's fresh hatch a starving ledger
prints one line into a job log and returns 0 — no demotion, no page.

Note the guide's §3 parenthetical *already* said this correctly, ~400
characters after the bold claim that contradicts it. A reader scanning bold
text gets the false version.

**Corrected** in both surfaces.

### F4 — Shipped guide advertises machinery the tree does not contain

**Quoted, as shipped:** `captains-cabinet-guide.md` §6 — *"The canonical work
store is a **local task board** (SQLite; **claim-by-CAS with leases**)."*

**What is actually enforced.** No lease machinery exists.
`git grep -niw 'lease|leases'` over `framework/ cabinet/ presets/ memory/`,
excluding `--force-with-lease`, returns **nothing**. `task-board.sqlite3` and
`lease_until` appear nowhere outside a plan document. The real store is the
append-only org-runtime event ledger (`cabinet/cache/org-runtime.sqlite3`, env
`ORG_RUNTIME_DB`) with `officer_tasks` / `mission_steps` as the task model
(`cabinet/scripts/task_adapters/base.py` docstring); concurrency is a
per-`(context, officer)` WIP cap enforced by a Postgres trigger taking
`pg_advisory_xact_lock` (`cabinet/sql/038-officer-tasks.sql`, spec 038 v1.2
amendment 038.1).

CAS-claim-with-leases was **planned** in
`docs/plans/plan-B-macmini-product-org-2026-07-02.md` (repo-only — `docs/plans/`
archives out of the export, so this path does not resolve in the egg) row B4.11 — 30-minute
leases, 5-minute heartbeats, 15-minute expiry reclaim — and never built. The
export archives `docs/plans/` out, so a stranger reading the egg had no way to
discover that the sentence described a plan. **Corrected.**

### F5 — "Only the Captain can resume, via a typed resume token" — no such token

**Quoted, as shipped:** `captains-cabinet-guide.md` §5 — *"**Only the Captain
can resume it**, via a typed resume token."*

**What is actually enforced.** `resume token` occurs exactly once in the whole
tree: in that sentence. `cabinet/scripts/kill-switch.sh deactivate` takes no
token and authenticates nobody. What actually holds the property is coarser and
worth stating honestly: while the switch is ACTIVE the pre-tool-use hook refuses
**every** tool call from a hooked officer session — verified, `echo hi` → rc=2,
and `redis-cli DEL cabinet:killswitch` → rc=2 — and the two disarm paths
(`kill-switch.sh deactivate`, the dashboard toggle) run outside officer hooks.
A same-uid process outside the hooks can still clear it; that is declared
residual RES-016. **Corrected.**

### F6 — "Model upgrades demote graduated cells" — nothing reads a model baseline

Found by the adversarial re-review, in a sentence this branch had already
rewritten without checking its third clause.

**Quoted, as shipped:**
* `README.md` — *"Demotion is automatic on wrong verdicts, detected fabrication
  **and model upgrades**."*
* `captains-cabinet-guide.md` §3 — *"**Model upgrades demote graduated cells one
  level pending re-proof** — graduation history is stamped with the model
  baseline it was earned on."*

**What is actually enforced.** Nothing.
`git grep -nIiE "model[-_ ]?baseline|model[-_ ]?upgrade|baseline_model"` over
`framework/ cabinet/ presets/ memory/ shared/ instance/` returns **zero** hits,
and `git grep -nIiw model -- framework/fidelity/graduation.py` returns zero:
the graduation math has no concept of a model at all. Evidence events do carry
an R-4 `model_id` (`framework/schemas/evidence-event.schema.json`), so the
*stamp* exists — but no consumer compares it or demotes on a change. Same shape
as F3: designed, disclosed nowhere, shipped as fact. **Corrected** in both
surfaces (marked target-state).

---

## Recorded, not corrected

| # | Claim | Verdict | Why not corrected here |
|---|---|---|---|
| R1 | `SECURITY.md`: *"This repository is **public**."* vs `README.md`: *"This repository is private today."* | Contradiction; `gh repo view` → `isPrivate: true` | The publication state is Captain-gated (CG-7). Editing either sentence asserts a decision that is not mine. |
| R2 | `captains-cabinet-guide.md` links `docs/plans/EXECUTION-STATUS.md` ×3 | Dead in the export | `docs/plans/` is archived out by the manifest's `plans-archive` transform; the link resolves in-repo and 404s in the egg. Same class: `docs/persona-employee-slice-2026-07-26.md` → `cabinet/scripts/cognitive-phase4-review-scope.py` (deleted from the export). |
| R3 | `docs/migration-phase0-baseline.md` → `framework/fw-002-spending-limits.sh`, `framework/fw-019-checkpoint-review.sh` | Stale paths | Both live at `memory/golden-evals/framework/`. Historical migration record; low blast radius. |
| R4 | Watchdogs outside the germline set (F2) | Real gap | Closing it changes the germline **set**, which is a Captain ceremony. |

---

## Claims verified TRUE by execution

Recorded so a later sweep does not re-pay these, and so the coverage claim is
bounded rather than vibes.

| Claim | Surface | How it was executed | Verdict |
|---|---|---|---|
| "CI asserts no ceiling cell can resolve to auto" | README, guide §5 | Mutated `external_comms` to `{"*": always_gated, "graduated": auto}` → `test_matrix_ci.py` went **3 failed** (`MatrixValidationError`); restored → 4 passed | TRUE — sensor is live, fails against the mutation |
| Six ceiling classes always gated | README, guide, governance | `verdicts[rc]` = `{"*": always_gated}` for all six; `hard_ceiling` set == `HARD_CEILING_TOUCHES`, len 6 | TRUE |
| "Designed fail-closed: if the switch's state store is unreachable, work stops" | README, guide §5 | `REDIS_PORT=6399` (nothing listening) → `killswitch-read.sh` rc=11 INDETERMINATE; `pre-tool-use.sh` rc=2, "EMERGENCY STOP UNVERIFIABLE — treating as STOPPED" | TRUE (scope: state-changing tools, MCP, subagents, egress; read + Captain-comms stay open — README now says so) |
| Germline blocks writes to policy engine / matrix / golden evals / graduation math / courses-of-action rule | README, guide §5 | `Write` through `pre-tool-use.sh` → rc=2 on each | TRUE |
| "Delete or corrupt that file and everything drops back to propose-only" (trust ladder) | governance doc | File absent → `current_rung` = `would-like-to`; file = `{{{ not yaml ::::` → still `would-like-to`; `RUNG_VERDICTS['would-like-to']` = `propose_only` | TRUE, both arms |
| Vetoes matched by exact fields, never by paraphrase; no expiry, lift-only | governance doc | `framework/frontdoor/veto_registry.py` — exact field equality, `_clean_scope` chokepoint, monotonic ids, `_is_lifted` the only clear path; no expiry/thaw code | TRUE |
| 48-hour undo window | governance doc, README | `action_undo.py:UNDO_WINDOW_H = 48`; `ttl_expires_at = ts + 48h`; pointer TTL 9d | TRUE |
| "Enforced egress … **off by default**" | README | `egress-guard.sh status` on the cut export → `enforce: false`, `proxy: STOPPED` | TRUE |
| Dashboard binds loopback by default | SECURITY.md | `start-dashboard.sh:55` → `HOST="${…:-127.0.0.1}"` | TRUE |
| `cabinet-init` proposes lanes "with citations" | `.claude/skills/cabinet-init/SKILL.md` | `estate.proposed_lanes` carries `evidence` / `source` / `derived_from` | TRUE |
| Falsifier line appended daily | governance doc | `cabinet/services.yml` `falsifier-daily` / `com.cabinet.falsifier-daily`, one idempotent JSON line/day | TRUE (scheduled) |
| Hatch seeds one labeled DEMO receipt | governance doc | `hatch.sh` step 14 → `emit-demo-receipt.sh` → `instance/memory/demo-receipt.md` | TRUE |
| Export ships no live instance values | README, SECURITY.md | `egg-export.sh` verify pass: all `expect-present`/`expect-absent` rules hold, 254 deletes, 15 transforms | TRUE (as gated by the manifest) |
| Guide's `(target state)` markers on the executor/outbox (phase B4) and the Gate runner (phase B5) | guide §3, §5 | Explicitly marked unbuilt in the shipped text | HONEST — no correction needed |

---

## The pattern worth keeping

Every one of F1–F5 is the same shape: **a ruling moved the code and the
headline sentence stayed.** F1 is the 2026-07-04 earn-demotion inversion. F3 is
graduation wiring that never landed. F4 is a plan row that never landed. F2 is
a set that was never extended. In three of the five, a *different* part of the
same shipped corpus already stated the truth — the governance one-pager for F1,
the guide's own parenthetical for F3, the script's own docstring for F3 — so the
egg was internally inconsistent rather than uniformly wrong.

**The cheap detector this suggests:** for any sentence promising a safety
property, the enforcing code must be reachable from the sentence *and* the
sentence must fail when the code is mutated. F1 and F3 would both have been
caught the day they went stale by asking the sentence "which command proves
you?" — the question this audit asked 26 times.
