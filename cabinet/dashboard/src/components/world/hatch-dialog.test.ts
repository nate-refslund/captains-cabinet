/**
 * HatchDialog static contracts (vitest, node env — grep-ratchet style, same
 * as components/world/ui-layer.test.ts). The pure behaviour is proven in
 * lib/world/hatch-dialog.test.ts; this suite pins that the VIEW obeys the
 * spec by construction: it drives off the pure frame, wears the parchment
 * pixel frame, renders data in DOM mono, gates buttons through the frame
 * (never hardcoded), and stays actuation-free (ratchet #1b) + wall-clock-free
 * (ratchet #4).
 */
import { describe, expect, it } from 'vitest'
import fs from 'fs'
import path from 'path'

const DASH = path.resolve(__dirname, '..', '..', '..')
const src = (...rel: string[]) =>
  fs.readFileSync(path.join(DASH, 'src', ...rel), 'utf8')

const DIALOG = src('components', 'world', 'hatch-dialog.tsx')

describe('HatchDialog wears the pixel frame (Harvestholm parchment)', () => {
  it('renders inside PixelFrame, parchment by default', () => {
    expect(DIALOG).toMatch(/<PixelFrame/)
    expect(DIALOG).toMatch(/parchment/)
  })
  it('never uses the heavy frame (reserved-salience: heavy = killswitch only)', () => {
    expect(DIALOG).not.toMatch(/theme=['"]heavy['"]/)
    // heavy is also refused at the type boundary.
    expect(DIALOG).toMatch(/Exclude<FrameTheme, 'heavy'>/)
  })
})

describe('HatchDialog drives off the pure, deterministic model', () => {
  it('imports and renders the pure frame from lib/world/hatch-dialog', () => {
    expect(DIALOG).toMatch(/from '@\/lib\/world\/hatch-dialog'/)
    expect(DIALOG).toMatch(/renderFrame\(/)
  })
  it('is wall-clock-free and randomness-free (ratchet #4)', () => {
    expect(DIALOG).not.toMatch(/Date\.now\s*\(/)
    expect(DIALOG).not.toMatch(/Math\.random\s*\(/)
  })
})

describe('H-2 button gating is structural, not hardcoded', () => {
  it('buttons render by mapping the gated frame list (empty in living mode)', () => {
    expect(DIALOG).toMatch(/frame\.buttons\.map\(/)
    // The button label comes from the gated kind, not a literal button set.
    expect(DIALOG).toMatch(/\{b\.kind\}/)
  })
  it('the hatching button set is wired as parent-owned handler props', () => {
    for (const h of ['onBack', 'onNext', 'onValidate', 'onSign', 'onSend']) {
      expect(DIALOG, h).toMatch(new RegExp(`\\b${h}\\b`))
    }
  })
})

describe('HatchDialog actuates nothing itself (read-only tree, ratchet #1b/#3)', () => {
  it('imports no server action and declares no server directive', () => {
    expect(DIALOG).not.toMatch(/@\/actions\//)
    expect(DIALOG).not.toMatch(/['"]use server['"]/)
  })
  it('renders text only — no HTML-injection surface', () => {
    expect(DIALOG).not.toMatch(/dangerouslySetInnerHTML/)
    expect(DIALOG).not.toMatch(/\binnerHTML\s*=/)
    expect(DIALOG).not.toMatch(/insertAdjacentHTML/)
  })
})

describe('base close button (ui-pack law: close is always allowed, mode-independent)', () => {
  it('renders the esc/close only when onClose is provided, with an aria-label', () => {
    // Close is the pre-existing base button H-2 adds its set "on top of" — it
    // is correctly NOT gated on hatching mode, but IS gated on the handler.
    expect(DIALOG).toMatch(/onClose \?/)
    // COMMISSIONING vocabulary (Captain ruling 2026-07-17): display strings
    // say "commissioning"; machine identifiers (DialogMode 'hatching',
    // HatchButton, file/route names) stay frozen.
    expect(DIALOG).toMatch(/aria-label="close commissioning dialog"/)
  })
})

describe('DOM-mono datum law (§9.2 / §15.6)', () => {
  it('the typewriter body and input render in DOM mono', () => {
    expect(DIALOG).toMatch(/data-typewriter/)
    // Both the body <p> and the input carry font-mono.
    expect((DIALOG.match(/font-mono/g) ?? []).length).toBeGreaterThanOrEqual(2)
  })
})
