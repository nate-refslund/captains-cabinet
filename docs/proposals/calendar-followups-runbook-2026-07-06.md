# Runbook — calendar follow-ups: ONE rebuild + re-grant, then validation

**Date:** 2026-07-06 · **Branch:** feat/fidelity-harness-design

This wave batches FOUR calendar refinements into the ONE consolidated signed
helper (`framework/frontdoor/calread_helper/calread.swift`), so there is exactly
**one rebuild and one TCC re-grant**:

1. **Fast delete reverse** — helper `delete <cal> <uid>` (confirmed-only) behind
   the germline `action_undo._inv_calendar_delete` dispatcher; AppleScript
   `whose uid is` delete stays as the authoritative fallback.
2. **All-day availability filter** — helper `read` now emits every event tagged
   `all_day` + `availability`; the policy lives in `calendar_read.py` behind
   `CABINET_CAL_ALLDAY_BUSY_BLOCKS` (default OFF = drop ALL all-day, byte-identical
   to today).
3. **Officer boot self-check** — helper `probe` + `cabinet/scripts/calendar-boot-selfcheck.sh`
   (wired into the officer BOOT_PROMPT); informational only, fails closed loud.
4. **Real-sharees pre-write gate (F1)** — helper `calinfo <cal>` behind the germline
   `action_exec._exec_calendar_event` act-first gate.

## What is proven vs Nate-gated

| Proven now (this write-only background context) | Nate-gated (granted Terminal / officer box) |
|---|---|
| Consolidated `calread.swift` COMPILES (swiftc → temp binary; live `bin/cabinet-calread` untouched) | Real create → helper-delete round-trip proving `uid == calendarItemExternalIdentifier` |
| Dispatch/usage exit codes: bad subcommand / wrong argc → 64 | Real all-day `.availability` values on Nate's Vacation vs holiday calendars |
| `probe` → `writeOnly` (exit 5) from this context (confirms the load-bearing TCC fact) | Real `calinfo Home` attributes (writable/shared/ambiguous) |
| All Python mock/unit tests: `test_calendar_read.py` (+ all-day + calinfo), `test_calendar_delete.py`, pre-staged `test_action_exec.py` | Whether the launchd officer chain gets fullAccess or silent-denies |
| Ratchet + layer-separation + full germline regression suite green | Speed: EventKit delete sub-second vs AppleScript 14-45s |

**None of the EventKit read/delete/calinfo behavior against Nate's real calendar
can be validated from here — this agent's context is write-only EventKit** (proven
by `probe` → writeOnly). Everything in the right column is Nate-gated.

## STEP 1 — the ONE rebuild + re-grant (Nate's Terminal, granted GUI login)

```bash
cd /Users/nate/captains-cabinet
bash cabinet/scripts/build-calendar-helper.sh      # rebuilds bin/cabinet-calread (re-keys cdhash)
# First run triggers the macOS Calendar prompt — grant FULL ACCESS.
bin/cabinet-calread read "$(date +%Y-%m-%dT00:00:00)" "$(date -v+1d +%Y-%m-%dT00:00:00)"
```

Rebuilding re-keys the ad-hoc cdhash, so this ONE re-grant covers all four
subcommands. (A stable Developer-ID / self-signed identity would make the grant
survive future rebuilds — see `docs/runbooks/calendar-officer-grant.md`.)

## STEP 2 — re-validate the READ subcommand's fail-closed behavior (do NOT skip)

Consolidation rebuilt the live, real-calendar-proven read binary; no automated
gate re-proves the refactored Swift read path. In the granted Terminal:

```bash
bin/cabinet-calread read "$(date +%Y-%m-%dT00:00:00)" "$(date -v+1d +%Y-%m-%dT00:00:00)"   # expect a JSON array of real events, each with all_day + availability
# and confirm it still FAILS CLOSED when access is withheld: revoke Full Access in
# System Settings → Privacy → Calendars, re-run → expect exit 3 + NOTHING on stdout
# (the load-bearing double-book property). Re-grant afterward.
```

## STEP 3 — prove uid == calendarItemExternalIdentifier (the fast-delete linchpin)

```bash
# Create a throwaway block via the SAME writer template, capture the returned uid:
osascript -e "$(python3.12 - <<'PY'
from framework.frontdoor.calendar_template import CALENDAR_EVENT_SCRIPT
print(CALENDAR_EVENT_SCRIPT)
PY
)" "Home" "cabinet-followup-canary" "runbook probe" "$(date -v+3d +%Y-%m-%dT15:00:00)"
# → prints ok:Home:<UID>. Then:
bin/cabinet-calread delete Home "<UID>"
# EXPECT: {"ok":true,"deleted":1} + exit 0, and the event is gone from Calendar.app.
# If it exits 4 (no match): uid != externalIdentifier — the fast path will ALWAYS
# fall back to the AppleScript delete (correct but not fast). Report that finding.
```

Also measure speed: the EventKit delete should be sub-second vs the AppleScript
fallback's 14-45s (the whole point of this wave).

## STEP 4 — real all-day availability data (the all-day filter's real basis)

```bash
# Read a window covering a real all-day Vacation/OOO day and a holiday/birthday day:
bin/cabinet-calread read "<vac-day>T00:00:00" "<vac-day+1>T00:00:00"
# Confirm the Vacation day carries availability:"busy" and a holiday carries
# "free" or "notSupported". This is the ONLY way to know real values (provider
# policy, not an Apple guarantee). With CABINET_CAL_ALLDAY_BUSY_BLOCKS=1, a busy
# all-day event should then block a same-day auto-block; a free holiday should not.
```

**Also check the all-day event's start/end SHAPE (review finding #4):** the JSON
must show a busy all-day event as `start: <day>T00:00:00`, `end: <day+1>T00:00:00`
(a real span). If a provider serializes all-day as a POINT (`start == end`), the
Python half-open `overlaps` test drops it → a busy all-day OOO would NOT block →
double-book. If you see point-duration all-day events, do NOT enable
`CABINET_CAL_ALLDAY_BUSY_BLOCKS` until the reader normalizes an all-day span to the
full day — tell me and I'll add that (a small reader-side fix). Default OFF is
safe regardless.

## STEP 5 — real sharees check (F1 blind-spot confirmation)

```bash
bin/cabinet-calread calinfo Home
# EXPECT: found:true, writable:true, ambiguous:false, shared:false, shared_signal:"none"
#         → Home clears the act-first gate with NO allowlist.
# Then point calinfo at a calendar Nate has ACTUALLY shared with someone and confirm
# it STILL reports shared_signal:"none" (the irreducible EventKit blind spot) —
# proving CABINET_CAL_PRIVATE (or the name-denylist) is the only positive protection
# for the writable-calDAV-shared-to-others case.
```

**When you apply PATCH 2, SET the positive allowlist (review finding #7):** add
`CABINET_CAL_PRIVATE="Home"` to `cabinet/.env`. Unset, the allowlist is a no-op and
the F1 gate leans only on the machine signal + name-denylist — which cannot see a
writable calDAV calendar shared to others. With it set, an act-first write is
PERMITTED only onto a listed calendar, closing that blind spot for this instance.

## STEP 6 — officer-context grant (the prompt-vs-deny question)

```bash
bash cabinet/scripts/diagnose-calendar-tcc.sh
# Runs `probe` under a transient launchd → bash → helper chain (self-cleaning,
# unique label). VERDICT: GRANTED (exit 0) / WRITE-ONLY (5) / SILENT DENY (3/4) /
# modal-waiting. If the officer chain silent-denies, the double-book gather RAISES
# (correct, fail-closed) and unattended calendar acts are simply unavailable there
# until the durable grant lands (docs/runbooks/calendar-officer-grant.md).
```

## STEP 7 — apply the germline patches + co-required tests

Apply `docs/proposals/germline-calendar-followups-2026-07-06.md` (PATCH 1 +
PATCH 2), add its co-required NEW tests, then:

```bash
python3.12 -m pytest framework/frontdoor/tests -q          # expect green
python3.12 -m pytest framework/tests/test_no_launcher_hardcode.py -q
bash cabinet/scripts/check-layer-separation.sh
```

## STEP 8 — live create→undo canary (still under the 120s osascript ceiling)

Re-run the existing forced create→undo canary against board 5091706356 with the
extra `calinfo` spawn on the act-first path; confirm it stays green and the
AppleScript fallback (if the fast delete falls back) still fits the 120s runner.
