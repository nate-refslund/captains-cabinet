# Checkpoint review — `feat/p1-staged-rebuild-real` cp1 (FW-019)

Reviewed-Scope-Digest: 3e05f69f93e3a246fecc358f40a71540cca62ef83a5af3809efee7d0f83cd9ab

**Scope:** the web door builds again. Four files:
`cabinet/dashboard/src/lib/updates.ts` (split),
`cabinet/dashboard/src/lib/updates-view.ts` (new, the pure half),
`cabinet/dashboard/src/components/updates/update-card.tsx` (one import),
`.../update-card.test.tsx` (the arm that keeps it that way).

## The defect being closed

`next build` has FAILED on this tree since the update path landed
(`eecc600d`, 2026-09-07). Measured 2026-09-10 while building U5c's real staged
rebuild:

```
./src/lib/updates.ts:25:1
Module not found: Can't resolve 'child_process'
  #4 [Client Component Browser]:
    ./src/lib/updates.ts
    ./src/components/updates/update-card.tsx
  #5 [Client Component SSR]: (the same two)
```

`update-card.tsx` is a client component. It imports three symbols from
`@/lib/updates` — a type, the Apply gate, the refusal selector, all pure — and
importing ONE symbol from a module pulls the WHOLE module into the browser
graph, `child_process` exec seam included. A browser has no `child_process`, so
the build refuses the whole thing.

**Three days unbuildable, zero reds.** Nothing in this repository ran a
dashboard build: CI installs the dashboard's dependencies twice (the world
capture, the vitest job) and never builds it, and the acceptance drill's P7
always passed `--skip-rebuild`. The suites were green the entire time — vitest
transpiles per module and never assembles a client graph, so the one thing that
could see this was the one thing nobody ran.

## What changed, and why each choice

| Choice | Reason |
|---|---|
| A new `updates-view.ts` holding the pure half — types, the two regexes, `refusalToShow`, `applyTarget`, `refusalHeadline`, `updateHeadline` | the browser graph must be able to reach the card's inputs without reaching an exec seam; a boundary is the only thing that makes that structural rather than remembered |
| `updates.ts` keeps the exec seam and `export *`s the view | every server-side importer (`page.tsx`, `actions/updates.ts`, `lib/updates.test.ts`) still says `@/lib/updates` and needed no change at all — the split costs one import line in one component |
| Only `update-card.tsx` (and its test) point at `updates-view` | it is the only client component in the update surface; a wider repoint would be churn with no property behind it |
| The regression arm lives in the CARD's suite, not in a lint | it is the card's own property: what this component may drag into a browser. Milliseconds, and it names the exact build error in its comment |
| No `server-only` marker | that makes the failure louder, not absent — the build still has to resolve the module. The boundary is the fix; a marker would be decoration on top of it |

## What proves it

* `npx vitest run` — 3921 passed, 1 skipped (the new arm included).
* `npx tsc --noEmit` — rc 0.
* `CABINET_BUILD_SOURCE_COMMIT=<sha> npm run build` — **builds**, where the same
  command on `ae687861` exits 1 with the error quoted above.
* The durable sensor is not this commit: it is cp2's drill, which runs a real
  `next build` through the real updater in CI. This arm is the cheap half so the
  next person to reach for the exec seam from a client component learns it in
  40 ms rather than in a three-minute build.

## Residual

`updates-view.ts` holds the boundary by convention plus one test that greps its
own imports. A general rule ("no client component may transitively reach a node
builtin") would need a module-graph walk; the real build in CI is that walk, and
it now runs on every PR.
