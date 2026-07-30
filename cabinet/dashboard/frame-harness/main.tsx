/**
 * main.tsx — mount the REAL EngineCanvas, with every input that decides a
 * screen-space pass pinned on the query string.
 *
 * WHY THIS EXISTS. `cabinet/scripts/world-capture/capture.py` judges a frame
 * that `raster.py` DRAWS from `composeLayout`'s blueprint. That pipeline has no
 * clock, no day bucket and no PIXI stage, so every pass the browser composites
 * on top of the world — the ambience remap, the weather layer, the killswitch
 * wash, the glow — sits outside all twelve invariants at every zoom. On
 * 2026-07-29 a dusk veil replaced 15.6% of every pixel in the frame and every
 * arm stayed green; the Captain found it by looking. A check that judges a
 * RE-DERIVATION of the render is testing the model, not the product.
 *
 * WHAT THIS IS AND IS NOT. It is not a second renderer. It imports
 * `components/world/engine-canvas` — the shipped component, its shipped PixiJS
 * boot, its shipped GLSL ambience filter — and hands it props. The only thing
 * stubbed is the DATA, which is exactly what `states/*.json` already stubs for
 * the blueprint path, from the same fixture files.
 *
 * IT IS NOT A ROUTE. Deliberately: a `?probe=1` door inside `/world` would be a
 * product surface with a test's blast radius, and the one input that has to be
 * forced here — the clock — is server-stamped data in the product on purpose.
 * This bundle is built by vite at capture time and never enters `next build`
 * (Next builds `src/app`; nothing imports this file).
 *
 * DETERMINISM IS THE POINT, not a nicety. The veil lived three hours a day and
 * was invisible for exactly that reason. `hour` here is the whole clock: it
 * feeds `clockHour`, which `bucketForHour` turns into the bucket, which selects
 * the ambience LUT. A capture whose bucket is whatever hour CI happens to run
 * at is a flaky sensor, not a sensor. Everything else that could move between
 * two runs is pinned to a literal below (tick, weather, life, cutaway, officer
 * presence) so that two captures of the same URL are comparable pixel for
 * pixel — which is what the day-vs-bucket arms in frame-judge.py rest on.
 *
 * QUERY STRING, all of it deliberate:
 *   state=hamlet|camp   which states/<name>.json to resolve the island from
 *   hour=0..23          Captain-local hour -> dawn 6-8 / day 8-18 / dusk 18-21 / night
 *   z=<float>           camera zoom, the axis the harness docstring admits it never varied
 *   w,h=<int>           canvas size, fixed so two captures are the same raster
 *   weather=sun|...     the weather layer, which is also outside the twelve
 *   killswitch=1        the red wash, likewise
 *   iso=0               the top-down kernel, for the bake-off path
 *   ground=1            the GROUND ALONE — sea, terrain, shore; every layer
 *                       above them hidden. The one frame in this harness whose
 *                       tone vocabulary is closed, and therefore the only one
 *                       that can be judged without a twin. Every other arm here
 *                       compares a frame with its day twin, and a twin carries a
 *                       CONTENT defect exactly as the frame does.
 */
// NO StrictMode, and that is not laziness. StrictMode double-invokes effects in
// development, and this canvas boots PixiJS in one — two boots race a destroy
// against an `await app.init`, and the frame you capture is whichever won. The
// product mounts it once; so does this.
import { createRoot } from 'react-dom/client'
import EngineCanvas from '@/components/world/engine-canvas'
import { buildWorldGeo } from '@/lib/world/world-geo'
import { buildWorldBuildings } from '@/lib/world/world-buildings'
import { cameraHome } from '@/lib/world/iso-scene'
import { initialCutaway } from '@/lib/world/lod'
import { initialWeather, type WeatherKind, type WeatherState } from '@/lib/world/weather'
import type { WorldResolution, ElementResolution } from '@/lib/world/era-engine'
import type { ProjectionKind } from '@/lib/world/projection'

/** The fixture shape both capture paths read. Same files, same island. */
interface Fixture {
  name: string
  seed: string
  date: string
  index: number
  state: {
    era: string
    road: string
    stages: Record<string, string>
    counts: Record<string, number>
  }
}

/**
 * The fixture's LayoutState, back through the door the engine actually reads.
 *
 * `iso-scene.layoutStateFrom(resolution)` is what EngineCanvas calls, and it
 * takes exactly two fields off each element: `rungName` and `rung`. The fixture
 * carries both, under `stages` and `counts`. So this is an INVERSE of the live
 * path's own projection, not a second opinion about it: whatever
 * `layoutStateFrom` does with these two fields is what the frame will show, and
 * if it ever reads a third the frames go wrong LOUDLY (the island changes)
 * rather than quietly.
 *
 * The remaining ElementResolution fields are the inspect card's, not the
 * renderer's. `measured: true` is the honest value for a fixture that names a
 * real rung — `false` is the renderer's "no measurement yet", and claiming that
 * would draw the unmeasured path.
 */
function resolutionFrom(f: Fixture): WorldResolution {
  const elements: Record<string, ElementResolution> = {}
  for (const [name, rungName] of Object.entries(f.state.stages)) {
    elements[name] = {
      rung: f.state.counts[name] ?? 0,
      rungName,
      vocab: null,
      pending: null,
      measured: true,
      value: null,
    }
  }
  return {
    era: f.state.era,
    eraIndex: f.index,
    eraUnmeasured: [],
    transition: null,
    elements,
    lanes: {},
  }
}

function num(p: URLSearchParams, k: string, d: number): number {
  const v = Number(p.get(k))
  return Number.isFinite(v) ? v : d
}

/**
 * THE SAME FIXTURE FILES THE BLUEPRINT PATH READS, bundled rather than fetched.
 *
 * `import.meta.glob` resolves at build time, so the set is whatever is on disk
 * — a fixture added for the blueprint path is capturable here with no edit, and
 * one deleted breaks the build instead of 404-ing into an empty island at
 * capture time. Two harnesses reading two copies of "what a hamlet is" is the
 * defect this whole directory exists about, one level up.
 */
const FIXTURES = import.meta.glob('../../scripts/world-capture/states/*.json', {
  eager: true,
  import: 'default',
}) as Record<string, Fixture>

function fixture(name: string): Fixture {
  for (const [path, f] of Object.entries(FIXTURES)) {
    if (path.endsWith(`/${name}.json`)) return f
  }
  throw new Error(`no state fixture '${name}' — have ${Object.keys(FIXTURES).join(', ')}`)
}

async function boot() {
  const p = new URLSearchParams(window.location.search)
  const f = fixture(p.get('state') || 'hamlet')

  const projection: ProjectionKind = p.get('iso') === '0' ? 'topdown' : 'iso'
  const resolution = resolutionFrom(f)
  // PINNED, not defaulted. buildWorldGeo is pure in its input, so a literal
  // here is a fixed island; reading it from anywhere live would make the
  // harness's frames a function of the deployment.
  const geo = buildWorldGeo({ orgEventsTotal: 0, lanes: {}, berths: [], probeWiredLanes: [] })
  const buildings = buildWorldBuildings(resolution, geo)

  const hourRaw = p.get('hour')
  const clockHour = hourRaw === null || hourRaw === '' ? null : ((num(p, 'hour', 12) % 24) + 24) % 24
  const weather: WeatherState = {
    ...initialWeather(),
    kind: (p.get('weather') || 'sun') as WeatherKind,
    why: 'frame-harness: pinned',
  }

  const w = Math.max(64, Math.round(num(p, 'w', 1200)))
  const h = Math.max(64, Math.round(num(p, 'h', 800)))
  const host = document.getElementById('stage') as HTMLDivElement
  host.style.width = `${w}px`
  host.style.height = `${h}px`

  createRoot(host).render(
    <EngineCanvas
        projection={projection}
        geo={geo}
        buildings={buildings}
        resolution={resolution}
        officers={{}}
        life={null}
        camera={{ z: num(p, 'z', 1), ...cameraHome(projection) }}
        cutaway={initialCutaway()}
        weather={weather}
        tick={0}
        killswitch={p.get('killswitch') === '1'}
        groundOnly={p.get('ground') === '1'}
        clockHour={clockHour}
        chartTable={false}
        courses={null}
        voyage={null}
        onPrimary={() => {}}
        onSecondary={() => {}}
        onIssues={(issues) => {
          // NOT swallowed. `ambienceFilter` returns null on a renderer with no
          // WebGL and the canvas raises it here — which, on a headless runner
          // falling back to a software path that cannot compile the shader,
          // would produce a perfectly daytime frame at midnight and a green
          // report about it. The driver reads this and refuses the capture.
          ;(window as unknown as { __frameIssues: string[] }).__frameIssues = issues
        }}
      />
  )
}

boot().then(
  () => {
    ;(window as unknown as { __frameBooted: boolean }).__frameBooted = true
  },
  (err: unknown) => {
    // A harness that fails silently reports a blank frame as a lawful one.
    ;(window as unknown as { __frameError: string }).__frameError =
      err instanceof Error ? err.message : String(err)
  }
)
