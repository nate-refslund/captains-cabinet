/**
 * capture.test.ts — THE GATE. Compose a real world state, draw a real frame,
 * and run all twelve invariants in checks/world_checks.py against the pixels.
 *
 * This is the arm that makes every measurement the layout stage has ever taken
 * mean something. Before it, composeLayout had no caller outside its own tests
 * and the checks had never seen a composed island; "does the belt read as
 * framing" was answered by a density histogram. Now a change that breaks the
 * world goes red here instead of in the Captain's eye.
 *
 * IT SHELLS OUT TO PYTHON ON PURPOSE. The checks may not import what they test
 * (their own first law, paid for when an on-road audit called the same
 * footprint helper the placement rule called and the world was reported clean
 * three times while props stood in the road). Running them as a separate
 * process against files on disk is the strongest form of that separation
 * available, and it is the same command a human runs.
 *
 * IT DOES NOT SKIP WHEN PYTHON OR PILLOW IS ABSENT. A skipped test is a
 * disabled sensor: the whole point is that CI cannot go green without a frame
 * having been judged. The failure message says exactly what to install.
 *
 * SIX MUTATIONS FOLLOW THE GREEN RUN, each breaking exactly one rule and
 * asserting the arm that guards it goes RED — and that NOTHING ELSE does. An
 * arm nobody has watched fail is decoration.
 */
import { describe, expect, it } from 'vitest'
import { execFileSync } from 'node:child_process'
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { composeFrame, type WorldPack } from './blueprint'
import type { LayoutState } from './iso-layout'

const DASH = process.cwd()
const CAPTURE = join(DASH, '..', 'scripts', 'world-capture')
const PACK_DIR = join(DASH, 'public', 'world-assets', 'originals', 'iso')
const PACK_JSON = join(PACK_DIR, 'world-pack.json')
const PACK: WorldPack = JSON.parse(readFileSync(PACK_JSON, 'utf8'))

/** The interpreter that has Pillow. Named rather than guessed, and never skipped. */
function python(): string {
  const tried: string[] = []
  for (const exe of ['python3.12', 'python3']) {
    try {
      execFileSync(exe, ['-c', 'import PIL'], { stdio: 'pipe' })
      return exe
    } catch (e) {
      tried.push(`${exe}: ${(e as Error).message.split('\n')[0]}`)
    }
  }
  throw new Error(
    'world capture needs python with Pillow, and found none — the twelve world ' +
      'invariants cannot run, so this suite must not report green.\n' +
      '  fix: pip install pillow\n  tried:\n    ' + tried.join('\n    ')
  )
}

interface Verdict {
  results: { check: string; ok: boolean; detail: string }[]
  unchecked: string[]
  red: string[]
}

function capture(fixtureName: string, mutate = ''): Verdict {
  const py = python()
  const f = JSON.parse(
    readFileSync(join(CAPTURE, 'states', `${fixtureName}.json`), 'utf8')
  ) as { seed: string; date: string; index: number; state: LayoutState }

  const dir = mkdtempSync(join(tmpdir(), `world-capture-${fixtureName}-`))
  try {
    // 1. THE LAYOUT — the same composeLayout the rest of this suite tests,
    //    called in-process. No browser, because the layout is a pure function.
    const frame = composeFrame(PACK, f.state, f.seed, { date: f.date, index: f.index })
    writeFileSync(join(dir, 'blueprint.json'), JSON.stringify(frame.blueprint))
    writeFileSync(join(dir, 'draw.json'), JSON.stringify(frame.draw))

    // auditLayout's own arms travel with the capture — a frame whose layout
    // already knows it is broken must not be judged as if it were not.
    expect(frame.audit.onLane, `${fixtureName}: layout audit onLane`).toEqual([])
    expect(frame.audit.stacked, `${fixtureName}: layout audit stacked`).toEqual([])
    expect(frame.audit.inWater, `${fixtureName}: layout audit inWater`).toEqual([])
    expect(frame.audit.outsideHarbour, `${fixtureName}: layout audit harbour`).toEqual([])

    // 2. THE PIXELS. Scale 1.0 always: the checks carry absolute-pixel
    //    constants, so a shrunk frame is judged at a different relative
    //    resolution and invents defects (measured — see raster.py --scale).
    const assets = join(dir, 'assets')
    mkdirSync(assets, { recursive: true })
    execFileSync(py, [
      join(CAPTURE, 'raster.py'),
      '--draw', join(dir, 'draw.json'),
      '--blueprint', join(dir, 'blueprint.json'),
      '--pack', PACK_JSON,
      '--atlas', PACK_DIR,
      '--assets', assets,
      '--out', join(dir, 'frame.png'),
      ...(mutate ? ['--mutate', mutate] : []),
    ], { cwd: CAPTURE, stdio: 'pipe' })

    // 3. THE TWELVE INVARIANTS, as a separate process reading only files.
    try {
      execFileSync(py, [
        join(CAPTURE, 'mirror', 'checks', 'verify.py'),
        '--render', join(dir, 'frame.png'),
        '--assets', assets,
        '--allow-ambient', join(CAPTURE, 'ambient-nature.txt'),
      ], { cwd: CAPTURE, stdio: 'pipe' })
    } catch {
      /* a red arm exits 1; the verdict file is still written and is what we read */
    }
    return JSON.parse(readFileSync(join(dir, 'frame.verify.json'), 'utf8')) as Verdict
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
}

const TIMEOUT = { timeout: 180_000 }

describe('the world, judged', () => {
  it('camp: all twelve invariants pass on a real frame', TIMEOUT, () => {
    const v = capture('camp')
    expect(v.results.filter((r) => !r.ok).map((r) => `${r.check}: ${r.detail}`)).toEqual([])
    expect(v.results).toHaveLength(12)
    // The camp frame declares no square and no plots, so the era floor table is
    // the only surface that can be judged there — and it can, which is why this
    // frame is the one that reaches zero unchecked surfaces.
    expect(v.unchecked).toEqual([])
  })

  it('hamlet: all twelve invariants pass on a real frame', TIMEOUT, () => {
    const v = capture('hamlet')
    expect(v.results.filter((r) => !r.ok).map((r) => `${r.check}: ${r.detail}`)).toEqual([])
    expect(v.results).toHaveLength(12)
    // KNOWN AND REPORTED, not hidden: every floor in world_checks.ERA_MIN is
    // 'hamlet', so above camp the era arm is structurally incapable of firing
    // and REFUSES to claim the surface rather than print a zero that reads like
    // evidence. Asserting [] here would be asserting a coverage this frame does
    // not have.
    expect(v.unchecked).toEqual(['era'])
  })
})

/**
 * Each row: break one rule, name the arm that must catch it. Proven by running
 * them — every one of these was red on first execution and green with the
 * mutation removed.
 */
const MUTATIONS: [string, string][] = [
  ['orphan-sprite', 'state_traceable'],   // a bench no rung or count entitles
  ['sprite-on-lane', 'on_road'],          // a building standing in the road
  ['no-shadows', 'shadows'],              // sprites floating without a cast shadow
  ['reverse-depth', 'depth_order'],       // far sprites painted over near ones
  ['unpaved-square', 'terrain'],          // a square declared and never paved
  ['ghost-sprite', 'paint_fidelity'],     // a declared sprite that leaves no mark
]

describe('the checks can fail — every arm, proven', () => {
  for (const [mutation, arm] of MUTATIONS) {
    it(`${mutation} turns ${arm} red, and only ${arm}`, TIMEOUT, () => {
      const v = capture('hamlet', mutation)
      expect(v.red, `${mutation} must be caught by exactly ${arm}`).toEqual([arm])
    })
  }
})
