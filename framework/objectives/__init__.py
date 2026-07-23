"""framework.objectives — the shadow causal objective/value graph (COG-3).

IMPORT-INERT BY DESIGN (contract rev-1 §6.5): this package root imports NOTHING
at module load. The transitive-closure gate imports `framework.objectives` in a
subprocess and asserts its forbidden-namespace closure is EMPTY — nothing under
framework.{authority,acting,frontdoor,fidelity,missions,ovi} may be reachable.
Submodules (model, states, query, ovi_view) are imported explicitly by callers.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; U1 (the derivation core).
"""
