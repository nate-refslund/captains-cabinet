import type { Metadata, Viewport } from 'next'
import './globals.css'

// Wave D app-feel: PWA/Add-to-Dock metadata. The manifest itself is the
// src/app/manifest.ts metadata route; html stays hardcoded dark.
export const viewport: Viewport = { themeColor: '#09090b' }

export const metadata: Metadata = {
  title: "Founder's Cabinet",
  description: "Admin dashboard for the Founder's Cabinet",
  appleWebApp: {
    capable: true,
    title: 'Cabinet',
    statusBarStyle: 'black-translucent',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-zinc-950 text-zinc-400 antialiased">
        {children}
      </body>
    </html>
  )
}
