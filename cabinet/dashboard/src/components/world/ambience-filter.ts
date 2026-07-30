/**
 * ambience-filter.ts — the GPU half of the ambience remap.
 *
 * The whole of the lighting DECISION lives in lib/world/ambience.ts, is pure, and
 * is tested there. This file does one thing: hand that module's lookup table to
 * the GPU and index it per pixel. There is deliberately no colour arithmetic here
 * — a second opinion about what night looks like, sitting in a renderer where no
 * test can reach it, is exactly how the dusk hue shipped wrong for a week.
 *
 * WHY A FILTER AND NOT AN OVERLAY. An overlay is a decision per SCREEN POSITION,
 * and that is the defect this replaced (see THE AMBIENCE STRUCTURE LAW in
 * ambience.ts). A filter reading a lookup table is a decision per COLOUR: the same
 * input colour leaves as the same output colour wherever it sits, so the art's own
 * dither survives intact and ambience cannot add grain of its own.
 *
 * WEBGL ONLY, ON PURPOSE. Pixi's own renderer priority is webgl-first, the app
 * pins `preference: 'webgl'` beside this comment's reason, and this filter ships a
 * GLSL program only. A WGSL twin that nothing ever ran would be a second shader
 * that cannot be verified in a browser capture, which is the only place a shader
 * IS verified. `ambienceFilter` returns null for any other renderer and the caller
 * raises it as a render issue in the HUD — loud and dual-coded, never a silent
 * daytime frame at midnight.
 */
import * as PIXI from 'pixi.js'
import {
  LUT_SLICES_PER_ROW,
  LUT_TEX_H,
  LUT_TEX_W,
  ambienceLut,
  lutPixels,
} from '@/lib/world/ambience'
import { PALETTE_QUANT_BITS } from '@/lib/world/corpus-palette'
import type { DayBucket } from '@/lib/world/lighting'

const LEVELS = 1 << PALETTE_QUANT_BITS

/**
 * Quantize to the palette's own bit depth, index the slice grid, sample NEAREST.
 *
 * Pixi hands a filter PREMULTIPLIED colour, so the source is divided by alpha
 * before the lookup and multiplied back after: skipping that turns every
 * half-transparent edge pixel into the wrong entry, which reads as a dark fringe
 * around every sprite.
 */
const FRAGMENT = `
in vec2 vTextureCoord;
out vec4 finalColor;

uniform sampler2D uTexture;
uniform sampler2D uLut;
/** x = levels, y = slices per texture row, z = lut width, w = lut height */
uniform vec4 uLutShape;

void main(void)
{
    vec4 src = texture(uTexture, vTextureCoord);
    if (src.a <= 0.0) { finalColor = src; return; }
    vec3 straight = clamp(src.rgb / src.a, 0.0, 1.0);

    float levels = uLutShape.x;
    float perRow = uLutShape.y;
    vec3 bin = min(floor(straight * 255.0 / (256.0 / levels)), vec3(levels - 1.0));

    float col = mod(bin.b, perRow);
    float row = floor(bin.b / perRow);
    vec2 texel = vec2(col * levels + bin.r + 0.5, row * levels + bin.g + 0.5);

    vec3 lit = texture(uLut, texel / uLutShape.zw).rgb;
    finalColor = vec4(lit * src.a, src.a);
}
`

/** The LUT as a nearest-sampled data texture. One per bucket, cached. */
const textures = new Map<DayBucket, PIXI.Texture>()
function lutTexture(bucket: DayBucket, lut: Uint32Array): PIXI.Texture {
  let t = textures.get(bucket)
  if (!t) {
    t = new PIXI.Texture({
      source: new PIXI.BufferImageSource({
        resource: lutPixels(lut),
        width: LUT_TEX_W,
        height: LUT_TEX_H,
        format: 'rgba8unorm',
        // DATA, not colour: premultiplying the table would scale every entry,
        // and interpolating it would blend one blue slice into the next.
        alphaMode: 'premultiplied-alpha',
        scaleMode: 'nearest',
      }),
    })
    textures.set(bucket, t)
  }
  return t
}

/**
 * The filter for a bucket, or `null` when this bucket changes nothing (day) or
 * this renderer cannot run it. Cached per bucket — a filter rebuilt every frame
 * re-uploads the table every frame.
 */
const filters = new Map<DayBucket, PIXI.Filter>()
export function ambienceFilter(
  bucket: DayBucket,
  renderer: PIXI.Renderer
): PIXI.Filter | null {
  const hit = filters.get(bucket)
  if (hit) return hit
  if (renderer.type !== PIXI.RendererType.WEBGL) return null
  const lut = ambienceLut(bucket)
  if (lut === null) return null
  const filter = new PIXI.Filter({
    glProgram: PIXI.GlProgram.from({
      vertex: PIXI.defaultFilterVert,
      fragment: FRAGMENT,
      name: `ambience-${bucket}`,
    }),
    resources: {
      uLut: lutTexture(bucket, lut).source,
      ambienceUniforms: new PIXI.UniformGroup({
        uLutShape: {
          value: [LEVELS, LUT_SLICES_PER_ROW, LUT_TEX_W, LUT_TEX_H],
          type: 'vec4<f32>',
        },
      }),
    },
  })
  filters.set(bucket, filter)
  return filter
}
