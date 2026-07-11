# Comms MCP — the LLM-native, channel-agnostic officer surface (spec)

**Status:** C2 BUILT (LLM-native Comms MCP on master @e3c3b572, registered `cabinet/mcp-scope.yml:149`); remaining §8 phases still design — header trued 2026-07-11 (docs-track-code)
**Date:** 2026-07-09
**Author:** Captain-directed (Nate: "implement properly, to the FOUNDATION of cabinet — not just my instance; ALL the TG features are worth it")
**Layer:** `framework/` (mechanism — MCP server, tool surface, channel Protocol) + `instance/config/` (which adapter, charter, scope)
**Builds on:** the attention gateway P1–P5 (situation identity, world-grounding, one-door channel, charter/standing-cards, T2). This is the gateway's **officer-facing surface** + the full channel feature set.

---

## 1. Problem

The gateway (P1–P5) made the cabinet's *own* messaging smart, but the channel features live as `framework/frontdoor/channel.py` Python functions + a poller that relays inbound as bracketed text into the tmux session. Consequences:

1. **Not LLM-native.** An officer that wants to send a poll, edit a standing card, react contextually, set typing, pin, or open a per-lane thread has **no tool** — it must shell out to python. So officers don't use these features at all.
2. **Reactions are deterministic** (the poller picks them) because the LLM has no `react` tool.
3. **Not foundational.** The features are Telegram-specific and instance-shaped. A clean-room / Flavor-B deployment, or a future non-Telegram channel, inherits none of it.
4. **Missing features.** Forum topics, pins, streaming "Thinking…" drafts, `date_time` entities, and Rich-Message tables aren't built.

## 2. The law

> **The cabinet talks to its Captain through ONE channel-agnostic seam, and every officer reaches it through ONE LLM-native MCP whose tools speak "comms," not "telegram." A channel (Telegram today) is an ADAPTER behind that seam; the officer tools, the gateway gating, and the feed journal never name it. So any captain, any flavor, any future channel inherits the same foundation — and the Captain's instance only chooses which adapter and charter to bind.**

FOUNDATION-FIRST, applied: the MCP + tool surface + channel Protocol are `framework/`; the Telegram adapter is a bound backend; the charter/scope/adapter-choice are `instance/`.

## 3. Architecture

```
 officer (LLM)                         framework                         instance
 ────────────         ┌───────────────────────────────────────┐      ┌──────────────┐
  mcp__cabinet_comms__send_card   ─┐                            │      │ sources.yml  │
  ...react / poll / pin / thread  ─┤   comms MCP server         │      │  channel:    │
  ...set_status / read_feed       ─┘   (framework/comms/mcp)    │      │   telegram   │
                                   │        │                   │      └──────────────┘
                                   │        ▼                   │      ┌──────────────┐
                                   │   attention.gate  ─────────┼──────│ comms-charter│
                                   │   (charter, dedup,         │      └──────────────┘
                                   │    quiet-hours, T2)        │
                                   │        │                   │
                                   │        ▼                   │
                                   │   ChannelAdapter (Protocol)│
                                   │        │  bound by         │
                                   │        ▼  sources.yml      │
                                   │   TelegramAdapter ─────────┼──►  Bot API
                                   │   (framework/comms/adapters)│
                                   │        │                   │
                                   │        ▼                   │
                                   │   feed journal (P3)        │
                                   └───────────────────────────┘
```

- **`framework/comms/channel_adapter.py`** — the `ChannelAdapter` **Protocol** (the seam): `send_card`, `edit_card`, `react`, `poll`, `set_status`, `pin`, `open_thread`, `answer_tap`, `download_inbound`, `capabilities()`. Channel-neutral vocabulary — no "telegram" in a method name. `capabilities()` lets an adapter advertise what it supports (a channel without polls returns `poll: false`; the tool degrades gracefully).
- **`framework/comms/adapters/telegram.py`** — the Telegram adapter: wraps the existing `channel.py` primitives + the new ones (topics/pins/date_time/effects/streaming). This is where "telegram" lives, and ONLY here.
- **`framework/comms/get_channel.py`** — resolver: reads `instance/config/sources.yml → channel:` (default `telegram`; `null` adapter for a headless/clean-room box), binds the adapter once per process. Sister of `framework.sources.get_source()` (the brain-bridge seam) — same pattern.
- **`framework/comms/mcp/`** — the MCP server (stdio + http, like the cabinet + library MCPs): tool schemas + dispatch. Every tool call routes **through `attention.gate`** (charter class, dedup, quiet-hours, standing-card, T2) then the bound adapter, and journals to the feed. So an officer's `send_card` inherits the whole gateway automatically — an officer CANNOT bypass the charter or the one-door.
- **Scope:** granted per officer in `cabinet/mcp-scope.yml` (like `brain`, `notion`), declared in `instance/config/extensions.yml`. The charter's external-comms floor still holds — the MCP has NO tool that sends to a human off-machine (that stays `queue_draft`).

## 4. The LLM-native tool surface (channel-agnostic)

| tool | what the officer does | gateway path | channel primitive |
|---|---|---|---|
| `send_card(situation, body, urgency?, class?)` | present a card to the Captain | full gate: classify → dedup → quiet-hours → standing-card | send / edit |
| `edit_card(situation_key, body, state?)` | update a standing card in place | identity → edit | editMessageText |
| `react(message_ref, emoji)` | contextual LLM reaction (the "LLM reactions" ask) | floor-checked | setMessageReaction |
| `poll(question, options[], multi?)` | AskUserQuestion-style select | charter class `poll` | sendPoll |
| `set_status(kind="thinking"\|"typing")` | show typing / streaming "Thinking…" | ephemeral, ungated | sendChatAction / sendMessageDraft |
| `pin(situation_key)` / `unpin()` | pin the standing decision-queue card | floor-checked | pinChatMessage |
| `open_thread(lane)` / `send_card(..., thread=lane)` | per-lane thread in the DM | charter | forum topics in private chat |
| `answer_tap(tap_id, toast?)` | ack an inline-button tap | — | answerCallbackQuery |
| `read_feed(cursor)` | the never-re-read cursor read (P3) | — | feed journal |
| `read_inbound(ref)` | fetch a Captain-sent file's local path | — | getFile |

`callback_data`/tap ids stay ≤64 bytes (ids only; chain state in Redis/ledger). Every tool is **fail-soft + gated**; an adapter that lacks a capability makes the tool a logged no-op, never an error.

## 5. All the TG features (Nate: "ALL worth it") — mapped

Built into the Telegram adapter + surfaced as tools/charter:

1. **Forum topics in the DM** (9.3/9.4) — `open_thread(lane)` → per-lane threads (PolAds / STEPhie / framework / personal) inside the Chair DM, no group. `createForumTopic` (private-chat supported); close/reopen aren't (documented limit) — we only create + route.
2. **Pinned standing card** — `pin()` pins the decision-queue card to the DM top bar. DM pins never notify.
3. **Streaming "Thinking…" drafts** (`sendMessageDraft`, 9.3+) — `set_status("thinking")` streams a draft placeholder while the officer composes; the final persists via `send_card`. Progressive enhancement (falls back to `sendChatAction` typing).
4. **`date_time` entities** (9.5) — due/acted timestamps rendered in the Captain's tz natively (the Timezone principle), not hand-formatted strings.
5. **Rich-Message tables** (10.1) — chain cards as real tables (step | action | state | gate) with collapsible evidence blocks; charter opt-in per class, graceful fallback to the terse text card.
6. **Message effects** (`message_effect_id`) — one reserved effect for ping-now tier (charter-configured), never elsewhere.
7. Already shipped (P3 + telegram-hardening branch): reply-to-specific, edit-in-place, silent, markdown→HTML, inline keyboards + callbacks, reactions (deterministic receipt), inbound files, **polls**, **typing**, message-id capture, feed journal.
8. **Unavailable (documented):** native checklists — business-connection-gated; a plain bot can't use them. The per-step widget stays inline-keyboard-based.

## 6. LLM reactions — the two-layer design

Never put an LLM in the poller's receive hot-path (latency + a failure mode on the ack). Instead:
- **Layer 1 (instant, deterministic):** the poller reacts on receipt with the charter reaction-vocabulary pick — fast, no LLM. Unchanged.
- **Layer 2 (contextual, LLM):** when the officer reads the relayed message, it calls `react(message_ref, emoji)` to UPDATE to a contextual reaction. Telegram allows one reaction/message, so the LLM's choice supersedes the instant one. This is "LLM-based reactions" done without risking the receive loop.

## 7. Framework / instance split (FOUNDATION-FIRST)

| framework (`framework/comms/`) | instance (`instance/config/`) |
|---|---|
| MCP server + tool schemas, `ChannelAdapter` Protocol, `get_channel` resolver, TelegramAdapter (the only place "telegram" appears), gate routing, feed journaling, capability degradation | `sources.yml → channel:` (which adapter), `comms-charter.yml` (routing/reactions/effects), `extensions.yml` + `mcp-scope.yml` (who gets the MCP) |

A clean-room / Flavor-B box binds the `null` channel adapter → every tool is a logged no-op, framework stays runnable. No captain-specific literal in `framework/comms/` (the launcher-hardcode ratchet extends to cover it).

## 8. Phases (each independently shippable, gauntlet + review each)

| Phase | Ships |
|---|---|
| **C0 primitives** | the missing channel.py Telegram primitives: `open_thread`/topics, `pin`/`unpin`, `date_time` entity rendering, `message_effect`, `send_status` streaming-draft (+ the already-done poll/typing on `feat/telegram-hardening`). Germline carry-patch; tests. |
| **C1 channel seam** | `ChannelAdapter` Protocol + `TelegramAdapter` (wraps channel.py) + `get_channel` resolver + `null` adapter + `sources.yml → channel:`. Launcher-hardcode ratchet extended. |
| **C2 comms MCP** | the MCP server (stdio+http) + tool surface (§4), each tool routing through `attention.gate` + adapter + feed. Registered in `extensions.yml`, scoped in `mcp-scope.yml`. |
| **C3 officer adoption** | cos/CoS role note: react contextually (Layer 2), open per-lane threads, pin the queue, use `set_status` while gathering; T2 apply_verdict wired to the `send_card` tool (closes the P5 Chair loop). |
| **C4 rich surfaces** | Rich-Message tables + collapsible evidence for chain cards; charter opt-in; fallback pinned by golden render. |

## 9. Non-negotiables (carried from the gateway)

- **External-comms floor** — no tool sends to a human off-machine; `queue_draft` only, per-item approved. In every posture.
- **One door** — the adapter is the only `api.telegram.org` caller (the CI tripwire already enforces it); the MCP routes through the gate, never raw.
- **Feed journal** — every outbound tool call journals (audit); `read_feed` is cursor-based (never re-read).
- **Charter-owned presentation** — reactions, effects, verbosity, banner visibility all come from the charter; the MCP tools carry no hardcoded style.
- **Germline** — channel.py + gate.py + situation/feed/acted_overlay are germline; adapter + MCP server join the lock set at C2 (they carry the send perimeter).
