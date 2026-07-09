/**
 * /world — Cabinet World, the ONE continuous world (T1 engine).
 *
 * OBSERVER-CLASS route with the ONE ruled exception: a pure read-model over
 * the E0a/E0b chronicle — no server actions are declared under /world (CI
 * ratchet). The single in-world actuator is the killswitch lever (Captain
 * ruling 2026-07-09, two-tap + confirm + captain cookie), which reuses the
 * EXISTING dashboard killswitch action; everything else stays read-only.
 *
 * T1 (spec v2 supersession #5): the three-scene shell (WorldClient —
 * wardroom/street/island scene swap) is REPLACED by EngineClient: chunked
 * unbounded tilemap, era×rung growth from hot-reloaded growth-ladders.yml,
 * continuous LOD zoom to the archipelago, in-place roof cutaway, and the
 * signal-bound weather layer. The legacy three-scene shell stays reachable
 * at ?legacy=1 for the engine bake-off, then deletes.
 *
 * canActuate: the captain session cookie is verified HERE (server) and
 * threaded down — without it the lever renders truth but refuses to act
 * (view-only law).
 */
import { cookies } from 'next/headers'
import WorldClient from '@/components/world/world-client'
import EngineClient from '@/components/world/engine-client'

export const metadata = {
  title: 'Cabinet World',
}

export default async function WorldPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const cookieStore = await cookies()
  const canActuate = Boolean(cookieStore.get('cabinet_session')?.value)
  const params = await searchParams
  if (params.legacy === '1') return <WorldClient canActuate={canActuate} />
  return <EngineClient canActuate={canActuate} />
}
