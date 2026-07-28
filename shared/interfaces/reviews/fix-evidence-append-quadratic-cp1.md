# FW-019 checkpoint review — fix/evidence-append-quadratic cp1

**Verdict: SHIP**
**Date:** 2026-07-28 · **Baseline:** origin/master `60c30967` · **Branch:** `fix/evidence-append-quadratic`

Reviewed-Scope-Digest: a1036829cc1852c9352a3b3c82100b1f0fff606a7dee1ceec539ccedfd32e8c0

---

## 1. The defect

`EvidenceRecorder.append` verifies a trial before extending it, and the whole
trial was re-verified on **every** append: `_emit` → `evidence_mirror` →
`recorder.append` → `verify_trial`. That is O(n) per filing and O(n²) per
trial, with one `contains_secret_shape` walk per row per append. Then
`append` read the same file a **second** time with `_rows()` for the length
and the tip.

Measured on the production path (`file_need`, mirror pointed at a scratch
store, this machine, `python3.12`):

| trial depth | before | after |
|---:|---:|---:|
| 40 | 3.88 ms | 1.48 ms |
| 240 | 18.58 ms | 2.07 ms |
| 480 | 35.11 ms | 2.86 ms |
| 499 (R-8 envelope) | 36.64 ms | 3.06 ms |

Depth-dependence: **71.4 µs per prior event → 3.4 µs**, a 21x reduction.
Against the 50 ms hook budget the depth term went from 33 ms (65% of budget)
to 1.6 ms (3%). `MAX_MIRROR_EVENTS_PER_TRIAL` / `MAX_TRIAL_EVENTS` are both
500, so depth 499 is the live ceiling, not a hypothetical.

`docs/propose-means-propose-2026-07-27.md` had already **measured** this
(~102 ms per filing, correctly attributed to `verify_trial` and its 54k
`contains_secret_shape` calls) and treated it as a flat cost to rate-limit
around. It was not flat — it was the trial's depth. That doc carries a dated
correction in this commit.

## 2. What `verify_trial` protects, and how this preserves it

The append-time verification exists so a broken or truncated ledger cannot be
**laundered by being written over**: extend a truncated trial and the anchor
is re-signed at the new length, and the missing rows leave no trace.

The per-row checks — `_shape_errors`, schema/trial_id/sequence/previous_hash,
the recomputed `_digest`, the HMAC `_event_signature`, `contains_secret_shape`
— are a **pure function of (row bytes, position in the chain, signing key,
trial id)**. No clock, no environment, no filesystem. Therefore a prefix whose
bytes hash identical to bytes that already verified clean **under the same
key** yields, by identity of inputs, the identical verdict; only the suffix
can carry news.

`_verify_events` memoizes exactly that, in process, keyed on
`(resolved store root, trial id)` and pinned to:

* `digest` — sha256 over **exactly** the bytes the proof covers, re-read and
  re-hashed on every call (not stat, not mtime — an in-place edit can preserve
  size and forge mtime);
* `key_digest` — sha256 of the signing key that proved them;
* `length` — a shorter ledger can never satisfy the memo.

A prefix is memoized **only** when the whole ledger verified with **zero**
findings and ended on a `b"\n"` boundary. Any edit, truncation, reorder, key
change, partial tail or finding misses the memo and re-scans from byte zero.
The permission checks, the anchor block and `_watermark_check` are **not**
memoized — they are properties of the filesystem and of `anchor.json`, not of
these bytes, and run every call unchanged.

`recorder.append` now takes `event_count` / `last_event_hash` from that
verdict instead of a second `_rows()` pass. On `ok=True` the recomputed
`last_event_hash` **is** `rows[-1]["event_hash"]` — a divergence is an
`:event_hash` finding, which would make `ok` False. This also closes a small
TOCTOU window: the old code re-read the file after verifying it, so it could
act on bytes the verification never saw.

## 3. Mutation proof — every arm fails against the code it polices

**The sensor that could not see the defect.** `evidence_mirror._store_root()`
returns `None` under `PYTEST_CURRENT_TEST` unless a scratch store is supplied,
so `test_filing_latency_smoke` measured a filing that never reached the
recorder (~0.2 ms) — green forever, on the wrong half of the path. It now
supplies `CABINET_EVIDENCE_MIRROR_STORE` (the mirror's own sanctioned seam)
and fills a trial to the R-8 envelope, and the fixture **asserts the observed
depth** so it fails loudly rather than silently reverting to the cheap path.

| arm | vs pre-change code (60c30967) |
|---|---|
| `test_needs.py::test_filing_latency_does_not_grow_with_trial_depth` | **RED** — 34.4 ms growth vs a 10 ms allowance (shallow 1.54 ms @ depth 16, deep 35.89 ms @ depth 495) |
| `test_recorder.py::test_append_reverifies_only_the_new_tail` | **RED** — re-verified 40 events to write one, expected 1 |
| `test_needs.py::test_filing_latency_smoke` | **green at 35.89 ms** — see the honest limit below |

**Honest limit, stated not papered over.** The 50 ms budget arm does *not* go
red on this machine even on the production path: the pre-fix worst case is
35.9 ms, 72% of budget. The absolute number is fsync-dominated and varies
~10x across machines (the same measurement on a slower disk read 22 ms at
depth 40, which extrapolates past 50 ms at the envelope). That is exactly why
the depth-difference arm exists beside it: subtracting the shallow sample
cancels the machine constant and leaves only the term that is the defect. The
budget arm holds the spec's number; the depth arm is the sensor.

**Soundness mutations** — each applied to the shipped code, suite re-run with
`__pycache__` purged, each reverted afterwards:

| mutation | caught by |
|---|---|
| A: trust the memo without re-hashing the prefix bytes | 4 tests, incl. `test_memoized_prefix_still_catches_mid_ledger_content_tampering` |
| B: drop the signing-key pin | `test_memoized_prefix_still_catches_a_swapped_signing_key` |
| C: drop the store root from the memo key | **not caught** — see §4 |
| D: memoize a prefix that carried findings | `test_a_failing_verification_is_not_memoized_as_clean` |
| E: restart suffix line numbering at 1 | `test_warm_and_cold_agree_on_a_ledger_that_goes_bad_after_the_memo` |
| F: restart the sequence counter | 43 tests |
| G: restart the hash chain at ZERO_HASH | 31 tests |
| H: drop the memoized tip signature | 31 tests |

## 4. What this review found and did NOT fix

**Mutation C is not caught, and the docstring was overclaiming.** Keying the
memo on the trial id alone does not produce a wrong verdict: the byte digest
and the key pin already refuse a foreign ledger. The store root in the key is
**thrash avoidance, not a safety property**, and `_resolved`'s docstring now
says so instead of claiming a guarantee its own mutation disproves. The root
stays in the key because a cache keyed on the thing it describes is the
correct shape, not because a test proves it must be.

**Degenerate ends checked:** empty ledger (`raw == b""` → memo trivially hits,
suffix is the whole file, identical verdict); absent ledger (`_read_ledger_bytes`
returns `b""`, no findings, `event_count == 0`); symlinked ledger (bytes never
read, nothing memoized, `_private_path_error` still refuses it); partial tail
(never memoized); unreadable ledger (never memoized); memo eviction at 128
entries (costs a full re-scan, never a verdict).

## 5. Blast radius

`framework/evidence/verifier.py` `_read_event_lines` is split into
`_read_ledger_bytes` + `_frame_event_lines` (framing bytes are unchanged; the
only new parameter is `first_line`, which exists so a suffix scan reports the
line numbers a whole-file scan would). The one doc reference to the old name,
in `cabinet/scripts/governance-review.py`, moves in this commit.

Suites re-run by this review, not inherited from a builder:
`framework/` 7300 passed / 25 skipped (the one red,
`framework/fidelity/tests/test_retro_shim.py::test_reexports_constants`,
reproduces identically on unmodified `origin/master` in a separate worktree —
it pins `claude-sonnet-4-6` against a local screenpipe pipe that now reports
`claude-sonnet-5`; not this change, and CI is green on master at 60c30967);
`cabinet/scripts/tests` green; `verify-cognitive-architecture.sh`,
`check-layer-separation.sh`, `docs-track-code-sweep.sh`,
`ledger-status-parity.sh`, `cognitive-architecture-census.py --check` all
green.

## 6. Census budget and the COG-4 digest

`framework_production_noncomment_lines` is zero-headroom by law
(observed == maximum). +126 production lines (verifier +124, recorder +2;
tests cost this budget nothing) therefore need a `temporary_allowances` row —
`evidence-append-quadratic`, exact measured running total 71931 vs 71805
base (re-measured after merging origin/master `dd01ce8f`, which moved the base
from 71151; +126 is unchanged by that merge).
Most of those lines are docstring prose stating the soundness argument; it is
deliberately **not** reformatted into `#` comments to duck the counter, which
would buy a number with the reasoning a later reader needs.

That budget table lives in `cabinet/config/cognitive-architecture-contract.yml`,
which sits in COG-4's `restore_from_baseline` and is therefore digest-bound.
It is the ONLY digest-bound path this landing touches — verified mechanically,
not asserted, by intersecting `resolve_scope()` with this commit's changed
paths. The re-bind is recorded in the phase-4 review artifact per the re-bind-
at-landing procedure that artifact itself prescribes. No COG-4 implementation
byte moves.
