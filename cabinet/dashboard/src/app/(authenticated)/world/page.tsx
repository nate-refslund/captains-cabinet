/**
 * /world — Cabinet World, the ONE continuous world (T1 engine).
 *
 * OBSERVER-CLASS map/renderer over the E0a/E0b chronicle — no server actions
 * are declared under /world (CI ratchet). The single org-state actuator is the
 * killswitch lever. Onboarding v2 adds a Captain UI overlay, not a World
 * mutation path: it renders the shared card and calls /api/onboarding, the same
 * service Dashboard uses; it cannot write map, chronicle, outcomes, or runtime.
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
import OnboardingJourneyCard from '@/components/onboarding/journey-card'

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
  return (
    <>
      {params.legacy === '1' ? (
        <WorldClient canActuate={canActuate} />
      ) : (
        <EngineClient canActuate={canActuate} />
      )}
      {/*
        Orientation overlay: this is NOT a World mutation path. It renders the
        canonical onboarding card and posts to /api/onboarding — the same
        authenticated action service as Dashboard. The map/renderer and every
        /api/world/* route remain read-only (killswitch remains its ruled,
        unrelated exception).
      */}
      <div className="fixed bottom-5 left-5 z-[80] max-h-[min(82vh,48rem)] overflow-y-auto">
        <OnboardingJourneyCard surface="world" variant="world" />
      </div>
    </>
  )
}
