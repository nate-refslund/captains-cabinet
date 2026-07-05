# instance/config/policies/ — Captain-locked instance policy layer

The third (instance) layer `policy_engine.load_policies` scans for typed
policies (`*.yml` / `*.yaml` only — this README is never loaded). It is
GERMLINE (D8, sovereign amendment 2026-07-05): schg-locked by
`cabinet/scripts/germline-lock.sh` and hook-blocked for officer writes, so no
officer or loop can drop a policy file here.

Two independent defenses, keep both:

- `load_policies` REFUSES any preset/instance policy typed `authority_matrix`
  or named `authority-matrix` (the framework floor always wins), and runtime-
  validates the merged floor fail-closed.
- This directory's lock closes the file-drop vector itself — even a policy
  that is not an authority matrix cannot be planted by an officer.

The Captain adds instance policies here in a germline unlock window
(`sudo bash cabinet/scripts/germline-lock.sh unlock` → edit → commit → `lock`).
