/**
 * env.d.ts — the one Vite type the harness uses, declared narrowly.
 *
 * `import.meta.glob` is Vite's, and the dashboard is a Next project: its
 * `tsc --noEmit` gate sees this directory (tsconfig includes `**​/*.tsx`) and
 * has no idea what it is. The usual fix is `/// <reference types="vite/client" />`,
 * which pulls Vite's whole ImportMetaEnv and asset-module surface into a Next
 * program that then has two opinions about `import.meta.env`. One signature is
 * enough, so one signature is what this declares.
 *
 * No import and no export on purpose — that is what makes this file a global
 * script whose `interface ImportMeta` MERGES with the built-in one rather than
 * declaring a second, module-local type nothing sees.
 */
interface ImportMeta {
  glob<T = unknown>(
    pattern: string,
    options?: { eager?: boolean; import?: string }
  ): Record<string, T>
}
