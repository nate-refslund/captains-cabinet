# The personal preset ships live — adjudication of record and what it bought

**Date:** 2026-07-27
**Gate type:** DIRECTION (two models, independently and blind), run 2026-07-26.
**Arms:** Fable 5 (arm A) and Opus 5 (arm B), own clones, identical prompt,
neither reading the other's output.
**Status:** adjudicated; arm B won all four divergences. This document is the
in-repo record of the two findings that produced the work landed here.

---

## 1. The finding

A blind gate arm measured that **every shipped preset stands up a C-suite for a
company the operator does not run** — `presets/work/agents/` and
`presets/developer/agents/` both ship cos/cto/cpo/cro/coo plus a compliance
officer, an operations officer and an executive assistant.

**The one preset shaped for a non-company operator was empty and FORBIDDEN.**
`presets/personal/README.md` said "Placeholder … Empty until Phase 2" and
instructed the reader not to write `personal` into
`instance/config/active-preset`. Three further mechanisms enforced that:

| Mechanism | Effect |
|---|---|
| No `validate.sh` | `cabinet/scripts/cabinet-bootstrap.sh` treats a preset with no `validate.sh` as a **hard-gate failure**, by name |
| No `measurement/scenarios/` seed | `framework.learning.self_improvement_loop._run_scenario_evals_for_validation` **fails closed** on zero role/learning scenarios |
| `flavor: personal` emitted no `sources.yml` | recall fail-closed to `framework/sources/null.py` — `available()` False, `search()` returns no hits |

So the altitude the north-star ruling names as the **majority** case — *"a
developer at a large software company doesn't get to run the company, but the
cabinet should help expanding the developer's capability"* — was the one
configuration that shipped inert. That is not an oversight; it is the hole made
visible, and both arms independently reached that reading of the evidence.

## 2. What is true now

- `presets/personal/` is **activatable**: README rewritten, `validate.sh` added
  (with two arms the other presets do not need — no C-suite archetype, and a
  measurement seed present), a role-category scenario seeded, and three working
  roles added — **navigator**, **librarian**, **reviewer** — beside the two
  existing coaches. No C-suite.
- `autonomy.flavor: personal` now emits an `instance/config/sources.yml`
  binding `framework.sources.local:LocalNotesSource`: exact-term recall over
  one declared folder, realpath-jailed, capped, dates derived or absent (never
  mtime), **and no write side at all**.

**Adjudicated surplus member: `framework/sources/local.py`** (registered in
`cabinet/config/cognitive-architecture-contract.yml` under `expansions`, class
`framework_production_modules`, two arms, this document as its adjudication).
The merge question is answered by grep rather than prose: `null.py` is the
fail-closed default the resolver binds when `sources.yml` is absent or damaged,
so teaching it to read a directory would put file I/O on the failure path; and
`org.py`'s `search()` shells to `memory.sh`, which needs a connection string
and an embedding provider that the box this serves does not have, so binding it
there buys the same empty the null adapter already gives. Its consumer existed
first: `framework/sources/__init__.py` `get_source()` importlib-loads and binds
it from config.
- `cabinet/scripts/hatch.sh` honours an explicit `cabinet.preset` answer. It
  previously read `org_shape` only, so a hatch whose answers declared
  `preset: personal` was accepted by the generator, printed in its next steps,
  and then silently discarded by the chain that runs them.

Proven by hatching, not asserted: a personal-flavor answers file →
`generate-instance.py` → the hatch preset step → `load-preset.sh` →
`first-briefing.sh --local` → a receipt carrying proposed outcome cards, with
`get_source()` resolving to the local adapter and returning real, dated,
cited hits from the operator's folder.

## 3. The value bar: rung 3 changed

`cabinet/scripts/lib/briefing_score.py` rung 3 was **"I'd act on it"**. That
conflates the quality of the item with the operator's **authority** over it. At
founder altitude "act" means ratify an outcome; at employee altitude the honest
answer to a genuinely excellent briefing is often *"I can't act on that, it
isn't mine"* — a permanent 2, so the ceiling was set by the org chart rather
than by cabinet quality, and the 2→3 transition could never fire.

Rung 3 is now **"changed what I did next"**: reachable at every altitude, and
still a number the operator typed about the cabinet's output, so the
never-a-score exemption (EVAL-025) holds unchanged. Two free rules landed with
it — the summary states in its own output that it is **not comparable across
operators**, and `unscored` stays in the readout.

**Deliberately NOT built: a per-altitude rubric.** Both arms refused it
independently; a second scale is a second instrument nobody asked for.

## 4. The promise, corrected

Growth at this altitude is **CONTEXT AND LEVERAGE, NOT PERMISSION.**

The six hard ceiling classes — external comms, production deploys, spend,
secrets, network writes, credential grants — belong to whoever owns the
resources. A grant is valid only when signed by the authority root, so inside
an employer's estate no posture, no trust ladder and no amount of earned
evidence can climb there. An authority ladder therefore has no rungs at this
altitude, and that is a property of who owns the resources, not a limitation of
the cabinet.

What survives, and is the stronger half: nothing prevents the operator from
holding a picture of their project and the organisation around it that no
individual at that altitude holds, assembled from systems they already
legitimately access, and from proposing with evidence nobody else can put
together. **Authority is granted downward and capped by the org chart; context
is assembled sideways and capped only by access.**

**No copy shipped with this preset may promise more autonomy over time at this
altitude.** It would be false, and the first person who reads it and hits the
ceiling would correctly conclude the framework lied to them. Pinned by
`cabinet/scripts/tests/test_personal_preset_live.py`.

## 5. What this unit deliberately did NOT do

The gate's resulting order has other items, and they are other units:

- **The ordering inversion** — making `lanes` derivable and having genesis and
  `run_briefing` consume a derived estate as first-class input. Genesis still
  composes its cards from the answers file, so a personal hatch's first
  briefing is a real briefing with real proposed cards but its *content* is not
  yet preset-shaped. That gap is unchanged by this unit and is stated here
  rather than papered over.
- The three entry modes, per-source ownership classes, structural read-only for
  non-owned sources beyond this one adapter, the first-time-list trajectory
  read, and the public README claim fix.
