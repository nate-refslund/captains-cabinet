/**
 * emit.ts — run composeLayout for a state fixture and write the bridge halves.
 *
 *   node --import ./resolve-ts.mjs emit.ts \
 *        --pack <world-pack.json> --state <states/hamlet.json> --out <dir>
 *
 * Writes <out>/blueprint.json (no `layers` — the rasteriser owns paint order),
 * <out>/draw.json and <out>/audit.json. Pure data in, pure data out: no pixels
 * are drawn here and no browser is involved, because the layout is a pure
 * function and the checks' blueprint needs nothing else.
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { composeFrame, type WorldPack } from '../../dashboard/src/lib/world/blueprint.ts'
import type { LayoutState } from '../../dashboard/src/lib/world/iso-layout/index.ts'

function arg(name: string, required = true): string {
  const k = process.argv.indexOf(`--${name}`)
  if (k < 0 || k + 1 >= process.argv.length) {
    if (required) throw new Error(`emit.ts: missing --${name}`)
    return ''
  }
  return process.argv[k + 1]
}

const pack = JSON.parse(readFileSync(arg('pack'), 'utf8')) as WorldPack
const fixture = JSON.parse(readFileSync(arg('state'), 'utf8')) as {
  name: string
  seed: string | number
  date: string
  index: number
  state: LayoutState
}
const out = arg('out')
mkdirSync(out, { recursive: true })

const frame = composeFrame(pack, fixture.state, fixture.seed, {
  date: fixture.date,
  index: fixture.index,
})

writeFileSync(`${out}/blueprint.json`, JSON.stringify(frame.blueprint, null, 1))
writeFileSync(`${out}/draw.json`, JSON.stringify(frame.draw))
writeFileSync(`${out}/audit.json`, JSON.stringify(frame.audit, null, 1))

const a = frame.audit
process.stdout.write(
  `emit ${fixture.name}: ${frame.blueprint.sprites.length} sprites, ` +
    `${Object.keys(frame.blueprint.lanes).length} lane runs, ` +
    `${frame.blueprint.fields.length} fields, ` +
    `justified ${frame.blueprint.state.justified.length}\n` +
    `audit: onLane ${a.onLane.length}, stacked ${a.stacked.length}, ` +
    `inWater ${a.inWater.length}, outsideHarbour ${a.outsideHarbour.length}, ` +
    // Printed, not just written to audit.json: an arm nobody reads on the way
    // past is an arm that goes red in a file. `beached` is the one that would
    // have caught the vessel drawn on the pier.
    `waterClaim ${a.waterClaim.length}, beached ${a.beached.length}\n`
)
