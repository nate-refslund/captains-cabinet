// cabinet-calread — read-only Apple Calendar provider helper for the Captain's
// Cabinet double-book gather (the calendar_event_create precondition).
//
// Subcommand:  read <start_iso> <end_iso>
//   → prints a JSON array of {calendar,start,end,summary} for TIMED events
//     overlapping [start,end) across ALL of the Captain's calendars, then exits 0.
//
// Why a signed binary: EventKit accessed from a bare script inherits the caller's
// (write-only) grant and is blind to the Captain's iCloud/Exchange/Google
// calendars. A binary signed with NSCalendarsFullAccessUsageDescription gets its
// OWN TCC identity and, at EKAuthorizationStatus.fullAccess, sees them all — fast
// (EventKit predicate, <0.1s) and complete.
//
// READ-ONLY BY CONSTRUCTION: this source contains NO EKEventStore save/remove and
// no event creation. It only ever reads.
//
// FAIL-CLOSED: if Full Access is not granted, it exits NON-ZERO with a stderr
// message and prints NOTHING to stdout — it must never emit an empty array when
// it simply cannot see the calendars, because the caller reads an empty result as
// "no conflict → safe to write" (a double-book). Only a real, fully-authorized
// read may return [].

import EventKit
import Foundation

@inline(__always)
func fail(_ msg: String, _ code: Int32 = 2) -> Never {
    FileHandle.standardError.write(Data((msg + "\n").utf8))
    exit(code)
}

func makeFormatter(_ fmt: String) -> DateFormatter {
    let df = DateFormatter()
    df.dateFormat = fmt
    df.timeZone = TimeZone.current               // naive local wall-clock (matches Python _parse_iso)
    df.locale = Locale(identifier: "en_US_POSIX")
    return df
}

let isoSec = makeFormatter("yyyy-MM-dd'T'HH:mm:ss")   // canonical output + primary input

// Parse a bound in the same naive-local frame Python uses: trim a trailing 'Z',
// accept second-, minute-, or date-only precision. Unparseable → fail-loud.
func parseBound(_ raw: String) -> Date {
    var s = raw
    if s.hasSuffix("Z") { s.removeLast() }
    for fmt in ["yyyy-MM-dd'T'HH:mm:ss", "yyyy-MM-dd'T'HH:mm", "yyyy-MM-dd"] {
        if let d = makeFormatter(fmt).date(from: s) { return d }
    }
    fail("unparseable ISO bound: \(raw)", 64)
}

let args = CommandLine.arguments
guard args.count >= 2, args[1] == "read" else {
    fail("usage: cabinet-calread read <start_iso> <end_iso>", 64)
}
guard args.count == 4 else {
    fail("usage: cabinet-calread read <start_iso> <end_iso>", 64)
}
let start = parseBound(args[2])
let end = parseBound(args[3])

let store = EKEventStore()
let sema = DispatchSemaphore(value: 0)
var granted = false
var reqErr: Error?
if #available(macOS 14.0, *) {
    store.requestFullAccessToEvents { ok, err in granted = ok; reqErr = err; sema.signal() }
} else {
    store.requestAccess(to: .event) { ok, err in granted = ok; reqErr = err; sema.signal() }
}
sema.wait()

if !granted {
    fail("calendar access not granted (need Full Access)" + (reqErr.map { ": \($0)" } ?? ""), 3)
}
// Belt-and-suspenders: a write-only grant must NEVER yield a silent partial read.
if #available(macOS 14.0, *), EKEventStore.authorizationStatus(for: .event) != .fullAccess {
    fail("calendar access is not Full (write-only/restricted) — refusing a partial read", 3)
}

// A freshly-spawned subprocess store (the gather runs headless, Calendar.app not
// open) can hold not-yet-synced remote sources — and under-reporting is the UNSAFE
// direction (fewer events → no conflict → write). Force a source refresh first.
store.refreshSourcesIfNecessary()

let pred = store.predicateForEvents(withStart: start, end: end, calendars: nil)
let out: [[String: String]] = store.events(matching: pred)
    .filter { !$0.isAllDay }                     // all-day markers don't occupy a 30-min slot
    .map { ev in
        [
            "calendar": ev.calendar?.title ?? "",
            "start": isoSec.string(from: ev.startDate),
            "end": isoSec.string(from: ev.endDate),
            "summary": ev.title ?? "",
        ]
    }

guard let data = try? JSONSerialization.data(withJSONObject: out, options: []) else {
    fail("failed to serialize events to JSON", 1)
}
FileHandle.standardOutput.write(data)
FileHandle.standardOutput.write(Data("\n".utf8))
