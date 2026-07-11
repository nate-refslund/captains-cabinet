# Attention Gateway — the Chair-owned Captain channel (spec)

**Status:** BUILT P1–P5 (merged to master, gauntlet-hardened — see §8 phase table); P6 open + retroactive P1–P5 ratification pending per HANDBACKS
**Date:** 2026-07-08
**Author:** Captain-side design session (Nate + Claude), from the 2026-07-08 feed investigation
**Layer:** `framework/` (mechanism) + `instance/config/` (posture, preferences, charter settings)
**Relates to:** F0.8 kill-list (raw Telegram posters), EARN-DEMOTION (2026-07-03/04), ACT-AND-DRAFT (2026-07-04), FOUNDATION-FIRST (2026-07-05), field-test override (2026-07-05 — superseded by §10 per Captain choice 2026-07-08), courses-of-action rule, axes-contract discipline

---

## 1. Problem (observed, 2026-07-07 → 2026-07-08)

The Captain's Telegram feed received **~24 action cards in ~18h covering ~8 distinct situations**, including 6+ cards and TWO executed (duplicate) calendar events for one testament-signing reminder, re-proposals of already-acted situations at 02:24 and 04:24, and batch-urgency cards pinging through the night. Loop stats measured the failure and kept going: 64 cards decided in 30d → 5% approved, 55 expired; calendar_event_create 7/7 expired; AWAITING queue at 32.

Root causes (traced to code, not guessed):

1. **Dedup keys are LLM prose.** `subject` = slugified `subject_hint` (fresh phrasing per run); the evidence-overlap backstop (`action_lane.py:496-498`) intersects *verbatim annotated strings* (`path — <paraphrase>`), so the stable ids inside them never match.
2. **Acting never updates perception.** `gather` reads vault text only; `action_exec` writes Redis/ledger/undo-journal/external systems but nothing gather reads. `reminder_set` exists nowhere in framework. The world looks perpetually broken → perpetual re-proposal.
3. **No single door.** The action/draft lanes and the re-card path post raw to `api.telegram.org`, bypassing `channel.py` and the intake→composer funnel that briefings already use.
4. **No feed self-awareness.** Outbound isn't journaled as a feed; nothing can ask "what did we already send about this?" (this investigation had to read screenpipe OCR of the Captain's screen).
5. **Learning exists but doesn't gate.** The consequence ledger records expiry/undo per cell; nothing feeds that back into what gets sent. Expiry-as-verdict is measured, then ignored.
6. **Security mechanics leak into presentation.** SEC-4's ⚠ INJECTION-SUSPECT banner (a taint flag that correctly forces propose-only) is rendered AT the Captain as noise on routine commit-digest cards.

## 2. The law (framework doctrine)

> **A Captain-facing message is an action on the org's scarcest resource — Captain attention — and gets the same discipline as every other action: a stable situation identity, world-grounding, one gate, a journaled feed, and a verdict loop that changes future behavior. The Chair owns the channel: every message is Chair-authored — as standing policy (the Comms Charter, executed mechanically) for routine traffic, as live Chair judgment for exceptional traffic — and the Chair continuously re-learns which is which. A short list of floors binds even the Chair.**

One sentence per half: *mechanism belongs to framework, posture and preference belong to the instance* (FOUNDATION-FIRST); *everything the Captain can perceive is Captain-promptable in one sentence, and the tiny invariant core exists only to make that single sentence authenticated, journaled, and reversible* (no loop edits its own judge — but the Captain's receipted word edits any preference instantly).

## 3. Ownership model — Editor-in-Chief over a mechanical desk

- **The Chair owns the Captain relationship.** All Captain-facing traffic is Chair-authored in one of two modes:
  - **Charter-mechanical (T0/T1):** rendered at machine speed from Chair-authored templates, voice, and routing rules in the Comms Charter. Digest lines, standing-card state flips, pre-authorized direct classes (e.g. infra pages) ride here — full speed, no LLM in the path.
  - **Chair-live (T2):** anything ping-now, world-acting, novel-class, low-confidence, or unclassified gets a per-message Chair judgment with full context (situation history, recent feed, captain-patterns/intents, brain). The Chair composes or vetoes the actual message.
- **The Chair improves the channel itself.** An event-triggered comms-retro reads the feed's own stats and amends the charter (routing, form, budgets, verbosity, even granting a watchdog class a direct line). Amendments are versioned, diffed, journaled with WHY, surfaced as one FYI line, and revertible.
- **Why not live-Chair on every byte:** the Chair is an LLM session that compacts, sleeps, and hits limits; deadline pings can't block on it; freehand per-message output is unreplayable and untestable; digest lines through full Chair turns burn quota real work needs. The charter IS the Chair on the routine path — judgment cached as policy, exactly the axes-contract pattern (judgment → tables → resolver).

## 4. Architecture

New package `framework/attention/` + surgical changes at existing seams. No new store of record: the situation view derives from ledgers that already exist plus one new append-only feed journal.

### 4.1 Situation identity — `framework/attention/situation.py` (pure)

- `canonical_refs(evidence) -> frozenset[str]` — mechanically extracts stable ids from evidence strings: vault-relative `.md` paths (strip ` — annotation` suffixes, `ref=` prefixes, quotes/whitespace/parens; end-guarded against `.mdx`/`.md.bak`/`.md-old` siblings), `cmt-<hex>` ids, `monday:<digits>` (incl. the prose `board <9+ digits>` form), calendar event UUIDs, correlation ids (`cabinet-proposal-id:<hex>`), cabinet scheme ids (`veto:`/`undo-journal:`/`thread:`/`NEED-<hex>`), normalized URLs (case/punctuation/trailing-slash). All ids lowercase. Deliberately NOT extracted: bare hex tokens and extensionless vault paths (false-positive magnets / instance layout). `path_grade(ref)` classifies the weaker `.md`-path grade for consumers. Deterministic, idempotent, no item-count truncation. Unit-tested against the *real observed corpus* — the five spellings of the testament evidence must all collapse onto `cmt-fca6836e2844` + its lowercased path.
- `situation_key(refs, subject) -> str` — primary: short hash of the sorted canonical ref-set; fallback for genuinely ref-less items: the slug. `situations_overlap(a, b)` = non-empty canonical-ref intersection.
- **LLM prose never keys anything.** `subject_hint` stays as display text only.

### 4.2 Situation view — `framework/attention/situations.py` (derived, rebuildable)

Per `situation_key`: status (`open → surfaced → pending → acted/decided → verified/resolved → dormant`), canonical refs, class, standing `telegram_message_id`, `last_surfaced_at`, counts, charter route. Built by folding the consequence ledger (proposal/acted rows), undo journal (created ids), and feed journal (sends/edits/verdicts). Redis carries only a fast `situation_key → message_id` index, rebuildable from the feed journal.

### 4.3 Feed journal — `framework/attention/feed.py`

Append-only JSONL `~/Library/Application Support/cabinet/feed/feed-YYYY-MM-DD.jsonl` (same conventions as the consequence ledger: schema `framework/schemas/feed-event.schema.json`, `additionalProperties:false`, last-write-wins supersession on an identity tuple).

Row: `ts, direction(out|in), situation_key, class, urgency, mode(charter|chair|fallback), kind(card|edit|digest|briefing|page|reply), content_hash, content_len, telegram_message_id, chat, charter_version, gate_trace[], verdict{...}`.

- Appended at the **transport layer** (`channel.py` send/edit) — cannot be skipped by any caller.
- **Cursor-based reads, never re-reads (Captain directive 2026-07-09).** The introspection primitive is `feed_since(cursor, max_n=200) -> (rows, new_cursor)`: every consumer (T2 dossier assembly, comms-retro, gate dedup, briefing composer) carries its OWN durable cursor (last-consumed feed seq, per consumer id) and reads only what is NEW since it — the same 50 rows are never re-read and re-judged turn after turn. A missing/corrupt cursor falls back to a bounded tail read (`recent_feed(n)`) ONCE and immediately re-anchors. Rows are monotonically sequenced at append time (`seq`), so cursoring is exact, replayable, and cheap regardless of feed size.

### 4.4 One door — channel + intake hardening

- `channel.edit_message(message_id, text)` + `upsert_card(situation_key, text, notify: bool)` — new standing message or in-place edit (Telegram edits do not notify). Material change or urgency ⇒ new message (map updates); everything else edits silently.
- **Bypass kill (F0.8):** `run_action_lane._tg`, `run_draft_lane._tg`, `action_exec._tg_send` re-route to `intake.submit(...)` with `situation_key/class/urgency/render_payload`; the surface service owns the send. `model-fallback-pager.sh` and any shell producer use a thin `cabinet/scripts/attention-submit.sh`.
- **CI tripwire ratchet** (sister of the launcher-hardcode ratchet): `api.telegram.org` outside `framework/frontdoor/channel.py` → red, with a documented shrink-only allowlist (inbound poller `getUpdates`/reaction; voice sender until migrated).
- Legacy Docker-era direct senders (`health-check.sh`, `cost-dashboard.sh`, `token-refresh-watch.sh`, `officer-supervisor.sh`, `reply-to-captain.sh`) are dormant on mac-native: marked deprecated → `attention-submit.sh` (docs-track-code in the same change).
- **Conversational replies** (Chair answering a Captain message) stay ungated — they are answers, not disturbances — but are journaled into the feed with `kind=reply`.

### 4.5 The Gateway — `framework/attention/gate.py` (deterministic tier)

Runs inside the existing 300s `surface.py` drain loop and at briefing compose. Ordered checks, every decision journaled to `gate_trace` (no silent drops):

1. **Floors:** kill switch / `allow_sends()`.
2. **Identity dedup:** overlapping open/pending/acted situation → **MERGE** (edit the standing card) instead of a new card; recently decided `skip:`/`never:` → suppress + (if evidence is genuinely new) file a need instead of re-asking.
3. **World-grounding probes** (pluggable per action kind, read-only, fail-open to `unknown` — never block on probe outage; `unknown ≠ satisfied`): reminder/calendar → calendar query by time+ref; monday_task → search by canonical ref / cid footer; delegate → officer task state. "Already satisfied" → suppress + emit a resolution consequence so the upstream signal closes.
4. **Charter resolve:** class × urgency → route (`direct-now | standing-card-edit | next-briefing | weekly-rollup | mute+need`), template, verbosity, per-class budget state.
5. **Timing:** quiet hours (captain_timezone); mechanical ping-now test — *ping-now is valid only if the item is wrong-or-worthless before the next briefing* (deadline < next briefing time), else demoted to batch.
6. **Mode pick:** charter-mechanical → render + send/edit now. Chair-required (ping-now, act-carrying, novel class, `confidence < floor`, unclassified) → T2.

### 4.6 Chair-live judgment (T2)

- The gateway files a **judgment request** via the existing Redis trigger/wake plumbing to `cos`, carrying a compact dossier: candidate content, situation history, last-N feed rows, matching captain-patterns/intents entries, the charter section, taint provenance.
- The Chair (its session, or a Chair-context subagent assembled deterministically from the Chair's role + tier2 + charter) returns `send | edit-standing | merge | fold-to-briefing | suppress(reason) | escalate` plus final text in Chair voice. The self-review rubric — *new? true? valuable? terse? well-timed? already answered?* — is the T2 system prompt core (versioned in framework; charter may extend, not delete).
- **SLA + fallback (charter-defined per class):** e.g. deadline-critical: 10 min, then charter-mechanical render sends with a `(chair-offline)` marker; all other classes: hold to next briefing. Timeout enforced by the surface service. Chair-down never means channel-dead (floor classes) and never means spam (everything else waits).

### 4.7 Comms Charter — Chair-authored policy artifact

- **Instance artifact:** `instance/config/comms-charter.yml`, schema-validated (`framework/schemas/comms-charter.schema.json`). **Framework default:** `framework/attention/charter-default.yml` — conservative: everything batch/terse, quiet hours 21:00–07:00 captain-tz, direct classes only `deadline-critical` and `infra-page`, banners off (§5).
- Contents: class taxonomy + matchers; routes; per-class budgets + demotion bars; standing-card templates (terse by default — verbose only on Captain request); voice/tone notes; verbosity overrides; SLAs + fallbacks; quiet hours; escalation criteria.
- **Amend path — provenance ladder (Captain feedback 2026-07-08: zero extra Captain actions):**
  - **Captain-prompted (`[trust:captain]`):** a Captain DM expressing a comms preference IS the amendment. The Chair applies it immediately — **no unlock, no confirm tap, no follow-up action**. Forgery resistance is mechanical, not ceremonial: the amend script requires a **citable receipt** — the triggering message id from the authenticated Captain-DM inbound journal (CAPTAIN_TELEGRAM_ID). The Chair's *belief* that the Captain said something cannot amend; a real inbound row must exist and be quoted in the amendment record. Hallucinated instructions fail the lookup; text inside captured content has no Captain-DM message id. Acknowledgment style is itself a charter setting (one-line confirm | silent apply + FYI digest line).
  - **Chair-initiated (`[trust:chair]`):** from comms-retros / pattern-listening, the Chair amends without any Captain involvement. Charter versions are perfectly reversible artifacts, so per the EARN-DEMOTION ruling these act first and tell after: one FYI line, `undo`-able by version. Quieter changes are always free; louder/wider changes ride this act-first-with-undo path.
  - **Everything else (captured content, officer suggestions):** never amends directly — routes to the Chair as a suggestion with no authority.
  - Mechanics per amendment: journaled diff + WHY + provenance receipt + `charter_version` bump, schema-validated, invariant-core-checked. "Go back to how it was" is one Captain sentence (revert by version). A schema-invalid or core-violating charter **loads as the framework default** (fail-closed), never best-effort.
- `charter_version` is stamped on every feed row → any historical send is replayable against the exact policy that produced it.

### 4.8 Learned attention budgets (adaptive posture)

- Reuse the graduation machinery pattern on **attention cells** keyed `(class, urgency)`: verdict supersessions from the feed — approve/edit/👍/reply-engagement promote; expiry/silence/undo/`stop`-patterns demote.
- States: `ping-eligible → batch-only → weekly-rollup → muted (need filed)`. Example bar (charter-tunable): ≥5 consecutive expiries with 0 approvals in a class → demote one state; sustained engagement → promote one state. Evaluation mechanical; the Chair may override per amendment — and the override is itself journaled and measured.
- Bars/posture live in the charter (instance); framework defaults conservative. **The Captain's silence is a verdict.** This supersedes the 2026-07-05 field-test "surface EVERYTHING" override per the Captain's 2026-07-08 choice: the label flow continues (everything is still *generated and journaled*), but presentation quiets adaptively.

### 4.9 Comms-retro (the Chair's learning loop)

Event-triggered (rides the existing retro-trigger): the Chair reads the feed falsifier stats — dup-rate, per-class expiry-rate, quiet-hour pings, undo-rate, edit-distance between its charter-mechanical renders and Captain-edited versions — plus captain-patterns/intents, then proposes/applies charter amendments. A daily **feed falsifier line** rides the existing falsifier-series: `dup_rate, expiry_rate, pings_quiet_hours, situations_open, charter_version`.

### 4.10 The invariant core (germline) — deliberately tiny, and never a preference ceiling

Revised per Captain feedback 2026-07-08: presentation/behavior rules originally listed as floors (one-card-per-situation, quiet hours + exception classes, re-surface policy) are **charter defaults, Captain-promptable in one sentence** (§4.7 ladder). What remains germline is only what makes the one-sentence rule trustworthy — each item either costs the Captain zero attention or is already the Captain's own ratified authority law; **none constrains a communication preference**:

1. **Kill switch / `allow_sends()` + token scrub** — safety harness; invisible to the Captain.
2. **Feed journaling + charter versioning at the transport layer** — the receipts, undo handles, dedup data, and learning loop are made of this. Disabling it changes nothing the Captain experiences; it only blinds the org. It is what makes "instant on your word" and "revert in one sentence" real.
3. **Single-channel topology** — no `api.telegram.org` outside `channel.py` (CI tripwire). A floor on *code*, not on the Captain: any behavior (including "watchdog X DMs me raw, instantly, 24/7") is expressible through the channel as one charter route line. Bypasses add no expressible behavior and subtract the killswitch, scrub, and journal.
4. **Never execute the same act twice by accident** (world-probe + acted-state guard). Correctness, not preference — an explicit Captain "do it again" is a fresh instruction, not a floor change. When/how often to *re-surface or re-mention* a situation is charter.
5. **Content-derived text is never the *authority* for an act** (D13/SEC-4 core). This does not limit the Captain — the Captain's receipted word authorizes anything, including standing grants via the attested sovereign machinery. It says captured email/commit/meeting text cannot *itself* be the authorization. Widening this dial is the one change that stays on the attested ritual, because it hands authority to future *attacker* text, not to the Captain — per the Captain's own upgrade-is-attested / downgrade-is-instant asymmetry (axes contract). Taint *presentation* is charter (§5).
6. **External-recipient rules unchanged** — `queue_draft` remains the only path to humans outside the machine (brain-bridge; separately ratified).

Identity machinery (situation keys, canonical refs) is framework code, but *how situations render* (standing card vs separate messages, terseness, ack style) is charter — the Captain can reshape all of it by prompting the Chair.

## 5. Security semantics vs presentation (INJECTION-SUSPECT and friends)

Today SEC-4 renders ⚠ INJECTION-SUSPECT *at the Captain* on routine cards whose source text tripped the taint heuristic (e.g. imperative phrases in commit digests). Captain feedback 2026-07-08: noise.

- **Mechanics stay (floor):** `injection_suspect`/taint remains on the card metadata and keeps forcing propose-only + D13 never-act-first. Unchanged, mechanical, not charter-editable.
- **Presentation moves to the charter:** default = banner hidden from the Captain; taint provenance always visible in the Chair's T2 dossier and the ledger row. The Chair triages: drop the flag as noise, bundle, or escalate.
- **A real security event is its own class:** `security-alert` (e.g. quarantine trip, repeated targeted injection attempts against outbound surfaces) — floor-listed direct class, never quieted by budgets.
- All watchdog/system flags follow the same shape: they file intake items with a class; the charter or the Chair decides drop / bundle / escalate. No system component renders its internal state directly at the Captain.
- Follow-up (out of scope here): tune the taint heuristic's false-positive rate on commit-digest text.

## 6. Framework / instance split (FOUNDATION-FIRST compliance)

| Framework (`framework/attention/`) | Instance (`instance/config/`) |
|---|---|
| situation.py, situations.py, feed.py, gate.py, charter.py (loader/validator), schemas, charter-default.yml (conservative), T2 rubric core, floors, attention-cell evaluator, CI tripwires | comms-charter.yml (this Captain's routing/voice/budgets/verbosity), posture election (permissive start per field-test lineage), quiet hours, class overrides, learned preference state |

No captain-specific literal in framework; resolvers per existing discipline (`framework.env.*`). A clean-room deployment gets the conservative default charter and a Chair that starts learning its own captain.

## 7. Data (concise)

- **feed-event.schema.json** — §4.3 row; identity tuple `(chat, telegram_message_id, kind, ts)`; supersession for verdict enrichment.
- **comms-charter.schema.json** — `version, classes[{id, matchers, route, budget, template, verbosity, sla, fallback}], quiet_hours, ack_style, voice` (+ per-amendment record: `diff, why, provenance{trust, receipt_message_id}, version`).
- **Consequence ledger** — unchanged shape; lanes additionally store `canonical_refs` alongside raw evidence in `refs` so `covered_evidence_refs()` compares stable ids.
- **Redis** — `cabinet:attention:msgid:<situation_key>` index (rebuildable); existing streams/budget keys reused.

## 8. Phases (validation-gated; each independently shippable)

| Phase | Ships | Acceptance (prove-it) |
|---|---|---|
| **P1 Identity** ✅ built + gauntlet-hardened 2026-07-08 | situation.py; canonical refs wired into `propose_actions` dedup at compare time, both sides (`lane_dedup`/ledger-row changes proved unnecessary — `covered_evidence` already carries every open+decided card's raw refs). Post-adversarial-review hardening: no item-count truncation (the 64-item cap silently no-op'd dedup at live ledger size, hash-order nondeterministic), `.md` end-guard (no phantom live path from `.md.bak`/`.mdx` siblings), paren-citation and URL normalization (case/punct/slash), lowercase identity, monday/board + veto:/undo-journal:/thread:/NEED- extraction, within-batch id-grade dedup (one LLM response can't double-card a commitment; shared source NOTES still yield distinct cards), id-grade vs `-path` drop reasons, 14d covered-evidence window (`CABINET_COVERED_EVIDENCE_WINDOW_D`) bounding rolling-digest-path suppression | PROVEN by pinned tests: the 5 testament evidence spellings collapse to one situation; 23 observed cards → ≤8 identity groups and 10 first-presentations under live suppression semantics; testament collapses to EXACTLY ONE card; full framework suite 3792 passed incl. launcher-hardcode + CG-2 + axes + germline-lockstep ratchets. **Known residuals (deliberate, bounded):** dedup-poisoning via attacker-influenceable evidence refs is bounded by the 14d window + suppress-log visibility until P2 world-grounding/P6 provenance weighting; bare-hex + extensionless-path refs deliberately carry no identity (false-positive magnets / instance vault layout); space-bearing meeting filenames rely on id-grade refs (documented-limitation test) |
| **P2 World-grounding** ✅ built 2026-07-08 | `framework/attention/acted_overlay.py` (ledger `acted:*` rows × undo journal → entries + live/reversed canonical ref-sets); ALREADY-ACTED section rendered into gather signals; `propose_actions(acted_refs=, reversed_refs=)` — standing acted artifacts drop with the distinct `already-acted` reason, Captain-REVERSED acts subtract from the covered set (undo = "act was wrong", not "situation is fake" — P1 alone wrongly kept suppressing); overlay build failure = world UNKNOWN → act-first disarmed for the run. Review-cp2 hardened: reversal = journal `status=="reversed"` ONLY (`reversal_failed`/`dead_letter` stamp `reversed_at` while the artifact stands); approved-then-undone cards un-cover too (`action-card` rows join by cid); the verbatim covered check also honors reversal; in-window journal rows against an empty ledger read = env drift → UNKNOWN (quiet-box old rows stay a legitimate empty world); unreadable journal file raises (never silent wrong suppression). Carried as `patches/p2-acted-overlay-world-grounding.patch` (applies on top of p1). **Deferred to P4 probes (documented):** artifact-grade matching (due_iso/title/live calendar+Monday queries) — journal rows don't yet persist payloads; the disjoint-refs duplicate class (3 commitment rows, one promise) is meanwhile mitigated at the LLM level by the overlay section + upstream commitment dedup (§13) | Pinned: acted testament situation → proposes nothing (`already-acted`); reversed act → same situation presents again even inside the covered window; unknown world state → still proposes, act-first disarmed; acted reason wins over generic covered reason; full suite 3808 passed |
| **P3 One door + feed** ✅ built 2026-07-09 | `framework/attention/feed.py` (cursor journal: monotonic seq under flock with high-water re-derivation, `feed_since(cursor)` per-consumer cursors, traversal-fenced) — the never-re-read directive as code; `channel.py` gains reply-to-SPECIFIC-message threading, `silent` sends, `reply_markup`, `edit_message` (noop on not-modified), `answer_callback`, conservative md→HTML `render_markdown`, sent `message_id` capture, and transport-layer feed journaling (ImportError-tolerated at bootstrap; append failure = loud JOURNAL-GAP, delivery still returns); poller widened to `callback_query`/`message_reaction`/`poll_answer` + deterministic reaction vocabulary (charter classes, Telegram whitelist, id-hash rotation) + inbound Captain files (getFile ≤20MB, sanitized+containment-checked inbox) relayed as `[tg-file]`/`[tg-callback]`/`[tg-reaction]`/`[tg-poll-answer]` lines; all three raw lane posters routed through the channel (`patches/p3-one-door.patch` for the two germline files + direct `run_draft_lane` edit) with `CABINET_ENV=runtime` added to both lane plists (allow_sends gate would otherwise silently block); `attention-submit.sh` + pager migration + per-card edit coalescer deferred to P4 (allowlisted TODO). Review-cp3 hardened: shims raise on ANY non-sent status incl. blocked-dev (a process missing `CABINET_ENV=runtime` pages instead of silently blackholing — marker added to action-lane/draft-lane/cos-inbound plists AND `services.yml` env blocks so regeneration can't wipe it); `edit_message` opts out of the parse-strip 400 retry (a markdown no-op edit could otherwise "succeed" by rewriting the card as raw markup); feed seq allocation + row append under ONE flock (a stalled writer can't publish a seq behind an already-passed cursor); journal row construction inside the delivery swallow; over-20MB Captain files inject a visible `[tg-file-error]` line | Ratchet `test_single_telegram_door.py` green: `api.telegram.org` only in channel.py + annotated shrink-only allowlist, kill-list files pinned out forever; framework 3880 + cabinet/scripts 242 passed; feed tests prove seq monotonicity under 8-thread concurrency and exact cursor resume; live feed dir verified clean of test pollution before merge |
| **P4 Standing cards + charter** ✅ built 2026-07-09 | `framework/schemas/comms-charter.schema.json` + `framework/attention/charter-default.yml` (conservative) + `charter.py` (load fail-closed-to-default, classify kind>keyword>lane, resolve, provenance-laddered `amend` — captain-receipt vs chair vs never-from-captured; the quiet-hours floor is the allow-list of classes that PING at night, so a chair amendment may only SHRINK it (quieter, free) — GROWING it is louder and needs Captain provenance (§4.10.4), checked against the CURRENT base floor so a chair tune after a Captain narrow isn't locked out); `gate.py` (situation-keyed standing-card map, TERSE render no-payload-dump with charter-owned injection banner + ·pid· passthrough — both wrap templated cards too, the binder marker can never be swallowed; ordered `decide`: identity-dedup→mute→STRUCTURAL quiet-hours/ping-now piercing in captain tz [floor kind OR a real deadline_iso before next briefing — never a prose keyword]→route, `deliver` via channel edit/send + intake briefing route, `submit`); `cabinet/scripts/attention-submit.sh` (shell producer, DRY mode, one-door-clean). **Gauntlet-hardened (cp4):** the conservative default's floor classes are ALL kind-matched (producer-attested) — a card that merely says "today"/"urgent" can never pierce quiet hours (the headline 3am-false-send the gateway exists to kill); a genuine ping-now with an imminent deadline PROMOTES over a batch route. Terse cards per Captain 2026-07-09; T2 Chair-live + composer briefing-render deferred to P5 | PROVEN: one situation = one message across 3 state flips; identical re-render suppresses; batch card (and a "today" note) at 02:00 → briefing not send; floor class at 02:00 → send unsilenced; non-floor ping-now pierces only with a real imminent deadline; no floor class is keyword-matched; chair may shrink but not grow the floor and isn't locked out after a Captain narrow; templated card keeps ·pid· + banner; charter-unavailable raises; full framework + cabinet green |
| **P5 Chair T2 + fallbacks** ✅ built 2026-07-09 | `framework/attention/t2.py` — `assemble_dossier` (candidate + situation history + recent feed + Captain patterns/intents standing rules + charter section + taint provenance; pure, fail-soft on absent ledgers), `file_judgment_request` (persists dossier + SLA deadline, fires a Redis trigger to `cos` carrying only the request-id pointer), `apply_verdict` (Chair callback: send/edit-standing/merge/fold-to-briefing/suppress/escalate + authored text; consumes + journals), `sweep_expired` (SLA fallback, idempotent). Gate `decide(chair_review=)` mode-pick (opt-in, P4 mechanical byte-identical by default) routes exceptional items (genuine ping-now, act-carrying, unclassified, low-confidence, real taint) to `action="chair"`. Surface service runs the sweep each 300s drain. Versioned `t2-rubric.md` (new/true/valuable/terse/well-timed/already-answered). `gate.briefing_item` makes the gate→composer path pure/testable; `gate.submit(chair_review=)` files the T2 request on `action="chair"` (activation wiring, not dead code). T2 rubric is prompt-side; module carries no LLM call. **Gauntlet-hardened (cp5):** `sweep_expired`/`apply_verdict` now default to real gate/channel delivery, so the surface service's no-arg `sweep_expired(now)` ACTUALLY delivers — the critical bug where a floor page past SLA was journaled `fallback-sent` and consumed while the channel went DARK (11 other findings refuted); a floor send that fails is journaled honestly (`fallback-send-failed`) and LEFT for retry, never a false 'sent'; a malformed/absent deadline expires (fail toward sweeping, never an immortal stuck request); `escalate` DELIVERS the Chair's authored ask (surfaces, not just journals) | PROVEN: chair-down floor request past SLA → mechanical send `(chair-offline)` incl. the REAL surface no-arg path (channel stubbed, one send asserted); non-floor holds to briefing; failed send not consumed + honestly journaled; malformed deadline still expires; escalate surfaces the ask; sweep idempotent; dossier carries no voice/model tokens; mode-pick opt-in preserves P4; identity wins over mode-pick; submit files T2 on chair action; framework 3963 + cabinet 242 + layer-sep green |
| **P6 Learned budgets + retro** | attention cells, demotion states, comms-retro skill, amend path, feed falsifier line | Synthetic 5-expiry streak demotes a class to briefing-only; amendment journaled + FYI-lined + revertible |

Governance: `framework/acting` + `frontdoor` are germline — lands as a proposal branch; the Captain applies (germline unlock). Docs-track-code rides every phase (courses-of-action rule §3 urgency text, CLAUDE.md pointers, runbooks).

## 9. What this kills (mapped to the observed feed)

| Observed 2026-07-07/08 | Under this design |
|---|---|
| 6+ testament cards, 2 duplicate calendar events | 1 standing card; P1 identity merges; P2 probe blocks act #2 |
| EC-details re-proposed at 04:24 after 18:09 act | acted-overlay + identity merge; card edits to `acted ✓` |
| 5× commit-hygiene cards + 2 grander variants | 1 situation; expiry streak demotes class to briefing, then weekly |
| Batch cards pinging 23:48–05:25 | quiet hours + mechanical ping-now test → briefing |
| AWAITING 32 clones | situations with states, not card piles |
| ⚠ INJECTION-SUSPECT on routine digests | Chair-triaged metadata; Captain sees it never (unless security-alert class) |
| 55/64 expired, 5% approved | expiry drives per-class demotion; feed falsifier makes it visible daily |

## 10. Ruling compatibility

- **Field-test override (2026-07-05):** superseded by Captain choice 2026-07-08 — adaptive budgets keep full label generation while quieting presentation per class.
- **EARN-DEMOTION / act_with_undo:** unchanged; this spec adds the act-once guarantee (P2) and moves acted-tells onto standing cards.
- **ACT-AND-DRAFT, external comms:** unchanged; outbound-to-external stays `queue_draft`, per-item approved.
- **Courses-of-action rule:** unchanged in substance; its `batch-into-next-briefing` default becomes mechanically enforced; one-card-per-situation becomes structural.
- **Axes contract:** attention cells and charter are DATA tables + resolvers; no axis branches. The amend asymmetry mirrors it exactly: quieter/narrower applies instantly from anywhere; louder/wider applies instantly on the Captain's receipted word (or Chair act-first-with-undo); only the content-derived-authority dial keeps the attested ritual.
- **Captain-law provenance discipline:** charter amendments follow the same provenance-stamped append pattern as the captain-patterns/intents ledgers — `[trust:captain]` requires a citable Captain-DM receipt, `[trust:chair]` is officer text that never silently becomes standing law without its stamp.

## 11. Alternatives considered

- **B — Chair authors every byte live:** rejected as the universal mode (availability, replayability, quota); adopted as T2 for the traffic that deserves it, and as authorship-via-charter for the rest.
- **C — minimal mechanical fix only:** adopted as P1–P2, rejected as the end state (next producer class recreates the mess; no learning; no feed awareness).
- **Pull-only dashboard / pinned state message:** deferred; standing cards capture most of the value inside the ratified Telegram-first surface.

## 12. Open questions (small, non-blocking)

1. Voice notes (post-reply-voice) — journal as feed rows in P3, migrate sender behind channel in a later pass?
2. Standing-card retention — archive a resolved situation's card text into the vault/day-recap after N days?
3. T2 executor — Chair session turn vs Chair-context subagent: start with subagent (deterministic assembly, no session contention), revisit after P5 telemetry?

## 13. Transport decision — direct Bot API through our own gated channel (ratified direction, research 2026-07-09)

**Verdict: extend `channel.py` + the inbound poller with direct Bot API features; do NOT route the live loop through the Claude Code telegram plugin.** Evidence: three-agent research sweep + adversarial doc-verification against core.telegram.org (Bot API 10.1, 2026-06-11).

- **Why not the plugin (v0.0.6):** the live deployment already bypasses it in BOTH directions for cause — it cannot wake an idle session (the founding constraint of the poller+tmux wake design) and its send path has none of our incident-hardened floors (killswitch gate, token scrub, chunk-no-false-ACK, transport retry). It doesn't even load in any officer session today (`start-officer-mac.sh` suppresses `--channels` when the inbound-watchdog plist exists). Adopting it = a second door P3 exists to close, plus a Bun/grammY runtime in the critical path. Its **permission-relay pattern is the reference implementation** we steal as design (answer-callback-first, sender re-auth on tap, edit-card-to-outcome so a card can't be double-answered) — a pattern, not a dependency.
- **What direct API adds (all additive to existing poller/channel):** inline keyboards + `callback_query` (per-step approve/edit/skip/undo buttons; `callback_data` ≤64 bytes → ids only, chain state stays in Redis/ledger); `editMessageText`/`editMessageReplyMarkup` (standing cards — NO edit window on a bot's own DM messages, doc-confirmed); `reply_parameters` with exact-substring quote (**reply to the SPECIFIC triggering message** — fixes the confirmed always-last-message threading at `channel.py` reply anchor + poller Redis key); native DM polls incl. multi-answer (AskUserQuestion-style selects, `poll_answer` is in default allowed_updates); `disable_notification` (batch/FYI tiers send silent — the phone only sounds for ping-now); private-chat forum topics (9.3/9.4 — per-lane threads inside the Chair DM; note close/reopen not supported in private chats); DM pins (never notify); `sendChatAction` + `sendMessageDraft` streaming ("Thinking…" during investigation-bar gathers); Rich Messages tables/collapsible evidence blocks (10.1); `date_time` entities (9.5, captain-tz rendering).
- **Undocumented-behavior policy (verifier findings):** silent-in-place edits and private-DM `message_reaction` delivery (👍-as-data for the ≥3-👍 quiet rule) are real client behavior but NOT documented API contract — build both as progressive enhancements with fallbacks (an edit that notifies is tolerable; 👍 falls back to the text grammar). Native checklists are business-connection-gated → unavailable to a plain bot; the per-step widget stays inline-keyboard-based.
- **Mechanical P3 deltas this ratifies:** widen the poller's `allowed_updates` from `["message"]` to `+callback_query, message_reaction, poll_answer` and route them into the binder (buttons AND the existing text grammar both bind — text stays the accessibility/killswitch-proof fallback); capture sent `message_id`s into the feed journal (today discarded); carry the triggering `message_id` through intake→composer→send for true threading; per-card edit coalescer ≤1 edit/sec/chat honoring `retry_after` (edits share flood control; ~1 msg/sec/chat, doc-confirmed).
- **Transport stays `getUpdates`** (Mac-behind-NAT, no public endpoint, killswitch-friendly); webhooks reconsidered only if a Mini-App dashboard ever lands.
- **UX rulings (Captain 2026-07-09):** (1) **Wake+inject stays law** — Captain DMs wake the Chair via the poller's tmux injection; every transport upgrade rides on it, never replaces it. (2) **Receipt discipline:** react on receipt with a **charter-carried reaction vocabulary** — class→emoji map (question→🤔, directive→🫡, urgent→⚡, file→📄, praise→❤️, default 👀/👌 …) picked deterministically (message-id hash rotates variants; Telegram's fixed reaction whitelist bounds the set), Chair T2 may override; then `sendChatAction` typing while gathering; `sendMessageDraft` "Thinking…"/streaming as progressive enhancement. (3) **Files both ways:** outbound briefings/cards render markdown → Telegram-native entities (HTML parse_mode; Rich-Message tables where they pay), documents over ~30 lines attach as files with a short rendered summary; inbound Captain files (photo/document/voice ≤20MB `getFile`) download to the inbox and inject their local path as session context — never silently dropped (today text-only). (4) Batch/FYI sends are `disable_notification` silent; the standing queue card is pinned (DM pins never notify); due/acted timestamps use `date_time` entities (captain-tz); ping-now may carry one reserved message effect.
- **Amendment 2026-07-10 — one-door allowlist +2 read-only pre-boot probes (PC-A integration; self-ratified per the 2026-07-07 full-autonomy grant):** the shrink-only allowlist in `framework/tests/test_single_telegram_door.py` grows by exactly two Captain-run errand helpers shipped by the Perfect Cabinet boot-path slice — `cabinet/scripts/telegram-validate-token.sh` (getMe token validation; exit codes distinguish rejected vs unreachable; token from env/`cabinet/.env`, never argv) and `cabinet/scripts/telegram-capture-chat-id.sh` (getUpdates with `timeout=0&limit=100` and NO offset parameter — never consumes updates, never sends; `--write` fills only-empty env names after TTY confirm / `--yes`). Both run pre-instance (Telegram is a post-first-receipt errand under the de-clouded boot), so they cannot ride `channel.py` (no framework env exists yet), and they are probes of the same class as the already-allowlisted `chair-preflight.sh` getMe health check. The P3 sender kill-list is untouched; the list stays shrink-only for anything that sends.

## 14. Out of scope (follow-ups filed separately)

- Upstream commitment-capture semantic dedup (3 rows for the EC promise — flavor-A screenpipe pipe); the gateway neutralizes its downstream blast either way.
- Taint-heuristic false-positive tuning (§5).
- Warroom/group-channel application of the same gateway (Captain DM first).
