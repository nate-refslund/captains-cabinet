# COG-4 W3 u3 — PARK marker: cortex verified-single-read SERVE-BINDING adoption

**Date:** 2026-07-24 · **Unit:** W3 u3 (cortex kernel adoption, contract §6.4) ·
**Branch:** `feat/cog4-w3-u3` (off `feat/cog4-w3-u1`).

## What adopted (byte-compat, full `test_cog2_*` green 283/283)

`framework/cortex/belief.py` + `engine.py` now route these already-identical
disciplines through `framework/projection/kernel.py` (§6.1 letters).
`framework/cortex/query.py` is **byte-unchanged** this unit (its two kernel
touchpoints are the by-value (g) below and the parked (f2) serve-binding).

- (a) canonical bytes + recorder-dialect digest — `belief.canonical_bytes` /
  `belief.digest` → `kernel.canonical_bytes` / `kernel.digest`.
- (b) content-excluded identity law — `belief.compute_belief_id` →
  `kernel.identity_digest`.
- (c) parameterized chained rows-hash — `belief.chained_hash` /
  `belief.hash_canonical_rows` → `kernel.chained_rows_hash`
  (`ALGEBRA_SHA256_CHAIN`, the frozen `_BELIEF_HASH_SEED`, belief_id order,
  the `_sorted_row` domain normalize).
- (d) manifest envelope — `engine.build_manifest` → `kernel.manifest_envelope`.
- (e) atomic write — `engine._atomic_write` → `kernel.atomic_write`.
- (f, leaf only) the rows-not-bytes JSONL reader — `engine.read_beliefs_jsonl`
  → `kernel.read_jsonl_rows`.

## NOT routed by reference — (g) the canonical-cutoff pattern (by-value model)

`query._CANON_TS_RE` is **left as its literal `re.compile(...)`** — NOT
re-pointed at `kernel.CANONICAL_CUTOFF_RE`. The corpus deliberately keeps the
pattern a **by-value replica** in each shipped source:
`test_cog4_kernel_store.py::TestCanonicalCutoff::test_pattern_equals_both_shipped_replicas_by_value`
text-scans `framework/cortex/query.py` (and `framework/objectives/graph.py`)
for the EXACT `kernel.CANONICAL_CUTOFF_PATTERN` literal — "the kernel is the
extraction of those replicas", pinned equal by value, so a silent kernel-side
drift is caught rather than followed. Reference-routing removed the literal and
RED-ed that tripwire; the discipline is "mirror the value, pin equality" (kernel
docstring (g)), not "route by reference". So (g) is intentionally not adopted
and query.py stays pristine — the corpus corrected an initial over-reach.

Byte-compat proof: a real driver-built cortex store (fold → build_manifest →
write_projection → verify_store → load_beliefs_verified) is **byte-identical**
before/after — `beliefs.jsonl` sha `6aaa4472…`, `fold-manifest.json` sha
`9607902b…`, `belief_store_hash` `5ad8c9d7…`. `ENGINE_VERSION`/epoch untouched.

## What is PARKED — and why

The verified single-read **serve-binding** itself (`query._verified_rows`) is
NOT routed through `kernel.verified_single_read`, even though the kernel
expresses the identical shape (single read, mandatory-present rows-hash limb,
refuse-on-mismatch).

- **Root cause (load-bearing divergence, §6.4):** `kernel.verified_single_read`
  hardcodes its internal reader (`kernel.read_jsonl_rows`). Cortex's F4
  no-window property is pinned by `cabinet/scripts/tests/test_cog2_corruption.py`
  `TestServeTimeHashBinding::test_toctou_rebuild_between_hash_and_serve_cannot_slip_bytes`,
  which `monkeypatch.setattr(engine, "read_beliefs_jsonl", racing)` and asserts
  the serve performs **exactly one** read *through that symbol*. Routing the
  serve through `kernel.verified_single_read` bypasses `engine.read_beliefs_jsonl`,
  so the monkeypatch never fires (`calls["n"] == 0`) and the test REDs. The test
  is CORRECT (it pins a real property); the corpus is immutable (§13).
- **Byte-compat is NOT the blocker** — the served bytes are identical either
  way. The blocker is the kernel's un-parameterized reader.
- **Fix path (kernel PARAMETER, u1 owns the bytes):** add an optional
  `read_rows` callable to `kernel.verified_single_read` (default
  `kernel.read_jsonl_rows`). Cortex would then adopt the binding by passing
  `read_rows=_engine.read_beliefs_jsonl`, the monkeypatch would fire, and both
  byte-compat and the F4 pin hold. Filed as a **contradiction** to the
  integrator/u1 — this unit does not edit `framework/projection`.

## Standing

`query._verified_rows` remains cortex-local but its READ and HASH already reach
the kernel at the leaf ((f) reader + (c) chain), so the only un-adopted surface
is the ~14-line binding wrapper. The kernel's `verified_single_read` is still
proven by u1's kernel batteries and the scheduler (third instantiation). This is
recorded debt, never silence — retire this marker when the kernel gains
`read_rows` and cortex's `_verified_rows` routes through it.
