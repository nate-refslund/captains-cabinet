# Fidelity Harness (F) — Design

> Authored 2026-06-18. The keystone of the "replace Nate with a digital clone"
> program (decomposition F/A/R/P — see tasks + `docs/clone-convergence-plan-2026-06-09.md`).
> Architecture locked by the Captain 2026-06-18. This doc is the build reference;
> implementation follows via per-phase plans (Corridor `analyzePlan` before any
> code, per house rule).

## North star

Measure how well a cabinet **officer's** decisions match Nate's **endorsed**
judgment, **per (lane × decision-type)**, and turn that measurement into:
1. the **graduation gate** that decides per-cell autonomy, and
2. a **continuous fidelity signal** with drift detection that can *demote* authority.

Without F, autonomy is faith-based. F is the instrument that makes "replace me"
measurable, and therefore safe.

The target is not Nate's raw decision *log* — it is his decision *function*:
his principles and weighting, grounded in history but recency-weighted to
current-Nate and filtered through endorsement labels. "Better than Nate" =
his best self executed consistently, which falls out of scoring against
*endorsed* (not raw) decisions.

**Intent-fidelity, not surface-fidelity (Captain clarification, 2026-06-18).**
The unit of fidelity is the *intent behind* the action — not its surface text,
not even its literal decision. Worked example from the first live run: a Teams
reply that was just a pasted Husqvarna-mower URL is not "share this string" —
the intent was *find a robotic mower with no boundary-wire (LiDAR instead) that
handles the large lawn at the new property*; that link is one
fitting option among few. A faithful clone must therefore **(a) gather the full
context before deciding** — the conversation's real goal *plus* real-world facts
screenpipe already captures (the property and its details) — and **(b) be credited
for a different or even *better* action that serves the same intent** (e.g.
researching and proposing fitting options, that link among them). Two
load-bearing consequences: the officer-under-test must **gather context before
deciding** (brain bridge + screenpipe capture, leak-guarded to the cutoff), and
the judge must score **intent-alignment** — crediting on-intent divergence — not
surface match. **F1 deliberately measured surface-only with a context-starved
officer**, which is exactly why its baseline reads low and is *not* the real
number. **F4 is re-centered on intent-fidelity + full-context gathering** (see
the F-phasing below) — that is where the real fidelity lives.

**Intent is structured: `missions/goals × core` (Captain, 2026-06-18).** An
intention is not free-floating — it is Nate's relevant *mission/goal* expressed
through his *core* (values, voice, behaviour, principles). The clone forms an
action by blending the two: *what am I pursuing here* (the mower for the new
property; shipping PolAds v1) **×** *who I am* (the core — the screenpipe
`nate-model` + voice profile). The officer should gather/recall the relevant
mission-or-goal and reason from the core, then act; the judge scores **that
blend**, not the surface. **Foundation-first:** nail this foundation — a
faithful model of the *core* and the *missions*, and the foundational
principles (business, human psychology, decision-making) the actions rest on —
*before* tool and scoring specifics. Get the foundation right and the specifics
follow; over-index on tools and the clone is a mimic, not a mind. This reframes
every downstream piece (the gathered context includes the active mission/goal;
the intent rubric is `mission × core` alignment; "better than Nate" = the same
core serving the same mission, executed more consistently).

**Layering — the layers are not co-equal (Captain, 2026-06-18).**
*Mission/intention* is the strategic direction (the driver); *values* are the
principles that judge; *behaviour/habits* are the repeated actions that pattern
how Nate executes; *voice* is only the **formulation of the final output** —
the surface phrasing, applied last. Therefore fidelity weights the **substance**
— does the action serve the mission, consistent with values + behaviour — **far
above voice/style.** Concretely, this *inverts* the inherited retrodiction
channel emphasis: the **DECISION/intent channel dominates** the score; the
**STYLE (voice) channel is a light confirmation** that the output is formulated
like Nate; **MECHANICS lighter still.** (This is why the Husqvarna draft's good
Danish voice was never the issue — the gap was the *decision serving the
mission*. A clone with perfect voice and wrong intent is a failure; a clone with
right intent and plain voice is a near-pass that the voice layer finishes.)

**Evidence check + self-corrections (2026-06-18, triangulated research).**
External literature validates intent>surface (behavioral cloning of surface
actions fails under distribution shift; intent/IRL recovers the objective and
generalizes; frontier framing: *behavior underdetermines intention* — target
behavior AND intent, where motivational structure = drives/values/priorities →
intentions → behavior, "inverse constitution learning" recovers values from
behavior). Three corrections that OVERRIDE earlier prose here:
1. **predictive ≠ inferential** — a clone that predicts Nate's *surface output*
   better is NOT necessarily better at *inferring his intent*; optimizing
   surface-fidelity as the target can actively mislead. (So F1's surface baseline
   is not merely incomplete — it is the wrong objective.)
2. **voice is not "just formulation"** — stylometry shows writing style is a
   *behavioral biometric* (identity fingerprint). The scoring still weights
   DECISION/intent over voice, but voice is a **separate authenticity axis**
   (right intent + tone-deaf voice still fails the human) — score the two
   separately, never collapse or dismiss voice.
3. **fitness = intent-served, NOT correction-count** — "minimize Captain
   corrections" is gameable (rewards timidity/avoidance, erodes corrigibility,
   the opposite of replace-me). Fitness = outcome-held + review-confirmed (the
   consequence ledger's positive signal); correction-rate is at most a secondary
   negative, with an explicit corrigibility guard.
Self-improvement mechanism, per the evidence: a **verified, curated learnings
memory + structural gates** (tests, validation-feedback), NOT more injected
rules (curse-of-instructions: compliance decays ~exponentially with instruction
count; context rot ~3k tokens). Bloat actively degrades the very judgment we are
trying to raise.

## Relationship to prior art (reuse, don't rebuild)

The fidelity scorer already exists: `~/.screenpipe/pipes/retrodiction/`
(`lib.py` ~1000 LOC + `run.py` + pytest). It already implements leak-safe
held-out extraction, blind clone-vs-baseline drafting, three-channel scoring
(STYLE = Voyage `voyage-4-large` cosine vs a recency-weighted per-channel
voice centroid; DECISION = a tone-blind Sonnet judge → `match|partial|divergent`;
MECHANICS = deterministic flags), aggregate stats, CUSUM drift, and
`score_draft()` — a ground-truth-free pre-proposal grader **explicitly built
for cabinet officers to call**. Baseline `decision_match_rate` = 0.083
(generic-assistant). **F reuses this scoring engine** (import/port
`extract_cases` / `score_case` / judge / `cusum` / `score_draft`); it does not
re-derive it. F's new work is the six gaps below.

## What F adds (the six gaps = the scope)

1. **Officer-under-test runner** — retrodiction grades the screenpipe drafter
   (`draft_lib`); F drives a **cabinet officer** to decide blind, under the
   courses-of-action rule, via the brain bridge. This is F's core.
2. **Beyond reply-text** — fidelity today is reply-only. F adds the other
   decision-types: triage/prioritization, mission proposals, briefing
   prioritization, board-status calls, course-of-action chains. Monday's
   triage choices are **not captured locally** → F pulls the Monday
   activity-log API + uses scenario elicitation.
3. **Endorsement axis** — score against Nate's *endorsed* call, not raw actual.
   Seed exists (`corrected` tag on `5-Reflections/Decisions/` notes); F wires
   it + grows it via WHY-mining and scenario elicitation.
4. **Consequence-event emitter** — the normalized `(actor, lane, action-class)`
   schema exists (`framework/schemas/consequence-event.schema.json`); the emitter
   is built in `framework/fidelity/consequence.py` (shared infra; F is the
   first consumer) so graduation math is single-source.
5. **Grader hardening** — one judge on one rubric today → ensemble /
   perspective-diverse rubrics + calibration against Nate's own
   `match/partial/divergent` labels.
6. **No-API-key online path** — *resolved by the locked architecture*: Claude
   via OAuth/Code path everywhere; no separate `ANTHROPIC_API_KEY`, no offline
   models.

## Locked architecture

**Cabinet-native fidelity module** (`framework/fidelity/`) that imports/ports
retrodiction's scoring logic. **Claude is reached via the OAuth/Code path in
both tiers** — the judge runs as a `claude -p` headless agent (bills to the Max
pool; runs in GitHub Actions for the server flavor via
`CLAUDE_CODE_OAUTH_TOKEN`). **One non-Claude dependency is kept**: Voyage
embeddings for the STYLE channel (a hosted embedding API already used by the
brain index — not an "offline model"; style-similarity is the wrong job for an
LLM).

**Two tiers — split for cost, not keys:**
- **Offline batch evaluator** (periodic / cron / CI): the deep, ensemble-judged
  run over held-out cases that produces the per-cell fidelity matrix and feeds
  the graduation gate. ~24+ cases per cell per run — modest volume, quota- and
  ToS-clean.
- **Online gate** (per officer action, hot path): reads the *precomputed* per-cell
  score + a cheap, ground-truth-free `score_draft()` check. **No LLM judge in
  the hot path** (quota + latency). Decides propose-vs-act per the authority
  matrix (track A).

**The unified control loop — F builds three of its four faces:**
*measure judgment* (F scorer) → *record consequence* (F emitter → the ledger) →
*gate authority* (online gate → policy engine, track A) → *policy* = the
authority matrix (track A). `outcome-system-self-001` (policy engine
shadow→enforcing) is the enforcement seam.

## Components (isolated units)

Each unit: **purpose · interface · depends-on.** All live under
`framework/fidelity/` unless noted.

### 1. `benchmark.py` — held-out case builder
- **Purpose:** produce/refresh the evaluation set per (lane × decision-type):
  `Case{case_id, lane, decision_type, situation_ref, ground_truth,
  endorsement, cutoff_ts, source, held_out: bool}`.
- **Interface:** `build_cases(lane, decision_type, n, window) -> list[Case]`;
  `refresh()`.
- **Depends-on:** retrodiction `extract_cases` (reply cases); `connectors/`
  (below); the elicitation dataset; the brain bridge for context refs.
- **Sources per decision-type:** reply ← retrodiction extract over
  `3-People/*/conversations.md`; approval ← `state/gate_decisions.jsonl`;
  triage/prioritization ← **Monday activity-log connector** (new);
  rationale-gold ← `5-Reflections/Decisions/`; thin/novel cells ← elicitation.

### 2. `connectors/monday_activitylog.py` — the uncaptured decision source
- **Purpose:** reconstruct Nate's triage/prioritization *choices* (priority set,
  item declined, status moved) from the Monday activity-log API — the one
  decision-type with no local ground truth.
- **Interface:** `pull_actor_decisions(board_id, actor, since) -> list[Decision]`.
- **Depends-on:** Monday API (read-only); the dev-tasks plugin's existing auth.
- **Note:** read-only; no writes to Monday from the harness.

### 3. `officer_runner.py` — the officer-under-test driver (F's core)
- **Purpose:** for each Case, drive the production officer (Chair / lane-CEO) to
  decide **blind** — context reconstructed as-of `cutoff_ts`, under the
  courses-of-action rule, via the brain bridge — in a sandboxed eval mode with
  **no side effects** (drafts are captured, never queued/sent; no board writes).
- **Interface:** `run_case(case, officer_role) -> OfficerDecision{decision,
  rationale, chain}`.
- **Depends-on:** the officer session path (OAuth `claude -p` / eval-mode
  session); the brain bridge with the **leak guard** (§ anti-leakage); A's
  authority context (read-only here).

### 4. `scorer.py` — endorsement-adjusted scoring (wraps retrodiction)
- **Purpose:** score `OfficerDecision` vs `ground_truth` across channels, then
  endorsement-adjust.
- **Interface:** `score(case, officer_decision) -> CaseScore{style_win,
  decision_verdict, mechanics_flags, endorsement_adjusted, composite}`.
- **Channels:** STYLE (Voyage vs voice centroid; text decisions only) ·
  DECISION-MATCH (judge, **new per-decision-type rubrics** beyond replies) ·
  MECHANICS (deterministic).
- **Endorsement adjustment:** if `endorsement ∈ {regretted, constrained}`, score
  against the *endorsed direction* (from the correction / WHY), not the raw
  actual; if `{endorsed, unknown}`, score against actual.
- **Grader hardening:** ensemble of N judges / perspective-diverse rubrics;
  ensemble split → flag `needs_nate_label` (don't auto-score); calibrate the
  ensemble against Nate's own labels.
- **Depends-on:** retrodiction `score_case` / judge; Voyage; the calibration set.

### 5. `consequence.py` — the missing emitter (shared infra)
- **Purpose:** emit `consequence-event` records (existing schema) from (a) F eval
  runs and (b) **live** officer actions (`proposal.decision` from the gate,
  `outcome.status`, `review.verdict`). Makes graduation single-source.
- **Interface (built):** `emit_consequence(**fields)` + `validate_consequence(event)`
  + `read_ledger(since)` + `compute_ratios(since) -> {(actor,lane,action): GraduationRatios}`
  in `framework/fidelity/consequence.py`. Append-only JSONL only, distinct
  filename family `consequence-events-YYYY-MM-DD.jsonl` (never collides with
  events/emitter.py's `events-*.jsonl` in the same dir). Validation is
  hand-rolled (no `jsonschema` dep on system Python 3.9.6); Postgres deferred
  until a consumer needs it.
- **Depends-on:** the schema; the event store.

### 6. `aggregate.py` — fidelity matrix + drift (wraps retrodiction)
- **Purpose:** roll case scores into per-(lane × decision-type) cell metrics over
  a rolling window (`decision_match_rate`, `partial_rate`, `divergent_rate`,
  `style_win_rate`, `mechanics_fail_rate`, `sample_count`) + CUSUM drift per cell.
- **Interface:** `compute_matrix(window) -> dict[cell, CellStats]`.
- **Depends-on:** retrodiction `aggregate` / `cusum`; the consequence ledger.

### 7. `graduation.py` — per-cell autonomy state (mirrors `autonomy_lib`)
- **Purpose:** per cell, read the ledger's three ratios (approval-unchanged,
  outcome-held, review-confirmed) + the fidelity matrix + sample-count +
  clean-streak → an autonomy recommendation. **Thermostat:** drift spike /
  divergent cluster / colleague-friction event flips a graduated cell back to
  propose-only and files a finding.
- **Interface:** `evaluate(cell) -> {state: propose_only|eligible|graduated|
  demote, evidence}`.
- **Bar (Captain-ratifiable defaults):** `match_rate ≥ 0.85`, `samples ≥ 20`,
  `≤ 1 divergent in last 10`, `recency-clean ≥ 14d`, no active drift alarm —
  **per decision-type** (irreversible types carry a higher bar or never auto,
  per the authority matrix). Mirrors the screenpipe `autonomy_lib` 15/90/14
  ramp; reconciled to one bar in track A.
- **Depends-on:** `aggregate.py`; the ledger; A's authority matrix.

### 8. `gate.py` — the online per-action check (hands to A)
- **Purpose:** in the officer hot path, read the precomputed cell state + run a
  fast `score_draft()` pre-proposal check, and return propose / act /
  act-with-veto-window per the authority matrix.
- **Interface:** `decide(officer, lane, action_type, draft) ->
  {verdict: act|propose|veto_window, reason}`.
- **Depends-on:** `graduation.py` output (precomputed); retrodiction
  `score_draft`; track A's policy engine (`fidelity_gate` policy type).

### 9. `elicitation/` — Nate-facing scenario + WHY battery
- **Purpose:** (a) fill thin cells (decision-types with little captured ground
  truth — esp. triage), (b) produce a held-out set the clone cannot have
  memorized, (c) label decisions with endorsement + the WHY (principle).
- **Modes:** **scenario battery** — present a real-or-synthetic situation per
  (lane × decision-type), capture Nate's decision + rationale → held-out
  benchmark + endorsement-labeled gold; **WHY-mining** — sample divergent
  harness cases (reuse retrodiction `divergence_questions`) + the
  `decisions-capture` format, ask "what made your call right / would you redo
  it?" → endorsement label + principle.
- **Interface:** delivered via the brain bridge `ask_nate` (Telegram) and/or a
  dashboard surface; persisted as a **labeled dataset kept OUT of the embeddings
  index** (held-out integrity).
- **Depends-on:** brain bridge; the benchmark store.

## Data flow (the closed loop)

1. `benchmark.py` (+ `connectors/`, `elicitation/`) builds the held-out case set
   per cell.
2. `officer_runner.py` drives officers blind over the cases (OAuth Claude,
   leak-guarded).
3. `scorer.py` scores each (endorsement-adjusted, ensemble).
4. `aggregate.py` → fidelity matrix + drift.
5. `consequence.py` emits events; `graduation.py` reads the ledger → per-cell
   autonomy state.
6. `gate.py` reads that state per action → propose / act / veto-window via A.
7. Divergent cases → `elicitation/` WHY questions → endorsement labels +
   principles → better benchmark **and** the clone learns the principle
   (drafting-lessons / nate-model patterns).

`measure → record → gate → (divergence) → elicit → improve → measure.`

## Anti-leakage (sacred)

- The officer sees **nothing timestamped ≥ `cutoff_ts`**: no brain/embeddings
  search returning the held-out reply, no draft-outbox, lessons date-filtered,
  commitments omitted — same protocol retrodiction proves with
  `test_cutoff_no_post_reply_leakage`.
- The **held-out / scenario set is kept out of the embeddings index** and is
  human-authored; the system never reads it during "training" and never
  generates its own held-out cases.
- Documented accepted leaks (current-state priors: person-intel, voice,
  nate-model, centroid) inflate equally across runs → trend stays valid;
  re-audited per phase.

## Privacy fence

`nate_model` / `voice` / `0-Self` inform scoring but **never egress** — never
quoted into any officer output, draft, commit, Notion page, group post, or web
call (`.claude/rules/brain-bridge.md`). `0-Self` is already excluded from the
embeddings index and is reachable only via `me_signal` — F reads it directly
there for scoring, never via brain search. Quote caps mirror retrodiction's
`lib._q` (80-char).

## Error handling / safety

- Anti-leakage failure → **hard-fail the case** (never silently score a leaked
  case).
- Ensemble judge split → mark `needs_nate_label`; route to calibration; do not
  auto-score.
- OAuth/quota exhaustion → batch eval backs off + retries; **never blocks the
  officer hot path** (the online gate uses precomputed scores).
- **No-silent-caps:** a cell with no/low ground truth **cannot graduate** and is
  surfaced (not skipped) — "unmeasured" is a visible state, not a pass.
- Thermostat: any false-positive block or bad live call demotes the cell + files
  a finding (ramp-down is designed, not just ramp-up).

## Testing / eval plan

- **pytest per module** (mirror retrodiction's suite): leak-guard, scorer
  determinism (mechanics), endorsement-adjustment logic, graduation math,
  consequence-event schema validation, demotion triggers.
- **Calibration set:** a Nate-labeled `match/partial/divergent` set to validate
  the judge ensemble (the grader-hardening gap).
- **Golden evals** (`memory/golden-evals/`): "a leaked case is rejected", "an
  unmeasured cell cannot graduate", "a divergent cluster demotes a graduated
  cell".
- **Bootstrap validation:** run F against the existing **176 paired**
  `autonomy_outcomes.jsonl` rows + the retrodiction baseline (0.083) to prove the
  officer-runner produces sane scores before any gate trusts it.

## F-internal phasing (for the implementation plan)

- **F0** — `consequence.py` emitter + ledger reader (shared infra; unblocks all)
  — **built**: `framework/fidelity/consequence.py`
  (`emit_consequence`/`validate_consequence`/`read_ledger`/`compute_ratios`,
  `GraduationRatios`).
- **F1** — `officer_runner.py` + `scorer.py` over the **reply** cell; validate vs
  the 176 paired set + baseline.
- **F2** — `aggregate.py` + drift + `graduation.py` (reply cell first).
- **F3** — broaden decision-types: Monday activity-log connector (triage),
  approval axis (gate ledger), proposal/board-status; new judge rubrics.
- **F4** — endorsement axis: wire the `corrected` tag + elicitation labels into
  scoring.
- **F5** — grader hardening (ensemble + calibration).
- **F6** — online `gate.py` + authority-matrix integration (hands to track A).
- **F7** — `elicitation/` battery (scenario + WHY), Nate-facing.

Each phase: Corridor `analyzePlan` before code · worktree-isolated build ·
review (security / correctness / conventions) · tests green.

## Open decisions for Captain ratification

1. **The numeric graduation bar** per decision-type (defaults proposed above).
   Reconciled with the screenpipe 15/90/14 ramp in track A's authority matrix.
2. **Elicitation cadence + volume** — how many scenario cases per cell, how often
   WHY-mining runs (your "huge questionnaire" offer sizes this).
3. **Decision-type taxonomy** — the exact cell list per lane (reply, triage,
   proposal, board-status, deploy-call, course-of-action … per polads /
   stephie-stepnetwork / system-self).

## Risks (mitigations in-design)

1. **Officer eval ≠ production officer** (eval mode drifts from real path) →
   officer_runner uses the *same* prompt + brain-bridge path, eval-only
   difference is the leak guard + no-side-effects.
2. **Judge bias / single-rubric** → ensemble + Nate-calibration (F5).
3. **OAuth quota contention** (eval vs officers vs interactive on one Max pool) →
   batch eval is modest + periodic + backoff; hot path never judges.
4. **Cloning the average self** → endorsement axis (F4) + held-out scenario set.
5. **Thin/absent ground truth** (triage) → Monday activity-log + elicitation;
   unmeasured cells can't graduate (fail-safe).
6. **Held-out leakage** → out-of-index storage + cutoff guard + per-phase audit.
