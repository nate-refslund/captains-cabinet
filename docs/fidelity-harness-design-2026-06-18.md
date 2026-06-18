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
   schema exists (`framework/schemas/consequence-event.schema.json`) but has no
   emitter. F builds it (shared infra; F is the first consumer) so graduation
   math is single-source.
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
- **Interface:** `emit(event)`; validates against the JSON schema; append-only
  JSONL + (optionally) Postgres, mirroring `framework/events/emitter.py`.
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

- **F0** — `consequence.py` emitter + ledger reader (shared infra; unblocks all).
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
