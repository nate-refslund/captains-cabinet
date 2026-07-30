# fix/script-agnostic-recall — cp1 self-review

Reviewed-Scope-Digest: e25eaf9e94cb08d3b2a25d287c20549ad4a8c781fb86b01d5dba85b300ce9657

Scope: 8 staged paths. `framework/onboarding/salience.py`,
`framework/onboarding/journey.py`, `framework/onboarding/genesis.py`,
`framework/sources/local.py`, `framework/onboarding/tests/test_salience.py`,
`framework/tests/test_script_agnostic_finding.py`,
`cabinet/config/cognitive-architecture-contract.yml`,
`docs/plans/declared-residuals-register.md`.

## What this changes, in one line

Four ASCII character classes decided what a word is in the FINDING path. They
now read one Unicode-aware splitter, and two things downstream of them (a
probe-pattern allow-list, a recall subject list) stop being ASCII-only too.

## The four class-11 questions, asked of this diff

**1. Does each arm FAIL against pre-change code — both directions, cache
purged?** Yes, and it was run rather than reasoned about. A detached worktree
at `origin/master` (363c9fa2), the new suite copied in, every `__pycache__`
removed, `PYTHONDONTWRITEBYTECODE=1`:

```
14 failed, 15 passed
```

The 14 are the arms that name the defect (a Japanese seed, a Cyrillic seed, a
mixed-script seed, a single ideograph, a Japanese probe pattern, a Japanese
join, a Japanese query, a Cyrillic query, a Japanese quote, the own-word
subjects, the seed-carried subjects, the subject cap, and the two arms pinning
the punctuation divergence). The 15 that pass pre-change are the ones that
MUST: every ASCII pin, every traversal refusal, every degenerate end. An arm
that passes in both directions is doing its job only if it is a pin — and each
of those is a pin. Post-change: 29 passed.

The seam's own arms live in `test_salience.py` instead, and they would fail
pre-change on an AttributeError rather than an assertion. That is a weaker
proof, which is exactly why the consumer arms were written against public
entry points that existed before this branch — a suite that cannot execute
against the old code proves the code is old, not that the sensor works.

**2. What happens at the degenerate end — zero, empty, absent, null?** Pinned
per consumer and at the primitive: `""`, `"   "`, punctuation-only in Latin
AND in CJK (`。。。 、、、`), `None`, a non-string, a list, a dict, a query
carrying no term, a purpose carrying no word, an operator who declared
nothing. Two of these are the load-bearing ones. `salience.terms(17) ==
["17"]` is pinned SEPARATELY so the "everything unusual is empty" line above
it cannot be read as a rule it is not. And `recall_probes({}) == []` keeps the
rule this whole derivation rests on: no source, no declaration, no sentence ⇒
no probe. The own-word subjects could have quietly turned "nothing to ask
about" into "ask about anything", and the arm that would catch that is there.

The single-character case is the one a length floor eats. `terms("日",
min_len=4) == ["日"]` — the floor applies to spaced scripts only, and the
sensor for it is `terms("of", min_len=4) == []` in the same arm, so a floor
that stopped applying anywhere would fail.

**3. What does the test environment guarantee that production does not?**
Three answers, and one of them is a real residual.

* The temp-folder arms build the corpus themselves, so they never depend on a
  developer's own notes folder. `LocalNotesSource(str(root))` is the same
  constructor override the existing adapter suite uses.
* The fixtures are three notes. Production is up to `MAX_FILES` (500) with
  `MAX_CHUNKS_PER_FILE` (40) — 20k chunks, each carrying a `tf` dict. Bigram
  emission multiplies the term count of an unspaced corpus by roughly the
  character count, so an all-CJK folder builds a bigger index than an English
  one of the same byte size. Bounded by the existing caps (the byte cap is
  256 KB/file, unchanged), and the distinct-bigram vocabulary of a real script
  is a few thousand, not one per character. Not measured at 500 files; the
  caps are what stand between it and unboundedness, and they are untouched.
* `git grep` and the CI runner see the same tree, but a LOCAL run of
  `framework/fidelity/tests/test_retro_shim.py::test_reexports_constants` reds
  on this machine because it reads a screenpipe pipe directory outside the
  repo. It reds identically on pristine `origin/master` (verified) and master's
  CI is green at 363c9fa2, so it is environment, not regression. Named here
  because "one red in the full suite" is exactly the shape a real regression
  wears.

**4. Is each sensor wired to the LIVE artifact?** The ASCII pins are the
answer worth checking. They do not compare the new code to itself: each one
writes the RETIRED character class out inline (`_OLD_SEED_RE`,
`_OLD_CONTENT_RE`, `_OLD_LOCAL_RE`, `_OLD_GENESIS_RE`) and grades the live
function against it. A pin that re-derived its expectation from the code under
test would pass whatever that code did — which is the failure this repo has
found ten ways. The oracles are dead in the tree and alive only in the test
file, so they cannot rot back into the thing they grade.

The residual-register row is wired the same way: its anchor is checked against
the live docstring by `test_declared_residuals_register.py`, which fails if the
paragraph is deleted or duplicated.

## What I attacked and did NOT find a defect in

* **The traversal allow-list.** `_PROBE_PATTERN_RE` became a function, which
  is the natural place to lose a containment rule. The existing pinned arm
  (`../outside/*`, `ci/cd*`, `/etc/passwd`, `safe*`) is unchanged and green,
  and the new arm adds `.hidden*`, `日本/../x`, a leading combining mark,
  an embedded space, a backslash, `$(x)`, a quote, an embedded newline and a
  65-character pattern — all refused, with `safe*` still executing so a
  function returning `False` unconditionally cannot pass. What is allowed grew
  by exactly one thing: word characters the Unicode database recognises.
* **`name_tokens` / `tokenize`.** They feed the RANKING, whose re-rank was
  measured on a live 665-name estate before RES-025 landed. They read
  `split_words` directly and take neither the script sub-split nor the
  bigrams, so no estate's ordering moves. Pinned by an arm that asserts
  `name_tokens("APIの設計") == ["apiの設計"]` — i.e. that the new layer did
  NOT reach them.
* **The join detector getting looser.** Bigram tokens make two-token matches
  easier in CJK, which could suppress a real finding. Both directions are
  pinned (a row that accounts for the commitment silences it; a row that does
  not, does not). The pre-change behaviour was zero findings either way, so
  this is strictly more signal, and the summary the detector prints already
  says it matched by shared wording.

## The divergence I could not remove, declared rather than hidden

The old classes carried `-`, `_`, `.` and `/` INSIDE a token; the shared
splitter ends a word at each of them. So `ENG-9` is two tokens now, and a
sentence-final period is no longer glued to the last word. Two arms pin it
explicitly rather than letting a "byte-identical" claim quietly not be one.
The join is not weakened: the alphabetic half falls below the floor on both
sides and the numeric half is shared on both, so a ticket id contributes the
same single matching token it always did. Pure-alphabetic English is
byte-identical, and that is what the pins assert.

## Placement, and why it is not a new module

Two blind arms (Fable 5 and Opus 5, own clones, neither reading the other)
were asked where the shared primitive belongs. Both returned
`framework/onboarding/salience.py`. Both gave the same decisive reason: a
`framework/text.py` is a net-new member of a zero-headroom bijection class, so
it needs an `expansions:` row whose `merge_refuted` anchor refutes
`salience.py::split_words` — and that refusal cannot be written honestly,
because the primitive IS that function plus one layer. Every live expansion
row in the contract refuses its merge target on a stated property difference
(different arity, different inputs, different failure mode); this one has
none. The runner-up argument, which both arms also stated, is that
`framework/env.py` proves the tree hoists a universal stdlib-only leaf to top
level rather than making `framework/sources/` depend on a hatch-time package.
Adjudicated for salience: `framework/onboarding/__init__.py` executes nothing,
`salience.py` imports only stdlib, the reverse edge (`genesis` →
`framework.sources`) is lazy and function-local, and module-level
`framework.onboarding.*` imports from always-live planes are already shipped
precedent (`framework/evidence/dogfood.py`, `framework/learning/gate.py`,
`framework/learning/apply_watch.py`, and the top-level evidence-plane modules,
one of which carries a shadow-law grep that this artifact must not trip — it
reds on the module's own NAME appearing anywhere outside its allowlist, which
is exactly the guarded-token trap a review artifact is well placed to spring).
Measured after the change:
`check-layer-separation.sh` new=0, census modules 248 ≤ 248.

## Budget

`framework_production_noncomment_lines` 61496 → 61724 (+228 measured, observed
76263 vs the then-effective 76035). Raised visibly, not paid by a temporary
allowance — an allowance promises a deletion gate, and this is permanent.
Roughly two thirds of the mass is docstring. Zero new production modules.

## Gates run

| gate | result |
|---|---|
| `pytest framework/onboarding/tests framework/sources/tests framework/tests -q` | 1998 passed, 2 skipped |
| `pytest framework -q` | 7844 passed, 25 skipped, 1 pre-existing env red (see Q3) |
| `bash cabinet/scripts/check-layer-separation.sh` | new=0, OK |
| `bash cabinet/scripts/verify-cognitive-architecture.sh` | PASS |
| `bash cabinet/scripts/docs-track-code-sweep.sh` | GREEN (files=64 findings=0) |
| `pytest cabinet/scripts/tests/test_declared_residuals_register.py -q` | 9 passed |
| new suite against `origin/master`, caches purged | 14 failed / 15 passed |

## Handback

`framework/onboarding/journey.py` is schg-locked germline in the live
checkout. This branch lands its bytes to master the documented
landed-then-ceremonied way (built in a clone, never touching the locked file);
re-materialising them in the live tree needs one Captain unlock/relock.
