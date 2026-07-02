# Calendar system — Outlook calendar read + auto-accept (design)

**Status:** design + phase-1 build (2026-06-25). Comms-officer owns calendar
long-term; this is screenpipe + Make-scenario infrastructure, built in place.
**Posture:** propose-first. Auto-accept only on a clean no-conflict invite;
**never auto-decline** — a clash always escalates to the Chair. Inviting people
and booking rooms are phase 2/3 (one needs admin-consent — see below).

> **⚠️ Scope-blocked update (2026-06-25):** the permission verdict below assumed
> `Calendars.ReadWrite` (delegated) is **self-serve**. It is **NOT** in the JFM
> tenant — it needs **tenant-admin consent Nate doesn't have**. So this Graph
> design is **gated** until/unless admin grants the scope. The **working
> workaround stack** — read/conflict-check via **Apple Calendar** + respond via
> **iMIP email** + **OWA** fallback, all with **no new scope** — is in
> **`docs/email-calendar-imip-2026-06-25.md`** (with a runnable prototype). Build
> that now; keep this design for if/when the scope unblocks (it's simpler then).

## The gap

The comms layer reads + sends **email (Outlook)** and **Teams** via Microsoft
Graph through the Make proxy (`email_lib.msgraph_call`, connection 4264707 =
`naref@stepnetwork.dk`). It does **not** touch the **calendar**. So:

- Nate's upcoming events and incoming invitations are invisible to the Cabinet.
- Invitations can't be responded to (Accept/Decline) from the runtime.
- And — the regression that triggered this — a meeting-invite *email* (e.g. Lisa
  Stentoft's recurring **"Ugentlig Planlægning – Agenda"**) gets captured as a
  normal `received` message and surfaces in the draft-lane as **"awaiting your
  reply,"** so the lane drafts a prose reply to an invite. An invite is answered
  by a calendar action, not an email. **Phase 1 fixes that classification now**
  (it needs no new permissions) and lays the read foundation.

There IS a Google-Calendar reader in `sp_lib` (`gcal_events_all`,
`gcal_meetings_in_window`) used by morning-brief/pre-meeting-brief — but that's
Nate's *Google* calendar via the screenpipe Google proxy. Nate's **work**
calendar is in **Outlook/Graph**, which has no reader yet. This design adds the
Graph calendar path, mirroring `sp_lib`'s normalized event shape so downstream
consumers (briefings, conflict checks) see one event schema.

---

## Capability — what calendar needs

| Capability | Graph scope (delegated) | Admin consent? | Phase |
|---|---|---|---|
| Read events (upcoming + invitations) | `Calendars.ReadWrite`¹ | **No** | 1 |
| Respond to invites (accept/decline/tentative) | `Calendars.ReadWrite` | **No** | 2 |
| Create events / invite people | `Calendars.ReadWrite` | **No** | 2 |
| Find / book meeting rooms | `Place.Read.All` | **Yes** | 3 |

¹ Read alone could use `Calendars.Read`, but respond + create need
`Calendars.ReadWrite`, and one scope covers all three of read/respond/create —
so request `Calendars.ReadWrite` once and the whole core capability is unlocked
without a second consent round. (`Calendars.ReadWrite.Shared` would only be
needed to act on *other people's* shared calendars — not in scope.)

### Permission verdict (the load-bearing residual)

- **`Calendars.ReadWrite` (delegated) — admin consent NOT required.** It acts on
  the signed-in user's own mailbox. **Self-serviceable by the Chair** in the
  Azure portal (Nate cleared portal/Chrome work): App registrations → the app
  behind connection 4264707 → API permissions → Add → Microsoft Graph →
  **Delegated** → `Calendars.ReadWrite` → and grant **user** consent. Because
  the JFM tenant's default "users may consent to apps accessing data on their
  behalf" applies to non-admin-consent scopes, this can be added and consented
  without a tenant admin. After it's added, the Make connection 4264707 must be
  **re-authorized once** (re-run the OAuth on that connection) so the refreshed
  token carries the new scope. *(Source: Microsoft Graph permissions reference —
  Calendars.ReadWrite delegated, Admin consent required = No.)*

- **`Place.Read.All` (delegated) — admin consent REQUIRED.** Reading the org's
  room lists / conference rooms (`findRooms` / `findRoomLists`) is tenant data,
  so a tenant admin must consent. **This is the one genuine Nate/Bjarke
  residual**, and it gates **only phase-3 room-booking** — not read, not
  invite-response, not create-event with a free-text location. *(Source:
  Microsoft Graph permissions reference — Place.Read.All delegated, Admin
  consent required = Yes.)*

**Bottom line:** the entire useful core — read the calendar, auto-accept clean
invites, escalate clashes, and even create events / invite people with a
typed-in location — ships on a **self-serve** permission the Chair can add.
Only structured **room discovery/booking** needs the admin-consent scope, and
that's deferrable to phase 3.

> Until `Calendars.ReadWrite` is added + the connection re-authorized, calendar
> read returns nothing. The phase-1 **classification fix below is independent**
> of this and is live now.

---

## Make scenarios (Screenpipe folder 510964)

The existing folder has READ (email 3902068, Teams 9309900) + SEND (email
9313456, Teams 9313459), all on azure connection 4264707. The proxy pattern is
fixed by `email_lib`: **Make has no `json()`** — Python builds the full Graph
body and Make forwards it raw as `{body}`; the `{url}`/`{method}`/`{filter}`/…
mappers pass through verbatim. Calendar reuses that exact contract, so
`email_lib.msgraph_call(...)` already works for calendar GETs the moment the
scope lands — the new scenarios below are the **write/respond** paths that need
their own webhooks (the read scenario can't return write bodies; same reason
`MSGRAPH_WRITE_WEBHOOK` exists separately from `MSGRAPH_MAKE_WEBHOOK`).

| New scenario | Graph call | Webhook env (in `_shared/.env`) | Phase |
|---|---|---|---|
| **Calendar READ** | `GET /v1.0/me/calendarView?startDateTime=…&endDateTime=…` (and `GET /v1.0/me/events` for invitations) | reuse `MSGRAPH_MAKE_WEBHOOK` (read proxy already returns GET bodies) | 1 |
| **Invite RESPOND** | `POST /v1.0/me/events/{id}/accept` \| `/decline` \| `/tentativelyAccept` (body: `{comment, sendResponse:true}`) | `MSGRAPH_CAL_RESPOND_WEBHOOK` | 2 |
| **Create event** | `POST /v1.0/me/events` (body: subject, start/end, attendees[], location, `isOnlineMeeting:true` for Teams) | `MSGRAPH_CAL_CREATE_WEBHOOK` | 2 |
| **Find rooms** | `POST /v1.0/me/findRooms` / `findMeetingTimes` | `MSGRAPH_CAL_ROOMS_WEBHOOK` | 3 |

Notes:
- **READ needs no new scenario** — `calendarView`/`events` are GETs that the
  existing read proxy (3902068) forwards fine; only the new scope is required.
  A new lib helper (`calendar_lib.list_events` / `incoming_invitations`) wraps
  `msgraph_call` with the calendar select/expand set.
- **RESPOND/CREATE need new scenarios** because the read proxy is GET-shaped and
  the write proxy (`MSGRAPH_WRITE_WEBHOOK`) is tuned for mail folder MOVES. Keep
  each a **dedicated** scenario returning a clean `{ok, …}` so a respond can
  never be confused with a read (the same separation rationale as send-email).
- Event/invite ids are base64-derived → must be percent-encoded before they hit
  the URL path. `email_lib._encode_graph_id_path` already does this and
  `msgraph_call` calls it — so `/me/events/{id}/accept` is encoded for free.

---

## Calendar read — shape

`calendar_lib` (new, in `~/.screenpipe/pipes/_shared/`) exposes, mirroring
`sp_lib.gcal_events_all`'s normalized dict so briefings/conflict-checks are
source-agnostic:

```
event = {
  id, subject, start (ISO), end (ISO), all_day, location,
  organizer_email, attendees:[{email,name,response}],
  is_online, join_url, response_status,        # Nate's own response
  is_invitation,                               # responseStatus == notResponded
  series_master_id,                            # set for recurring instances
}
```

- **Upcoming events:** `GET /me/calendarView?startDateTime=now&endDateTime=now+Nd`
  (`calendarView` expands recurrences into instances — the right call for
  conflict checks; `/me/events` returns series masters, which don't carry
  concrete times).
- **Incoming invitations:** events where `responseStatus.response == 'notResponded'`
  (the org-side equivalent of "an invite waiting on Nate"). Surfaced for the
  auto-accept loop.

---

## Auto-accept / conflict logic

On each calendar-read pass, for every **invitation** (`is_invitation`):

1. **Already responded?** `response_status != notResponded` → skip (idempotent).
2. **Conflict scan.** Pull Nate's confirmed events overlapping
   `[start, end]` (from the same `calendarView`, excluding all-day/`free`/OOO
   blocks and the invite itself). Overlap = `a.start < b.end and b.start < a.end`.
3. **Decide — three outcomes, one of them never automatic:**
   - **No conflict → AUTO-ACCEPT.** `POST …/accept {sendResponse:true}`. Log via
     `log_reasoning` (action=`calendar-accept`, subject=event, rationale=`no
     conflict`, expectation) + `record_run`. (Optionally surface a quiet FYI in
     the next briefing digest — not a ping.)
   - **Conflict OR ambiguity → ESCALATE, do nothing to the calendar.** Push **one
     card** to the Chair via the front-door intake
     (`framework.frontdoor.intake.enqueue`, `cabinet:frontdoor:intake`) /
     `captain_attention_push comms …`, tier `batch` (or `ping-now` if the meeting
     is <24h out). The card states the clash (which existing event it overlaps),
     the organizer + attendees, and offers **Accept anyway / Decline / Propose
     new time** as per-step gates (a course of action, per
     `.claude/rules/courses-of-action.md`). The Chair relays; Nate decides.
   - **NEVER auto-decline.** Declining is always a Nate decision. The loop has no
     auto-decline branch by construction.
4. **Ambiguity triggers that force escalation (not auto-accept):** organizer is
   outside STEP/JFM (external), the invite has no end time / is multi-day, it
   overlaps a `tentative` block, or the conflict scan failed to load (fail
   safe → escalate, never silently accept).

**Investigation bar (per `courses-of-action.md`).** Before escalating a clash the
comms-officer gathers the full picture — the conflicting event, person-intel on
the organizer, any open commitment touching them — so the Chair's card is a
real course of action, not a bare "there's a clash."

**Separation from email.** Calendar items are classified **separately** from
reply-needing email and must **never** surface as awaiting-reply. Phase 1 below
enforces this at the draft-lane chokepoint.

---

## Build phases

**Phase 1 — read foundation + the misclassification fix (THIS CHANGE).**
- **Awaiting-reply fix (no new scope — live now):** `is_calendar_invite(thread)`
  added to `framework/acting/screenpipe_adapter.py`, applied in `find_threads`
  before the gate/drafter (mirrors `is_skipped_group`). A captured meeting-invite
  email is dropped from the awaiting-reply set, so the lane never drafts a reply
  to an invite. Pure read-only classification — mutates nothing, sends nothing,
  declines nothing; best-effort (any error → False, falls through to the existing
  gate). Covered by `framework/acting/tests/test_skip_stick.py::TestIsCalendarInvite`
  (incl. the exact Lisa DA-invite case + negatives proving normal human
  "let's meet" mail is NOT filtered).
- **Calendar read (gated on the scope add):** `calendar_lib.list_events` /
  `incoming_invitations` over `msgraph_call`. Ships the moment
  `Calendars.ReadWrite` is added + connection 4264707 re-authorized.

**Phase 2 — respond + create (self-serve scope; new respond/create scenarios).**
Auto-accept/escalate loop; create-event with attendees + free-text/online
location for "invite people." Outbound calendar actions follow the same
propose-first posture; auto-accept is the only un-gated action and only on a
clean no-conflict invite.

**Phase 3 — rooms (needs admin consent).** `findRooms`/`findMeetingTimes` for
structured room discovery + booking. Blocked on `Place.Read.All` admin consent
(Nate/Bjarke). Until then, create-event uses a typed location.

---

## Residual for Nate (only this)

1. **Self-serve (Chair can do, Chrome/portal):** add **`Calendars.ReadWrite`**
   (delegated) to the app registration behind Make connection 4264707, grant user
   consent, and **re-authorize that Make connection once** so its token carries
   the scope. Unlocks read + respond + create.
2. **Genuine Nate/Bjarke residual (admin consent):** **`Place.Read.All`**
   (delegated) — only if/when phase-3 structured room booking is wanted. Nothing
   else is blocked on it.
