---
globs:
  - "framework/policies/**"
  - "presets/*/policies/**"
  - "cabinet/scripts/lib/policy_engine.py"
---

# Policy Development Rules

- Policies are YAML definitions evaluated by the typed Python engine — NOT bash regex.
- Three layers: framework/policies/ (universal safety) → presets/*/policies/ (product-type) → instance overrides.
- The policy engine uses shlex for shell parsing — never add regex bypass patterns.
- Test every policy with both positive (must block) and negative (must allow) cases.
- The engine handles: eval wrapping, bash -c, env prefix, quote splicing, brace expansion, full paths.
- Policy YAML format: name, type, match criteria, message. See framework/policies/base-safety.yml.
