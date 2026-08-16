import OnboardingJourneyCard from '@/components/onboarding/journey-card'

export const metadata = {
  title: 'Orientation · Cabinet',
}

/**
 * THE PAGE IS A FRAME, AND A FRAME SAYS NOTHING.
 *
 * It used to carry a hero ("Orient your Cabinet" / "Three short questions, then
 * one folder to read"), a link to the briefing, and a Now/Next/Over-time
 * roadmap — all of it standing above and below whichever screen the flow was
 * on. Three separate defects came out of that:
 *
 *   · It CONTRADICTED the flow. "Three short questions" is not what the flow
 *     does any more, and a frame that describes the product differently from
 *     the product is the thing an operator trusts least.
 *   · It repeated the same promise in different words on every step. That is
 *     the always-present summary the Captain read as the page not moving
 *     (2026-08-14) — the standing read-only line inside the flow says it once,
 *     in one wording, and that is enough.
 *   · It PRE-EMPTED the screens. Screens replace each other; page furniture
 *     that never leaves is the accumulation the redesign removed, reintroduced
 *     one level up.
 *
 * The briefing link went with it: it is on the arrival screen, where a finished
 * operator is actually looking for it, rather than above a wizard they have not
 * started. The completion branch is gone for the same reason — the frame no
 * longer has anything to hide when the journey ends, so it does not need to
 * know whether it has.
 */
export default function OnboardingPage() {
  return (
    <div className="mx-auto max-w-3xl">
      <OnboardingJourneyCard />
    </div>
  )
}
