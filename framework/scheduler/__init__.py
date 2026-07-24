"""framework.scheduler — the deterministic SHADOW scheduler (COG-4 §7).

A pure planner over a versioned wake-snapshot: `snapshot` builds the declared
input record from the cortex/objectives serve surfaces + declared parameters
(§7.1), `fold` is the pure function snapshot -> schedule store (§7.2), and
`serve` is the ONE kernel-bound loader every public read routes through
(§6.3/F1). Store discipline rides the C3 projection kernel
(framework.projection): atomic writes, MANDATORY-present rows-hash, verified
single-read serve; writers per cache_dir are serialized by an O_EXCL lockfile
(§7.5). SHADOW-ONLY this phase: nothing here executes, dispatches, or renders
launchd jobs — the separate dispatcher (§7.3, W5) rechecks authority, budget,
freshness and idempotency against live state and even IT never executes.

The six forbidden powers (§7.2) are structural in this tree: no objectives
writes, no learning/self-extension imports, no authority imports, no
acting/frontdoor imports, no subprocess/os.system/socket, the policy version
is a snapshot INPUT echoed untouched, and no consequence/evidence/trajectory
write path exists — pinned by the §8.3 boundary rows and the §8.4 scheduler
AST pin (test_cog4_scheduler_ast_pin.py).

IMPORT-INERT BY DESIGN (the framework.projection idiom): this package root
imports NOTHING at module load — the transitive-closure gate subprocess-
imports `framework.scheduler` and asserts its forbidden-namespace closure is
EMPTY. Import framework.scheduler.{model,snapshot,fold,serve} explicitly.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; COG-4 W3 u2 (scheduler on the kernel).
"""
from __future__ import annotations

__all__: list[str] = []
