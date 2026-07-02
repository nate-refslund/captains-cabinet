# Calendar without the Graph scope — iMIP email + Apple Calendar + OWA (research, design, prototype)

**Status:** research + prototype (2026-06-25). Companion to
`docs/calendar-system-design-2026-06-25.md` (the Graph-scope design). This doc
covers the **workaround paths** for when `Calendars.ReadWrite` stays blocked
(it needs JFM tenant-admin consent Nate doesn't have — that's the operative
constraint, correcting the earlier doc's "self-serve" assumption).
**Posture:** propose-first. Nothing here auto-sends. Auto-accept only on a
clean no-conflict invite; **never auto-decline** — clashes escalate to the Chair.

**Prototype:** `~/.screenpipe/pipes/_shared/imip_lib.py` — the iMIP REPLY
builder (`respond_to_invite(invite_eml, response, comment)`). Pure builder, no
network. Runs green (`python3.12 _shared/imip_lib.py`).

---

## TL;DR — the verdict

Three paths exist; the cleanest answer is a **combination**, not one of them:

| Capability | **Winner** | Why |
|---|---|---|
| **READ events / conflict-check** | **Apple Calendar (osascript/EventKit)** | The Mac's Calendar.app is already signed into JFM; the **"Work" calendar reads Nate's real Exchange events RIGHT NOW with no scope and no permission prompt** (verified live). Solves the conflict-check problem that the email path cannot. |
| **RESPOND (accept/tentative/decline)** | **iMIP email reply** | Outlook/Exchange **honor** an inbound `text/calendar; method=REPLY` email and update the organizer's tracking. Uses the Mail.Send we already have. EventKit/AppleScript **cannot** respond programmatically (verified — GUI-only). |
| **Everything / fallback** | **OWA browser** | Full fidelity (read, respond, invite, propose-time) but browser-driven (computer-use). The escape hatch for anything the two cheap paths can't do. |

**Recommended build:** **READ + conflict-check via Apple Calendar; RESPOND via
iMIP email; OWA as the fallback.** Both primary paths work today with no new
Graph scope. The only residuals are (a) the iMIP REPLY needs a **raw-MIME**
send path (a new Make scenario — current send scenario only does JSON), and (b)
the Apple Calendar read needs a **fast access pattern** (AppleScript `whose`
over Exchange stalls; use bulk-fetch-then-filter or EventKit). Neither blocks
the design; both are named below.

---

## Part 1 — iMIP research findings (RESPOND path)

Researched via Perplexity (`sonar`) + cross-checked against the RFCs and MS
Learn. Three questions, three verdicts:

### Q1 — Does sending an email REPLY accept/decline a meeting? **YES.**

RFC 6047 (iMIP) over RFC 5546 (iTIP): an attendee updates their status by
sending a `text/calendar; method=REPLY` part with their `ATTENDEE;PARTSTAT=…`
to the organizer. **Outlook/Exchange Online honor inbound iMIP REPLY emails and
update the organizer's attendee-tracking**, provided the .ics carries the
mandatory fields: `UID`, `SEQUENCE`, `DTSTAMP`, `ORGANIZER`, exactly one
`ATTENDEE` with `PARTSTAT`. (Exchange 2007+ rejects a REPLY without *exactly
one* ATTENDEE+PARTSTAT.)
*Sources: RFC 6047 / RFC 5546 / RFC 2446 §3.2.3; MS Learn Q&A "Declining Meeting
Invitations via Modified ICS" 2024-11-18; icalendar.org RFC-6638 §B.4 example.*

### Q2 — Does an iMIP REPLY update NATE'S OWN calendar? **NO — but the event is already there as Tentative.** (the load-bearing residual)

This is the subtle one, and the answer is two-part:

1. **The REPLY only notifies the ORGANIZER.** Exchange's Calendar Attendant
   **ignores a reply a mailbox sends to itself** — a user can't change their own
   participation status by replying to their own mailbox. So sending the iMIP
   REPLY does **not** flip Nate's own copy from Tentative → Busy/Accepted.
2. **BUT the event is already on Nate's calendar as TENTATIVE.** Exchange
   auto-processes the inbound `METHOD:REQUEST` and books it tentatively before
   Nate does anything — `AddNewRequestsTentatively` is **forced-on for user
   mailboxes** (Microsoft removed the ability to disable it, CU7-era). So the
   slot is visible and blocks free/busy the moment the invite arrives.

**Net effect for the cabinet:** sending the iMIP REPLY does the socially-important
thing — the organizer sees "Nate accepted." Nate's own calendar shows the
meeting (as Tentative). What it does **not** do is mark his own copy "Accepted."

**Workarounds to get his own copy to "Accepted" (all optional, none required for
the organizer to be informed):**
- **Do nothing** — Tentative already blocks the slot and shows in briefings; for
  most purposes this is fine, and it's the honest default.
- **Apple Calendar GUI accept** (computer-use) — one click flips it; scriptable
  only via the GUI, not EventKit (see Part 2).
- **OWA accept** (browser) — same, via the confirmed OWA path.
- **Graph `/me/events/{id}/accept`** — the clean API flip, but needs the
  **blocked** `Calendars.ReadWrite` scope. Out until the scope lands.

*Sources: Perplexity sonar synthesis citing MS Learn `Set-CalendarProcessing`
(AutomateProcessing=AutoUpdate, AddNewRequestsTentatively default $true);
michev.info "Disabling AddNewRequestsTentatively is no longer possible for
user/shared mailboxes"; Exchange Calendar Attendant behavior docs.*

### Q3 — Exact REPLY format + the Graph send gotcha. **(documented; prototype implements it)**

**The .ics REPLY** (matches RFC-6638 §B.4 / sabre vobject iTIP REPLY example):

```
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Captains Cabinet//iMIP REPLY//EN
METHOD:REPLY
BEGIN:VEVENT
UID:<the original REQUEST's UID, verbatim>
SEQUENCE:<the original SEQUENCE, verbatim>
DTSTAMP:<now, UTC, YYYYMMDDTHHMMSSZ>
ORGANIZER;CN="…":mailto:<organizer>
ATTENDEE;CN="…";PARTSTAT=ACCEPTED:mailto:<nate's matched address>
DTSTART;TZID=…:…            (echoed from the request; optional but harmless)
DTEND;TZID=…:…
SUMMARY:<echoed>
COMMENT:<the "with notes" free text>     ← optional
REQUEST-STATUS:2.0;Success
END:VEVENT
END:VCALENDAR
```
- `PARTSTAT` ∈ `ACCEPTED | TENTATIVE | DECLINED`.
- `UID` + `SEQUENCE` **must match the original** — that's how Exchange correlates
  the reply to the meeting. (Don't bump SEQUENCE on a reply; SEQUENCE is the
  organizer's revision counter.)
- `COMMENT` carries "respond with notes."
- CRLF line endings; RFC-5545 line folding (>75 octets → CRLF + leading space);
  TEXT values escape `\ ; , \n`. The prototype does all of this and round-trips.

**THE GRAPH SEND BUG (decisive design fork).** Microsoft Graph `sendMail` in
**JSON** form, given a `#microsoft.graph.fileAttachment` with
`contentType: "text/calendar; method=REPLY; charset=utf-8"`, **silently resets
it to bare `text/calendar;`** — dropping `method=REPLY`, so Exchange won't
process the iMIP reply. This is a **documented, still-open MS bug** (MS Learn
Q&A 2025-07-24, "MS graph sendMail endpoint bug with ics attachment"). The fix:
**send RAW MIME.** Graph `sendMail` with request header `Content-Type:
text/plain` + a base64 RFC-5322 MIME body is copied by Exchange **"more or less
intact"** (MS Learn `outlook-send-mime-message` /
`outlook-things-to-know-about-send-mail`), preserving `method=REPLY`.

➡️ **The cabinet must send the iMIP reply as raw MIME, not as a JSON
fileAttachment.** The prototype emits exactly that MIME (`build_reply_mime`),
ready for a MIME-format `sendMail`.
*Sources: MS Learn Q&A 5491335 (the bug); MS Learn outlook-send-mime-message +
outlook-things-to-know-about-send-mail (the raw-MIME fix); MS Learn Q&A 501593
(MIME headers must be complete / `saveChanges()` analogue).*

---

## Part 2 — Apple Calendar research + LIVE test (READ path; RESPOND verdict)

The Mac (`Nates-MacBook-Pro` / the deploy target) runs Calendar.app signed into
JFM. Calendar.app keeps a **local synced copy** of the Exchange calendar that is
readable with **no Graph scope**.

### READ — verified working LIVE, no permission prompt

Ran `osascript -e 'tell application "Calendar" …'` from the Bash tool:

- `count of calendars` → **12**; names include **`Work`**, plus `Calendar`,
  `Family`, `refslund@gmail.com`, Danish holiday calendars, etc.
- A 30-day event read returned **Nate's real JFM events**: *"PolAds Weekly
  Review", "Product & Publishers weekly meeting", "STEP Network Allhands
  (MEDIELAB ODENSE)", "Polads.eu hackathon", "Polads.eu x Navison", "Fælles
  morgenmad – sommerafslutning"* — i.e. the actual Exchange "Work" calendar.
- **No TCC/automation prompt fired** in the shell — the controlling process
  already holds Calendar access. (So conflict-check needs **zero** new consent.)

**This solves the conflict-check problem the iMIP path can't.** With the local
synced store, the auto-accept loop can scan Nate's confirmed events for a clash
without any calendar scope and without the browser.

#### The one real READ caveat — access pattern (an engineering residual, not a blocker)
AppleScript's `(every event of c whose start date ≥ now …)` **filtering over the
Exchange-backed store can stall** — observed: a summary+start read returned
instantly, but adding per-event `end date` / `status` property reads, or re-running
during a Calendar.app sync cycle, hung past 2 min. This mirrors the known
screenpipe Reminders gotcha ("a whose-filtered collection is slow; bulk-get
unfiltered then filter in Python"). **Mitigations (pick one at build time):**
- **Bulk-fetch then filter in Python** — read summary/start/end with minimal
  per-event property access, filter the window + overlaps in Python (the proven
  Reminders pattern).
- **EventKit via pyobjc** (`pip install pyobjc-framework-EventKit`) — a proper
  `predicateForEventsWithStartDate:endDate:calendars:` API, much faster and more
  robust than AppleScript `whose`. **Not currently installed** in the screenpipe
  py (`ModuleNotFoundError: No module named 'EventKit'`) — a one-line add.
- Cache the read (the loop runs on a cadence; a 5-min-stale conflict view is fine).

### RESPOND — verified NOT possible programmatically (GUI-only)

Researched: **EventKit `EKEventStore` cannot set `EKParticipant.participantStatus`
or send an RSVP**, and **AppleScript `tell application "Calendar"` has no
accept/decline command**. EventKit is read/write for *events* but **read-only
for attendee status** — responding to an invitation is restricted to the
Calendar.app **GUI** (or system meeting handler). So Apple Calendar can RSVP only
via **computer-use clicking the GUI**, not via script.
*Sources: Apple EventKit docs + WWDC23 "Discover Calendar and EventKit"; Apple
Developer Forums (EventKit tag); MS Learn EKEventStore reference — all consistent
that RSVP/participantStatus is not programmatically settable.*

➡️ **Apple Calendar is a READ instrument, not a RESPOND instrument** (short of
driving its GUI). That's why the recommendation pairs **Apple-read + iMIP-respond**.

---

## Part 3 — OWA browser (fallback)

Already confirmed working (the OWA path Nate validated). Full fidelity: read,
accept/decline (incl. flipping his **own** copy to Accepted — the thing iMIP
can't), invite people, propose new time, book rooms via the UI. Cost: it's
**browser-driven** (computer-use / claude-in-chrome), so it's slower, more
fragile, and not headless. **Role:** the escape hatch — used when (a) Nate
wants his own copy marked Accepted and the Graph scope is still blocked, (b) a
non-standard invite the iMIP builder can't parse, or (c) anything outside
accept/tentative/decline (propose-time, room booking) before phase 2/3.

---

## Part 4 — Three-way comparison

| | **iMIP email** | **Apple Calendar** | **OWA browser** |
|---|---|---|---|
| New Graph scope? | **No** | **No** | **No** |
| Headless / no GUI? | **Yes** | **Yes** (script) | No (browser) |
| Read events / conflict-check | ✗ (only from prior captured invites) | ✅ **real synced store, now** | ✅ |
| Respond accept/decline/tentative | ✅ (notifies organizer) | ✗ (GUI-only) | ✅ |
| "With notes" reply | ✅ (`COMMENT`) | ✗ | ✅ |
| Updates Nate's OWN copy → Accepted | ✗ (stays Tentative) | ✗ (script) / ✅ (GUI) | ✅ |
| Invite people / book rooms | ✗ | ✗ (script) | ✅ |
| Reliability | high (once raw-MIME send wired) | high read; access-pattern care | medium (browser) |
| Build cost | new raw-MIME Make scenario | osascript/EventKit reader | computer-use flow (exists) |

**The combination beats every single path:** the cheap headless pair
(Apple-read + iMIP-respond) covers the 95% case — *see the invite, check the
calendar, auto-accept clean or escalate a clash, respond with a note* — entirely
without the blocked scope or the browser. OWA covers the long tail.

---

## Part 5 — Design (the recommended combination)

### DETECT
Reuse `framework/acting/screenpipe_adapter.py::is_calendar_invite` (already
shipped: detects `text/calendar`/iCalendar markers, the When/Where (EN+DA)
skeleton, Teams-join block, room-mailbox senders). It already drops invites from
the awaiting-reply set so the draft-lane never prose-replies to an invite. The
calendar course consumes that same signal as its **inbound queue**: a captured
message that `is_calendar_invite()` → candidate for an iMIP response.

**Recovering the .ics to reply to.** The vault stores a *cleaned text* body —
the raw .ics is not retained. So at respond-time, fetch the original message's
calendar part from Graph: `GET /me/messages/{id}?$expand=attachments` (or
`…/attachments/{id}/$value`) over the existing **read** proxy (`msgraph_call`)
and pull the `text/calendar` attachment's `contentBytes`. (No new scope — it's a
mail read.) `imip_lib.parse_invite` accepts the raw .ics, a full MIME message,
or even the captured body if the .ics markers survived — so it's robust to
whichever source we feed it.

### CONFLICT-CHECK (the part the combination uniquely solves)
**Read Nate's confirmed events from Apple Calendar** (osascript bulk-read →
Python filter, or EventKit). For an invite `[start,end]`:
- overlap = `a.start < b.end and b.start < a.end`, excluding all-day / free /
  OOO blocks and the invite's own tentative placeholder.
- dedup the Apple read (the same event appears under multiple calendar
  memberships — seen in the live test: "Work" + "Calendar" both list the PolAds
  review). Key by (summary, start, end).
- if the Apple read is unavailable/stale/errors → **fail safe: escalate, never
  auto-accept** (same rule as the Graph design).

### RESPOND (course of action, propose-first)
On each pass, for every inbound invitation:
1. **Already handled?** (local ledger by UID) → skip (idempotent).
2. **Conflict scan** (Apple Calendar, above).
3. **Decide — three outcomes, one never automatic:**
   - **No conflict → AUTO-ACCEPT.** Build the iMIP REPLY (`respond_to_invite(…,
     "accept")`) and send the **raw MIME** via the MIME-format sendMail path
     (new scenario — Part 6). Log `log_reasoning`(action=`calendar-imip-accept`)
     + `record_run`. Quiet FYI in the next briefing digest, not a ping.
   - **Conflict / ambiguity → ESCALATE, touch nothing.** One **course-of-action
     card** to the Chair (per `.claude/rules/courses-of-action.md`): states the
     clash (which existing event), organizer + attendees, person-intel, any open
     commitment — and offers **Accept anyway / Decline (with note) / Propose new
     time** as per-step gates. Tier `batch` (or `ping-now` if <24h out). The
     Chair relays; Nate decides; the chosen action runs the matching builder.
   - **NEVER auto-decline.** No auto-decline branch exists.
4. **Ambiguity triggers forcing escalation:** organizer external to STEP/JFM,
   no end time / multi-day, overlaps a `tentative` block, or the conflict read
   failed.

**Own-copy note.** After an iMIP accept, Nate's own copy stays **Tentative**
(Part 1 Q2). The briefing FYI says so plainly ("accepted to organizer; your copy
shows tentative"). If/when he wants his own copy flipped, that's the OWA/GUI or
the (blocked) Graph `/accept` — surfaced as an optional one-tap, never silent.

**Outbound gate.** Every send (auto-accept included, since it leaves the machine)
is an outbound message → it goes through the **propose-first** posture. Per
`.claude/rules/brain-bridge.md` the cabinet's only sanctioned outbound path is
`queue_draft` (Telegram human-approve). So the iMIP reply MIME is **queued**, not
fired — auto-accept means "auto-*propose* the accept," and the clean-no-conflict
case can be configured to auto-approve once trust is established. **Nothing
auto-sends in v1.**

### RESPOND (Apple/OWA fallback)
If Nate wants his own copy Accepted, or the invite won't parse, escalate a
card offering "handle in OWA" → computer-use drives the Calendar.app/OWA Accept.

---

## Part 6 — Build plan

**Phase 1 — DONE / shippable now (no new scope):**
- ✅ `is_calendar_invite` classifier (already shipped; drops invites from
  awaiting-reply).
- ✅ `imip_lib.py` REPLY builder (this change; prototype, runs green).
- **Apple Calendar reader** `calendar_read_apple.py` — osascript bulk-read →
  Python window+overlap filter (or EventKit via pyobjc). Mirror
  `sp_lib.gcal_events_all`'s normalized event dict so briefings/conflict-checks
  stay source-agnostic. This is the conflict-check foundation.

**Phase 2 — respond wiring (no new scope; one new Make scenario):**
- **New Make scenario: MIME-format sendMail** (Screenpipe folder 510964, azure
  connection 4264707). `POST /v1.0/me/sendMail` with request header
  `Content-Type: text/plain` and the base64 MIME as the raw body (NOT the JSON
  `{message:…}` shape — that triggers the method-strip bug). New env
  `MSGRAPH_SEND_MIME_WEBHOOK` in `_shared/.env`. Dedicated scenario (same
  separation rationale as send-email) returning clean `{ok,…}`.
  - `email_lib.send_mime(raw_mime)` helper wraps it (base64 + post). The current
    `send_email` (JSON sendMail) stays for prose; `send_mime` is the iMIP path.
- **Respond loop** in the comms/calendar course: detect → fetch .ics via Graph
  read → `respond_to_invite` → conflict-check (Apple) → auto-accept(queue) /
  escalate. Local UID ledger for idempotency. `log_reasoning` + `record_run`.

**Phase 3 — OWA fallback flow + own-copy flip:** computer-use Calendar.app/OWA
Accept for "mark my own copy accepted" and unparseable invites. (The Graph
`/accept` clean path stays gated on the blocked `Calendars.ReadWrite`.)

---

## Part 7 — The prototype (`_shared/imip_lib.py`)

Pure builder, **no network, sends nothing.** Public surface:

- `parse_invite(invite_text, me_emails=None) -> ParsedInvite` — lifts UID,
  SEQUENCE, ORGANIZER (CN+email), the Nate-side ATTENDEE, SUMMARY, DTSTART/END
  (TZID preserved), METHOD from a raw .ics / full MIME / captured body.
  Unfolds RFC-5545 folding; never raises (soft `ok=False`+`error`).
- `build_reply_ics(invite, response, comment="") -> str` — the RFC-5546 REPLY
  VCALENDAR: METHOD:REPLY, one VEVENT, matching UID/SEQUENCE, single
  ATTENDEE+PARTSTAT, REQUEST-STATUS, optional COMMENT. CRLF, folded, escaped.
- `build_reply_mime(invite, response, reply_ics, comment="") -> str` — the full
  RFC-5322 MIME: `multipart/alternative` (text/plain human line + `text/calendar;
  method=REPLY` part, base64). **This is the Graph-bug-proof shape** — `method=REPLY`
  preserved in the Content-Type. From=Nate's matched attendee, To=organizer.
- `respond_to_invite(invite_eml, response, comment="") -> InviteResponse` — the
  one-shot: parse → reply ics → reply mime → base64(mime). Returns
  `{ok, response, partstat, organizer_email, summary, reply_ics, reply_mime,
  reply_mime_b64, invite}`. `reply_mime_b64` is exactly the body the MIME-format
  `sendMail` wants. **Never sends.**

**Verified (`python3.12 _shared/imip_lib.py`):**
- Parses an Outlook-shaped DA invite (TZID, RSVP, NEEDS-ACTION) correctly.
- Builds accept / tentative / decline replies; COMMENT carries the note.
- A long UID (>75 octets) folds and **round-trips** parse→build→reparse intact.
- TEXT escaping (`,` `;` `\`) is RFC-5545 correct; folded physical lines are
  **≤75 octets** (strict-checked).
- Negatives fail safe: unknown response, no-VCALENDAR body, and
  not-an-attendee invite all return `ok=False` + a precise error.

---

## Part 8 — Residuals (the honest list)

1. **Own-calendar update (Q2).** An iMIP accept informs the **organizer** but
   leaves Nate's **own** copy **Tentative** (Exchange ignores self-replies; the
   event is already auto-booked Tentative). Flipping his own copy to Accepted
   needs OWA/GUI (computer-use) or the **blocked** Graph `/accept`. **Decision
   needed from Nate:** is "Tentative on my side, Accepted to the organizer"
   acceptable as the default, or should every accept also drive an OWA click to
   flip his own copy? (Recommendation: accept Tentative-on-own-side as default;
   offer the OWA flip as an optional one-tap.)
2. **Raw-MIME send path.** The iMIP reply MUST go out as **raw MIME** (the JSON
   fileAttachment path strips `method=REPLY` — documented Graph bug). The current
   send scenario (9313456) only does JSON sendMail → **a new MIME-format Make
   scenario + `MSGRAPH_SEND_MIME_WEBHOOK` is required.** Not yet built. **Needs
   one live end-to-end test** (send a real REPLY, confirm the organizer's
   tracking flips) before trusting it.
3. **Apple Calendar access pattern.** Read works **now** with no prompt, but
   AppleScript `whose`-filtering over the Exchange store **can stall**. Build the
   reader as bulk-fetch-then-filter (the Reminders pattern) or add
   `pyobjc-framework-EventKit` (not currently installed). Also **dedup** the read
   (one event appears under multiple calendar memberships).
4. **.ics recovery.** The vault keeps cleaned text, not the raw .ics → the
   respond loop must re-fetch the original message's `text/calendar` attachment
   via the Graph **read** proxy at respond-time (no new scope). Straightforward,
   not yet wired.
5. **Scope still the cleanest if it ever unblocks.** If JFM admin ever grants
   `Calendars.ReadWrite`, the Graph design (`docs/calendar-system-design-2026-06-25.md`)
   is simpler than all of this (native read + `/accept` flips the own copy). This
   workaround stack is the answer *while the scope is blocked* — keep both.
