/**
 * Cabinet World CI ratchets — land AT route creation, not later (chassis
 * consensus graft; kickoff step 3 "CI ratchets at route creation").
 *
 * These greps are the mechanical form of the doctrine:
 *  1. NO write server-actions DECLARED anywhere under the world trees
 *     ('use server') — and, per the Captain ruling 2026-07-09 (killswitch
 *     lever = the ONE in-world actuator), EXACTLY ONE world file
 *     (components/world/killswitch-lever.tsx) may IMPORT a server action,
 *     and only the existing killswitch one. Every other world file stays
 *     action-free (test 1b).
 *  2. NO POST/PUT/PATCH/DELETE exports from /api/world routes (GET-only —
 *     the world never grows a write path; the lever rides the pre-existing
 *     dashboard action, not a world route).
 *  3. Text-only rendering: no dangerouslySetInnerHTML / innerHTML /
 *     insertAdjacentHTML in world components.
 *  4. Determinism: no Math.random / Date.now in the render path
 *     (lib/world + components/world). Seeded hashes + the logical tick are
 *     the only variation sources.
 *  5. CSP header pinned for /world in next.config.ts.
 *  6. Opaque handles: the URL layer never writes a raw officer slug param.
 *  7. Auth gate cloned on the /api/world routes.
 *  8. CSP stays eval-free: PixiJS compat comes from the official
 *     'pixi.js/unsafe-eval' PATCH import (+ workers off), never from
 *     widening script-src. Root cause of the 2026-07-08 black-canvas
 *     incident — pixi's init threw on the eval check and nothing surfaced.
 *  9. Loud-failure surfaces exist: renderer boot/manifest/texture problems
 *     must console.error AND badge in DOM (silent-black is a regression
 *     class, never a cosmetic nit).
 */
import { describe, expect, it } from 'vitest'
import fs from 'fs'
import path from 'path'

const DASH = path.resolve(__dirname, '..', '..', '..')

const WORLD_COMPONENTS = path.join(DASH, 'src', 'components', 'world')

/**
 * The pixi renderers and world shells, DERIVED from the tree rather than typed.
 *
 * A filename ratchet is only as good as its list. Until 2026-07-29 these were
 * literals naming three renderers and two shells; the legacy three-scene shell
 * was deleted that day, and a hardcoded list would have gone on "passing" over
 * two files that no longer exist — the vacuous-green class this repo keeps
 * paying for. Deriving them means adding a renderer opts it IN automatically,
 * and the floor assertions below mean deleting them all cannot report green.
 */
const WORLD_FILES = fs
  .readdirSync(WORLD_COMPONENTS)
  .filter((f) => /\.tsx$/.test(f))
  .sort()
const PIXI_RENDERERS = WORLD_FILES.filter((f) =>
  fs.readFileSync(path.join(WORLD_COMPONENTS, f), 'utf8').includes("from 'pixi.js'")
)
const WORLD_SHELLS = WORLD_FILES.filter((f) => /-client\.tsx$/.test(f))
const WORLD_TREES = [
  path.join(DASH, 'src', 'lib', 'world'),
  path.join(DASH, 'src', 'components', 'world'),
  path.join(DASH, 'src', 'app', 'api', 'world'),
  path.join(DASH, 'src', 'app', '(authenticated)', 'world'),
]

function collectSources(dir: string): string[] {
  if (!fs.existsSync(dir)) return []
  const out: string[] = []
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name)
    if (entry.isDirectory()) out.push(...collectSources(p))
    else if (/\.(ts|tsx)$/.test(entry.name) && !entry.name.endsWith('.test.ts'))
      out.push(p)
  }
  return out
}

const sources = WORLD_TREES.flatMap(collectSources)
const read = (p: string) => fs.readFileSync(p, 'utf8')

describe('world CI ratchets', () => {
  it('world trees exist and are non-empty', () => {
    expect(sources.length).toBeGreaterThan(4)
  })

  it('1. no server actions declared under any world tree', () => {
    for (const p of sources) {
      expect(read(p), p).not.toMatch(/['"]use server['"]/)
    }
  })

  it('1b. ONE-actuator carve-out: only killswitch-lever.tsx imports a server action', () => {
    // Captain ruling 2026-07-09: the killswitch lever is the single
    // in-world actuator (two-tap + confirm + captain cookie), wired to the
    // PRE-EXISTING dashboard killswitch action. This ratchet pins the
    // carve-out to exactly that one file and exactly that one action —
    // any second '@/actions/' import in the world trees is a regression.
    const offenders: string[] = []
    for (const p of sources) {
      if (!/@\/actions\//.test(read(p))) continue
      offenders.push(p)
    }
    expect(offenders.map((p) => path.basename(p))).toEqual(['killswitch-lever.tsx'])
    const lever = read(
      path.join(DASH, 'src', 'components', 'world', 'killswitch-lever.tsx')
    )
    // Only the killswitch action, nothing else, and no broadened imports.
    expect(lever.match(/@\/actions\/[\w-]+/g)).toEqual(['@/actions/killswitch'])
  })

  it('2. /api/world routes are GET-only (no write verbs exported)', () => {
    const apiSources = sources.filter((p) =>
      p.includes(path.join('app', 'api', 'world'))
    )
    expect(apiSources.length).toBeGreaterThan(0)
    for (const p of apiSources) {
      const text = read(p)
      expect(text, p).not.toMatch(
        /export\s+(async\s+)?function\s+(POST|PUT|PATCH|DELETE)/
      )
      expect(text, p).toMatch(/export\s+async\s+function\s+GET/)
    }
  })

  it('3. text-only rendering — no HTML injection surfaces', () => {
    for (const p of sources) {
      const text = read(p)
      expect(text, p).not.toMatch(/dangerouslySetInnerHTML/)
      expect(text, p).not.toMatch(/\binnerHTML\s*=/)
      expect(text, p).not.toMatch(/insertAdjacentHTML/)
      expect(text, p).not.toMatch(/document\.write/)
    }
  })

  it('4. determinism — no Math.random / Date.now in the render path', () => {
    const renderPath = sources.filter(
      (p) =>
        p.includes(path.join('lib', 'world')) ||
        p.includes(path.join('components', 'world'))
    )
    expect(renderPath.length).toBeGreaterThan(3)
    for (const p of renderPath) {
      const text = read(p)
      expect(text, p).not.toMatch(/Math\.random\s*\(/)
      expect(text, p).not.toMatch(/Date\.now\s*\(/)
    }
  })

  it('5. CSP header for /world pinned in next.config.ts', () => {
    const cfg = read(path.join(DASH, 'next.config.ts'))
    expect(cfg).toMatch(/source:\s*['"]\/world['"]/)
    expect(cfg).toMatch(/Content-Security-Policy/)
    expect(cfg).toMatch(/frame-ancestors 'none'/)
    expect(cfg).toMatch(/default-src 'self'/)
  })

  it('6. URL layer writes opaque sel handles, never slug params', () => {
    // Every shell, not one named one: this read `world-client.tsx` until
    // 2026-07-29, and that file is now deleted — a ratchet pointed at a deleted
    // file does not fail, it throws or (worse, if guarded) passes over nothing.
    expect(WORLD_SHELLS.length).toBeGreaterThan(0)
    for (const name of WORLD_SHELLS) {
      const client = read(path.join(WORLD_COMPONENTS, name))
      // The only sel writes must come from the server-issued handle field.
      expect(client, name).not.toMatch(/set\(['"]slug['"]/)
      expect(client, name).not.toMatch(/[?&]slug=/)
    }
    // And the stream route must issue hashed handles.
    const route = read(
      path.join(DASH, 'src', 'app', 'api', 'world', 'stream', 'route.ts')
    )
    expect(route).toMatch(/selHandle/)
    expect(route).toMatch(/sha256/)
  })

  it('7. EVERY /api/world route carries the auth gate (cookie check + 401)', () => {
    // v1a review fix: ratchets land AT route creation — this walks ALL
    // route.ts files under app/api/world (like ratchet #2), so a new route
    // can never ship (or lose) the gate unpinned.
    const apiRoutes = sources.filter(
      (p) =>
        p.includes(path.join('app', 'api', 'world')) && path.basename(p) === 'route.ts'
    )
    expect(apiRoutes.length).toBeGreaterThanOrEqual(5) // stream/grammar/engine/rail/mailbox
    for (const p of apiRoutes) {
      const text = read(p)
      expect(text, p).toMatch(/cabinet_session/)
      expect(text, p).toMatch(/401/)
    }
  })

  it("8. CSP stays eval-free — pixi ships the unsafe-eval PATCH, the header never widens", () => {
    // The header side: /world's script-src must never gain 'unsafe-eval'
    // (or a blob: worker escape hatch). PixiJS v8 compiles uniform-sync via
    // dynamically generated functions unless patched; the sanctioned
    // mechanism is the official AOT patch module, imported before init.
    // (Assert on the header VALUE block — the comment above it documents
    // the patch module by name.)
    const cfg = read(path.join(DASH, 'next.config.ts'))
    const valueBlock = cfg.match(/value:\s*\[([\s\S]*?)\]/)?.[1] ?? ''
    expect(valueBlock).toContain("default-src 'self'")
    expect(valueBlock).not.toMatch(/unsafe-eval/)
    expect(valueBlock).not.toMatch(/worker-src/)
    // The renderer side: the patch import + workers disabled must be
    // present in EVERY pixi renderer, or the canvas boots black under the
    // pinned header (2026-07-08 incident; engine-canvas pinned per v1a).
    // The list was ['world-canvas.tsx','outdoor-canvas.tsx','engine-canvas.tsx']
    // until 2026-07-29, when the legacy three-scene shell was deleted; a
    // filename ratchet left pointing at a deleted file passes VACUOUSLY, which
    // is why the array is edited in the same commit as the deletion. There is
    // exactly one pixi renderer in the tree now, and PIXI_RENDERERS below is
    // asserted to be that whole set rather than a hand-kept list.
    for (const name of PIXI_RENDERERS) {
      const canvas = read(path.join(DASH, 'src', 'components', 'world', name))
      expect(canvas, name).toMatch(/import\(\s*['"]pixi\.js\/unsafe-eval['"]\s*\)/)
      expect(canvas, name).toMatch(/preferWorkers:\s*false/)
    }
  })

  it('9. silent-black is ratcheted: failures console.error AND badge in DOM', () => {
    // The loud-failure contract extends to EVERY canvas/asset class
    // (world-alive §0): the Wardroom renderer, the outdoor renderer AND
    // the T1 continuous-world engine (v1a review fix: engine-canvas was
    // compliant but unpinned — the 2026-07-08 silent-black regression
    // class could have returned in the new renderer unnoticed).
    for (const name of PIXI_RENDERERS) {
      const canvas = read(path.join(DASH, 'src', 'components', 'world', name))
      // Boot rejection + manifest/texture gaps must be loud…
      expect(canvas, name).toMatch(/console\.error\(/)
      expect(canvas, name).toMatch(/onIssues/)
      expect(canvas, name).toMatch(/boot\(\)\.catch/)
      // …and stay CSP-safe (AOT patch import, workers off — ratchet #8).
      expect(canvas, name).toMatch(/import\(\s*['"]pixi\.js\/unsafe-eval['"]\s*\)/)
      expect(canvas, name).toMatch(/preferWorkers:\s*false/)
    }
    // …and the shell must render them as a visible DOM badge. Two shells until
    // 2026-07-29; the legacy one is deleted and WORLD_SHELLS is derived, not
    // typed, so this cannot silently shrink to zero.
    for (const name of WORLD_SHELLS) {
      const client = read(path.join(DASH, 'src', 'components', 'world', name))
      expect(client, name).toMatch(/data-world-issues/)
      expect(client, name).toMatch(/onIssues=/)
      // Census absence badges too (growth surfaces at day-0 — §4 data path).
      expect(client, name).toMatch(/data-world-census-badge/)
    }
  })
  it('10. ONE tile size in the ENGINE path — no sixth copy of the transform', () => {
    // The world→screen transform existed FIVE times and disagreed with itself
    // (engine-canvas camera, engine-canvas hit-test, engine-client pan,
    // engine-client DOM-label project, lod.ts's private TILE_PX). They now go
    // through lib/world/projection.ts. This is the ratchet that stops a sixth
    // appearing while the iso port is being written: no file on the engine path
    // may declare a tile constant of its own, and none may import the legacy
    // wardroom TILE.
    //
    // The LEGACY three-scene shell used to be out of scope here because it
    // still spoke the wardroom layout's tile; it was deleted 2026-07-29, so
    // there is no longer an exempt renderer in the tree.
    const ENGINE_PATH = [
      path.join(DASH, 'src', 'components', 'world', 'engine-canvas.tsx'),
      path.join(DASH, 'src', 'components', 'world', 'engine-client.tsx'),
      path.join(DASH, 'src', 'lib', 'world', 'lod.ts'),
      path.join(DASH, 'src', 'lib', 'world', 'iso-scene.ts'),
      path.join(DASH, 'src', 'lib', 'world', 'iso-pack.ts'),
    ]
    for (const file of ENGINE_PATH) {
      const src = read(file)
      const name = path.basename(file)
      expect(src, `${name} declares its own tile constant`).not.toMatch(
        /(const|let)\s+(TILE|TILE_PX|TILE_SIZE)\s*=/
      )
      expect(src, `${name} imports the legacy wardroom TILE`).not.toMatch(
        /import\s*\{[^}]*\bTILE\b[^}]*\}\s*from\s*['"][^'"]*world\/layout['"]/
      )
    }
    // …and the kernel module really is where the constants live.
    const proj = read(path.join(DASH, 'src', 'lib', 'world', 'projection.ts'))
    expect(proj).toMatch(/export const TOPDOWN_TILE/)
    expect(proj).toMatch(/export const ISO_TILE/)
  })
})

describe('the ratchet lists themselves', () => {
  /**
   * A DERIVED list can still go empty, and an empty for-loop passes every
   * assertion inside it. These two arms are the floor under ratchets 8, 9 and
   * 10: they fail if the world ever has no pixi renderer or no shell to gate,
   * which is exactly the state a careless deletion would leave behind.
   */
  it('there is at least one pixi renderer, and it is the engine canvas', () => {
    expect(PIXI_RENDERERS.length).toBeGreaterThan(0)
    expect(PIXI_RENDERERS).toContain('engine-canvas.tsx')
  })

  it('there is at least one world shell, and it is the engine client', () => {
    expect(WORLD_SHELLS.length).toBeGreaterThan(0)
    expect(WORLD_SHELLS).toContain('engine-client.tsx')
  })

  /**
   * And the legacy shell is GONE, asserted by absence rather than assumed.
   * `?legacy=1` was a live URL until 2026-07-29; a stray re-add would restore a
   * third renderer nobody is maintaining, on a code path with no bake-off left
   * to justify it.
   */
  it('the legacy three-scene shell does not come back', () => {
    for (const gone of ['world-client.tsx', 'world-canvas.tsx', 'outdoor-canvas.tsx']) {
      expect(fs.existsSync(path.join(WORLD_COMPONENTS, gone)), gone).toBe(false)
    }
    const page = read(path.join(DASH, 'src', 'app', '(authenticated)', 'world', 'page.tsx'))
    expect(page).not.toMatch(/params\.legacy/)
    expect(page).not.toMatch(/WorldClient/)
  })
})
