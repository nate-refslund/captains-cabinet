/**
 * How a connector's last sweep reads on a card — shared by the journey card and
 * the arrival's management view.
 *
 * EXTRACTED 2026-08-14, and not for tidiness. The arrival's "Connected tools"
 * section first rendered `row.reason` directly, which would have shown an
 * operator the raw diagnostic string (`credential_absent`, `http_401`) that
 * every other surface translates. Two surfaces describing the same row two
 * different ways is how a product stops speaking one voice; one function is the
 * fix. It lives here rather than in journey-card.tsx because the card imports
 * the arrival, so importing back would close a cycle.
 */
import type { OnboardingSweptConnector } from './types'

/**
 * Why a connector came back with nothing, in the operator's words.
 *
 * The sweep's own reason strings are diagnostic and stable (`credential_absent`,
 * `http_401`, `read_only_refused:<verdict>`) — good in a log, useless on a card.
 * This translates the ones an operator can ACT on and passes anything else
 * through readably rather than swallowing it: an unrecognised reason printed
 * plainly is still a fact, while a generic "something went wrong" is not.
 */
export function plainReason(reason: string): string {
  const code = String(reason || '').trim()
  if (!code) return 'it did not answer'
  if (code === 'credential_absent') return 'no key is stored for it yet'
  if (code === 'inventory_returned_no_items') return 'it answered, and there is nothing in it yet'
  if (code === 'http_401' || code === 'http_403') {
    return 'the key was refused — check you pasted the whole key, and that it has read access'
  }
  if (code === 'http_404') return 'that address answered “not found”'
  if (code === 'http_429') return 'it asked me to slow down — try again in a minute'
  if (code.startsWith('http_5')) return 'the other side had an error of its own'
  if (code.startsWith('http_')) return `it answered ${code.slice(5)}`
  if (code.startsWith('unreachable')) return 'I could not reach it'
  if (code.startsWith('egress_')) return 'outbound calls are switched off for this cabinet'
  if (code.startsWith('read_only_refused')) return 'that shape is not a read, so I did not run it'
  if (code.startsWith('name_path_missed')) return 'I read it, but found no names where I was told to look'
  if (code === 'response_not_json') return 'what came back was not a list I can read'
  if (code === 'response_too_large') return 'what came back was too big to read'
  return code.replaceAll('_', ' ')
}

/** The date half of a sweep stamp. ISO in, `2026-08-13` out, locale-free. */
export function dayOf(stamp: string | null | undefined): string {
  const match = /^\d{4}-\d{2}-\d{2}/.exec(String(stamp ?? ''))
  return match ? match[0] : ''
}

/** What one connector's last sweep amounts to, in one sentence. */
export function sweepLine(row: OnboardingSweptConnector): string {
  if (!row.connected) return plainReason(String(row.reason ?? ''))
  const parts = [`read ${row.items} thing${row.items === 1 ? '' : 's'}`]
  const day = dayOf(row.latest)
  if (day) parts.push(`newest ${day}`)
  if (row.actors) parts.push(`${row.actors} account${row.actors === 1 ? '' : 's'}`)
  return parts.join(' · ')
}
