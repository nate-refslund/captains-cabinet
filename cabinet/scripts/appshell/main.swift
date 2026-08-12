// main.swift — "Hatch Cabinet.app" v0.5.1 thin-shell stub (HATCH-APPSHELL-V05).
//
// Doctrine: orchestrate-never-reimplement — ZERO hatch logic lives here. The
// stub (1) unpacks the bundled egg payload to a stable prefix, (2) hands off
// to Terminal on hatch-run.command via Launch Services (/usr/bin/open -a
// Terminal) — no Apple-events automation of Terminal, no scripting bridges —
// and (3) on re-launch over an existing install offers the read-only doctor
// instead. It never re-unpacks, never overwrites, and never claims the
// WORLD-ONBOARDING-V1B stranger bars (claims-lint.sh enforces the strings).
//
// WORDING (2026-08-12, never-strand pass): every string below is read by
// whoever double-clicked this icon, and by nobody else. So they are written
// for a person: what is about to happen, how long it takes, what they need to
// do (usually nothing), and what to do if something is in the way. The
// vocabulary of this codebase — hatch, move-in, egg, launch agents, First
// Mate, errand notes — stays out of them. Identifiers, comments, requests and
// the allowlist keep it, because that is where it belongs.
//
// Modes:
//   default              native dialogs (NSAlert), then Terminal handoff
//   HATCH_APP_SMOKE=1    headless CI smoke: unpack + engine --dry-run --defaults
//
// Env:
//   CABINET_HATCH_PREFIX  install prefix override (default ~/Cabinet/captains-cabinet)
//
// Build: swiftc via build-hatch-app.sh (ad-hoc signed bundle). Compiled on the
// dev Mac only — the hatch target never compiles anything.

import AppKit

let appVersion = "0.5.1"
let defaultPrefix = "~/Cabinet/captains-cabinet"
/// The only requests the stub may hand the runner (the runner re-validates).
let allowedRequests: Set<String> = ["hatch", "hatch --with-launchd", "doctor"]

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

enum PrefixState { case absent, empty, populated }

func prefixState(_ prefix: String) -> PrefixState {
    let fm = FileManager.default
    var isDir: ObjCBool = false
    guard fm.fileExists(atPath: prefix, isDirectory: &isDir) else { return .absent }
    guard isDir.boolValue else { return .populated } // a non-dir in the way = occupied
    let entries = (try? fm.contentsOfDirectory(atPath: prefix)) ?? ["?"]
    return entries.isEmpty ? .empty : .populated
}

/// Unpack the bundled egg into the prefix. Refusing to clobber is the caller's
/// job (prefixState) — this only ever runs against absent/empty prefixes.
func unpack(into prefix: String) throws {
    let fm = FileManager.default
    let zip = try resourcePath("payload/cabinet-egg.zip")
    let runnerSrc = try resourcePath("hatch-run.command")
    try fm.createDirectory(atPath: prefix, withIntermediateDirectories: true)
    guard try run("/usr/bin/ditto", ["-x", "-k", zip, prefix]) == 0 else {
        throw ShellError(description: "payload extraction failed (ditto -x -k)")
    }
    let runnerDst = prefix + "/hatch-run.command"
    if fm.fileExists(atPath: runnerDst) { try fm.removeItem(atPath: runnerDst) }
    try fm.copyItem(atPath: runnerSrc, toPath: runnerDst)
    try fm.setAttributes([.posixPermissions: 0o755], ofItemAtPath: runnerDst)
    // Strip quarantine on the EXTRACTED PAYLOAD ONLY — never on the .app
    // itself (no Gatekeeper evasion; best-effort, absent xattrs are fine).
    _ = try? run("/usr/bin/xattr", ["-dr", "com.apple.quarantine", prefix])
    guard fm.fileExists(atPath: prefix + "/cabinet/scripts/hatch.sh") else {
        throw ShellError(description: "extracted payload is missing cabinet/scripts/hatch.sh")
    }
}

func writeRequest(_ request: String, prefix: String) throws {
    guard allowedRequests.contains(request) else {
        throw ShellError(description: "internal: request not in allowlist")
    }
    try (request + "\n").write(toFile: prefix + "/.hatch-run-args",
                               atomically: true, encoding: .utf8)
}

func openTerminal(onRunnerIn prefix: String) throws {
    let runner = prefix + "/hatch-run.command"
    guard try run("/usr/bin/open", ["-a", "Terminal", runner]) == 0 else {
        throw ShellError(description: "could not open Terminal on \(runner)")
    }
}

// ---- headless smoke (CI): no dialogs, no Terminal -------------------------------

func smokeMain(prefix: String) -> Int32 {
    do {
        if case .populated = prefixState(prefix) {
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

func dialogMain(prefix: String) -> Int32 {
    let app = NSApplication.shared
    app.setActivationPolicy(.regular)
    app.activate(ignoringOtherApps: true)
    do {
        if case .populated = prefixState(prefix) {
            // Re-launch face: doctor or quit. No re-unpack, no overwrite.
            // Honest wording: ANY non-empty prefix lands here — a real
            // install, or a partial tree left by an interrupted unpack.
            let choice = ask(
                "Your Cabinet is already here",
                "There is already something in\n\(prefix)\n\n"
                + "That is either a Cabinet you set up before, or a setup that was "
                + "interrupted partway. This app never writes over it.\n\n"
                + "\u{201C}Check it over\u{201D} opens a Terminal window and looks at how it is "
                + "doing. It only reads — it changes nothing.",
                buttons: ["Check it over", "Quit"])
            guard choice == 0 else { return 0 }
            guard FileManager.default.isExecutableFile(atPath: prefix + "/hatch-run.command") else {
                _ = ask("Something is missing",
                        "The file that runs setup was not found in\n\(prefix)\n\n"
                        + "If that folder is a setup that was interrupted partway, move it "
                        + "to the Trash and open this app again.\n\n"
                        + "Otherwise you can run the check yourself in Terminal:\n"
                        + "  bash \(prefix)/cabinet/scripts/cabinet-doctor.sh",
                        buttons: ["Quit"])
                return 1
            }
            try writeRequest("doctor", prefix: prefix)
            try openTerminal(onRunnerIn: prefix)
            return 0
        }

        // First launch: hatch / hatch + move-in (second confirm) / cancel.
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
        try writeRequest(request!, prefix: prefix)
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
exit(env["HATCH_APP_SMOKE"] == "1" ? smokeMain(prefix: prefix) : dialogMain(prefix: prefix))
