import type { Metadata, Viewport } from 'next'

/**
 * Full-bleed layout for the wall-monitor kiosk view.
 *
 * This route lives OUTSIDE the (authenticated) route group, so it does NOT
 * inherit the dashboard nav sidebar / kill-switch header / command palette.
 * It inherits only the root layout (html.dark + body.bg-zinc-950), which is
 * exactly the dark full-screen canvas we want for a Chrome kiosk display.
 *
 * No nav, no chrome — just the children, edge to edge.
 */

export const metadata: Metadata = {
  title: 'Cabinet — Live Wall',
  description: 'Live wall-monitor view of the autonomous AI organization',
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  // Kiosk: prevent accidental pinch-zoom on a touch wall display.
  maximumScale: 1,
}

export default function DisplayLayout({ children }: { children: React.ReactNode }) {
  return <div className="min-h-screen w-full bg-zinc-950 text-zinc-300">{children}</div>
}
