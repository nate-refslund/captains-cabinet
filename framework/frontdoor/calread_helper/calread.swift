// cabinet-calread — signed EventKit calendar helper for the Captain's Cabinet.
//
// ONE consolidated binary, dispatched on argv[1]:
//
//   read   <start_iso> <end_iso>
//     → JSON ARRAY of {calendar,start,end,summary,all_day,availability} for EVERY
//       event overlapping [start,end) across ALL of the Captain's calendars, then
//       exit 0. It NO LONGER drops all-day events — it tags each with all_day +
//       availability so 100% of the all-day/free-vs-busy policy lives in the
//       freely-editable Python reader (calendar_read.py) and no future policy
//       tweak needs another rebuild/re-grant.
//
//   delete <calendar> <externalId>
//     → remove the single event whose calendarItemExternalIdentifier == externalId
//       AND whose calendar.title == <calendar>, CONFIRM removal by re-query, then
//       print {"ok":true,"deleted":N} + exit 0. The reverse/undo side. Read+write
//       (needs fullAccess). Exits NON-ZERO on ANY uncertainty (0-match=4,
//       recurrence=5, remove-throw / unconfirmed=6) — it NEVER prints a success it
//       did not confirm. fullAccess is acquired BEFORE any lookup (the write-only
//       trap: a write-only grant answers a lookup with [] WITHOUT throwing, which a
//       lookup-based delete would misread as "already gone → success").
//
//   calinfo <calendar>
//     → JSON OBJECT of real EventKit attributes for the named calendar
//       {calendar,found,ambiguous,writable,shared,shared_signal,type}, exit 0.
//       The real-sharees pre-write gate (F1) reads this. NOTE the honest limit:
//       macOS public EventKit has NO sharees/isShared/owner API, so a WRITABLE
//       calDAV calendar the Captain shared with others reports shared_signal="none"
//       and is indistinguishable from a private one — the positive protection for
//       that case is the reader's CABINET_CAL_PRIVATE allowlist + name-denylist.
//
//   probe
//     → EKEventStore.authorizationStatus(for:.event) ONLY (no window, no
//       requestAccess, no read); print the status token; exit 0 fullAccess,
//       5 writeOnly, 4 notDetermined, 3 denied/restricted. The officer boot
//       self-check reads this to convert a silent grant-denial into one loud line.
//
// Why a signed binary: EventKit from a bare script inherits the caller's
// (write-only) grant and is blind to the Captain's iCloud/Exchange/Google
// calendars. A binary signed with NSCalendarsFullAccessUsageDescription gets its
// OWN TCC identity and, at EKAuthorizationStatus.fullAccess, sees them all.
//
// FAIL-CLOSED: read/delete/calinfo exit NON-ZERO and print NOTHING to stdout when
// Full Access is not granted — they must NEVER emit an empty result when they
// simply cannot see the calendars (a caller reads [] as "no conflict → safe to
// write" = a double-book; and a delete reads [] as "already gone → undone" = a
// false success). Only a real, fully-authorized operation may print a result.
//
// An unknown subcommand or a wrong argc exits 64 (usage) so an OLD helper (which
// only knows `read`) is detectable and the boot script can fall back to `read`.

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

func writeStdout(_ data: Data) {
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data("\n".utf8))
}

func emitObject(_ obj: [String: Any]) {
    guard let data = try? JSONSerialization.data(withJSONObject: obj, options: [.sortedKeys]) else {
        fail("failed to serialize JSON object", 1)
    }
    writeStdout(data)
}

// The SHARED fullAccess gate, called by read/delete/calinfo. Requests access,
// then asserts the grant is FULL (a write-only/restricted grant must never yield
// a silent partial read or an unconfirmable delete), then forces a source refresh
// (a freshly-spawned headless store can hold not-yet-synced remote sources, and
// under-reporting is the UNSAFE direction). Exits 3 without full access — BEFORE
// any calendarItems/events lookup, so the write-only trap can never fire.
func requireFullAccess(_ store: EKEventStore) {
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
    if #available(macOS 14.0, *), EKEventStore.authorizationStatus(for: .event) != .fullAccess {
        fail("calendar access is not Full (write-only/restricted) — refusing", 3)
    }
    store.refreshSourcesIfNecessary()
}

// EKEventAvailability → a stable lowercase token. @unknown default keeps a future
// enum case honest as "unknown" (which the reader treats as a KEEP-as-conflict).
func availabilityString(_ a: EKEventAvailability) -> String {
    switch a {
    case .busy: return "busy"
    case .free: return "free"
    case .tentative: return "tentative"
    case .unavailable: return "unavailable"
    case .notSupported: return "notSupported"
    @unknown default: return "unknown"
    }
}

func calendarTypeString(_ t: EKCalendarType) -> String {
    switch t {
    case .local: return "local"
    case .calDAV: return "calDAV"
    case .exchange: return "exchange"
    case .subscription: return "subscription"
    case .birthday: return "birthday"
    @unknown default: return "unknown"
    }
}

// The only machine-detectable "not my private writable calendar" signals EventKit
// exposes (there is NO public sharees/isShared/owner API): a read-only calendar
// (subscribed team/holiday, view-only share), a subscription, or a birthday
// calendar. A writable calDAV calendar shared to others is INDISTINGUISHABLE from
// a private one here → "none" (covered by the reader's allowlist + name-denylist).
func sharedSignal(_ c: EKCalendar) -> String {
    if c.type == .subscription { return "subscription" }
    if c.type == .birthday { return "birthday" }
    if !c.allowsContentModifications { return "read_only" }
    return "none"
}

// --- subcommands -------------------------------------------------------------

func runRead(_ startArg: String, _ endArg: String) {
    let start = parseBound(startArg)
    let end = parseBound(endArg)
    let store = EKEventStore()
    requireFullAccess(store)
    let pred = store.predicateForEvents(withStart: start, end: end, calendars: nil)
    let out: [[String: String]] = store.events(matching: pred).map { ev in
        [
            "calendar": ev.calendar?.title ?? "",
            "start": isoSec.string(from: ev.startDate),
            "end": isoSec.string(from: ev.endDate),
            "summary": ev.title ?? "",
            "all_day": ev.isAllDay ? "true" : "false",
            "availability": availabilityString(ev.availability),
        ]
    }
    guard let data = try? JSONSerialization.data(withJSONObject: out, options: []) else {
        fail("failed to serialize events to JSON", 1)
    }
    writeStdout(data)
}

func runDelete(_ calName: String, _ uid: String) {
    let store = EKEventStore()
    // fullAccess FIRST — BEFORE any lookup (the write-only trap defense).
    requireFullAccess(store)
    func matches() -> [EKEvent] {
        return store.calendarItems(withExternalIdentifier: uid)
            .compactMap { $0 as? EKEvent }
            .filter { $0.calendar?.title == calName }
    }
    let found = matches()
    if found.isEmpty {
        // 0-match: cannot CONFIRM a removal. Fail-loud (the reader falls back to
        // the authoritative AppleScript delete which keys on the true uid space).
        fail("no event with external id in calendar \(calName) — cannot confirm delete", 4)
    }
    for ev in found where ev.hasRecurrenceRules {
        // A recurring series is NOT a lane-created single 30-min block; refuse to
        // touch it (removing .thisEvent of a series is a surprise mutation).
        fail("matched event is recurring — refusing (not a lane-created single event)", 5)
    }
    for ev in found {
        do {
            try store.remove(ev, span: .thisEvent, commit: true)
        } catch {
            fail("removeEvent failed: \(error)", 6)
        }
    }
    // Re-query to CONFIRM the event is actually gone before claiming success.
    if !matches().isEmpty {
        fail("event still present after remove — delete not confirmed", 6)
    }
    emitObject(["ok": true, "deleted": found.count])
}

func runCalinfo(_ calName: String) {
    let store = EKEventStore()
    requireFullAccess(store)
    let cals = store.calendars(for: .event).filter { $0.title == calName }
    if cals.isEmpty {
        emitObject([
            "calendar": calName, "found": false, "ambiguous": false,
            "writable": false, "shared": false, "shared_signal": "none",
            "type": "none",
        ])
        return
    }
    // Aggregate fail-closed across same-title calendars: writable iff ALL are,
    // shared iff ANY is, ambiguous iff more than one shares the title.
    let writableAll = cals.allSatisfy { $0.allowsContentModifications }
    var signal = "none"
    for c in cals {
        let s = sharedSignal(c)
        if s != "none" { signal = s; break }
    }
    emitObject([
        "calendar": calName,
        "found": true,
        "ambiguous": cals.count > 1,
        "writable": writableAll,
        "shared": signal != "none",
        "shared_signal": signal,
        "type": calendarTypeString(cals[0].type),
    ])
}

func runProbe() {
    if #available(macOS 14.0, *) {
        switch EKEventStore.authorizationStatus(for: .event) {
        case .fullAccess: print("fullAccess"); exit(0)
        case .writeOnly: print("writeOnly"); exit(5)
        case .notDetermined: print("notDetermined"); exit(4)
        default: print("denied"); exit(3)     // denied / restricted / @unknown
        }
    } else {
        switch EKEventStore.authorizationStatus(for: .event) {
        case .authorized: print("authorized"); exit(0)
        case .notDetermined: print("notDetermined"); exit(4)
        default: print("denied"); exit(3)
        }
    }
}

// --- dispatch ----------------------------------------------------------------

let usage = "usage: cabinet-calread read <start> <end> | delete <calendar> <uid> "
    + "| calinfo <calendar> | probe"
let args = CommandLine.arguments
guard args.count >= 2 else { fail(usage, 64) }

switch args[1] {
case "read":
    guard args.count == 4 else { fail(usage, 64) }
    runRead(args[2], args[3])
case "delete":
    guard args.count == 4 else { fail(usage, 64) }
    runDelete(args[2], args[3])
case "calinfo":
    guard args.count == 3 else { fail(usage, 64) }
    runCalinfo(args[2])
case "probe":
    guard args.count == 2 else { fail(usage, 64) }
    runProbe()
default:
    fail(usage, 64)
}
