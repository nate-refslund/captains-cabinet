/**
 * T3 UI-layer static contracts (vitest, node env — same grep-ratchet style
 * as lib/world/ratchets.test.ts, which owns the tree-wide rules; this suite
 * pins the T3-specific ones):
 *
 *  A. MAILBOX READ-ONLY: the decision-queue view issues plain GET fetches
 *     only — no request method options, no server-action imports, no Redis
 *     write verbs in its route (Captain ruling 2026-07-09: mailbox renders
 *     + deep-links, never actuates).
 *  B. RAIL READ-ONLY: same contract for the portrait rail + its route.
 *  C. CARD COVERAGE: the inspect card derives its tab set from the shared
 *     tabsFor contract (WHAT/NOW/PROOF bound · WHAT-only decorative) and
 *     wears the pixel frame.
 *  D. LEVER CEREMONY: the lever uses the tick-driven two-tap machine, pins
 *     actuation behind canActuate, and prints the honest CLI fallback.
 *  E. LIMEZU CREDIT: both world shells render the LimeZu art credit in the
 *     always-on bottom bar (Captain-ratified license condition, 2026-07-12) —
 *     plain text, never behind the legend toggle — and render it ONLY where
 *     LimeZu pixels are measured on screen (2026-07-28: the owned cast made
 *     "always visible" a false claim about our own art).
 */
import { describe, expect, it } from 'vitest'
import fs from 'fs'
import path from 'path'

const DASH = path.resolve(__dirname, '..', '..', '..')
const src = (...rel: string[]) =>
  fs.readFileSync(path.join(DASH, 'src', ...rel), 'utf8')

const MAILBOX_CARD = ['components', 'world', 'decision-queue-card.tsx']
const RAIL = ['components', 'world', 'portrait-rail.tsx']
const FRAME = ['components', 'world', 'pixel-frame.tsx']
const CARD = ['components', 'world', 'inspect-card.tsx']
const LEVER = ['components', 'world', 'killswitch-lever.tsx']
const MAILBOX_ROUTE = ['app', 'api', 'world', 'mailbox', 'route.ts']
const RAIL_ROUTE = ['app', 'api', 'world', 'rail', 'route.ts']

/** fetch(...) calls must be single-argument (no init object → plain GET). */
function assertPlainGetFetches(text: string, name: string) {
  const calls = text.match(/fetch\(([^)]*)\)/g) ?? []
  expect(calls.length, `${name} should fetch something`).toBeGreaterThan(0)
  for (const call of calls) {
    expect(call, `${name}: ${call}`).not.toMatch(/,/) // no init arg at all
  }
  expect(text, name).not.toMatch(/method\s*:/i)
  expect(text, name).not.toMatch(/@\/actions\//)
  expect(text, name).not.toMatch(/['"]use server['"]/)
}

describe('A+B. mailbox + rail are read-only by construction', () => {
  it('decision-queue-card.tsx: GET-only fetches, no actions, no mutation', () => {
    assertPlainGetFetches(src(...MAILBOX_CARD), 'decision-queue-card')
  })
  it('portrait-rail.tsx: GET-only fetches, no actions, no mutation', () => {
    assertPlainGetFetches(src(...RAIL), 'portrait-rail')
  })
  it('pixel-frame.tsx: GET-only manifest fetch, no actions', () => {
    assertPlainGetFetches(src(...FRAME), 'pixel-frame')
  })
  it('mailbox + rail routes export GET only and never write Redis', () => {
    for (const [name, rel] of [
      ['mailbox', MAILBOX_ROUTE],
      ['rail', RAIL_ROUTE],
    ] as const) {
      const text = src(...rel)
      expect(text, name).toMatch(/export\s+async\s+function\s+GET/)
      expect(text, name).not.toMatch(
        /export\s+(async\s+)?function\s+(POST|PUT|PATCH|DELETE)/
      )
      // Redis surface is read-only: no write/expiry verbs anywhere.
      expect(text, name).not.toMatch(
        /\.(set|del|hset|hdel|xadd|lpush|rpush|sadd|incr|decr|expire|persist)\(/i
      )
      // Auth gate cloned (ratchet #7 pattern extends to every new route).
      expect(text, name).toMatch(/cabinet_session/)
      expect(text, name).toMatch(/401/)
    }
  })
  it('the mailbox card carries the deep-link/honest-channel block', () => {
    const text = src(...MAILBOX_CARD)
    expect(text).toMatch(/queueHref/)
    expect(text).toMatch(/Telegram binder/)
    expect(text).toMatch(/cabinet:action:\*/)
  })
})

describe('C. inspect-card coverage contract + pixel frame', () => {
  it('card derives tabs from the shared tabsFor contract', () => {
    const text = src(...CARD)
    expect(text).toMatch(/tabsFor\(/)
    expect(text).toMatch(/from '@\/lib\/world\/ui-cards'/)
  })
  it('card renders inside the pixel frame (shell swap, contract intact)', () => {
    const text = src(...CARD)
    expect(text).toMatch(/<PixelFrame/)
    // The honesty contract's load-bearing strings survive the re-skin.
    expect(text).toMatch(/decorative — carries no data/)
    expect(text).toMatch(/codex pending/)
  })
  it('frame resolves ONLY through manifest rows (no hand-built asset URLs)', () => {
    const text = src(...FRAME)
    expect(text).toMatch(/manifest\.json/)
    expect(text).toMatch(/frame_interim/)
    // Loud fallback exists (placeholder doctrine, never silent-broken).
    expect(text).toMatch(/data-frame=/)
  })
})

describe('D. killswitch lever ceremony', () => {
  it('lever rides the tick-driven two-tap machine (no wall clock)', () => {
    const text = src(...LEVER)
    expect(text).toMatch(/leverReduce/)
    expect(text).toMatch(/from '@\/lib\/world\/lever'/)
    expect(text).not.toMatch(/Date\.now\s*\(/)
    expect(text).not.toMatch(/Math\.random\s*\(/)
  })
  it('actuation is cookie-gated and intent-pinned — NEVER derived from a guess', () => {
    const text = src(...LEVER)
    expect(text).toMatch(/disabled=\{!canActuate\}/)
    // The intent used to be `active ? 'deactivate' : 'activate'`, which under
    // an UNKNOWN reading picks a direction out of the guess the reading does
    // not have. It now comes from `intentFor`, which returns null for unknown,
    // and the dialog asks. This grep is a spelling check, not the behaviour
    // test — that lives in lib/world/killswitch.test.ts and the surfaces suite.
    expect(text).toMatch(/toggleKillSwitch\(intent\)/)
    expect(text).not.toMatch(/active \? 'deactivate' : 'activate'/)
    expect(text).toMatch(/intentFor/)
  })
  it('failure prints the exact CLI fallback (honest degradation)', () => {
    expect(src(...LEVER)).toMatch(/fallbackCommandFor\(/)
  })
  it('the lever takes a three-state reading, never a boolean', () => {
    const text = src(...LEVER)
    // A boolean prop has nowhere to put "nobody could read it", and `?? false`
    // then files it under "verified not engaged" — the whole defect.
    expect(text).toMatch(/state: KillswitchGlance/)
    expect(text).not.toMatch(/active: boolean/)
    expect(text).toMatch(/killswitchWord\(state\)/)
  })
  it('consequence copy states next-tool-invocation semantics verbatim', () => {
    expect(src(...LEVER)).toMatch(
      /halt on their next tool invocation — not instantly/
    )
  })
})

describe('E. LimeZu art credit (ratified license condition, 2026-07-12)', () => {
  /**
   * ONE shell since 2026-07-29. This was a two-row list until the legacy
   * three-scene shell was deleted; the second row named a file that no longer
   * exists, and a list of filenames is only a sensor while every filename in it
   * is real. The credit assertion itself is UNCHANGED and deliberately so — the
   * resolution to "the iso pack is owned art" is ADDITIVE, never the deletion
   * of a licence line. LimeZu pixels remain on /world under both projections
   * (the portrait rail's portraits are LimeZu-derived, and the rail is chrome
   * that mounts under either kernel), so the line is still owed and still
   * asserted. What decides whether it RENDERS is credit.ts, measured from the
   * manifest's own licence column over what each mounted surface binds.
   */
  const SHELLS = [['engine-client', ['components', 'world', 'engine-client.tsx']]] as const
  it('every world shell carries the exact credit line', () => {
    for (const [name, rel] of SHELLS) {
      const text = src(...rel)
      expect(text, name).toMatch(/data-world-credit/)
      expect(text, name).toMatch(/Art: LimeZu — limezu\.itch\.io/)
    }
  })
  /**
   * SHOWN WHERE IT IS OWED, ABSENT WHERE IT IS NOT (2026-07-28). The line used
   * to render unconditionally, and this suite pinned it that way — which was
   * correct while every frame was LimeZu and became false attribution of our
   * own art the day the cast flipped to the owned sheets under iso.
   *
   * This arm is STATIC (the suite runs in node with no DOM), so it pins the
   * WIRING: the decision comes from lib/world/credit.ts and the span is inside
   * a conditional on its result. The DECISION itself — shown/absent, in both
   * directions, against the real manifest — is tested behaviourally in
   * lib/world/credit.test.ts. Splitting it that way is deliberate: a grep can
   * prove the shell asks the predicate, and only the predicate's own suite can
   * prove the predicate answers correctly.
   */
  it('the credit is CONDITIONAL on measured LimeZu art, in every shell', () => {
    for (const [name, rel] of SHELLS) {
      const text = src(...rel)
      // asks the one authority…
      expect(text, name).toMatch(/from '@\/lib\/world\/credit'/)
      expect(text, name).toMatch(/limezuSurfaces\(/)
      // …and renders the span only when it answers yes
      expect(text, name).toMatch(/\{creditSurfaces\.length > 0 && \(/)
      const gateAt = text.indexOf('{creditSurfaces.length > 0 && (')
      const creditAt = text.indexOf('data-world-credit')
      expect(gateAt, name).toBeGreaterThan(-1)
      expect(gateAt, name).toBeLessThan(creditAt)
      // the surfaces are named on the element, so a live page can be asked
      // WHY the line is there without reading the source
      expect(text, name).toMatch(/data-credit-surfaces=/)
    }
  })
  it('the iso arm can be empty: neither shell hardcodes a non-empty surface list', () => {
    for (const [name, rel] of SHELLS) {
      const text = src(...rel)
      // No `creditSurfaces = ['...']` literal, and no `|| true` style escape —
      // the value must come from the predicate call.
      expect(text, name).not.toMatch(/creditSurfaces\s*=\s*\[\s*'/)
      expect(text, name).not.toMatch(/creditSurfaces\.length > 0 \|\|/)
    }
  })
  it('the credit sits in the always-on bottom bar, not inside the legendOpen panel', () => {
    for (const [name, rel] of SHELLS) {
      const text = src(...rel)
      const creditAt = text.indexOf('data-world-credit')
      expect(creditAt, name).toBeGreaterThan(-1)
      // The credit span must not live inside the conditional legend panel:
      // it appears before the `{legendOpen && (` block in both shells.
      const legendPanelAt = text.indexOf('{legendOpen && (')
      expect(legendPanelAt, name).toBeGreaterThan(-1)
      expect(creditAt, name).toBeLessThan(legendPanelAt)
    }
  })
})

/**
 * F. NO DEAD CLICKS, ON THE CHANNEL PEOPLE USE.
 *
 * MEASURED IN A BROWSER 2026-07-30 and it had shipped that way: `onPrimary`
 * opened with `if (!target || target.kind === 'ground') return`, so a LEFT click
 * on open water did NOTHING while a RIGHT click on the same pixel opened
 * "ground / water — carries no data". `openInspect`'s honesty branch — the one
 * commented "catch-all honesty: unmapped pixels answer plainly (no dead
 * clicks)" — was unreachable from the primary channel, and `pick.ts`'s reason
 * for making `ground` a PickKind member rather than a null was true of the type
 * and false of the product.
 *
 * A grep is a weak sensor and this file knows it, so the arm asserts the DEFECT
 * SHAPE is gone rather than that some helpful string is present: the disjunctive
 * early return must not swallow `ground`, and the primary path must route it to
 * the card. A behavioural arm is impossible here — the shell is a 1,200-line
 * PixiJS-bearing React closure with no test harness in the tree — which is why
 * the browser measurement is the primary evidence and this is the ratchet.
 */
describe('F. an unmapped pixel answers on the primary channel too', () => {
  const SHELL = ['components', 'world', 'engine-client.tsx'] as const
  /**
   * COMMENTS STRIPPED FIRST, and that is not a convenience. The fix's own
   * comment QUOTES the shape it removed, verbatim, so a grep over the raw text
   * fires on the prose that documents the fix — the guarded-token-in-a-doc
   * class. A sensor that cannot tell code from a comment about code is reading
   * the wrong file.
   */
  const codeOnly = (text: string) =>
    text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')
  const primaryOf = (text: string) =>
    codeOnly(text).match(/const onPrimary = useCallback\([\s\S]*?\n  \)/)?.[0] ?? ''

  it('onPrimary does not early-return on ground', () => {
    const body = primaryOf(src(...SHELL))
    expect(body, 'onPrimary body found').not.toBe('')
    // the shape that shipped, in either operand order
    expect(body).not.toMatch(/if \([^)]*kind === 'ground'[^)]*\)\s*return\b/)
    expect(body).not.toMatch(/if \([^)]*'ground' === [^)]*\)\s*return\b/)
  })

  it('onPrimary routes a ground target to the inspect card', () => {
    const body = primaryOf(src(...SHELL))
    const branch = body.match(/if \(target\.kind === 'ground'\) \{[\s\S]*?\}/)?.[0]
    expect(branch, 'ground branch exists in onPrimary').toBeTruthy()
    expect(branch).toContain('openInspect(target)')
  })

  it('the card the ground branch opens is still the honest one', () => {
    const text = src(...SHELL)
    const ground = text.match(/id: 'ground',[\s\S]{0,200}/)?.[0] ?? ''
    expect(ground).toContain('carries no data')
    expect(ground).toContain('decorative: true')
  })
})
