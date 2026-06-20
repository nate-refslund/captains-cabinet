# Decision cell (F3-intent) design — 2026-06-20

The reply cell measures VOICE (re-baseline confirmed: vault context didn't move
it). "Replace Nate as Head of Tech" is **decisions** — judgment calls with a
WHY. This is the decision-cell design: measure intent-fidelity where it maps to
*doing the job*.

## Data reality (decided the cell shape)
Two ground-truth sources exist; neither is a robust baseline yet:

| Source | N | Shape | Verdict |
|---|---|---|---|
| `inbox-triage` (autonomy_outcomes.jsonl) | 924 | binary keep/archive, 78/22 skewed, `match=True` 100% (backfill artifact), single batch timestamp | shallow attention-classifier; NOT time-fenceable; weak intent |
| `5-Reflections/Decisions` corpus | 16 | rich: `## Situation` + `## Why (Nate)`, real `detected_at`, true judgment calls | the right INTENT surface, but all from ONE day (2026-05-28) |

**Choice: build on the decisions corpus** (intent-aligned, leak-fenceable via
real timestamps, carries the WHY). inbox-triage is parked as a future high-N
*attention-triage* metric (scored honestly vs the 78% always-archive base rate),
not the intent cell.

**Honest caveat, stated up front:** 16 one-day cases is a PIPELINE PROOF +
directional read, NOT a robust baseline. The genuine next foundation step is
growing decision ground truth (mine Monday activity-log transitions, commitment
closures, the agent reasoning log; or capture it live via shadow-drafting). The
cell is built so it ingests more cases the moment they exist.

## Cell structure (reuses the reply-cell machinery)
1. **Extractor (one-time, LLM, cached, leak-guarded).** Each note →
   `{dilemma, nate_decision, nate_why}`. The `## Situation` text fuses the
   situation with Nate's choice ("you greenlit…"); the extractor splits them so
   the `dilemma` states the decision point WITHOUT revealing the choice. A
   leak-scan asserts `nate_decision`/`nate_why` tokens do not appear in
   `dilemma` before a case is admitted (mirrors the reply cell's scan).
2. **DecisionCase** `{case_id, detected_at (cutoff), app, dilemma,
   ground_truth={decision, why}}`.
3. **Runner.** Clone sees `dilemma` + **values-identity** (voice + nate_model
   patterns + drafting lessons date-filtered strictly before `detected_at`) and
   proposes `{decision, why}` AS NATE'S CLONE, privacy-fenced (reuses
   `_CLONE_PRIVACY_FENCE` + the `BrainAdapter` identity gather). It NEVER
   receives `decision`/`why`. **No person-anchored vault gather in v1:** these
   dilemmas have no single counterparty, and `context_lib.gather` is
   person-anchored — so the *dilemma itself* carries the situational facts (the
   extractor keeps every fact needed to decide, minus the choice), and the
   call is driven by Nate's values-identity. Vault/topic gather for decisions is
   a v2 enrichment (needs a topic-anchor strategy), kept out per YAGNI.
4. **Scorer.** The INTENT judge (already built) scores: does the clone's
   decision serve the same intent as `nate_why`? Two axes — `decision_match`
   (surface: same call?) and `intent_match` (primary: same WHY/goal?). A
   generic-assistant baseline (no identity) is the contrast, as in the reply cell.

## Leak-safety
- Cutoff = `detected_at` (real). gather fenced as-of-then (content_ts), same as
  reply cell. Clone identity (voice/patterns/lessons) injected to SYSTEM only,
  never echoed (post-output scan).
- The extractor is the new leak surface → its dilemma output is scanned for the
  held-out decision/why tokens; any bleed drops the case (never silently scored).

## Scope (YAGNI)
Build: extractor (cached JSON), DecisionCase + builder, decision runner, decision
scorer, tests (stubbed-LLM deterministic + a live smoke). REUSE: gather,
leak fence, clone identity, intent judge, baseline contrast. Do NOT build: the
inbox-triage connector, a decision-corpus grower, or F5 ensemble — those are
follow-ons gated on this proving out + more data.
