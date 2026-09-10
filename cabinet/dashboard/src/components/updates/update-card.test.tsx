/**
 * The update card renders the three facts a person needs before tapping Apply.
 *
 * WHY A TEST FOR THREE STRINGS. A5.11 says the card shows the waiting bundle's
 * `source_commit`, `built_at` and the inbox file's owner and mtime, because the
 * inbox is same-uid writable: anything on the box could have put that tarball
 * there. Round-1 shipped the card with `built_at` in the type, in the status
 * JSON and in the applied receipt — and nowhere on the screen. A field that
 * travels the whole way and is never rendered is the same as a field that was
 * never collected, and nothing else in the suite could see the difference.
 */
import { readFileSync } from 'fs'
import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

import UpdateCard from './update-card'
import { updateHeadline, type UpdateStatus } from '@/lib/updates-view'

const WAITING: UpdateStatus = {
  installed_sha: 'a'.repeat(40),
  installed_short: 'aaaaaaaa',
  phase: 'idle',
  last: null,
  snapshots: [],
  available: [],
  latest: {
    sha: 'b'.repeat(40),
    short: 'bbbbbbbb',
    built_at: '2026-09-07T11:22:33Z',
    from_sha: 'a'.repeat(40),
    file_count: 12,
    changelog: ['the tap reaches the installed cabinet'],
    owner: 'someone',
    mtime: '2026-09-07T11:30:00Z',
  },
}

describe('UpdateCard', () => {
  it('names when the waiting bundle was built, who placed it and when', () => {
    const html = renderToStaticMarkup(<UpdateCard status={WAITING} headline="Update ready" />)
    expect(html).toContain('2026-09-07T11:22:33Z')
    expect(html).toContain('someone')
    expect(html).toContain('2026-09-07T11:30:00Z')
    expect(html).toContain('the tap reaches the installed cabinet')
  })

  it('says so rather than inventing a time when the manifest carried none', () => {
    const status = {
      ...WAITING,
      latest: { ...WAITING.latest!, built_at: '', owner: '' },
    }
    const html = renderToStaticMarkup(<UpdateCard status={status} headline="Update ready" />)
    expect(html).toContain('at an unrecorded time')
    expect(html).toContain('an unknown account')
  })

  it('offers no Apply button when nothing is waiting', () => {
    const status = { ...WAITING, latest: null }
    const html = renderToStaticMarkup(<UpdateCard status={status} headline="Up to date" />)
    expect(html).not.toContain('>Apply<')
  })
})

// ---------------------------------------------------------------------------
// A5.15 on the card itself. The headline is one sentence; the card is where a
// refusal becomes actionable, because "which files" is the whole of what the
// operator needs in order to do anything about it.
// ---------------------------------------------------------------------------

const REFUSED: UpdateStatus = {
  ...WAITING,
  phase: 'refused',
  last_refusal: {
    bundle: 'b'.repeat(40),
    reason: 'bundle changes locked constitutional paths',
    paths: ['cabinet/scripts/start-officer-mac.sh'],
    ts: '2026-09-08T18:58:00Z',
    door: 'terminal',
  },
}

describe('UpdateCard on a refusal', () => {
  it('names the files that differ, so the sentence can be acted on', () => {
    const html = renderToStaticMarkup(
      <UpdateCard status={REFUSED} headline={updateHeadline(REFUSED)!} />)
    expect(html).toContain('Update refused')
    expect(html).toContain('cabinet/scripts/start-officer-mac.sh')
    expect(html).not.toContain('Update ready')
  })

  it('offers no Apply for a bundle that cannot be applied without a person', () => {
    const html = renderToStaticMarkup(
      <UpdateCard status={REFUSED} headline={updateHeadline(REFUSED)!} />)
    expect(html).not.toContain('>Apply<')
  })

  // RE-AIMED, round 6. Both arms below used to build a status by hand that the
  // resolver cannot produce — a `busy` record in `last_refusal`, and a verdict
  // about one bundle while another is waiting. Since A5.17 the report carries
  // `current(W)`: a timing note is not a candidate on any channel, and a
  // verdict about another sha is not the answer to a question about this one.
  // So these render what the report ACTUALLY carries in each state. The
  // scoping is pinned where it now lives — 5250 rows in lib/updates.test.ts
  // and, on the resolver itself, in cabinet/scripts/tests/test_cabinet_update.py.
  it('a busy refusal neither withdraws Apply nor speaks over the bundle', () => {
    const busy: UpdateStatus = {
      ...WAITING,
      phase: 'refused',
      last_refusal: null,
      last_busy: { bundle: 'b'.repeat(40), ts: '2026-09-09T10:00:30Z', door: 'web' },
    }
    const html = renderToStaticMarkup(
      <UpdateCard status={busy} headline={updateHeadline(busy)!} />)
    expect(html).not.toContain('Update refused')
    expect(html).toContain('Update ready')
    expect(html).toContain('>Apply<')
  })

  // THE BLOCKING DEFECT of round 1, as the card sees it. `phase` stays
  // `refused` until some later apply moves it, so this is the state every
  // bundle cut after a constitutional refusal arrives into — the Captain's
  // ceremony, then the next bundle. The card was showing the OLD refusal's
  // headline and files over it and withdrawing Apply, which is the only
  // no-terminal way to take the update that would clear the phase.
  it('offers the NEXT bundle even while the phase still says refused', () => {
    const next: UpdateStatus = {
      ...REFUSED,
      last_refusal: null,
      last_refusal_source: '',
      latest: { ...WAITING.latest!, sha: 'f'.repeat(40), short: 'ffffffff', file_count: 7 },
    }
    const html = renderToStaticMarkup(
      <UpdateCard status={next} headline={updateHeadline(next)!} />)
    expect(html).toContain('Update ready — 7 files changed (ffffffff)')
    expect(html).not.toContain('Update refused')
    expect(html).not.toContain('cabinet/scripts/start-officer-mac.sh')
    expect(html).toContain('>Apply<')
  })

  // A5.17.7 ON THE CARD, which is the half round 5 declared a per-surface
  // difference and the A5.17 gate retired. A bundle this box took and put back
  // is not a bundle nobody has tried: "Update ready" over it hides the one
  // fact the Captain would want before tapping Apply a second time. Apply
  // STAYS — a health gate that went red is worth re-testing — so the sentence
  // is the whole of the change, and it is the briefing's sentence word for
  // word.
  it('says a bundle was rolled back and still keeps Apply', () => {
    const rolled: UpdateStatus = {
      ...WAITING,
      last_refusal: null,
      waiting_rollback: { bundle: 'b'.repeat(40), reason: 'the health gate was red',
                          ts: '2026-09-09T10:00:20Z' },
    }
    const html = renderToStaticMarkup(
      <UpdateCard status={rolled} headline={updateHeadline(rolled)!} />)
    expect(html).toContain(
      'Update rolled back — the health gate was red; still waiting (bbbbbbbb)')
    expect(html).toContain('>Apply<')
    expect(html).not.toContain('Update refused')
  })

  // THE SHAPE THE TWO RACES LEAVE ON DISK, rendered. e1 (a rollback that lost
  // the lock, writing a note about NO bundle) and e2 (an apply of another
  // bundle that lost it, writing a note about THAT one) both end with a
  // constitutional verdict standing on the waiting bundle and a timing note
  // beside it. Round 5 shipped a resolver that handed this card `last_refusal:
  // null` for e1 and the note about the other bundle for e2, and it rendered
  // `>Apply<` over bytes the box had refused. The resolution is pinned in
  // pytest end to end through the real updater, and the row it lands on is
  // pinned to this card over all 5250 in lib/updates.test.ts; what is left is
  // the rendering itself, which is the half a person actually taps.
  //
  // HONEST LABEL: this arm is GREEN at c0a92731 as well. At those bytes the
  // card was handed the WRONG DOCUMENT for these two races, not handed the
  // right one and rendered wrong — `status --json` reported no refusal at all
  // (e1) or the note about the other bundle (e2). The red for that lives in
  // the resolver's arms and in the 5250-row sweep; this one pins the
  // rendering so it cannot drift out from under them.
  it.each([
    ['a note about no bundle at all (e1)', ''],
    ['a note about another bundle (e2)', 'e'.repeat(40)],
  ])('keeps the verdict on screen beside %s', (_what, busySha) => {
    const raced: UpdateStatus = {
      ...REFUSED,
      last_busy: { bundle: busySha, ts: '2026-09-09T10:00:30Z', door: 'web' },
    }
    const html = renderToStaticMarkup(
      <UpdateCard status={raced} headline={updateHeadline(raced)!} />)
    expect(html).toContain(
      'Update refused \u2014 1 constitutional file differs; needs the Captain (bbbbbbbb)')
    expect(html).toContain('cabinet/scripts/start-officer-mac.sh')
    expect(html).not.toContain('Update ready')
    expect(html).not.toContain('>Apply<')
  })

  it('says so when the record is being held outside the ledger (A5.16)', () => {
    const held: UpdateStatus = { ...REFUSED, event_fallback: true }
    const html = renderToStaticMarkup(
      <UpdateCard status={held} headline={updateHeadline(held)!} />)
    expect(html).toContain('held')
    // and the benign sentence, because this one IS benign: the emitter that
    // knows the update events arrives with the update.
    expect(html).toContain('does not know the update events yet')
  })

  // A5.16, round 2. The recorder holds the record whatever went wrong — that
  // half is right and stays. What was wrong is that a full disk and a ledger
  // one version behind produced the SAME sentence, and it was the reassuring
  // one: "the next update files it". No update files a full disk.
  it('calls a broken ledger a fault rather than a version it will grow out of', () => {
    const faulty: UpdateStatus = {
      ...REFUSED,
      event_fallback: true,
      ledger_error: 'OSError: [Errno 28] No space left on device: events-2026-09-08.jsonl',
    }
    const html = renderToStaticMarkup(
      <UpdateCard status={faulty} headline={updateHeadline(faulty)!} />)
    expect(html).toContain('ledger fault')
    expect(html).toContain('No space left on device')
    expect(html).not.toContain('does not know the update events yet')
  })

  // A5.18, and it is a BUILD property this suite can hold in milliseconds.
  //
  // Measured 2026-09-10, on the first staged build anything ever ran: `next
  // build` failed outright —
  //
  //     ./src/lib/updates.ts:25:1
  //     Module not found: Can't resolve 'child_process'
  //     #4 [Client Component Browser]: ./src/lib/updates.ts
  //                                    ./src/components/updates/update-card.tsx
  //
  // — because this card is a client component and importing ONE symbol from a
  // module pulls the WHOLE module into the browser graph, exec seam and all.
  // The dashboard had not been buildable since the update path landed, and
  // nothing noticed because no gate anywhere ran a build. The drill's P7 runs
  // one now; this arm is the cheap half, so the next person to reach for the
  // exec seam from a client component learns it in a test rather than in a
  // three-minute build.
  it('pulls nothing into the browser graph that a browser cannot have', () => {
    const card = readFileSync(new URL('./update-card.tsx', import.meta.url), 'utf-8')
    expect(card).not.toMatch(/from '@\/lib\/updates'/)
    expect(card).toMatch(/from '@\/lib\/updates-view'/)
    const view = readFileSync(new URL('../../lib/updates-view.ts', import.meta.url), 'utf-8')
    for (const builtin of ['child_process', 'fs', 'path', 'os', 'net', 'util']) {
      expect(view).not.toMatch(new RegExp(`from '(node:)?${builtin}'`))
    }
  })
})
