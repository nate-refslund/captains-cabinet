# Monday / Make cascade audit — act-first surface evidence (TI-0)

**Wave-1 Lane L3 of the trust-inversion plan** · 2026-07-04 · branch `feat/fidelity-harness-design`
Companion artifact: `instance/config/act-first-surfaces.yml` (the DRAFT verdict + knobs).
Feeds: GERM-2 germline allowlist · TI-7 weekly re-audit baseline.

> **This is an audit, not an activation.** It records which Monday boards the
> act-first lane may write to unattended. Nothing here enables execution — the
> enforcing allowlist lands in GERM-2 (Captain-applied) and the Captain ratifies
> the flip. Where I could not positively clear a board, I say so; those boards are
> `unverified`, not `clean`.

---

## Verdict counts

| Verdict | Count | Meaning |
|---|---|---|
| **allow** | **1** | `5091706356` "Tasks" (AI Workspace) — create-only, capped |
| **blocked** | **7 classes** | real/near-certain outbound cascade — never act-first |
| **unverified (excluded)** | **4** | private AI-Workspace boards I could not positively clear |
| **reachable, not routing-surface** | ~522 | rest of the 534-board org — default-denied, not individually audited |

**Boards reachable by the audit token: 534 active** (all STEP workspaces).
**The one clean act-first surface today: `5091706356`, and only for `monday_task_create`.**

---

## What I ran (method)

Read-only Monday GraphQL (`https://api.monday.com/v2`, `API-Version: 2024-10`) via a
throwaway enumerator (`$CLAUDE_JOB_DIR/tmp/audit_monday.py`, **not committed**). The
token was loaded with the exact `action_exec._load_shared_env` pattern from
`~/.screenpipe/pipes/_shared/.env` and used **only** as the `Authorization` header —
never printed, logged, or written to any artifact.

Queries (all read-only, zero mutations):
1. `me { id name email account }` — establish the acting identity.
2. `boards(limit:100, page:1..6, state:active){ id name board_kind workspace{name} }` — inventory.
3. `webhooks(board_id: <id>){ id event board_id config }` — per-board push-integration snapshot, over the focus set + every board whose name matched `booking|crm|people|relationship|task|reflection|contact|deal|lead|sales`.
4. `boards(ids:[…]){ items_count permissions }` — corroboration on the primary board.

---

## Finding 1 — the audit token is a full-org identity (the crux)

`me` resolved to **user `48307552` — "STEPhie" (`stephie@stepnetwork.dk`, account "STEP")**.
Board enumeration returned **534 active boards** across every STEP workspace: CRM
(Win Tracker, Opportunities), Invoice management, Bookings, AdSales (Deals, Contacts,
Leads, Prices), Support & Service (PolAds Tickets), SN On/Off-boardings, Media &
Insights, plus the AI Workspace.

This is not a scoped bot. Any unattended write on this token (a) is attributable only
to "STEPhie" — indistinguishable from the human-driven STEPhie assistant — and (b) has
**org-wide blast radius**: a single mis-resolved `board_id` could land on a live CRM,
Bookings, or Invoice board. This is the primary argument for the dedicated agent token
(below), and the reason the executor's board allowlist must be a hard gate, not a hint.

---

## Finding 2 — per-board cascade verdicts (the routing surface)

### `5091706356` "Tasks" (AI Workspace) → **allow (create only)**
- `items_count: 1813`, `permissions: everyone` (org-visible, not a scratch board).
- Webhooks: `change_column_value` (id `157255553`) and `change_subitem_column_value`
  (id `157257050`), both `config: {}`. **No `create_item` subscriber.**
- **Therefore:** `monday_task_create` fires no webhook → the lowest-blast surface, and the
  only board cleared to `allow`. This matches the SEC-3 fallback allowlist `{5091706356}`.
- **Caveat (load-bearing):** the `change_column_value` webhook means a **`monday_task_update`
  (status/priority/due) on this board triggers a subscriber I cannot see** (Monday does not
  expose webhook destinations — Finding 4). So `monday_task_update` stays **propose-only** on
  this board until that webhook's destination is identified. The `allow` is scoped
  `kinds: [monday_task_create]` in the YAML for exactly this reason.

### Blocked — evidence-backed outbound cascades
| Board | id | Evidence |
|---|---|---|
| **Bookings** (STEP Network 3.0) | `1549621337` | status-change webhooks on `status0__1` at index 19 (`126701248`, `166272135`) — the trigger family behind **Make scenario 1952299 "Booking Changed" → emails Jannie**. The canonical known cascade. |
| **Deals** (AdSales) | `1623368485` | 4 webhooks incl. button-column launch points; live CRM revenue board. |
| **Contacts** (AdSales) | `1402911034` | `create_item` + `contact_email`-change webhooks — contact creation fans out. |
| **Sales Activities** (AdSales) | `1402911042` | `create_item` + board-relation webhooks on the live CRM. |
| **PolAds Tickets** (Support & Service) | `5092199368` | 0 API webhooks, **but** a support/ticket board — routes complainant/requester **email** via native automation and/or Make (PolAds complaint-conduit). Outbound-to-external-human near-certain. |
| **Team Task boards** | `1717613454` (AdOps), `1693359113` (Marketing), `1635510115` (Video), `1635251745` (AdTech), `1762038452` (Yield & Growth), `1711642084` (BI-Eng), `1711637245` (Email-Automation), `2028600766` (Audience) | all carry `create_item` + `link_to_teams` board-relation webhooks that **fan out to Microsoft Teams channels**. |
| **CRM / AdSales / Invoice / onboarding / commercial** (policy class) | many | company-operational boards touching customers, money, publishers, staff — blocked by workspace policy independent of webhook state, incl. `Prices` `5091003553`. |

### Unverified — excluded (default-deny)
| Board | id | Why not cleared |
|---|---|---|
| **People & Relationships** | `5096013693` | private, 0 API webhooks; PII + the never-write-by-index gotcha. Excluded pending a people-safe write contract. |
| **Reflections & Research** | `5096013783` | private, 0 API webhooks; **strongest promote-to-`allow` candidate** after a Make re-audit. |
| **Products** | `5091839409` | private AI-Workspace, 0 API webhooks; unverified vs the Make blind spot. |
| **Activities** | `5091999365` | private AI-Workspace, 0 API webhooks; unverified vs the Make blind spot. |

---

## Finding 3 — the @-mention / notification cascade class (executor obligation)

Monday `create_update` (and item-update note) bodies containing **@-mention syntax**
(`@name`, `@team`, or a raw Monday user-id mention token) generate a **notification AND an
email** to the mentioned user. This is a real outbound cascade that **no board verdict
captures** — it rides on body *content*, not board configuration. It is therefore an
**executor obligation**, not a board knob:

> **The L1 executor MUST strip / never emit @-mention tokens in any Monday body it writes.** [RT-A8]

This lands in SEC-3 (`action_exec.py`) alongside the provenance banner and the
`people|person|assignee|subscriber|owner` key rejection (assigning/subscribing a human
also emails them). Recorded in `act-first-surfaces.yml → executor_obligations` so the
allowlist and the obligations travel together. Per Nate's 2026-07-04 ruling, a plain
Monday *notification* is harmless; the **email** a mention/assignment sends to a non-Nate
human is the part that blocks — hence strip mentions even on `allow` boards.

---

## Finding 4 — audit blind spots (read this before trusting a "clean")

Being honest about what this audit **cannot** see is the point of the exercise.

1. **Make.com scenarios are invisible to me.** I have no Make API credentials, and the
   Cabinet MCP scope forbids the Make MCP for this work. So I audited Make **from repo +
   vault + memory evidence only** (Finding 5). Any board watched by a Make **"Watch
   Records" (polling)** trigger leaves **no Monday webhook** and is undetectable here.
   ⇒ A "0 webhooks" board is **not** proven cascade-free.
2. **Monday's `webhooks()` API never returns a webhook's destination URL** — only
   `id`, `event`, `board_id`, `config`. So even where a webhook exists (e.g. the Tasks
   board `change_column_value`), I can see *that* something subscribes but **not what**.
   The destination could be the dev-tasks plugin (benign) or a Make email scenario. I do
   not guess — I mark the path unverified.
3. **Native Monday automations (recipes) are not exposed** to this token's GraphQL. A
   board can email/Slack/Teams on a status change via a native recipe with **no webhook
   and no Make scenario** — invisible here. (Nate's ruling narrows the damage: native
   *notifications* are harmless; a native *email* recipe is not, and I cannot see either.)
4. **Scope:** 534 active boards; I individually webhook-audited the routing-surface
   focus set (~35 boards). The other ~500 are default-denied by policy, not individually
   cleared. `state:active` only — archived boards not scanned.

**Consequence for verdicts:** only boards I can positively reason about are `allow`.
Everything else is `unverified` (excluded) or `blocked`. The unverified boards get that
label **specifically because of blind spots 1–3**, and can only graduate to `allow` after
a Make-side re-audit (someone with Make creds confirms no scenario watches them) — which
is exactly the TI-7 weekly cascade re-audit's job, using this snapshot as its baseline.

---

## Finding 5 — Make.com evidence (from repo + vault, not the Make API)

Scenario IDs referenced across the repo/vault, classified by what they touch:

| Scenario | Name / role | Cascade class |
|---|---|---|
| **1952299** | "Booking Changed" (org: refslund.ai) | **email cascade** — watches the Bookings board, updates Monday CRM columns + **emails Jannie**. Pre-classified cascade-bearing; corroborated by the `1549621337` status webhooks. |
| 3902068 | "Screenpipe · Graph Read (Email)" | Graph **read** proxy (inbound email capture). Not a board cascade. |
| 9309900 | "Screenpipe · Graph Read (Teams)" | Graph **read** proxy. Not a board cascade. |
| 9437751 | "Graph Write" (email filing / isRead PATCH) | Graph **write** (mailbox filing) — outbound-ish but not Monday-board triggered. |
| 9313456 / 9313459 | Send Email / Send Teams | **outbound send** scenarios — invoked by the screenpipe comms path, not by Monday board changes. Out of scope for board act-first, but confirm they are never wired to a board the lane writes. |

**What I could NOT verify:** whether any of these (or any *unlisted* Make scenario) has a
**Monday "Watch Records" trigger** on a board in the act-first routing surface. That
requires Make API access I do not have. This is the single largest residual risk and the
reason `unverified` exists as a verdict.

---

## Recommendation — dedicated Monday agent token (design only; do NOT create)

Finding 1 shows unattended act-first cannot safely ride the `MONDAY_API_TOKEN`
(full-org "STEPhie"). Design:

- **Mint a dedicated Monday user** — e.g. "Cabinet Agent" (`cabinet-agent@stepnetwork.dk`)
  — **member of ONLY the allowlisted AI-Workspace boards** (today: `5091706356`; later,
  post-re-audit, `5096013783`). Its token lives in a new env var **`MONDAY_AGENT_TOKEN`**.
- **Payoffs:**
  1. **Attribution** — acted items show the agent identity, not "STEPhie"; undo and audit
     become unambiguous (this is also what the UNDO-3 `probe_monday` Nate-attribution
     check needs to tell "his hand" from "the lane's hand").
  2. **Server-side allowlist** — board membership *is* the allowlist. The agent literally
     cannot write to Bookings/Deals/CRM/Invoices because it is not a member. Defence in
     depth behind the executor's `act-first-surfaces.yml` check.
  3. **Fail-safe** — token absent ⇒ act-first **degrades to propose-only**, and NEVER
     borrows the full-privilege `MONDAY_API_TOKEN` for unattended writes. (Approved-card
     executions may still use `MONDAY_API_TOKEN` — the Captain judged those.)
- **Do NOT create it here.** This is design input for the Captain / SEC-3's
  scoped-token-preference leg. Creating a Monday user and re-scoping board membership is a
  Captain action.

---

## Done-when (audit acceptance)

- [x] Every board in the act-first routing surface has a recorded cascade verdict
      (`act-first-surfaces.yml`): 1 allow, 7 blocked classes, 4 unverified.
- [x] `act-first-surfaces.yml` parses and carries `confidence_floor: 0.65`, caps, and the
      executor obligations; DRAFT-gated behind Captain ratification.
- [x] @-mention cascade class documented as an executor obligation for the L1 lane.
- [x] Blind spots (Make invisibility, webhook-URL opacity, native recipes, scope) stated
      honestly; unverified boards labelled unverified, not clean.
- [x] `MONDAY_AGENT_TOKEN` agent-user recommendation recorded (design only).
- [ ] **Captain:** ratify the allowlist (flip `status: draft → ratified`) before the
      act-first flip; commission the Make-side re-audit to graduate `5096013783`.

*Baseline snapshot for the TI-7 weekly re-audit: allow=`{5091706356}`; Tasks-board
webhooks = `{157255553 change_column_value, 157257050 change_subitem_column_value}`. Any
drift (new webhook, changed event) freezes the board at runtime.*
