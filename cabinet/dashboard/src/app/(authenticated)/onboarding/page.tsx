import OnboardingJourneyCard from '@/components/onboarding/journey-card'

export const metadata = {
  title: 'Orientation · Cabinet',
}

export default function OnboardingPage() {
  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6">
        <p className="text-sm font-medium text-purple-300">Start small, grow without a ceiling</p>
        <h1 className="mt-1 text-3xl font-bold text-white">Orient your Cabinet</h1>
        <p className="mt-2 max-w-2xl text-zinc-400">
          Start wherever you actually are. Connect a source and it reads first and asks second; connect nothing and it
          asks what you do, then goes looking; grant nothing at all and it tells you plainly what it cannot know.
        </p>
      </div>
      <OnboardingJourneyCard />
      <div className="mt-6 grid gap-3 text-sm text-zinc-400 sm:grid-cols-3">
        <p><strong className="block text-zinc-200">Now</strong>One cited useful result.</p>
        <p><strong className="block text-zinc-200">Next</strong>Deep read-only orientation and Strategy Mirror.</p>
        <p><strong className="block text-zinc-200">Over time</strong>Per-lane trust earned from receipts.</p>
      </div>
    </div>
  )
}
