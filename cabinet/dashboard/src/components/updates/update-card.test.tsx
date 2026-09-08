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

  it('keeps Apply when the refusal was timing rather than content', () => {
    const busy: UpdateStatus = {
      ...WAITING,
      phase: 'refused',
      last_refusal: { ...REFUSED.last_refusal!, reason: 'busy', paths: [] },
    }
    const html = renderToStaticMarkup(
      <UpdateCard status={busy} headline={updateHeadline(busy)!} />)
    expect(html).toContain('Update refused')
    expect(html).toContain('>Apply<')
  })

  it('says so when the record is being held outside the ledger (A5.16)', () => {
    const held: UpdateStatus = { ...REFUSED, event_fallback: true }
    const html = renderToStaticMarkup(
      <UpdateCard status={held} headline={updateHeadline(held)!} />)
    expect(html).toContain('held')
  })
})
