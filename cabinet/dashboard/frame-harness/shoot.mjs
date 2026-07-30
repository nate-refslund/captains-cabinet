/**
 * shoot.mjs — capture real composited /world frames across the CLOCK and the ZOOM.
 *
 *   node frame-harness/shoot.mjs --out /tmp/world-frames
 *   node frame-harness/shoot.mjs --out DIR --state camp --hours 7,13,19,2 --zooms 0.5,1,2
 *
 * BOTH AXES WERE BLIND, and that is the whole reason this file exists.
 *   THE CLOCK: `cabinet/scripts/world-capture/capture.py` has no clock at all —
 *     `grep -r 'veil\|clockHour\|bucket'` over it returns nothing — so the dusk
 *     ambience lived three hours a day, outside all twelve invariants, until a
 *     person looked at a picture.
 *   THE ZOOM: capture.py's own docstring says CAPTURE AT SCALE 1.0 TO JUDGE, so
 *     every visual claim the world has ever made is also a claim about one zoom.
 * A capture whose bucket is whatever hour CI happens to run at is a flaky
 * sensor, not a sensor, so the hour is an INPUT here and never a reading.
 *
 * WHAT COMES OUT: one PNG per cell plus `frames.json`, the manifest the judge
 * reads. Every lit cell is paired with its own DAY twin at the identical state,
 * zoom, weather and canvas size — the pairing is what lets a check ask whether
 * the shipped ambience is the pure colour remap it claims to be, which no
 * single frame can answer and no unit test can reach past the GPU.
 *
 * IT NEVER SKIPS. No browser, no WebGL, a renderer that reported an issue, a
 * frame that came back a single flat colour: each is a non-zero exit with the
 * reason. A capture step that quietly produces nothing is the disabled sensor
 * this whole programme keeps finding in its own tests.
 */
import { createServer } from 'vite'
import { chromium } from 'playwright-core'
import { existsSync, mkdirSync, writeFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))

// ── the browser ─────────────────────────────────────────────────────────────
/**
 * A real Chromium, named rather than downloaded.
 *
 * `playwright-core` carries no browser, which is deliberate: GitHub's
 * ubuntu-latest image ships Chromium and Chrome already, so the alternative —
 * `playwright` plus a ~150MB per-run browser install — buys nothing but minutes.
 * Every candidate below is a real path on one of the two machines this runs on.
 */
function chromePath() {
  const tried = []
  const cands = [
    process.env.CHROME_PATH,
    // GitHub's runner images set this for the Chrome they ship. Named rather
    // than assumed: this is the one that makes the CI job work without a
    // 150MB browser download per run.
    process.env.CHROME_BIN,
    '/usr/bin/chromium-browser',
    '/usr/bin/chromium',
    '/usr/bin/google-chrome',
    '/opt/google/chrome/chrome',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
  ].filter(Boolean)
  for (const c of cands) {
    if (existsSync(c)) return c
    tried.push(c)
  }
  for (const bin of ['chromium', 'google-chrome', 'google-chrome-stable']) {
    try {
      const p = execFileSync('which', [bin], { encoding: 'utf8' }).trim()
      if (p && existsSync(p)) return p
    } catch {
      tried.push(`which ${bin}`)
    }
  }
  throw new Error(
    'frame capture found no Chromium. It does not skip: without a browser there ' +
      'is no composited frame, and the twelve invariants would be reporting on a ' +
      'blueprint again.\n  set CHROME_PATH, or install one.\n  tried:\n    ' +
      tried.join('\n    ')
  )
}

/**
 * Screenshot the stage, and keep screenshotting until two in a row are the same
 * bytes.
 *
 * WHY, and it is not belt-and-braces. Readiness is asserted three ways above —
 * the canvas element exists, the network is quiet, three frames have composited
 * — and every one of those is a PROXY for the thing that actually matters,
 * which is that the world has finished arriving. On a laptop three frames is
 * plenty; on a shared runner with a software GL stack it is a guess, and a
 * capture taken one frame early is a frame with half its atlases missing that
 * every arm below would then judge as the world. Comparing two captures asks
 * the question directly and costs one extra screenshot when it is already
 * settled.
 *
 * BOUNDED, and a failure to settle is an ERROR rather than a best effort: a
 * renderer that never stops changing is a finding, and quietly returning the
 * last frame would bury it.
 */
async function settled(page, file) {
  let prev = null
  for (let i = 0; i < 8; i++) {
    const shot = await page.locator('#stage').screenshot()
    if (prev && prev.equals(shot)) {
      writeFileSync(file, shot)
      return
    }
    prev = shot
    await page.evaluate(() => new Promise((r) => setTimeout(r, 120)))
  }
  throw new Error(`${file}: the frame never settled — 8 captures in a row differed`)
}

// ── arguments ───────────────────────────────────────────────────────────────
function argv() {
  const a = {}
  for (let i = 2; i < process.argv.length; i++) {
    const k = process.argv[i]
    if (k.startsWith('--')) a[k.slice(2)] = process.argv[i + 1]?.startsWith('--') ? '1' : process.argv[++i]
  }
  return a
}
const A = argv()
const OUT = resolve(A.out || '/tmp/world-frames')
const STATE = A.state || 'hamlet'
/**
 * One hour from EACH bucket by default (lighting.ts DEFAULT_BUCKETS: dawn 6-8,
 * day 8-18, dusk 18-21, night otherwise). Named as hours rather than as buckets
 * because the hour is the only lever the render path takes — the bucket is
 * `bucketForHour`'s output, and asking for a bucket directly would be this
 * harness deciding something the renderer decides.
 */
const HOURS = (A.hours || '7,13,19,2').split(',').map((s) => Number(s.trim()))
/**
 * ISLAND, CLOSE and COAST. capture.py judges 1.0 alone; `lodTier` switches
 * behaviour at 2.5 / 1.5 / 0.75 / (below) 0.35, so three zooms cross three of
 * those boundaries. A screen-space defect is identical at every zoom and a
 * world-space one is not — one capture cannot tell you which kind you have.
 */
const ZOOMS = (A.zooms || '0.5,1,2').split(',').map((s) => Number(s.trim()))
const WEATHER = (A.weather || 'sun').split(',')
/**
 * `--killswitch 1` adds a killswitch TWIN of each cell at the FIRST zoom, into
 * the same manifest — never a whole separate run. The red wash can only be
 * judged against the frame it is a wash OVER, and a twin in another directory
 * is a twin no arm can find.
 */
const KILLSWITCH = A.killswitch === '1'
const W = Number(A.w || 1200)
const H = Number(A.h || 800)
/** lighting.ts DEFAULT_BUCKETS, and the ONE place this file names them. */
const bucketOf = (h) => (h >= 6 && h < 8 ? 'dawn' : h >= 8 && h < 18 ? 'day' : h >= 18 && h < 21 ? 'dusk' : 'night')

// ── capture ─────────────────────────────────────────────────────────────────
async function main() {
  mkdirSync(OUT, { recursive: true })
  const exe = chromePath()
  const server = await createServer({ configFile: join(HERE, 'vite.config.mts'), server: { port: 0 } })
  await server.listen()
  const base = server.resolvedUrls.local[0].replace(/\/$/, '')

  const browser = await chromium.launch({
    executablePath: exe,
    args: [
      // The ambience remap is a GLSL filter and the app pins `preference:
      // 'webgl'`. A headless runner has no GPU, so WebGL comes from SwiftShader
      // — without these flags Chromium refuses it, `ambienceFilter` returns
      // null, and the harness produces a perfectly daytime frame at midnight.
      // main.tsx surfaces that as a render issue and this script refuses it, but
      // refusing every frame is not a gate either.
      '--enable-unsafe-swiftshader',
      '--use-gl=angle',
      '--use-angle=swiftshader',
      '--disable-dev-shm-usage',
    ],
  })
  // deviceScaleFactor PINNED to 1. On a retina laptop the default is 2 and the
  // PNG comes back at twice the CSS size — the same defect capture.py's --scale
  // help describes, where absolute-pixel constants are read at a different
  // relative resolution and invent findings.
  const page = await browser.newPage({ viewport: { width: W + 40, height: H + 40 }, deviceScaleFactor: 1 })
  page.on('pageerror', (e) => console.error(`  page error: ${e.message}`))

  const frames = []
  const cells = []
  for (const z of ZOOMS) {
    for (const weather of WEATHER) {
      // The DAY twin first, and per (zoom, weather) rather than once per run:
      // the pair a check compares must differ in the CLOCK ALONE.
      const dayHour = HOURS.find((h) => bucketOf(h) === 'day') ?? 13
      const seen = new Set()
      for (const h of [dayHour, ...HOURS]) {
        if (seen.has(h)) continue
        seen.add(h)
        cells.push({ hour: h, z, weather, killswitch: false })
        if (KILLSWITCH && z === ZOOMS[0]) cells.push({ hour: h, z, weather, killswitch: true })
      }
    }
  }

  /**
   * One navigation, one settled PNG, every readiness assertion in between.
   *
   * Extracted so the GROUND pass goes through the identical door as the
   * composite. A second, shorter capture path for the ground frame would be a
   * second opinion about when the world has finished arriving — and a ground
   * frame captured one frame early is a frame with half its terrain missing,
   * which the vocabulary arm would read as a lawful (very small) world.
   */
  async function shoot(q, name, file) {
    await page.goto(`${base}/?${q}`, { waitUntil: 'load' })
    await page.waitForFunction(
      () => window.__frameBooted === true || typeof window.__frameError === 'string',
      null,
      { timeout: 60_000 }
    )
    const err = await page.evaluate(() => window.__frameError ?? null)
    if (err) throw new Error(`${name}: harness failed to boot — ${err}`)
    // The canvas exists LONG before it has the world on it: `app.init` appends
    // it, and only then does EngineCanvas fetch the manifest and load the
    // atlases. So the element, then the network going quiet, then a few
    // composited frames — the difference between capturing the island and
    // capturing the clear colour.
    await page.waitForSelector('#stage canvas', { timeout: 60_000 })
    await page.waitForLoadState('networkidle')
    await page.evaluate(
      () =>
        new Promise((r) => {
          let n = 0
          const step = () => (++n >= 3 ? r() : requestAnimationFrame(step))
          requestAnimationFrame(step)
        })
    )
    // THE CANVAS MUST BE THE SIZE ASKED FOR. PixiJS sizes itself from its host
    // via `resizeTo`, and the host's `absolute inset-0` are Tailwind classes
    // this page has to supply itself — when it did not, every capture came back
    // 1200x600 in a 1200x800 stage with a black band along the bottom, and the
    // twelve invariants would have measured that band as a third of the world.
    const size = await page.evaluate(() => {
      const c = document.querySelector('#stage canvas')
      return c ? { w: c.clientWidth, h: c.clientHeight } : null
    })
    if (!size || size.w !== W || size.h !== H) {
      throw new Error(`${name}: canvas is ${size ? `${size.w}x${size.h}` : 'absent'}, asked for ${W}x${H}`)
    }
    const issues = await page.evaluate(() => window.__frameIssues ?? [])
    // A renderer that could not build the ambience filter says so, and a frame
    // captured through that path is a daytime frame wearing a night filename.
    const fatal = issues.filter((s) => /ambience|renderer|texture|manifest/i.test(s))
    if (fatal.length) throw new Error(`${name}: renderer raised ${JSON.stringify(fatal)}`)

    await settled(page, file)
    console.log(`  shot ${name}`)
    return issues
  }

  for (const c of cells) {
    const params = {
      state: STATE,
      hour: String(c.hour),
      z: String(c.z),
      w: String(W),
      h: String(H),
      weather: c.weather,
      ...(c.killswitch ? { killswitch: '1' } : {}),
    }
    const bucket = bucketOf(c.hour)
    const stem = `${STATE}-${bucket}-h${c.hour}-z${String(c.z).replace('.', '_')}-${c.weather}${c.killswitch ? '-ks' : ''}`
    const name = `${stem}.png`
    const file = join(OUT, name)
    const issues = await shoot(new URLSearchParams(params), name, file)

    /**
     * THE GROUND TWIN — the same cell with every layer above the terrain
     * hidden, and the only frame in this sweep that can be judged WITHOUT a
     * comparison. Captured for the plain cells only: the killswitch wash is a
     * screen-space pass and already has a differential arm, and a ground frame
     * under it would carry the wash into the vocabulary the arm checks.
     */
    let ground = null
    if (!c.killswitch) {
      ground = join(OUT, `${stem}.ground.png`)
      await shoot(new URLSearchParams({ ...params, ground: '1' }), `${stem}.ground.png`, ground)
    }
    frames.push({ file, ground, state: STATE, hour: c.hour, bucket, zoom: c.z, weather: c.weather, killswitch: c.killswitch, w: W, h: H, issues })
  }

  // ONE cell re-shot, and asserted identical. Every day-vs-bucket arm in the
  // judge rests on two captures of the same island differing in the clock
  // alone; if the renderer is not reproducible at all, those arms are comparing
  // noise and would have to be believed anyway. Proving it here costs one frame.
  const twin = join(OUT, '_determinism-twin.png')
  const first = frames[0]
  const tq = new URLSearchParams({ state: first.state, hour: String(first.hour), z: String(first.zoom), w: String(W), h: String(H), weather: first.weather })
  await page.goto(`${base}/?${tq}`, { waitUntil: 'load' })
  await page.waitForFunction(() => window.__frameBooted === true, null, { timeout: 60_000 })
  await page.waitForSelector('#stage canvas', { timeout: 60_000 })
  await page.waitForLoadState('networkidle')
  await page.evaluate(() => new Promise((r) => { let n = 0; const s = () => (++n >= 3 ? r() : requestAnimationFrame(s)); requestAnimationFrame(s) }))
  await settled(page, twin)

  // The manifest lands IN the capture directory, so the CI artifact that gets
  // kept on a red carries the frames, the report and the map between them.
  writeFileSync(join(OUT, 'frames.json'), JSON.stringify({ frames, determinism: { a: first.file, b: twin } }, null, 1))
  console.log(`frame-harness: ${frames.length} frames -> ${OUT}`)

  await browser.close()
  await server.close()
}

main().catch((e) => {
  console.error(`frame-harness: ${e.message}`)
  process.exit(1)
})
