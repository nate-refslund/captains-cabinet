/**
 * vite.config.mts — serve the frame harness, and nothing else.
 *
 * Vite rather than Next on purpose. `/world` is an authenticated Next route
 * behind redis, a session cookie, a project list and a live snapshot; standing
 * all of that up is a lot of moving parts for a capture whose whole value is
 * that its inputs are pinned. This config mounts the same component with the
 * same public assets and nothing else in the process.
 *
 * NOTHING HERE IS PART OF `next build`. Next builds `src/app`; no file under
 * `src/` imports anything in this directory, and `frame-harness/` carries no
 * page. It ships in the tree because a sensor that only exists on one laptop is
 * not a gate.
 */
import { defineConfig } from 'vite'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const HERE = dirname(fileURLToPath(import.meta.url))
const DASH = resolve(HERE, '..')

export default defineConfig({
  root: HERE,
  // The atlases and manifest EngineCanvas fetches ('/world-assets/...') are the
  // shipped ones. A harness with its own copy of the art would be judging art
  // the product does not draw.
  publicDir: resolve(DASH, 'public'),
  // esbuild's automatic JSX runtime rather than @vitejs/plugin-react: the
  // plugin's job is Fast Refresh, and a capture that reloads its component
  // mid-flight is the one thing this harness must never do.
  esbuild: { jsx: 'automatic' },
  resolve: {
    // The same '@' the dashboard's tsconfig declares, so every import in the
    // component graph resolves identically to the way Next resolves it.
    alias: { '@': resolve(DASH, 'src') },
  },
  server: {
    // The state fixtures live under cabinet/scripts/world-capture/states and are
    // pulled in by import.meta.glob, which is outside `root`.
    fs: { allow: [resolve(DASH, '..', '..')] },
  },
  // Vite would otherwise pre-bundle pixi on first request, which puts a
  // multi-second stall between "server up" and "first frame" and makes the
  // driver's readiness wait look like a hang.
  optimizeDeps: { include: ['pixi.js', 'react', 'react-dom/client'] },
})
