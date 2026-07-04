# Scoped auto-reply — Kristoffer UAT (graduated autonomy) — design

**Date:** 2026-06-25
**Status:** built, DISARMED. Not live on real traffic. Awaiting Nate's review of the sample + (if he agrees) one germline sanction + the arm.
**Captain choice:** option (a), "let's try (a) for this case" — when Kristoffer sends UAT feedback on Teams, the cabinet auto-sends him a bounded ack directly, scoped to him + UAT only. This is the **first time the cabinet auto-sends to a human**, so the whole thing is built safety-first.

---

## 1. The real outbound path (traced before designing — gather-then-decide)

There are **two outbound stacks** in the cabinet today; both end at the *same* byte-egress libraries (`email_lib` / `teams_graph_lib` in the screenpipe `_shared`):

1. **Brain MCP `queue_draft`** (`~/.screenpipe/pipes/brain-mcp/server.py`):
   `queue_draft(person, channel, draft, why, ...)` → sends a Telegram prompt `kind="draft-reply"` whose payload matches the screenpipe telegram-bot `_reply_draft` handler. **The actual send is NOT in `queue_draft`** — it happens in `telegram-bot/handlers.py::_reply_draft._deliver()` *when Nate replies "send"*, which calls `email_lib.send_email` / `teams_graph_lib.send_teams_to_email`. This is the path `.claude/rules/brain-bridge.md` names as "the ONLY outbound path."

2. **Chair-owned draft flow** (`framework/frontdoor/chair_drafts.py`) — the LIVE path per Nate's 2026-06-24 directive *"make the drafts end here in this chat"*:
   `present_draft(...)` presents in the Chair chat via `framework.frontdoor.channel.send`, stores the draft at `cabinet:draft:<pid>`; on Nate's "send" reply the Chair calls `deliver_draft(pid)`, which sends via the same `email_lib` / `teams_graph_lib`. The screenpipe bot is back-end only here.

**Conclusion:** the human approval is a *thumb-tap that triggers an already-built, approved send backend*. There is no magic "auto-approve" switch inside `queue_draft`; the seam is simply **"call the approved send backend without waiting for the tap."**

**Precedent already in the tree:** `framework/authority/veto.py` does exactly this for the internal-comms veto window — it auto-sends on TTL expiry "through the SAME approved `queue_draft` backend," with the backend **injected**, idempotent, kill-switched, dead-lettering, and explicitly **NOT wired into the policy engine** ("a later Captain-authorized pass"). This auto-reply follows that template precisely.

So: **no raw Teams/Graph/Make bypass.** The auto-send is the approved `deliver_draft` (or `queue_draft`) backend, fired by a scoped code rule instead of Nate's thumb, **for this one cell only**.

---

## 2. What was built (the safe parts)

Package `framework/autoreply/` — three files + tests:

| File | Role |
|------|------|
| `kristoffer_uat.py` | **Pure decision + compose core.** Scope detection, UAT-report detector (EN+DA), bounded-ack template, the three gates, the orchestrator `handle_message`. Every side effect is **injected** (send, copy-to-Nate, Redis, audit, route) — unit-tested with fakes, no real Redis/network/Telegram. |
| `wiring.py` | **Live wiring — ships DISARMED.** Supplies the real collaborators: the approved send backend (`chair_drafts.present_draft` + `deliver_draft`), the Nate-copy (`channel.send`), the audit (JSONL + `agent_reasoning.log`), the bug-routing (`notify-officer.sh polads-ceo`). Exposes `process`, `dry_run_sample`, `arm`, `disarm`, `status` + a CLI. |
| `tests/test_kristoffer_uat.py` | 39 tests over the safety contract. All green. |

### The mechanism (per inbound Kristoffer Teams message)

`handle_message` runs **three gates in order, each fail-closed**, then acts:

1. **SCOPE** (pure, no I/O) — must be FROM Kristoffer's resolved identity (slug `Kristoffer-Møller-Nielsen`, accent-folded variants, or primary email `krmoj@step.dk`), ON Teams, AND match the UAT bug-report shape. Any miss → `declined` (caller falls back to the normal propose-only `queue_draft` gate). Checked **before** arm-state so an out-of-scope message is handled identically whether armed or not.
2. **ARM** — the Redis flag `cabinet:autoreply:kristoffer-uat:enabled` must read **exactly `"1"`**. Absent / any other value / Redis-down → `disarmed`. **This is how it ships — DEFAULT OFF.**
3. **GLOBAL KILLSWITCH** — `cabinet:killswitch` must not be `active` (the same emergency halt every officer honours). Active → `halted`.
4. **ACT** — route the bug to polads-ceo (first, so the bug is never lost even if the ack hiccups), fire the approved send backend, **copy the exact ack to Nate** via `channel.send`, audit every outcome.

### The bounded ack (never a substantive reply)

Templated, three claims only — **received + routing-to-team + ETA**:

> got your UAT report on **<topic>** — thanks, that's logged and i'm routing it to the team now (ref <X>). **<ETA>**. i'll follow up here once there's a fix.

- `<topic>` is pulled **verbatim** from Kristoffer's own first line (greeting stripped), never paraphrased — paraphrase is a chance to misstate.
- It can **never** assert a fix, a root cause, or any substantive claim. No free-form LLM text leaves the machine on this path.
- Teams house style: lowercase-casual, **unsigned** (Teams is never signed — `voice.md`). No `nate_model`/voice content is interpolated.

### The four safety rails (all built)

- **Nate-visibility** — every auto-send (and every dry-run sample) emits a COPY to Nate's Telegram via `framework.frontdoor.channel.send`, labelled `AUTO-SENT to Kristoffer` (or `SAMPLE (dry-run…)`), **before the function returns**. A copy-send failure is surfaced in the result, not swallowed.
- **Audit log** — every decision (`sent` / `declined` / `disarmed` / `halted` / `send-failed`) writes a JSONL line to `~/.cabinet/autoreply/kristoffer-uat.jsonl` AND mirrors to the brain reasoning log (`agent_reasoning.log`, pipe `autoreply-kristoffer-uat`) for the reasoning-review governance loop.
- **Kill-switch** — `cabinet:autoreply:kristoffer-uat:enabled`, checked before every auto-send; `disarm()` deletes it instantly. `arm()` supports an optional TTL so an arm can auto-expire (e.g. arm for a UAT session). **Defaults OFF / disarmed.**
- **Bounded ack only** — see above.

---

## 3. The sample (produced; sent to Nate only)

`python -m framework.autoreply.wiring sample` → composed a labelled SAMPLE and sent it to Nate's Telegram only (dry-run: **nothing to Kristoffer, nothing routed to polads-ceo** — routing shown as "would route… simulated"). The sample text:

> 🤖 SAMPLE (dry-run, NOT sent to Kristoffer) — Kristoffer UAT auto-reply
> topic: the publisher VIES auto-fill is broken on staging…
> ———
> got your UAT report on the publisher VIES auto-fill is broken on staging… — thanks, that's logged and i'm routing it to the team now. we're aiming to have a fix in the next deploy. i'll follow up here once there's a fix.
> ———
> would route→polads-ceo (simulated, not routed)

Nate reviews this exact behaviour **before** anything is armed.

---

## 4. What needs Nate before it can go live (NOT done here)

Two explicit, Captain-only steps — neither is taken by this build:

### 4a. Germline sanction (FLAGGED — do not self-edit)

`.claude/rules/brain-bridge.md` is **germline** (pre-tool-use hook write-protects it; officers propose, only Nate applies). It currently states, unconditionally:

> "The ONLY way an officer sends anything to a human outside this machine … is the brain server's `queue_draft` tool. Every queued draft goes through Nate's human approval gate on Telegram before anything is sent."

A scoped auto-send **relaxes** that "before anything is sent" clause for one cell. Even though the auto-send still goes **through the approved backend** (not a raw API), the *human-approval-gate* invariant is what's being narrowed. **This needs a one-line germline carve-out that Nate applies himself**, e.g.:

> *Exception (Captain-sanctioned 2026-06-25): the scoped Kristoffer-UAT auto-reply lane (`framework/autoreply/`) may auto-approve its own bounded ack for the narrow case [Kristoffer + Teams + UAT-report], kill-switched at `cabinet:autoreply:kristoffer-uat:enabled` (default OFF), with every send copied to Nate and audited. No other auto-send is sanctioned.*

The same one-line exception ideally also lands in `.claude/rules/courses-of-action.md` (also germline) since auto-acking is a single-action-without-the-full-chain by design for this cell. **I did not edit either file.** Proposed wording above; Nate's call.

> Note: `framework/authority/veto.py` set the precedent that an auto-send through the approved backend is architecturally acceptable, but it was never wired live, so the germline text was never actually relaxed. This is the first lane that would *use* the seam on real human traffic — hence the explicit sanction now.

### 4b. Arm the kill-switch

`python -m framework.autoreply.wiring arm [ttl_seconds]` → sets `cabinet:autoreply:kristoffer-uat:enabled=1`. Until then, `process()` returns `disarmed` on every real message. Disarm any time: `python -m framework.autoreply.wiring disarm`.

### 4c. (Separate, later) wire `process()` to live inbound

`wiring.process(sender, channel, text)` is the entry point, but **nothing calls it on live Teams traffic yet** — exactly like `veto.py` is "not wired into pre-tool-use." The detection input would be the comms-officer's existing Teams read (Make Graph-read scenario 9309900) or the brain conversation index. Wiring that trigger is a separate, Captain-authorized pass once 4a + 4b are done and Nate has watched a few samples.

---

## 5. Why this is the right shape (altitude)

- **L1 (this case):** Kristoffer gets an instant, honest, bounded ack; the bug still reaches polads-ceo; Nate sees every send. Removes a real latency wart (Kristoffer waiting on "did it land?") without risking a wrong autonomous claim.
- **L2 (the cabinet):** reuses the proven `veto.py` injected-backend / kill-switch / fail-closed pattern; adds no new egress path; keeps `queue_draft`/`deliver_draft` as the single egress; the trust-ladder vocabulary (`framework/learning/trust_ladder.py`) already frames this as an `ive-done` rung earned per-cell — this is the manual, scoped first instance of that. *[Note 2026-07-04: that module was removed under the earn-demotion ruling — reversible autonomy is day-one with undo, demoted on evidence, never rung-earned. The egress hard lines in this bullet stand.]*
- **L3 (graduated autonomy):** this is the template for *every* future auto-send — narrow scope in code, kill-switch default-off, copy-to-Captain, full audit, germline sanction per relaxation. Capability is built day-one; trust (the arm) stays Nate's.
