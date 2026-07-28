/**
 * live-state.ts — the ORG'S ACTUAL STATE as a world-capture fixture.
 *
 *   curl -s -H "Cookie: cabinet_session=$TOKEN" \
 *        http://localhost:3100/api/world/engine > /tmp/engine.json
 *   node --import ./resolve-ts.mjs live-state.ts \
 *        --engine /tmp/engine.json --out states/live.json
 *   python3.12 capture.py --state states/live.json
 *
 * WHY IT EXISTS. states/camp.json and states/hamlet.json are hand-authored, and
 * every rung in them is a real rung — but they are still two chosen points. The
 * question "does the world draw what the org IS today" had no offline answer at
 * all, and when it was finally asked (Captain, 2026-07-27) the live page was
 * drawing a CAMP island for a hamlet org and nothing on the frame said so. The
 * first capture from a real state also turned `check_on_road` red on two sprites
 * that both shipped fixtures leave green. A fixture set that cannot express
 * today is a battery that cannot fail on today.
 *
 * NOT A RE-IMPLEMENTATION. It runs the SAME engineStep the browser runs, seeded
 * the same way engine-client seeds it (evalPrev first, so the hysteresis holders
 * hold what they really hold), and the SAME layoutStateFrom the canvas composes
 * through. If any of those change, this changes with them.
 *
 * THE OUTPUT IS A SNAPSHOT AND SHOULD NOT BE COMMITTED. It is true on the day it
 * is taken and a lie a week later; regenerate it rather than keeping one. That
 * is why this file is the deliverable and states/live.json is not.
 *
 * TWO WAYS THE FEED IS EMPTY, both of which produce `eval: undefined` and, in
 * the browser, a silent CAMP island (see iso-scene.ts UNMEASURED_STATE_ISSUE):
 *   - no `cabinet_session` cookie: /api/world/engine 401s;
 *   - no shared/interfaces/world-chronicle.jsonl under CABINET_ROOT — it is a
 *     gitignored RUNTIME artifact, so a dev server in a fresh clone or a
 *     worktree has no keyframes. Start it with CABINET_ROOT=<live checkout>.
 * This script REFUSES rather than emitting a hatch fixture that looks measured.
 */
import { readFileSync, writeFileSync } from 'node:fs'
import {
  engineStep,
  initialEngineState,
  type EngineEval,
  type GrowthLaddersConfig,
} from '../../dashboard/src/lib/world/era-engine.ts'
import { layoutStateFrom } from '../../dashboard/src/lib/world/iso-scene.ts'

interface EnginePayload {
  ladders: { config: GrowthLaddersConfig | null }
  eval?: EngineEval
  evalPrev?: EngineEval
  todayISO?: string
}

function arg(name: string, fallback?: string): string {
  const k = process.argv.indexOf(`--${name}`)
  if (k < 0 || k + 1 >= process.argv.length) {
    if (fallback !== undefined) return fallback
    throw new Error(`live-state.ts: missing --${name}`)
  }
  return process.argv[k + 1]
}

const payload = JSON.parse(readFileSync(arg('engine'), 'utf8')) as EnginePayload
if (!payload?.ladders?.config || !payload?.eval) {
  throw new Error(
    'live-state.ts: the payload carries no ladders config or no eval. ' +
      'That is the same empty feed the live page renders as a camp island — ' +
      'check the cabinet_session cookie and CABINET_ROOT rather than proceeding.'
  )
}

let engine = initialEngineState()
if (payload.evalPrev) engine = engineStep(engine, payload.evalPrev, payload.ladders.config).state
const resolution = engineStep(engine, payload.eval, payload.ladders.config).out
const state = layoutStateFrom(resolution)

writeFileSync(
  arg('out'),
  JSON.stringify(
    {
      name: 'live',
      seed: arg('seed', 'cabinet-world'),
      date: payload.todayISO ?? new Date().toISOString().slice(0, 10),
      index: resolution.eraIndex,
      state,
    },
    null,
    1
  )
)

process.stdout.write(
  `live: era=${resolution.era} index=${resolution.eraIndex.toFixed(3)} road=${state.road} ` +
    `dwellings=${state.counts?.officer_dwellings ?? 0} berths=${state.counts?.berths ?? 0} ` +
    `posts=${state.counts?.lantern_posts ?? 0}/${state.counts?.posts_lit ?? 0} lit ` +
    `lamp=${state.stages?.lighthouse_lamp ?? 'none'}\n`
)
