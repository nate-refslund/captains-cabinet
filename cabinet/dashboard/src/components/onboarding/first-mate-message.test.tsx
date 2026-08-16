/**
 * ATTRIBUTION — if it has an author it is a message, and if it does not it must
 * not look like one.
 *
 * THE DEFECT THIS GUARDS (Captain, 2026-08-14, reading a finding on a live
 * run): "the information is not super useful and it is too much and honestly i
 * don't even know what kind of information this is... if it is from the first
 * mate, make it look like a message from first mate, if it is something else,
 * show or describe that then." Authored content and page furniture rendered
 * identically, so the operator could not tell which he was reading.
 *
 * THE HALF THAT IS EASY TO TEST is that authored content gets the container.
 * THE HALF THAT MATTERS is the inverse: nothing else may wear it. A form, a
 * table or a progress line dressed with an avatar and a name would borrow an
 * authority nobody granted it — so the container's marker is asserted UNIQUE to
 * the one file that owns it, and the impersonation shapes are searched for
 * across every onboarding component.
 */
import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

import { COORDINATOR_ROLE, officerTitle } from '@/lib/officer-title'
import type { OnboardingCard } from '@/lib/onboarding/types'
import FirstMateMessage, { AUTHORED_MARKER, clockOf, initialsOf } from './first-mate-message'
import type { ScreenTheme } from './screen-chrome'

const HERE = __dirname
const OWNER = path.join(HERE, 'first-mate-message.tsx')

const T: ScreenTheme = {
  shell: 'shell', eyebrow: 'eyebrow', title: 'title', muted: 'muted', faint: 'faint',
  panel: 'panel', input: 'input', primary: 'primary', secondary: 'secondary',
  ghost: 'ghost', danger: 'danger', choice: 'choice', choiceOn: 'choiceOn',
  badge: 'badge', railOn: 'railOn', railDone: 'railDone', railOff: 'railOff',
  railLine: 'railLine', railLineDone: 'railLineDone',
}

function card(over: Partial<OnboardingCard> = {}): OnboardingCard {
  return {
    schema: 'cabinet.onboarding-card/v1',
    id: 'card-1',
    journey_id: 'journey-1',
    revision: 1,
    stage: 'dividend_ready',
    kind: 'first_dividend',
    title: 'A finding',
    speaker: 'coordinator',
    body: 'The whole ledger.',
    disclosures: [
      { id: 'lead_0', layer: 'headline', title: '', text: 'I found one thing.', cites: [] },
      { id: 'finding', layer: 'fold', title: 'What I found', text: 'The whole ledger.', cites: [] },
    ],
    status: 'open',
    evidence: [],
    options: [],
    ...over,
  }
}

/** Every component file the onboarding surface renders from. */
function onboardingSources(): Array<[string, string]> {
  const files: Array<[string, string]> = []
  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name)
      if (entry.isDirectory()) walk(full)
      else if (/\.tsx?$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name)) {
        files.push([full, fs.readFileSync(full, 'utf8')])
      }
    }
  }
  walk(HERE)
  return files
}

describe('authored content gets the message, and gets it right', () => {
  it('renders the container, the resolved sender, and the payload', () => {
    const html = renderToStaticMarkup(<FirstMateMessage t={T} card={card()} />)
    expect(html).toContain(`data-authored="${AUTHORED_MARKER}"`)
    expect(html).toContain(officerTitle(COORDINATOR_ROLE))
    expect(html).toContain('I found one thing.')
  })

  it('names the sender through the resolver and never writes a name down', () => {
    // The core says only that the speaker is the COORDINATING officer; what a
    // deployment calls that officer is the resolver's answer.
    const source = fs.readFileSync(OWNER, 'utf8')
    expect(source).toContain('officerTitle(COORDINATOR_ROLE)')
    expect(source).not.toMatch(/['"`]First Mate['"`]/)
  })

  it('stamps the message with a locale-free clock, or with nothing', () => {
    // SSR and the client must not disagree about what a timestamp says.
    expect(clockOf('2026-08-16T09:41:07Z')).toBe('09:41')
    expect(clockOf(null)).toBe('')
    expect(clockOf('not a stamp')).toBe('')
    const html = renderToStaticMarkup(
      <FirstMateMessage t={T} card={card()} stamp="2026-08-16T09:41:07Z" />
    )
    expect(html).toContain('09:41')
  })

  it('puts the grade INSIDE the message it grades', () => {
    const html = renderToStaticMarkup(
      <FirstMateMessage t={T} card={card()} footer={<span>ZEBRAGRADE</span>} />
    )
    const opened = html.indexOf(`data-authored="${AUTHORED_MARKER}"`)
    const closed = html.lastIndexOf('</article>')
    const at = html.indexOf('ZEBRAGRADE')
    expect(at).toBeGreaterThan(opened)
    expect(at).toBeLessThan(closed)
  })

  it('builds initials from the resolved name, never from a hardcoded pair', () => {
    expect(initialsOf('First Mate')).toBe('FM')
    expect(initialsOf('Chief of Staff')).toBe('CO')
    expect(initialsOf('')).toBe('')
  })
})

describe('nothing without an author may look like one', () => {
  it('renders NOTHING for a card the core did not attribute', () => {
    // THE DEGENERATE END. No speaker means nobody said it, so there is nobody
    // to put it in the mouth of.
    const unattributed = card()
    delete (unattributed as { speaker?: unknown }).speaker
    expect(renderToStaticMarkup(<FirstMateMessage t={T} card={unattributed} />)).toBe('')
  })

  it('renders NOTHING for an attributed card with no payload', () => {
    // An empty message with a name on it is furniture wearing a byline.
    const empty = card({ disclosures: [], headline: [], details: [], body: '' })
    expect(renderToStaticMarkup(<FirstMateMessage t={T} card={empty} />)).toBe('')
  })

  it('THE MARKER IS UNIQUE — no other component can claim authorship', () => {
    // The sensor for the half that matters. A screen that hand-rolled an
    // avatar-and-name header to make its table look authoritative would either
    // carry this marker (and fail here) or lack it (and be findable below).
    const carriers = onboardingSources()
      .filter(([, source]) => source.includes(`data-authored`))
      .map(([file]) => path.relative(HERE, file))
    expect(carriers).toEqual(['first-mate-message.tsx'])
  })

  it('no furniture builds a sender header of its own', () => {
    // The impersonation shape, searched for structurally: the resolver is what
    // produces a sender's name, and only the message may call it.
    const users = onboardingSources()
      .filter(([, source]) => source.includes('officerTitle('))
      .map(([file]) => path.relative(HERE, file))
    expect(users).toEqual(['first-mate-message.tsx'])
  })

  it('the container is a real landmark, not a styled div', () => {
    const html = renderToStaticMarkup(<FirstMateMessage t={T} card={card()} />)
    expect(html).toContain('<article')
    expect(html).toContain(`aria-label="Message from ${officerTitle(COORDINATOR_ROLE)}"`)
  })
})
