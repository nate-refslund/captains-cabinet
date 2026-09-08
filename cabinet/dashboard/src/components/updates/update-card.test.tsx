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
import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

import UpdateCard from './update-card'
import { updateHeadline, type UpdateStatus } from '@/lib/updates'

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

  // RE-AIMED, round 2. This arm used to demand the words "Update refused" over
  // a bundle whose only refusal was `busy` — timing, which says nothing about
  // these bytes. Reading a refusal over a bundle it is not a verdict on is the
  // same defect as withdrawing Apply for one, one surface further along: the
  // retry that is the right thing to do about `busy` is exactly what the card
  // was talking the operator out of.
  it('a busy refusal neither withdraws Apply nor speaks over the bundle', () => {
    const busy: UpdateStatus = {
      ...WAITING,
      phase: 'refused',
      last_refusal: { ...REFUSED.last_refusal!, reason: 'busy', paths: [] },
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
      latest: { ...WAITING.latest!, sha: 'f'.repeat(40), short: 'ffffffff', file_count: 7 },
    }
    const html = renderToStaticMarkup(
      <UpdateCard status={next} headline={updateHeadline(next)!} />)
    expect(html).toContain('Update ready — 7 files changed (ffffffff)')
    expect(html).not.toContain('Update refused')
    expect(html).not.toContain('cabinet/scripts/start-officer-mac.sh')
    expect(html).toContain('>Apply<')
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
})
