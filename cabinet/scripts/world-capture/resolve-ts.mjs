/**
 * Extensionless-import resolver for running the dashboard's TypeScript straight
 * off disk with node's own type stripping.
 *
 * The dashboard's sources import './coastline', not './coastline.ts', because
 * that is what a bundler wants. Node's ESM resolver does not guess extensions,
 * so `node emit.ts` dies on the first relative import. This hook adds the three
 * candidates a bundler would try and nothing else — it never invents a module
 * that is not on disk, and a genuinely missing import still fails loudly.
 *
 * WHY NOT A BUNDLER: a build step between the layout and its capture is one
 * more artifact that can go stale, and the whole point of this harness is that
 * the frame it judges came from the SAME composeLayout the tests run.
 */
import { existsSync } from 'node:fs'
import { registerHooks } from 'node:module'

const CANDIDATES = ['.ts', '.tsx', '/index.ts']

registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('.') && context.parentURL) {
      for (const ext of CANDIDATES) {
        const u = new URL(specifier + ext, context.parentURL)
        if (existsSync(u)) return next(specifier + ext, context)
      }
    }
    return next(specifier, context)
  },
})
