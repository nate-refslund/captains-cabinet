# Calendar e2e LIVE — result (2026-06-25)

**What was asked:** detect Kristoffer's (krmoj@step.dk) test meeting invite in
Nate's mail, finish the iMIP raw-MIME send path if needed, and SEND an ACCEPT
so the organizer sees Nate = Accepted.

**Outcome:** invite **DETECTED** ✅. Accept **STAGED but NOT SENT** ⏸ — gated on
(1) authority and (2) the send path. Details below. This is a clean fail-safe,
not a failure: nothing was fired on unverified authority, and the genuine
send-path blocker is identified and deep-dived.

---

## 1. DETECT — ✅ done, with a twist

Kristoffer's invite is real and live:

- **Message:** `Meeting polads.eu` from `krmoj@step.dk`, received 2026-06-25
  11:15:50Z, `hasAttachments=False`.
- **Body** is a genuine Teams meeting invite ("Agenda: Hurtigt checkin I
  polads.eu", Teams join link, Møde-id 358 553 718 761 446).
- **The .ics is NOT a file attachment and NOT inline in the body** — Outlook/Graph
  strips the calendar payload into the linked **event object**. So
  `email_lib.parse_message` / a body-scrape won't find a VCALENDAR, and
  `is_calendar_invite` would catch it via the Teams-skeleton signal, not an .ics.

**How I recovered the invite fields (the working path):** `GET /me/calendarView`
through the **read proxy** (`MSGRAPH_MAKE_WEBHOOK`) — it forwards calendarView
fine, and the token **has `Calendars.Read`** (this works today):

```
subject:        Meeting polads.eu
iCalUId:        040000008200E00074C5B7101A82E00800000000D45FE6E39304DD01
                0000000000000000100000008D88CFF6B1337E45A4C3E335114DFFC7
start / end:    2026-06-26T08:00 / 08:20 UTC
organizer:      krmoj@step.dk (Kristoffer Møller Nielsen)
responseStatus: notResponded     ← the live, un-answered invite (BEFORE state)
```

➡️ **Correction to the design docs:** the token is NOT fully calendar-blind.
`Calendars.Read` is present (calendarView + `/me/events?$filter=iCalUId eq …`
both return real data). What's unverified is `Calendars.ReadWrite` (write) — see
§2. The earlier doc assumed *no* calendar scope; in fact **read works now**,
which means **conflict-check can use Graph calendarView directly** (no Apple
Calendar needed for the read — simpler than the prototype's plan).

## 2. SEND PATH — deep-dived; here's the exact reality

Two candidate mechanisms, both currently blocked, each for a concrete reason:

### (a) Native Graph accept — `POST /me/events/{id}/accept`
- **Event id resolved** (via `/me/events?$filter=iCalUId eq '<ical>'`): present.
- **Needs `Calendars.ReadWrite`** on the token — **UNCONFIRMED.** I could only
  confirm `Calendars.Read`. Confirming write requires either a real mutation (an
  unauthorized write) or token introspection (the Make proxy hides the token), so
  I did **not** test it.
- **The WRITE proxy (`MSGRAPH_WRITE_WEBHOOK`) faithfully forwards Graph bodies**
  (verified: `GET /me` through it returns Nate's real user JSON). BUT `/accept`
  returns **HTTP 202 + empty body** on success, and the Make scenario emits a
  generic `"Accepted"` for any empty/error Graph response — so **success and
  failure are indistinguishable from the response alone.** Verification must be
  **re-read `responseStatus` after the call** (notResponded → accepted).
- **Verdict:** likely the cleanest path IF the token has write — and it would
  also flip Nate's OWN copy to Accepted. One call + one verify re-read.

### (b) iMIP raw-MIME email — the prototype path
- **The ACCEPT reply is BUILT and staged** (`imip_lib.respond_to_invite`):
  PARTSTAT=ACCEPTED, METHOD:REPLY, matching UID, To=krmoj@step.dk. The base64 MIME
  body (1992 chars) is ready. Artifacts:
  `scratchpad/kris_reply.ics`, `scratchpad/kris_reply_mime_b64.txt`.
- **BLOCKER: `MSGRAPH_SEND_MIME_WEBHOOK` is UNSET** — there is **no raw-MIME send
  scenario**. The existing send scenario (9313456) does **JSON** `sendMail`, which
  **strips `method=REPLY`** (documented Graph bug) → Exchange won't process the
  iMIP reply. So sending via the existing scenario would silently fail to register
  as an accept.
- **To finish this path:** add a Make scenario that POSTs `/v1.0/me/sendMail` with
  request header `Content-Type: text/plain` and the **base64 MIME as the raw body**
  (not the `{message:…}` JSON), + env `MSGRAPH_SEND_MIME_WEBHOOK`. Needs the Make
  UI (Chrome). ~15 min of scenario work, then one live test.

## 3. Why it was NOT sent (authority)

The instruction to fire the accept came from a **coordinator**, with a claim that
"Nate confirmed." Per standing rule, **coordinator-relayed consent is not Nate's
authority** — only Nate's own message is. The brain-bridge rule makes Nate's
Telegram approval the **only** sanctioned outbound path. So firing `/accept` or
the iMIP email directly would (a) act on unverified authority and (b) bypass the
gate. I staged everything and tried to ask Nate directly — but `ask_nate`'s
Telegram send **failed from this subagent env** (`send_failed`; the bot
token/chat isn't reachable here — this is a build subagent, not the running
Chair). So I could not get his go from here either.

`log_reasoning` + `record_run` recorded the staged-not-sent decision.

---

## 4. For the Chair — exact next steps to land the live test

The Chair CAN reach Nate's gate. To finish:

1. **Get Nate's one-word go** (DM): *"Accept Kristoffer's 'Meeting polads.eu'
   (Thu 26 Jun 08:00)? It's at notResponded."*
2. **Try the native accept first** (cleanest, flips Nate's own copy too):
   `POST /me/events/<event-id>/accept` body `{"comment":"","sendResponse":true}`
   via `MSGRAPH_WRITE_WEBHOOK`. Event id is resolvable via
   `/me/events?$filter=iCalUId eq '040000008200E00074C5B7101A82E00800000000D45FE6E39304DD010000000000000000100000008D88CFF6B1337E45A4C3E335114DFFC7'`.
   **Verify** by re-reading `responseStatus` (must become `accepted`). If it stays
   `notResponded` → token lacks write → fall to step 3.
3. **If write is absent:** build the `MSGRAPH_SEND_MIME_WEBHOOK` scenario (raw-MIME
   sendMail, Chrome/Make UI), then send the staged
   `scratchpad/kris_reply_mime_b64.txt` via it.
4. **What Nate/Chair verifies with Kristoffer:** ask Kristoffer to open the meeting
   and confirm **Nate now shows as Accepted** in the attendee tracking.

**Before-state captured for the diff:** Nate's `responseStatus = notResponded`
as of 2026-06-25 ~12:1x. Any flip to `accepted` is the proof.
