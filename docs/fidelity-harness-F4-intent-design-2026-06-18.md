# Fidelity Harness F4 — Intent-Fidelity Design

> Extends `docs/fidelity-harness-design-2026-06-18.md` North star "Intent-fidelity, not surface-fidelity" (§25-42); Captain clarification 2026-06-18. F1 deliberately measured surface-only with a context-starved officer (no live MCP chain) — that baseline reads low *by design*. F4 wires the leak-guarded context-gathering step F1 skipped and re-centers the judge on intent-alignment (`mission × core`), crediting on-intent divergence. This doc is the build reference; per house rule, Corridor `analyzePlan` runs before any code.

---

## 0. What F4 is, in one paragraph

For each held-out `Case`, F4 lets the officer-under-test **gather real as-of-cutoff context before deciding** (the brain bridge, fenced to the cutoff), then scores the draft on **intent-alignment** rather than surface text. The intent the officer must serve is `mission/goal × core` — *what is Nate pursuing here* blended through *who Nate is*. A draft that diverges from Nate's literal reply but serves the same intent equally well or better earns credit; a draft that hits the surface but misses the intent, or that hallucinates / goes off-topic, is gated to zero. The single hardest engineering constraint is that **gathering live context at eval time is a future-leak vector** — the brain's live tiers are "now," and one of them (`_fetch_sent`) literally contains the held-out reply. F4's leak model is therefore built around *exclusion by default* of every un-fenceable source, not redaction-after-the-fact.

---

## 1. Components (purpose · interface · depends-on)

All live under `framework/fidelity/` unless noted. F4 adds **no new modules** — it extends four existing files plus two new helper functions. The delta table in §8 maps every change to its verified seam.

### 1.1 `gather_cutoff_context(case) -> dict` — NEW, in `officer_runner.py`
- **Purpose:** assemble the officer's as-of-cutoff context from the brain bridge, with **every un-fenceable source excluded** and every fenceable source passed through `leakguard.filter_mcp_result(...)`. This is the wiring that turns F1's context-starved officer into F4's context-gathering officer.
- **Interface:** `gather_cutoff_context(case: Case) -> dict` returning a **structured, ts-keyed** context dict (the exact safe shape is §2.2). Never returns free-text prose.
- **Depends-on:** the brain MCP tools (`gather_context`, `person_intel`, `open_commitments`, `read_note`), `leakguard.filter_mcp_result`, and the eligibility/snapshot rules in §2 + §5. Called by `run_case` between the pre-cutoff thread assertion (`officer_runner.py:55`) and the prompt build (`officer_runner.py:62`).
- **A/B control:** `run_case(case, role, gather=gather_cutoff_context)` is the F4 path; `run_case(case, role, gather=None)` reproduces F1 exactly (context-starved). This is the context-lift control — scoring the same case set with and without gathering isolates the contribution of context.

### 1.2 `intent_and_context(case) -> dict` — NEW, in `officer_prompt.py`
- **Purpose:** reconstruct, from `thread_before` **only**, a leak-safe **as-of-cutoff intent** — the `mission/goal × core` the officer should serve — for the judge to score against. Never reads `real_reply`.
- **Interface:** `intent_and_context(case: Case) -> {"reconstructed_intent": str, "mission_or_goal": str}` (each ≤500 chars to keep the judge payload lean).
- **Depends-on:** `case.thread_before`, `case.person/channel/language`. Pure function of pre-cutoff data; no MCP calls, so no leak surface of its own.

### 1.3 `run_case(...)` — EXTENDED, `officer_runner.py:48`
- **Purpose (added):** inject the gathered context into the eval prompt, conditionally, so the A/B knob is honest.
- **Interface:** `run_case(case, officer_role, llm=oauth_raw_llm, emit_events=True, gather=None) -> OfficerDecision`. New `gather` param; default `None` = F1 behavior.
- **Depends-on:** `gather_cutoff_context`, `build_eval_system`, `format_situation`, the conditional `EVAL_MODE_RULES` (§4).

### 1.4 `judge_with_oauth(...)` — EXTENDED, `scorer.py:35`
- **Purpose (added):** append the `INTENT_RUBRIC` to the judge system at call-time (keeping `JUDGE_SYSTEM` pristine), pass the reconstructed intent + fenced full cutoff context into the payload, and **run the programmatic grounding + topic post-checks** (§3.2-§3.3) before accepting any `intent-aligned` / `intent-partial` verdict on a divergent row.
- **Interface:** `judge_with_oauth(case_dict, clone_draft, reconstructed_intent="", full_cutoff_context=None) -> dict`. Returns the dual-verdict dict (§3.3). The generic `oauth_json_llm` call shape is **unchanged** — the extension lives entirely in `judge_with_oauth`, which builds the extended system before the call.
- **Depends-on:** `retro.judge_decision` (reused; its payload construction is extended to inject the two new sections), `retro.parse_json_block`, the grounding post-check helper (§3.2).

### 1.5 `score(...)` + `CaseScore` — EXTENDED, `scorer.py:24,41`
- **Purpose (added):** read both verdicts, compute the composite via the `decision-dominant, intent-penalizing` blend (§3.4), and expose the intent axis on the score row.
- **Interface:** `CaseScore` gains `intent_verdict: str = ""`, `intent_grounded_fact: str = ""`, `intent_composite: float = 0.0`. `score(...)` gains an optional `intent_ctx: dict | None = None` it threads to the judge.
- **Depends-on:** `judge_with_oauth`, the existing `retro.score_case` (called exactly as today, `judge=False`; intent weighting is applied *on top* of its decision verdict).

### 1.6 `Case.intent` — EXTENDED, `types.py:14`
- **Purpose:** carry the benchmark's reconstructed intent on the case so a refreshed benchmark can be cached and so `score(...)` has it without recomputation.
- **Interface:** `Case` gains `intent: str = ""`; `from_retro_case` leaves it `""` (computed lazily by `intent_and_context` at score time if empty). **Never populated from `real_reply`.**

---

## 2. The leak-guarded context-gathering step (resolves Blockers 1–4)

The naive design — "call the brain tools, run the dict through `filter_mcp_result`, inject" — **leaks**, four independent ways. The verified guard (`leakguard.py:40-63`) only redacts dict/list items that carry an ISO-**string** value under `_TS_KEYS = ("ts","date","edit_date","reply_ts","created_at","resolved_ts")` (`leakguard.py:21`) and are `>= cutoff_ts`. Anything else — a free-text string, a dict with no ts-key, an epoch-float `mtime` — passes through unchanged (`leakguard.py:63` returns non-dict/non-list as-is). F4's gathering is therefore built on **exclusion-by-default**: a source is admitted only if it is structured, per-record, and content-timestamped before the cutoff. Everything else is **dropped and surfaced**, never passed through.

### 2.1 Eligibility rules (what `gather_cutoff_context` may call)

| Brain tool | Verified shape | F4 disposition | Why (blocker) |
|---|---|---|---|
| `gather_context(handle)` | `{entity, hits[], brief(str), counts}`. `brief` concatenates the FUSED hits — incl. live Tier-2 — into prose (`context_lib.py:341-351`). Tier 2 is live-by-construction (`context_lib.py:18-23`); `_fetch_sent` reads the live Graph Sent folder (`context_lib.py:155`). | **Tier-1 only; `brief` DROPPED.** Call `context_lib.gather(handle, sources=["vault"])` — the `sources` kwarg exists (`context_lib.py:304`). Discard `brief` entirely; keep only the per-hit dicts, then fence them. | B1: `brief` is un-fenceable prose that already summarized post-cutoff facts. B2: Tier 2 is "now," and `_fetch_sent` IS the held-out reply. |
| `search_brain(query, filter)` | `{path, heading, text, score, components, mtime}` (`embeddings/lib.py` / `server.py:158`). `mtime` is an epoch **float**, not in `_TS_KEYS`; chunk `text` comes from a continuously-rebuilt index. | **EXCLUDED in eval mode.** `mtime` is file-EDIT time, not content time, so it cannot fence (a May note edited in June is pre-cutoff content with a post-cutoff mtime, and vice-versa); and a raw float never matches `_ISO_RE` so the guard would pass every hit through. Fall back to `read_note` on **specific pre-cutoff paths** only. | B3: search hits carry no usable cutoff field; even `mtime` is the wrong clock. |
| `person_intel(slug)` | raw markdown **string** (`server.py:247-261`); the reply-enrichment pipe appends `## Notes from replies` to these files live, dated after the cutoff. | **Static-frontmatter snapshot only.** Strip any dated section (`## Notes from replies`, any line matching `_ISO_RE`) and serve only the atemporal frontmatter (role, relationship, primary_email). | B4: the live dossier absorbs notes *derived from the held-out reply* — a case-specific leak, not an aggregate prior. |
| `open_commitments(direction)` | list of dicts with `source_date`, `due`, `resolved_ts` — all in `_TS_KEYS` (`server.py:265-282`). | **Admitted, fenced.** Genuinely ts-keyed per-record dicts; `filter_mcp_result` drops any with `source_date`/`resolved_ts >= cutoff_ts`. | Genuinely guard-walkable. |
| `read_note(path)` | raw markdown string for one explicit path. | **Admitted only for explicit pre-cutoff paths** (e.g. a daily note `1-Daily/2026-05-12.md` strictly before the cutoff date). Output `_ISO_RE`-scrubbed for any post-cutoff date line. | The path is the operator-chosen pre-cutoff source; no recency ranking, no live tier. |

**The one hard rule:** a value with no per-record content-timestamp is **un-fenceable and excluded**, never passed through. `gather_cutoff_context` whitelists structured ts-keyed records; it never forwards a free-text string field (a `brief`, a raw dossier) to the officer.

### 2.2 The safe gathered shape

```
gather_cutoff_context(case) returns, after exclusion + fencing:
{
  "thread": <case.thread_before>,                  # already pre-cutoff (asserted at officer_runner.py:55)

  "commitments": filter_mcp_result(
        open_commitments("owed_by_nate") + open_commitments("owed_to_nate"),
        case.cutoff_ts),                            # ts-keyed dicts → fenced

  "vault_hits": filter_mcp_result(
        [h for h in context_lib.gather(handle, sources=["vault"])["hits"]
         if _content_ts(h) and _content_ts(h) < case.cutoff_ts],
        case.cutoff_ts),                            # brief DISCARDED; per-hit ts is ISO (server.py:209-212)

  "person_static": _static_frontmatter(person_intel(case.slug)),  # dated sections stripped (§2.1)

  "excluded": [ "search_brain (mtime != content-ts)",
                "gather_context.brief (un-fenceable prose)",
                "gather_context Tier-2 sent/audio/ocr/monday (live = now)" ]
}
```

`gather_context`'s **per-hit** dicts are guard-compatible because `server.py:209-212` converts each hit's `ts` datetime to an ISO string — but only the Tier-1 (`vault`) hits are admitted, and only after a belt-and-suspenders pre-filter on a real content timestamp (`_content_ts`). The `brief` is never read. `_strip_self_hits` (`server.py:124-133`) already removes `0-Self/` from these hits; the privacy fence (parent §281-288) holds in addition to the cutoff fence.

### 2.3 `_content_ts(hit)` — the content-clock helper (B3 detail)
`mtime` (file edit) is the wrong clock for the cutoff. Until the brain index carries a per-chunk **content** timestamp, `gather_cutoff_context` derives a conservative content ts for a vault hit from, in order: (a) the ISO `ts` field that `server.py:209-212` already emits for `gather_context` hits; falling back to (b) a date parsed from the note path / daily-note name (`1-Daily/2026-05-12.md`); and **if neither yields a content date, the hit is excluded** (treated as un-fenceable). There is **no `mtime` fallback — ever**.

### 2.4 Injection
The fenced dict is rendered to a compact, ts-tagged context block and appended **after** `format_situation(case)` in the user message (so it inherits no new system-prompt authority), only when `gather is not None`. Empty/thinned results are expected and rendered as "(no admissible pre-cutoff context for X)" — the officer must reason from a thin set, exactly as Nate sometimes did. `format_situation`'s body caps (`last_cap=1500/cap=600`, `officer_prompt.py:50`) apply to the thread; the context block is appended outside them with its own per-record cap.

---

## 3. The intent judge + anti-rubber-stamp guard (resolves Blockers 5–6, Majors 1–2)

### 3.1 Layering: decision verdict stays first and visible
`JUDGE_SYSTEM` (`retro lib.py:671-685`) is **unchanged** — it remains the tone-blind `match|partial|divergent` decision rubric and runs first. `judge_with_oauth` appends a second `INTENT_RUBRIC` after a divider, and `retro.judge_decision`'s payload (`lib.py:691-695`) is extended with two new sections (`# RECONSTRUCTED INTENT (before reply)`, `# FULL CUTOFF-SAFE CONTEXT`). The judge returns **both** verdicts in one JSON object, decision-first. This keeps `divergent × intent-aligned` the only auditable credit path and keeps the surface decision visible on every row for audit.

### 3.2 The structural guard, made real (Major 2 fix — not self-attested)
The review's core finding: three prompt-level "guards" graded by the same LLM that produced the verdict are not guards. F4 adds a **programmatic, deterministic post-check** in `judge_with_oauth`, run **before** any `intent-aligned`/`intent-partial` verdict on a `divergent` decision is accepted:

```
def _grounding_ok(intent_grounded_fact: str, ctx_text: str, thread_text: str) -> bool:
    # the cited ground must actually exist in the supplied pre-cutoff material
    fact = _normalize(intent_grounded_fact)
    hay  = _normalize(thread_text + " " + ctx_text)
    return _substring_or_high_overlap(fact, hay, token_jaccard_min=0.6)
```

If the judge returns `intent_verdict ∈ {intent-aligned, intent-partial}` on a `divergent` decision but `_grounding_ok` is False, `judge_with_oauth` **forces `intent_verdict = "intent-divergent"`** and stamps `intent_grounded_fact = "FORCED: cited ground absent from cutoff context"`. This makes the citation requirement a fact, not a promise: a judge that hallucinates a plausible `intent_grounded_fact` fails the substring/overlap test and the credit is revoked deterministically. The check runs only over `thread_before` + the fenced `full_cutoff_context` — never `real_reply` — so it adds no leak.

### 3.3 The rubric (prompt layer, appended at call-time)
`INTENT_RUBRIC` instructs the judge to score `mission × core` alignment and return:
- `intent_verdict ∈ {intent-aligned, intent-partial, intent-divergent}`
- `intent_rationale` (≤140 chars)
- `intent_what_diverged` (≤120 chars)
- `intent_grounded_fact` — **mandatory citation** in the form `From [person] at [date]: [excerpt]`, drawn from the supplied context. (§3.2 verifies it.)

Hard gate clauses (force `intent-divergent`, in the prompt **and** backed where deterministic):
- **(a) Hallucination** — draft asserts a fact not present in `thread_before`/context → forced by §3.2 grounding check on any cited fact, and by prompt for uncited facts.
- **(b) Off-topic** — draft changes the topic (reply was about the mower; draft is about vacuums) → `intent-divergent`. Backed by a deterministic topic-overlap floor: if token Jaccard between the draft and `reconstructed_intent` < 0.15, `judge_with_oauth` forces `intent-divergent` regardless of the LLM's verdict.
- **(c) Ignored ask** — draft does not address the counterparty's actual request → `intent-divergent` (prompt clause; the §3.2 grounding still applies to any claimed alignment).
- **(d) Ungrounded intent** — judge cannot cite a ground for its intent reading → §3.2 forces `intent-divergent`.

### 3.4 Composite blend (Major 1 fix — formula == narrative)
`_DEC = {"match":1.0, "partial":0.5, "divergent":0.0, "error":0.0, "skipped":0.0}` (unchanged, `scorer.py:20`). The `max(_DEC[dec], intent)` blend the review flagged is wrong: `max` can only raise the composite above the decision baseline, so it can never penalize a hollow surface-match (`match × intent-divergent` would stay 1.0, contradicting the narrative). F4 uses a **decision-dominant, intent-penalizing** blend so the intent layer can *both* credit on-intent divergence *and* zero a surface-match that missed the goal:

```
_INTENT = {"intent-aligned": 1.0, "intent-partial": 0.5,
           "intent-divergent": 0.0, "error": 0.0}

def composite(dec_verdict, intent_verdict):
    dec = _DEC.get(dec_verdict, 0.0)
    if intent_verdict in ("error", ""):        # intent layer unavailable
        return dec                              # decision-only fallback (== F1 behavior)
    if intent_verdict == "intent-divergent":
        return 0.0                              # hollow surface-match or off-intent → ZERO
    # intent serves the mission: credit the BETTER of literal-match and intent.
    return max(dec, _INTENT[intent_verdict])
```

Worked quadrants (now consistent with the narrative):

| decision | intent | composite | meaning |
|---|---|---|---|
| match | intent-aligned | 1.0 | literal + on-intent (gold) |
| match | intent-divergent | **0.0** | echoed the words, missed the goal (gate fires; **penalized**, not rubber-stamped) |
| divergent | intent-aligned | **1.0** | different/better action, same intent (**the F4 credit path**) |
| divergent | intent-divergent | 0.0 | wrong action, wrong intent |
| partial | intent-aligned | 1.0 | hedged literally but understood + served the goal |
| partial | intent-partial | 0.5 | partial on both axes |
| any | error / "" | `_DEC[dec]` | intent layer failed → decision-only fallback |

This is the headline scoring number, and it is now internally consistent: the `intent-divergent → 0.0` branch is exactly what makes the §3.2/§3.3 gates load-bearing rather than inert. (Parent §60-72 mandates that the decision/intent channel dominate and voice be a light finish — this blend honors that by making intent the dominant gate over the decision baseline.)

### 3.5 Note on independence (honest scope)
F4's grounding post-check is *programmatic* and independent of the judge's free text. A *second LLM grader* (ensemble) for the intent rubric is **F5's grader-hardening gap** (parent §187-189, §330). F4 ships the deterministic check, which is cheap, reproducible, and closes the specific hallucinated-citation hole — but F4 does not claim ensemble-grade robustness. This boundary is stated so the credit path is not over-sold.

---

## 4. EVAL_MODE_RULES — conditional, no contradiction (Minor 1 fix)

F1's `EVAL_MODE_RULES` (`officer_runner.py:27-40`) says both "you have NO knowledge / do not consult search results" and "return ONLY the reply text." Bolting on "you gathered context, propose options" would contradict both. F4 makes the block **conditional on whether gathering ran**:

- **Always (both arms):** keep the strict boundary — *"You have NO knowledge of events at or after {cutoff_ts}. Do not consult or reference anything timestamped at or after that moment (search results, vault notes, commitments, decisions)."* This is the sacred cutoff; it holds whether or not context was gathered.
- **Only when `gather is not None`:** append — *"The CONTEXT block below was gathered as-of the cutoff and is safe to use. You may reason about the situation's real goal and propose the fitting course of action — including options — in your reply. Serve the intent, not just the literal ask."*
- **Reconcile the output constraint:** replace F1's "Return ONLY the reply text" with *"Return only the message you would send Nate's counterparty — no JSON, no meta-commentary. If the best response proposes options, put them in that message."* This lets the Husqvarna case put options *in the reply text* (where they belong) without inviting JSON/scaffolding.

The `gather=None` arm keeps F1's exact strict framing (including the original "Return ONLY the reply text" line), so the A/B comparison is clean: the only difference between arms is the gathered context block and the permission to use it.

---

## 5. Benchmark intent enrichment

`benchmark.py` (parent Component 1) gains intent reconstruction:
- For each reply `Case`, `intent_and_context(case)` derives `reconstructed_intent` from the **last ≤5 messages of `thread_before` only**, expressed as `mission/goal × core` (e.g. *"Goal: find a no-boundary-wire (LiDAR) robotic mower for the 3000+ m² lawn at the new house. Core: decisive, gives a concrete recommendation, Danish, low-ceremony."*). It is **textually grounded** — only what `thread_before` supports — and **never reads `real_reply`** (the held-out ground truth).
- `Case.intent` caches the result. A refreshed benchmark persists `intent` alongside the case, kept (like the held-out set) **out of the embeddings index** (parent §274-276) so the clone cannot memorize it.
- Real-world facts the situation implicates (the house, the lawn size) enter only through the §2 leak-guarded `gather_cutoff_context` path at officer time — they are NOT baked into the benchmark intent, which stays a pure function of the pre-cutoff thread.

---

## 6. Leak-safety rules (consolidated) + the web-research tension

**Three enforced layers:**
1. **Exclude-at-source (new in F4, §2):** un-fenceable sources (`gather_context.brief`, all Tier-2, `search_brain` mtime-only hits, dated dossier sections) are never gathered. This is the primary defense — most of the real leak surface is removed before any guard runs.
2. **Fence-in (`filter_mcp_result`, `leakguard.py:40-63`):** every admitted structured source is run through the ts-keyed guard; anything `>= cutoff_ts` is dropped and logged to stderr for audit.
3. **Re-fence-at-judge:** the judge sees only `thread_before` + the already-fenced `full_cutoff_context`; the §3.2 grounding check runs over that same fenced text. No new source enters at scoring time.

Plus F1's two unchanged live guards: `assert_thread_pre_cutoff` (`leakguard.py:66`) pre-execution and `scan_for_leaks` (`leakguard.py:76`) post-execution on the officer's output.

**The web-research tension (explicit).** Intent-fidelity invites "research the real goal and propose fitting options" (the Husqvarna case wants researched mower options). But **web search at eval time is `now` (≥ 2026-06-18), i.e. a guaranteed future-leak** relative to a May cutoff, and web MCPs are CRO-only-scoped anyway (`cabinet/mcp-scope.yml`), not available to the five officers. F4 resolves this three ways:
- **Disallow live web at eval time.** No officer-under-test makes a live web call during a held-out eval. The "propose fitting options" permission (§4) means *reason over the gathered cutoff-safe context and the situation* — not *query the live internet*.
- **`research_dependent` marking.** A case whose faithful answer genuinely required external research the harness cannot reconstruct as-of-cutoff is **marked `research_dependent`, excluded from the scored set, and surfaced** — never silently zeroed, which would punish the officer for the harness's blind spot (the "no-silent-caps" rule, parent §298-299).
- **Deferred time-boxed archival path (documented, NOT built in F4):** a future capability could serve a *cutoff-dated* web snapshot (archived search results as-of the cutoff) so research-dependent cases become scoreable without leaking "now." Explicitly out of F4 scope; noted as an open capability (§10.2).

**Accepted aggregate priors (unchanged from parent §277-279):** the voice centroid and `nate_model` are *aggregate* current-state priors that inflate equally across runs, so trend validity holds — and they inform the clone draft / centroid, never egress (privacy fence, parent §281-288). **Crucially, `person_intel` is NOT in this class** (Blocker 4): a per-person dossier mutated by the specific held-out interaction is a *case-specific* leak, so F4 fences it to static frontmatter (§2.1) rather than accepting it whole — proving which fields are atemporal rather than classifying the live dossier as a §277-279 prior.

---

## 7. The Husqvarna example, re-scored

**Situation (real first live run):** counterparty thread asking, in substance, for help finding a robotic mower for the large lawn at the new house. **Nate's held-out reply:** a pasted Husqvarna-mower URL.

**F1 scoring (surface-only, context-starved):** the context-starved officer drafts a generic "I'll look into mower options" with no specific link. The judge sees no surface match to the pasted URL → `divergent` → `composite = _DEC["divergent"] = 0.0`. This is the artificially low baseline — the officer never had the house/lawn facts and was scored on string overlap.

**F4 scoring (intent-fidelity, context-gathered):**
1. `gather_cutoff_context` admits the pre-cutoff thread + fenced vault hits about the house/lawn (the Mosevråvej details screenpipe captured before the cutoff), excludes `brief` / Tier-2 / search-mtime hits.
2. `intent_and_context` reconstructs: *Goal — source a no-boundary-wire (LiDAR) robotic mower handling 3000+ m² at the new house; Core — decisive, concrete recommendation, Danish, low ceremony.*
3. The officer, now context-aware, drafts a short Danish reply naming 2-3 fitting LiDAR mowers for that lawn size, the Husqvarna among them, with a one-line recommendation.
4. Judge: decision verdict vs the literal pasted URL → `divergent` (different surface). Intent verdict → `intent-aligned`, `intent_grounded_fact = "From thread: lawn ~3000 m² at new house, wants no boundary wire."` §3.2 grounding check passes (that fact is in `thread_before`). Topic-overlap floor (§3.3b) passes (mowers, not vacuums).
5. **Composite = `max(_DEC["divergent"]=0.0, _INTENT["intent-aligned"]=1.0) = 1.0`** — fully auditable on the row as `decision_verdict=divergent, intent_verdict=intent-aligned, composite=1.0`. Better-than-literal, credited.

**Adversarial control (same case, lazy / hallucinated draft):**
- **Off-topic vacuum link** → topic-overlap floor (§3.3b) forces `intent-divergent` → **composite 0.0**.
- **Hallucinated "I already ordered the Husqvarna"** (a fact absent from the thread) with a fabricated `intent_grounded_fact` → §3.2 grounding check fails (no such ground in cutoff context) → forced `intent-divergent` → **composite 0.0**.
- **Surface-echo that pastes the same URL but the gate flags off-intent** (e.g. wrong lawn assumption) → `match × intent-divergent` → §3.4 branch → **composite 0.0**, not rubber-stamped.

The gate is real (deterministic), not a prompt promise.

---

## 8. What changes vs F1 (delta table — extend, don't rebuild)

| Seam (F1, verified) | F4 change | Leak / guard note |
|---|---|---|
| `run_case` (`officer_runner.py:48`) | Add `gather=None` param; if set, call `gather_cutoff_context(case)` between `:55` and `:62`, inject after `format_situation`. | A/B control; `gather=None` == F1 byte-for-byte. |
| `gather_cutoff_context` | **NEW** in `officer_runner.py` (§2). | Exclude-by-default; only ts-keyed structured records admitted, then `filter_mcp_result`. |
| `filter_mcp_result` (`leakguard.py:40-63`) | Now **live** (F1 had it built-but-inert). Applied only to the admissible structured sources. | Cannot fence strings/mtime — hence §2 exclusions, not reliance on the guard. |
| `EVAL_MODE_RULES` (`officer_runner.py:27-40`) | Make conditional (§4): strict boundary always; "use gathered context / propose options" only when `gather` set; output line reconciled to allow options in the reply text. | No contradictory framing across the A/B arms. |
| `intent_and_context` | **NEW** in `officer_prompt.py` (§1.2, §5). | Pure function of `thread_before`; never reads `real_reply`. |
| `judge_with_oauth` (`scorer.py:35`) | Add `reconstructed_intent`, `full_cutoff_context` params; append `INTENT_RUBRIC` at call-time; run §3.2 grounding + §3.3b topic post-checks. `JUDGE_SYSTEM` untouched; `oauth_json_llm` call shape untouched. | Grounding check makes citation real; no new leak (runs over fenced text only). |
| `retro.judge_decision` (`lib.py:688`) | Reused; payload construction (`lib.py:691-695`) extended to inject the two sections. | Reads `thread_before[-12:]` + intent/context, never `real_reply`. |
| `score` + `CaseScore` (`scorer.py:24,41`) | Add intent fields; apply §3.4 composite blend on top of `retro.score_case` (called as today, `judge=False`). | Decision verdict still computed and stored first. |
| `Case.intent` (`types.py:14`) | New field, default `""`; `from_retro_case` leaves empty. | Never populated from `real_reply`. |

No OAuth call shapes change; no module is rebuilt. The change set is four extended files + two new helper functions.

---

## 9. Test / eval plan

**New leak tests — `framework/fidelity/tests/test_f4_leakguard.py` (Major 3 fix).** The existing retrodiction `test_cutoff_no_post_reply_leakage` (`retrodiction/tests/test_extraction.py:13`) tests `extract_cases()` over synthetic person fixtures in a different repo and has **no concept** of live gathering, `gather_context`, `search_brain`, `person_intel`, or `filter_mcp_result` — it provably cannot cover F4's surface, so F4 ships its own against the actual `gather_cutoff_context` pipeline with brain tools mocked:
- `test_brief_excluded`: `gather_context` mock returns a post-cutoff `brief` string + post-cutoff hits → assert `brief` never appears in the output and the dict carries no free-text source field.
- `test_tier2_unreachable`: assert `gather_cutoff_context` calls `context_lib.gather` with `sources=["vault"]` and never triggers `sent`/`screen`/`monday` (mock raises if a Tier-2 fetcher is invoked); a golden eval asserts the same.
- `test_search_brain_mtime_not_trusted`: a `search_brain`-shaped hit with `mtime` = post-cutoff epoch float and no content ts → excluded (no `mtime` fallback).
- `test_person_intel_dated_section_stripped`: dossier string with a post-cutoff `## Notes from replies` block → only static frontmatter survives.
- `test_commitments_fenced`: a commitment with `source_date >= cutoff_ts` → dropped by `filter_mcp_result`.
- `test_gather_none_is_f1`: `run_case(..., gather=None)` produces a byte-identical prompt to the F1 path.

**Anti-rubber-stamp tests — `test_f4_judge.py`:**
- `test_hallucinated_ground_forced_divergent`: judge returns `intent-aligned` with a `intent_grounded_fact` absent from context → §3.2 forces `intent-divergent`, composite 0.0.
- `test_offtopic_forced_divergent`: draft topic disjoint from `reconstructed_intent` → §3.3b floor forces `intent-divergent`.
- `test_match_intent_divergent_is_zero`: `decision=match, intent=intent-divergent` → composite 0.0 (formula == narrative).
- `test_divergent_intent_aligned_is_one`: the Husqvarna credit path → composite 1.0.
- `test_intent_error_falls_back`: `intent_verdict="error"` → composite == `_DEC[decision]` (decision-only fallback).

**Composite-determinism tests:** the §3.4 table, all seven quadrants, asserted exactly.

**Golden evals (`memory/golden-evals/`):** "no Tier-2 source is reachable from `gather_cutoff_context`"; "a hollow surface-match (match × intent-divergent) scores 0.0"; "an on-intent divergence (divergent × intent-aligned) scores 1.0"; "a `research_dependent` case is excluded and surfaced, never zeroed".

**A/B context-lift run:** the full reply-cell case set scored twice — `gather=None` (F1 reproduction) vs `gather=gather_cutoff_context` (F4) — to quantify the context contribution and confirm F4 lifts the artificially-low F1 baseline. Cross-checked against the 176 paired `autonomy_outcomes.jsonl` rows + the retrodiction baseline 0.083 (parent §313-315).

**Per-phase gate:** Corridor `analyzePlan` before code; worktree-isolated build; review (security / correctness / conventions); tests green (parent §334-335).

---

## 10. Open decisions — RESOLVED (Captain delegated authority 2026-06-18)

> The Captain delegated decision authority ("you make the decisions autonomously
> here on now"). Orchestrator ratification, research-grounded:
> **(1)** composite stays decision-dominant + intent-penalizing as shipped
> (`match × intent-partial` keeps 1.0). **(2)** `research_dependent` =
> exclude-and-surface; archival snapshot deferred. **(3)** `person_intel` =
> static frontmatter for F4; cutoff-dated dossier snapshot deferred. **(4)**
> `search_brain` stays excluded with the `read_note`-on-pre-cutoff-paths
> fallback for F4 — **adding per-chunk *content* timestamps to the brain index
> is a scheduled follow-up** (re-admits the richest retrieval tool). **(5)**
> deterministic grounding check + single intent-LLM for F4; the 2-judge ensemble
> is F5. **(6)** intent = `mission/goal × core`, pulling the active mission/goal
> from gathered context where available, else inferring from the thread.
> **(7) Voice-authenticity (research correction, 2026-06-18):** voice is a
> *separate light authenticity axis*, NOT dismissible surface — a right-intent /
> tone-deaf-voice draft still fails the human (stylometry: writing style is a
> behavioral biometric). F4's composite stays intent-dominant (the substance); a
> light voice-authenticity signal rides secondary, detailed in F5 with the
> grader-hardening — it must never perturb the intent gate.

The items below are retained for the record (now ratified above):

1. **Composite blend shape (§3.4).** F4 ships *decision-dominant, intent-penalizing* (`intent-divergent → 0.0`; otherwise credit the better of literal-match and intent). Parent §60-72 says the decision/intent channel should dominate and voice is a light finish — the blend honors that by making intent the dominant gate. Confirm this weighting, or specify a different decision↔intent balance (e.g. should `match × intent-partial` keep 1.0 or drop to 0.75?).

2. **`research_dependent` exclusion vs scoring (§6).** F4 excludes-and-surfaces research-dependent cases rather than scoring them (no live web at eval time). Ratify that policy, or prioritize the deferred time-boxed archival snapshot path so those cases become scoreable.

3. **`person_intel` snapshot fidelity (§2.1, Blocker 4).** F4 serves only static frontmatter to avoid the held-out-reply-derived `## Notes from replies` leak. A higher-fidelity alternative is a *cutoff-dated dossier snapshot* (from git history / a dated `3-People/` archive). Worth the build, or is static frontmatter sufficient for F4?

4. **Search-index content-timestamps (§2.3, Blocker 3).** `search_brain` is excluded from eval-mode gathering until the index carries a per-chunk **content** timestamp (today it has only `mtime` = file-edit time). Schedule adding content-ts to the brain index (re-admitting the single richest retrieval tool to the harness), or accept the `read_note`-on-pre-cutoff-paths fallback for F4?

5. **Intent-judge independence (§3.5).** F4 ships a deterministic grounding post-check but a *single* LLM for the intent rubric; the ensemble / second grader is F5. Confirm F4 may ship with the deterministic check alone, or pull a minimal 2-judge intent ensemble forward into F4.

6. **Intent granularity (parent §44-58).** `reconstructed_intent` is `mission/goal × core`. Confirm the reconstruction should pull the *active mission/goal* from the gathered context where available (vs. inferring goal purely from the thread), since that determines how much the §2 gathering must surface mission state.
