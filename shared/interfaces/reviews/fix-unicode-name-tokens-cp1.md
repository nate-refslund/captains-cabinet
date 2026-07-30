# FW-019 checkpoint review — `fix/unicode-name-tokens`

Reviewed-Scope-Digest: cff9912c2650c4554fcf66665630a19630af281e5a3fcbd82e89c74cfa7e2a9f

**What is staged:** the onboarding name tokenizer stops assuming the operator's
world is spelled in Latin letters, plus the six new arms that hold it there, the
visible line-budget raise, and the retirement of the residual registered against
the gap.

**The defect, driven before the fix.** `salience.name_tokens` split on
`[^0-9a-z]+`. A name carrying no ASCII alphanumeric therefore produced NO words —
on BOTH sides of every comparison — so it shared none with ITSELF. Driven end to
end on the pre-change tree: answer `日本`, propose the folder literally named
`日本` ⇒ `salience_window_off_target`, *"“日本” shares no word with it"*, with
`target_words=[]` and `window_words=[]`. Same for Cyrillic, Greek, Arabic,
Hebrew and Devanagari. A framework primitive, in a public repo, telling a
Japanese, Greek, Russian, Arabic, Hebrew, Hindi, Thai or Korean operator
something false about their own data.

**What landed.** ONE splitter, read by both `name_tokens` and `tokenize`, asking
the Unicode database rather than an alphabet: a Letter or a Number carries a
word, a Mark belongs to the character before it and may never START one,
everything else ends the word. Applied after `casefold` (a fold that works past
ASCII, where `lower` leaves a German sharp s and a Greek final sigma as distinct
letters) and NFKC (so an accent a filesystem decomposed is still the same name).
No second splitter: two of them would drift apart the way the length floor did.

**The Mark rule is not decoration.** It is the one way widening the split could
have turned a false refusal into a false BIND. A pictogram carries an invisible
modifier; counted as a word in its own right it becomes a one-character word
every decorated row shares, and two unrelated folders would bind on it. Arm:
`test_a_decoration_is_not_a_word_two_names_can_share`.

**The re-rank was MEASURED, not assumed** — this vocabulary is what every score,
cluster, discount, demotion and grade reads. One live read-only sweep of a real
665-name, four-connector estate (14 calls, no writes), ranked twice with `now`
pinned to the sweep instant so the tokenizer is the only variable:

| | before | after |
|---|---|---|
| ranked clusters | 49 | 49 — **identical in order and in score** |
| ranking vocabulary | 1226 tokens | 1211 |
| names below the span floor | 607 | 608 |
| discounted tokens | 33 | 33, same set |
| estate identity strings | 138, incl. 15 shattered fragments | 136, those replaced by 13 whole names |
| names whose ranking tokens changed | — | 35 of 665, every one previously shattered |

The shortlist did not move, so it moved neither toward nor away from the
operator's own answers: nothing reachable became unreachable and nothing new
entered the cut. What moved is that a name is now read as the word the estate
actually writes instead of the fragments either side of a non-ASCII letter, and
the demotion set is built from whole names rather than from fragments of them.

**The honesty arm no longer shares the assumption it checks.** Its independent
reading was `[^0-9a-z]+` — the same ASCII splitter as the module under test — so
two non-Latin names produced two EMPTY sets, an empty intersection, and the
false refusal passed VACUOUSLY. Proven, on the exact case: old checker certifies
`日本` vs `日本` honest (`set()` / `set()`); new checker refuses it (`{'日本'}` /
`{'日本'}`). The replacement derives words from Python's IDENTIFIER grammar
(XID_Start / XID_Continue via `str.isidentifier`) — a different table answering a
different question — and agrees with the module on all 665 real estate names,
which makes the agreement evidence rather than tautology.

**Verification.** Seven arms are RED against the pre-change tree with caches
purged (5 in `test_salience.py`, 2 in `test_journey.py`, including the honesty
arm), and both directions run on every table: the permitted rows outnumber the
refused ones, so a bind that refuses everything cannot pass by symmetry, and each
refusal's stated reason is re-graded by the independent reading. Green after:
`framework/` 7776 passed (1 known-red, `test_retro_shim.py::test_reexports_constants`,
reproduced identically on a pristine master clone — env-driven model-id pin),
`cabinet/scripts/tests` 5121 passed, golden evals 32/32, docs-track-code sweep,
ledger status-parity, layer separation, architecture census at zero headroom.

**Budget.** `framework_production_noncomment_lines` raised VISIBLY 61433 → 61474
(+41 measured, observed 76013). Never an allowance: a splitter that reads the
operator's own script has no deletion gate that could ever fire. Zero new
production modules, so no bijection class moves.

**Residual.** RES-025 flips to `retired`; its declaration is deleted from
`framework/onboarding/salience.py` in this same commit, which is what the pin
test requires.
