/**
 * Every disclosure the core emits reaches the screen — and no screen is a wall
 * of text again.
 *
 * TWO SENSORS, POINTED AT THE TWO WAYS THIS REDESIGN COULD LIE.
 *
 * 1. RENDER PARITY. The core's own parity gate
 *    (framework/onboarding/tests/test_disclosure_parity.py) proves every
 *    disclosure row that existed before this branch is still EMITTED. It cannot
 *    see whether a surface renders one. A row emitted and rendered nowhere is
 *    deleted honesty with a green test beside it, so this file renders the
 *    components and asserts every row's text is on the screen.
 *
 * 2. THE PER-SCREEN WORD CEILING. "Shorter" is the goal, and a goal with no
 *    number is a preference. The ceiling is set where the build FAILED it: the
 *    connected welcome card's body — the ~180-word blob the Captain read on a
 *    live run and answered with "this is way too much text" — is loaded from
 *    the PRE-CHANGE fixture and asserted to exceed it, before any screen is
 *    asserted to be under it. A ceiling that has never been shown to fire is
 *    the disabled sensor this program keeps finding in its own tests.
 *
 * WHAT THESE CANNOT PROVE, said plainly: they render components with fixture
 * props, so they measure the COMPONENTS, not the router's choice of which one
 * to show (screen-router.test.ts owns that) and not the core's row set
 * (the Python parity gate owns that). And the word count is of visible text
 * only — a screen could still be dense with controls and pass.
 */
import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

import type { OnboardingCard, OnboardingDisclosure } from '@/lib/onboarding/types'
import FirstMateMessage, { AUTHORED_MARKER } from './first-mate-message'
import type { ScreenTheme } from './screen-chrome'
import { ApproveScreen, LookScreen, PurgeScreen } from './screens/result'
import { BeginScreen, DreamScreen, WelcomeScreen, YouScreen } from './screens/questions'
import { FolderScreen, SweepScreen } from './screens/access'

// <root>/cabinet/dashboard/src/components/onboarding → five levels up = <root>
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..', '..', '..')
const PRE_CHANGE = path.join(
  REPO_ROOT, 'framework', 'onboarding', 'tests', 'data', 'disclosure-parity.json'
)

/**
 * THE CEILING, in visible words per screen.
 *
 * 150 is not a taste: it is above every screen this branch ships (the widest is
 * the folder screen, whose breadth caveat is a real disclosure and stays) and
 * below the single blob the Captain refused. A screen that needs more than this
 * is two screens.
 */
export const PER_SCREEN_WORD_CAP = 150

/**
 * Visible words: what an operator reads on ARRIVAL, before opening anything.
 *
 * FOLDED TEXT IS EXCLUDED, BY DESIGN AND NOT BY CONVENIENCE. A `<details>` is
 * shut when the screen loads, so its body is not what confronts the operator —
 * and that is the entire mechanism this redesign uses instead of deleting
 * caveats. Counting folded text would make the ceiling punish the layering it
 * exists to reward. The summary IS counted: a fold announces itself.
 *
 * THIS IS ONLY SAFE BECAUSE THE PARITY ARMS ABOVE EXIST. Excluding folded text
 * from a length measurement is exactly how a redesign hides a deletion — so the
 * arms that prove every row is PRESENT run in the same file, and the core's own
 * gate proves every row is still emitted. Neither is optional.
 */
function visibleWords(html: string): number {
  const unfolded = html
    .replace(/<style[\s\S]*?<\/style>/g, ' ')
    // Keep the summary, drop what it hides.
    .replace(/<details\b[^>]*>([\s\S]*?)<\/details>/g, (_all, inner: string) => {
      const summary = /<summary\b[^>]*>([\s\S]*?)<\/summary>/.exec(inner)
      return summary ? summary[1] : ' '
    })
  const text = unfolded
    .replace(/<[^>]*>/g, ' ')
    .replace(/&[a-z]+;|&#\d+;/gi, ' ')
    .trim()
  return text ? text.split(/\s+/).length : 0
}

const T: ScreenTheme = {
  shell: 'shell', eyebrow: 'eyebrow', title: 'title', muted: 'muted', faint: 'faint',
  panel: 'panel', input: 'input', primary: 'primary', secondary: 'secondary',
  ghost: 'ghost', danger: 'danger', choice: 'choice', choiceOn: 'choiceOn',
  badge: 'badge', railOn: 'railOn', railDone: 'railDone', railOff: 'railOff',
  railLine: 'railLine', railLineDone: 'railLineDone',
}

const SHARED = { t: T, variant: 'dashboard' as const, working: false, surface: 'dashboard' }

const ROWS: OnboardingDisclosure[] = [
  { id: 'lead_0', layer: 'headline', title: '', text: 'I read across your 2 connected tools — 666 items.', cites: ['notes/plan.md:12'] },
  { id: 'lead_1', layer: 'headline', title: '', text: 'First: confirm which account is you in tracker.', cites: [] },
  { id: 'opening', layer: 'fold', title: 'How I will start', text: 'ZEBRAFOLD one — the opening move, verbatim. ', cites: [] },
  { id: 'cannot_know', layer: 'fold', title: 'What I cannot know without access', text: 'ZEBRAFOLD two — what I cannot know. ', cites: [] },
  { id: 'probes', layer: 'ledger', title: 'What I looked for and could not reach', text: 'ZEBRALEDGER one — the probes. ', cites: [] },
  { id: 'discovery', layer: 'ledger', title: 'What I went and looked up', text: 'ZEBRALEDGER two — the look-up. ', cites: [] },
]

function card(over: Partial<OnboardingCard> = {}): OnboardingCard {
  return {
    schema: 'cabinet.onboarding-card/v1',
    id: 'card-1',
    journey_id: 'journey-1',
    revision: 3,
    stage: 'welcome',
    kind: 'first_window',
    title: 'Test title',
    speaker: 'coordinator',
    body: ROWS.filter((row) => row.layer !== 'headline').map((row) => row.text).join(''),
    headline: ROWS.filter((row) => row.layer === 'headline').map((row) => row.text),
    details: ROWS.filter((row) => row.layer !== 'headline').map(({ id, title, text }) => ({ id, title, text })),
    disclosures: ROWS,
    status: 'open',
    evidence: [{ path: 'notes/plan.md', line: 12, excerpt: 'ZEBRACITE the cited line', sha256: 'x' }],
    options: [],
    ...over,
  }
}

describe('render parity — every emitted disclosure reaches the screen', () => {
  it('puts every row of every layer on the message, in its own layer', () => {
    const html = renderToStaticMarkup(<FirstMateMessage t={T} card={card()} />)
    for (const row of ROWS) {
      expect(html, `row ${row.id} was emitted and is not on the screen`).toContain(row.text.trim())
    }
    // …and each fold/ledger row wears the question it answers.
    for (const row of ROWS.filter((r) => r.layer !== 'headline')) {
      expect(html).toContain(row.title)
    }
  })

  it('THE SENSOR FIRES: a row the core stops emitting is visibly absent', () => {
    // Proof this is a measurement. Without it, "every row is on the screen"
    // could be true of a renderer that prints the whole card body regardless.
    const short = ROWS.filter((row) => row.id !== 'probes')
    const html = renderToStaticMarkup(
      <FirstMateMessage t={T} card={card({ disclosures: short })} />
    )
    expect(html).not.toContain('ZEBRALEDGER one')
    expect(html).toContain('ZEBRALEDGER two')
  })

  it('opens the citation in place, as a chip on the claim that rests on it', () => {
    const html = renderToStaticMarkup(<FirstMateMessage t={T} card={card()} />)
    expect(html).toContain('notes/plan.md:12')
    expect(html).toContain('ZEBRACITE the cited line')
    // A chip, not a standalone receipt panel: it lives inside the message.
    expect(html.indexOf('notes/plan.md:12')).toBeGreaterThan(html.indexOf(AUTHORED_MARKER))
  })

  it('reads an OLDER card that predates the row list, losing nothing', () => {
    // Version skew must not become deleted honesty: a card with only
    // headline/details still renders every section it carries.
    const older = card()
    delete (older as { disclosures?: unknown }).disclosures
    const html = renderToStaticMarkup(<FirstMateMessage t={T} card={older} />)
    for (const row of ROWS) expect(html).toContain(row.text.trim())
  })

  it('lays the consent screen out UNFOLDED — every term, no disclosure widget', () => {
    const terms: OnboardingDisclosure[] = [
      { id: 'grant', layer: 'fold', title: 'What I may read', text: 'ZEBRAGRANT the folder. ', cites: [] },
      { id: 'limits', layer: 'fold', title: 'What I will not do', text: 'ZEBRALIMIT the caps. ', cites: [] },
      { id: 'fingerprint', layer: 'ledger', title: 'The exact thing you are approving', text: 'ZEBRAHASH abc.', cites: [] },
    ]
    const html = renderToStaticMarkup(
      <ApproveScreen
        {...SHARED}
        card={card({ disclosures: terms, kind: 'orientation_charter', options: [] })}
        onApprove={() => {}}
        onChange={() => {}}
        error=""
      />
    )
    for (const term of terms) {
      expect(html).toContain(term.text.trim())
      expect(html).toContain(term.title)
    }
    // The one screen where nothing is folded away: the operator is granting.
    expect(html).not.toContain('<details')
  })
})

describe('the per-screen word ceiling', () => {
  it('THE CEILING FIRES: the blob this replaced is over it', () => {
    // The pre-change artifact, recorded off the commit this branch forked from.
    const table = JSON.parse(fs.readFileSync(PRE_CHANGE, 'utf8')) as Record<
      string,
      { body: string }
    >
    const blob = table.welcome_swept.body
    expect(visibleWords(blob)).toBeGreaterThan(PER_SCREEN_WORD_CAP)
  })

  const screens: Array<[string, () => string]> = [
    ['welcome', () => renderToStaticMarkup(<WelcomeScreen {...SHARED} onBegin={() => {}} />)],
    ['you', () => renderToStaticMarkup(
      <YouScreen {...SHARED} name="" role="" onName={() => {}} onRole={() => {}}
        onNext={() => {}} onBack={() => {}} blocked="Tell me what you do first." />
    )],
    ['dream', () => renderToStaticMarkup(
      <DreamScreen {...SHARED} name="Ada" dream="" onDream={() => {}} onNext={() => {}} onBack={() => {}} />
    )],
    ['begin', () => renderToStaticMarkup(
      <BeginScreen {...SHARED} startPreference="" onPreference={() => {}} onNext={() => {}}
        onBack={() => {}} blocked="Choose one of the two above." />
    )],
    ['folder', () => renderToStaticMarkup(
      <FolderScreen {...SHARED} source="~/Documents" ownership="" authorityBasis=""
        onSource={() => {}} onUseDocuments={() => {}} onOwnership={() => {}}
        onAuthorityBasis={() => {}} onSubmit={() => {}} onBack={() => {}}
        backLabel="Back" error="" managing={false} />
    )],
    ['sweep', () => renderToStaticMarkup(
      <SweepScreen {...SHARED} swept={[{ name: 'tracker', connected: true, items: 12, calls: 1, latest: '2026-08-13' }]}
        sweptAt="2026-08-13T09:00:00Z" answeredTarget="" onChooseFolder={() => {}}
        onConnectMore={() => {}} onRepoint={() => {}} repointable={false} error=""
        card={undefined} />
    )],
    ['look', () => renderToStaticMarkup(
      <LookScreen {...SHARED} line={1} source="~/Documents" />
    )],
    ['purge', () => renderToStaticMarkup(
      <PurgeScreen {...SHARED} confirmation="" onConfirmation={() => {}}
        onSubmit={() => {}} onCancel={() => {}} error="" />
    )],
  ]

  for (const [name, render] of screens) {
    it(`${name} is under the ceiling`, () => {
      const words = visibleWords(render())
      expect(words, `${name} renders ${words} visible words`).toBeLessThanOrEqual(
        PER_SCREEN_WORD_CAP
      )
    })
  }

  it('counts words rather than characters — the counter is not a stub', () => {
    // The degenerate end, checked: an empty render is zero, and a known string
    // counts what it says. A counter that returned 0 for everything would make
    // every arm above pass.
    expect(visibleWords('')).toBe(0)
    expect(visibleWords('<p class="x">one two three</p>')).toBe(3)
    expect(visibleWords('<div><span>a</span><span>b</span></div>')).toBe(2)
    // And the fold is counted by its summary, not by what it hides.
    expect(visibleWords('<details><summary>open me</summary>one two three four</details>')).toBe(2)
  })
})
