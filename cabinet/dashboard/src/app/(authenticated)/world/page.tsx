/**
 * /world — Cabinet World, the Wardroom (E1).
 *
 * OBSERVER-CLASS route: a pure read-model over the E0a/E0b chronicle. This
 * server component renders the client shell and nothing else — no server
 * actions exist under /world (CI ratchet), no write path ever will
 * (renderer-never-writes doctrine, kickoff 2026-07-07).
 *
 * Ships at /world → replaces /display after the E1 bake-off → becomes /
 * after two weeks of real defaulting (ratified flip criterion).
 */
import WorldClient from '@/components/world/world-client'

export const metadata = {
  title: 'Cabinet World — Wardroom',
}

export default function WorldPage() {
  return <WorldClient />
}
