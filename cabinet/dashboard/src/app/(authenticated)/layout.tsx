import Nav from '@/components/nav'
import KillSwitchHeader from '@/components/kill-switch-header'
import NeedsYouBadge from '@/components/needs-you-badge'
import CommandPalette from '@/components/library/CommandPalette'
import { getProjects, getActiveProject } from '@/actions/projects'
import { getDashboardConfig } from '@/lib/config'
import { readKillswitch } from '@/lib/killswitch-state'
import { glanceOf } from '@/lib/world/killswitch'
import StorePostureBanner from '@/components/store-posture-banner'
import { currentStoreReading } from '@/lib/redis'

export default async function AuthenticatedLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const [projects, activeProject, killswitch, store] = await Promise.all([
    getProjects(),
    getActiveProject(),
    // Three states, never two: an unread emergency stop used to render the
    // same "⏸ Stop All" pill as one the org had verified was not engaged.
    readKillswitch(),
    // A PROBE, not a re-read of the import-time constant. `storeReading` is
    // decided from the environment and cannot know that the host it names has
    // died — which is the ordinary shape of an outage, and used to hang this
    // page rather than disclose anything.
    currentStoreReading(),
  ])
  const { consumerModeEnabled } = getDashboardConfig()

  // Spec 034: hide /cabinets nav link when provisioning flag is off
  const cabinetsEnabled =
    consumerModeEnabled || process.env.CABINETS_PROVISIONING_ENABLED === 'true'

  return (
    <>
      {/* Sidebar navigation — handles its own mobile header (branding + hamburger) */}
      <Nav
        projects={projects}
        activeProject={activeProject}
        consumerModeEnabled={consumerModeEnabled}
        cabinetsEnabled={cabinetsEnabled}
      />

      {/*
        Command Palette — Spec 037 A3.
        Global Cmd-K / Ctrl-K listener across all authenticated pages.
        Client island — no SSR, z-[70] above kill switch (z-60).
      */}
      <CommandPalette />

      {/*
        Persistent kill switch pill — Spec 032 §5.
        Fixed top-right on desktop, fixed top with a right offset on mobile so
        it sits LEFT of the nav's hamburger button (which lives at right-4 inside
        the z-50 mobile header). z-[60] is above the nav so the pill paints on top,
        but the pill background is bg-red-600/20 (20% opaque) — without the offset
        the hamburger shows through the translucent fill and looks like it
        overlaps the "Stop All" label.
        min-h/min-w ensures ≥ 44pt tap target on mobile.
      */}
      <div className="fixed right-14 top-2 z-[60] md:right-3">
        <KillSwitchHeader state={glanceOf(killswitch)} />
      </div>

      {/*
        War-room strip — command-center §4B: the amber "⚑ N need you" badge
        on EVERY authenticated page, left of the kill-switch pill. Client
        island, GET-only, hidden at N=0 (north star: zero pixels when
        nothing pends). Links to /queue — navigation, never actuation.
      */}
      <div className="fixed right-40 top-2 z-[60] md:right-32">
        <NeedsYouBadge />
      </div>

      {/* Main content area */}
      <main className="pt-14 md:pl-64 md:pt-0">
        <div className="mx-auto max-w-6xl px-6 py-8 sm:px-10 lg:px-12">
          {/*
            What produced the numbers below — on EVERY authenticated page, above
            everything, before the Captain reads a single figure. Zero pixels
            when the store is live. A dashboard with no REDIS_URL used to be
            pixel-indistinguishable from a healthy org; the fabrication is gone
            now, but "nothing was measured" still has to SAY so rather than
            leaving the Captain to infer it from empty cards.
          */}
          <div className="mb-6 empty:mb-0">
            <StorePostureBanner reading={store} />
          </div>
          {children}
        </div>
      </main>
    </>
  )
}
