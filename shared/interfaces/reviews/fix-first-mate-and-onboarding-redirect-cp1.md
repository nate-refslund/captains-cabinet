# Checkpoint review — fix/first-mate-and-onboarding-redirect (cp1)

Reviewed-Scope-Digest: 37cb4854924da02db24e207b7e945f5732f98cec97d5b6479a4b3eeaebd5e563

Clean-context self-review of the staged change (13 paths). Two independent
defects, both measured on the Captain's live install.

## F1 — the coordinator is "First Mate" everywhere a human reads it

**Defect.** Surfaces printed the raw slug uppercased where a name belongs. The
Captain saw "COS is offline" and rejected it: it is "First Mate", not "COS",
not "Chief of Staff", not "Chair". The root was `role.toUpperCase()` used as a
person's name in `card-cabinet.tsx`, plus two fallbacks in `config.ts` that
degraded a known officer to its shouted id.

**One source of truth.** New pure module `lib/officer-title.ts` holds
`OFFICER_TITLES` (the frozen ids → their human titles; `cos → First Mate`, no
parenthetical) and `officerTitle()`. Pure (no `fs`/`yaml`) so client and server
both import it without dragging Node built-ins into the client bundle. Known id
→ configured title; unknown custom lane → readable Title Case, never a raw
uppercased slug.

**Routed through it:** `card-cabinet.tsx` (the reported symptom — all 9 activity
strings), `officer-column.tsx` (task-board header), `display/page.tsx` and
`actions/cabinets.ts` (title fallbacks now degrade readably, and known officers
short-circuit to the map). `config.ts::getOfficerConfig` prefers the map for
known officers so the portfolio preset (no H1 heading) no longer falls through
to "COS"; the mock titles now reference the map. Agent-definition display name
aligned: `presets/portfolio/agents/cos.md` ("Chair" → "First Mate") — the
Captain's live preset. The `work` preset's cos.md is deliberately LEFT as its
ratified "Chief of Staff" base: `test_preset_developer_parity` pins developer as
a flat copy of work with `agents/cos.md` a ratified "First Mate" delta, so
editing work collapses that delta. A work-preset dashboard renders "First Mate"
anyway (the map wins over the agent heading), so nothing user-facing shows
"Chief of Staff"; unifying the preset prose is a separate ratified-design change.

**Identifier vs. display — left untouched (by design):** `cos` id, redis keys,
`TELEGRAM_COS_TOKEN` env-var names (`actions/officers.ts`, `docker.ts`), world
sprite slugs, `OFFICER_COLORS`/`ChartLegend` axis codes, and the cost mini-chart
(`HorizontalBars` renders `{d.role}` in a fixed 40px column — a compact
axis-code register, like a ticker, not a person-name surface). `framework/`
uses "Chair" as an internal prompt/comment nickname; that is not a dashboard
display name and is out of scope for this dashboard-measured fix (and would trip
the census gate). Agnosticism: no "First Mate" literal is added to `framework/`;
it lives in the instance/preset + dashboard-config layer. `check-layer-separation.sh`:
no new violation.

**Arm:** `officer-title.test.ts` — known id never renders as its uppercased
slug; the degenerate untitled lane degrades to Title Case not a shout; empty
input does not throw.

## F2 — unfinished onboarding lands on /onboarding

**Defect.** The Captain logged in, landed on `/`, and was "totally confused
about what to do now."

**Signal.** New `lib/onboarding/completion.ts` reads the onboarding core's OWN
durable record (`instance/onboarding/v2/state.json`, written by
`framework/onboarding/journey.py`): complete iff `charter.status === "ratified"`
AND `first_dividend` is set — exactly what the `ratify_charter` action stamps.
No invented flag. Everything short of that (no state file, charter pending,
purged/paused/revoked, unreadable) is NOT complete, so uncertainty resolves to
a redirect the operator can navigate out of — never dropping a not-yet-oriented
operator on the confusing home.

**Placement.** The redirect is in the authenticated home `page.tsx` (NOT
middleware — another builder owns it; NOT the layout, which also wraps
`/onboarding` and would loop), before either dashboard mode renders.

**Arm:** `completion.test.ts` — no state → redirect; ratified+dividend → home;
charter-pending / purged / ratified-without-dividend / unreadable → redirect.

## Gates
- `npx vitest run`: 3320 passed, 1 skipped (full suite) — incl. the two new arms.
- `npx tsc --noEmit`: clean.
- `check-layer-separation.sh`: no new violation.
- Guarded-token grep on the diff: no product slug / captain identity / score /
  killswitch literal introduced.
