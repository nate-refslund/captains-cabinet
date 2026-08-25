// main.swift — "Hatch Cabinet.app" v0.6.0 thin-shell stub (HATCH-APPSHELL-V05).
//
// Doctrine: orchestrate-never-reimplement — ZERO hatch logic lives here. The
// stub (1) recognises whether this Mac already has a Cabinet, (2) hands off to
// Terminal on hatch-run.command via Launch Services (/usr/bin/open -a
// Terminal) — no Apple-events automation of Terminal, no scripting bridges —
// and (3) never claims the WORLD-ONBOARDING-V1B stranger bars (claims-lint.sh
// enforces the strings).
//
// THE APP IS A LAUNCHER (2026-08-25). It was an installer: it set a Cabinet up
// once, and every double-click after that had nothing to offer but a read-only
// check-over or Quit. Measured on the Captain's Mac — second double-click over
// a healthy install, no message, no browser, a Terminal window that ended on
// "[Process completed]". Two things were wrong and both are fixed here: there
// was no path that OPENED the Cabinet, and the one path there was handed the
// runner a request it answered by replacing itself with another program, so
// nothing ever printed a closing sentence.
//
// So: double-click means "take me to my Cabinet". Install once, launch
// forever, and start over only by choosing to.
//
//   already a Cabinet   -> Open my Cabinet (start it if needed, then browser)
//                          · Start completely fresh… · Check it over · Quit
//   nothing there yet   -> the ordinary first-time setup, unchanged
//   something else there -> say so plainly and offer the move-aside path;
//                          NEVER write over it, never delete it
//
// STARTING FRESH MOVES, IT NEVER DELETES. The old Cabinet is renamed to a
// dated `archived-…` folder beside it, its contents untouched, and the operator
// has to type the words to get there. There is no delete call on that path —
// `removeItem` appears exactly once in this file, on the app's own handoff
// script, and a test pins that.
//
// Modes:
//   default              native dialogs (NSAlert), then Terminal handoff
//   HATCH_APP_PROBE=1    headless, READ-ONLY: prints the detected state
//   HATCH_APP_SMOKE=1    headless CI smoke: unpack + engine --dry-run --defaults
//   HATCH_APP_SMOKE=fresh  headless: archive an existing prefix, then as above.
//                          NEVER stops anything — the fleet-stop is a dialog-
//                          path act, because a test must not touch a live Mac.
//
// Env:
//   CABINET_HATCH_PREFIX  install prefix override (default ~/Cabinet/captains-cabinet)
//
// Build: swiftc via build-hatch-app.sh (ad-hoc signed bundle). Compiled on the
// dev Mac only — the hatch target never compiles anything.

import AppKit

let appVersion = "0.6.0"
let defaultPrefix = "~/Cabinet/captains-cabinet"
/// The only requests the stub may hand the runner (the runner re-validates).
let allowedRequests: Set<String> = ["hatch", "hatch --with-launchd", "doctor", "open"]
/// The words an operator types to move an existing Cabinet aside. Exact match,
/// case-sensitive: a typed phrase is the one confirmation a reflex click cannot
/// give by accident.
let freshConfirmPhrase = "START FRESH"

struct ShellError: Error, CustomStringConvertible { let description: String }

func stderrLine(_ s: String) {
    FileHandle.standardError.write((s + "\n").data(using: .utf8)!)
}

/// Fixed-argv subprocess: absolute tool path + literal argument array only.
func run(_ tool: String, _ args: [String], cwd: String? = nil) throws -> Int32 {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: tool)
    p.arguments = args
    if let cwd = cwd { p.currentDirectoryURL = URL(fileURLWithPath: cwd) }
    try p.run()
    p.waitUntilExit()
    return p.terminationStatus
}

func resourcePath(_ name: String) throws -> String {
    guard let base = Bundle.main.resourceURL else {
        throw ShellError(description: "bundle has no Resources dir")
    }
    let path = base.appendingPathComponent(name).path
    guard FileManager.default.fileExists(atPath: path) else {
        throw ShellError(description: "bundle resource missing: \(name)")
    }
    return path
}

// ---- what is actually in the prefix ----------------------------------------------

/// `cabinet` is the only state that gets the launcher. Everything else is
/// either an empty lot to build on, or something we must not touch.
enum PrefixState: String { case absent, empty, cabinet, occupied }

/// The engine — proves the payload was unpacked here at all.
let markerEngine = "cabinet/scripts/hatch.sh"
/// Written BY the hatch run and gitignored, so it is in no export and cannot
/// arrive from an unpack: its presence means setup actually ran to the point
/// of choosing this deployment's shape.
let markerPreset = "instance/config/active-preset"
/// Also hatch-written and gitignored — the deployment's own env file. Either
/// marker is enough; an operator who cleared one still has a Cabinet.
let markerEnv = "cabinet/.env"

func isNonEmptyFile(_ path: String) -> Bool {
    let fm = FileManager.default
    var isDir: ObjCBool = false
    guard fm.fileExists(atPath: path, isDirectory: &isDir), !isDir.boolValue else { return false }
    guard let attrs = try? fm.attributesOfItem(atPath: path) else { return false }
    return ((attrs[.size] as? NSNumber)?.intValue ?? 0) > 0
}

/// An honest predicate, and honest about what it cannot see: it asks whether
/// this folder is a cabinet that FINISHED setting up, not whether that cabinet
/// is healthy. A half-written tree — an unpack that died, a folder someone else
/// made — answers no, which is what keeps the launcher off it.
func looksLikeCabinet(_ prefix: String) -> Bool {
    let fm = FileManager.default
    guard fm.fileExists(atPath: prefix + "/" + markerEngine) else { return false }
    if isNonEmptyFile(prefix + "/" + markerPreset) { return true }
    if fm.fileExists(atPath: prefix + "/" + markerEnv) { return true }
    return false
}

func prefixState(_ prefix: String) -> PrefixState {
    let fm = FileManager.default
    var isDir: ObjCBool = false
    guard fm.fileExists(atPath: prefix, isDirectory: &isDir) else { return .absent }
    guard isDir.boolValue else { return .occupied } // a non-dir in the way
    let entries = (try? fm.contentsOfDirectory(atPath: prefix)) ?? ["?"]
    if entries.isEmpty { return .empty }
    return looksLikeCabinet(prefix) ? .cabinet : .occupied
}

// ---- the handoff script ----------------------------------------------------------

/// The app's own files inside the prefix. There are three, they all live at the
/// TOP of the install (never inside the operator's `cabinet/`), and they are
/// refreshed on EVERY handoff rather than only on a first install:
///
///   hatch-run.command        the Terminal runner
///   .hatch-open.command      a copy of cabinet/scripts/open-cabinet.sh
///   .hatch-dashboard-lib.sh  a copy of cabinet/scripts/lib/dashboard.sh
///
/// WHY REFRESH. These are the app's orchestration, versioned with the app. An
/// install made by an OLDER app carries an older runner that does not know the
/// requests this one sends, and a Cabinet set up before the opener existed has
/// no opener at all — that install is exactly the one someone is double-clicking
/// this app to get back into. Carrying our own copies is what makes "install
/// once, launch forever" survive both directions of that skew.
///
/// WHY THE COPIES ARE NEVER WRITTEN INTO cabinet/scripts/. That tree belongs to
/// the Cabinet, and a newer Cabinet may well have a newer opener than this app
/// does. The runner and the opener therefore PREFER the cabinet's own copy and
/// fall back to these only when it is absent.
///
/// The egg payload is never re-unpacked and nothing of the operator's is touched.
let appOwnedFiles: [(resource: String, name: String)] = [
    ("hatch-run.command", "hatch-run.command"),
    ("open-cabinet.sh", ".hatch-open.command"),
    ("lib-dashboard.sh", ".hatch-dashboard-lib.sh"),
]

func installRunner(into prefix: String) throws {
    let fm = FileManager.default
    for f in appOwnedFiles {
        let src = try resourcePath(f.resource)
        let dst = prefix + "/" + f.name
        if fm.fileExists(atPath: dst) { try fm.removeItem(atPath: dst) }
        try fm.copyItem(atPath: src, toPath: dst)
        try fm.setAttributes([.posixPermissions: 0o755], ofItemAtPath: dst)
    }
}

/// Unpack the bundled egg into the prefix. Refusing to clobber is the caller's
/// job (prefixState) — this only ever runs against absent/empty prefixes.
func unpack(into prefix: String) throws {
    let fm = FileManager.default
    let zip = try resourcePath("payload/cabinet-egg.zip")
    try fm.createDirectory(atPath: prefix, withIntermediateDirectories: true)
    guard try run("/usr/bin/ditto", ["-x", "-k", zip, prefix]) == 0 else {
        throw ShellError(description: "payload extraction failed (ditto -x -k)")
    }
    try installRunner(into: prefix)
    // Strip quarantine on the EXTRACTED PAYLOAD ONLY — never on the .app
    // itself (no Gatekeeper evasion; best-effort, absent xattrs are fine).
    _ = try? run("/usr/bin/xattr", ["-dr", "com.apple.quarantine", prefix])
    guard fm.fileExists(atPath: prefix + "/" + markerEngine) else {
        throw ShellError(description: "extracted payload is missing \(markerEngine)")
    }
}

func writeRequest(_ request: String, prefix: String, archived: String? = nil) throws {
    guard allowedRequests.contains(request) else {
        throw ShellError(description: "internal: request not in allowlist")
    }
    var body = request + "\n"
    // Line 2, when there is one, is where the previous Cabinet went — so the
    // Terminal window can say it too. The runner accepts it only as an
    // absolute path and drops anything else.
    if let archived = archived { body += archived + "\n" }
    try body.write(toFile: prefix + "/.hatch-run-args", atomically: true, encoding: .utf8)
}

func openTerminal(onRunnerIn prefix: String) throws {
    let runner = prefix + "/hatch-run.command"
    guard try run("/usr/bin/open", ["-a", "Terminal", runner]) == 0 else {
        throw ShellError(description: "could not open Terminal on \(runner)")
    }
}

// ---- starting over: MOVE, never delete -------------------------------------------

func archiveStamp() -> String {
    let f = DateFormatter()
    f.dateFormat = "yyyyMMdd-HHmmss"
    f.timeZone = TimeZone(identifier: "UTC")
    f.locale = Locale(identifier: "en_US_POSIX")
    return f.string(from: Date())
}

/// Rename the existing install to a dated sibling and return where it went.
/// A rename, on the same volume, of the whole tree: nothing is copied, nothing
/// is deleted, and every byte the operator had is still on disk under the new
/// name. If the name is somehow taken, this counts up rather than overwriting.
func archiveInstall(at prefix: String) throws -> String {
    let fm = FileManager.default
    // Degenerate end, and the only place it could ever matter: the prefix is
    // operator-settable (CABINET_HATCH_PREFIX). Moving a home directory or a
    // volume root is not an install being replaced, it is a disaster, so those
    // are refused before anything is touched — typed confirmation or not.
    let normalized = (prefix as NSString).standardizingPath
    let home = NSHomeDirectory()
    guard normalized.hasPrefix("/"), normalized != "/", normalized != home,
          !home.hasPrefix(normalized + "/") else {
        throw ShellError(description:
            "refusing to move \(prefix) — that is a home or root folder, not an install")
    }
    let parent = (normalized as NSString).deletingLastPathComponent
    let base = parent + "/archived-" + archiveStamp()
    var dest = base
    var n = 2
    while fm.fileExists(atPath: dest) {
        dest = base + "-\(n)"
        n += 1
        if n > 50 { throw ShellError(description: "could not find a free name beside \(prefix)") }
    }
    try fm.moveItem(atPath: normalized, toPath: dest)
    return dest
}

/// Ask the old Cabinet's own script to stop anything it had running in the
/// background, before its folder moves out from under it. Delegated, never
/// re-implemented: `deploy-mac.sh --stop all` is the sanctioned teardown and it
/// owns the boot-out idiom. Best effort by design — an install too broken to
/// have that script is exactly the one being moved aside.
func stopOldCabinet(at prefix: String) -> Bool {
    let script = prefix + "/cabinet/scripts/deploy-mac.sh"
    guard FileManager.default.fileExists(atPath: script) else { return false }
    let rc = (try? run("/bin/bash", [script, "--stop", "all"], cwd: prefix)) ?? -1
    return rc == 0
}

// ---- headless modes (CI + tests): no dialogs, no Terminal ------------------------

func probeMain(prefix: String) -> Int32 {
    // Read-only by construction: it looks, prints, and exits.
    print("state=\(prefixState(prefix).rawValue)")
    print("prefix=\(prefix)")
    return 0
}

func smokeMain(prefix: String, fresh: Bool) -> Int32 {
    do {
        if fresh {
            // The move half of "start completely fresh", exercised for real.
            // The fleet-stop is deliberately NOT here: a test must never boot
            // out LaunchAgents on the machine it happens to be running on.
            if prefixState(prefix) != .absent {
                let dest = try archiveInstall(at: prefix)
                print("archived: \(dest)")
            }
        } else if prefixState(prefix) != .absent, prefixState(prefix) != .empty {
            stderrLine("smoke: prefix \(prefix) is not empty — refusing to clobber an existing install")
            return 2
        }
        try unpack(into: prefix)
        // Engine dry-run on the unpacked export bytes: prints the numbered
        // plan + errand notes, executes nothing.
        return try run("/bin/bash", ["cabinet/scripts/hatch.sh", "--dry-run", "--defaults"], cwd: prefix)
    } catch {
        stderrLine("smoke: \(error)")
        return 1
    }
}

// ---- dialog mode -----------------------------------------------------------------

/// Returns the 0-based index of the pressed button.
func ask(_ title: String, _ body: String, buttons: [String]) -> Int {
    let a = NSAlert()
    a.messageText = title
    a.informativeText = body
    for b in buttons { a.addButton(withTitle: b) }
    return a.runModal().rawValue - NSApplication.ModalResponse.alertFirstButtonReturn.rawValue
}

/// The typed confirmation. Returns the text the operator typed, or nil if they
/// backed out. Nothing is done with a wrong answer except say so.
func askTyped(_ title: String, _ body: String, ok: String) -> String? {
    let a = NSAlert()
    a.messageText = title
    a.informativeText = body
    let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 260, height: 24))
    field.placeholderString = freshConfirmPhrase
    a.accessoryView = field
    // Back is the DEFAULT (Return), so the destructive-looking path always
    // takes a deliberate click — the one-actuator idiom used for move-in.
    a.addButton(withTitle: "Back")
    a.addButton(withTitle: ok)
    let pressed = a.runModal().rawValue - NSApplication.ModalResponse.alertFirstButtonReturn.rawValue
    guard pressed == 1 else { return nil }
    return field.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
}

/// The whole start-over flow. Returns where the old Cabinet went, or nil when
/// the operator backed out (in which case nothing at all has happened).
func startFresh(prefix: String, isCabinet: Bool) -> String? {
    let what = isCabinet
        ? "Everything your Cabinet has learned — your answers, its notes, what it has read and written — lives in this folder:"
        : "Whatever is in this folder — including a setup that stopped partway — lives here:"
    let typed = askTyped(
        "Start over with a new Cabinet?",
        what + "\n\(prefix)\n\n"
        + "Starting fresh does not delete any of it. The whole folder is renamed and left "
        + "beside itself, dated, so you can go back to it or copy things out of it later.\n\n"
        + "Anything this Cabinet had running in the background is stopped first.\n\n"
        + "If that is what you want, type \(freshConfirmPhrase) below.",
        ok: "Move it aside and set up a new one")
    guard let typed = typed else { return nil }
    guard typed == freshConfirmPhrase else {
        _ = ask("Nothing was changed",
                "That didn't match \(freshConfirmPhrase), so nothing was moved and nothing was "
                + "started. Your Cabinet is exactly as it was.",
                buttons: ["OK"])
        return nil
    }
    if isCabinet { _ = stopOldCabinet(at: prefix) }
    do {
        let dest = try archiveInstall(at: prefix)
        _ = ask("Your old Cabinet has been moved aside",
                "It is all still here, nothing deleted:\n\(dest)\n\n"
                + "Setting up the new one starts next.",
                buttons: ["Continue"])
        return dest
    } catch {
        _ = ask("Could not move the old folder",
                "\(error)\n\nNothing was moved, nothing was deleted and nothing was started. "
                + "Your Cabinet is exactly as it was.",
                buttons: ["Quit"])
        return nil
    }
}

func dialogMain(prefix: String) -> Int32 {
    let app = NSApplication.shared
    app.setActivationPolicy(.regular)
    app.activate(ignoringOtherApps: true)

    var archived: String? = nil

    // ---- there is already a Cabinet here: this is the everyday path ----------
    if prefixState(prefix) == .cabinet {
        let choice = ask(
            "Your Cabinet is already set up here",
            "\(prefix)\n\n"
            + "Opening it starts it if it isn't running, then opens it in your browser. "
            + "A Terminal window shows what is happening and closes itself when you are in.\n\n"
            + "Captain's Cabinet, version \(appVersion)",
            buttons: ["Open my Cabinet", "Start completely fresh…", "Check it over", "Quit"])
        switch choice {
        case 0, 2:
            let request = choice == 0 ? "open" : "doctor"
            do {
                try installRunner(into: prefix)
                try writeRequest(request, prefix: prefix)
                try openTerminal(onRunnerIn: prefix)
            } catch {
                _ = ask("Could not open your Cabinet",
                        "\(error)\n\nNothing was changed. You can start it yourself in Terminal:\n"
                        + "  bash \(prefix)/cabinet/scripts/open-cabinet.sh",
                        buttons: ["Quit"])
                return 1
            }
            return 0
        case 1:
            guard let dest = startFresh(prefix: prefix, isCabinet: true) else { return 0 }
            archived = dest
        default:
            return 0
        }
    } else if prefixState(prefix) == .occupied {
        // Non-empty and not a finished Cabinet. Honest about the ambiguity, and
        // it never writes over what is there.
        let choice = ask(
            "There is something else in this folder",
            "There is already something in\n\(prefix)\n\n"
            + "It is not a Cabinet that finished setting up — most likely a setup that was "
            + "interrupted partway. This app never writes over it.\n\n"
            + "Starting fresh renames that folder, dated, and leaves it beside itself. "
            + "Nothing in it is deleted.",
            buttons: ["Start completely fresh…", "Quit"])
        guard choice == 0 else { return 0 }
        guard let dest = startFresh(prefix: prefix, isCabinet: false) else { return 0 }
        archived = dest
    }

    // ---- first-time setup (also where a start-over lands) --------------------
    do {
        var request: String?
        while request == nil {
            let choice = ask(
                "Set up Captain's Cabinet",
                "This will take a few minutes and open in your browser when it is ready. "
                + "You can leave it running.\n\n"
                + "A Terminal window will open and scroll while it works. That is normal — "
                + "you do not need to type anything.\n\n"
                + "Everything goes in this folder, and a record of the run is kept in "
                + "~/hatch-logs:\n\(prefix)\n\n"
                + "The second button also lets your Cabinet keep working while you are "
                + "away. It asks you to confirm first.\n\n"
                + "Captain's Cabinet setup, version \(appVersion)",
                buttons: ["Set up", "Set up, and keep it running", "Cancel"])
            switch choice {
            case 0:
                request = "hatch"
            case 1:
                // One-actuator doctrine: move-in only on a SECOND explicit
                // confirm — and Back is the DEFAULT (Return) button, so
                // arming --with-launchd always takes a deliberate click,
                // never a reflex default-accept.
                let confirm = ask(
                    "Let it keep working while you are away?",
                    "Your Cabinet will keep running in the background instead of only while "
                    + "you are watching it. macOS will show a "
                    + "\u{201C}Background Items Added\u{201D} notification when it does.\n\n"
                    + "You can decide this later instead: choose Back, and setup will tell "
                    + "you the one command that turns it on whenever you want it.\n\n"
                    + "Either way, if it cannot start on this Mac, setup says so plainly and "
                    + "still opens your Cabinet in your browser.",
                    buttons: ["Back", "Yes, keep it running"])
                if confirm == 1 { request = "hatch --with-launchd" }
            default:
                return 0
            }
        }
        try unpack(into: prefix)
        try writeRequest(request!, prefix: prefix, archived: archived)
        try openTerminal(onRunnerIn: prefix)
        return 0
    } catch {
        _ = ask("Setup could not start",
                "\(error)\n\nNothing was started, and nothing else on your Mac was changed. "
                + "Any notes are in ~/hatch-logs.\n\n"
                + "If setup stopped partway, move this folder to the Trash before trying "
                + "again — this app will not write over a folder that already has "
                + "something in it:\n\(prefix)",
                buttons: ["Quit"])
        return 1
    }
}

// ---- entry -----------------------------------------------------------------------

let env = ProcessInfo.processInfo.environment
let prefix = ((env["CABINET_HATCH_PREFIX"] ?? defaultPrefix) as NSString).expandingTildeInPath
let smoke = env["HATCH_APP_SMOKE"] ?? ""
if env["HATCH_APP_PROBE"] == "1" {
    exit(probeMain(prefix: prefix))
} else if smoke == "1" || smoke == "fresh" {
    exit(smokeMain(prefix: prefix, fresh: smoke == "fresh"))
} else {
    exit(dialogMain(prefix: prefix))
}
