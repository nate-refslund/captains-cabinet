# COG-4 W3 u4 — objectives kernel adoption: PARKED (2026-07-24)

**Unit:** feat/cog4-w3-u4 (branched off feat/cog4-w3-u1).
**Deliverable (contract §6.4, second instantiation):** route
`framework/objectives/{model,graph,query}.py` digest / canonical-bytes /
rows-hash / manifest / verified serve through `framework.projection.kernel`
(u1-owned) under the byte-compat gate.
**Disposition:** **PARKED** — recorded debt, not silence (§6.4 / §13). Zero
objectives code changed; only this dated marker lands. The scheduler (u1, the
third instantiation) already proves the kernel independently, so the parked
adoption blocks nothing downstream.

## Why parked — a cross-corpus contradiction on the objectives boundary

Adopting the kernel REQUIRES a `framework/objectives/*.py` file to import
`framework.projection`. Two IMMUTABLE corpus artifacts disagree on whether that
import is allowed:

1. **The C2 module gate SANCTIONS it.** `cabinet/config/boundary-manifest.yml`
   ROW 6 (`framework.projection`) allowlists `framework/objectives/*` with the
   comment "second instantiation (§6.4)" (lines 330-331). So the module-level
   boundary gate explicitly permits objectives → projection.

2. **The COG-3 objectives SYMBOL pin FORBIDS it, and must never weaken.**
   `cabinet/scripts/tests/lib_cog3_import_ast.py:124-134` allows an objectives
   import only if it is stdlib, internal (`framework.objectives[.*]`), or
   `from framework.cortex.query import <one of the 7 enumerated symbols>` —
   EVERYTHING else (including `framework.projection`) is RED.
   `test_cog3_objectives_ast_pin.py::TestSymbolImportPin::test_real_tree_is_green_by_vacuity`
   (lines 56-58) asserts `objectives_import_violations(_REPO) == []` over the
   REAL tree. Contract **§8.4** and the **§3** disposition row both bind this
   pin as **"byte-untouched and never weakens" (MR7)**.

The adoption therefore cannot proceed without EITHER weakening the never-weaken
pin (a corpus edit — forbidden to a builder, and contradicting §8.4) OR a
covert/dynamic import (whose own docstring declares "evasion IS the violation",
lib_cog3_import_ast.py:30-34). No import spelling escapes — `from
framework.projection import kernel`, `import framework.projection.kernel`,
`from framework import projection`, and `from framework.projection.kernel import
digest, canonical_bytes` were all verified RED against the pin.

This is a genuine contradiction between two things the corpus asserts at once
(C2 ROW 6 says "allowed, §6.4"; the COG-3 symbol pin says "forbidden, never
weaken"). Cortex (u3) has NO symbol pin, so cortex adoption is consistent and
unblocked; objectives is the asymmetric case — it carries an extra COG-3-era
boundary pin that was never reconciled with the C2 §6.4 allowance.

## Recommended resolution (integrator's call — corpus adjudication, L1111)

The objectives symbol pin's own docstring already anticipates a **conscious**
amendment for a later wave that legitimately needs a new lane
(lib_cog3_import_ast.py:24-28, "amends this pin consciously… the G-m4 posture").
The minimal, surgical amendment: add `framework.projection` (the kernel) as a
sanctioned internal-kernel prefix alongside the 7 cortex symbols, leaving the
cortex 7-symbol restriction, the transitive-closure test, and the defaults-only
`as_of` pin fully intact — i.e. widen by EXACTLY the kernel and nothing else,
matching C2 ROW 6's explicit allowance. Then unpark and re-run this unit.
Alternatively, accept the park as permanent debt: objectives keeps its own
`canonical_bytes`/`digest`/rows-chain, which are ALREADY byte-parity-pinned to
the recorder/cortex/kernel (model.py header; kernel.py docstring (a)) — so the
duplication carries ZERO correctness cost, only lost code-unification. Either
path is the integrator's to choose; a builder may not edit corpus.

## Secondary gotcha for whoever unparks (empty-graph rows-hash)

`framework/objectives/graph.py:_rows_chain([])` returns `""` for an EMPTY graph,
and the manifest records `graph_rows_hash: ""`. Current serve passes (`"" ==
""`, query.py:214-215 `is not None and`). But the kernel's `verified_single_read`
(projection/kernel.py:264-269) REFUSES an empty-string store-hash (`not
expected`) — so routing `query.py:_load_bound` through the kernel would refuse an
empty-graph serve, a byte-compat break IF any test builds+serves an empty graph.
The §6.4 "becomes a kernel PARAMETER" path (allow the domain's legitimately-empty
rows-hash) is the fix; kernel bytes are u1-owned, so that parameter is a
u1/integrator change. The same "" case is why the query.py:214-215
skip-when-absent hole must be closed as "absent-key → refuse" ONLY (which leaves
`""` serving), never as "empty-or-absent → refuse" (which breaks empty graphs) —
they are NOT the same closure.

## Base-branch note (NOT this unit's)

At the feat/cog4-w3-u1 tip,
`test_cog4_scheduler_ast_pin.py::TestSchedulerTransitiveClosure::test_real_trees_are_armed_and_absent`
FAILS by design: u1 landed `framework/projection/`, tripping that vacuity
guard's "protected trees absent" assertion (its retirement condition is to arm
the real-tree closure scan — a corpus edit only the integrator can make). This
is inherited from u1, unrelated to objectives adoption, and reported for
integrator visibility.

Provenance: parked per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; COG-4 W3 u4.
