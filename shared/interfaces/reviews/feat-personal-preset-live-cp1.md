# feat/personal-preset-live — checkpoint 1 (FW-019)

**Unit:** unblock `presets/personal/` (the north star's own altitude, shipping
inert), bind a working recall source for the personal flavor, and change the
briefing scale's rung 3.
**Adjudication of record:** `docs/plans/personal-preset-live-2026-07-27.md`
(two blind arms, 2026-07-26; arm B won all four divergences).

---

## What changed, and why each piece is load-bearing

| Surface | Change | Why |
|---|---|---|
| `framework/sources/local.py` (new) | `LocalNotesSource` — bounded, realpath-jailed, read-only recall over one declared folder | `flavor: personal` emitted no `sources.yml`, so recall fail-closed to `NullPersonalSource`: `available()` False, `search()` no hits |
| `cabinet/scripts/generate-instance.py` | emits `sources.yml` on BOTH flavors; personal binds the local adapter with `local_root:` | the emission gap was the mechanism of the inertness |
| `cabinet/scripts/hatch.sh` | `do_set_preset` honours an explicit `cabinet.preset` | it read `org_shape` only, so `preset: personal` was accepted by the generator, printed in its next steps, then discarded by the chain that runs them |
| `presets/personal/` | README rewritten (no longer forbids activation); `validate.sh` added; measurement seed added; navigator/librarian/reviewer role cards added | each was an independent gate the preset could not pass |
| `cabinet/scripts/lib/briefing_score.py` | rung 3 `"I'd act on it"` → `"changed what I did next"`; summary states it is not comparable across operators | the old rung measured the operator's authority, not the cabinet's quality — a permanent 2 at employee altitude |
| `cabinet/config/cognitive-architecture-contract.yml` | two `temporary_allowances` rows + one `expansions` row | both mass budgets were at zero headroom; the module is a registered set member |

## Verification run for this checkpoint

- Census: **PASS**, 245 ≤ 245 modules / 69985 ≤ 69985 lines, expansion row
  registered and its `merge_refuted` anchor + `consumer` resolve.
- Layer separation: `new=0` (the module reads instance config only through
  single joined string literals, the `env.py`/`sources/__init__.py` idiom).
- Axis linter: 34 passed — no framework code branches on `flavor` to select the
  adapter; the binding is data in `sources.yml`.
- `framework/sources/tests` 55 passed, including arms that fail against the
  pre-change tree: real ranked hits from a real folder, resolver binding,
  traversal + symlink-escape refusal, file/byte caps, `content_ts` derived or
  `None` (never mtime), and no write verb anywhere on the module.
- `presets/personal/validate.sh` passes; both of its new arms proved to FAIL
  against a violating fixture (a `cto` archetype; a removed scenario seed).
- **End-to-end personal hatch, executed:** answers → `generate-instance.py`
  → hatch preset step (`active-preset = personal (from answers cabinet.preset)`)
  → `load-preset.sh` (`Loading preset: personal`, 5 staged, measurement
  scenarios seeded) → `first-briefing.sh --local` → receipt with 3 proposed
  outcome cards. `get_source()` resolved to
  `framework.sources.local:LocalNotesSource`, `available()` True, and returned
  two dated, cited hits from the operator's folder;
  `get_dispatch()` stayed `NullPersonalDispatch`.

## Honest limits of this checkpoint

- **Card composition is unchanged.** Genesis still derives cards from the
  answers file, so a personal hatch's first briefing is real and gate-passing
  but its *content* is not preset-shaped. That is the ordering inversion —
  resulting-order item 2 of the same gate — and a separate unit. Stated in
  `docs/plans/personal-preset-live-2026-07-27.md` §5 rather than papered over.
- **Recall is exact-term over one folder**, not an ingest engine and not
  cross-source. It is deliberately the smallest thing that is actually live.
- The two inverted generator tests previously asserted "no `sources.yml` for
  personal". Those assertions were literally true and were the defect; both are
  inverted in place with the reason recorded in the test docstring, per the
  no-weakening rule.

## Disclosure

An early `load-preset.sh` run in the hatch rehearsal was launched without
`REDIS_PORT` pointed at a spare port, so it reached the live Redis on 6379 and
issued `SET cabinet:officer:expected:cos active` — the value that key already
held for the live Chair. No other key was written and no fleet action followed.
Every subsequent run used port 6399.

Verdict: PASS
