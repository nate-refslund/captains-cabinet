# Portfolio-preset measurement seed (org-discipline scenarios)

The portfolio preset runs lane CEOs behind a Chair rather than the work
preset's five functional officers, so it ships the GENERIC org-as-a-system
scenarios only — no per-role evals (those are role-specific to the
five-officer archetype; see `presets/work/measurement/role_evals/`).

## Contents

- `scenarios/` — the 5 org-discipline scenario evals (`role_adaptation`,
  `role_retirement`, `policy_enforcement`, `outcome_to_mission`,
  `outcome_to_verified`), byte-identical to the work/developer seed. They
  validate that the org can safely adapt roles and apply learning regardless
  of roster shape; none hardcode a roster or product.

## Why this seed exists (audit #27)

The self-improvement validation gate
(`framework/learning/self_improvement_loop.py`, `_run_scenario_evals_for_validation`)
runs the `role`/`learning` scenarios as its org-safety check and now **fails
closed on zero scenarios** (same discipline as the golden-eval shells gate,
audit #21). Without a seed the gate would previously report green *without
measuring* — a vacuous pass on the default portfolio shape. `load-preset.sh`
copies this into `instance/measurement/scenarios/` at hatch so the gate has
real scenarios to run.
