import Link from 'next/link'
import OnboardingJourneyCard from '@/components/onboarding/journey-card'

export const metadata = {
  title: 'Orientation · Cabinet',
}

export default function OnboardingPage() {
  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-violet-300/90">
          Start small, grow without a ceiling
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">Orient your Cabinet</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-400">
          Three short questions, then one folder to read. Nothing is opened until you approve
          a Charter — you always see exactly what it would read first.
        </p>
      </div>
      {/* The door to /briefing. The hatch lands the operator here, and the
          first thing it wrote — the genesis briefing + research brief — is
          otherwise reachable only by opening a file in a terminal. Rendered in
          the PAGE, deliberately not inside journey-card.tsx: the card owns the
          journey state machine, this is a sibling link with no state. */}
      <Link
        href="/briefing"
        className="group mb-4 flex items-center justify-between gap-4 rounded-xl border border-zinc-800 bg-zinc-900/50 px-4 py-3 text-sm transition-colors hover:border-violet-700/70 hover:bg-zinc-900"
      >
        <span>
          <strong className="block text-zinc-200">Read your first briefing</strong>
          <span className="text-zinc-500">
            What the Cabinet proposed first, and what it read before proposing it.
          </span>
        </span>
        <span aria-hidden className="ml-2 text-violet-300 transition-transform group-hover:translate-x-0.5">
          →
        </span>
      </Link>
      <OnboardingJourneyCard />
      <div className="mt-6 grid gap-3 text-sm text-zinc-400 sm:grid-cols-3">
        <p><strong className="block text-zinc-200">Now</strong>One cited useful result.</p>
        <p><strong className="block text-zinc-200">Next</strong>Deep read-only orientation and Strategy Mirror.</p>
        <p><strong className="block text-zinc-200">Over time</strong>Per-lane trust earned from receipts.</p>
      </div>
    </div>
  )
}
