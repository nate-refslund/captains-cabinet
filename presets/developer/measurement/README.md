# Developer-preset measurement seed (five-officer archetype)

Concrete measurement content for the `developer` preset's five functional
officers (cos/cto/cpo/cro/coo) — the developer preset is a flat copy of
`work`, and this seed is the work seed byte-verbatim (same roster, same
scenarios; lineage: relocated out of the framework layer by egg row
**R006**, 2026-07-07, concrete tests riding along per the R050 pairing).
The framework keeps the MACHINERY only — `framework/measurement/`
{role_eval_runner, scenario_runner, _eval_registry, _scenario_registry,
eval_pattern_detector} — and ships zero concrete content; its runners
degrade gracefully (discover nothing) until a deployment installs a seed.

## Contents

- `role_evals/` — 10 per-role evals (mission compiler, work routing, outbox
  relay, event replay, OVI components, policy engine, DAG validation).
  Declared slugs use the five-officer archetype roster; at registration the
  framework resolves them against the deployment's live roster
  (`_eval_registry.resolve_role_slug`), so installing on a non-work roster
  attributes eval events to a loadable role (e.g. `cos`).
- `scenarios/` — 5 org-as-a-system scenario evals
  (outcome_to_mission, outcome_to_verified, policy_enforcement,
  role_adaptation, role_retirement).
- `tests/test_org_scenarios_developer.py` — the concrete-content tests
  (basename deliberately differs from the work twin: no `__init__.py` in
  either tests/ dir, so repo-root pytest collection needs distinct module
  names). They perform a miniature install into a temp root (seed copied
  verbatim, repo layers symlinked) and run the scenarios there, so they
  verify the seed from this repo with no manual install:
  `python3.12 -m pytest presets/developer/measurement -q`.

## Install semantics

A developer-preset deployment installs the seed by copying the content dirs
into the framework tree it runs from:

```bash
cp -R presets/developer/measurement/role_evals framework/measurement/role_evals
cp -R presets/developer/measurement/scenarios  framework/measurement/scenarios
```

The seed modules are written for that install location: each does
`sys.path.insert(0, <4 parents up>)` (repo root when installed under
`framework/measurement/…`) and imports the runners via their canonical
`framework.measurement.…` paths; `policy_enforcement.py` and
`cto_block_destructive.py` additionally import the engine as
`framework.authority.policy_engine` off that same root (CG-14 pull-down —
`cabinet/scripts/lib` no longer carries it) and resolve the policy layers
install-relative via `load_policies(<4 parents up>)`. Keep the files verbatim
here — do not "fix" the parent counts for this preset location (the tests
exercise them at a real install shape instead).

Once installed, the runners' directory discovery picks the content up with
no further wiring (`python3 -m framework.measurement.role_eval_runner`,
`python3 -m framework.measurement.scenario_runner`), which is what the
weekly role-evals cron and the self-improvement loop's scenario validation
gate consume.
