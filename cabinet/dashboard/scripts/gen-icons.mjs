// gen-icons.mjs — dev-time icon pipeline (Wave D app-feel). Renders the
// committed PNG icon set from the single source of truth src/app/icon.svg.
// The PNGs are COMMITTED (this script is not part of any build/start path);
// re-run it after editing icon.svg:
//
//   node cabinet/dashboard/scripts/gen-icons.mjs
//
// Zero new dependencies: `sharp` is already a cabinet/dashboard dependency
// (0.34.x). The ESM bare specifier resolves from THIS script's location up
// to cabinet/dashboard/node_modules/sharp regardless of cwd.
//
// Outputs:
//   public/icons/icon-192.png           192x192  full-bleed (transparent
//   public/icons/icon-512.png           512x512   rounded corners kept)
//   public/icons/icon-512-maskable.png  512x512  glyph scaled into the
//                                       central 80% safe zone, extended on
//                                       opaque #09090b (maskable purpose)
//   src/app/apple-icon.png              180x180  opaque #09090b (Next
//                                       auto-links apple-touch-icon; iOS
//                                       applies its own corner mask)
import { fileURLToPath } from 'node:url'
import sharp from 'sharp'

const BG = '#09090b' // globals.css --color-zinc-950; keep in sync with manifest.ts
const SAFE_ZONE = 0.8 // maskable spec: keep the glyph inside the central 80%

const p = (rel) => fileURLToPath(new URL(rel, import.meta.url))
const SVG = p('../src/app/icon.svg')

async function fullBleed(size, out) {
  await sharp(SVG, { density: 300 }).resize(size, size).png().toFile(out)
  console.log(`gen-icons: wrote ${out} (${size}x${size}, full-bleed)`)
}

async function maskable(size, out) {
  const glyph = Math.round(size * SAFE_ZONE)
  const inner = await sharp(SVG, { density: 300 })
    .resize(glyph, glyph)
    .png()
    .toBuffer()
  await sharp({
    create: { width: size, height: size, channels: 4, background: BG },
  })
    .composite([{ input: inner, gravity: 'center' }])
    .png()
    .toFile(out)
  console.log(`gen-icons: wrote ${out} (${size}x${size}, maskable safe-zone)`)
}

async function apple(size, out) {
  await sharp(SVG, { density: 300 })
    .resize(size, size)
    .flatten({ background: BG })
    .png()
    .toFile(out)
  console.log(`gen-icons: wrote ${out} (${size}x${size}, opaque)`)
}

await fullBleed(192, p('../public/icons/icon-192.png'))
await fullBleed(512, p('../public/icons/icon-512.png'))
await maskable(512, p('../public/icons/icon-512-maskable.png'))
await apple(180, p('../src/app/apple-icon.png'))
