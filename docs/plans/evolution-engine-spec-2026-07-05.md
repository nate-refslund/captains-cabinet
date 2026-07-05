# Evolution Engine — Phase-2 Spec of Record (2026-07-05)

**Status:** Captain-ratified direction (captain-decisions.md 2026-07-05 "FOUNDATION-FIRST + EVOLUTION ENGINE GO"); build starts AFTER sovereign v1 integrates and the three-stream reconciliation pass (§6) is green.
**Adopts:** `docs/plans/cabinet-rapid-self-improvement-addendum-2026-07-05.md` — with the four corrections in §1.
**Builds on:** sovereign v1 (`docs/plans/sovereign-build-spec-2026-07-04.md`) — the Gate (SOV-8), Ring-0 (`framework/policies/immutable-core.yml`), verdict_gate (SOV-7), needs ledger (SOV-1), posture matrix (SOV-2/3); the sim harness (A8 as-of fences, `verdict_sim` quarantine, fence_lib); B2 probes/verifier.

## §0 — Goal restated (Captain, 2026-07-05)

The target artifact is the **framework** — the world's best foundational AI org / personal agent, for ANY captain, in EITHER flavor. Nate's deployment is the first instance and the proving ground, not the product. Consequences:

- Everything in this spec lands under `framework/` with zero launcher-specific assumptions; launcher specifics enter only through `instance/` config and source adapters.
- Every evaluator, benchmark miner, and fitness function is written against framework schemas (consequence ledger, org_events, probes, undo journal) — never against Nate's vault layout, screenpipe paths, or Monday board IDs. Where today's code violates this (known: screenpipe_adapter imports, Monday creds from `~/.screenpipe`, vault paths in run_action_lane), the violation is *worked around via adapter seams now* and *queued as migration needs* — not silently re-baked into new code.
- The doctrine in one line: **boundless lab, bounded deployment, universal substrate.**

## §1 — The four corrections to the addendum (Captain-presented, ratified)

1. **Ring-0 stands.** The "boundless inner loop" runs *inside* Ring-0 limits: the league may mutate prompts, skills, retrieval/memory policies, role definitions, tool routing, eval tactics — it may NEVER mutate the Gate, the holdout generator (§3), killswitch, germline-lock, grants registry, posture selector, or the hard-ceiling list. `gate.ratify` (SOV-8) already refuses Ring-0 diffs; the league submits through the same Gate. No second promotion path.
2. **Text genome first, architecture search earned.** Waves E1–E3 evolve the *text genome* (prompts / skills / retrieval / memory policies / model routes). Architecture search (officer counts, role graphs, delegation topologies — ADAS-style) is gated behind an explicit criterion: the benchmark factory has ≥3 generations of holdout stability (champion gains on public suites reproduce on frozen holdout within a stated tolerance) — i.e., we've shown the evaluators can't be Goodharted before we spend combinatorial compute on them.
3. **Frozen holdout + probe-dominant fitness.** The hidden holdout suite is authored by a **frozen, separately-versioned generator** (`framework/evolution/holdout_gen.py`, Ring-0-adjacent: listed in `immutable-core.yml`, league-invisible, mutable only via Captain unlock). Fitness = weighted sum where **real-world machine outcomes (CI, deploy, Sentry, undo/TTL survival, probe verdicts) strictly dominate LLM-judged evals**; an LLM-judge score can rank candidates but can never promote one on its own.
4. **Launcher genericization is core scope** (this ruling) — §4 Wave E4 is a first-class lane, not deferred productization.

## §2 — Architecture (the addendum's six planes, mapped onto what exists)

| Plane | Addendum name | Implementation | Status |
|---|---|---|---|
| 1 | World & trace | consequence ledger + org_events + undo journal + probe logs (existing) | live; hygiene gaps in §5 |
| 2 | Benchmark factory | NEW `framework/evolution/bench_factory.py` + `holdout_gen.py` (frozen) | build |
| 3 | Candidate generator | NEW `framework/evolution/generator.py` (patch/config candidates over the text genome) | build |
| 4 | Arena | **the sim harness** — worktree isolation, A8 as-of fences, `verdict_sim` quarantine, no live creds, mocked externals | exists; needs a league driver |
| 5 | Archive | NEW `framework/evolution/archive.py` (lineage, scores, failures preserved) — extends SOV-8's variant archive | build |
| 6 | Promotion membrane | **the Gate** (SOV-8 `gate.ratify`) + authority matrix promotion sources (§5.1) | exists post-v1 |

New package: `framework/evolution/` — `archive.py`, `candidate.py`, `generator.py`, `arena.py`, `scorers.py`, `bench_factory.py`, `holdout_gen.py` (frozen), `league.py` (orchestrator), `promote.py` (thin shim → gate.ratify; no bypass).

## §3 — Fitness & anti-Goodhart contract

- Every generated eval carries: source trace id, cutoff time (fence-compatible), expected behavior, allowed tools, scorer id, split (public|private|holdout), leakage constraints, promotion eligibility.
- Splits: **public** (league trains against), **private** (league sees scores, not cases), **holdout** (frozen generator; league never sees cases OR per-case scores — only pass/fail at promotion time).
- `graduation-credit:false` rows (test-only diffs, probe_ci) are excluded from promotion ratios — already stamped, must be honored in `compute_ratios` (§5.2).
- Promotion rule: champion must beat incumbent on public AND private, not regress holdout, pass all golden evals + falsifier corpus, and — for any candidate touching action policy — show probe-verified outcome improvement, not just judge preference.

## §4 — Build waves (each = one workflow, sequenced)

- **E0 · Reward-signal hygiene** (immediately after sovereign v1 merges; ~1 lane-day): `review.source` into consequence-event schema; universal `action_type` stamping on propose-only cards; honor `graduation-credit:false`; per-lane promotion sources **as an authority-matrix key** (`promotion_sources` per risk class — one enforcement story, never a fourth config file); schedule B2 probes + verifier + undo-sweep from `services.yml` with healthchecks (kills the "reward functions sitting dark" defect).
- **E1 · League MVP**: archive + candidate + arena driver over the sim harness + league loop; 20 prompt/retrieval candidates vs existing fidelity/scenario evals; ranked archive; **no live promotion**. Proves search works.
- **E2 · Benchmark factory**: mine consequence events, undo reversals, human edits/rejects, probe outcomes, injection attempts into living public/private suites; holdout_gen frozen + Ring-0-listed; per-launcher preference evals seeded from onboarding answers (generic mechanism, Nate = first dataset).
- **E3 · Skill & memory evolution**: skill induction upgraded from skeletons to candidate-procedure search (cluster → generate → replay/sim → mutate → promote via Gate); memory policies (retrieval/summarization/decay/trust) as candidates scored by downstream task performance. Skills gain status lifecycle (candidate/tested/active/deprecated/failed) — extends the SOV-8 skill auto-promote wire.
- **E4 · Launcher foundation** (parallel with E2/E3): source-map + adapter seams so framework/ imports zero Nate paths (screenpipe/vault/Monday behind `framework/sources/` interfaces with instance-bound adapters); cabinet-init extended to generate goal model, risk posture, seed preference cases, initial benchmark suite, source map; framework CI gains a **clean-room test**: full suite green on a bare instance with no personal sources present.
- **E5 · Champion auto-promotion** (needs E1+E2 stable + correction-2 criterion): prompt/retrieval/skill champions auto-promote through the Gate in sovereign posture; machine-verifiable product policies promote on probe evidence; architecture search unlocks only per correction 2.

## §5 — Reconciliation pass (BEFORE E0 code — the three-stream collision)

Three concurrent streams hold opinions on the same files: sovereign build (feat/sovereign-posture), guardian doctrine wave (feat/fidelity-harness-design @ e97479d3), and the addendum's hygiene list. One agent reconciles, in this order, before any E0 edit:
1. `consequence.py` promotion semantics — sovereign's `verdict_gate` (posture-gated) vs doctrine wave's demote-wire vs addendum's per-lane `promotion_sources`. Target: matrix-keyed promotion sources; `verdict_gate` becomes one source among them; guardian behavior byte-stable.
2. Proposal stamping — doctrine wave's widen-act-first stamping vs addendum §4 universal stamping; dedupe into one contract.
3. Probe/verifier scheduling — addendum §7 nervous-system rows vs existing INSTALL-flip LaunchAgents vs services.yml manifest doctrine; land as services.yml rows (one manifest).

## §6 — What stays true from tonight's rulings

Standing grants + needs ledger + ACT-AND-DRAFT (external = per-item approval, structurally non-grantable) + Ring-0 + guardian-byte-identity are **invariants of the platform**, not Nate-instance quirks: they are exactly the deployment membrane that lets any captain run the lab at full speed. The league never bypasses the Gate; the Gate never edits itself; demote always narrows; evidence beats posture — in every posture, for every launcher.
