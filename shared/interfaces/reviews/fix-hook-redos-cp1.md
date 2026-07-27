# Checkpoint review — `fix/hook-redos` cp1

Reviewed-Scope-Digest: 14fb0d52815e4d787c79171d819d031f4c1fb9d659ae768717f9ef2d248a9ab5

Base: master `f77bcf45`. Scope: 7 paths, 741 added / 2 removed.

## What this closes

`policy_engine._WRITE_PATTERNS[1]` (the `sed -i` write matcher) is type
`bash_write_to_path`, which is in `policy-shadow._LEGACY_ENFORCING_TYPES` and is
reached from `pre-tool-use.sh:63` — its verdict is a live refusal, not a
recorded opinion. It nested `(?:[^;&|]|'[^']*'|"[^"]*")*` twice in one
expression. `[^;&|]` also matches both quote characters, so every quoted span is
tileable two ways and answering "no match" costs `2**(quote pairs)`.

Measured on the real shadow record, rebuilt read-only (`mode=ro`) with
`authority-matrix-dryrun.py --extract`: **52 of 80,307 recorded officer tool
calls exceed 1.5s in this one policy**. Smallest corpus reproducer 889 bytes
(an ordinary multi-line heredoc, 20 single + 48 double quotes) at 2.5s; largest
5,414 bytes, >30s. The hook has **no time bound** anywhere
(`pre-tool-use.sh:63`/`:72`, `policy-shadow.py`, `policy_engine.py` — all
unbounded), so such a command pins the officer's own gate at 99% CPU
indefinitely with nothing reporting it.

## Two ambiguities, and a first draft that only killed one

The obvious rewrite — require the quoted alternative to CONTAIN a separator —
removes the tiling ambiguity and is language-identical. **It was still
exponential.** Written `'[^']*[;&|][^']*'`, a span holding *s* separators has
*s* parses, and that unit sits inside the outer star, so the cost becomes
`s**k`. A hostile sibling sweep broke that draft in **110 bytes**
(`sed ` + `';;'`×26), and on realistic shapes: `sed -i.bak -e 's/;;/;/g'`×16 at
245 bytes, a 635-byte multi-line agent script.

The first bench missed it because every pump used ONE separator per span —
exactly the case that stays fast. The landed form anchors each span on its
FIRST separator (`[^';&|]*` before the `[;&|]`), leaving one parse. Both pumps
are now in the suite, and **neither alone catches both defects** — verified by
hash against three trees:

| tree | `TestWritePatternBacktracking` |
|---|---|
| master `f77bcf45` | 4 arms FAIL (quote-tiling pump) |
| the broken first draft | 8 arms FAIL (multi-separator pumps) |
| landed | 31 pass |

## Equivalence — the rule is not narrowed

Proved in both directions, then checked three independent ways.

*Proof.* In any tiling of the old star, rewrite every quoted span containing no
separator as its individual characters (each is a non-separator, so `[^;&|]`
accepts it). What survives is separator-free runs joined by spans that DO
contain a separator — exactly the new form. Conversely each new alternative is a
subset of an old one. A span contains a separator iff it contains a first one,
so anchoring on the first does not change the set.

| check | volume | mismatches |
|---|---|---|
| exhaustive, star language, class-complete alphabet ≤ len 8 (full-accept + maximal-prefix) | 6,725,601 | 0 |
| exhaustive, full pattern over token compositions | 41,371 | 0 |
| **replay of the real corpus through `evaluate_policy`** | **80,307** | **0** |
| independent reviewer's own fuzzer (random + structured + unicode + flag variants) | 3,560,000 + 97,944 | 0 |

Corpus replay detail: **80,271 identical verdicts, 0 different**, 36 records
where the OLD pattern could not finish inside 45s (that inability IS the
defect; the new pattern answers all 80,307 with none over 0.5s). Total engine
time 145.5s → 0.8s, excluding the 36 that never finished. The replay binds
master's patterns from `git show` against the WORKING FILE's patterns, and
asserts exactly index 1 differs — it measures shipped bytes, not a
transcription.

## The timeout — fail closed, and why

Defence in depth, not the fix. One wall-clock budget for the whole typed-policy
evaluation; a breach returns `decision=block` naming the policy.

It must NOT fall through to the regex shadow like every other exception in
`_engine_decision`, for two reasons. A gate that cannot compute a verdict does
not know the call is safe — allowing on "I don't know" is a fail-open in the
enforcer. And falling through would make a slow regex a **bypass primitive**:
craft an input that wedges the classifier and be judged by the weaker fallback
instead. Fail-closed makes the same input a self-inflicted, legible refusal.

Demonstrated end-to-end on a still-slow pattern (the perl residual, 2,401
bytes): unbounded >20s and still running; bounded returns
`block / no_product_workspace_write_eval_timeout` in 2.03s.

## Adversarial review findings — all taken

A fresh-context reviewer was given the staged bytes with instructions to break
them. It returned CHANGES REQUIRED with 8 items. Every one is fixed here.

1. **`inf` budget disabled the typed engine.** `_eval_budget` rejected
   non-numeric and negative but not non-finite; `inf` parses, then `setitimer`
   raises `OverflowError` (confirmed: *timestamp out of range for platform
   time_t*), which the blanket handler turned into a silent fall-through to the
   regex shadow — a one-env-var bypass, and `0` (the documented disable) was
   safer than `inf`. Now rejects NaN/±inf and clamps to 60s. Arm added.
2. **Straggler SIGALRM.** A signal generated just before disarm is delivered
   after it; the reviewer reproduced both an escaped `_PolicyEvalTimeout` and a
   process death (exit 142). Now an armed-flag makes a late alarm a no-op, and
   teardown order is flag → timer → handler. The outer handler also converts an
   escaped timeout to `block` rather than `None`.
3. **A non-sensor test.** `test_alarm_handler_is_restored` passed against master
   and walked only the fast path — it could not see defect 2. Added
   `test_alarm_state_is_clean_after_a_TIMEOUT` plus a ten-breach loop.
4. **Per-policy vs total bound.** Eleven policies load, so the real worst case
   was 11× the number the docstring guaranteed. The budget is now a TOTAL
   deadline across the loop, with an arm proving it.
5. **The `sed` pattern is still CUBIC on a third axis** — the flag-alternation
   split point × `re.search` restarting at each `sed`. Independently re-measured
   here: 2,813 bytes 0.98s (master 1.00s), 4,865 bytes 5.30s (master 5.29s) —
   **not a regression**, but not closed either. Declared as RES-019(a), pinned
   by a characterisation arm, and the class docstring no longer reads as
   "bounded on all input".
6. Contract row said 22,621 token compositions, the report said 41,371 — one
   was stale. Both now 41,371.
7. The report scoped the germline caveat to `policy-shadow.py`, but
   `policy_engine.py` is in the same schg set, so **the ReDoS fix is equally
   repo-only** until a Captain ceremony. Corrected — this matters: the live hook
   still carries the exponential pattern today.
8. "Cost is bounded and visible" corrected to state the total-budget semantics.

Reviewer verdicts on the rest: language equivalence PASS (its own fuzzer, 3.6M
cases, zero disagreements); budget row PASS (true delta measured as exactly 1,
not padded; row is load-bearing — deleting it REDs the census); sensor quality
PASS apart from item 3.

## Sibling sweep — method and results

Two methods, reported as different claims. **Mechanical:** every Bash command in
the 80,307-record corpus timed per pattern with a SIGALRM bound (attribution:
all 52 breaches to index 1, none elsewhere); plus targeted pumping of every
pattern on the enforcing path at 8/12/16/20/24 repetitions. **Structural:** a
full inventory of every regex reachable from `evaluate_policy` for the six
enforcing types and from the `_regex_decision` fallback, each classified for
the ambiguity signature.

Can be made slow: the `sed` flag axis (cubic, 2.8KB→1s), `perl` (degree ~4,
601B→2.5s, 1.2KB→>5s), the brace expander (quadratic, ~80KB), and the fallback
rm/write-verb patterns (cubic/quadratic, 2KB–120KB, fallback path only). All
four are declared in RES-019 and bounded by the timeout. Attempted and could not
be made slow: the tee/patch/cp/mv/rsync/tar patterns and their relaxed variants,
the interpolated path sub-patterns, the shell-parser primitives, and all 89
`path_block` globs (`fnmatch.translate` emits backtrack-free constructs on both
3.9.6 and 3.12). `command_contains` and `tier2_isolation` evaluate no regex at
all.

## Interpreter

The hook invokes bare `python3` = **3.9.6** on the target, which has no
`(?>...)` and no `*+`. The landed pattern uses neither, and compiles and matches
identically under 3.9.6 and 3.12.13 (both verified). Atomic groups would also
have been WRONG: emulating one with the 3.9-compatible `(?=(X))\1` idiom on the
perl pattern made `perl-i/workspace/a/` stop matching — a silent narrowing of an
enforcing safety rule. That measurement is why the perl pattern was left alone
rather than guessed at.

## Gates

framework 6,984 passed (1 pre-existing red, `test_retro_shim.py::test_reexports_constants`,
identical on master) · cabinet/scripts/tests 4,841 passed · lib tests 488 passed
· golden evals 32/32 · census PASS at zero headroom (69316 ≤ 69316, allowance
`additional: 1` = the true measured delta) · layer-sep new=0 · import gate OK ·
A13 parity 353 ids · residuals register 9 passed · COG-4 review binding OK.

Verdict: PASS
