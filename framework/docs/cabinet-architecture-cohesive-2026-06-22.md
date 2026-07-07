# Cabinet × Screenpipe — The Cohesive Architecture

**Status:** committed 2026-06-22 (ratified with Nate over the 2026-06-21/22 sessions).
**Supersedes:** the "draft-lane in front" framing in `docs/screenpipe-cabinet-convergence-map-2026-06-21.md` (that doc's planes/disposition still hold; its acting-lane-as-product is replaced by §3 here).

---

## 0. The one-sentence architecture

> **screenpipe is System 1 (senses + memory, behind). The cabinet is System 2 (the one brain, in front). Only the cabinet talks to Nate, and it does so through one Telegram channel — composing every outbound, judging before it sends, receiving every reply, and orchestrating whatever the reply sets in motion.**

Everything below follows from that.

## 1. Why one brain (the property nothing else can give)

Today ~30 screenpipe pipes each fire into Telegram independently. On 2026-06-22, before noon, that was **8 separate pings from 8 pipes**. No single thing owns the full provenance of any message, so nothing can intelligently handle the reply.

The cohesive architecture is the *only* shape in which both of these are simultaneously true:
1. **"The thing that messages me knows everything"** — what it sent, why, who, the sources, the confidence — because **one brain composed it** and therefore holds the whole record.
2. **"It can act after my reply"** — reply to Lisa → *then* adapt PolAds — because the same brain that owns the thread also orchestrates the officers.

System 1 / System 2 is the right mental model:
- **System 1 = screenpipe** — fast, automatic, perceptual, always-on, narrow. Capture + memory + cheap reflex suggestions.
- **System 2 = cabinet** — deliberate, context-holding, orchestrating, consequential. It *mediates what reaches consciousness* (Nate). System 1 feeds it; System 1 never grabs the wheel (never DMs Nate directly).

## 2. The shape

```
                YOU  ──  one channel (@NateHQChairBot)
                 ▲ │
   only the      │ │ your message / reply
   cabinet  ─────┤ ▼
   speaks to     │  CABINET — the one brain (System 2)
   you           │   • sole sender + sole receiver on Telegram
                 │   • owns full context of everything it sends
                 │   • JUDGES before sending (worth it? enrich? make a task?)
                 │   • routes your inbound → assistant / PolAds CTO / CPO …
                 │   • drives multi-step: reply → THEN adapt PolAds → ship
         reads   │ │ feeds (reflexes + triggers as INPUT, never to you directly)
                 ▼ │
            SCREENPIPE (BEHIND) — System 1
              • capture: email, Teams, audio, screen, calendar
              • memory: the vault + embeddings brain (queryable)
              • reflex drafts/triage → SUGGESTIONS the cabinet judges
```

## 3. The front-door (the one genuinely-new build)

Everything that wants to reach Nate, and everything Nate sends, passes through one structure owned by the persistent Chair officer:

1. **Durable intake.** Pipes and triggers write here (Redis stream / queue) instead of Telegram. Durable so nothing is lost if the officer is restarting/compacting — it drains when back.
2. **Inbound + intent-router.** Nate's messages arrive via the Channels plugin (the Chair is the *sole* poller). The router reads intent and dispatches: quick ask → assistant-reflex; product change → lane officer (PolAds CTO/CPO); decision → the Chair handles directly.
3. **Composer / judge.** Drains intake, **dedupes and weaves across sources**, decides what actually merits Nate's attention (start conservative — forward most, just unified + enriched; tighten as trust grows), and composes one message carrying full provenance (inbound, sources, why, confidence).
4. **Reply binder.** Maps Nate's reply to the originating record, drives the consequence — including multi-step orchestration — and records it to the consequence ledger (proof → the ladder).
5. **Trigger registry.** The at-time / interval / on-event entries Nate authors (see §4), all of which wake the Chair.

**Reuse note:** the *drafting + retrieval* that screenpipe's `draft_lib` already does well becomes a **tool the Chair calls**, not a thing screenpipe sends. The Chair composes; `draft_lib` is one of its instruments.

## 4. Triggers — one bus, three flavors

All scheduling/automation Nate asks for is the same primitive: a trigger that wakes the one brain. Nate authors them conversationally through the one channel.

| Nate says | Trigger | Behavior |
|---|---|---|
| "remind me tomorrow about X" | **one-shot, at-time** | stores X *with full context*; wakes tomorrow; **re-checks reality before pinging** |
| "do this every Y" | **recurring, interval** | repeating wake; each fire runs "this"; reaches Nate only if warranted |
| "whenever Z happens, do A" | **on-event, predicate** | standing rule `{when: Z, then: A}`; senses' stream matched against Z; a match wakes the Chair to do A |

Properties that require these to live in the brain (not a dumb scheduler):
- **Context preserved at creation** — stores the record, not the string.
- **Gather-then-decide at fire** — re-checks before acting (did Nate already reply? did the deploy recover?); closes silently if moot. Never a stale nudge. (Generalizes the discipline already hard-won in the pipes.)
- **Woven, not blind** — a 9:00 reminder + the 7:00 brief + an 8:30 deploy-fail are one woven message, not three pings.
- **Ladder-governed when A is an action** — read-only reminders fire freely; actions ("fix it + open a PR") start as *propose* and earn autonomy.

**The unification:** reactive pipes + scheduled pipes + Nate's reminders/rules are all *triggers (at-time · interval · on-event) feeding the one brain*. There is no separate reminder app, automation engine, and pipe estate — one trigger bus, one composer, one voice.

**Mechanism:** the cabinet's existing `cron → Redis trigger → Channel` path delivers into the warm Chair session (which is *why* a standing `/loop` isn't needed — a permanent `/loop` is the cabinet anti-pattern). Claude's builtin `CronCreate` is the native equivalent timer for dynamic, Nate-authored time triggers. Either way the work runs in the one brain; triggers never each talk to Nate.

## 5. The pipe estate — four fates

| Fate | Which | What happens |
|---|---|---|
| **Stay** (senses) | mail/Teams capture, embeddings index, conversations-sync, meeting capture, product-ops sync | Untouched screenpipe crons — memory plumbing, behind the cabinet. |
| **Rewire** (valuable reasoning) | morning-brief, inbox-triage, draft sweeps, commitment surfacing, what-needs-you-now, pre-meeting-brief | Schedule survives as a **trigger into the Chair**, not a message to Nate. The Chair composes/judges/dedupes and sends once. |
| **Absorb** (already cabinet functions) | reasoning-review, architect/self-improvement, voice + self-knowledge | Become officer-native scheduled tasks (the cabinet already has reflection + 24h evolution loops + captain-model/patterns/intents). |
| **Retire** (redundant / zero-value) | the zero-engagement Monday-insight cluster (screenpipe's own architect flagged these), any pipe whose only output is an ignored ping | Delete, don't migrate. |

## 6. Reused vs rewired vs new (this is NOT a from-scratch rebuild)

| Reused as-is | Rewired (not rebuilt) | Genuinely new |
|---|---|---|
| screenpipe capture; the vault + embeddings brain (the memory); `draft_lib` drafting + retrieval (now a *tool*); person intel; commitments; the cabinet ledger / officers / governance; the brain-MCP bridge | screenpipe reasoning pipes stop DMing Nate → write to the intake; the Chair becomes sole Telegram poller; reply-handling moves from regex handlers into the Chair (an upgrade) | the **front-door**: intake + intent-router + composer/judge + reply-binder + trigger-registry, and the **orchestration** (reply → route to officer → multi-step work) |

≈80% is reuse/rewiring. We *demote* screenpipe to behind and build the one missing layer.

## 7. Operational invariants

- **Durable intake** — nothing lost across officer restarts.
- **Reliably-on** — the cabinet is now the only channel; the Chair must be supervised/auto-restarted.
- **Sole poller** — only the Chair long-polls the bot; screenpipe goes fully silent on Telegram.
- **Judge conservative → tighten** — start by forwarding almost everything (unified + enriched); increase filtering only as trust grows (the ladder, applied to *what reaches Nate*).
- **Gather-then-decide** — every trigger re-checks reality at fire time.
- **Ladder for actions; never auto-merge / auto-deploy** — work is proposed and reviewed; Nate holds the ship decision until a lane earns autonomy.

## 8. Build sequence

1. **Front-door first** (the foundation): durable intake → Chair as sole poller/sender → composer/judge → reply-binder → trigger-registry. Start with screenpipe's outputs routed in and one unified morning message.
2. **Rewire the reasoning pipes** into the intake; **retire** the dead cluster.
3. **First orchestration demo:** a real PolAds task flows through the front-door end-to-end — e.g. the Critical security bug (`lib/auth/partner-access.ts` impersonation-cookie) → CTO officer → reviewed PR → Nate's merge call. This is the thing screenpipe structurally cannot do, and the proof the cabinet earns its existence.
4. **Author-by-talking triggers** (§4) come online with the registry: reminders + recurring + crisp-events early; fuzzy-events (LLM-evaluated predicates) follow.
