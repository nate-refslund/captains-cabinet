// cabinet-companion — the Captain's menu-bar hand for the Cabinet.
// Wave D / D1, spec: DESIGN-companion-2026-07-10.md (v0.6).
//
// Compiled on-target by cabinet/scripts/build-companion.sh into
// "bin/Cabinet Companion.app" (LSUIElement accessory — menu bar only, no Dock
// icon), ad-hoc signed, calread-style, together with its ONE sibling source
// pet.swift (the desk pet's BODY — this file stays the brain). argv dispatch:
//
//   (no args)   GUI: NSStatusItem tray icon + menu
//   --smoke     headless one-shot poll: prints "STATE=<S> reason=<r>", exit 0
//               (any HONEST state passes — the acceptance gate works on
//               un-hatched Macs too; nonzero only on internal failure)
//   --version   print version, exit 0
//   --pet       GUI + the floating desk pet beside the Dock (pet.swift).
//               Optional: --pet-officer <slug>, --pet-scale <n>.
//   --pet-demo <STATE>   GUI + pet rendering a SYNTHETIC state, live poll
//               SUPPRESSED and the menu labelled DEMO. Exists so each of the
//               five states can be photographed on the real desktop; it is
//               the same synthetic input the test gate asserts on.
//   --pet-selftest       headless: the pure state→look mapping, one line each
//   --pet-render <STATE> <out.png>   headless: the composed canvas at source
//               resolution, so a test can assert on the PIXELS
//
// DOCTRINE MAP (spec §10):
//  1. Orchestrate-never-reimplement: every actuation shells an existing repo
//     script; the app itself only READS Redis (PING/GET — never SET/DEL;
//     grep-pinned by cabinet/scripts/tests/test_build_companion.py).
//  2. No new runtime deps: AppKit + Foundation + redis-cli (the fleet's
//     canonical Redis access) + /bin/bash. Nothing fetched, nothing bundled.
//  3. Kill-switch safety (§7): explicit verbs, fresh pre-read (refuse on
//     unknown), typed confirm (STOP / RESUME), post-verify by GET — the
//     locked script has no errexit and reports success even when its write
//     failed, so its stdout is NEVER trusted.
//  4. Loopback-only: every URL and the Redis host are 127.0.0.1. The
//     companion reads NO dashboard bind variable — it is bind-agnostic by
//     construction and probes loopback, which is served under either bind.
//  5. Honesty: boots AMBER "no data yet" (never green-by-default); every
//     non-GREEN header carries a machine-built reason; Terminal-opening
//     items are labeled "(opens Terminal)"; stale data renders AMBER.
//
// Child processes: fixed argv arrays (no shell strings, no user input),
// cwd = <root>, sanitized env (GUI apps do NOT inherit brew PATH), and an
// app-enforced kill-timeout on every spawn (redis-cli 2s).

import AppKit
import Darwin
import Foundation
import ServiceManagement
import UserNotifications

// MARK: - Constants

let companionVersion = "0.7.0"
let companionBundleID = "com.cabinet.companion"

enum Const {
    static let redisHost = "127.0.0.1"
    static let redisPort = "6379"
    /// GUI apps do not inherit the brew PATH; redis-cli lives in /opt/homebrew/bin (spec §4).
    static let sanitizedPath = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    static let defaultRoot = NSHomeDirectory() + "/captains-cabinet"
    static let defaultDashboardPort = 3100
    static let redisTimeout: TimeInterval = 2
    static let probeTimeout: TimeInterval = 1
    static let doctorTimeout: TimeInterval = 180
    static let killSwitchTimeout: TimeInterval = 10
    static let pollInterval: TimeInterval = 15
    static let offBackoffInterval: TimeInterval = 60
    static let staleAfter: TimeInterval = 120        // displayed data older than this renders AMBER (§5)
    static let presenceSkewAfter: TimeInterval = 300 // presence ts older than this = clock skew (§5)
    static let doctorSilenceFloor: TimeInterval = 26 * 3600 // mirrors the services.yml watchdog floor (§5)
}

// MARK: - Status model (§5)

enum CabinetState: String {
    case GREEN, AMBER, RED, PAUSED, OFF
}

struct OfficerRow {
    let slug: String
    let present: Bool
    let verb: String
    let ttlSeconds: Int
    let since: String
}

struct Snapshot {
    let state: CabinetState
    let reason: String
    let officers: [OfficerRow]
    let rootValid: Bool
    let redisUp: Bool
    let killswitchActive: Bool? // nil = unknown / unreadable
    let doctorLine: String
    let takenAt: Date

    /// Boot state — honest AMBER, never green-by-default (doctrine 5).
    static func booting(rootValid: Bool) -> Snapshot {
        Snapshot(state: .AMBER, reason: "no data yet", officers: [], rootValid: rootValid,
                 redisUp: false, killswitchActive: nil, doctorLine: "Doctor: no data yet",
                 takenAt: Date())
    }

    /// The 120s staleness rule (§5/§6): if the last successful poll is old
    /// (App Nap despite the activity token, wedged queue, …) the DISPLAYED
    /// state degrades to AMBER instead of showing a stale verdict.
    func stalenessAdjusted(now: Date) -> Snapshot {
        let age = now.timeIntervalSince(takenAt)
        guard age > Const.staleAfter else { return self }
        return Snapshot(state: .AMBER,
                        reason: "status stale — last successful poll \(CompanionCore.agoString(age)) ago",
                        officers: officers, rootValid: rootValid, redisUp: redisUp,
                        killswitchActive: killswitchActive, doctorLine: doctorLine, takenAt: takenAt)
    }
}

// MARK: - Process runner (fixed argv, sanitized env, kill-timeout)

struct ProcResult {
    let exitCode: Int32
    let stdout: String
    let stderr: String
    let timedOut: Bool
}

// MARK: - Log

final class CompanionLog {
    static let shared = CompanionLog()
    static let path = NSHomeDirectory() + "/Library/Logs/cabinet-companion.log"
    private let q = DispatchQueue(label: companionBundleID + ".log")
    private let stamp: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()

    func ensureExists() {
        q.sync {
            if !FileManager.default.fileExists(atPath: Self.path) {
                FileManager.default.createFile(atPath: Self.path, contents: Data())
            }
        }
    }

    func line(_ s: String) { write(stamp.string(from: Date()) + " " + s + "\n") }

    func block(_ s: String) { write(s.hasSuffix("\n") ? s : s + "\n") }

    private func write(_ s: String) {
        q.async {
            let fm = FileManager.default
            if !fm.fileExists(atPath: Self.path) {
                fm.createFile(atPath: Self.path, contents: Data())
            }
            guard let h = FileHandle(forWritingAtPath: Self.path) else { return }
            defer { try? h.close() }
            h.seekToEndOfFile()
            h.write(Data(s.utf8))
        }
    }
}

// MARK: - Core (shared by GUI and --smoke; no AppKit state in here)

enum CompanionCore {

    // ---- root discovery (§8) ----

    /// self-locate (bundle at <root>/bin/Cabinet Companion.app ⇒ root = two
    /// dirs up) → CABINET_ROOT env override → fixed fallback; each candidate
    /// validated by cabinet/scripts/cabinet-doctor.sh existing.
    static func resolveRoot() -> (path: String, valid: Bool) {
        var candidates: [String] = []
        let bundlePath = Bundle.main.bundlePath
        if bundlePath.hasSuffix(".app") {
            let binDir = (bundlePath as NSString).deletingLastPathComponent
            candidates.append((binDir as NSString).deletingLastPathComponent)
        }
        if let env = ProcessInfo.processInfo.environment["CABINET_ROOT"], !env.isEmpty {
            candidates.append(env)
        }
        candidates.append(Const.defaultRoot)
        for c in candidates where isValidRoot(c) { return (c, true) }
        return (candidates[0], false)
    }

    static func isValidRoot(_ p: String) -> Bool {
        FileManager.default.isReadableFile(atPath: p + "/cabinet/scripts/cabinet-doctor.sh")
    }

    // ---- env / tool discovery ----

    static func sanitizedEnv(root: String) -> [String: String] {
        ["PATH": Const.sanitizedPath, "HOME": NSHomeDirectory(), "CABINET_ROOT": root]
    }

    static func redisCliPath() -> String? {
        for dir in Const.sanitizedPath.split(separator: ":") {
            let p = String(dir) + "/redis-cli"
            if FileManager.default.isExecutableFile(atPath: p) { return p }
        }
        return nil
    }

    // ---- subprocess (fixed argv; app-enforced kill-timeout) ----

    static func run(argv: [String], cwd: String?, env: [String: String],
                    timeout: TimeInterval) -> ProcResult {
        precondition(!argv.isEmpty)
        let p = Process()
        p.executableURL = URL(fileURLWithPath: argv[0])
        p.arguments = Array(argv.dropFirst())
        if let cwd, FileManager.default.fileExists(atPath: cwd) {
            p.currentDirectoryURL = URL(fileURLWithPath: cwd)
        }
        p.environment = env
        p.standardInput = FileHandle.nullDevice
        let outPipe = Pipe()
        let errPipe = Pipe()
        p.standardOutput = outPipe
        p.standardError = errPipe
        let done = DispatchSemaphore(value: 0)
        p.terminationHandler = { _ in done.signal() }
        do {
            try p.run()
        } catch {
            return ProcResult(exitCode: -1, stdout: "", stderr: "spawn failed: \(error.localizedDescription)", timedOut: false)
        }
        // Drain both pipes off-thread so a full pipe can never wedge the child.
        // Buffers are lock-guarded: if the readers.wait grace below times out
        // (SIGKILL'd child, slow drain) a reader thread may still be writing
        // while the return path reads — same-lock access keeps that a
        // stale-but-safe empty read instead of a data race.
        let bufLock = NSLock()
        var outData = Data()
        var errData = Data()
        let readers = DispatchGroup()
        readers.enter()
        DispatchQueue.global(qos: .utility).async {
            let d = outPipe.fileHandleForReading.readDataToEndOfFile()
            bufLock.lock(); outData = d; bufLock.unlock()
            readers.leave()
        }
        readers.enter()
        DispatchQueue.global(qos: .utility).async {
            let d = errPipe.fileHandleForReading.readDataToEndOfFile()
            bufLock.lock(); errData = d; bufLock.unlock()
            readers.leave()
        }
        var timedOut = false
        if done.wait(timeout: .now() + timeout) == .timedOut {
            timedOut = true
            p.terminate()
            if done.wait(timeout: .now() + 0.5) == .timedOut {
                kill(p.processIdentifier, SIGKILL)
                _ = done.wait(timeout: .now() + 0.5)
            }
        }
        _ = readers.wait(timeout: .now() + 1)
        let code: Int32 = p.isRunning ? -1 : p.terminationStatus
        bufLock.lock()
        let outSnapshot = outData
        let errSnapshot = errData
        bufLock.unlock()
        return ProcResult(exitCode: code,
                          stdout: String(data: outSnapshot, encoding: .utf8) ?? "",
                          stderr: String(data: errSnapshot, encoding: .utf8) ?? "",
                          timedOut: timedOut)
    }

    // ---- redis reads (READ-ONLY: PING / GET only — doctrine 1) ----

    static func redisArgv(_ cli: String, _ tail: [String]) -> [String] {
        [cli, "-h", Const.redisHost, "-p", Const.redisPort] + tail
    }

    /// nil = CANNOT TELL; true = stop armed; false = PROVEN clear.
    ///
    /// 2026-07-25 ADVERSARIAL AUDIT: this used to run its own `GET` and return
    /// `stdout == "active"`, so every reply that was not that literal string
    /// became a confident `false` — "the kill switch is off". redis-cli prints
    /// error replies ON STDOUT WITH EXIT 0, so NOAUTH (requirepass), NOPERM
    /// (`ACL SETUSER default -get`), WRONGTYPE (`LPUSH cabinet:killswitch x`)
    /// and LOADING each made the Captain's phone report the stop as OFF while
    /// the fleet kept working. The read now goes through the ONE shared reader,
    /// cabinet/scripts/hooks/killswitch-read.sh, which reports CLEAR only on a
    /// definitive AUTHENTICATED clear read and also consults the second
    /// (filesystem marker) stop channel. Anything else is nil — and nil is
    /// rendered as PAUSED/"cannot verify", never as "off" (§5 ladder).
    static func killswitchRead(root: String) -> Bool? {
        let helper = root + "/cabinet/scripts/hooks/killswitch-read.sh"
        guard FileManager.default.isReadableFile(atPath: helper) else { return nil }
        let res = run(argv: ["/bin/bash", helper], cwd: root,
                      env: sanitizedEnv(root: root), timeout: Const.redisTimeout)
        guard !res.timedOut else { return nil }
        let verdict = res.stdout
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .split(separator: "\t", maxSplits: 1)
            .first.map(String.init) ?? ""
        switch verdict {
        case "ACTIVE": return true
        case "CLEAR":  return false
        default:       return nil
        }
    }

    // ---- parsing ----

    enum PresenceParse {
        case absent
        case unparseable
        case badSchema(Int)
        /// killswitch is Optional ON PURPOSE: nil = the v==1 blob is missing
        /// the field (or it is non-bool) — an upstream contract violation that
        /// must route to the fallback GET + AMBER, never default to false
        /// (green-by-default on the safety-critical field, doctrine 5).
        case ok(killswitch: Bool?, ts: Date?, officers: [OfficerRow])
    }

    static func parsePresence(_ raw: String) -> PresenceParse {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return .absent }
        guard let data = trimmed.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data),
              let dict = obj as? [String: Any] else { return .unparseable }
        guard let v = dict["v"] as? Int else { return .unparseable }
        guard v == 1 else { return .badSchema(v) } // unknown schema → AMBER (§4)
        var rows: [OfficerRow] = []
        if let offs = dict["officers"] as? [String: Any] {
            for (slug, any) in offs.sorted(by: { $0.key < $1.key }) {
                guard let o = any as? [String: Any] else { continue }
                rows.append(OfficerRow(slug: slug,
                                       present: o["present"] as? Bool ?? false,
                                       verb: o["verb"] as? String ?? "?",
                                       ttlSeconds: o["hb_ttl_s"] as? Int ?? -1,
                                       since: o["since"] as? String ?? ""))
            }
        }
        return .ok(killswitch: dict["killswitch"] as? Bool, // no default — nil flows to the fallback GET
                   ts: (dict["ts"] as? String).flatMap(parseISO),
                   officers: rows)
    }

    enum DoctorVerdict {
        case green
        case dead(Int)
    }

    enum HeartbeatParse {
        case absent
        case unparseable
        case ok(ts: Date, verdict: DoctorVerdict)
    }

    /// Contract (doctor header, re-verified): "<iso8601> GREEN" or "<iso8601> DEAD:<n>".
    static func parseHeartbeat(_ raw: String) -> HeartbeatParse {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return .absent }
        let parts = trimmed.split(separator: " ").map(String.init)
        guard parts.count == 2, let ts = parseISO(parts[0]) else { return .unparseable }
        if parts[1] == "GREEN" { return .ok(ts: ts, verdict: .green) }
        if parts[1].hasPrefix("DEAD:"), let n = Int(parts[1].dropFirst("DEAD:".count)) {
            return .ok(ts: ts, verdict: .dead(n))
        }
        return .unparseable
    }

    static let isoPlain: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()

    static let isoFractional: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    static func parseISO(_ s: String) -> Date? {
        isoPlain.date(from: s) ?? isoFractional.date(from: s)
    }

    static func iso(_ d: Date) -> String { isoPlain.string(from: d) }

    static func agoString(_ seconds: TimeInterval) -> String {
        let s = max(0, Int(seconds))
        if s < 60 { return "\(s)s" }
        if s < 3600 { return "\(s / 60)m" }
        if s < 86400 { return "\(s / 3600)h" }
        return "\(s / 86400)d"
    }

    // ---- dashboard port discovery (§8) ----

    /// Line-scan cabinet/.env for the anchored assignment
    /// CABINET_DASHBOARD_PORT=<digits>. The file is NEVER sourced or executed
    /// and no other line is read into state (it is the secrets file). On
    /// (pathological) duplicate assignments the LAST valid one wins — the same
    /// value bash `set -a` sourcing (start-dashboard.sh) would take.
    static func dashboardPort(root: String) -> Int {
        let prefix = "CABINET_DASHBOARD_PORT="
        guard let raw = try? String(contentsOfFile: root + "/cabinet/.env", encoding: .utf8) else {
            return Const.defaultDashboardPort
        }
        var found: Int?
        for sub in raw.split(separator: "\n", omittingEmptySubsequences: true) {
            let line = String(sub)
            guard line.hasPrefix(prefix) else { continue }
            let value = String(line.dropFirst(prefix.count))
            if !value.isEmpty, value.allSatisfy({ $0.isNumber }),
               let n = Int(value), (1...65535).contains(n) {
                found = n // last assignment wins
            }
        }
        return found ?? Const.defaultDashboardPort
    }

    /// 1s HEAD probe of the loopback dashboard (§4/§6). ANY HTTP response —
    /// including auth redirects — means the server is up; connection failure
    /// means the open-items stay disabled ("dashboard not running").
    static func headProbe(port: Int) -> Bool {
        guard let url = URL(string: "http://127.0.0.1:\(port)/") else { return false }
        var req = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData,
                             timeoutInterval: Const.probeTimeout)
        req.httpMethod = "HEAD"
        let cfg = URLSessionConfiguration.ephemeral
        cfg.timeoutIntervalForRequest = Const.probeTimeout
        cfg.timeoutIntervalForResource = Const.probeTimeout
        let session = URLSession(configuration: cfg)
        let sem = DispatchSemaphore(value: 0)
        // Lock-guarded like run()'s pipe buffers: after a sem.wait timeout the
        // completion can still fire concurrently with the return-path read —
        // same-lock access keeps that a stale-but-safe read, never a data race.
        let upLock = NSLock()
        var up = false
        session.dataTask(with: req) { _, resp, _ in
            let ok = resp is HTTPURLResponse
            upLock.lock(); up = ok; upLock.unlock()
            sem.signal()
        }.resume()
        _ = sem.wait(timeout: .now() + Const.probeTimeout + 0.2)
        session.invalidateAndCancel()
        upLock.lock(); let result = up; upLock.unlock()
        return result
    }

    // ---- the poll (§5 precedence, §6 budget: ≤3 spawns + 1 conditional) ----

    static func poll(rootInfo: (path: String, valid: Bool)) -> Snapshot {
        let now = Date()
        guard rootInfo.valid else {
            return Snapshot(state: .OFF, reason: "cabinet repo not found at \(rootInfo.path)",
                            officers: [], rootValid: false, redisUp: false, killswitchActive: nil,
                            doctorLine: "Doctor: unavailable (no cabinet root)", takenAt: now)
        }
        let root = rootInfo.path
        guard let cli = redisCliPath() else {
            return Snapshot(state: .OFF, reason: "redis-cli not found on sanitized PATH",
                            officers: [], rootValid: true, redisUp: false, killswitchActive: nil,
                            doctorLine: "Doctor: state unknown (no redis-cli)", takenAt: now)
        }
        let env = sanitizedEnv(root: root)
        let ping = run(argv: redisArgv(cli, ["PING"]), cwd: root, env: env, timeout: Const.redisTimeout)
        guard ping.exitCode == 0,
              ping.stdout.trimmingCharacters(in: .whitespacesAndNewlines) == "PONG" else {
            return Snapshot(state: .OFF,
                            reason: "Redis unreachable at \(Const.redisHost):\(Const.redisPort) — cabinet not running",
                            officers: [], rootValid: true, redisUp: false, killswitchActive: nil,
                            doctorLine: "Doctor: state unknown (Redis down)", takenAt: now)
        }
        let presenceRes = run(argv: redisArgv(cli, ["GET", "cabinet:world:presence"]),
                              cwd: root, env: env, timeout: Const.redisTimeout)
        let hbRes = run(argv: redisArgv(cli, ["GET", "cabinet:doctor:heartbeat"]),
                        cwd: root, env: env, timeout: Const.redisTimeout)
        let presence = parsePresence(presenceRes.timedOut ? "" : presenceRes.stdout)
        let doctor = parseHeartbeat(hbRes.timedOut ? "" : hbRes.stdout)

        var killswitch: Bool?
        var officers: [OfficerRow] = []
        var amberReasons: [String] = []
        var presenceAbsent = false

        switch presence {
        case .ok(let ks, let ts, let rows):
            killswitch = ks // Bool? — nil = field missing/non-bool in a v==1 blob
            officers = rows
            if ks == nil {
                // Mirrors the nil-ts handling below: GREEN claims "killswitch
                // off", so it must stay unreachable when the presence field is
                // unreadable — even if the fallback GET below also fails. The
                // fallback still runs so a genuinely ACTIVE switch renders
                // PAUSED (which outranks AMBER in the §5 ladder).
                amberReasons.append("presence killswitch unreadable")
            }
            if let ts {
                let age = now.timeIntervalSince(ts)
                if age > Const.presenceSkewAfter {
                    amberReasons.append("presence clock skew — presence ts \(agoString(age)) old")
                }
            } else {
                amberReasons.append("presence ts unreadable")
            }
        case .absent:
            presenceAbsent = true
        case .unparseable:
            amberReasons.append("presence unparseable")
        case .badSchema(let v):
            amberReasons.append("presence schema v\(v) unknown")
        }
        if killswitch == nil {
            // presence unusable — the ONE conditional fallback read (§5 sources)
            killswitch = killswitchRead(root: root)
        }

        var doctorLine: String
        var doctorAbsent = false
        switch doctor {
        case .ok(let ts, .green):
            let age = now.timeIntervalSince(ts)
            doctorLine = "Doctor: GREEN (\(agoString(age)) ago)"
            if age > Const.doctorSilenceFloor {
                amberReasons.append("doctor silent >26h — last GREEN \(iso(ts))")
            }
        case .ok(let ts, .dead(let n)):
            doctorLine = "Doctor: DEAD:\(n) (stamped \(iso(ts)))"
        case .absent:
            doctorAbsent = true
            doctorLine = "Doctor: has never run"
        case .unparseable:
            doctorLine = "Doctor: heartbeat unparseable"
        }

        // ---- precedence ladder, first match wins (§5) ----
        if killswitch == true {
            return Snapshot(state: .PAUSED,
                            reason: "kill switch active — every officer halts on its next tool call",
                            officers: officers, rootValid: true, redisUp: true,
                            killswitchActive: true, doctorLine: doctorLine, takenAt: now)
        }
        if killswitch == nil {
            // CANNOT VERIFY outranks everything below it, and renders as
            // STOPPED — never as "off", never as a benign AMBER note. The
            // Captain has to be able to tell "stopped" from "I cannot tell",
            // and both mean nothing is permitted to act (2026-07-25 audit).
            return Snapshot(state: .PAUSED,
                            reason: "emergency stop UNVERIFIABLE — treating as STOPPED; the switch could not be read",
                            officers: officers, rootValid: true, redisUp: true,
                            killswitchActive: nil, doctorLine: doctorLine, takenAt: now)
        }
        if case .ok(let ts, .dead(let n)) = doctor {
            var reason = "doctor RED: \(n) dead check(s) (stamped \(iso(ts)))"
            if now.timeIntervalSince(ts) > Const.doctorSilenceFloor {
                reason += " — doctor silent since \(iso(ts))"
            }
            return Snapshot(state: .RED, reason: reason, officers: officers, rootValid: true,
                            redisUp: true, killswitchActive: killswitch, doctorLine: doctorLine,
                            takenAt: now)
        }
        if presenceAbsent && doctorAbsent {
            amberReasons = ["hatched but quiet — no presence/doctor data"] // §8 wording
        } else {
            if presenceAbsent { amberReasons.append("world-chronicle silent — officer presence unknown") }
            if doctorAbsent { amberReasons.append("doctor has never run") }
            if case .unparseable = doctor { amberReasons.append("doctor heartbeat unparseable") }
        }
        if !amberReasons.isEmpty {
            return Snapshot(state: .AMBER, reason: amberReasons.joined(separator: "; "),
                            officers: officers, rootValid: true, redisUp: true,
                            killswitchActive: killswitch, doctorLine: doctorLine, takenAt: now)
        }
        var greenAge = ""
        if case .ok(let ts, .green) = doctor { greenAge = agoString(now.timeIntervalSince(ts)) }
        return Snapshot(state: .GREEN,
                        reason: "presence v1 fresh · killswitch off · doctor GREEN \(greenAge) ago",
                        officers: officers, rootValid: true, redisUp: true,
                        killswitchActive: false, doctorLine: doctorLine, takenAt: now)
    }

    // ---- --smoke (§11): headless one-shot; ANY honest state passes ----

    static func runSmoke() -> Int32 {
        let snap = poll(rootInfo: resolveRoot())
        // single-line contract: ^STATE=(GREEN|AMBER|RED|PAUSED|OFF) reason=
        let reason = snap.reason.replacingOccurrences(of: "\n", with: " ")
        print("STATE=\(snap.state.rawValue) reason=\(reason)")
        return 0
    }
}

// MARK: - Tray icon (programmatic, template, shape-encoded — never color-only)

enum StatusIcon {
    static func image(for state: CabinetState) -> NSImage {
        let size = NSSize(width: 18, height: 18)
        let img = NSImage(size: size, flipped: false) { _ in
            let path: NSBezierPath
            var alpha: CGFloat = 1.0
            var fill = true
            switch state {
            case .GREEN: // filled circle
                path = NSBezierPath(ovalIn: NSRect(x: 4, y: 4, width: 10, height: 10))
            case .AMBER: // filled triangle
                path = NSBezierPath()
                path.move(to: NSPoint(x: 9, y: 14.5))
                path.line(to: NSPoint(x: 15, y: 3.5))
                path.line(to: NSPoint(x: 3, y: 3.5))
                path.close()
            case .RED: // filled octagon
                path = NSBezierPath()
                let c = NSPoint(x: 9, y: 9)
                let r: CGFloat = 6.0
                for i in 0..<8 {
                    let angle = (CGFloat(i) + 0.5) * (.pi / 4)
                    let pt = NSPoint(x: c.x + r * cos(angle), y: c.y + r * sin(angle))
                    if i == 0 { path.move(to: pt) } else { path.line(to: pt) }
                }
                path.close()
            case .PAUSED: // pause bars
                path = NSBezierPath()
                path.appendRoundedRect(NSRect(x: 5, y: 4, width: 3, height: 10), xRadius: 1, yRadius: 1)
                path.appendRoundedRect(NSRect(x: 10, y: 4, width: 3, height: 10), xRadius: 1, yRadius: 1)
            case .OFF: // hollow circle, dimmed
                path = NSBezierPath(ovalIn: NSRect(x: 4.75, y: 4.75, width: 8.5, height: 8.5))
                path.lineWidth = 1.5
                alpha = 0.55
                fill = false
            }
            NSColor.black.withAlphaComponent(alpha).set()
            if fill { path.fill() } else { path.stroke() }
            return true
        }
        // Template rendering adapts to menu-bar appearance; the STATE signal is
        // carried by SHAPE (+ tooltip + accessibility), never by color alone.
        img.isTemplate = true
        img.accessibilityDescription = "Cabinet status: \(state.rawValue)"
        return img
    }
}

// MARK: - Typed-confirm helper (§7)

final class TypedConfirmDelegate: NSObject, NSTextFieldDelegate {
    let requiredWord: String
    weak var confirmButton: NSButton?

    init(requiredWord: String) {
        self.requiredWord = requiredWord
    }

    func controlTextDidChange(_ obj: Notification) {
        guard let field = obj.object as? NSTextField else { return }
        // confirm stays disabled until the field EXACTLY equals the verb word
        confirmButton?.isEnabled = (field.stringValue == requiredWord)
    }
}

// MARK: - App delegate (GUI)

final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    private let statusBar = NSStatusBar.system // strong refs held (§6)
    private var statusItem: NSStatusItem?
    private let menu = NSMenu()
    private var activityToken: NSObjectProtocol? // App Nap suppression — held for app lifetime (§6)
    private var wakeObserver: NSObjectProtocol?
    private var pollTimer: Timer?
    private var staleSentinel: Timer?
    private var currentInterval: TimeInterval = 0
    private let pollQueue = DispatchQueue(label: companionBundleID + ".poll")
    private let workQueue = DispatchQueue(label: companionBundleID + ".work")
    private let rootInfo = CompanionCore.resolveRoot()
    private var lastSnapshot: Snapshot?
    private var pollInFlight = false
    private var doctorInFlight = false
    private var dashboardUp = false
    private var loginItemOn = false
    private var notificationsWorking: Bool?
    private var lastEventLine: String?
    private var wrappersDir = ""
    private var pet: PetController? // the floating desk pet (pet.swift), only with --pet

    func applicationDidFinishLaunching(_ notification: Notification) {
        // ONE background-activity token, strong, for the whole app lifetime —
        // releasing it re-enables App Nap throttling (§6).
        activityToken = ProcessInfo.processInfo.beginActivity(
            options: .background, reason: "cabinet-companion status polling")
        CompanionLog.shared.line("companion v\(companionVersion) launched (root=\(rootInfo.path) valid=\(rootInfo.valid))")
        verifyNotificationPathEarly()
        menu.autoenablesItems = false
        menu.delegate = self
        let item = statusBar.statusItem(withLength: NSStatusItem.squareLength)
        item.menu = menu
        statusItem = item
        if rootInfo.valid { regenerateWrappers(root: rootInfo.path) }
        render() // boots AMBER "no data yet" — never green-by-default
        if PetOptions.enabled {
            if let demo = PetOptions.demoState {
                CompanionLog.shared.line("pet: DEMO MODE — rendering a SYNTHETIC \(demo.rawValue) snapshot; the live poll is suppressed and the menu says so. Nothing here is a reading of the cabinet.")
            }
            pet = PetController(root: rootInfo.path, slug: PetOptions.slug,
                                scale: PetOptions.scale, initial: displayedSnapshot())
        }
        pollNow()
        scheduleTimer(interval: Const.pollInterval)
        let sentinel = Timer(timeInterval: 30, repeats: true) { [weak self] _ in self?.render() }
        sentinel.tolerance = 10
        RunLoop.main.add(sentinel, forMode: .common)
        staleSentinel = sentinel
        wakeObserver = NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.didWakeNotification, object: nil, queue: .main
        ) { [weak self] _ in self?.pollNow() }
    }

    // ---- notification path (verify early; degrade honestly — §4) ----

    private func verifyNotificationPathEarly() {
        guard Bundle.main.bundleIdentifier == companionBundleID else {
            // Unbundled run (bare binary outside the .app): UNUserNotificationCenter
            // is unavailable — menu-line fallback carries events instead.
            notificationsWorking = false
            CompanionLog.shared.line("unbundled run — notifications unavailable, menu-line fallback active")
            return
        }
        UNUserNotificationCenter.current().getNotificationSettings { [weak self] settings in
            DispatchQueue.main.async {
                if settings.authorizationStatus == .denied { self?.notificationsWorking = false }
                CompanionLog.shared.line("notification authorization at launch: rawValue=\(settings.authorizationStatus.rawValue) (denied → menu-line fallback)")
            }
        }
    }

    private func notify(title: String, body: String) {
        lastEventLine = "\(Self.clock()) \(title)"
        CompanionLog.shared.line("event: \(title) — \(body)")
        guard Bundle.main.bundleIdentifier == companionBundleID else {
            notificationsWorking = false
            render()
            return
        }
        let center = UNUserNotificationCenter.current()
        let deliver: () -> Void = { [weak self] in
            let content = UNMutableNotificationContent()
            content.title = title
            content.body = body
            let req = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
            center.add(req) { err in
                DispatchQueue.main.async {
                    self?.notificationsWorking = (err == nil)
                    if let err {
                        CompanionLog.shared.line("notification delivery failed (\(err.localizedDescription)) — menu-line fallback active")
                    }
                    self?.render()
                }
            }
        }
        center.getNotificationSettings { [weak self] settings in
            switch settings.authorizationStatus {
            case .notDetermined:
                // request lazily on FIRST use (§4)
                center.requestAuthorization(options: [.alert]) { granted, _ in
                    DispatchQueue.main.async {
                        self?.notificationsWorking = granted
                        if !granted {
                            CompanionLog.shared.line("notifications denied at request — menu-line fallback active")
                        }
                        self?.render()
                    }
                    if granted { deliver() }
                }
            case .denied:
                DispatchQueue.main.async {
                    self?.notificationsWorking = false
                    self?.render() // menu-line-only, silently honest
                }
            default:
                deliver()
            }
        }
    }

    private static func clock() -> String {
        let f = DateFormatter()
        f.dateFormat = "HH:mm"
        return f.string(from: Date())
    }

    // ---- polling ----

    private func scheduleTimer(interval: TimeInterval) {
        guard interval != currentInterval else { return }
        pollTimer?.invalidate()
        let t = Timer(timeInterval: interval, repeats: true) { [weak self] _ in self?.pollNow() }
        t.tolerance = interval / 3 // 15s → 5s tolerance (§6)
        RunLoop.main.add(t, forMode: .common)
        pollTimer = t
        currentInterval = interval
    }

    private func pollNow() {
        // DEMO: one choke point. A synthetic state must never be mixed with a
        // real reading — so while --pet-demo is on, the cabinet is never read.
        guard PetOptions.demoState == nil else { return }
        guard !pollInFlight else { return }
        pollInFlight = true
        let info = rootInfo
        pollQueue.async { [weak self] in
            let snap = CompanionCore.poll(rootInfo: info)
            DispatchQueue.main.async {
                guard let self else { return }
                self.pollInFlight = false
                self.apply(snapshot: snap)
            }
        }
    }

    private func apply(snapshot: Snapshot) {
        if let prev = lastSnapshot {
            if prev.state != snapshot.state {
                CompanionLog.shared.line("state \(prev.state.rawValue) → \(snapshot.state.rawValue): \(snapshot.reason)")
            }
        } else {
            CompanionLog.shared.line("first poll: \(snapshot.state.rawValue): \(snapshot.reason)")
        }
        lastSnapshot = snapshot
        // backoff to 60s while OFF (§6)
        scheduleTimer(interval: snapshot.state == .OFF ? Const.offBackoffInterval : Const.pollInterval)
        render()
    }

    private func displayedSnapshot() -> Snapshot {
        // DEMO returns a freshly stamped synthetic snapshot, so the forced
        // state neither ages into "stale" nor leaks a real reading.
        if let demo = PetOptions.demoState {
            return PetCLI.demoSnapshot(demo, slug: PetOptions.slug)
        }
        return (lastSnapshot ?? Snapshot.booting(rootValid: rootInfo.valid)).stalenessAdjusted(now: Date())
    }

    private func render() {
        let snap = displayedSnapshot()
        statusItem?.button?.image = StatusIcon.image(for: snap.state)
        // The DEMO marker belongs on the TOOLTIP too, not only inside the open
        // menu: --pet-demo exists so states can be photographed on the real
        // desktop, and the menu bar is in those photographs (adversarial
        // review, 2026-07-30).
        let demoTag = PetOptions.demoState == nil ? "" : "DEMO (synthetic, not a reading) — "
        statusItem?.button?.toolTip = "\(demoTag)Cabinet: \(snap.state.rawValue) — \(snap.reason)"
        pet?.apply(snapshot: snap)
        rebuildMenu(snap: snap)
    }

    // ---- menu ----

    func menuNeedsUpdate(_ menu: NSMenu) {
        pollNow() // immediate poll on menu open (§6)
        if rootInfo.valid, PetOptions.demoState == nil {
            // menu-open budget: one bounded ~1s HEAD probe (§6) — run OFF the
            // main thread so opening the menu never stalls behind a down
            // dashboard. Last-known dashboardUp renders instantly; the
            // open-items correct themselves when the probe lands (main-queue
            // blocks run during menu tracking — the async poll's path already
            // relies on this). Global queue: workQueue may be busy with a
            // long doctor run.
            let root = rootInfo.path
            DispatchQueue.global(qos: .userInitiated).async { [weak self] in
                let up = CompanionCore.headProbe(port: CompanionCore.dashboardPort(root: root))
                DispatchQueue.main.async {
                    guard let self, self.dashboardUp != up else { return }
                    self.dashboardUp = up
                    self.render()
                }
            }
        }
        loginItemOn = Self.loginItemEnabled() // re-read on every menu open, never cached (§4)
        render()
    }

    private func rebuildMenu(snap: Snapshot) {
        menu.removeAllItems()
        // DEMO: the snapshot is synthetic, so every item whose LABEL or
        // ENABLEMENT would be derived from it is disabled. Actuation was
        // always safe (the kill-switch lever re-reads Redis before arming),
        // but the lever's verb is read off the state — and "▶ Resume
        // Officers…" computed from a made-up PAUSED is a lie in the one menu
        // that must never lie (adversarial review, 2026-07-30).
        let demo = PetOptions.demoState != nil
        let rootOK = rootInfo.valid && !demo

        if let demo = PetOptions.demoState {
            menu.addItem(infoItem("DEMO — synthetic \(demo.rawValue); the cabinet is NOT being read, and every action is disabled"))
            menu.addItem(.separator())
        }
        let header = infoItem("Cabinet: \(snap.state.rawValue)")
        menu.addItem(header)
        menu.addItem(smallInfoItem(snap.reason))
        menu.addItem(smallInfoItem(snap.doctorLine))
        menu.addItem(.separator())

        // officers submenu
        let officersItem = NSMenuItem(title: "Officers", action: nil, keyEquivalent: "")
        let sub = NSMenu()
        sub.autoenablesItems = false
        if snap.officers.isEmpty {
            sub.addItem(infoItem("no officers reported"))
        } else {
            for o in snap.officers {
                let mark = o.present ? "●" : "○"
                let detail = o.present ? "\(o.verb) (hb \(o.ttlSeconds)s)" : "absent"
                sub.addItem(infoItem("\(mark) \(o.slug) — \(detail)"))
            }
        }
        officersItem.submenu = sub
        officersItem.isEnabled = rootOK
        menu.addItem(officersItem)
        menu.addItem(.separator())

        let openDash = actionItem("Open Dashboard", #selector(openDashboard))
        openDash.isEnabled = rootOK && dashboardUp
        if !dashboardUp { openDash.toolTip = "dashboard not running (loopback probe failed)" }
        menu.addItem(openDash)
        let openOrientation = actionItem("Continue Orientation", #selector(openOrientationAction))
        openOrientation.isEnabled = rootOK && dashboardUp
        if !dashboardUp { openOrientation.toolTip = "dashboard not running (loopback probe failed)" }
        menu.addItem(openOrientation)
        let openWorld = actionItem("Open World", #selector(openWorldAction))
        openWorld.isEnabled = rootOK && dashboardUp
        if !dashboardUp { openWorld.toolTip = "dashboard not running (loopback probe failed)" }
        menu.addItem(openWorld)

        let doctorItem = actionItem(doctorInFlight ? "Doctor running…" : "Run Doctor (background)",
                                    #selector(runDoctorClicked))
        doctorItem.isEnabled = rootOK && !doctorInFlight
        doctorItem.toolTip = "runs cabinet-doctor.sh in the background; verdict lands as a notification + companion log (no Terminal window)"
        menu.addItem(doctorItem)

        // services submenu — every entry opens Terminal and says so
        let servicesItem = NSMenuItem(title: "Services", action: nil, keyEquivalent: "")
        let servicesSub = NSMenu()
        servicesSub.autoenablesItems = false
        servicesSub.addItem(wrapperItem("Start Fleet (opens Terminal)", wrapper: "start-fleet.command", enabled: rootOK))
        servicesSub.addItem(wrapperItem("Stop Fleet (opens Terminal)", wrapper: "stop-fleet.command", enabled: rootOK))
        let dryRunItem = wrapperItem("Deploy Dry-Run (opens Terminal)", wrapper: "deploy-dry-run.command", enabled: rootOK)
        dryRunItem.toolTip = "runs deploy-mac.sh --all --dry-run — prints the full-fleet plan, changes nothing"
        servicesSub.addItem(dryRunItem)
        servicesItem.submenu = servicesSub
        servicesItem.isEnabled = rootOK
        menu.addItem(servicesItem)

        // Hatch offer: only when Redis is down AND hatch.sh exists on disk (§8 feature-guard)
        if rootOK, !snap.redisUp, snap.state == .OFF,
           FileManager.default.isReadableFile(atPath: rootInfo.path + "/cabinet/scripts/hatch.sh") {
            menu.addItem(wrapperItem("Hatch in Terminal…", wrapper: "hatch.command", enabled: true))
        }
        menu.addItem(.separator())

        // kill-switch lever — explicit verb from CURRENT state, never a toggle (§7)
        let leverTitle: String
        switch snap.killswitchActive {
        case .some(true): leverTitle = "▶ Resume Officers…"
        case .some(false): leverTitle = "⏸ Stop All Officers…"
        case .none: leverTitle = "⏸ Stop All Officers…"
        }
        let lever = actionItem(leverTitle, #selector(killSwitchLever))
        lever.isEnabled = rootOK && snap.redisUp
        if snap.killswitchActive == nil {
            lever.toolTip = "kill-switch state unknown — the click re-verifies before arming"
        }
        menu.addItem(lever)

        let refresh = actionItem("Refresh Now", #selector(refreshNow))
        refresh.isEnabled = rootOK
        menu.addItem(refresh)

        if let pet {
            let toggle = actionItem(pet.isVisible ? "Hide Desk Pet" : "Show Desk Pet",
                                    #selector(toggleDeskPet))
            toggle.toolTip = "the floating officer beside the Dock; it cannot be clicked (per-pixel click-through is broken on this macOS — see pet.swift)"
            menu.addItem(toggle)
        }
        menu.addItem(.separator())

        let login = actionItem("Launch at Login", #selector(toggleLoginItem))
        login.state = loginItemOn ? .on : .off
        login.isEnabled = rootOK && Self.loginItemAPIAvailable()
        login.toolTip = "opt-in via SMAppService (default OFF); macOS shows a one-time “background items added” banner"
        menu.addItem(login)

        menu.addItem(actionItem("Open Companion Log", #selector(openLog))) // enabled even with invalid root (§8)

        if notificationsWorking == false, let last = lastEventLine {
            menu.addItem(smallInfoItem("Last event: \(last) (notifications unavailable)"))
        }
        menu.addItem(.separator())
        let quit = NSMenuItem(title: "Quit Cabinet Companion",
                              action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        quit.target = NSApp
        quit.isEnabled = true
        menu.addItem(quit)
    }

    private func infoItem(_ title: String) -> NSMenuItem {
        let i = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        i.isEnabled = false
        return i
    }

    private func smallInfoItem(_ title: String) -> NSMenuItem {
        let i = infoItem(title)
        i.attributedTitle = NSAttributedString(
            string: title, attributes: [.font: NSFont.menuFont(ofSize: 11)])
        return i
    }

    private func actionItem(_ title: String, _ sel: Selector) -> NSMenuItem {
        let i = NSMenuItem(title: title, action: sel, keyEquivalent: "")
        i.target = self
        i.isEnabled = true
        return i
    }

    private func wrapperItem(_ title: String, wrapper: String, enabled: Bool) -> NSMenuItem {
        let i = actionItem(title, #selector(openWrapper(_:)))
        i.representedObject = wrappersDir + "/" + wrapper
        i.isEnabled = enabled && !wrappersDir.isEmpty
        return i
    }

    // ---- actions ----

    @objc private func openDashboard() { openLoopback(path: "/") }

    /// Commercial app shell: route into the SAME Dashboard-owned journey.
    /// The companion stores no onboarding state and performs no onboarding act.
    @objc private func openOrientationAction() {
        let trace = "trace-companion-" + UUID().uuidString.lowercased()
        let correlation = "corr-companion-" + UUID().uuidString.lowercased()
        openLoopback(path: "/onboarding?from=companion&trace_id=\(trace)&correlation_id=\(correlation)")
    }

    /// /world is auth-gated — the first open bounces to /login; expected, documented.
    @objc private func openWorldAction() { openLoopback(path: "/world") }

    private func openLoopback(path: String) {
        let port = CompanionCore.dashboardPort(root: rootInfo.path)
        if let url = URL(string: "http://127.0.0.1:\(port)" + path) {
            NSWorkspace.shared.open(url)
        }
    }

    @objc private func refreshNow() { pollNow() }

    @objc private func toggleDeskPet() {
        guard let pet else { return }
        pet.setVisible(!pet.isVisible)
        render()
    }

    @objc private func openLog() {
        CompanionLog.shared.ensureExists()
        NSWorkspace.shared.open(URL(fileURLWithPath: CompanionLog.path))
    }

    @objc private func openWrapper(_ sender: NSMenuItem) {
        guard let path = sender.representedObject as? String,
              FileManager.default.fileExists(atPath: path) else { return }
        // Launch Services only — the .command file opens in Terminal; the menu
        // item title already says "(opens Terminal)". Never AppleEvents (§4).
        NSWorkspace.shared.open(URL(fileURLWithPath: path))
    }

    @objc private func runDoctorClicked() {
        guard rootInfo.valid, !doctorInFlight else { return }
        doctorInFlight = true
        render()
        let root = rootInfo.path
        CompanionLog.shared.line("doctor: background run started (output → companion log)")
        workQueue.async { [weak self] in
            guard let self else { return }
            let res = CompanionCore.run(
                argv: ["/bin/bash", root + "/cabinet/scripts/cabinet-doctor.sh"],
                cwd: root, env: CompanionCore.sanitizedEnv(root: root),
                timeout: Const.doctorTimeout)
            CompanionLog.shared.block(
                "---- cabinet-doctor run (exit \(res.exitCode)\(res.timedOut ? ", TIMED OUT" : "")) ----\n"
                + res.stdout + res.stderr
                + "---- end doctor run ----")
            let verdict = res.stdout.split(separator: "\n")
                .last(where: { $0.hasPrefix("CABINET_DOCTOR ") }).map(String.init)
            DispatchQueue.main.async {
                self.doctorInFlight = false
                if res.timedOut {
                    self.notify(title: "Doctor run timed out",
                                body: "No verdict after \(Int(Const.doctorTimeout))s — see companion log.")
                } else if res.exitCode == 0 {
                    self.notify(title: "Doctor: GREEN", body: verdict ?? "CABINET_DOCTOR GREEN")
                } else {
                    self.notify(title: "Doctor: DEAD",
                                body: (verdict ?? "nonzero exit \(res.exitCode)") + " — see companion log")
                }
                self.pollNow() // the doctor stamps its own heartbeat — the menu doctor line refreshes (§4)
            }
        }
    }

    // ---- kill-switch lever (§7) ----

    @objc private func killSwitchLever() {
        guard rootInfo.valid else { return }
        let root = rootInfo.path
        // 1. synchronous fresh read (2s) — never actuate on unknown state
        guard let active = CompanionCore.killswitchRead(root: root) else {
            let a = NSAlert()
            a.alertStyle = .warning
            a.messageText = "Cannot verify current kill-switch state — refusing to arm."
            a.informativeText = "The fresh Redis read failed or timed out. Nothing was actuated."
            a.addButton(withTitle: "OK")
            _ = a.runModal()
            return
        }
        let activating = !active
        let word = activating ? "STOP" : "RESUME"
        let alert = NSAlert()
        alert.alertStyle = .critical
        alert.messageText = activating ? "Stop ALL officers?" : "Resume officers?"
        alert.informativeText = activating
            ? "Activates the cabinet kill switch: every officer tool call halts on its next invocation (enforced by the pre-tool-use hook). Type \(word) in the field to enable the confirm button."
            : "Deactivates the cabinet kill switch: officers resume on their next tool call. Type \(word) in the field to enable the confirm button."
        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 240, height: 24))
        field.placeholderString = "type \(word) to confirm"
        let confirmDelegate = TypedConfirmDelegate(requiredWord: word)
        field.delegate = confirmDelegate
        alert.accessoryView = field
        // Cancel FIRST = default button (Return); Esc maps to "Cancel" automatically.
        _ = alert.addButton(withTitle: "Cancel")
        let confirm = alert.addButton(withTitle: activating ? "Stop All Officers" : "Resume Officers")
        confirm.isEnabled = false
        confirm.hasDestructiveAction = activating
        confirmDelegate.confirmButton = confirm
        alert.window.initialFirstResponder = field
        // ARC hazard under -O: the delegate's last strong use is above, and both
        // NSTextField.delegate and TypedConfirmDelegate.confirmButton are weak —
        // without an explicit lifetime pin the optimizer may release it before
        // the modal runs, the delegate zeroes, and the confirm button could
        // never enable (doctrine-3 lever dead from the tray).
        let response = withExtendedLifetime(confirmDelegate) { alert.runModal() }
        guard response == .alertSecondButtonReturn, field.stringValue == word else { return }
        actuate(activate: activating, root: root)
    }

    private func actuate(activate: Bool, root: String) {
        let verb = activate ? "activate" : "deactivate"
        CompanionLog.shared.line("kill-switch: \(verb) armed (typed confirm passed)")
        workQueue.async { [weak self] in
            guard let self else { return }
            var env = CompanionCore.sanitizedEnv(root: root)
            // kill-switch.sh call site: the locked script defaults to a docker-era
            // Redis hostname and calls bare redis-cli with no errexit — it prints
            // success even when its write failed. Pin loopback here and NEVER
            // trust its stdout; the GET post-verify below is mandatory (§4/§7).
            let redisURLExport = "REDIS_URL=redis://127.0.0.1:6379" // grep-pinned literal
            let kv = redisURLExport.split(separator: "=", maxSplits: 1).map(String.init)
            if kv.count == 2 { env[kv[0]] = kv[1] }
            let script = root + "/cabinet/scripts/kill-switch.sh"
            let res = CompanionCore.run(argv: ["/bin/bash", script, verb],
                                        cwd: root, env: env, timeout: Const.killSwitchTimeout)
            CompanionLog.shared.block(
                "---- kill-switch.sh \(verb) (exit \(res.exitCode)\(res.timedOut ? ", TIMED OUT" : "")) ----\n"
                + res.stdout + res.stderr
                + "(script stdout is never trusted — post-verifying via GET)\n")
            let after = CompanionCore.killswitchRead(root: root)
            DispatchQueue.main.async {
                switch (after, activate) {
                case (.some(true), true):
                    self.notify(title: "Kill switch ACTIVE",
                                body: "Officers halt on next tool call.")
                case (.some(false), false):
                    self.notify(title: "Kill switch deactivated",
                                body: "Officers resume on next tool call.")
                case (.some, _):
                    self.notify(title: "Actuation FAILED — state unchanged",
                                body: "Post-verify read contradicts the requested change — see companion log.")
                case (.none, _):
                    self.notify(title: "Actuation UNVERIFIED",
                                body: "Post-verify Redis read failed — kill-switch state unknown; see companion log.")
                }
                self.pollNow()
            }
        }
    }

    // ---- login item (opt-in, default OFF — §9) ----

    private static func loginItemAPIAvailable() -> Bool {
        if #available(macOS 13.0, *) { return true }
        return false
    }

    private static func loginItemEnabled() -> Bool {
        if #available(macOS 13.0, *) { return SMAppService.mainApp.status == .enabled }
        return false
    }

    @objc private func toggleLoginItem() {
        guard #available(macOS 13.0, *) else { return }
        let svc = SMAppService.mainApp
        do {
            if svc.status == .enabled {
                try svc.unregister()
                CompanionLog.shared.line("login item unregistered")
            } else {
                try svc.register()
                CompanionLog.shared.line("login item registered (one-time macOS 'background items added' banner expected)")
            }
        } catch {
            lastEventLine = "\(Self.clock()) login-item change failed"
            CompanionLog.shared.line("login-item change failed: \(error.localizedDescription)")
        }
        loginItemOn = Self.loginItemEnabled()
        render()
    }

    // ---- Terminal wrappers (§4): static .command files, Launch Services open ----

    private func regenerateWrappers(root: String) {
        let fm = FileManager.default
        let dir = NSHomeDirectory() + "/Library/Application Support/Cabinet Companion"
        do {
            try fm.createDirectory(atPath: dir, withIntermediateDirectories: true)
        } catch {
            CompanionLog.shared.line("wrapper dir create failed: \(error.localizedDescription)")
            return
        }
        // hatch.command is generated UNCONDITIONALLY: the runtime feature-guard
        // lives on the menu item (on-disk hatch.sh check at menu build), so if
        // hatch.sh appears after launch (e.g. a branch merge) the offer works
        // without an app restart. Running the wrapper without hatch.sh on disk
        // fails honestly in Terminal ("no such file").
        // deploy-dry-run pins --all --dry-run: a bare --dry-run carries no
        // selector, falls through deploy-mac.sh's else-branch and exits 64
        // with usage (runtime-verified 2026-07-10) — the spec §4 table said
        // plain --dry-run; correction recorded in the PC-D-COMPANION ledger
        // note. --all --dry-run prints the full-fleet plan (or the honest
        // roster-refusal on an unseeded box) and mutates nothing.
        let wrappers: [(file: String, script: String, args: [String], label: String)] = [
            ("start-fleet.command", "deploy-mac.sh", ["--all"], "start the full fleet"),
            ("stop-fleet.command", "deploy-mac.sh", ["--stop", "all"], "stop the full fleet"),
            ("deploy-dry-run.command", "deploy-mac.sh", ["--all", "--dry-run"], "show the full-fleet deploy plan (no changes)"),
            ("hatch.command", "hatch.sh", [], "hatch the cabinet"),
        ]
        for w in wrappers {
            let scriptPath = root + "/cabinet/scripts/" + w.script
            let argSuffix = w.args.map { " " + Self.bashQuoted($0) }.joined()
            let content = """
            #!/bin/bash
            # Generated by Cabinet Companion v\(companionVersion) — \(w.label).
            # Static wrapper: regenerated at every companion launch; fixed content,
            # absolute root-stamped paths (bash-quoted), zero user input
            # (DESIGN-companion §4).
            cd \(Self.bashQuoted(root)) || exit 1
            exec /bin/bash \(Self.bashQuoted(scriptPath))\(argSuffix)
            """
            let path = dir + "/" + w.file
            do {
                try content.write(toFile: path, atomically: true, encoding: .utf8)
                try fm.setAttributes([.posixPermissions: 0o755], ofItemAtPath: path)
            } catch {
                CompanionLog.shared.line("wrapper write failed (\(w.file)): \(error.localizedDescription)")
            }
        }
        wrappersDir = dir
        CompanionLog.shared.line("wrappers regenerated at \(dir) (root-stamped: \(root))")
    }

    /// Quote a string as ONE double-quoted bash word (escaping \ " $ `).
    /// Wrapper inputs are operator-controlled absolute paths plus fixed flag
    /// literals — this is belt-and-braces so an exotic root path (quotes,
    /// dollar signs) can never inject into the generated wrapper source.
    private static func bashQuoted(_ s: String) -> String {
        var escaped = ""
        for ch in s {
            if ch == "\\" || ch == "\"" || ch == "$" || ch == "`" { escaped.append("\\") }
            escaped.append(ch)
        }
        return "\"" + escaped + "\""
    }
}

// MARK: - Entry point (argv dispatch — calread-style consolidated binary)

let cliArgs = Array(CommandLine.arguments.dropFirst())
let usageLine = "usage: cabinet-companion [--smoke | --version | --pet [--pet-officer <slug>] [--pet-scale <n>] | --pet-demo <STATE> | --pet-selftest | --pet-render <STATE> <out.png> [--pet-tick <n>]]"

func petArgFail(_ msg: String) -> Never {
    FileHandle.standardError.write(Data("\(usageLine)\n\(msg)\n".utf8))
    exit(64)
}

if cliArgs.contains("--version") {
    print("cabinet-companion \(companionVersion)")
    exit(0)
}
if cliArgs.contains("--smoke") {
    exit(CompanionCore.runSmoke())
}

// ---- pet argv (pet.swift). Unknown flags still exit 64 — no silent accept.
var petRenderTarget: (state: CabinetState, path: String)?
var petSelftest = false
var argIndex = 0
while argIndex < cliArgs.count {
    let arg = cliArgs[argIndex]
    func value(_ name: String) -> String {
        guard argIndex + 1 < cliArgs.count else { petArgFail("\(name) needs a value") }
        argIndex += 1
        return cliArgs[argIndex]
    }
    switch arg {
    case "--pet":
        PetOptions.enabled = true
    case "--pet-officer":
        PetOptions.slug = value("--pet-officer")
    case "--pet-tick":
        guard let n = Int(value("--pet-tick")), n >= 0 else { petArgFail("--pet-tick must be a non-negative integer") }
        PetOptions.renderTick = n
    case "--pet-scale":
        guard let n = Int(value("--pet-scale")), (1...8).contains(n) else {
            petArgFail("--pet-scale must be an integer 1...8 (integer scales only — a resampled pet is a failed pet)")
        }
        PetOptions.scale = n
    case "--pet-demo":
        let raw = value("--pet-demo")
        guard let s = PetCLI.parseState(raw) else { petArgFail("--pet-demo: unknown state \(raw)") }
        PetOptions.enabled = true
        PetOptions.demoState = s
    case "--pet-selftest":
        petSelftest = true
    case "--pet-render":
        let raw = value("--pet-render")
        guard let s = PetCLI.parseState(raw) else { petArgFail("--pet-render: unknown state \(raw)") }
        petRenderTarget = (s, value("--pet-render <out.png>"))
    default:
        petArgFail("unknown argument: \(arg)")
    }
    argIndex += 1
}
if petSelftest { exit(PetCLI.selftest()) }
if let target = petRenderTarget { exit(PetCLI.render(state: target.state, to: target.path, tick: PetOptions.renderTick)) }

let app = NSApplication.shared
app.setActivationPolicy(.accessory) // LSUIElement twin: menu bar only, no Dock icon
let appDelegate = AppDelegate()
app.delegate = appDelegate
app.run()
