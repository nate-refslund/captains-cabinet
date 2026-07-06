# Calendar `calendar_event_create` unfreeze runbook (2026-07-06)

The act-first calendar double-book guard was rebuilt onto a **signed read-only
EventKit helper** after real-integration testing showed the old path was broken
three ways (all hidden because it was only ever mock-tested):

| Component | File | Germline | Real-world finding |
|---|---|---|---|
| Reader | `framework/frontdoor/calendar_read.py` | no | EventKit-from-a-plain-script is write-only → blind to iCloud/Exchange/Google calendars; AppleScript `whose` scan is ~70s across the real calendars. **REBUILT** onto the signed helper (this change). |
| Writer | `framework/frontdoor/calendar_template.py` | **yes** | `uid of newEvent` reproducibly throws through the `(first calendar whose name is …)` reference → `_exec_calendar_event` raises "no UID" → canary create fails. **Blocks the unfreeze on its own.** Fix below. |
| Reverse | `framework/frontdoor/action_undo.py` | yes | Works, but ~14s (`whose uid is` scan). Functional under the 30s timeout; optional future fix. |

Proof a signed helper works: run from a normal Terminal with Full Access granted,
it read **339 real events** across all sources (iCloud Home/Work/Family, JFM
Exchange, Google). `auth_before=4` (write-only) → `auth_after=3` (fullAccess) is
the whole story.

---

## Step 1 — build + grant the helper (no germline needed)

```bash
cd /Users/nate/captains-cabinet
bash cabinet/scripts/build-calendar-helper.sh
# then run it ONCE from a normal Terminal window and click "Allow" (Full Access):
./bin/cabinet-calread read "$(date +%Y-%m-%dT00:00:00)" "$(date -v+1d +%Y-%m-%dT00:00:00)"
```

- It must print a JSON array (possibly `[]`). If it exits non-zero with "calendar
  access not granted", the grant did not take — re-run and Allow.
- Point the action lane at it: set `CABINET_CAL_HELPER=/Users/nate/captains-cabinet/bin/cabinet-calread`
  in `cabinet/.env` (or rely on the `<repo>/bin/cabinet-calread` default).
- Ad-hoc signature caveat: the TCC grant is keyed to the binary's cdhash, so a
  **rebuild needs a one-time re-grant**. (A stable Developer ID would remove that.)

The reader **fails closed**: if the helper is missing, non-executable, exits
non-zero, or lacks Full Access, `conflicts_for_due` raises `CalendarReadError`
and the act-first write is refused — an empty read is never mistaken for
"no conflict".

## Step 2 — germline window: fix the writer uid bug

`framework/frontdoor/calendar_template.py` is germline (unlock via
`cabinet/scripts/germline-lock.sh unlock`, edit, re-lock). The event is created
inside `tell (first calendar whose name is calName)`, a `whose`-nested specifier
that `uid of newEvent` cannot resolve. Reproduced (rc=1, both runs); the direct
`tell calendar calName` form works (rc=0, both runs).

Replace, in `CALENDAR_EVENT_SCRIPT`:

```applescript
 if not (exists (first calendar whose name is calName)) then return "err:calendar-not-found:" & calName
 set targetCal to (first calendar whose name is calName)
 if (writable of targetCal is false) then return "err:calendar-not-writable:" & calName
 tell targetCal
  set newEvent to make new event with properties {summary:evTitle, start date:startDate, end date:endDate, description:evNotes}
 end tell
end tell
return "ok:" & calName & ":" & (uid of newEvent)
```

with:

```applescript
 if not (exists calendar calName) then return "err:calendar-not-found:" & calName
 if (writable of calendar calName is false) then return "err:calendar-not-writable:" & calName
 tell calendar calName
  set newEvent to make new event with properties {summary:evTitle, start date:startDate, end date:endDate, description:evNotes}
  set theUid to uid of newEvent
 end tell
end tell
return "ok:" & calName & ":" & theUid
```

(Reads `uid` inside the `tell calendar calName` block, off the direct reference.)
The classifier imports the same constant, so the byte-match stays consistent —
no other germline edit needed for this fix.

## Step 3 — run the unfreeze

```bash
ACTION_LANE_CALENDAR=Home CABINET_CAL_HELPER=/Users/nate/captains-cabinet/bin/cabinet-calread \
  python3.12 -m framework.frontdoor.actfirst_canary --unfreeze calendar_event_create
```

The canary runs a real create→verify→reverse on **Home** (03:00 next day). With
the helper granted (Step 1) and the writer fixed (Step 2): the B2 gather reads
Home fast + complete, the write returns a uid, the reverse deletes it → green →
the freeze lifts. If any leg is red it stays frozen (by design).

---

## Notes / follow-ups (not blockers)

- **Reverse latency** (~14s `whose uid is` scan): optional germline follow-up —
  route `action_undo._calendar_delete_script` through a write-capable EventKit
  helper (delete by `eventIdentifier`, instant). Until then it's fine under the
  30s timeout.
- **Two-store edge**: the writer creates via AppleScript (Calendar.app) and the
  reader reads via EventKit. With Full Access these are the same iCloud store, so
  a settled event is seen. A just-created event may not be visible for a second —
  only matters for two cabinet writes seconds apart on the same slot (the canary
  verifies by uid, not read-back, so it's unaffected). The clean end-state is to
  unify create+read+delete on one write-capable helper (a later germline wave).
- **Share-state (F1)**: Nate's Home is private, so act-first blocks don't surface
  to anyone. The helper exposes `EKCalendar.sharees`; a zero-sharees pre-write
  gate for OTHER captains is a separate follow-up.
- **All-day events are excluded from conflicts** (conscious ruling, flagged by the
  adversarial review). The helper filters `isAllDay` so holiday/birthday markers
  don't block every 30-min slot — but this also means an all-day "Vacation" /
  "Out of office" won't stop a focus block being booked that day. It's reversible
  (delete-by-UID undo) and not a collision with a specific timed meeting. If you
  want all-day *busy* blocks to count, the refinement is to keep all-day events
  whose `EKEvent.availability` is `.busy`/`.unavailable` and drop only `.free`
  ones — but that needs live validation of how your calendars mark those, so it's
  a deliberate follow-up rather than a blind change. **Your call.**
