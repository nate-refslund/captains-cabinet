/**
 * pixi.js v8 ships the './unsafe-eval' export (lib/unsafe-eval/init.mjs)
 * without a matching type declaration under bundler moduleResolution.
 * It is a side-effect-only CSP patch (installs the AOT uniform-sync path),
 * imported by components/world/world-canvas.tsx before renderer init —
 * see world/ratchets.test.ts #8.
 */
declare module 'pixi.js/unsafe-eval'
