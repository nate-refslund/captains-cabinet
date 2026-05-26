---
globs:
  - "framework/missions/**"
  - "framework/ovi/**"
  - "instance/config/outcomes.yml"
---

# Mission & OVI Rules

- Outcomes are Captain-declared — never auto-create outcomes.
- Missions compile from outcomes via `framework/missions/compiler.py`.
- Work graphs are DAGs — cycle detection is mandatory before activation.
- Tasks are assigned to roles by capability matching against `framework/roles/lifecycle.list_roles()`.
- OVI components have weights that must sum to 1.0.
- OVI trend detection compares current snapshot to previous — up/down/flat.
- Inverse-direction components (e.g., captain_attention_cost) normalize so lower raw = higher score.
- Every mission compilation and OVI snapshot emits an event.
