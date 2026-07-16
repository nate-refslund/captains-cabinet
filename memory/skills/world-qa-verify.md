---
name: world-qa-verify
description: QA the live Cabinet World render (/world) after any world change — verify aliveness with clipped page screenshots or DOM signals, never canvas.toDataURL (WebGL reads false-dead); run the per-zoom post-merge checklist.
status: promoted
author: foundation
date: 2026-07-17
validated_against: ["2026-07-08 world-alive review: 8/8 byte-distinct clipped frames over 5s on an officer sprite; toDataURL control read 1 'frame' over 22s while the render loop ran ~120fps rAF (false-dead)"]
usage_count: 0
---

# Skill: World QA / Verify — Cabinet World aliveness probes

Scope: QA of `/world` (Wardroom Z2, street Z1, island Z0.5, night/cozy
ambience). Applies to any automated or agent-driven "is the world alive?"
check. Companion to the gate set (vitest + `tsc --noEmit` + `next build` +
`world-binding-validator.py` + `world-asset-gate.py`), which stays the
merge-time bar — this skill covers the LIVE render surface.

## When to Use

After any world change lands (post-merge, live build), or whenever an
automated/agent-driven aliveness check of the `/world` surface is needed —
including writing new QA probes. If you are about to gate anything on canvas
pixel readback, stop and use this skill first.

## Procedure

QA checklist per world change (post-merge, live build):

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
5. Aliveness: clipped page screenshots per "What to use" below — never
   `toDataURL`.

What to use for aliveness:

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

## Expected Outcome

Every world change gets a live-surface verdict: distinct clipped frames (or
moving DOM clock/chips) prove aliveness; the per-zoom checklist confirms
stations, scene cuts, growth bindings, and the killswitch drill. No aliveness
probe in the codebase gates on buffer readback.

## Known Pitfalls

**`toDataURL()` on the world canvas reads FALSE-DEAD.** The world canvas is
**WebGL without `preserveDrawingBuffer`** (the PIXI default, kept
deliberately — enabling it costs a persistent framebuffer copy on every frame
for a debug-only convenience). After each frame is presented, the drawing
buffer is invalidated, so:

- `canvas.toDataURL()` / `getContext(...).readPixels` / `getImageData`
  return a **frozen, stale buffer** — NOT the current frame.
- Measured 2026-07-08 (world-alive review): 1 distinct "frame" over 22s via
  `toDataURL` while the real render loop ran at ~120fps rAF. Any aliveness
  probe gating on `toDataURL` deltas will report **false-dead** on a
  perfectly live world.

**Never gate aliveness on `toDataURL()` or buffer readback.**

## Validation Scenarios

- Live world, clipped page screenshots over 5s → 8/8 byte-distinct frames
  (verified 2026-07-08, world-alive review).
- Live world, `toDataURL` deltas over 22s → 1 distinct "frame" at ~120fps
  real render (the false-dead control — the reason this skill exists).
- Killswitch drill → red wash + unsuppressible DOM banner + director freeze.

## Origin

Graduated verbatim from `docs/runbooks/world-qa-verify.md` (2026-07-17,
vault wave; runbook→skill policy in `vault/README.md`, Captain-ratified
2026-07-16): this is an officer-EXECUTABLE procedure — world lanes run it
after every world change — so it lives in the skill library where the
learning loops can improve it. A pointer stub remains at the old runbook
path. Root evidence: the 2026-07-08 world-alive review (measurements above;
`cabinet/dashboard/src/components/world/world-canvas.tsx` documents the
WebGL gotcha at the code seam).
