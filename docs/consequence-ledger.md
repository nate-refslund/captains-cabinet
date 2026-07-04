# Consequence Ledger — one event shape for every acting surface

> Schema: `framework/schemas/consequence-event.schema.json` (JSON Schema
> 2020-12). Adopted in R3 of the convergence roadmap
> (`docs/clone-convergence-plan-2026-06-09.md`). Universal: the shape carries
> no deployment specifics — lanes, actor ids, and refs are instance data.

## Why this exists

The estate already records what its agents do — but in **heterogeneous,
unqueryable shapes**. An audit of the existing outcome records found
**1,182 mixed-schema rows** across the perception side's ledgers alone:
reasoning entries, gated-decision rows, silent-shadow rows, and triage rows
each carry different keys, and the cabinet's `org_events` adds a fifth shape.
Nothing can answer, in one query, the questions graduation actually needs:

- *How often was this actor's proposal approved unchanged vs. edited vs.
  rejected?*
- *Of the actions that executed, how many held vs. broke?*
- *Of the expectations recorded, how many did the reviewer confirm vs. mark
  wrong?*

Graduated autonomy is **evidence math over exactly those three ratios**.
A ledger that can't be queried can't graduate anyone. The consequence
ledger fixes this with ONE normalized event per action, shared by
screenpipe pipes, cabinet officers, and crew subagents.

## The event shape

```json
{
  "ts": "2026-06-10T08:00:00Z",
  "actor": {"kind": "pipe | officer | crew", "id": "<stable id>"},
  "lane": "<context slug or null>",
  "action": "drafted-reply",
  "action_type": "internal_message | external_message | local_edit | ... | null",
  "subject": "thread:abc123",
  "refs": ["msg:1", "board:42"],
  "proposal": {"required": true, "decision": "approved | edited | rejected | expired | null", "decided_at": "..."},
  "outcome": {"status": "ok | failed | unknown", "evidence": "..."},
  "review": {"verdict": "confirmed | wrong | unknown", "reviewed_at": "...", "lesson_ref": "..."},
  "decision_verdict": "match | partial | divergent | error | skipped | null",
  "intent_verdict": "intent-aligned | intent-partial | intent-divergent | error | '' | null",
  "intent_composite": 0.0,
  "endorsement": "unknown | regretted | constrained | corrected | null",
  "sim": true
}
```

The four scorer-axis fields (`decision_verdict` … `endorsement`) are the
optional **F4 scorer-axis fields** `[T3]` — absent on non-eval acting surfaces
and legacy rows (the unmeasured default; a real falsy value like
`intent_verdict: ""` or `intent_composite: 0.0` is written, an unpassed field
is dropped). They are stamped by the F4 scoring-path emit
(`framework/fidelity/fidelity_events.py:emit_case_scored`) from a scorer
`CaseScore`. `additionalProperties: false` still holds at every level.

`sim` `[SIE-7]` is the **replay-simulation quarantine marker** — present-and-true
ONLY on events emitted under `CABINET_SIM_MODE=1`, never written as `false`. The
single write chokepoint (`_write_to_log`) enforces that the marker agrees with
the target dir's `-sim` suffix: a `sim:true` row can land ONLY in a `-sim` event
dir and a non-sim row NEVER lands there, so simulated consequences can never
contaminate the live graduation / breaker / cell math Nate's real verdicts feed.
`read_ledger` additionally drops sim rows for live consumers (defense in depth).
This is what lets ~100 replay simulations run against years of history in
parallel with — and fully isolated from — the live estate.

One event = one action, written when the action happens and **enriched in
place** (or superseded append-only, see Storage) as its consequence
resolves:

1. **Act** — actor emits the event with `ts/actor/lane/action/subject/refs`,
   plus `proposal.required` (and `decision: null` while the gate is open).
   The optional `action_type` enum field [FIX-1] is stamped at emit time by
   the shared `framework/authority/classifier.py:classify_action()` — the SAME
   classifier the authority-matrix gate reads — so the ledger and the verdict
   table agree on what each action *is*. It is left ABSENT (the unstamped /
   unmeasured default) when no classifier-derived value is supplied; the enum
   mirrors `classifier.ACTION_TYPES` exactly (CI-asserted, no drift).
2. **Decide** — when the human gate resolves, `proposal.decision` +
   `decided_at` land. `edited` is approval *with corrections* — it counts
   against graduation exactly like the perception side's edited-draft signal
   today. `expired` means the proposal aged out into a briefing unanswered.
3. **Resolve** — `outcome.status` flips from `unknown` to `ok`/`failed`
   from HARD signals (sent message bounced or held, deploy verified or
   rolled back, board item stayed closed or was reopened), with `evidence`.
4. **Review** — the existing reasoning-review / architect loop compares the
   action's expectation to reality and writes `review.verdict`
   (+ `lesson_ref` when `wrong`).
5. **Score (F4 eval) `[T3]`** — for a held-out fidelity case, the scoring path
   emits a distinct `fidelity-case-scored` event carrying the scorer's
   `decision_verdict` / `intent_verdict` / `intent_composite` / `endorsement`
   AND maps `review.verdict` FROM the intent verdict
   (`intent-aligned→confirmed`, `intent-divergent→wrong`,
   `intent-partial / error / ""→unknown`). This is the seam that makes
   `review_confirmed_rate` measurable for scored cells — before it, every scored
   case landed `review.verdict: unknown` so the bar's denominator was 0 forever.

## Mapping the existing sources

The three live record families map onto the shape without information loss.
Field names below are the sources' actual keys.

### 1. screenpipe `agent_reasoning` log (jsonl + daily markdown)

Source shape: `{ts, pipe, action, subject, rationale, expectation, ref,
reviewed}` — written by `agent_reasoning.log(action, subject, rationale,
expectation, pipe, ref)`; reviewed every 12h by reasoning-review, which
writes confirmed/wrong/unknown verdicts and consequence lessons.

| source field | consequence event |
|---|---|
| `ts` | `ts` |
| `pipe` | `actor` → `{kind: "pipe", id: <pipe>}` |
| `action` | `action` |
| `subject` | `subject` |
| `ref` | `refs[0]` |
| `rationale`, `expectation` | stay in the reasoning log (the review *inputs*); the reviewer's verdict lands here as `review.verdict` |
| `reviewed` + reviewer output | `review.{verdict, reviewed_at, lesson_ref}` (lesson_ref → the lessons file anchor) |

What's gained: reasoning entries today have **no proposal or outcome
fields at all** — a drafted reply and a silent auto-close look identical.
Mapped events make the gate (`proposal`) and the consequence (`outcome`)
first-class.

### 2. screenpipe autonomy ledger (`autonomy_outcomes.jsonl`)

Three row shapes share that file today:

- **Gated decisions** `{ts, lane, action_id, decision: accepted|edited|skipped,
  content_hash, blast, rung, goal, outcome: pending→held|broken, resolved_ts}` →
  `proposal.required: true`, `decision` maps `accepted→approved`,
  `edited→edited`, `skipped→rejected`; `outcome` maps `held→ok`,
  `broken→failed`, `pending→unknown`; `action_id` → `subject`,
  `content_hash` → `refs[]`.
- **Shadow rows** `{ts, lane, action_id, mode: shadow, would_text,
  <captain>_text, match, resolved_ts}` → a shadow is an action that was
  *not* surfaced: `proposal.required: true, decision: null`; resolution
  maps `match: true→review.verdict: confirmed`, `match: false→wrong` (the
  captain's real action is the ground truth the would-action is scored
  against; the source names its captain-decision fields after the captain).
- **Triage proposals** `{ts, action_id, subject, sender, proposed,
  <captain>, match}` → `action: "proposed-triage"`, `proposal.decision`
  from the captain's confirmation, `review.verdict` from `match`.

`blast`/`rung`/`goal` are autonomy-engine internals; they remain in the
source row and travel as a `refs[]` pointer, not as schema fields — the
consequence event stays minimal and shared.

### 3. cabinet `org_events`

Source shape: `{event_id, event_type, product_slug, aggregate_type,
aggregate_id, actor, source, payload, supersedes_event_id, created_at}`.
`org_events` stays the cabinet's **full organizational ledger** (missions,
roles, hats, policy decisions — most of which are not "an action on the
captain's world"). The consequence ledger is the *behavioral subset*: when
an officer or crew agent takes a gated or consequence-bearing action
(queue a draft, close a board item, deploy, nudge), it emits ONE
consequence event whose `refs[]` carries the `org_events` `event_id` for
drill-down. `product_slug` → `lane`; `actor` → `{kind: "officer"|"crew",
id}`. Nothing is removed from `org_events`; the consequence event is the
normalized projection the graduation math reads.

## Storage and access

- **Append-only JSONL**, one file per estate side, both conforming to the
  same schema: the perception side writes alongside its existing state
  files; the cabinet writes under its durable event-log dir
  (`CABINET_EVENT_LOG_DIR`) using the distinct filename family
  `consequence-events-YYYY-MM-DD.jsonl` (never collides with the
  `events-*.jsonl` org_events ledger `framework/events/emitter.py` writes in
  the same dir). Enrichment (decision/outcome/review landing later) is an
  appended superseding event carrying the same
  `actor + action + subject + ts` identity — consumers take the last
  write per identity, the same convention the autonomy resolver uses
  today. The cabinet read path `read_ledger` collapses that identity tuple
  last-write-wins; `compute_ratios` derives the graduation ratios per
  `(actor, lane, action_type)` cell (→ `GraduationRatios`: approval-unchanged,
  outcome-held, review-confirmed, and `[T3]` `intent_match_rate` =
  `intent-aligned / (intent-aligned + intent-divergent)`, `None` when the
  denominator is 0) — keyed on the
  `action_type` enum (the shared classifier's stamp), NOT the free-text
  `action`, so the ledger and the authority gate agree on the cell. A row with
  no `action_type` (unstamped/legacy) buckets under the visible
  `__unstamped__` sentinel rather than its free-text action, so unstamped noise
  can never conflate into a measured cell (fail-closed) `[FIX-1]`.
- **Validation**: emitters validate against
  `framework/schemas/consequence-event.schema.json` before writing
  (`additionalProperties: false` everywhere — drift fails loud, which is
  the point of normalizing).

> Built: `framework/fidelity/consequence.py` — `emit_consequence` validates (hand-rolled, no jsonschema dep) then appends to `consequence-events-YYYY-MM-DD.jsonl`; `read_ledger` + `compute_ratios` are the graduation read path.

## Adoption (R3 of the convergence roadmap)

- **R3 wires the emitters**: cabinet officers (via the brain bridge's
  reasoning/run-recording path) and every *surviving* perception pipe emit
  this shape for consequence-bearing actions. Pipes scheduled for
  migration to the cabinet (see `docs/work-model.md` — Pipe disposition)
  are NOT retrofitted; they retire on shadow parity instead.
- **Existing rows are not migrated.** The old ledgers stay as history;
  reviewers may backfill high-value rows opportunistically, but the
  graduation window restarts on normalized data — clean evidence beats
  long dirty evidence.
- **Graduation math reads ONLY this ledger.** Per (actor, lane,
  action_type): approval-unchanged rate, outcome-held rate, review-confirmed
  rate over a rolling window. The autonomy engine's thresholds stay where
  they are configured; this ledger is the single input feed. No more
  per-source special-casing.
- The reasoning-review / architect loops keep their cadence and prompts;
  their *outputs* now also land as `review` blocks on the corresponding
  events, closing the loop in the same record the action opened.
