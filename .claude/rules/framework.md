---
globs:
  - "framework/**/*.py"
  - "framework/**/*.sql"
  - "framework/**/*.yml"
  - "framework/**/*.json"
---

# Framework Development Rules

- Framework code is universal — no product-specific logic, no deployment-specific config.
- All state changes MUST emit events via `framework.events.emitter.emit()`.
- New SQL tables use `CREATE TABLE IF NOT EXISTS` + `uuid-ossp` for IDs.
- Every Python module has tests in an adjacent `tests/` directory.
- YAML schemas are validated by JSON Schema files in `framework/schemas/`.
- Three-layer separation: framework (universal) → preset (product-type) → instance (deployment).
- Never import from `instance/` or `presets/` in framework code.
