import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  output: 'standalone',
  async headers() {
    return [
      {
        // Cabinet World CI ratchet (E1, kickoff 2026-07-07): strict CSP on
        // the /world surface — self-contained bundle only, no remote
        // origins, no framing. Speech/label text renders as textContent;
        // this header is the transport-level belt under that discipline.
        //
        // script-src stays EVAL-FREE by design (ratchets.test.ts #8): the
        // PixiJS v8 renderer's eval dependency is satisfied by importing
        // the official 'pixi.js/unsafe-eval' AOT patch in world-canvas.tsx
        // (plus preferWorkers:false so no blob: worker needs worker-src) —
        // never by adding 'unsafe-eval' here. 2026-07-08 black-canvas
        // incident: init rejected on the eval check under this header.
        source: '/world',
        headers: [
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-inline'",
              "style-src 'self' 'unsafe-inline'",
              "img-src 'self' data: blob:",
              "connect-src 'self'",
              "font-src 'self'",
              "object-src 'none'",
              "base-uri 'none'",
              "frame-ancestors 'none'",
              "form-action 'none'",
            ].join('; '),
          },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'no-referrer' },
        ],
      },
    ]
  },
}

export default nextConfig
