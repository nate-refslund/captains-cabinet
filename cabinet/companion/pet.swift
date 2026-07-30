// pet.swift — the desk pet: a floating always-on-top officer beside the Dock.
//
// Captain's ruling 2026-07-30 (designs/dock-pet-2026-07-30.md, meta): of
// dock-tile / floating-window / build-and-judge, he chose "Floating window
// beside the Dock" — the Shimeji model — knowing it is crisper (one resample),
// can roam, is not literally in the Dock, and carries a click-through risk.
//
// THIS IS A BODY, NOT A BRAIN. Every decision it renders comes from
// CompanionCore.poll() in main.swift, which already reads the cabinet
// read-only and runs the five-state precedence ladder. This file adds no
// Redis read, no new data source, no new permission and no new daemon — it
// turns a Snapshot into pixels.
//
// THE LAW THIS FILE EXISTS TO OBEY (world doctrine): absence must not look
// like calm. Every desk pet in the genre sleeps when idle, and sleeping reads
// as "all is well". The most common truth for this cabinet today is "I cannot
// see anything", so:
//
//   GREEN   walks, full colour             — the fleet is working
//   AMBER   stands, GREY, "?" chip         — it does not know
//   RED     stands, GREY, "!" chip         — it knows, and it is bad
//   PAUSED  frozen mid-stride, full colour — the world's own killswitch idiom
//   OFF     hollow shell, "?" chip         — nothing to observe; the pet is
//                                            still visibly alive, because a
//                                            pet that VANISHES is
//                                            indistinguishable from a pet
//                                            that was never launched
//
// The OFF row is the one deviation from the dock-tile plan in the design doc
// (which said "empty tile, plain app icon"). A dock tile still shows the app
// icon when the pet is empty, so the app's presence survives; a floating
// window that draws nothing is simply GONE, which re-creates exactly the
// confusion the doc forbids for the badge ("no badge" and "badge 0" must never
// be confusable). Hence: hollow, not absent.
//
// MEASURED ON THIS MAC (macOS 26.6, 2026-07-30), and both results are load
// bearing:
//
//  1. PER-PIXEL CLICK-THROUGH IS BROKEN. A borderless transparent window that
//     draws NOTHING AT ALL still takes the mouse-down across its whole frame
//     (NSWindow.windowNumber(at:belowWindowWithWindowNumber:) returns the
//     empty window's number; the same probe passes through with
//     ignoresMouseEvents = true, and an opaque control window is hit — so the
//     sensor is alive, not stuck). The design doc predicted this regression
//     window (broke in 26.3 RC, fixed in 26.3, regressed in 26.4 beta) and
//     could not state 26.6. Now it can: broken.
//     THE FALLBACK IS THE SHIPPED BEHAVIOUR: ignoresMouseEvents = true, always
//     (petWindowIgnoresMouse below). The pet cannot intercept a single click.
//     The cost is that v1 is not clickable — which the design already chose
//     ("the first version is deliberately not interactive"). Interaction stays
//     in the menu-bar item this app already owns. Do not flip that flag back
//     without re-running the probe.
//  2. THIS DISPLAY IS EXACT-2x (mode 1728x1117 points / 3456x2234 pixels,
//     ratio 2.0), so the "framebuffer trap" in the design doc — a scaled HiDPI
//     mode resampling the whole desktop under every app — does NOT bite here.
//     At an integer point scale the pet is pixel-exact end to end.
//
// PERMISSIONS: NONE. Not Accessibility, not Screen Recording. The Captain
// accepted an Accessibility cost when he chose this surface; it turned out not
// to be needed, because the Dock's geometry is derivable with zero permission
// from NSScreen.frame minus NSScreen.visibleFrame. Window-edge tracking (the
// pet walking along OTHER apps' windows) is the feature that would need it,
// and it is not in v1.
//
// ART: the owned org-original cast (licence "owned — org-original"), the same
// 20 sheets and the same officer→sheet hash the World uses, so the pet is the
// SAME BODY the Captain sees in the world. Geometry and hash below are
// deliberate mirrors of cabinet/dashboard/src/lib/world/{sprites,hash}.ts and
// are pinned against it by test_build_companion.py.
//
// The alpha-keyline idea (build the outline from the sprite's ALPHA so one
// recipe works for any art) is taken from hellogumbo/codex-dock-pet (MIT) —
// the idea, not the code: this implementation is a plain 8-neighbour dilate in
// our own pixel buffer, with no CoreImage and no dependency.

import AppKit
import QuartzCore

// MARK: - Options (argv, parsed in main.swift)

enum PetOptions {
    static var enabled = false
    /// Non-nil = DEMO: the pet renders a SYNTHETIC snapshot and the live poll
    /// is suppressed, so a forced state can never be mixed with a real one.
    /// Loudly logged and labelled in the menu (§ demoBanner).
    static var demoState: CabinetState?
    static var slug = "cos"
    static var scale = 3
    /// Which animation tick --pet-render composes. Exists so the pixel gate can
    /// sample more than one frame of the strip; the live pet ignores it.
    static var renderTick = 0
}

// MARK: - Deterministic hash (mirror: dashboard/src/lib/world/hash.ts)

enum PetHash {
    /// FNV-1a 32-bit over UTF-16 code units — byte-identical to the world's
    /// fnv1a(), so an officer gets the SAME sheet here and in the World.
    static func fnv1a(_ input: String) -> UInt32 {
        var h: UInt32 = 0x811c_9dc5
        for u in input.utf16 {
            h ^= UInt32(u)
            h = h &* 0x0100_0193
        }
        return h
    }

    /// mulberry32 — the world's PRNG. Seeded from the slug, so the roam is
    /// deterministic per officer (no clock, no Random).
    static func mulberry32(seed: UInt32) -> () -> Double {
        var a = seed
        return {
            a = a &+ 0x6d2b_79f5
            var t = a
            t = (t ^ (t >> 15)) &* (t | 1)
            t ^= t &+ ((t ^ (t >> 7)) &* (t | 61))
            return Double((t ^ (t >> 14))) / 4_294_967_296.0
        }
    }
}

// MARK: - Sheet geometry (mirror: dashboard/src/lib/world/sprites.ts)

enum PetFacing: String {
    case right, up, left, down
}

enum PetSheet {
    static let cellW = 16
    static let cellH = 32
    static let sheetW = 384
    static let sheetH = 96
    static let characterCount: UInt32 = 20
    static let characterDir = "cabinet/dashboard/public/world-assets/originals/characters"

    /// Direction origin (px) of the 6-frame strips at y=32 (idle) / y=64 (walk).
    static func dirX(_ f: PetFacing) -> Int {
        switch f {
        case .right: return 0
        case .up: return 96
        case .left: return 192
        case .down: return 288
        }
    }

    static let idleY = 32
    static let walkY = 64
    static let staticY = 0

    /// The four static frames on row 0 — R,U,L,D at x=0,16,32,48.
    static func staticX(_ f: PetFacing) -> Int {
        switch f {
        case .right: return 0
        case .up: return 16
        case .left: return 32
        case .down: return 48
        }
    }

    static func sheetPath(root: String, slug: String) -> String {
        let n = (PetHash.fnv1a(slug) % characterCount) + 1
        let nn = n < 10 ? "0\(n)" : "\(n)"
        return root + "/" + characterDir + "/Premade_Character_\(nn).png"
    }

    /// Per-officer animation phase, so two pets on one screen never step in
    /// lockstep. The world's charFrame() takes the same argument; dropping it
    /// while claiming "the same cadence" would have been a quiet lie.
    static func phase(for slug: String) -> Int {
        Int(PetHash.fnv1a(slug) % 6)
    }

    /// Frame rect (top-left origin, sheet space) for one logical tick — the
    /// same cadence as the world's charFrame(): walk advances every tick, idle
    /// every other tick.
    static func frameOrigin(anim: PetAnim, facing: PetFacing, tick: Int, phase: Int = 0) -> (x: Int, y: Int) {
        switch anim {
        case .walk:
            let f = (((tick &+ phase) % 6) + 6) % 6
            return (dirX(facing) + f * cellW, walkY)
        case .idle:
            let f = ((((tick &+ phase) / 2) % 6) + 6) % 6
            return (dirX(facing) + f * cellW, idleY)
        case .frozen:
            // PAUSED: one held walk frame — the world freezes mid-stride on the
            // killswitch and this reuses that idiom exactly.
            return (dirX(facing) + 2 * cellW, walkY)
        }
    }
}

// MARK: - Appearance — the pure state→look function (unit-pinned)

enum PetAnim: String {
    case walk, idle, frozen
}

enum PetBody: String {
    /// full colour · desaturated · outline-only shell · sprite sheet unreadable
    case full, grey, hollow, missing
}

enum PetChip: String {
    case none, question, bang, pause
}

struct PetLook: Equatable {
    let state: CabinetState
    let anim: PetAnim
    let body: PetBody
    let chip: PetChip
    let why: String

    var triple: String { "\(anim.rawValue)/\(body.rawValue)/\(chip.rawValue)" }
}

enum PetAppearance {
    /// The ONLY place a state becomes an appearance.
    ///
    /// GREEN is reachable only when the ladder says GREEN *and* this pet's own
    /// officer is present in the presence blob. A body that walks contentedly
    /// while the officer it portrays is missing would be the same lie as a
    /// green-by-default boot.
    static func look(for snap: Snapshot, officer slug: String) -> PetLook {
        switch snap.state {
        case .OFF:
            return PetLook(state: .OFF, anim: .idle, body: .hollow, chip: .question, why: snap.reason)
        case .PAUSED:
            return PetLook(state: .PAUSED, anim: .frozen, body: .full, chip: .pause, why: snap.reason)
        case .RED:
            return PetLook(state: .RED, anim: .idle, body: .grey, chip: .bang, why: snap.reason)
        case .AMBER:
            return PetLook(state: .AMBER, anim: .idle, body: .grey, chip: .question, why: snap.reason)
        case .GREEN:
            guard let row = snap.officers.first(where: { $0.slug == slug }) else {
                return PetLook(state: .AMBER, anim: .idle, body: .grey, chip: .question,
                               why: "fleet GREEN but no presence row for \(slug)")
            }
            guard row.present else {
                return PetLook(state: .AMBER, anim: .idle, body: .grey, chip: .question,
                               why: "fleet GREEN but \(slug) is absent")
            }
            return PetLook(state: .GREEN, anim: .walk, body: .full, chip: .none, why: snap.reason)
        }
    }
}

// MARK: - Pixel buffer (premultiplied RGBA8, source resolution)

/// Everything is composed at SOURCE resolution and blitted ONCE at an integer
/// scale with interpolation .none. That is the whole crispness argument: no
/// intermediate resample can creep in, because there is no intermediate.
struct PetPixels {
    let w: Int
    let h: Int
    var px: [UInt8] // premultiplied RGBA, row-major, top-left origin

    init(w: Int, h: Int) {
        self.w = w
        self.h = h
        self.px = [UInt8](repeating: 0, count: w * h * 4)
    }

    @inline(__always) func idx(_ x: Int, _ y: Int) -> Int { (y * w + x) * 4 }

    @inline(__always) func alpha(_ x: Int, _ y: Int) -> UInt8 {
        guard x >= 0, y >= 0, x < w, y < h else { return 0 }
        return px[idx(x, y) + 3]
    }

    @inline(__always) mutating func set(_ x: Int, _ y: Int, _ r: UInt8, _ g: UInt8, _ b: UInt8, _ a: UInt8) {
        guard x >= 0, y >= 0, x < w, y < h else { return }
        let i = idx(x, y)
        px[i] = r; px[i + 1] = g; px[i + 2] = b; px[i + 3] = a
    }

    /// Source-over composite of `src` at (ox, oy).
    mutating func blit(_ src: PetPixels, ox: Int, oy: Int) {
        for y in 0..<src.h {
            let dy = oy + y
            if dy < 0 || dy >= h { continue }
            for x in 0..<src.w {
                let dx = ox + x
                if dx < 0 || dx >= w { continue }
                let si = src.idx(x, y)
                let sa = Int(src.px[si + 3])
                if sa == 0 { continue }
                let di = idx(dx, dy)
                if sa == 255 {
                    px[di] = src.px[si]; px[di + 1] = src.px[si + 1]
                    px[di + 2] = src.px[si + 2]; px[di + 3] = 255
                    continue
                }
                let inv = 255 - sa
                for c in 0..<4 {
                    // CLAMPED, not asserted. The premultiplied invariant
                    // (rgb <= a) is a property of the SOURCE ART, and this
                    // buffer also carries pixels that colour transforms have
                    // touched — an unchecked UInt8(...) here turns one light
                    // semi-transparent pixel in a re-exported sheet into a
                    // SIGTRAP that kills the whole menu-bar app, in exactly
                    // the two states that mean "I do not know" and "it is
                    // bad" (found by adversarial review, 2026-07-30).
                    let v = (Int(src.px[si + c]) * 255 + Int(px[di + c]) * inv) / 255
                    px[di + c] = UInt8(max(0, min(255, v)))
                }
            }
        }
    }

    /// Luminance-flatten every visible pixel — the doctrinal "fail toward
    /// grey". The gamma lift is cosmetic only: this cast is painted in dark
    /// reds and browns, whose raw luminance renders as a near-black smudge
    /// rather than a legible grey officer. Blacks stay black, so the art's own
    /// outline survives. Asserted on the RENDERED PIXELS by the test suite
    /// (r == g == b), not on the fact that this function was called.
    func desaturated(gamma: Double = 0.84, dim: Double = 0.94) -> PetPixels {
        var out = self
        for i in stride(from: 0, to: px.count, by: 4) {
            let a = Int(px[i + 3])
            if a == 0 { continue }
            // premultiplied → luminance is linear in the stored values
            let l = Double(px[i]) * 0.2126 + Double(px[i + 1]) * 0.7152 + Double(px[i + 2]) * 0.0722
            let lifted = (255.0 * pow(l / 255.0, gamma) * dim).rounded()
            // Capped at the pixel's OWN alpha: this buffer is premultiplied, so
            // a channel above its alpha is not a bright pixel, it is a broken
            // one — and the gamma lift can produce exactly that on a light
            // semi-transparent pixel (adversarial review, 2026-07-30).
            let v = UInt8(max(0, min(Double(a), lifted)))
            out.px[i] = v; out.px[i + 1] = v; out.px[i + 2] = v
        }
        return out
    }

    /// The lowest row carrying any visible pixel (nil if the buffer is empty).
    func bottomRow() -> Int? {
        for y in stride(from: h - 1, through: 0, by: -1) {
            for x in 0..<w where alpha(x, y) >= 128 { return y }
        }
        return nil
    }

    /// 8-neighbour dilate of the alpha channel by 1px, MINUS the original —
    /// i.e. a 1px keyline that hugs the art whatever the art is.
    ///
    /// `omitBelow` suppresses the row under the feet: a white line between the
    /// soles and the contact shadow reads as a gap and un-grounds the pet.
    func keyline(r: UInt8, g: UInt8, b: UInt8, a: UInt8 = 255, omitBelow: Int? = nil) -> PetPixels {
        var out = PetPixels(w: w, h: h)
        for y in 0..<h {
            if let omitBelow, y > omitBelow { continue }
            for x in 0..<w {
                if alpha(x, y) >= 128 { continue } // interior is the sprite's own
                var touching = false
                for dy in -1...1 {
                    for dx in -1...1 where !(dx == 0 && dy == 0) {
                        if alpha(x + dx, y + dy) >= 128 { touching = true }
                    }
                }
                if touching { out.set(x, y, r, g, b, a) }
            }
        }
        return out
    }

    /// The sprite's OWN outermost pixels — every visible pixel touching a
    /// transparent neighbour, recoloured. Paired with an outer keyline this
    /// gives the OFF shell two tones (dark contour, white halo), which is what
    /// makes it legible on a light wallpaper as well as a dark one; a single
    /// light-grey outline disappeared against a light background.
    func innerEdge(r: UInt8, g: UInt8, b: UInt8) -> PetPixels {
        var out = PetPixels(w: w, h: h)
        for y in 0..<h {
            for x in 0..<w where alpha(x, y) >= 128 {
                var exposed = false
                for dy in -1...1 {
                    for dx in -1...1 where !(dx == 0 && dy == 0) {
                        if alpha(x + dx, y + dy) < 128 { exposed = true }
                    }
                }
                if exposed { out.set(x, y, r, g, b, 255) }
            }
        }
        return out
    }

    private func makeRep() -> NSBitmapImageRep? {
        NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: w, pixelsHigh: h,
                         bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
                         isPlanar: false, colorSpaceName: .deviceRGB,
                         bytesPerRow: w * 4, bitsPerPixel: 32)
    }

    func toImage() -> NSImage {
        let bytes = px
        guard let rep = makeRep() else { return NSImage(size: NSSize(width: w, height: h)) }
        if let dest = rep.bitmapData {
            bytes.withUnsafeBufferPointer { src in
                dest.update(from: src.baseAddress!, count: bytes.count)
            }
        }
        let img = NSImage(size: NSSize(width: w, height: h))
        img.addRepresentation(rep)
        return img
    }

    func pngData() -> Data? {
        guard let rep = makeRep() else { return nil }
        if let dest = rep.bitmapData {
            px.withUnsafeBufferPointer { src in
                dest.update(from: src.baseAddress!, count: px.count)
            }
        }
        return rep.representation(using: .png, properties: [:])
    }

    /// Load a PNG at EXACT pixel size into a premultiplied RGBA8 buffer.
    /// Drawn 1:1 with interpolation .none, so no resample happens on the way in.
    ///
    /// The DIMENSION CHECK is the point, not a formality: a truncated or
    /// re-exported sheet still decodes, and drawing it into a 384x96 rect
    /// silently resamples it — which produced a pet with ten visible pixels
    /// and no error at all (adversarial review, 2026-07-30). Refusing here is
    /// what routes the caller to the loud MISSING body. A partially-decoded
    /// image is a broken sheet, not a small one.
    static func load(path: String, w: Int, h: Int) -> PetPixels? {
        guard FileManager.default.isReadableFile(atPath: path),
              let img = NSImage(contentsOfFile: path) else { return nil }
        let pixelSizes = img.representations.map { ($0.pixelsWide, $0.pixelsHigh) }
        guard pixelSizes.contains(where: { $0 == (w, h) }) else {
            CompanionLog.shared.line("pet: sheet \(path) decodes at \(pixelSizes) — expected \(w)x\(h); refusing to resample a broken sheet")
            return nil
        }
        guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: w, pixelsHigh: h,
                                         bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
                                         isPlanar: false, colorSpaceName: .deviceRGB,
                                         bytesPerRow: w * 4, bitsPerPixel: 32) else { return nil }
        NSGraphicsContext.saveGraphicsState()
        defer { NSGraphicsContext.restoreGraphicsState() }
        guard let ctx = NSGraphicsContext(bitmapImageRep: rep) else { return nil }
        NSGraphicsContext.current = ctx
        ctx.imageInterpolation = .none
        img.draw(in: NSRect(x: 0, y: 0, width: w, height: h),
                 from: NSRect(x: 0, y: 0, width: w, height: h),
                 operation: .copy, fraction: 1.0)
        ctx.flushGraphics()
        guard let data = rep.bitmapData else { return nil }
        var out = PetPixels(w: w, h: h)
        // NSBitmapImageRep rows are top-left origin, matching PetPixels.
        for i in 0..<(w * h * 4) { out.px[i] = data[i] }
        return out
    }

    /// One 16x32 cell out of a sheet (top-left origin coordinates).
    func cell(x: Int, y: Int, w cw: Int, h ch: Int) -> PetPixels {
        var out = PetPixels(w: cw, h: ch)
        for yy in 0..<ch {
            for xx in 0..<cw {
                let sx = x + xx, sy = y + yy
                guard sx >= 0, sy >= 0, sx < w, sy < h else { continue }
                let si = idx(sx, sy)
                out.set(xx, yy, px[si], px[si + 1], px[si + 2], px[si + 3])
            }
        }
        return out
    }
}

// MARK: - Chip glyphs (3x5 pixels — legible at any integer scale, no font)

enum PetChipArt {
    static let glyphW = 3
    static let glyphH = 5

    static func glyph(_ chip: PetChip) -> [String] {
        switch chip {
        case .question: return ["###", "..#", ".##", "...", ".#."]
        case .bang: return [".#.", ".#.", ".#.", "...", ".#."]
        case .pause: return ["#.#", "#.#", "#.#", "#.#", "#.#"]
        case .none: return []
        }
    }

    /// Chip body colour. State is carried by the GLYPH SHAPE first (the
    /// menu-bar icon's own doctrine: never colour alone); colour is the second
    /// channel, and the white keyline is what makes it read on any wallpaper.
    static func bodyColor(_ chip: PetChip, dim: Bool) -> (UInt8, UInt8, UInt8) {
        if dim { return (0x6a, 0x6a, 0x74) }
        switch chip {
        case .question: return (0xf0, 0xa1, 0x22)
        case .bang: return (0xd8, 0x36, 0x2c)
        case .pause: return (0x36, 0x7c, 0xd8)
        case .none: return (0, 0, 0)
        }
    }

    static func glyphColor(_ chip: PetChip, dim: Bool) -> (UInt8, UInt8, UInt8) {
        if dim { return (0xf2, 0xf2, 0xf6) }
        switch chip {
        case .question: return (0x24, 0x1a, 0x06) // dark on amber — white would not read
        default: return (0xff, 0xff, 0xff)
        }
    }

    /// 7x9 chip: rounded body + 3x5 glyph. Returned WITHOUT its keyline; the
    /// composer adds that from the alpha, same recipe as the officer's.
    static func render(_ chip: PetChip, dim: Bool) -> PetPixels? {
        let g = glyph(chip)
        if g.isEmpty { return nil }
        let w = 7, h = 9
        var out = PetPixels(w: w, h: h)
        let (br, bg, bb) = bodyColor(chip, dim: dim)
        for y in 0..<h {
            for x in 0..<w {
                // clip the four corners → a rounded chip rather than a box
                let corner = (x == 0 || x == w - 1) && (y == 0 || y == h - 1)
                if corner { continue }
                out.set(x, y, br, bg, bb, 255)
            }
        }
        let (gr, gg, gb) = glyphColor(chip, dim: dim)
        let ox = (w - glyphW) / 2
        let oy = (h - glyphH) / 2
        for (row, line) in g.enumerated() {
            for (col, ch) in line.enumerated() where ch == "#" {
                out.set(ox + col, oy + row, gr, gg, gb, 255)
            }
        }
        return out
    }
}

// MARK: - Composer: (look, facing, tick) → one source-resolution canvas

final class PetComposer {
    // Canvas layout, in SOURCE pixels. The sprite CELL is 16x32 but its art
    // occupies rows 5...31 (measured across all 48 frames of the owned cast),
    // so the head and the feet — not the cell edges — set these numbers.
    static let canvasW = 24
    static let canvasH = 39
    static let spriteX = 4     // 16 wide → cols 4...19, keyline 3...20
    static let spriteY = 6     // 32 tall → rows 6...37; art rows 11...37
    static let chipX = 16      // 7 wide  → cols 16...22 (clear of the head)
    static let chipY = 0       // 9 tall  → rows 0...8, one clear row above the hair
    static let shadowY = 38    // contact shadow: the ground line, and the
                               // window's bottom row — it lands ON the Dock's
                               // top edge, which is what makes the pet look
                               // like it is standing there rather than hovering

    private let sheet: PetPixels?
    private let sheetPath: String
    private let phase: Int
    private var cache: [String: NSImage] = [:]

    init(root: String, slug: String) {
        phase = PetSheet.phase(for: slug)
        sheetPath = PetSheet.sheetPath(root: root, slug: slug)
        sheet = PetPixels.load(path: sheetPath, w: PetSheet.sheetW, h: PetSheet.sheetH)
        if sheet == nil {
            CompanionLog.shared.line("pet: sprite sheet unreadable at \(sheetPath) — rendering the MISSING body (hollow box), never a silent nothing")
        }
    }

    var sheetLoaded: Bool { sheet != nil }
    var loadedFrom: String { sheetPath }

    func image(look: PetLook, facing: PetFacing, tick: Int) -> NSImage {
        let key = "\(look.triple)|\(facing.rawValue)|\(tick % 12)|\(sheet == nil)"
        if let cached = cache[key] { return cached }
        let img = canvas(look: look, facing: facing, tick: tick).toImage()
        cache[key] = img
        return img
    }

    func canvas(look: PetLook, facing: PetFacing, tick: Int) -> PetPixels {
        var out = PetPixels(w: Self.canvasW, h: Self.canvasH)

        // --- contact shadow: anchors the pet to the Dock's top edge ---
        let shadowCols = [(7, 55), (8, 100), (9, 140), (10, 160), (11, 170), (12, 170), (13, 160), (14, 140), (15, 100), (16, 55)]
        for (x, a) in shadowCols {
            // premultiplied black
            out.set(x, Self.shadowY, 0, 0, 0, UInt8(a))
        }

        // --- body ---
        let body = bodyPixels(look: look, facing: facing, tick: tick)
        let bottom = body.bottomRow()
        out.blit(body.keyline(r: 0xff, g: 0xff, b: 0xff, omitBelow: bottom),
                 ox: Self.spriteX, oy: Self.spriteY)
        if look.body == .hollow {
            // OFF: the shell only — the officer's outline with nobody in it.
            out.blit(body.innerEdge(r: 0x8c, g: 0x8c, b: 0x98), ox: Self.spriteX, oy: Self.spriteY)
        } else {
            out.blit(body, ox: Self.spriteX, oy: Self.spriteY)
        }

        // --- chip ---
        if let chip = PetChipArt.render(look.chip, dim: look.body == .hollow) {
            out.blit(chip.keyline(r: 0xff, g: 0xff, b: 0xff), ox: Self.chipX, oy: Self.chipY)
            out.blit(chip, ox: Self.chipX, oy: Self.chipY)
        }
        return out
    }

    /// The sprite cell for this look, already colour-treated.
    private func bodyPixels(look: PetLook, facing: PetFacing, tick: Int) -> PetPixels {
        guard let sheet else { return Self.missingBody() }
        let o = PetSheet.frameOrigin(anim: look.anim, facing: facing, tick: tick, phase: phase)
        let cellPixels = sheet.cell(x: o.x, y: o.y, w: PetSheet.cellW, h: PetSheet.cellH)
        // A cell with no ink means the sheet decoded but the frame is not
        // there. Drawing it renders an EMPTY window, which is the one thing
        // this file exists to forbid — a pet nobody can see is
        // indistinguishable from a pet that was never launched. Fail to the
        // loud box instead (adversarial review, 2026-07-30).
        guard cellPixels.bottomRow() != nil else {
            Self.warnOnce("pet: sheet frame at (\(o.x),\(o.y)) is empty — the sheet loaded but carries no art there; rendering the MISSING body")
            return Self.missingBody()
        }
        switch look.body {
        case .full: return cellPixels
        case .grey: return cellPixels.desaturated()
        case .hollow: return cellPixels // only its keyline is drawn (shell)
        case .missing: return Self.missingBody()
        }
    }

    /// One line per distinct message — the composer runs at 8 fps and an
    /// unguarded log would write the same sentence 480 times a minute.
    private static var warned = Set<String>()
    static func warnOnce(_ message: String) {
        guard !warned.contains(message) else { return }
        warned.insert(message)
        CompanionLog.shared.line(message)
    }

    /// Sheet unreadable: an unmistakable empty box, never an empty window.
    static func missingBody() -> PetPixels {
        var out = PetPixels(w: PetSheet.cellW, h: PetSheet.cellH)
        for y in 8..<28 {
            for x in 2..<14 where (x == 2 || x == 13 || y == 8 || y == 27) {
                out.set(x, y, 0xc8, 0x50, 0x50, 255)
            }
        }
        return out
    }
}

// MARK: - The view: one blit, integer scale, nearest neighbour

final class PetView: NSView {
    var image: NSImage? {
        didSet { needsDisplay = true }
    }

    override var isFlipped: Bool { false }
    override var isOpaque: Bool { false }

    override func draw(_ dirtyRect: NSRect) {
        NSColor.clear.setFill()
        dirtyRect.fill(using: .copy)
        guard let image else { return }
        NSGraphicsContext.current?.imageInterpolation = .none
        NSGraphicsContext.current?.shouldAntialias = false
        image.draw(in: bounds.integral, from: NSRect(origin: .zero, size: image.size),
                   operation: .sourceOver, fraction: 1.0)
    }
}

// MARK: - Controller: window placement beside the Dock, roam, animation

final class PetController {
    /// MEASURED 2026-07-30 on macOS 26.6: per-pixel click-through is BROKEN —
    /// an empty transparent window still swallows clicks. This stays true.
    static let petWindowIgnoresMouse = true

    static let fps: Double = 8

    private let window: NSWindow
    private let view = PetView()
    private let composer: PetComposer
    private let slug: String
    private let scale: Int
    private var rng: () -> Double
    private var tick = 0
    private var lastFrameTime: CFTimeInterval = 0
    private var displayLink: CADisplayLink?
    private var timer: Timer?
    private var screenObserver: NSObjectProtocol?

    private var snapshot: Snapshot
    private var look: PetLook
    private var facing: PetFacing = .down
    private var x: CGFloat = 0
    private var targetX: CGFloat = 0
    private var idleUntilTick = 0
    private var track = (feetY: CGFloat(0), minX: CGFloat(0), maxX: CGFloat(0))

    init(root: String, slug: String, scale: Int, initial: Snapshot) {
        self.slug = slug
        self.scale = max(1, min(8, scale))
        self.composer = PetComposer(root: root, slug: slug)
        self.snapshot = initial
        self.look = PetAppearance.look(for: initial, officer: slug)
        self.rng = PetHash.mulberry32(seed: PetHash.fnv1a(slug))

        let w = CGFloat(PetComposer.canvasW * self.scale)
        let h = CGFloat(PetComposer.canvasH * self.scale)
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: w, height: h),
                          styleMask: .borderless, backing: .buffered, defer: false)
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = false
        window.level = .floating
        window.ignoresMouseEvents = Self.petWindowIgnoresMouse
        window.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle, .fullScreenAuxiliary]
        window.isReleasedWhenClosed = false
        window.contentView = view

        recomputeTrack()
        x = (track.minX + track.maxX) / 2
        targetX = x
        idleUntilTick = 30
        place()
        redraw()
        window.orderFrontRegardless()
        startClock()

        screenObserver = NotificationCenter.default.addObserver(
            forName: NSApplication.didChangeScreenParametersNotification, object: nil, queue: .main
        ) { [weak self] _ in self?.recomputeTrack(); self?.place() }

        CompanionLog.shared.line("pet: window up — officer=\(slug) scale=\(self.scale) sheet=\(composer.sheetLoaded ? composer.loadedFrom : "MISSING") clickThrough=ignoresMouseEvents(\(Self.petWindowIgnoresMouse))")
    }

    deinit {
        displayLink?.invalidate()
        timer?.invalidate()
        if let screenObserver { NotificationCenter.default.removeObserver(screenObserver) }
    }

    var isVisible: Bool { window.isVisible }

    func setVisible(_ visible: Bool) {
        if visible {
            recomputeTrack()
            place()
            window.orderFrontRegardless()
            startClock()
        } else {
            // Stop the clock, do not merely hide the window: a hidden pet that
            // keeps stepping burns 0.3% of a core drawing frames nobody can
            // see, and CADisplayLink holds its target STRONGLY, so leaving it
            // armed is also what keeps this controller alive forever
            // (adversarial review, 2026-07-30).
            stopClock()
            window.orderOut(nil)
        }
    }

    func apply(snapshot newSnapshot: Snapshot) {
        snapshot = newSnapshot
        let next = PetAppearance.look(for: newSnapshot, officer: slug)
        if next.triple != look.triple {
            CompanionLog.shared.line("pet: \(look.state.rawValue)[\(look.triple)] → \(next.state.rawValue)[\(next.triple)] — \(next.why)")
        }
        look = next
        redraw()
    }

    // ---- placement (ZERO permissions: NSScreen frame minus visibleFrame) ----

    private func recomputeTrack() {
        let screen = window.screen ?? NSScreen.main ?? NSScreen.screens.first
        guard let screen else { return }
        let f = screen.frame
        let v = screen.visibleFrame
        let bottom = v.minY - f.minY
        let left = v.minX - f.minX
        let right = f.maxX - v.maxX
        let w = CGFloat(PetComposer.canvasW * scale)
        let margin: CGFloat = 8

        // The Dock is the largest non-menu-bar inset. Autohidden ⇒ every inset
        // is ~0 and the pet stands on the screen's own bottom edge, which is
        // still "beside the Dock" the moment the Dock slides up.
        if bottom >= max(left, right) {
            track = (feetY: f.minY + bottom, minX: f.minX + margin, maxX: f.maxX - w - margin)
        } else if left > right {
            track = (feetY: f.minY + margin, minX: f.minX + left + margin, maxX: f.maxX - w - margin)
        } else {
            track = (feetY: f.minY + margin, minX: f.minX + margin, maxX: f.maxX - right - w - margin)
        }
        if track.maxX < track.minX { track = (track.feetY, track.minX, track.minX) }
        x = min(max(x, track.minX), track.maxX)
        targetX = min(max(targetX, track.minX), track.maxX)
    }

    private func place() {
        // The contact-shadow row IS the canvas' last row, so the window's
        // bottom edge is the ground line and lands exactly on the Dock's top
        // edge — that is what makes the officer read as standing on it rather
        // than hovering above it.
        precondition(PetComposer.shadowY == PetComposer.canvasH - 1,
                     "the ground line must be the canvas' last row")
        window.setFrameOrigin(NSPoint(x: x.rounded(), y: track.feetY.rounded()))
    }

    // ---- clock ----

    private func stopClock() {
        displayLink?.invalidate()
        displayLink = nil
        timer?.invalidate()
        timer = nil
    }

    private func startClock() {
        guard displayLink == nil, timer == nil else { return }
        if #available(macOS 14.0, *) {
            let link = view.displayLink(target: self, selector: #selector(displayTick(_:)))
            link.preferredFrameRateRange = CAFrameRateRange(minimum: Float(Self.fps),
                                                            maximum: Float(Self.fps),
                                                            preferred: Float(Self.fps))
            link.add(to: .main, forMode: .common)
            displayLink = link
        } else {
            let t = Timer(timeInterval: 1.0 / Self.fps, repeats: true) { [weak self] _ in self?.step() }
            t.tolerance = 0.05
            RunLoop.main.add(t, forMode: .common)
            timer = t
        }
    }

    @available(macOS 14.0, *)
    @objc private func displayTick(_ link: CADisplayLink) {
        // Gate on wall time as well as the frame-rate hint: on a 120Hz panel an
        // uncapped link would run the walk 15x too fast.
        if link.timestamp - lastFrameTime < (1.0 / Self.fps) - 0.002 { return }
        lastFrameTime = link.timestamp
        step()
    }

    private func step() {
        tick &+= 1
        if look.anim == .walk {
            roam()
        } else {
            facing = .down // stopped, looking at the Captain
        }
        redraw()
    }

    private func roam() {
        let speed = CGFloat(scale) // 1 source pixel per frame
        if tick < idleUntilTick {
            facing = .down
            return
        }
        if abs(targetX - x) < speed {
            // arrived → stand a moment, then choose a new destination
            let span = max(1, track.maxX - track.minX)
            targetX = track.minX + CGFloat(rng()) * span
            idleUntilTick = tick &+ 8 &+ Int(rng() * 40)
            facing = .down
            return
        }
        if targetX > x {
            x += speed
            facing = .right
        } else {
            x -= speed
            facing = .left
        }
        place()
    }

    private func redraw() {
        view.image = composer.image(look: look, facing: facing, tick: tick)
    }
}

// MARK: - Headless entry points (proof surfaces — no window, print, exit)

enum PetCLI {

    /// Synthetic snapshots for the five ladder states + the two degraded-GREEN
    /// cases. Used by --pet-selftest, --pet-render and --pet-demo, so the
    /// forced states in the proof are the SAME inputs the tests assert on.
    static func demoSnapshot(_ state: CabinetState, slug: String) -> Snapshot {
        let now = Date()
        switch state {
        case .OFF:
            return Snapshot(state: .OFF, reason: "Redis unreachable at 127.0.0.1:6379 — cabinet not running",
                            officers: [], rootValid: true, redisUp: false, killswitchActive: nil,
                            doctorLine: "Doctor: state unknown (Redis down)", takenAt: now)
        case .PAUSED:
            return Snapshot(state: .PAUSED, reason: "kill switch active — every officer halts on its next tool call",
                            officers: [], rootValid: true, redisUp: true, killswitchActive: true,
                            doctorLine: "Doctor: GREEN (2m ago)", takenAt: now)
        case .RED:
            return Snapshot(state: .RED, reason: "doctor RED: 119 dead check(s)",
                            officers: [], rootValid: true, redisUp: true, killswitchActive: false,
                            doctorLine: "Doctor: DEAD:119", takenAt: now)
        case .AMBER:
            return Snapshot(state: .AMBER, reason: "hatched but quiet — no presence/doctor data",
                            officers: [], rootValid: true, redisUp: true, killswitchActive: false,
                            doctorLine: "Doctor: has never run", takenAt: now)
        case .GREEN:
            return Snapshot(state: .GREEN, reason: "presence v1 fresh · killswitch off · doctor GREEN 12s ago",
                            officers: [OfficerRow(slug: slug, present: true, verb: "working", ttlSeconds: 42, since: "")],
                            rootValid: true, redisUp: true, killswitchActive: false,
                            doctorLine: "Doctor: GREEN (12s ago)", takenAt: now)
        }
    }

    static func parseState(_ s: String) -> CabinetState? {
        CabinetState(rawValue: s.uppercased())
    }

    /// --pet-selftest: every state through the PURE look function, one machine
    /// readable line each. The gate asserts the five ladder looks are DISTINCT
    /// (a pet that shows the same thing regardless of state is the defect) and
    /// that nothing but GREEN walks.
    static func selftest() -> Int32 {
        let slug = PetOptions.slug
        var lines: [String] = []
        for state in [CabinetState.OFF, .PAUSED, .RED, .AMBER, .GREEN] {
            let look = PetAppearance.look(for: demoSnapshot(state, slug: slug), officer: slug)
            lines.append("PETLOOK in=\(state.rawValue) state=\(look.state.rawValue) anim=\(look.anim.rawValue) body=\(look.body.rawValue) chip=\(look.chip.rawValue) why=\(look.why)")
        }
        // degraded GREEN: the ladder says GREEN, this officer does not
        var snap = demoSnapshot(.GREEN, slug: slug)
        let noRow = Snapshot(state: .GREEN, reason: snap.reason, officers: [],
                             rootValid: true, redisUp: true, killswitchActive: false,
                             doctorLine: snap.doctorLine, takenAt: snap.takenAt)
        var look = PetAppearance.look(for: noRow, officer: slug)
        lines.append("PETLOOK in=GREEN_NO_ROW state=\(look.state.rawValue) anim=\(look.anim.rawValue) body=\(look.body.rawValue) chip=\(look.chip.rawValue) why=\(look.why)")
        snap = Snapshot(state: .GREEN, reason: snap.reason,
                        officers: [OfficerRow(slug: slug, present: false, verb: "?", ttlSeconds: -1, since: "")],
                        rootValid: true, redisUp: true, killswitchActive: false,
                        doctorLine: snap.doctorLine, takenAt: snap.takenAt)
        look = PetAppearance.look(for: snap, officer: slug)
        lines.append("PETLOOK in=GREEN_ABSENT state=\(look.state.rawValue) anim=\(look.anim.rawValue) body=\(look.body.rawValue) chip=\(look.chip.rawValue) why=\(look.why)")

        let root = CompanionCore.resolveRoot()
        let sheet = PetSheet.sheetPath(root: root.path, slug: slug)
        lines.append("PETSHEET officer=\(slug) path=\(sheet) readable=\(FileManager.default.isReadableFile(atPath: sheet))")
        lines.append("PETWINDOW ignoresMouseEvents=\(PetController.petWindowIgnoresMouse) canvas=\(PetComposer.canvasW)x\(PetComposer.canvasH) scale=\(PetOptions.scale)")
        for l in lines { print(l) }
        return 0
    }

    /// --pet-render <STATE> <out.png>: the composed canvas at SOURCE
    /// resolution, so a test can assert on the actual pixels (is grey really
    /// grey, is hollow really hollow) instead of on a label.
    static func render(state: CabinetState, to path: String, tick: Int) -> Int32 {
        let root = CompanionCore.resolveRoot()
        guard root.valid else {
            FileHandle.standardError.write(Data("pet-render: no cabinet root at \(root.path)\n".utf8))
            return 1
        }
        let slug = PetOptions.slug
        let composer = PetComposer(root: root.path, slug: slug)
        guard composer.sheetLoaded else {
            FileHandle.standardError.write(Data("pet-render: sprite sheet unreadable at \(composer.loadedFrom)\n".utf8))
            return 1
        }
        let look = PetAppearance.look(for: demoSnapshot(state, slug: slug), officer: slug)
        let canvas = composer.canvas(look: look, facing: look.anim == .walk ? .right : .down, tick: tick)
        guard let data = canvas.pngData() else {
            FileHandle.standardError.write(Data("pet-render: PNG encode failed\n".utf8))
            return 1
        }
        do {
            try data.write(to: URL(fileURLWithPath: path))
        } catch {
            FileHandle.standardError.write(Data("pet-render: write failed: \(error.localizedDescription)\n".utf8))
            return 1
        }
        print("PETRENDER state=\(state.rawValue) look=\(look.triple) canvas=\(canvas.w)x\(canvas.h) out=\(path)")
        return 0
    }
}
