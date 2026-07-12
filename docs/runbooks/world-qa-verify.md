# World QA / Verify Runbook — Cabinet World aliveness probes

Scope: QA of `/world` (Wardroom Z2, street Z1, island Z0.5, night/cozy
ambience). Applies to any automated or agent-driven "is the world alive?"
check. Companion to the gate set (vitest + `tsc --noEmit` + `next build` +
`world-binding-validator.py` + `world-asset-gate.py`), which stays the
merge-time bar — this runbook covers the LIVE render surface.

## Gotcha — `toDataURL()` on the world canvas reads FALSE-DEAD

The world canvas is **WebGL without `preserveDrawingBuffer`** (the PIXI
default, kept deliberately — enabling it costs a persistent framebuffer copy
on every frame for a debug-only convenience). After each frame is presented,
the drawing buffer is invalidated, so:

- `canvas.toDataURL()` / `getContext(...).readPixels` / `getImageData`
  return a **frozen, stale buffer** — NOT the current frame.
- Measured 2026-07-08 (world-alive review): 1 distinct "frame" over 22s via
  `toDataURL` while the real render loop ran at ~120fps rAF. Any aliveness
  probe gating on `toDataURL` deltas will report **false-dead** on a
  perfectly live world.

**Never gate aliveness on `toDataURL()` or buffer readback.**

## What to use instead

1. **Clipped page screenshots** (the verified method): drive the page with a
   real browser (Chrome MCP / Playwright / chrome-devtools MCP) and take
   viewport/element screenshots clipped to the canvas. Verified 2026-07-08:
   **8/8 byte-distinct frames over 5s** on an officer sprite — page
   compositor screenshots see the live WebGL output, unlike canvas readback.
2. **DOM signals**: the world's text layer is DOM by construction (labels,
   chips, clock, chronicle ticker with the always-on LimeZu art credit,
   killswitch banner). Clock text changing and chip/label reconciliation
   are cheap liveness signals with no GPU readback at all.
3. If a pixel-exact extract is ever truly needed, expose a debug `extract()`
   path (render-to-texture → `pixi.Extract` on demand) rather than flipping
   `preserveDrawingBuffer` globally. Do not enable `preserveDrawingBuffer`
   just for QA.

## QA checklist per world change (post-merge, live build)

1. Rebuild + restart: `rm -rf cabinet/dashboard/.next && launchctl
   kickstart -k gui/501/com.cabinet.dashboard` (start script rebuilds when
   `.next` is absent; serves on `$CABINET_DASHBOARD_PORT`, default 3100).
2. `/world` at z=2 (Wardroom): officers at stations, cozy dressing, lamp
   pools/tint matching the snapshot clock bucket (dawn/day/dusk/night).
3. z=1 (street) and z=0.5 (island): scene swap through the 120ms cut;
   growth bindings render (HQ floors, land radius, fields, harbor beacon —
   honest zero renders LOUD, never invented).
4. Killswitch drill (if testing): red wash + unsuppressible DOM banner,
   director freeze.
5. Aliveness: clipped page screenshots per the section above — never
   `toDataURL`.
