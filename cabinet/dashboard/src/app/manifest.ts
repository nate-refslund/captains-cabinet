// PWA manifest (Wave D app-feel) — Next metadata route: auto-serves AND
// auto-links /manifest.webmanifest. Served WITHOUT the auth cookie (see the
// src/middleware.ts matcher exclusions) so Chrome "Install page as app" /
// Safari "Add to Dock" can read it; it carries brand statics only — no
// config, no state, no secrets. Colors = globals.css --color-zinc-950.
import type { MetadataRoute } from 'next'

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Founder's Cabinet",
    short_name: 'Cabinet',
    description: "Admin dashboard for the Founder's Cabinet",
    id: '/',
    start_url: '/',
    scope: '/',
    display: 'standalone',
    background_color: '#09090b',
    theme_color: '#09090b',
    icons: [
      { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
      { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
      {
        src: '/icons/icon-512-maskable.png',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'maskable',
      },
    ],
  }
}
