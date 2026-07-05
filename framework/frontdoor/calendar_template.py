"""[GERM-2] Single source of the action lane's calendar-event AppleScript.

Imported by BOTH the executor (framework/frontdoor/action_exec.py:_exec_calendar_event)
and the classifier (framework/authority/classifier.py:_classify_bash) so
"byte-match the lane template" is literally true and can never drift — the
classifier types an osascript Calendar write as the reversible-with-undo
`calendar_event_create` ONLY when the command contains this exact string.

Zero dependencies (a leaf module — imports nothing), so importing it introduces
no cycle: the executor and the classifier both import it, never the reverse.
"""

CALENDAR_EVENT_SCRIPT = (
    'on run argv\n'
    'set calName to item 1 of argv\n'
    'set evTitle to item 2 of argv\n'
    'set evNotes to item 3 of argv\n'
    'set dueIso to item 4 of argv\n'
    'set startDate to my parseIso(dueIso)\n'
    'set endDate to startDate + (30 * minutes)\n'
    'tell application "Calendar"\n'
    # [RT-A7, 2026-07-05] NEVER redirect to or re-create the retired "Cabinet"
    # sandbox: the Captain DELETED it, so a silent fallback would resurrect it and
    # land events off his phone (defeating the whole point). A missing / non-
    # writable configured calendar FAILS LOUDLY — returns an "err:" string that
    # carries no "ok", so _exec_calendar_event raises and the card downgrades.
    ' if not (exists (first calendar whose name is calName)) then return "err:calendar-not-found:" & calName\n'
    ' set targetCal to (first calendar whose name is calName)\n'
    ' if (writable of targetCal is false) then return "err:calendar-not-writable:" & calName\n'
    ' tell targetCal\n'
    '  set newEvent to make new event with properties {summary:evTitle, start date:startDate, end date:endDate, description:evNotes}\n'
    ' end tell\n'
    'end tell\n'
    'return "ok:" & calName & ":" & (uid of newEvent)\n'
    'end run\n'
    'on parseIso(s)\n'
    ' set d to current date\n'
    ' set year of d to (text 1 thru 4 of s) as integer\n'
    ' set month of d to (text 6 thru 7 of s) as integer\n'
    ' set day of d to (text 9 thru 10 of s) as integer\n'
    ' if (length of s) > 10 then\n'
    '  set hours of d to (text 12 thru 13 of s) as integer\n'
    '  set minutes of d to (text 15 thru 16 of s) as integer\n'
    ' else\n'
    '  set hours of d to 9\n'
    '  set minutes of d to 0\n'
    ' end if\n'
    ' set seconds of d to 0\n'
    ' return d\n'
    'end parseIso')
