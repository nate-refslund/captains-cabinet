/**
 * /world — Cabinet World, the Wardroom (E1).
 *
 * OBSERVER-CLASS route with the ONE ruled exception: a pure read-model over
 * the E0a/E0b chronicle — no server actions are declared under /world (CI
 * ratchet). The single in-world actuator is the killswitch lever (Captain
 * ruling 2026-07-09, two-tap + confirm + captain cookie), which reuses the
 * EXISTING dashboard killswitch action; everything else stays read-only.
 *
 * canActuate: the captain session cookie is verified HERE (server) and
 * threaded down — without it the lever renders truth but refuses to act
 * (view-only law).
 *
 * Ships at /world → replaces /display after the E1 bake-off → becomes /
 * after two weeks of real defaulting (ratified flip criterion).
 */
import { cookies } from 'next/headers'
import WorldClient from '@/components/world/world-client'

export const metadata = {
  title: 'Cabinet World — Wardroom',
}

export default async function WorldPage() {
  const cookieStore = await cookies()
  const canActuate = Boolean(cookieStore.get('cabinet_session')?.value)
  return <WorldClient canActuate={canActuate} />
}
