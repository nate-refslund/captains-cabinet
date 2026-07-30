# COG-4 §12.3/§15 FROZEN REVIEW — Composable Cognitive Organs + Deterministic Shadow Scheduler

**Scope:** the COG-4 surface at commit `f62094f7c6ee419db20df3d5445a89f5258467bb` (`feat/cog4-w6-e4`,
"COG-4 W6 e4: census done-flip tighten (§9.4/§11) — record final phase actuals, N7 machine-pinned",
over master `fc51fd59`; W1-W5 already on master, W6 e1-e4 = `6502f597`→`b4bc2c34`→`2ab7d607`→`2338d6c9`→tip):
`framework/projection/{__init__,kernel}.py`, `framework/scheduler/{__init__,model,snapshot,fold,serve}.py`,
`framework/organs/{__init__,registry,descriptor}.py`, `framework/schemas/cognitive-trajectory.v2.schema.json` +
the `framework/evolution/contracts.py` version dispatch, `framework/watchdog/registry.py` `_parse_organ_manifests`,
`cabinet/config/boundary-manifest.yml` + the converted engine `cabinet/scripts/cog2-import-gate.py`,
`cabinet/scripts/{cog4-snapshot,cog4-schedule,cog4-dispatch-shadow,cog4-parity,cog4-measure,cog4-organ-runner}.py`,
the W6-e2 compose (`cabinet/services.yml` + 5 organ manifests under `cabinet/config/organs/`), the phase twins
(`verify-cognitive-phase4.sh`, `cognitive-phase4-review-scope.py`, `cognitive-phase4-rollback-rehearsal.py`,
rollback manifest `docs/plans/cognitive-core-phase-4-rollback-manifest-2026-07-24.yml`), the `test_cog4_*`/`lib_cog4_*`
corpus, and the egg-export manifest extension.
**Reviewer:** frozen fresh-context Fable panel (clean-room clone off the canonical remote, zero prior-session
context; 2026-07-24). The F1 lesson bound this review: every public entry point of every new serve surface was
attacked with the panel's OWN tamper code, never only the suite's.
**Contract:** `docs/plans/cognitive-core-phase-4-contract-2026-07-23.md` rev 1 (§15 standing questions answered
below, every one).
**Method:** every claim is bound to bytes (`file:line`) or a run executed by this panel (`python3.12`). No doc or
comment was trusted un-run. 74 independent panel probes + the full committed batteries; the clone worktree was
byte-clean (`git status --porcelain` empty) after every run.

Reviewed-Scope-Digest: 11b7586887b031e6677acbf4fc653a54cbb4eea971240fe09307c655d1a62d34
(RE-BOUND 2026-07-30 on `fix/unicode-name-tokens`, previous value `35b4ae16…`.
ONE in-scope path moved and NO COG-4 implementation byte did:
`cabinet/config/cognitive-architecture-contract.yml` raises
`framework_production_noncomment_lines` VISIBLY 61433 -> 61474 (+41 measured over
this tree with cognitive-architecture-census.py, observed 76013 vs the
then-effective 75972 — not an allowance, because a splitter that reads the
operator's own script has no deletion gate that could ever fire). The change it
pays for is one function pair in `framework/onboarding/salience.py`: the name
tokenizer split on `[^0-9a-z]+`, so a name carrying no ASCII alphanumeric
produced NO words on either side of any comparison and therefore shared none
with ITSELF — an operator answering in Japanese, Cyrillic, Greek, Arabic,
Hebrew, Devanagari, Thai or Korean had every window refused, including the
folder spelled exactly like their answer. One Unicode-aware split now serves
both `name_tokens` and `tokenize`, and its re-rank was MEASURED on a live
665-name four-connector estate before landing: all 49 ranked clusters identical
in order and score, vocabulary 1226 -> 1211, below-span 607 -> 608, 35 of 665
names re-read as the word the estate writes. Census PASS at observed == maximum
with zero headroom; ZERO new production modules, so no bijection class moves.)
(MERGE RE-BIND, 2026-07-30, `fix/short-answer-binds` x master. Both sides
re-bound this line, so the merge left two; ONE value stands and it is
recomputed over this merge commit. No COG-4 implementation byte moved on
either side — the only in-scope path is the contract file, whose ceiling is
RE-MEASURED over the merged tree rather than summed on paper. Both re-bind
sections are kept verbatim at the end of this file, because a re-freeze that
hides what moved asserts a review that never happened. Master's note from
this same day follows.)

(RE-BOUND 2026-07-30 on `fix/identity-picker-tail`, previous value
`c83b9b88…`. ONE in-scope path moved and NO COG-4 implementation byte did:
`cabinet/config/cognitive-architecture-contract.yml` raises
`framework_production_noncomment_lines` VISIBLY 61327 -> 61372 (+45 measured over
this tree with cognitive-architecture-census.py, observed 75911 vs the
then-effective 75866 — not an allowance, because an offer that cannot exclude the
person it is addressed to has no deletion gate that could ever fire), and the
operator-identity phase row records what the +45 bought. The unit's own work is
in `framework/onboarding/{research,journey}.py` and the dashboard card, all
outside this digest's scope: the identity picker offered the 12 BUSIEST accounts
a connector reported, so on the real estate — 531 of 665 rows, 30 accounts, the
operator's own carrying exactly one and ranking about 25th — the only writer of
an identity could not be handed the identifier, and 80% of that estate was
unresolvable by any sequence of operator actions. Every earlier note stands
verbatim below. Previous header note follows.)

(MERGE RE-BIND, 2026-07-30, `feat/operator-identity` x master. Both sides
re-bound this line, so the merge left two; ONE value stands and it is recomputed
over this merge commit. Every note from both sides is kept verbatim below,
because a re-freeze that hides what moved asserts a review that never happened.
No COG-4 implementation byte moved on either side — the only in-scope path is the
contract file, whose ceiling is RE-MEASURED over the merged tree rather than
summed on paper.)
(RE-BOUND 2026-07-30 on `feat/operator-identity` — twice, the second time for the
two defects that branch was caught with by attacking its own landing; previous
values `df74c54b…` and before it `80d1b9fe…`.
ONE bound path moved — `cabinet/config/cognitive-architecture-contract.yml`,
which takes a +246 non-comment-line phase row for the operator-identity unit —
and NO COG-4 implementation byte did. The note for it is appended at the end of
this file; every earlier note stands verbatim. Previous header note follows.)

(RE-BOUND 2026-07-30 on `fix/answer-binds-depth`, previous value `80d1b9fe…`.
ONE in-scope path moved and NO COG-4 implementation byte did:
`cabinet/config/cognitive-architecture-contract.yml` raises
`framework_production_noncomment_lines` VISIBLY 60979 -> 61094 (+115 measured
over this tree with cognitive-architecture-census.py, observed 75371 vs the
then-effective 75256 — not an allowance, because a control that makes a
SHIPPED sentence true has no deletion gate that could ever fire while the
sentence ships). The unit's own work is entirely in
`framework/onboarding/journey.py` and `framework/onboarding/salience.py`,
outside this digest's scope: the salience answer was recorded and read by
nothing, so an operator could answer one target and have a First Window on any
other folder accepted, ratified and READ while the card kept publishing "that
is where I spend depth". `_window_binding` is the control; `WINDOW_RELATIONS`
is the named escape. Re-bound in the SAME commit as the contract raise, per the
zero-headroom chain this artifact's RES-007 note describes.)
(MERGE RE-BIND, 2026-07-29, `fix/connector-loader-honesty` x master. Both sides
re-bound this line, so the merge left two; ONE value stands and it is recomputed
over this merge commit. Every note from both sides is kept verbatim below,
because a re-freeze that hides what moved asserts a review that never happened.
No COG-4 implementation byte moved on either side — the only in-scope path is the
contract file, whose line ceiling is RE-MEASURED over the merged tree rather than
added on paper.)

(RE-BOUND 2026-07-29 on `feat/look-capabilities`, previous value
`408e6b97…`. ONE in-scope path moved and NO COG-4 implementation byte did:
`cabinet/config/cognitive-architecture-contract.yml` raises
`framework_production_noncomment_lines` VISIBLY 60543 -> 60637 (+94 measured
over this tree, with a three-item breakdown in the row's own comment — not an
allowance, because a read lane that reads more clock encodings honestly and
refuses to describe its own misconfiguration as the operator's empty estate has
no deletion gate that could ever fire). The unit's own work is in
`framework/onboarding/` and `instance/config/`, which this scope does not bind.
Named here rather than absorbed silently, because a re-freeze that hides what
moved would assert a review that never happened.)

(RE-BOUND 2026-07-29 on `fix/connector-loader-honesty`, previous value
`408e6b97…`. ONE in-scope path moved and NO COG-4 implementation byte did:
`cabinet/config/cognitive-architecture-contract.yml` raises
`framework_production_noncomment_lines` 60543 -> 60572 VISIBLY, with the
per-item breakdown in the row's own comment — not an allowance, and not a
bijection class. The unit's own work is in `framework/onboarding/`, which
this scope does not bind: the connector loader's two silent skips (an
unparseable declaration returning the document an ABSENT one returns, and a
malformed entry dropped without a word) now arrive as named refusals. Stated
here rather than absorbed silently, because a re-freeze that hides what moved
asserts a review that never happened.)

(RE-BOUND 2026-07-29 on `fix/framework-specifics`, previous value
`0df4d12a…`. TWO in-scope paths moved and NO COG-4 implementation byte did:
`cabinet/config/cognitive-architecture-contract.yml` raises
`framework_production_noncomment_lines` VISIBLY (+261 over this tree, with a
per-item breakdown in the row's own comment — not an allowance), and
`cabinet/scripts/tests/test_cog4_exit_fixtures.py` follows the
consequence-event schema's `action_type` from a flat enum to a `oneOf`:
the CLOSED branch is still asserted equal to `classifier.ACTION_TYPES`, is
now located by SHAPE rather than by position, and the new OPEN branch is
asserted pattern-gated and un-able to match any of the 30 — so the arm got
stronger, not looser. The unit's own work is in `framework/` and
`instance/config/`, which this scope does not bind. Named here rather than
absorbed silently, because a re-freeze that hides what moved would assert a
review that never happened.)


(RE-BOUND 2026-07-29 on `feat/onboarding-connector-read`, previous value
`e7a6983a…`. TWO in-scope paths moved and NO COG-4 implementation byte did:
`cabinet/config/cognitive-architecture-contract.yml` gains one
`temporary_allowances` row (`connector-read-lane`, +416 non-comment lines, the
line ceiling re-measured over this tree), and
`cabinet/scripts/egg-export-manifest.txt` gains one `delete` line for
`instance/config/connectors.yml` so a live instance value cannot ship in the
egg. The unit's own work is in `framework/onboarding/` and
`instance/config/`, which this scope does not bind. The delta is named here
rather than absorbed silently, because a re-freeze that hides what moved would
assert a review that never happened.)

(RE-BOUND 2026-07-29 on `fix/briefing-and-recall`, merged with the connector-read re-bind above rather than replacing it — both sides re-bound this line and both notes are kept verbatim, because a re-freeze that hides what moved asserts a review that never happened. This branch's in-scope delta is named in its own re-bind note at the end of this file: `cabinet/services.yml` (the retrieval-eval row's notes + `RE_ABSTAIN_FLOOR`) and one budget maximum in `cabinet/config/cognitive-architecture-contract.yml`. No COG-4 implementation byte moved on either side.)
(MERGE RE-BIND, 2026-07-29, `fix/fence-newline-forgery` x master (the eight-PR billing-wall drain, final landing). Both sides had re-bound this line, so the merge left two; the SECOND is removed and the value above is recomputed over this merge commit. Every note from both sides is kept verbatim. No COG-4 implementation byte moved on either side — the only in-scope path is the contract file, whose ceiling is re-measured over the merged tree.)


(RE-BOUND again in the same branch, 2026-07-29: the agnosticism gate landed on
master and correctly refused this unit's prose, so the line allowance was
re-measured 685 -> 687 — a contract edit, and the contract IS in this scope. I
first wrote that nothing in scope had moved; the verifier said otherwise and it
was right. Prior digest
`ffe8b3ee489ed66b44bc83aa1613b99dd245cf50a96baa8be07227ceff5806d3`. No COG-4
byte moved; only the census ledger's own number.)

(MERGE RE-BIND, 2026-07-29, `feat/salience-sweep` x master `1875e112`.
Both sides had re-bound this line and both moved
`cabinet/config/cognitive-architecture-contract.yml` (this branch: the visible
bijection raise plus the salience expansion row; master: the recall unit's own
allowance), so the two digests conflicted textually and NEITHER described the
merged tree. The value above is recomputed over the MERGE COMMIT rather than
taken from either side — taking either would have bound this artifact to bytes
that no longer exist, which is the one thing the digest is for. Prior digests:
this branch `918d6306d1b8104fc6f787951cfd4029b28ef388a9fada291451e12b1657ce6d`,
master `c18946e6377c31c9c653389e02ff26273df8cb587cf446c80170e589340a9109`. Both
landings' notes survive below verbatim; neither is the other's restamp, and the
contract carries both allowance rows whole — the conflict was two independent
additions to one list, not a contest.)
(MERGE RE-BIND, 2026-07-29, `feat/salience-sweep` x master (the eight-PR billing-wall drain). Both sides had re-bound this line, so the merge left TWO digest lines and neither described the merged tree; the SECOND is removed and the value above is recomputed over this merge commit. Every note from both sides is kept verbatim below. The contract carries BOTH allowance rows whole (`onboarding-salience-sweep` +687, `stranger-hatch-unopened-areas` +27) and `framework/onboarding/tests/test_journey.py` carries BOTH sides' arms — nine salience arms and six starved-area arms, zero overlapping definitions. Every conflict here was two independent additions to one place, not a contest.)


(MERGE RE-BIND, 2026-07-28, `fix/stranger-hatch-timed` x master `a70bcfb5`
(PR #268). Both sides had re-bound this line and BOTH moved
`cabinet/config/cognitive-architecture-contract.yml`, so the two digests
conflicted textually: neither describes the merged tree and the value above is
RECOMPUTED over it. Both sides added a `temporary_allowances` row at the same
position — `stranger-hatch-unopened-areas` (+27, this branch) and
`onboarding-derivation-false-positives` (+34, master) — and BOTH ARE KEPT; the
conflict was textual adjacency, not a contested value, and the running total is
RE-MEASURED on the merged tree rather than carried from either side. No budget
`maximum` raised, no expansion member, no bijection class, and NO COG-4
implementation byte moved on either side. Nothing below was re-reviewed,

(MERGE RE-BIND, 2026-07-29, `fix/stranger-hatch-timed` x master `0166f74b`
(PR #281). Fourth master merge for this branch, same shape: both sides had
re-bound this line, neither digest describes the merged tree, value above
RECOMPUTED over it, every prior note kept. Master's side also touched
the Phase-4 evidence lens test file under `framework/tests/`
(named by role, not by module: the shadow-law reference proof scans every
shipped file for the module token), which auto-merged cleanly — this
branch's two arms in that file (the ARMED assertion it already carried and the
new shipped-twin lockstep) are both present and green after the merge, verified
by running the file rather than by reading the merge output. NO COG-4
implementation byte moved on either side.)

(MERGE RE-BIND #4, 2026-07-29, vs the hostile-input red-team landing
(`2c6f4d636640e0b094348d0bf24eb7ecd22435a265d07514cf8aea928f15c92a`). That leg fixed the SAME
injection screen from the other side and its Nordic/German arms are the
richer half, so this branch TOOK master's screen verbatim and re-applied only
the measured delta (seven payloads that still scored zero against those arms).
The budget row was re-measured down from +19 to +13 accordingly — the ceiling
follows the merged tree, not this branch's original claim. Only the contract
file is in COG-4 scope; no COG-4 implementation byte moved on either side.)

(MERGE RE-BIND #3, 2026-07-29, vs master's specifics-ratchet landing
(`1c91f915f42e5243ddfc3a0b7a1af291394a25944661d50d0c981f43895a5934`). Both sides raised the SAME
`framework_production_noncomment_lines` maximum off the same 60164 base and
both moved only the contract file in COG-4 scope, so the merged ceiling is
re-measured over the merge tree (60188; observed 73104) rather than added on
paper, and the digest above is recomputed over that merge commit. No COG-4
implementation byte moved on either side.)

(MERGE RE-BIND, 2026-07-28: this branch and master each re-bound this line and
both moved in-scope bytes, so neither recorded digest describes the merged tree —
the value above is recomputed over the MERGE commit and supersedes both. HEAD is
what the gate reads. Superseded: `3d18b9363409a4dfe6f4655ed2877ea745ea7e8b09e7630b2b75ee1ca942d49f`
(this branch) and `3c8c1f7f60bd32a56e831438d768ea1b760b8f148353e65aba3c76c9b6d50a79`
(master, the onboarding-derivation landing).

THIS BRANCH's in-scope move, and it is not a COG-4 byte:
`cabinet/config/cognitive-architecture-contract.yml`, whose
`framework_production_noncomment_lines` maximum went 60164 -> 60183 to pay —
visibly, not by a temporary allowance — for the Danish alternations added to
`framework/acting/action_lane.py`'s injection screen, after a read-only
rehearsal against the operator's real estate measured that screen catching 7/7
English payloads and missing 8 of 11 semantically identical Danish ones. The
merge stacks that ceiling bump on master's +34 allowance row for the onboarding
derivation fixes; the two are disjoint and the census re-pins at zero headroom
over both. No COG-4 finding, claim or verdict in this review is touched, and a
strictly higher ceiling leaves every ratchet claim made here standing.)

(MERGE RE-BIND #2, 2026-07-29: master re-bound this line again while this
branch's CI ran (the memory-honest-empty landing). Neither recorded digest
describes the merged tree, so the value above is recomputed over THIS merge
commit and supersedes master's `c18946e6377c31c9c653389e02ff26273df8cb587cf446c80170e589340a9109`
as well. No COG-4 byte moved on either side; the only in-scope path is the
contract file, and both landings' budget rows are additive and disjoint.)

(RE-BIND, 2026-07-28, `fix/hostile-input-red-team`. The hostile-input red
team added a `temporary_allowances` row to
`cabinet/config/cognitive-architecture-contract.yml` — a restore_from_baseline
member of this phase's scope — paying +31 production non-comment lines for the
fenced-bundle provenance fix (a source file could type its own fence header,
defeating both the taint map and the D13 never-act-first floor). No COG-4
surface changed: framework/acting, framework/sources and framework/frontdoor
are outside this scope set. Recomputed over the committed tree; the prior
value is superseded, the note below it is retained in full.)

(superseded historical binding, kept for archaeology — prior digest `1c91f915f42e5243ddfc3a0b7a1af291394a25944661d50d0c981f43895a5934`)

(MERGE RE-BIND, 2026-07-29, `fix/stranger-hatch-timed` x master `4c7d42e7`
(PR #276). Fifth master merge for this branch. The shape has stopped being
incidental and is worth recording as a finding in its own right: this one line
is re-bound by EVERY landing that touches the digest scope, so with landings
arriving faster than a full CI pass every in-flight branch conflicts here
exactly once per landing, and each resolution is mechanical — keep both note
blocks, recompute the digest over the merged tree, never pick a side. Nothing
below was re-reviewed; NO COG-4 implementation byte moved on either side.)

(MERGE RE-BIND, 2026-07-28, `fix/recall-live-claims-it-never-earned` x master
`a70bcfb5` (PR #268). Both sides re-bound this line and both moved
`cabinet/config/cognitive-architecture-contract.yml`, so the two digests
conflicted textually: neither describes the merged tree, and the value above is
recomputed over the MERGE COMMIT rather than taken from either side. Prior
digests: this branch `ec75278e9929f8a03d811ec3689716e1190808db3df0a3a0ba0a0ef2275c5666`,
master `3c8c1f7f60bd32a56e831438d768ea1b760b8f148353e65aba3c76c9b6d50a79`.
THIS BRANCH's in-scope move: `cabinet/config/cognitive-architecture-contract.yml`,
and only its `temporary_allowances` list — a new row buying the +30 non-comment
lines two recall fixes cost (an unconfigured backend reporting live recall; the
chunk heading rendered as the operator's own shared wording). No budget MAXIMUM,
no set pin, no bijection class and no declared invariant moved. The two changed
production files, `framework/sources/org.py` and `framework/onboarding/genesis.py`,
are NOT in this scope, and neither is anything PR #268 touched
(`framework/onboarding/estate.py`, `framework/onboarding/journey.py` and their
tests) — the two branches share no production file. NO COG-4 implementation byte
moved on either side: no organ, no scheduler or projection surface, no serve
surface, no boundary row, no fixture, no CLI. Nothing below was re-reviewed,

(MERGE RE-BIND, 2026-07-28, `fix/stranger-hatch-timed` x master `1875e112`
(PR #269). Third master merge for this branch and the same shape each time:
both sides re-bound this line and both moved
`cabinet/config/cognitive-architecture-contract.yml`, so the digests conflicted
textually while neither described the merged tree. Value above RECOMPUTED over
it; every prior note kept, none superseded. Master's side added
`recall-live-claims-it-never-earned` (+30); this branch's
`stranger-hatch-unopened-areas` (+27) is untouched, and the running total is
RE-MEASURED on the merged tree rather than carried. NO COG-4 implementation
byte moved on either side.)
because no reviewed COG-4 byte moved.)

(RE-BOUND 2026-07-29 at the landing of `feat/salience-sweep`, over the merge of
`origin/master` b4859c55. Prior digest on this branch:
`528005675917203f902d45d5b8c7769cbe1f3598cdc58fb016284f1ebce88a56`; master's own
at that merge: `3c8c1f7f60bd32a56e831438d768ea1b760b8f148353e65aba3c76c9b6d50a79`.
NEITHER side's value survives, because the digest is a function of the MERGED
bytes — a concurrent branch moved the same in-scope file, and taking either
recorded value would have bound this artifact to bytes that no longer existed.
ONE in-scope path moved on this branch and it is not a COG-4 byte:
`cabinet/config/cognitive-architecture-contract.yml` gains the visible bijection
raise 207 -> 208 for `framework/onboarding/salience.py`, that member's expansion
row, and one `framework_production_noncomment_lines` allowance re-measured after
the merge (73735 = 73016 + this unit's 685 + master's 34, both rows kept whole —
the conflict was two independent additions to one list, not a contest). The
budgets file is in scope because COG-4 extended it; the salience ranker itself,
its suite and `framework/onboarding/journey.py` are OUTSIDE the scope set —
verified, since the digest over this branch's FIRST commit still read
`9b433220…`, unchanged from master. No COG-4 organ, contract clause or
measurement was touched, so nothing this artifact reviewed changed meaning; only
the census ledger grew by one adjudicated member. Re-bound in the SAME commit as
the contract edit, because a recorded digest and the bytes it binds must never be
able to disagree, even for one commit.

Earlier RE-BIND 2026-07-28 at the landing of `fix/world-art-manifest-truth-and-egg`.
(MERGE RE-BIND, 2026-07-28, `feat/agnosticism-gate` x master `e8449ce6`.
Third re-bind of this line in a day, same mechanism: both sides moved
`cabinet/config/cognitive-architecture-contract.yml`, so neither recorded
digest describes the merged tree and the value above is recomputed over
THIS merge commit. Prior digests: this branch
`d517beb0de1e284304c54d4a3591be173433c8a830b87b5cd7f8d13694595796`, master
`c18946e6377c31c9c653389e02ff26273df8cb587cf446c80170e589340a9109`.
THIS BRANCH's in-scope move: the contract's
`framework_production_noncomment_lines` MAXIMUM, 60164 -> 60169, raised
visibly for the parameterised charset seam that replaces a deleted
keyboard whitelist (+5 measured). No set pin, no bijection class, no
declared invariant and no temporary allowance moved; master's side moved
only the allowances list, so the two edits are disjoint within the file.
NO COG-4 implementation byte moved on either side: no organ, no scheduler
or projection surface, no serve surface, no boundary row, no fixture, no
CLI. Nothing below was re-reviewed, because no reviewed COG-4 byte moved.)

(RE-BOUND 2026-07-28 at the landing of `fix/world-art-manifest-truth-and-egg`.
Prior digest: `ebbdcc3f771afef7ffddc7558ea64a06bf3f8fa782cf14b5dd129891f796ca15`.
TWO in-scope paths moved, both on the egg-export surface COG-4 extended and
neither a COG-4 byte: `cabinet/scripts/egg-export-manifest.txt` (the WORLD ART
block — the owned iso atlas, resolve table and 20-sheet character cast now SHIP
in the egg instead of being deleted from it, per the Captain's 2026-07-28 "ALL
OUT of LimeZu" direction; the block that stood there reserved the call to the
Captain and stated the cost it was paying, which was a fresh hatch with no world
art at all) and `cabinet/scripts/tests/test_egg_export.py` (`test_world_assets_
and_node_modules_absent` -> `test_licensed_art_must_not_ship_but_owned_art_must`:
the arm banned every `.png` under `world-assets` on the stated grounds that
binaries there are licensed, i.e. it tested the file extension and not the
licence, so it kept passing after 20 owned sheets landed beside the licensed
packs while the property it named had stopped being what it measured. It now
reads the manifest's `license` field and carries a floor — the atlas and all 20
owned sheets must BE in the export — so shipping nothing can no longer satisfy
it). Verified by intersecting `resolve_scope()` with
`git diff --name-only origin/master...HEAD`: exactly those two paths, and the
intersection with the manifest's DIR entries is empty. NO COG-4 implementation
byte moved — no organ, no scheduler or projection surface, no serve surface, no
boundary row, no fixture, no CLI, and the contract file is untouched. Nothing
below was re-reviewed, because no reviewed COG-4 byte moved. The re-bind is a
separate commit from the byte-moving one only because this landing's brief
forbids `--force`, so the pushed branch could not be amended; both commits land
together and HEAD is what the gate reads.)

(MERGE RE-BIND, 2026-07-28, `fix/stranger-hatch-timed` x master `4148d1e6`
(PRs #266 + #267). Both sides had re-bound this line — this branch at
`e8da2ab0`, master at `9b433220` — so the two digests conflicted textually:
NEITHER describes the merged tree, and the value above is RECOMPUTED over it.
Both note sets are kept in full, none superseded. This branch's digest-bound
move is `cabinet/config/cognitive-architecture-contract.yml` alone: one new
`temporary_allowances` row (`stranger-hatch-unopened-areas`, +27 on
`framework_production_noncomment_lines`) paying for the First Window's
truncation caveat naming the areas it never opened. Verified by intersecting
`resolve_scope()` with `git diff --name-only origin/master...HEAD`: exactly
that one path. No budget `maximum` raised, no expansion member, no bijection
class, and NO COG-4 implementation byte moved on either side — no organ, no
scheduler or projection surface, no serve surface, no boundary row, no fixture,
no CLI. Master's side moved the egg-export world-art block and its export test,
neither a COG-4 byte. Nothing below was re-reviewed, because no reviewed COG-4
byte moved. Census re-measured on the MERGED tree: 73043, at the pinned
effective level.)

(MERGE RE-BIND, 2026-07-28, `fix/probe-truncation-unearned-negative` x master
`2b3de03d` (PR #261). Both sides had re-bound this line and both moved
`cabinet/config/cognitive-architecture-contract.yml`, so the two digests
conflicted textually: neither describes the merged tree and the value above is
RECOMPUTED over it. Both note sets are kept in full below, none superseded.
This branch's own row (`onboarding-probe-truncation`) also moved `additional:
13` -> `28` in this merge, for +15 non-comment lines in `_name_matches` fixing
the boundary defect its hostile review found: `truncated` meant "reached the
cap", not "something remained", so a folder of exactly `MAX_PROBE_HITS`
matching files — read to its last entry — was disclosed to the operator as an
unfinished search. Master's side moved `briefing-consumes-recall` 456 -> 491.
Measured on the merged tree: 73016 non-comment lines against master `2b3de03d`
at 72988, delta 28. No budget `maximum` raised, no expansion member, no
bijection class, and NO COG-4 implementation byte moved on either side —
the contract file remains this branch's only digest-bound path.)

(MERGE RE-BIND, 2026-07-28, `fix/probe-truncation-unearned-negative` x master
`d8ab0308` (PR #255). Both sides re-bound this line and both moved
`cabinet/config/cognitive-architecture-contract.yml` — this branch one
`temporary_allowances` row (`onboarding-probe-truncation`, +13 non-comment lines),
master its own (`briefing-consumes-recall`, +456). git auto-merged the allowance
list with no contested byte. Neither recorded digest describes the merged tree, so
the value above is RECOMPUTED over it. No budget `maximum`, no existing
`additional`, no expansion member and no bijection class changed on either side,
and NO COG-4 implementation byte moved. Every note from both sides is kept below,
none superseded.)

(RE-BOUND 2026-07-28 by `fix/probe-truncation-unearned-negative`, branched from
master `a0cd4bc1`. Its ONLY digest-bound path is
`cabinet/config/cognitive-architecture-contract.yml` — one `temporary_allowances`
row, +13 framework production non-comment lines, no `maximum` raised, no
bijection class touched, no expansion registered. Verified by intersecting
`git diff --name-only a0cd4bc1 HEAD` with the tool's resolved scope: the contract
file is the only intersection, and NO COG-4 implementation byte moved — no organ,
no scheduler surface, no serve surface, no fixture, no boundary row. The other
files in the change are `framework/onboarding/*` and `cabinet/dashboard/*`, none
of them in scope. Nothing below was re-reviewed, because no reviewed byte moved.
Every prior note is kept verbatim, none superseded.)

(RE-BOUND 2026-07-28 by `fix/recall-card-claims-its-own-cites`, merged with
master `f224e884` (PR #259). Its ONLY digest-bound path is
`cabinet/config/cognitive-architecture-contract.yml` — the existing
`briefing-consumes-recall` `temporary_allowances` row moved from `additional:
456` to `491` for +35 framework production non-comment lines in
framework/sources/local.py. No budget `maximum` raised, no bijection class
touched, no expansion registered, and NO COG-4 implementation byte moved.
MEASURED rather than reasoned: the digest was recomputed at each commit of this
branch — `f224e884` and the master merge `e3d5e9ad` and the test-only commit
`28cacfda` all read `657db3fd`, and only the commit carrying the contract file
moves it; two single-path probe commits off `28cacfda` then isolated it, the
contract file alone reading `ae050c1a` and `framework/sources/local.py` plus its
test alone reading `657db3fd`, i.e. the sources change is out of scope
entirely. Nothing below was re-reviewed, because no reviewed byte moved. Every
prior note is kept verbatim, none superseded.)

(MERGE RE-BIND, 2026-07-28, `fix/briefing-consumes-recall` x master
`dad973d5` (PR #257). Fourth master landing this branch has merged in one
day, and the third that had re-bound this same line. Neither recorded
digest describes the merged tree, so the value above is RECOMPUTED over
it; every note from both sides is kept below, none superseded. This
branch's only in-scope path remains
`cabinet/config/cognitive-architecture-contract.yml` (one
`temporary_allowances` row, `briefing-consumes-recall`, +456 non-comment
lines); no budget `maximum`, no existing `additional`, no expansion member
and no bijection class changed, and NO COG-4 implementation byte moved on
either side.)


(MERGE RE-BIND, 2026-07-28, `fix/briefing-consumes-recall` x master
`8cf00772` (PR #253, connector-registry). BOTH sides had re-bound this
line and both moved the SAME in-scope path,
`cabinet/config/cognitive-architecture-contract.yml` — this branch one
`temporary_allowances` row (`briefing-consumes-recall`, +456 non-comment
lines), master one of its own (`onboarding-connector-registry`, +566).
The rows are independent and BOTH are kept; git flagged the hunk only
because they append at the same point. Neither recorded digest describes
the merged tree, so the value above is RECOMPUTED over it, and every note
from both sides is kept below, none superseded. No budget `maximum`, no
existing `additional`, no expansion member and no bijection class changed
on either side. NO COG-4 implementation byte moved: intersecting
`resolve_scope()` with each side's changed paths yields the contract file
and nothing else.)


(MERGE RE-BIND, 2026-07-28, `fix/briefing-consumes-recall` x master
d67fba97: master landed PR #250 while this branch sat green locally, and
BOTH sides had re-bound this line — `338e6f08…` here, `d85d407f…` on
master. Neither describes the merged tree, so the value above is
RECOMPUTED over it rather than picked from a parent; every note from both
sides is KEPT below, none superseded. The two sides' in-scope deltas are
disjoint and were computed, not read off the diff: intersecting
`resolve_scope()` with `git diff --name-only` on each side gives
`cabinet/config/cognitive-architecture-contract.yml` on BOTH — but on
DISJOINT rows (master added its own budget movements; this branch appended
one `temporary_allowances` row, `briefing-consumes-recall`, +456 on
`framework_production_noncomment_lines`), and git auto-merged them with no
contested byte. The delta was RE-MEASURED against the new base rather than
carried: 71805 -> 72261 on 6ec81460 and 71931 -> 72387 on d67fba97, the
same 456 both times, which is the check that the number measures the unit
and not the merge. No budget `maximum`, no existing `additional`, no
expansion member and no bijection class changed —
`framework_production_modules` stays 247, zero new modules. No COG-4
implementation byte moved on either side.)


(RE-BOUND 2026-07-28 at the landing of `fix/briefing-consumes-recall`,
same commit as the change that moved the bytes. Prior digest:
`fa66d3d0541fa8b0…`. The one moved file in scope is again
`cabinet/config/cognitive-architecture-contract.yml`, and the move is ONE
added `temporary_allowances` row: `briefing-consumes-recall`, +456 on
`framework_production_noncomment_lines`, for the recall probe and card
composition in `framework/onboarding/genesis.py` plus the honest-unset
resolve_root in `framework/sources/local.py`. No budget `maximum`, no
existing `additional`, no expansion member and no bijection class changed
— `framework_production_modules` stays 247 (zero new modules), and the
census is back at observed == maximum so the ratchet still bites. No COG-4
implementation byte changed; `framework/authority/classifier.py` remains in
the manifest's `must_remain_unchanged` block against the pinned phase
anchor. The phase-4 findings below are unaffected.)

(MERGE RE-BIND, 2026-07-28, `fix/needs-anti-vacuity-and-depth-labels` x
`feat/connector-registry`: both sides re-bound this line and both moved
`cabinet/config/cognitive-architecture-contract.yml` — this branch a PROSE-ONLY
correction of the evidence-append-quadratic row's trial-depth labels (no budget,
no maximum, no additional, no row identity; census unmoved at 71931 <= 71931),
master a connector-registry allowance row. git auto-merged the file with no
contested byte. Neither recorded digest describes the merged tree, so the value
above is RECOMPUTED over it rather than picked from a parent, and every note
from both sides is kept below, none superseded. NO COG-4 implementation byte
moved on either side: `resolve_scope()` intersected with
`git diff --name-only origin/master...HEAD` over this branch yields exactly the
contract file, and the intersection with the manifest's DIR entries is empty.)

(MERGE RE-BIND, 2026-07-28, `feat/connector-registry` x `fix/evidence-append-quadratic`: both sides re-bound this line and both moved `cabinet/config/cognitive-architecture-contract.yml` — this branch a `temporary_allowances` row for the connector registry, master the evidence recorder's own budget note. git auto-merged the allowance list with no contested byte. Neither recorded digest describes the merged tree, so the value above is RECOMPUTED over it. Every note from both sides is kept below, none superseded. NO COG-4 implementation byte moved on either side: this branch's only digest-bound path is the contract file, verified by intersecting `resolve_scope()` with `git diff --name-only 6ec81460 HEAD`.)

(RE-BOUND AGAIN 2026-07-28 at the merge of `origin/master` 3126cfac into
`feat/connector-registry` — the connector-registry landing moved
`cabinet/config/cognitive-architecture-contract.yml`, its ONLY in-scope path
(one `temporary_allowances` row, +566 non-comment lines; no maximum raised, no
bijection class touched), and master had re-bound this line in the merge
described below, so neither recorded value survives. The value above is
RECOMPUTED over the merged tree. Verified by intersecting
`git diff --name-only 6ec81460 HEAD` with the tool's resolved scope: the
contract file is the only digest-bound path this branch touched, and NO COG-4
implementation byte moved — no organ, no scheduler surface, no serve surface,
no fixture, no boundary row. Nothing below was re-reviewed, because no reviewed
byte moved. The prior re-bind's own note follows verbatim.)

(RE-BOUND 2026-07-28, `fix/needs-anti-vacuity-and-depth-labels`, in the SAME
commit as the change that moved the bytes — the re-bind-at-landing procedure
this artifact prescribes. Prior digest: `d85d407f5047ea53…`. The moved file in
scope is the ONE budget surface again:
`cabinet/config/cognitive-architecture-contract.yml`, whose
`evidence-append-quadratic` row cited trial depths 40 and 499 for latency
figures the `filing_latency` fixture takes at depths 16 and 495 — a governance
record asserting a measurement the code does not take. PROSE ONLY: no `budget`,
no `maximum`, no `additional`, no `owner`, no `sunset` and no row identity
changed, and the census is byte-for-byte unmoved at 71931 <= 71931.
MECHANICALLY VERIFIED rather than asserted: `resolve_scope()` was intersected
with `git diff --name-only` over this landing for ALL FIVE phase scopes and this
file is the only digest-bound path any of them touches; the intersection with
the manifest's DIR entries is empty. The other two paths —
`framework/authority/tests/test_needs.py` (its latency fixture's fill loop
bounded, so the fixture's own anti-vacuity assert becomes reachable instead of
spinning forever) and one dated doc correction — are in no phase scope. No
organ, no scheduler surface, no serve surface, no COG-4 entry point. Neither
`cognitive-phase4-rollback-rehearsal.py` nor `verify-cognitive-phase4.sh` is
touched: the frozen battery is byte-identical, which is what keeps this re-bind
mechanical rather than a restamp of a review that never happened. The
rehearsal's compatibility battery runs in a worktree detached at the pinned
anchor `c58d4a57`, so the `test_needs.py` edit is not in the bytes it runs.)

(MERGE RE-BIND, 2026-07-28, `fix/evidence-append-quadratic` x `iso-port-composition`:
PR #223 landed on master while this branch sat green in CI, and BOTH sides had
re-bound this line — `5435fddb…` here, `eebcf40b…` on master. Neither describes
the merged tree, so the value above is RECOMPUTED over it rather than picked
from a parent; every note from both sides is kept below, none superseded. The
two sides' in-scope deltas are disjoint and were computed, not read off the
diff: intersecting `resolve_scope()` with `git diff --name-only HEAD
origin/master` and with this branch's own changed paths gives
`cabinet/config/cognitive-architecture-contract.yml` (this branch's allowance
row) and `cabinet/scripts/egg-export-manifest.txt` (master's iso-art export
rows) — different files, no contested byte, git auto-merged both. No COG-4
implementation byte moved on either side.)

(MERGE RE-BIND, 2026-07-28, `fix/evidence-append-quadratic`: origin/master's
`feat/onboarding-ordering-inversion` landing re-bound this same digest while this
branch was in flight. Two concurrent landings cannot both be right about one
number, so it is RECOMPUTED over the MERGED committed tree rather than either
side being picked — a hand-picked digest from either parent records a tree that
never existed. Both parents moved the SAME one scope file,
`cabinet/config/cognitive-architecture-contract.yml`, and their edits are
disjoint rows; both re-bind notes are kept below.)

(RE-BOUND 2026-07-28, `fix/evidence-append-quadratic`, the re-bind-at-landing
procedure this artifact prescribes. Prior digest: `deca1533428d8df8…`. The moved
file in scope is the ONE budget surface again:
`cabinet/config/cognitive-architecture-contract.yml` gains an
`evidence-append-quadratic` allowance row on
`framework_production_noncomment_lines` (+126, exact measured running total
71277 vs 71151) for a fix to `framework/evidence/verifier.py` and
`recorder.py` — the append path was O(n) in the trial and O(n^2) overall.
MECHANICALLY VERIFIED rather than asserted: `resolve_scope()` was intersected
with `git diff --cached --name-only` over this landing and the contract file is
the ONLY digest-bound path it touches; the intersection with the manifest's DIR
entries is empty too. The other seven paths are the evidence verifier and
recorder, their tests, `framework/authority/tests/test_needs.py`,
`cabinet/scripts/governance-review.py` (one renamed-helper doc reference) and
one dated doc correction — none in COG-4 scope. No organ, no scheduler surface,
no serve surface, no COG-4 entry point, no budget `maximum` and no `additional`
on any pre-existing row changed. `framework/authority/classifier.py` remains in
the manifest's `must_remain_unchanged` block against the pinned phase anchor,
which the rollback rehearsal re-checks. The rehearsal's nine-directory
compatibility battery runs in a worktree detached at the pinned anchor
`c58d4a57`, so the edit to `framework/authority/tests/test_needs.py` is not in
the bytes it runs; that same battery at HEAD, which
`verify-cognitive-phase4.sh` runs, is green. The phase-4 findings below are
unaffected.)
(RE-BOUND 2026-07-28 at the merge of `origin/master` dd01ce8f into
`iso-port-composition` — the merge that unblocked PR #223, which had been
CONFLICTING for days and was therefore running NO CI at all. Both sides of the
merge had re-bound this line, so neither recorded value can be carried: the
branch's `dbdf515c…` and master's `fa66d3d0…` are each a digest over a tree that
no longer exists. The value above is RECOMPUTED over the merged tree and folded
into the merge commit itself.

Exactly TWO in-scope paths differ across the merge, and the delta is disjoint by
side — computed, not read off the diff, by intersecting
`git diff --name-only HEAD origin/master` with the tool's resolved 85-entry
scope: `cabinet/config/cognitive-architecture-contract.yml` moved on MASTER only
(the branch never touched it — the two allowance/budget landings its own notes
below describe), and `cabinet/scripts/egg-export-manifest.txt` moved on the
BRANCH only (master never touched it — the `delete`/`expect-absent` rows that
keep the org's commissioned iso art out of the public export). Neither side
contested a byte of the other's, so git auto-merged both and no row of either was
dropped. NO COG-4 implementation byte changed on either side: no organ, no
scheduler surface, no serve surface, no fixture, no boundary row, and
`framework/authority/classifier.py` remains in the manifest's
`must_remain_unchanged` block against the pinned phase anchor. Only two files in
the whole merge were touched by BOTH sides — this artifact and
`.github/workflows/cabinet-ci.yml`, whose four added steps sit in four disjoint
regions and all four survive in the merged file. The phase-4 findings below are
unaffected, and nothing here was re-reviewed, because no reviewed byte moved.)

(RE-BOUND 2026-07-28 at the landing of `feat/onboarding-ordering-inversion`,
same commit as the change that moved the bytes. Prior digest:
`deca1533428d8df8…`. The one moved file in scope is again
`cabinet/config/cognitive-architecture-contract.yml`, and the move is: the
`framework_production_modules` budget maximum raised visibly 206 -> 207, the
duplicate temporary-allowance row for `framework/onboarding/estate.py` removed
(master's bijection-allowance-bypass landing refuses an allowance that names a
bijection class, and an expansion row for that member was already present), and
the `framework_production_noncomment_lines` allowance 646 -> 654 for eight lines
fixing two defects found in this unit by the landing review. No COG-4
implementation byte changed; `framework/authority/classifier.py` remains in the
manifest's `must_remain_unchanged` block against the pinned phase anchor. The
phase-4 findings below are unaffected.)

(RE-BOUND 2026-07-27, `fix/bijection-allowance-bypass`, same commit as the change
that moved the bytes — the re-bind-at-landing procedure this artifact prescribes.
Prior digest: `8bee10cdcd41994b…`. The one moved file in scope is
`cabinet/config/cognitive-architecture-contract.yml`, and the move is COMMENT
bytes plus one allowance `reason` string: the expansion-registry header now
states what the census actually enforces after an adversarial review falsified
its previous claim by execution. No budget maximum, no `additional`, no member
and no expansion row changed — verified by loading both revisions and comparing
the parsed budgets/allowances/expansions. NO COG-4 implementation byte changed;
`framework/authority/classifier.py` remains in the manifest's
`must_remain_unchanged` block against the pinned phase anchor, which the rollback
rehearsal re-checks. The phase-4 findings below are unaffected. Re-bound a
second time at the merge of `origin/master` b6a58b15, which had itself re-bound
to `e3675c7b4b1db4c2…` for the `onboarding-three-entry-modes` row; the digest
above is recomputed over the MERGED tree, since both sides moved the same one
scope file.)



(RE-BOUND repeatedly on 2026-07-27 — the census-shift-left, expansion-registry and
census-set-pins landings each edited `cabinet/config/cognitive-architecture-contract.yml`,
which sits in `restore_from_baseline` and is therefore digest-bound, and so did this
branch's `recipient-exclusion-carve-backs` allowance row, and again for the
`onboarding-three-entry-modes` allowance row (2026-07-27). NO COG-4 implementation byte
changed by any of them: every edit is a budget/allowance row, and
`framework/authority/classifier.py` remains in the manifest's `must_remain_unchanged`
block against the pinned phase anchor, which the rollback rehearsal re-checks. The
phase-4 findings below are unaffected.)
(RE-BOUND 2026-07-27, `fix/propose-means-propose`, same commit as the change that
moved the bytes — the re-bind-at-landing procedure this artifact already
prescribes. Prior digest: `b8ee235e0c34bd2a…`. The moved file in scope is
`framework/authority/policy_engine.py`: `_eval_authority_matrix` now returns a
`GateDecision` carrying a structured verdict kind instead of a bare `str`, so
`propose_only` and `always_gated` stop being operationally identical. The COG-4
findings are unaffected — the change adds no organ, no scheduler surface and no
serve surface, touches no COG-4 entry point, and is separately reviewed in
`fix-propose-means-propose-cp1.md` with six per-ceiling arms and a corpus
cross-check over 80,307 recorded calls. Exit codes and all guardian block
strings are byte-identical, which is what keeps this re-bind mechanical rather
than a re-review.)
(RE-BOUND 2026-07-27, `feat/onboarding-entry-modes`, same commit as the change
that moved the bytes. The moved file in scope is the ONE budget surface again:
`cabinet/config/cognitive-architecture-contract.yml` gains an
`onboarding-three-entry-modes` allowance row. MECHANICALLY VERIFIED rather than
asserted: `resolve_scope()` was intersected with `git diff --name-only` over that
landing and the contract file is the ONLY digest-bound path it touches — the rest
are the onboarding entry-mode surface, its tests, its vendored pre/post-migration
snapshot and the dashboard, none of them in COG-4 scope. No organ, no scheduler
surface, no serve surface, no COG-4 entry point. A re-bind that moved an
implementation byte would not be a mechanical delta and is not what this records.)
(MERGE RE-BIND, 2026-07-27, `feat/onboarding-entry-modes`: the propose/gate and
hook-redos landings each re-bound this same digest while this branch was in CI.
Two concurrent landings cannot both be right about one number, so it is
RECOMPUTED over the MERGED committed tree rather than either side being picked —
a hand-picked digest from either parent records a tree that never existed. The
digest line was the ONLY conflict in this artifact both times; every landing's
note above is preserved verbatim, none overwritten. In-scope paths carried in by
the merges: the census contract only. Census re-measured on the merged bytes:
PASS, observed==max with zero headroom.)
(MERGE RE-BIND #2, 2026-07-27, same branch: the source-ownership-class and
killswitch-test-fence landings re-bound this digest again while the branch was
in CI. Recomputed over the merged committed tree for the same reason — a
hand-picked digest from either parent records a tree that never existed. The
digest line was again the only conflict here; every note is preserved. In-scope
paths carried in by the merge: the census contract only. Census re-measured on
the merged bytes: PASS, observed==max with zero headroom.)
(MERGE RE-BIND #3, 2026-07-27, same branch: the personal-preset-live landing
re-bound this digest while the branch was in CI. Recomputed over the merged
committed tree, same reason and same mechanics as #1 and #2 — in-scope paths
carried in by the merge: the census contract only; census re-measured on the
merged bytes: PASS, observed==max with zero headroom. Three merge re-binds on
one branch is not drift, it is a hot shared surface: every concurrent landing
that pays line mass edits the same contract file, which is in this digest's
restore_from_baseline set.)
(As frozen, the panel bound the DECLARED W1-W5 scope: `cognitive-phase4-review-scope.py` EXPECTED_SCOPE
deliberately excluded the e2/e3 sibling surfaces (cog4-organ-runner.py, cog4-measure.py, organ manifests,
their out-of-band tests, the FW-019 sibling artifacts) pending the landing integrator's PAIRED extension of
the §16 rollback manifest + EXPECTED_SCOPE in the same commit — `resolve_scope()` fails closed on any
one-sided edit, and the digest is re-bound at landing per the phase-3 precedent. The e2/e3 surfaces
themselves WERE fully reviewed by this panel; only the mechanical digest scope awaited the pair-extension.)
(Re-bound at the W6 landing, 2026-07-24 — the cp3 precedent, a MECHANICAL-DELTA re-bind, not a restamp.
The panel's original digest was d6625b82fc969ce9958e3eebcb96b58c4c6483cf5e3f14fb6cce8908f086ac6e, binding
tip f62094f7. Four landing commits moved it: (1) 48028427 committed THIS artifact (excluded from the digest
but named in the manifest remove list); (2) 93b26f74 the §13 corpus surgery — the panel's OWN named
discharge of the 5 designed flip-arms, each retired-live per its retirement text, pre-proven green
out-of-band by the panel-reviewed test_cog4_measure_baseline.py + test_cog4_organ_runner_real.py; (3)
eefc9c11 the §16/EXPECTED_SCOPE pair-extension, which pulled the ALREADY-PANEL-REVIEWED e2/e3 surfaces into
the digest scope (+ the P5 egg tidy rows; the L61 draft-lane plist DELETION declared as
out_of_phase_in_range residue — a deleted-at-HEAD path cannot be digest-bound); (4) 5d1547c0 the wave
FW-019 batch proof + its own pair rows. Mechanical deltas only — ZERO behavior bytes changed beyond the
§13 corpus surgery itself. Re-verified on the final bytes: full battery armed 690 passed 1 declared skip /
unarmed 689 passed 2 declared skips (ZERO failures — the designed interim discharged); rollback rehearsal
PASS with the compose-revert arm ARMED (the 12-file sibling residue resolved); egg battery 58 passed 1
declared skip; verify-cognitive-phase4.sh full green end-to-end after this re-bind. The panel verdict
stands. MOVED AGAIN same day (2026-07-24, 3ce64a36… → the value above) by the first-PR-CI root-cause
commit 429fa17b — the REMAINING e2-routed §6.4-6.7 sibling-suite re-anchors (charter-shadow /
judge-calibration / preference-pairs / prediction-scorer locks re-anchored to the composed vehicle; these
four files join restore_from_baseline + EXPECTED_SCOPE, the pair-extension that moved the digest), the
evidence-proof allowlist row for this phase's rollback manifest (that proof file is out-of-phase, unbound
by this digest), and the wave artifact's §6 addendum. Zero behavior bytes beyond that routed §13 surgery;
the full twin re-ran green end-to-end after this second re-bind. The panel verdict stands. FINAL MOVE
(2026-07-24, e2c35aa9… → the value above): the post-flip range-seal commit pinned the manifest's
done_flip_sha to the ledger flip commit c58d4a57 (the §16 retirement condition, the phase-3 e7f95d5a
retrofit shape) — a one-line YAML pin inside the scope; zero behavior bytes; the W6 merge dfb1a00e and the
flip c58d4a57 each carried all 7 CI jobs green. The panel verdict stands. MOVED BY THE COG-5 W1 LANDING
(2026-07-24, 95e6ea8bf1288655a488342ea2675e515d7332829c2ff623664db5cd23a10c42 → the value above): a
NEXT-PHASE rows-only extension, sanctioned IN ADVANCE by the COG-5 contract §10 (+ §7.5 Stage A) — zero
engine/behavior bytes. Exactly TWO in-scope paths moved vs the last binding (verified by diffing the
resolved 85-entry scope over 70bca2ae..HEAD; the COG-5 contract doc + the operative ledger sit OUTSIDE this
scope, and the parallel master doc-hygiene pair 21df33c9 moved ZERO in-scope paths): (1)
`cabinet/config/boundary-manifest.yml` +103 lines — COG-5 ROWs 8/9/10 APPENDED (holdout_gen sweep /
foundry-archive data-plane / evolution reverse); ROW 6 byte-untouched (the deliberate non-extension); the
engine `cog2-import-gate.py` byte-untouched; (2) `cabinet/scripts/egg-export-manifest.txt` +15 lines — the
§7.5.5 Stage-A INTERIM vacuity-armed holdout delete/expect-absent pair. Re-run at the landing on the merged
bytes: the boundary harness `test_cog4_boundary_rows.py` (the generic per-row mutant generator — a biting
mutant auto-generated per NEW row) + `test_cog5_boundary_rows.py` (content pins) 113 passed;
`cog2-import-gate.py` rc0; the full `test_cog4_*` battery 702 passed 2 declared skips; armed
`cog4-measure --check` within bound; `verify-cognitive-phase4.sh` full green end-to-end after this re-bind.
A MECHANICAL-DELTA re-bind per the cp3 precedent, never a restamp: zero COG-4 claims are touched by rows
APPENDED for the next phase. The panel verdict stands.
MOVED BY THE BOUNDARY-ENGINE DYNAMIC-FORM LANDING (2026-07-25,
d8d316b244e10156d45b3b46cff7bddb52bfbd526b736d1b7bb97745f1241eb2 -> the value above; from
093e5866...). Landed branch `fix/import-gate-dynamic-forms`, two commits, closing ten spellings of a
dynamic-import evasion in the boundary engine. READ THIS ONE DIFFERENTLY: every re-bind above is a
MECHANICAL-DELTA re-bind (zero behavior bytes). This is the FIRST BEHAVIOR-DELTA re-bind of this
artifact — the engine's own logic changed, so "mechanical delta" would be a false claim and is not made
here. EXACTLY ONE in-scope path moved (verified by diffing the resolved 85-entry scope over
origin/master 26d4cce2..HEAD): `cabinet/scripts/cog2-import-gate.py`, +432/-13, adding an AST pass
(constant-fold + binding-accurate hook resolution over `_HOOKS_OF_MODULE` {importlib, builtins}).
The other three landed paths sit OUTSIDE this scope and are named for the record: the new suite
`cabinet/scripts/tests/test_boundary_dynamic_forms.py` (only the enumerated `test_cog4_*`/`lib_cog4_*`
files are scope entries — `cabinet/scripts/tests` is NOT a DIR entry) and the two FW-019 batch proofs
`fix-import-gate-dynamic-forms-cp{1,2}.md`.
WHY THE PANEL VERDICT STILL STANDS — the Q9 engine claims were RE-MEASURED by the landing integrator on
the merged bytes, not inherited: (a) engine over the committed repo rc0, and its `check`/`--report`/
`--json` streams are BYTE-IDENTICAL to master's engine on the same tree (so the change is invisible to
every real caller — no new false positive anywhere in the repo); (b) the legacy suites
`test_cog2_import_gate.py` + `test_cog3_import_gate.py` are BYTE-UNTOUCHED vs master (`git diff` empty)
and, with `test_cog4_boundary_rows.py` + `test_cog5_boundary_rows.py`, 229 passed; (c) the panel's
six-mutant shape was re-run by the integrator against BOTH engines side by side with the fenced token
SPLIT (so the token-grep rule cannot mask the result): the two literal controls keep IDENTICAL rule-id
attribution on both engines, all ten dynamic spellings go rc0-on-master -> rc1-on-this-engine carrying
the SAME rule id the literal dynamic spelling already carried (`FORBIDDEN_PROJECTION_TOKEN` — attribution
does not move), and six false-positive controls (own-`def import_module`, rebound name, unrelated target,
allowlisted importer, non-fenced lane, 200-deep fold nest) stay CLEAN on both. The change is therefore
STRICTLY WIDENING: it can only add catches, never retract one or re-attribute one. (d) `cog4-measure
--check` armed and within bound; census PASS at the e4-tightened maxima with zero headroom preserved
(the engine lives in `cabinet/scripts`, outside the `framework_production_*` counters); layer-sep new=0;
`verify-cognitive-phase4.sh` full green end-to-end after this re-bind.
WHAT WAS NOT DONE, stated plainly: this was NOT re-reviewed by a fresh frozen COG-4 panel. The
integrator re-ran the panel's Q9 claim surface (above) and the branch carries its own two adversarial
fresh-context review artifacts, cp1 and cp2; cp2 records that cp1's own residual text was FALSE BY
OMISSION and corrects it. A later session that wants a panel-grade re-review of the widened engine
should read cp2 first — its residual set is measured against these exact bytes and pinned by tests.
SIBLING BINDERS: `cabinet/scripts/cog2-import-gate.py` also sits in the COG-2 and COG-3 EXPECTED_SCOPEs,
so this landing moves those digests too (COG-2 98bae784 -> 59514d4a, COG-3 34a382fa -> 61644fda). They
are NOT re-bound and must not be: COG-0/1/2/3 are the digest-frozen historical instances their own
docstrings describe and were ALREADY BLOCK on master 26d4cce2 before this branch (measured: COG-0
f543dc1e vs 63f4643a, COG-1 25c2f5e3 vs 2fb7a390, COG-2, COG-3) — a pre-existing, by-design condition
this landing neither improves nor worsens. COG-4 is the one LIVE binding, and it is the one re-bound
here.)
(MOVED BY THE CAPTAIN-CONTACT LIVENESS LANDING, 2026-07-25 — d8d316b2... -> the value above. Landed
branch `feat/captain-contact-liveness` (PR #196, one commit db2a3346, merge 0830a076) over master
32ff7384: the Captain-contact dead-man (D1), the honest queued-vs-delivered sender (D4-cheap), and
severity-ordered watchdog findings (X). EXACTLY TWO in-scope paths moved, verified by intersecting the
resolved 85-entry scope with `git diff --name-only 32ff7384..db2a3346` rather than by reading the diff:
  (1) `cabinet/config/cognitive-architecture-contract.yml` — two `temporary_allowances` rows APPENDED
      (`framework_production_modules` +2, `framework_production_noncomment_lines` +386) for the new
      stdlib-only `framework/liveness` package. Declarative budget consumed by the census gate, not by
      any COG-4 engine. Census re-measured on the merged bytes: PASS at 238<=238 and 66934<=66934 —
      exact totals, zero headroom preserved, no maximum relaxed and no threshold touched.
  (2) `framework/watchdog/registry.py` — the path named in this review's scope for its
      `_parse_organ_manifests` surface. That function's body is BYTE-IDENTICAL on the merged bytes
      (measured line-exact over its 71-line span, base vs merged), as is `_resolve_organ_artifact`.
      What changed is its CALLER.
A BEHAVIOR-DELTA RE-BIND, stated plainly rather than inheriting the MECHANICAL-DELTA formula from the
re-binds above: `verify_no_silent_cron_failure` now tags every finding with a causal severity
(`_SEV_NOT_LOADED` 0 .. `_SEV_MARKER` 5; organ findings are `_SEV_ORGAN` 4) and STABLY SORTS before the
pre-existing 8-item truncation. Per-finding message TEXT is unchanged — measured, both organ literals
byte-identical base vs merged — and so is finding MEMBERSHIP; what moves is ORDER, and therefore WHICH
eight survive when more than eight findings exist. Differential run on this repo's own `_mini_probe`
fixture (memory-worker unloaded + retro-trigger exit 127):
    base   -> "...retro-trigger: last exit status 127; memory-worker: declared ... but not loaded ..."
    merged -> "...memory-worker: declared ... but not loaded ...; retro-trigger: last exit status 127"
Same set, same per-finding text, CAUSE first. That inversion is the point: the not-loaded scan appends
LAST, so in exactly the broad-outage case the truncation exists for, the line naming the cause was
always the first casualty. No COG-4 claim is retracted — the organ-floor detection logic and the
reviewed property "a silent organ inside a live runner trips its own floor" are untouched; only the
rendering order of a multi-finding detail string moved, and organ findings can now be displaced by
strictly more-causal rows (not-loaded / no-log / non-zero-exit) and can now displace error-marker
symptoms. Re-measured on the merged bytes, not inherited: `verify-cognitive-phase4.sh` full green
end-to-end after this re-bind; census PASS; layer-sep new=0; `framework/` 6511 passed and
`cabinet/scripts/tests` 4534 passed against a re-measured 32ff7384 baseline (6454 / 4523).
WHAT WAS NOT DONE, stated plainly: this was NOT re-reviewed by a fresh frozen COG-4 panel. The branch
carries its own adversarial fresh-context artifact,
`shared/interfaces/reviews/feat-captain-contact-liveness-cp1.md`, whose residual section records the
honest limit of that unit — the primary off-machine detector is INERT until an operator registers a
watcher, so the branch ships the mechanism, not the activation.
SIBLING BINDERS: `cabinet/config/cognitive-architecture-contract.yml` sits in the COG-0/1/2/3
EXPECTED_SCOPEs too, so this landing moves those digests as well (COG-0 63f4643a -> 869b2db6, COG-1
2fb7a390 -> 7f17308d, COG-2 59514d4a -> 7f4047d3, COG-3 61644fda -> 727b8fee). They are NOT re-bound
and must not be: all four were ALREADY BLOCK on pre-merge master 32ff7384 — measured, not assumed, by
running each verify twin there (recorded vs recomputed: COG-0 f543dc1e vs 63f4643a, COG-1 25c2f5e3 vs
2fb7a390, COG-2 b38632b9 vs 59514d4a, COG-3 78a7bf18 vs 61644fda; all exit 1). COG-4 was the one
binding GREEN on 32ff7384 (verify twin exit 0, recorded == recomputed == d8d316b2) and the only one
this landing turned BLOCK, so it is the only one re-bound. This commit edits ONLY the digest-excluded
review artifact, so the digest it records is stable under its own landing.)

(MOVED BY THE EGG EGRESS-DEFAULT FLIP, 2026-07-26 —
6f04c4bc47876ba2152aceaf9cb7feb003c8cd1f7f498d0c0c3cb955937e1cae -> the value above. Landed branch
`fix/egg-egress-default` over master f3914dde, executing the Captain's 2026-07-26 ruling that the egg
ship the framework's documented allow-all egress default with enforcement left as a one-command OPTION.
EXACTLY TWO in-scope paths moved, verified by intersecting the resolved 85-entry scope with
`git diff --name-only origin/master..HEAD` rather than by reading the diff:
  (1) `cabinet/scripts/egg-export-manifest.txt` — COMMENT LINES ONLY. The `delete
      instance/config/egress.yml` row and the `transform egress-default` row are byte-identical; only
      their explanatory prose changed, to stop claiming the shipped twin is `enforce: true`. Zero
      manifest semantics, zero rows added or removed, no expect-present/expect-absent rule touched.
  (2) `cabinet/scripts/tests/test_egg_export.py` — one assertion in
      `test_egress_default_is_the_scrubbed_twin` INVERTED under the ruling, plus its docstring. The
      byte-identity assertion (`shipped == twin`) is untouched; what changed is the posture pinned on
      top of it, and it was made STRICTLY STRONGER in the same edit: substring presence
      (`b"enforce: true" in shipped`) became an exact match on the single active `enforce:` scalar, so
      the egg shipping ANY unratified posture is still red. Substring matching would in fact have been
      wrong post-flip, since the twin's prose legitimately names the enabling value while telling a
      stranger how to opt in.
A MECHANICAL-DELTA re-bind per the cp3 precedent, never a restamp, and — unlike the two BEHAVIOR-DELTA
re-binds above — the claim is made here because it holds: ZERO COG-4 engine, organ, scheduler,
projection or trajectory bytes are touched by this landing. Neither moved path is a COG-4 surface; they
are bound only because the egg packaging manifest and its test sit inside the declared scope. The four
COG-4 §15 findings are untouched and none is re-derived. Re-measured on the merged bytes, not inherited:
`verify-cognitive-phase4.sh` full green end-to-end after this re-bind; the full `test_cog4_*` battery
702 passed 2 declared skips; `test_cog4_boundary_rows.py` + `test_cog5_boundary_rows.py` 113 passed;
`cog2-import-gate.py` rc0; the egg battery (`test_egg_export.py` + `test_egress_guard.py` +
`test_egress_dry_run_asymmetry.py`) 108 passed 1 skip; census PASS at every maximum with zero headroom
preserved — no maximum relaxed, no threshold touched, no `temporary_allowances` row added (this landing
adds no framework Python at all); layer-sep new=0; `null-hatch.sh` rc0.
WHAT WAS NOT DONE, stated plainly: this was NOT re-reviewed by a fresh frozen COG-4 panel. The two moved
paths are the egg packaging contract, not the phase's claim surface, and the landing carries its own
adversarial fresh-context review artifact for the branch.
SIBLING BINDERS: both moved paths sit in the COG-0/1/2/3 EXPECTED_SCOPEs too (measured: each of the four
scope tools names both), so this landing moves those digests as well (COG-0 dcf3b43d -> b454304d, COG-1
16f7547a -> e0efb3cf, COG-2 7f4047d3 -> 03a65104, COG-3 727b8fee -> 6a7bc7fe). They are NOT re-bound and
must not be: all four were ALREADY BLOCK on pristine master f3914dde — measured, not assumed, by running
each verify twin there (recorded vs recomputed: COG-0 f543dc1e vs dcf3b43d, COG-1 25c2f5e3 vs 16f7547a,
COG-2 b38632b9 vs 7f4047d3, COG-3 78a7bf18 vs 727b8fee; all exit 1). COG-4 was the one binding GREEN on
f3914dde (verify twin exit 0, recorded == recomputed == 6f04c4bc) and the only one this landing turned
BLOCK, so it is the only one re-bound. This commit edits ONLY the digest-excluded review artifact, so the
digest it records is stable under its own landing.)

(MOVED BY THE ATTENTION-WELL-SPENT LANDING, 2026-07-26 —
93839d991e56db1fe048e1df97774e1dd4b248f0071d90171979d38ab08109d4 -> the value above. Landed branch
`fix/attention-silence-ratchet` over master f07787fa: the cabinet was structurally biased toward going
quiet and its own score rewarded it — the OVI attention term was weighted `direction: inverse`, reading a
perfect 1.00 in EVERY window (7d/30d/365d) including a 7d window with 0.0 throughput and 0.0 verification.
EXACTLY ONE in-scope path moved, verified by intersecting the resolved scope with
`git diff --name-only origin/master..HEAD` (27 changed files, one of them in scope) rather than by reading
the diff:
  (1) `cabinet/config/cognitive-architecture-contract.yml` — ONE `temporary_allowances` row APPENDED
      (`framework_production_noncomment_lines` +252, phase `attention-well-spent`) for the fix's framework
      surface. Declarative budget consumed by the census gate, not by any COG-4 engine — the same class as
      the captain-contact-liveness rows two re-binds above. Census re-measured on the branch bytes: PASS at
      67186<=67186 — exact total, zero headroom preserved, no `maximum` relaxed and no threshold touched.
      The row's own reason records the honest accounting: 209 of those 252 lines are docstring prose and
      only 43 are executable code (measured, not estimated), and they were deliberately NOT reformatted
      into `#` comments — which the counter ignores, and which would have bought back ~209 lines by moving
      words sideways instead of shrinking anything.
A MECHANICAL-DELTA re-bind per the cp3 precedent, never a restamp, and the claim is made here because it
holds: ZERO COG-4 engine, organ, scheduler, projection or trajectory bytes are touched by this landing.
The moved path is not a COG-4 surface; it is bound only because the census contract sits inside the
declared scope. The four COG-4 §15 findings are untouched and none is re-derived. Re-measured on the
branch bytes, not inherited: `verify-cognitive-phase4.sh` full green end-to-end after this re-bind;
census PASS; layer-sep new=0; `cog2-import-gate.py` rc0; `null-hatch.sh` rc0; golden evals 30/30;
`framework/` 6587 passed and `cabinet/scripts/tests` 4665 passed against a re-measured f07787fa baseline,
with the one declared pre-existing red (`test_retro_shim.py::test_reexports_constants`) reproduced
identically on pristine master.
WHAT WAS NOT DONE, stated plainly: this was NOT re-reviewed by a fresh frozen COG-4 panel. The moved path
is a declarative budget row, not the phase's claim surface, and the landing carries its own review
artifact `shared/interfaces/reviews/fix-attention-silence-ratchet-cp1.md`.
SIBLING BINDERS: `cabinet/config/cognitive-architecture-contract.yml` sits in the COG-1/2/3
EXPECTED_SCOPEs too, so this landing moves those digests as well (COG-1 e0efb3cf -> 497909af, COG-2
03a65104 -> 9fc88f5c, COG-3 6a7bc7fe -> 6a6aa580). They are NOT re-bound and must not be: all three were
ALREADY BLOCK on pristine master f07787fa — measured, not assumed, by running each verify twin there
(recorded vs recomputed: COG-1 25c2f5e3 vs e0efb3cf, COG-2 b38632b9 vs 03a65104, COG-3 78a7bf18 vs
6a7bc7fe; all exit 1). COG-0 has a scope tool but NO review artifact on this tree, so it has no binding to
move. COG-4 was the one binding GREEN on f07787fa (verify twin exit 0, recorded == recomputed ==
93839d99) and the only one this landing turned BLOCK, so it is the only one re-bound. This commit edits
ONLY the digest-excluded review artifact, so the digest it records is stable under its own landing.)

(RE-BOUND ON THE MASTER MERGE, 2026-07-27 —
60ab5575264c12afc2bec225e9a943c8762900c2a4fa8b8fbb1ad2971ece1e38 -> the value above. The
attention-well-spent branch was rebased onto master by merge rather than by rewrite, and master had moved
f07787fa -> ac56ce78 under it.
READ THIS ONE DIFFERENTLY FROM THE NOTE ABOVE: when that note was written, COG-4 was the one binding GREEN
on f07787fa and this landing was the only thing turning it BLOCK. That is NO LONGER the starting
condition. COG-4 is ALREADY BLOCK on master ac56ce78 — measured, not assumed: the verify twin run there
exits 1 with recorded 93839d99 vs recomputed e7fccd9b, and the full `verify-cognitive-phase4.sh` on
pristine ac56ce78 exits 1 on that same binding. The captain-availability-dial landing (PR #210, merge
ac56ce78) appended two `temporary_allowances` rows to `cabinet/config/cognitive-architecture-contract.yml`
— an in-scope path — and did not discharge the re-bind ceremony. So this commit re-binds the digest to the
MERGED bytes and, as a side effect, clears a pre-existing BLOCK it did not cause. Recording that plainly
rather than quietly inheriting the credit: one of the two deltas folded into this digest is not this
branch's work.
EXACTLY ONE in-scope path moved vs origin/master ac56ce78, verified by intersecting the resolved scope
with `git diff --name-only origin/master..HEAD` (29 changed files, one in scope):
`cabinet/config/cognitive-architecture-contract.yml` — now carrying BOTH landings' rows, master's two
captain-availability-dial rows and this branch's one attention-well-spent row, reconciled by keeping both
sides rather than taking either wholesale. Census re-measured on the merged bytes: PASS at 239<=239 and
67578<=67578 — exact totals, zero headroom preserved, no maximum relaxed. This branch's row is unchanged
at +252; only its recorded running total was re-measured (67186/66934 -> 67578/67326) because master's
rows moved the base underneath it.
STILL A MECHANICAL-DELTA re-bind, and the claim still holds: ZERO COG-4 engine, organ, scheduler,
projection or trajectory bytes are touched by either landing folded here. Both are declarative budget rows
consumed by the census gate. The four COG-4 §15 findings are untouched and none is re-derived.
Re-measured on the merged bytes: `verify-cognitive-phase4.sh` full green end-to-end after this re-bind.
SIBLING BINDERS: the contract yml sits in the COG-1/2/3 scopes too, so this landing moves those digests as
well. They are NOT re-bound and must not be: all three were ALREADY BLOCK on pristine master ac56ce78 —
measured by running each verify twin there, all exit 1 (recorded vs recomputed: COG-1 25c2f5e3/3e0e6a84,
COG-2 b38632b9/04c276bb, COG-3 78a7bf18/218ba7dd). COG-0 has a scope tool but no review artifact on this
tree, so it has no binding to move. This commit edits ONLY the digest-excluded review artifact, so the
digest it records is stable under its own landing.)
MOVED BY THE SPEND-METER LANDING (2026-07-27, a30366943126b05011435269b1f72335a4455bd8f0fbfd1518a426ab462c2df2 -> the value above): a
MECHANICAL-DELTA re-bind per the cp3 precedent, never a restamp, and the claim is made here because it
holds. ZERO COG-4 engine, organ, scheduler, projection or trajectory bytes are touched. EXACTLY ONE
in-scope path moved, verified by intersecting the resolved 85-entry scope with
`git diff --name-only origin/master...HEAD` (41 changed files, one in scope) rather than by reading the
diff: `cabinet/config/cognitive-architecture-contract.yml` gains TWO temporary_allowances rows recording
the framework/cost/ package as an exact measured total (+4 modules, +778 noncomment lines). That file is
not a COG-4 surface; it is bound only because the census contract sits in the declared scope — precisely
the class of the attention-well-spent re-bind immediately prior (3dcd3e62) and the contact-liveness rows
before it (598868ed). No maximum was relaxed: the census re-measures PASS at 243<=243 modules and
68356<=68356 lines, exact totals, zero headroom preserved.
Re-measured on the branch bytes, not inherited: `verify-cognitive-phase4.sh` full green end-to-end after
this re-bind; census 29 passed; egg battery 58 passed 1 declared skip; `framework/` 6658 passed with the one
declared pre-existing red (`test_retro_shim::test_reexports_constants`) reproduced identically on pristine
master. NOT re-reviewed by a fresh frozen COG-4 panel; the branch carries its own review artifacts
(fix-spend-meter-uncapped-cp1.md, unit-sensor-cp1.md, unit-lanes-cp1.md).
SIBLING BINDERS NOT TOUCHED, deliberately: the contract yml also sits in the COG-1/2/3 scopes, all three of
which were ALREADY BLOCK on pristine master before this branch existed. Re-binding them would restamp
frozen gate archaeology. This commit edits ONLY the digest-excluded review artifact, so the digest it
records is stable under its own landing.)

---

## §15 standing questions — findings

### Q1 — Does any serve path return rows it did not hash in the same read?

**NO.** `framework/scheduler/serve.py` has exactly ONE public entry, `serve_schedule` (:126), routing through
`framework/projection/kernel.py::verified_single_read` (:223-285): the store is read ONCE (`read_jsonl_rows`,
:271 "the ONE read"), the chained hash re-derived from the RE-PARSED rows, bound to the manifest, and the
returned rows ARE the hashed rows. Panel probe (own code, store built end-to-end via the real
`cog3-rebuild.py`→`cog4-snapshot.py`→`cog4-schedule.py` CLIs in a tmp root): served rows == disk rows ==
`model.schedule_rows_hash` input; tampered row / REORDERED-but-identical rows (file-order chain, model.py:126-134)
/ forged counts / tampered+missing snapshot record / partial epoch key-set / snapshot echo forgery — 8/8
tamper classes `ScheduleRefused`, 1/1 pristine control ANSWERED. Package roots are import-inert in a fresh
subprocess (forbidden closure EMPTY; loaded = framework{,.organs,.projection,.scheduler} only). The serve
module's public surface is {`serve_schedule`, `ScheduleRefused`} + its imports — no second loader exists;
`cog4-schedule.py` reports THROUGH the loader (:69 "F1: report via the loader"); `cog4-dispatch-shadow.py`
serves through it (`run_shadow_dispatch` :569) and its availability probe returns no rows (Q4/F2).

### Q2 — Does any manifest-absent key skip a limb?

**NO.** The rows-hash key is MANDATORY-PRESENT (kernel :264-269): panel-deleted `schedule_rows_hash` AND
empty-string value both REFUSE ("MANDATORY-PRESENT (§6.3)"); the objectives `is not None and` skip-hole is
closed for this store. Epoch completeness limb refuses a partial wake-input key SET (serve.py:70-72, panel
probe). Snapshot builder: absent cortex `belief_store_hash` / objectives `graph_rows_hash` REFUSE
(snapshot.py:100-104/128-132 — "never an invented wake input"). Dispatcher: manifest-absent
`freshness_needs` => `freshness_underivable` REFUSE; absent `idempotency` => `idempotency_underivable`
REFUSE; missing organ manifest => `organ_manifest_missing` REFUSE (all panel-probed, zero would_dispatch).
Descriptor: absent block/member/idempotency discipline => `DescriptorRefused` (8 panel refusal probes incl.
the unknown-key fail-closed subset guard, descriptor.py:121-126).

### Q3 — Can any non-declared input (env/clock) reach the fold?

**NO.** Grep over `framework/{scheduler,projection,organs}`
(`os.environ|getenv|datetime.now|utcnow|time.time|getcwd|Path.cwd|expanduser|gethostname|random`): zero code
hits (three docstring prose mentions only). `build_snapshot` takes every input as a declared parameter
(snapshot.py:107-115); `validate_snapshot` recomputes SF2 family hashes + the registry hash from the
snapshot's own data (model.py:207-215). N1 panel probe: 3 subprocess rebuilds under PYTHONHASHSEED 0/1/987654321
from the same snapshot file → identical `schedule_rows_hash` (a9def50c37d7…). AST pins green in the battery
(`test_cog4_scheduler_ast_pin.py`); `test_cog4_sim_fold.py` purity mutants green.

### Q4 — Can the dispatcher execute anything?

**NO.** AST trace over `cog4-dispatch-shadow.py` + the whole planner tree: zero
subprocess/socket/http/urllib imports, zero `os.system/popen/exec*/spawn*` attributes. The CLI writes ONLY
the shadow log (O_EXCL lock + O_EXCL tmp + fsync + os.replace, :625-658). Hermetic mode never calls
`_act_with_undo_gap` (:301 live-only guard). All SIX §7.3 limbs fire in order — panel per-limb fixtures
(violate limb k, satisfy k−1): (1) tamper=>`serve_refused`/`rows_hash_mismatch` rc2 zero records; absent
key=>`rows_hash_key_absent`; missing store=>`safe_fallback` rc4, fixed safe schedule echoed, NEVER permission;
(2) any live-vs-recorded difference incl. recorded-exists/live-null AND live-extra-key (symmetric union,
:583-587) => `stale_snapshot` rc2; (3) `authority:ceiling` / `authority:undo_gap` / `authority:propose_only`
fail-safe, allow-set {auto, act_with_undo, auto_with_veto_window, notify_after} (:166-167); (4)
`budget_overflow` with `planner_admitted: true`; (5) `stale_organ:age=…` + `staleness_flagged`, never
auto-permission; eligibility rechecks (crashed-vs-unhealthy health classification :215-222, fallback honored,
dependency/capability unavailability with ORIGINAL identity); (6) re-derived idempotency key (row-carried keys
never trusted), replay across runs refuses `idempotency_replay` (panel double-run probe). §7.4 pointer
tripwire: a pointer created under a scratch-HOME `~/.cabinet/state/cog4-dispatch-pointer` => rc5
`pointer_tripwire`, zero records, on the DEFAULT path (expanduser proven live); no pointer => normal rc0. The
live machine carries no pointer file. Import pin `test_cog4_dispatch_ast_pin.py` green.

### Q5 — Can `capability` reach any verdict predicate?

**NO.** `_AuthorityJoint.check` (dispatch :257-309) reads ceiling/action_type/risk_class/undo_contract only;
grep for capability-keyed predicates over organs+scheduler+dispatcher: zero. Panel probe: two operations with
identical declared members resolve IDENTICAL enforcement tuples under distinct capabilities
(descriptor.py resolution is identity lookup). The corpus capability-blindness harness
(`test_cog4_exit_fixtures.py::_assert_capability_blindness`, capability-keyed mutant REDs) ran green per
cabinet across all three non-software fixtures.

### Q6 — Does any path grow ACTION_TYPES or bypass the adapter parity?

**NO.** `len(ACTION_TYPES) == 30` incl. `ambiguous`; the consequence-schema closed enum == ACTION_TYPES+null
(byte-mirror probe); census `central_action_types 30 <= 30`; v1 trajectory schema byte-identical to master
(`git diff --quiet` clean); the §16 protected union (classifier/matrix/policy_engine/matrix-yml/consequence
schema/v1 schema/HUMAN_PHRASES both mirrors/graduation/cog3 AST pin/extension gate pair) verified
byte-unchanged over baseline..HEAD by the rehearsal's per-path diff leg (that leg PASSED; the rehearsal's
later red is the sibling-residue ratchet, Q10). Parity: legs independent BY CONSTRUCTION
(`cog4-parity.py` leg b: own declarer scan `_leg_b_owner` :211 + own raw merge `_leg_b_declared` :225; source
between `action_types_leg` and `_leg_tuple` never calls `resolve_descriptor`/`descriptor_leg` — byte-probe).
Panel-seeded divergent manifest (declared `spend` vs matrix-derived `read_only_dispatch`) => exit 2, the
divergence RECORDED in the written record with both legs; flat operation id => setup exit 3 (the
collision guard — load-bearing while CG-33 schema validation is parked); zero-operations => exit 3 (no
vacuous green); the REAL composed pilot manifests => exit 0, zero divergent tuples. Trajectory v2: version
dispatch decided BEFORE v1 checks (contracts.py:265-275, `_is_v2_record` exact-literal marker); a namespaced
id in the effect compat `action_type` FAILS the v2 pattern (`compatActionType` excludes `/` — panel probe:
schema.pattern violation at `$.effects[0].action_type`); forged `v3` and absent versions fall to the FROZEN
v1 path and fail; the full evolution contracts suite green (47 passed).

### Q7 — Does composing rows drop a floor or LOOSEN its (cadence, threshold, probe) tuple?

**NO — recomputed by this panel from the pre-compose tree.** Pre-compose services.yml (master `fc51fd59`):
57 rows / 44 enabled; the five absorbed rows (charter-shadow, judge-calibration, prediction-calibration,
preference-pairs, world-census) all ENABLED, all daily. Post: 52 rows / 40 enabled; runner row
`interval_s: 43200` ≤ every absorbed 86400 period (cadence leg). Threshold leg: every organ
`max_staleness_seconds` 90000 ≤ the absorbed row's `_floor_for_entry` floor 93600 (all five, computed via the
REAL registry functions against the pre-compose text). Probe leg: five DISTINCT per-organ
`cabinet/cache/organs/<name>/last-run.json` receipt artifacts — never the shared runner log; the runner stamps
receipts only on HEALTHY completion (ok|honest_failure — judge-calibration's exit-1-by-design encoded as
`health_proof.exit_codes.honest_failure`), so a silent organ trips ITS OWN floor. COUNT leg: the REAL
`_parse_organ_manifests` over the post manifest derives exactly the 5 floors, zero problems; disabled rows
derive none (belt-and-braces re-filter, registry.py). `test_cog4_organ_runner_real.py`
TestRealDerivationCrossCheck + TestRealComposeForwardTree green (incl. thresholds-do-not-loosen and
per-organ-probe cells). Draft-lane: the ONE disabled-row retirement (L61 evidence bundle in
`feat-cog4-w6-e2-cp1.md`), row + hand-made plist deleted together.

### Q8 — Can the organ-runner observe the schedule store at all?

**NO — three independent ways.** (a) Behavioral, panel's own variant on the REAL CLI: a full schedule
artifact set injected under the runner's run-root `cabinet/cache/scheduler/` => byte-identical behavior JSON
vs the clean run, and the injected store byte-untouched after the wake. (b) Static: zero
`framework.scheduler` imports and zero store-path literals in the runner source (the two grep hits are
docstring prose :13/:70); `test_cog4_organ_runner_real.py::test_real_cli_source_is_statically_scheduler_blind`
green. (c) Boundary DELIBERATE ABSENCE bites: panel scratch-tree mutants — runner importing
`framework.scheduler` REDs `UNALLOWLISTED_SCHEDULER_IMPORTER`; runner naming the store (assembled token)
REDs `FORBIDDEN_SCHEDULER_DATAPLANE` (rows 4/7 `deliberately_absent`). Row→manifest association is DECLARED
(`organs:` block, services.yml:946-951; bare-name discovery refused without `--manifest-dir`).

### Q9 — The boundary ENGINE + exit gates N1-N9 (table below).

Engine: committed-tree run OK rc0; legacy suites `test_cog2_import_gate.py` + `test_cog3_import_gate.py`
116 passed (byte-compat + completeness invariant + every legacy mutant); per-row generated mutants
(`test_cog4_boundary_rows.py`) green in the battery; panel's own six mutants all RED with the row-correct
rule ids (runner→scheduler, runner→store, frontdoor→scheduler, scheduler→authority reverse, organs→frontdoor
reverse MF-A1, un-curated kernel importer).

### Q10 — Anything else that would refuse ship?

**No must-fix.** Full COG-4 battery: armed `5 failed, 687 passed, 1 skipped`; unarmed `5 failed, 686 passed,
2 skipped` — ALL five failures are DESIGNED retire-me flip signals ("<artifact> has LANDED — retire this
vacuity skip") awaiting the landing integrator's §13 corpus surgery: the floor derivation arm
(test_cog4_floor_conservation), the verify-twin + real-pilot measurement arms (test_cog4_measurement), and
the runner invariance + store-blindness arms (test_cog4_organ_runner). Every flipped property is pre-proven
GREEN out-of-band: `test_cog4_measure_baseline.py` 16/16; `test_cog4_organ_runner_real.py` (e2's routed
drop-in) full green. Both skips declared (wall-clock posture skip, armed by the twin; CG-33 germline-window
vacuity skip — the §4.5 amendment is FILED, window unopened, PARK marker present). `verify-cognitive-phase4.sh`:
every pre-battery leg green — `cog4-measure --check` ARMED within bound ("proxies EXACT, wall-clock <= bound"),
review-absent skip-loud branch, pointer tripwire clean, `verify-cognitive-architecture.sh` 76 passed,
census PASS at the e4-TIGHTENED maxima (`services_total 52<=52`, `services_enabled 40<=40`,
`central_action_types 30<=30`, modules `236<=236`, lines `66548<=66548` — zero headroom, observed==max),
layer-sep OK (new=0); overall exit 1 at the battery leg = the documented pre-surgery interim, and the
ROLLBACK REHEARSAL is likewise DESIGNED-RED at HEAD (12-file e2/e3 sibling residue — the §16 manifest's
`sibling_landing_note` + e3 cp1 §6 declare it; the strict inverse-diff equality is the completeness ratchet
WORKING; its protected-surface and A13 legs passed before the ratchet). The §16/scope pair is
force-coupled: `resolve_scope()` fails closed on a one-sided edit. Standalone: A13 parity OK (351 rows);
egg battery 58 passed + 1 declared machine-shape skip (twin delete + expect-absent pairs for all three
phase-4 twins; expect-present for parity/dispatch/runner/measure CLIs + the tracked parity record + S0
baseline); anti-phantom probe — `COG4_ENFORCE_BOUND` is the only COG4_* flag in the twin and has live
non-twin consumers (cog4-measure.py, test_cog4_measurement.py, test_cog4_measure_baseline.py); the e3
claim-surface fix (2338d6c9) removed the phantom `--mode` flag. All four PARK markers exist (officer-plist
cleanup W1-u3; cortex serve adoption W3-u3; objectives kernel adoption W3-u4; organ schema validation W4-u1).
Fleet truth: rowless template-organ set pinned to EXACTLY the 9 (conservation guard green; officer-leakage
subset tolerant pending parked u3). N8: the three non-software cabinets (garden-delivery extended +
harbor-warehouse + care-rota, MR4) ran end-to-end through the REAL CLIs in the battery with the enum-growth
walls asserted and the operation-name-authority mutant exercised per cabinet.

---

## Findings register

| id | severity | finding | file:line | disposition |
|---|---|---|---|---|
| P1 | NOTE | Shadow-log replay window: `replay_keys` are read BEFORE `append_shadow_log`'s O_EXCL lock, so two dispatchers racing one log could each record `would_dispatch` for the same idempotency key (the log itself cannot corrupt; single-process replay refusal panel-proven). Zero effect surface exists this phase. | cog4-dispatch-shadow.py:858-877 vs :625-658 | Recorded; MUST be folded into the future cutover amendment's requirements (read+check+append under one lock) before any dispatch becomes real. Not ship-blocking in shadow. |
| P2 | NOTE (as designed) | After a `ScheduleRefused`, `_classify_refusal`/`_probe_availability` re-read store bytes to CLASSIFY the refusal (availability vs integrity). No rows are served from the probe; a raced re-read degrades conservative (`store_corrupt`). Documented in the CLI header. | cog4-dispatch-shadow.py:315-356 | As designed; recorded so the second read is never mistaken for a serve path. |
| P3 | INFO | `framework/organs` imports third-party `yaml` — a declared allowance in the organs package pin (stdlib \| yaml \| internal), unlike the stdlib-only kernel/watchdog surfaces; the canonical-bytes stdlib replica is parity-pinned against the kernel. | framework/organs/registry.py:54; test_cog4_organs_package.py:622 | As designed (module docstring states the row-6 rationale). |
| P4 | INFO | Designed interim at this tip: 5 corpus flip-arms RED + rollback rehearsal RED (sibling residue) + review-scope EXPECTED_SCOPE excludes e2/e3 surfaces; verify twin exits 1 overall. All declared in-tree with forcing functions; discharge = the landing integrator's §13 surgery + §16-manifest/EXPECTED_SCOPE paired extension + review re-freeze/digest re-bind. | verify-cognitive-phase4.sh:14-22; rollback manifest sibling_landing_note; e3 cp1 §6-7 | The integrator's named move at landing; this panel's verdict binds the reviewed bytes. |
| P5 | INFO | `cog4-snapshot.py` and `cog4-schedule.py` have no `expect-present` egg lines (they ship by default; the other four cog4 CLIs + records are asserted) — consistency nit vs the cog3 expect-present precedent. | cabinet/scripts/egg-export-manifest.txt:489-520 | Optional tidy at landing; egg battery green either way. |

## N1-N9 exit-gate table

| gate | mechanical proof | run + result |
|---|---|---|
| N1 determinism | panel triple: 3 subprocess rebuilds × PYTHONHASHSEED {0,1,987654321} from one snapshot → identical chained hash; delete→rebuild = the kernel rollback grammar; file-order chain refuses reorder | PASS (panel probe + sim-fold battery green) |
| N2 starvation | declared bounds are snapshot inputs (organ `starvation_bound` else scheduler_policy default, fold.py:99-107); sim-7 battery | PASS (battery) |
| N3 forged/stale | tamper/absent-key/reorder/counts/snapshot-binding all REFUSE at serve; stale/null/extra-key symmetric union REFUSES at dispatch | PASS (8 serve + 3 dispatch panel probes) |
| N4 budget | `budget_overflow` at dispatch though planner admitted (`planner_admitted: true`) | PASS (panel probe) |
| N5 authority | ceiling/undo-gap/propose_only/gated refuse via the pinned read-only joint; allow-set exact | PASS (panel probes + exit fixtures) |
| N6 latency/cost | armed `cog4-measure --check` vs the tracked S0 baseline within bound; proxies EXACT always-on; `COG4_ENFORCE_BOUND` consumers live (anti-phantom probe) | PASS (verify leg + probe) |
| N7 service-retirement | 57/44 → 52/40 recounted by panel parser; census maxima TIGHTENED to actuals (52<=52, 40<=40, observed==max); fleet-truth conservation green (rowless == the pinned 9) | PASS |
| N8 three non-software cabinets | garden-delivery (extended) + harbor-warehouse + care-rota end-to-end via real CLIs; zero new central members (30 pinned, mirrors byte-intact) | PASS (battery + panel walls) |
| N9 parity | real pilot manifests → exit 0 zero divergent tuples; seeded divergence exit 2 + recorded; legs independent at bytes; tracked record gated by test_cog4_parity_record.py | PASS |

## Command log (this run)

1. clone canonical remote + checkout `f62094f7c6ee419db20df3d5445a89f5258467bb` (chain verified over master fc51fd59)
2. `verify-cognitive-phase4.sh` full → N6 armed within bound; census PASS (52/40/30/236/66548 observed==max); layer-sep OK; battery `5 failed 687 passed 1 skipped` (the 5 = designed flip-arms) → exit 1 (documented interim)
3. unarmed battery → `5 failed 686 passed 2 skipped` (both skips declared)
4. `cog2-import-gate.py` → OK rc0; legacy engine suites → 116 passed
5. A13 heredoc → OK 351 rows; `test_egg_export.py` → 58 passed 1 declared skip
6. `cognitive-phase4-rollback-rehearsal.py` → protected-surface + A13 legs PASS, then DESIGNED-RED on the declared 12-file e2/e3 sibling residue (completeness ratchet)
7. panel probe battery 1 (31): real-CLI store build; 8 serve tamper classes REFUSE + pristine control; dispatch limbs 1-6 per-limb fixtures; pointer tripwire under scratch HOME (rc5) + clean run (rc0); no-subprocess AST trace; import-inertness (subprocess re-probe)
8. panel probe battery 2 (43): 8 organ refusals + collision + capability-blindness + registry refusals; trajectory v2 dispatch/namespaced/forged/absent + v1 suite 47 passed; parity divergence rc2 + record / flat-id rc3 / vacuity rc3 / real pilot rc0 / leg-independence bytes; 6 boundary mutants RED with row-correct ids; runner injection byte-identical + store untouched; N1 triple; census recount; floor COUNT+TUPLE recompute; anti-phantom flags
9. panel sweep 3: A-M6 grep clean; freshness/idempotency/manifest underivable refusals; ACTION_TYPES walls; egg lines; PARK markers ×4; draft-lane plist gone; v1 schema byte-untouched; worktree clean
10. `cognitive-phase4-review-scope.py --print` → `d6625b82fc969ce9958e3eebcb96b58c4c6483cf5e3f14fb6cce8908f086ac6e`

## Must-fix list

**None.** The five corpus flip-arms + the rehearsal sibling-residue red are the DOCUMENTED pre-surgery
interim (pre-proven green out-of-band), discharged by the landing integrator's §13 corpus surgery + the
force-paired §16-manifest/EXPECTED_SCOPE extension + review re-freeze; P1 binds the future cutover
amendment, not this phase.

(MOVED BY THE ARM-THE-CABINET LANDING, 2026-07-26 —
93839d991e56db1fe048e1df97774e1dd4b248f0071d90171979d38ab08109d4 -> the value above. Landed branch
`feat/arm-the-cabinet` over master 6079be4d, executing four Captain rulings of 2026-07-26 as one unit.
EXACTLY TWO in-scope paths moved, verified by intersecting the resolved 114-entry scope with
`git diff --name-only origin/master..HEAD` rather than by reading the diff:
  (1) `cabinet/services.yml` — 8 parked rows armed, 2 NEW rows added (the two COG-3 captain-report
      CLIs), 2 rows given machine-readable parking reasons. The COG-4 organ-runner row, its `organs:`
      block and every organ manifest are BYTE-UNTOUCHED.
  (2) `cabinet/config/cognitive-architecture-contract.yml` — the two fleet maxima raised
      (`services_total` 52->54, `services_enabled` 40->50) and `framework_production_noncomment_lines`
      60067->60155, each re-pinned at observed==max with zero headroom; NO `temporary_allowances` row
      added; no other budget touched.
A BEHAVIOR-DELTA RE-BIND, and — unlike the mechanical ones above — it moves a number this review's own
exit gate names, so that is stated first rather than buried. N7's exit condition was
`services_total` < 57 AND `services_enabled` < 44 AT THE DONE-FLIP, with maxima tightened to the phase
actuals under the shrink-only law. That condition WAS met and stays historically true (52 < 57,
40 < 44, measured at the flip). This landing GROWS the fleet past those actuals under an explicit
Captain ruling of 2026-07-26 — one bump for the whole batch, re-pinned with zero slack so the ratchet
still bites at 54/50. Shrink-only is therefore SUSPENDED ONCE BY RULING, not quietly relaxed; no
maximum was set above the observed value and no allowance row hides the growth.
What is NOT retracted, measured rather than asserted on the landed bytes: the §9 fleet-truth
conservation guard and the §9.2 COUNT+TUPLE floor conservation both re-run GREEN
(`test_cog4_fleet_truth.py` + `test_cog4_floor_conservation.py`, 29 passed) — no row moved OUT of the
manifest, no new row-less template plist appeared, and every composed organ keeps its own derived
floor. The composed-runner claim ("a persistently failing organ inside a live runner trips its own
floor") is untouched; the compose itself is untouched.
Re-measured on the landed bytes, not inherited: `verify-cognitive-phase4.sh` full green end-to-end
after this re-bind; census PASS at 54/50 with observed==max; layer-sep new=0; golden evals 29/29;
null-hatch PASS; `framework/` 6531 passed / 25 skipped / 1 failed (the single known pre-existing
`test_retro_shim.py::test_reexports_constants`, identical to the re-measured origin/master baseline)
and `cabinet/scripts/tests` 4686 passed / 28 skipped against a re-measured 6079be4d baseline
(6531/25/1 and 4670/28).
WHAT WAS NOT DONE, stated plainly: this was NOT re-reviewed by a fresh frozen COG-4 panel. The branch
carries its own artifact, `shared/interfaces/reviews/feat-arm-the-cabinet-cp1.md`, whose residual
section records the honest limits of that unit — two rows the Captain asked for that were verified off
for a REAL reason and left off, and one ruling (drafting to act-then-tell) that could not ship because
its file is germline and is filed as CG-35 instead.
SIBLING BINDERS: `cabinet/config/cognitive-architecture-contract.yml` sits in the COG-0/1/2/3
EXPECTED_SCOPEs too, so this landing moves those digests as well. They are NOT re-bound and must not
be: all four were ALREADY BLOCK on pre-change master 6079be4d — measured, not assumed, by running each
verify twin in a detached worktree there (all exit 1; recorded digests COG-0 f543dc1e, COG-1 25c2f5e3,
COG-2 b38632b9, COG-3 78a7bf18). COG-4 was the one binding GREEN on 6079be4d (verify twin exit 0) and
the only one this landing turned BLOCK, so it is the only one re-bound. This commit edits ONLY the
digest-excluded review artifact, so the digest it records is stable under its own landing.)
RE-BOUND AFTER MERGING origin/master 888255b6 (2026-07-27, 0305f77547e14563c1a8505c14336ec4e8993fbc133217ce81136f7e4c5c4ce5 -> the value above): the merge brought a concurrent landing's own re-bind of this same artifact, so the two digest lines conflicted textually while BOTH landings' in-scope deltas were additive and disjoint. Resolved by recomputing over the MERGED committed tree rather than by picking a side — a hand-picked digest from either parent would have recorded a tree that never existed. Still a MECHANICAL-DELTA re-bind, never a restamp: ZERO COG-4 engine, organ, scheduler, projection or trajectory bytes are touched by this branch; its only in-scope path remains cabinet/config/cognitive-architecture-contract.yml (the two census allowance rows). Census re-measured on the merged bytes; verify-cognitive-phase4.sh re-run green after this re-bind.)

(RE-BOUND BY THE ARM-THE-CABINET LANDING REVIEW, 2026-07-26 — 77df1746138bb26148bed68ccbed438e5291da65a7ac4ee1ec1002366f35880e
-> the value above. Mechanical, and the reason is stated before the claim: this binding was ALREADY
BLOCK on origin/master before this branch existed. Master carries the ORIGINAL
93839d991e56db1fe048e1df97774e1dd4b248f0071d90171979d38ab08109d4 while computing
e7fccd9b622f479d1f098962778163725a88927fde1bb85394496463f2b2dbe4 (measured on master a55dea44,
`verify-cognitive-phase4.sh` exit 1) — PR #210 moved an in-scope path and did not re-bind. This
landing does not inherit that red; it closes it.
EXACTLY TWO in-scope paths moved since the re-bind above, verified by intersecting the resolved
85-entry scope with `git diff --name-only 9883f270..HEAD` rather than by reading the diff:
  (1) `cabinet/config/cognitive-architecture-contract.yml` — the captain-availability dial's two
      allowance rows (from master, PR #210) plus this review's own
      `framework_production_noncomment_lines` 60155 -> 60164 re-pin (+9 measured), still
      observed==max with zero headroom.
  (2) `cabinet/scripts/egg-export-manifest.txt` — the availability dial's delete + expect-present
      pair (from master, PR #210).
NO COG-4 implementation path moved: not `framework/projection`, `framework/scheduler`,
`framework/organs`, no organ manifest, no runner, no measurement surface, no fixture. The behavior
this review's verdict covers is byte-untouched, so this is a scope-membership re-bind and NOT a
behavior-delta re-bind like the entry above it.
WHAT WAS NOT DONE, stated plainly: no fresh frozen COG-4 panel ran. What DID run, on the landed
bytes: `verify-cognitive-phase4.sh` green end-to-end after this re-bind; census PASS at 54/50/67423
observed==max; layer-sep new=0; import gate exit 0; golden evals 30/30; A13 ledger parity GREEN
(353/353, 0 findings); null-hatch PASS; `framework/` 6573 passed / 25 skipped / 1 failed and
`cabinet/scripts/tests` 4711 passed / 28 skipped — the single failure being the known pre-existing
`test_retro_shim.py::test_reexports_constants`, identical to a re-measured origin/master a55dea44
baseline (6573/25/1). The landing review's own findings — a role_slug traversal that let the ARMED
loop rewrite an arbitrary tracked .yml, and a phantom journal row whose advertised inverse removes a
capability the loop never granted — are fixed in this same branch with ten arms that fail against the
pre-fix module.
SIBLING BINDERS unchanged from the note above: COG-0/1/2/3 were already BLOCK on pre-change master and
are NOT re-bound here.)

(MERGE RE-BIND, 2026-07-26: `fix/attention-silence-ratchet` (PR #211) landed on master while this
branch was in review and re-bound this same digest to 41a85f9e...'s sibling
a30366943126b05011435269b1f72335a4455bd8f0fbfd1518a426ab462c2df2. Two concurrent landings cannot both
be right about one number, so it is recomputed over the MERGED tree rather than either side being
picked: 0305f77547e14563c1a8505c14336ec4e8993fbc133217ce81136f7e4c5c4ce5. The digest line was the ONLY merge conflict in this
artifact; both landings' notes above are preserved verbatim, neither overwritten. In-scope paths
carried in by that merge: the census contract (its attention allowance) — no COG-4 implementation
path, so this stays a scope-membership re-bind. `verify-cognitive-phase4.sh` exits 0 on the merged
tree.)

(RE-BOUND BY THE CAPTAIN-DATES LANDING, 2026-07-27 — 0305f77547e14563c1a8505c14336ec4e8993fbc133217ce81136f7e4c5c4ce5
-> 5615aae1867d54024ac851578e7970611e55ff7a2860bd83d7d879bb5f10f0aa, superseded by the merge note below. EXACTLY TWO in-scope paths moved, verified by intersecting the resolved 85-entry
scope with `git diff --name-only origin/master..HEAD` rather than by reading the diff:
  (1) `cabinet/config/cognitive-architecture-contract.yml` — one new
      `framework_production_noncomment_lines` allowance row for the dates store (+208 measured; the
      env.py resolver family plus the morning_synthesis briefing leg, ZERO new modules), re-measured
      OVER THE MERGED TREE at 67883 vs 67675 base, still observed==max with zero headroom.
  (2) `cabinet/scripts/egg-export-manifest.txt` — the dates store's `delete` +
      `expect-present` pair, the same shape the availability dial added.
NO COG-4 implementation path moved: not `framework/projection`, `framework/scheduler`,
`framework/organs`, no organ manifest, no runner, no measurement surface, no fixture. The behavior
this review's verdict covers is byte-untouched, so this is a SCOPE-MEMBERSHIP re-bind, not a
behavior-delta one.
WHAT WAS NOT DONE, stated plainly: no fresh frozen COG-4 panel ran. What DID run on the merged bytes:
`verify-cognitive-phase4.sh` green end-to-end after this re-bind; census PASS at 54/50/67883
observed==max; layer-sep new=0; state-persistence 0 UNACCOUNTED; docs-track-code GREEN; A13 ledger
parity GREEN (353/353); golden evals 30/30 (EVAL-027 included, extended by this landing and shown RED
against pre-change state first); `framework/` 6653 passed / 26 skipped / 1 failed and
`cabinet/scripts/tests` 4727 passed / 28 skipped / 1 failed — the framework failure being the known
pre-existing `test_retro_shim.py::test_reexports_constants` (a locally-installed pipe constant CI does
not have), and the cabinet one a wall-clock latency bound over an ephemeral Postgres cluster that
passes in isolation under no load.
SIBLING BINDERS unchanged: COG-0/1/2/3 were already BLOCK on pre-change master and are NOT re-bound
here. This commit edits ONLY the digest-excluded review artifact, so the digest it records is stable
under its own landing — verified by recomputing after the edit.)
(RE-BOUND 2026-07-27, `fix/hook-redos`, same commit as the change that moved the
bytes. The moved file in scope is `cabinet/config/cognitive-architecture-contract.yml`:
ONE `temporary_allowances` row paying for the +1 framework line of
`policy_engine._STMT_RUN`, the rewrite that removes catastrophic backtracking from
the `sed -i` write pattern (52 of 80,307 recorded officer calls exceeded 1.5s in it,
and the hook has no time bound). The COG-4 findings are unaffected — no organ, no
scheduler surface, no serve surface, no COG-4 entry point. The landing's other two
files, `framework/authority/policy_engine.py` and `cabinet/scripts/policy-shadow.py`,
are not in EXPECTED_SCOPE. Reviewed in `fix-hook-redos-cp1.md`, with equality proved
in both directions and re-checked over all 80,307 recorded calls: 0 verdict changes.)

(MERGE RE-BIND, 2026-07-27: the spend-meter landing (PR #215) reached master while this branch was in
CI and re-bound this same digest to 540c08fb.... Two concurrent landings cannot both be right about one
number, so it is recomputed over the MERGED committed tree rather than either side being picked — a
hand-picked digest from either parent would record a tree that never existed. Merged value:
e68adad9456b80394270fa6354b65d6f4a5de10162235232b787571e1e3e2b0a. The digest line was the ONLY conflict in this artifact;
both landings' notes above are preserved verbatim, neither overwritten. In-scope paths carried in by the
merge: the census contract (the spend meter's two allowance rows) — no COG-4 implementation path, so this
stays a scope-membership re-bind. Census re-measured on the merged bytes: PASS at 243 modules / 68661
lines, observed==max with zero headroom, the dates row still +208. `verify-cognitive-phase4.sh` re-run
green end-to-end on the merged tree after this re-bind.)

(MOVED BY THE CHANNEL-FLATLINE ALARM LANDING, 2026-07-27 —
e68adad9456b80394270fa6354b65d6f4a5de10162235232b787571e1e3e2b0a -> the value above. Branch
`feat/channel-flatline-alarm` (PR #224), one commit b7dcde05 over master 19d1c2e1: a captain-facing
channel that goes silent now says so once, per Captain-Seat dry-run finding 2.
A SCOPE-MEMBERSHIP re-bind, and the claim is made here because it holds. EXACTLY ONE in-scope path
moved, verified by intersecting the resolved 85-entry scope with
`git diff --name-only origin/master...HEAD` (12 changed files, one in scope) rather than by reading
the diff: `cabinet/config/cognitive-architecture-contract.yml` gains TWO `temporary_allowances` rows
(`framework_production_modules` +1, `framework_production_noncomment_lines` +390) for the new
`framework/frontdoor/card_flatline.py` detector and its two delivery seams. That file is not a COG-4
surface; it is bound only because the census contract sits in the declared scope — the same class as
the spend-meter (a3036694), attention-well-spent (3dcd3e62) and contact-liveness (598868ed) re-binds
above. NO maximum was relaxed and no threshold touched: the census re-measures PASS at 244<=244
modules and 69051<=69051 lines, exact totals, zero headroom preserved.
NO COG-4 implementation path moved: not `framework/projection`, `framework/scheduler`,
`framework/organs`, no organ manifest, no runner, no measurement surface, no fixture, no boundary row.
The eleven other changed paths sit OUTSIDE this scope and are named for the record: the new detector,
probe, runbook and two test modules; `framework/frontdoor/{tell_digest,run_briefing}.py`;
`cabinet/scripts/cabinet-doctor.sh` (a new check 16); `cabinet/scripts/docs-sweep-allowlist.txt`;
the root `conftest.py` (one new read fence); and this landing's own FW-019 proof
`feat-channel-flatline-alarm-cp1.md`.
Re-measured on the branch bytes, not inherited: `verify-cognitive-phase4.sh` full green end-to-end
after this re-bind; census 29 passed; `cabinet/scripts/tests` 4768 passed / 28 skipped;
`framework/` 6748 passed with the one declared pre-existing red
(`test_retro_shim::test_reexports_constants`, a locally-installed pipe constant CI does not have)
reproduced identically on pristine master.
NOT re-reviewed by a fresh frozen COG-4 panel; the branch carries its own FW-019 artifact.
SIBLING BINDERS NOT TOUCHED, deliberately: the contract yml also sits in the COG-1/2/3 scopes, all
three of which were ALREADY BLOCK on pristine master before this branch existed. Re-binding them
would restamp frozen gate archaeology. This commit edits ONLY the digest-excluded review artifact, so
the digest it records is stable under its own landing — verified by recomputing after the edit.)

Verdict: PASS

MOVED BY THE MATRIX-CLASS-MAPPING-PIN LANDING (2026-07-27,
e68adad9456b80394270fa6354b65d6f4a5de10162235232b787571e1e3e2b0a -> the value
above). MECHANICAL-DELTA re-bind: exactly ONE in-scope path moved,
`cabinet/config/cognitive-architecture-contract.yml`, and the only change to it
is one appended `temporary_allowances` row (`matrix-class-mapping-pin`,
framework_production_noncomment_lines +65, 68661 -> 68726). No reviewed BEHAVIOUR
byte changed: the branch's executable changes are all in
`framework/authority/{matrix,classifier,deploy_classifier}.py` and
`framework/authority/tests/test_matrix.py`, none of which is in this scope
(verified by intersecting `git diff --name-only origin/master...HEAD` against
the tool's resolved EXPECTED_SCOPE, not by reading the diff).

RE-MEASURED, not assumed: `cognitive-architecture-census.py --check` PASS at
observed == max (68726 <= 68726), and the full `verify-cognitive-phase4.sh`
twin runs end-to-end green on this commit. The digest was recomputed over the
COMMITTED tree and folded into the SAME commit — this artifact is excluded from
its own scope, so the amend is stable under itself. NOT done: no COG-0/1/2/3
twin was re-bound (frozen-historical, already BLOCK by design), and no prose
section of this review was edited — no reviewer saw new bytes, because none of
the reviewed bytes changed behaviour.

RE-BOUND ON THE MASTER MERGE, 2026-07-27 —
8421cbabbc5331087530603011d139ae0acfdd4d82cfeed45f95006ffa171f82 -> the value
above. The matrix-class-mapping-pin branch merged origin/master 91412878
(fail-closed-control-plane, channel-flatline-alarm, ask-batching and
dashboard-availability landings). Both sides had appended a
`temporary_allowances` row to `cabinet/config/cognitive-architecture-contract.yml`,
the one in-scope path either side touched; the conflict was resolved by keeping
BOTH rows, and the branch's own row was RE-MEASURED against the new base rather
than carried (69116 vs 69051 at 91412878; +65 unchanged, since the growth is
that unit's own lines). Still a MECHANICAL-DELTA re-bind: no reviewed BEHAVIOUR
byte changed on either side of the merge.

MOVED BY THE RECIPIENT-ALL-INTERNAL-QUANTIFIER LANDING (2026-07-27,
7f05bdcfaa716f78a9fb638ab464d5fd41699a388e9c13107957fdc128ca7e35 -> the value
above). MECHANICAL-DELTA re-bind: exactly ONE in-scope path moved,
`cabinet/config/cognitive-architecture-contract.yml`, and the only change to it
is one appended `temporary_allowances` row
(`recipient-all-internal-quantifier`, framework_production_noncomment_lines
+13, 69116 -> 69129). No reviewed BEHAVIOUR byte changed: the branch's
executable changes are all in `framework/authority/classifier.py` and
`framework/authority/tests/test_classifier.py`, neither of which is in this
scope — verified by intersecting `git diff --name-only origin/master...HEAD`
against the tool's resolved scope, not by reading the diff (the intersection is
exactly the contract file).

RE-MEASURED, not assumed: the old digest above was recomputed over HEAD rather
than carried from the previous re-bind note (master moved between them), and
`cognitive-architecture-census.py` is PASS at observed == max (69129 <= 69129).
The digest was recomputed over the COMMITTED tree and folded into the SAME
commit — this artifact is excluded from its own scope, so the amend is stable
under itself. NOT done: no COG-0/1/2/3 twin was re-bound (frozen-historical,
already BLOCK by design), and no prose section of this review was edited — no
reviewer saw new bytes, because none of the reviewed bytes changed behaviour.

RE-BOUND 2026-07-27 by the `feat/personal-preset-live` landing: 3188bf08… -> 26528114….
(First bound at b3523559… -> e7926158…; RE-MEASURED after merging origin/master,
whose `fix/propose-means-propose` landing moved the same two in-scope files
mid-flight. The merge kept BOTH allowance blocks — neither landing's row was
dropped — and the branch census re-reads PASS at observed == max against every new
baseline (6e50570f, then 8095ded9 after the hook-redos landing), with the module
delta exactly +1/+331 each time, which is the check that the number measures
this module and not a merge.)
ONE in-scope surface changed, `cabinet/config/cognitive-architecture-contract.yml`
(it sits in `restore_from_baseline` and is therefore digest-bound), and the change
is two `temporary_allowances` rows plus one `expansions` row paying for
`framework/sources/local.py` — the local-folder PersonalSource that unblocks
`presets/personal/`. NO COG-4 implementation byte changed: intersecting
`git diff --name-only origin/master...HEAD` with the tool's resolved scope yields
exactly the contract file. `cognitive-architecture-census.py` is PASS at
observed == max (245 <= 245 modules, 69985 <= 69985 lines) with the expansion row
registered. The digest was recomputed over the COMMITTED tree and folded into the
same landing; this artifact is excluded from its own scope, so the edit is stable
under itself.

NOT done: the COG-0/1/2/3 twins were NOT re-bound, which is the state the
`cognitive-phase4` CI job's own scope note already records ("the phase-0/1/2/3
twins are the digest-frozen HISTORICAL instances their own docstrings describe,
and all of them are already BLOCK on master by design"). Re-measured here on a
clean clone of `origin/master` at 91faed1b, before this branch existed: phase 0
f543dc1e -> 268e01b4, phase 1 25c2f5e3 -> 3168b0b1, phase 2 b3863291 ->
ae79b6e2, phase 3 78a7bf18 -> fde71324, and phase 4 clean. Re-binding a frozen
historical twin here would absorb earlier landings' drift under this one's name
and bless bytes no reviewer on this branch has read, so they are left as they
were.

RE-BOUND 2026-07-27 by the `feat/personal-preset-live` landing: 9c1a8082… -> 8bee10cd….
ONE in-scope surface changed, `cabinet/config/cognitive-architecture-contract.yml`
(`restore_from_baseline`, therefore digest-bound): two `temporary_allowances` rows
plus one `expansions` row paying for `framework/sources/local.py`, the
local-folder PersonalSource that unblocks `presets/personal/`. NO COG-4
implementation byte changed — intersecting `git diff --name-only
origin/master...HEAD` with the tool's resolved scope yields exactly that file.
RE-MEASURED on every merge rather than carried: master moved four times while
this branch was in flight, and the census re-reads PASS at observed == max
against each new baseline with the module delta exactly +1/+331 every time
(d7c66fe2 70434 -> 70765), which is the check that the number measures this
module and not a merge. The concurrent `feat/source-ownership-class` landing
edited the same contract and the same census tests; BOTH landings' allowance and
expansion rows are kept (verified by set-difference against
`origin/master`, zero rows lost), and this branch took master's census-test
version wholesale — its bijection assertion is strictly stronger than the
"no unregistered surplus" form this branch had written for the same defect, and
it additionally catches a row that outlives its member.

---

## Re-bind 2026-07-27 (merge of origin/master into iso-port-composition)

The gate blocked correctly — reviewed bytes were not tested bytes — and this records why
the digest moved rather than quietly restamping it.

Three of the 85 in-scope paths changed, and NONE of them by this branch. All three are
master's own commits arriving through the merge, each already reviewed on its own PR:

  cabinet/config/cognitive-architecture-contract.yml  — the expansion-gate set pins
      (D3, 2026-07-27), adding budget arms for the surfaces the mass budgets are blind to
  cabinet/scripts/egg-export-manifest.txt             — the recipient-exclusions and
      expansion-registry rows
  cabinet/scripts/tests/test_egg_export.py            — the matching assertion for the
      recipient-exclusions twin

Nothing in this branch's own work touches the COG-4 scope: it is the world layout, the
renderer and the check harness. The digest is re-anchored over the merged tree so the
binding again means "these exact bytes were reviewed", with the delta named above rather
than absorbed silently.

Recorded digest: dbdf515ca91c7f4c9d618b9029af44e8cb02e626123738c4df230dabf7f90300
Previous:        9c1a8082d1d6348f345e3aad1faee87fef59e98d3538b08fe9c1f130dce5d68d

SUPERSEDED 2026-07-28 — the `dbdf515c…` above is HISTORY, not the live binding. It is
kept because it records what was reviewed at that merge; the live value is the single
`Reviewed-Scope-Digest:` line at the top of this file, recomputed over the 2026-07-28
merge of `origin/master` dd01ce8f. Both this branch's note and the master-line notes
above it survive that merge verbatim: they describe different landings and neither is
the other's restamp.

---

## Re-bind 2026-07-28 (merge of origin/master dd01ce8f into iso-port-composition)

PR #223 had been CONFLICTING for days. An unmergeable PR gets no checks at all, so this
artifact's own gate — and every other gate on the branch — had been silently OFF the
whole time; the merge is what turns them back on. That is the finding worth recording:
the digest did not drift unnoticed, it went UNCHECKED, which is the worse failure of the
two and is invisible from a green-looking PR page.

The conflict here was in this file only, and it was two append-only note histories
colliding, not a contested byte. Resolution kept BOTH sides in full — verified by
`grep -c` for each side's marker strings in the merged file, so the claim is a count and
not a reading — and the digest was RECOMPUTED over the merged tree rather than either
side's value being carried, since both sides' values are digests over trees that no
longer exist.

The in-scope delta and why it is mechanical are stated with the digest at the top of
this file. Nothing was re-reviewed and no prose finding was edited, because no reviewed
byte moved: the branch's entire diff is the world layout, the renderer, the hit test and
the check harness, none of which is in the COG-4 scope.

---

## Re-bind 2026-07-29 (feat/salience-loop — the sweep's two silent claims)

One bound path changed: `cabinet/config/cognitive-architecture-contract.yml`, which
takes a +200 non-comment-line phase row for the who/when unit. NO COG-4
implementation path moved — no organ, no projection, no scheduler byte — so the
review's findings are untouched by this landing. The contract sits inside this
digest's scope precisely so that a budget row cannot ride in unnoticed behind a
frozen review; ZERO new modules ride here, so no bijection class moves.

Recorded digest: d9d2d8a9b4d228d72661fc6145c5e3243f01e0fb619baed4ea55bde34cbb80b1
Previous:        0df4d12ac60f2353118fdadf244ed8d522a9e1fdcaee5edbd2e7dc078bd211a6

Re-bound at landing by the integrator, in the SAME commit as the change, per §15.

---

## Re-bind 2026-07-29 (feat/salience-loop — merge of origin/master 2eeaa8d7)

Both branches re-bound this digest the same afternoon, which is what the conflict
was. Master's note above survives VERBATIM — it describes a different landing and
is not this one's restamp — and this is the value over the merged tree.

One bound path moves on this branch: `cabinet/config/cognitive-architecture-contract.yml`,
a +200 non-comment-line phase row for the who/when unit. NO COG-4 implementation
path moved — no organ, no projection, no scheduler byte — and ZERO new modules,
so no bijection class moves either. The unit's own work is in
`framework/onboarding/`, which this scope does not bind.

Recorded digest: a8e0903b5f5bcc2c216dc886b83aa12d5d5a78ac79804a1c65f76ecc8f367cd5
Previous:        2c6fdb6779f555a5fc7a360a5eb9f316aec08be78c4ad85d71e1646a3a32d782

---

## Re-bind 2026-07-29 (fix/briefing-and-recall)

Recorded digest: f6cff878b3bbd8f2dcfde7118cfa1b161a0bcad7d23ff8ed5cd23b16e7d2646a
Previous:        e7a6983a05d08cd4e88233935a84a8a3afded44dbb6e79021f24a54fede4bf86

TWO bound paths changed, NEITHER of them COG-4 behaviour. Named rather than
absorbed silently, so the binding again means "these exact bytes were reviewed":

* `cabinet/services.yml` — the `retrieval-eval` row's `notes:` prose and its
  env-overridable floor list. The nightly gate used to self-harvest its pairs
  from this store, deriving each query from the expected document's own leading
  110 characters; the row now names the committed question-shaped seed and the
  added `RE_ABSTAIN_FLOOR`. Schedule, command, label and `expected:` contract
  are untouched — no service starts, stops or runs differently.
* `cabinet/config/cognitive-architecture-contract.yml` — ONE budget maximum,
  `framework_production_noncomment_lines` 60185 -> 60282, for +97 measured
  non-comment lines in `framework/onboarding/genesis.py` (the first briefing's
  claim refusals). Raised visibly, zero headroom, zero new modules. No COG-4
  set pin, allowance, or organ row is touched.

Nothing in this branch's own work touches the COG-4 implementation: it is
retrieval ranking, the retrieval eval, and the genesis briefing composition.


---

## Re-bind 2026-07-29 (merge of origin/master into fix/briefing-and-recall, second)

Recorded digest: b6872d9f98e0b1138aec5c496a1787e23a3afe1aa20b1acc2f7865bf6b18fd13

Both sides had re-bound the line again and both notes are kept verbatim. The only
in-scope path that moved on either side is
`cabinet/config/cognitive-architecture-contract.yml`, whose ceiling is RE-MEASURED
over this merge tree (74620 at zero headroom) rather than added on paper: the
de-specification ceiling and this branch's +97 genesis claim refusals are disjoint
sets of lines. No COG-4 implementation byte moved on either side.

## Re-bind 2026-07-29 (feat/salience-loop — merge of origin/master c98a58a6)

Third re-bind of this digest in one afternoon, by three branches landing in
parallel; every prior note above survives verbatim, because each describes a
different landing and none is another's restamp. This value is over the merged
tree. This branch moves ONE bound path,
`cabinet/config/cognitive-architecture-contract.yml` (+200 non-comment lines for
the who/when unit), and NO COG-4 implementation byte; ZERO new modules, so no
bijection class moves.

Recorded digest: 408e6b979fff5a1d84da85fdc19ed7114a8a2df96492636407d80febee0aa017
Previous:        b6872d9f98e0b1138aec5c496a1787e23a3afe1aa20b1acc2f7865bf6b18fd13

---

## Re-bind 2026-07-29 (fix/salience-ranking, over the merge of origin/master b65ae3fb)

Recorded digest: d424e84fd9b7b8c1d17af49915dfa4951c1680c472df9a3215f6eee7ef9d4e1f
Previous:        a9be6fa17cc368ca64a84309d26fb65d1b1483633ec39722cf8b0c2796894658

Every prior note above survives verbatim; each describes a different landing and
none is another's restamp. Two committed conflict markers this file had been
carrying since an earlier resolution are removed in the same commit — no note
text moved, and this file is excluded from its own digest, so nothing here can
change the value it records.

ONE bound path moved and NO COG-4 implementation byte did:
`cabinet/config/cognitive-architecture-contract.yml`. It carries BOTH sides'
mass raises verbatim — master's +94 read-lane row and this branch's +305 for the
ranker's discount, join seam and oracle — under a merged `maximum` of 60944 that
is RE-MEASURED over this tree (observed 75221, zero headroom) rather than summed
on paper. It also supersedes two prose blocks that described the salience floors
as DELETING, which is precisely what this branch stops them doing; leaving them
would have left the contract's own words contradicting the code they adjudicate.

Neither raise is an allowance — a bijection class may never be bought with one,
and this is mass on the line the zero-headroom law is read from. ZERO new
modules, so no bijection class moves. The unit's own work is in
`framework/onboarding/`, which this scope does not bind.


---

## Re-bind 2026-07-29 (fix/salience-ranking, prose correction)

Recorded digest: ade4e533458db0efd149a6f80da69b95f364f096bd934361f6a31ed75aaee975
Previous:        d424e84fd9b7b8c1d17af49915dfa4951c1680c472df9a3215f6eee7ef9d4e1f

Comment bytes only in the one bound path,
`cabinet/config/cognitive-architecture-contract.yml`: the merge note added by
the re-bind above said "the two raises above are DISJOINT" while sitting between
them, and is moved below both. No budget value changes, the census re-runs at
observed == maximum with zero headroom, and no COG-4 implementation byte moves.
Named rather than absorbed, because a digest that moves for reasons nobody wrote
down is a binding to nothing.


---

## Re-bind 2026-07-29 (fix/salience-ranking, actor-harvest dedupe)

Recorded digest: 8e9e9177e4f168b3404ddc947d5d128445fe7d1101b07d694eab9611530e8eba
Previous:        ade4e533458db0efd149a6f80da69b95f364f096bd934361f6a31ed75aaee975

ONE bound path, `cabinet/config/cognitive-architecture-contract.yml`, taking
`framework_production_noncomment_lines` 60944 -> 60946 for a two-line fix in
`framework/onboarding/salience.py`: the actor harvest read one identity string
per ROW, so 665 rows produced 665 strings for four distinct owners. Raised
visibly on the same maximum line, census PASS at observed == maximum with zero
headroom, no allowance, zero new modules, no COG-4 implementation byte moved.


---

## Re-bind 2026-07-29 (fix/salience-ranking, fail-soft judgment)

Recorded digest: fb9ef1716b7171213bf9c38eb24db1eb06a19127b31527ec01520ba0540ba29d
Previous:        8e9e9177e4f168b3404ddc947d5d128445fe7d1101b07d694eab9611530e8eba

ONE bound path, `cabinet/config/cognitive-architecture-contract.yml`, taking
`framework_production_noncomment_lines` 60946 -> 60950 for four lines in
`framework/onboarding/salience.py`: a judgment callable that raised took the
exception out through `rank()`, so an unreachable model would have taken down
the operator's offer to improve its ordering. Raised visibly, census PASS at
observed == maximum with zero headroom, no allowance, zero new modules, no
COG-4 implementation byte moved.


---

## Re-bind 2026-07-29 (fix/salience-ranking, merge of origin/master 468e1a7b)

Recorded digest: 80d1b9fed616d8bc4332d015bcedb155f3aa409b0181022f3bde359bd80b2a7b
Previous:        b885033efb7fe6c672a8d8c43b3aafd8852e601f7c398e6bf868f9436b21ae24

Both sides re-bound this digest the same day. Master's copy of this file is
taken wholesale so nothing it carries is dropped, and this branch's four notes
are appended to it; every note above stands verbatim and none is another's
restamp.

ONE bound path moved and NO COG-4 implementation byte did:
`cabinet/config/cognitive-architecture-contract.yml` carries BOTH sides' mass
raises verbatim — master's +29 connector-loader honesty row and this branch's
ranker rows — under a merged `maximum` of 60979 that is RE-MEASURED over this
tree (observed 75256, zero headroom) rather than summed on paper. Neither is an
allowance; ZERO new modules, so no bijection class moves.


---

## Re-bind 2026-07-30 (feat/answer-merges-aliases)

Recorded digest: aadee358cd344264da512138552918b2763ab43b033738ce979860fdf0c3f090
Previous:        80d1b9fed616d8bc4332d015bcedb155f3aa409b0181022f3bde359bd80b2a7b

ONE bound path moved and NO COG-4 implementation byte did:
`cabinet/config/cognitive-architecture-contract.yml` takes
`framework_production_noncomment_lines` 60979 -> 61198 (+219 measured, observed
75475 vs the then-effective 75256) for the merge channel the escape hatch was
documented to have and did not — `same_as` on `answer_salience`, `merge_ask`,
the accumulating `salience_merges` store and the alias-group closure, all inside
`framework/onboarding/{salience,journey}.py`. Raised visibly, never an
allowance; census PASS at observed == maximum with zero headroom; ZERO new
production modules, so no bijection class moves.


---

## Re-bind 2026-07-30 (feat/answer-merges-aliases, checkpoint 2)

Recorded digest: 59c9bafb460cc268d5713ec601a7840de89a1bbfdac38855a490a0f9b654143c
Previous:        aadee358cd344264da512138552918b2763ab43b033738ce979860fdf0c3f090

ONE bound path moved and NO COG-4 implementation byte did:
`cabinet/config/cognitive-architecture-contract.yml` takes
`framework_production_noncomment_lines` 61198 -> 61211 (+13 measured, observed
75488) for a defect found by attacking the checkpoint-1 landing — a merge
absorbs one of the names it joins, so validating an answer against the current
ranking alone refused the operator's own already-taught name. Raised visibly,
never an allowance; census PASS at observed == maximum with zero headroom; ZERO
new production modules.


---

## Re-bind 2026-07-30 (feat/answer-merges-aliases, checkpoint 3)

Recorded digest: 720e924b5a4ff3aa8da793ce37bdf4d43ee05195b20d1edbe40d6f61ce8d8e9f
Previous:        59c9bafb460cc268d5713ec601a7840de89a1bbfdac38855a490a0f9b654143c

ONE bound path moved and NO COG-4 implementation byte did:
`cabinet/config/cognitive-architecture-contract.yml` takes
`framework_production_noncomment_lines` 61211 -> 61212 (+1 measured, observed
75489) for scrubbing and bounding the caller text the merge refusal quotes back
— a 4000-character name produced a 4061-character refusal on the previous
commit. Raised visibly, never an allowance; census PASS at observed == maximum
with zero headroom; ZERO new production modules.


---

## Re-bind 2026-07-30 (merge of origin/master 589565ea into feat/answer-merges-aliases)

Recorded digest: 7c7b036c211fb79c09a23948dc9b420f4eea397de585de1c4150fe1974372299
Previous:        720e924b5a4ff3aa8da793ce37bdf4d43ee05195b20d1edbe40d6f61ce8d8e9f
                 (this branch) / 8b6b1c9d157204e238ca3b7df2c678de1803492f02f9885c6c053167ca36f388 (master)

Both sides re-bound this digest the same day and neither is the other's
restamp: master's `fix/answer-binds-depth` made the depth claim ENFORCED, this
branch made the answer able to JOIN two names for one thing. Master's copy of
this file is taken wholesale so nothing it carries is dropped, and this
branch's notes stand verbatim beside it.

ONE bound path moved and NO COG-4 implementation byte did:
`cabinet/config/cognitive-architecture-contract.yml` carries BOTH sides' mass
raises verbatim under a merged `framework_production_noncomment_lines` of
61327, RE-MEASURED over this merge tree with cognitive-architecture-census.py
(observed 75604, zero headroom) rather than summed on paper — the paper sum
agrees, and the agreement is evidence for the measurement, not a substitute for
taking it. Neither is an allowance; ZERO new modules, so no bijection class
moves.
---

## Re-bind 2026-07-30 (feat/operator-identity — the ask that makes attribution reachable)

One bound path changed: `cabinet/config/cognitive-architecture-contract.yml`,
which takes a +246 non-comment-line phase row for the unit that gives
`operator_identity` the writer it never had. NO COG-4 implementation path moved
— no organ, no projection, no scheduler byte — so the review's findings are
untouched by this landing. The contract sits inside this digest's scope
precisely so that a budget row cannot ride in unnoticed behind a frozen review;
ZERO new modules ride here, so no bijection class moves, and the ceiling is
RE-MEASURED over this tree (observed 75502, zero headroom) rather than added on
paper.

Recorded digest: 8666074818270283cb3f7773b7f3b5334b8b83bce7bd0e44041661994d06c1bb
Previous:        df74c54be382546821d5cec711bf7f8d136af9196d62be04f30b0f50110f59f9
Before that:     80d1b9fed616d8bc4332d015bcedb155f3aa409b0181022f3bde359bd80b2a7b

Two commits, one bound path both times: the phase row was measured +246 at the
first and re-measured +262 at the second, when attacking the landing found the
candidate note counting the CAPPED offer list and an empty connector key being
accepted as a system. Still no COG-4 implementation byte, still zero new
modules, still zero headroom (observed 75518).

Re-bound at landing by the integrator, in the SAME commit as the change, per §15.

---

## Merge re-bind 2026-07-30 (feat/operator-identity x master 589565ea)

Both sides re-bound this digest the same day; one value stands and it is
recomputed over this merge commit. Every note above is verbatim from its own
side and none is another's restamp.

ONE bound path moved on either side and NO COG-4 implementation byte did:
`cabinet/config/cognitive-architecture-contract.yml` carries master's VISIBLE
`framework_production_noncomment_lines` maximum raise (60979 -> 61094, the
answer-binds-depth control) AND this branch's +262 operator-identity phase row,
RE-MEASURED over the merged tree with cognitive-architecture-census.py —
observed 75633, zero headroom — rather than summed on paper. ZERO new modules on
either side, so no bijection class moves. The two branches' framework work does
not overlap: master's is the window binding, this branch's is the identity ask,
and the one textual collision was two functions added at the same line, both
kept.

Recorded digest: e19c72599f83d6ccb03be390974d611157b23e4ea432a711cbb397f742a42b5a
Previous (this branch):  8666074818270283cb3f7773b7f3b5334b8b83bce7bd0e44041661994d06c1bb
Previous (master):       8b6b1c9d157204e238ca3b7df2c678de1803492f02f9885c6c053167ca36f388


---

## Re-bind 2026-07-30 (merge of origin/master ee8e5366 into feat/answer-merges-aliases)

Recorded digest: c83b9b88e3a75869150222c436539d5e9737e3ee8b292612b1d8dc9f6be8ab3c
Previous (this branch): 7c7b036c211fb79c09a23948dc9b420f4eea397de585de1c4150fe1974372299
Previous (master):      e19c72599f83d6ccb03be390974d611157b23e4ea432a711cbb397f742a42b5a

Master's `feat/operator-identity` landed while this branch was in CI. The two do
NOT overlap: master's is the identity ask that gives `operator_identity` a
writer, this branch's is the merge channel that lets an operator say two names
are one thing. Both sides' notes stand verbatim above and below; neither is the
other's restamp, and the header's earlier parentheticals are kept for the same
reason.

ONE bound path is in scope and NO COG-4 implementation byte moved on either
side: `cabinet/config/cognitive-architecture-contract.yml` carries master's
+246 phase row and this branch's `framework_production_noncomment_lines`
maximum of 61327 together, RE-MEASURED over the merged tree with
cognitive-architecture-census.py (PASS, observed 75866 at zero headroom).
Merged onboarding suite: 655 passed, 1 skipped.

---

## Re-bind 2026-07-30 (`fix/identity-picker-tail`)

Recorded digest: 56f58f88b0ca89aedfa610a8cf95033138250685ee3987acad6dbbb41e26b0a0
Previous:        c83b9b88e3a75869150222c436539d5e9737e3ee8b292612b1d8dc9f6be8ab3c

ONE bound path moved and NO COG-4 implementation byte did:
`cabinet/config/cognitive-architecture-contract.yml` raises
`framework_production_noncomment_lines` VISIBLY 61327 -> 61372 (+45 measured over
this tree with cognitive-architecture-census.py: PASS, observed 75911 == maximum,
zero headroom) and the operator-identity phase row records what it bought.

The unit itself lands outside this digest's scope, in
`framework/onboarding/research.py`, `framework/onboarding/journey.py`,
`instance/config/connectors.yml.example` and the dashboard card. The identity
picker offered the 12 BUSIEST accounts a connector reported, and frequency
decided membership — so on the estate this lane was built against (531 of 665
rows on one connector, 30 accounts, the operator's own carrying exactly ONE and
ranking about 25th) the only writer of an identity could not be handed the
identifier, and 80% of the estate was unresolvable by any sequence of operator
actions. Frequency now orders the offer and no longer decides membership; where a
guardrail still binds, `complete: false` obliges the surface to accept a typed
answer rather than present a head as the whole estate. Three smaller defects ride
the same commit: a silently truncated identifier (refused by name now, at a bound
tied to the sweep's own), a scalar handles value iterated per character, and the
public connectors example teaching `actor_field` under a key nothing reads.

Batteries over this commit: framework/ 7763 passed (1 known local-only red,
reproduced identically on a clean master clone), onboarding 664 passed / 1
skipped, cabinet/scripts 5121 passed / 34 skipped, dashboard `tsc --noEmit` clean
and 2891 vitest passed, layer separation new=0, docs sweep and ledger parity
green.


---

## Re-bind 2026-07-30 (fix/short-answer-binds)

Recorded digest: ea42d51ba95ed81bcd1fa3018b1503d659ce5dfa1a428a67a6b8985df4ce2238
Previous:        c83b9b88e3a75869150222c436539d5e9737e3ee8b292612b1d8dc9f6be8ab3c

ONE bound path moved and NO COG-4 implementation byte did:
`cabinet/config/cognitive-architecture-contract.yml` takes
`framework_production_noncomment_lines` 61327 -> 61388 (+61 measured, observed
75927 vs the then-effective 75866) for a regression the window bind shipped
with — it derived BOTH sides of its name test with the RANKING tokenizer, whose
length floor drops every part and every compound below four characters, so an
operator whose answer was a short product, an acronym or an initialism had zero
wanted words, and a control built to refuse ONE window refused EVERY window
while telling them the folder "does not carry that name" — false of the folder
spelled exactly like their answer. `salience.name_tokens` splits the floor out
of the primitive (`tokenize` output pinned byte-identical), the bind compares
names with it and returns the word sets it compared, and every sentence
rendered from the bind now states the test that ran. Raised visibly, never an
allowance; census PASS at observed == maximum with zero headroom; ZERO new
production modules, so no bijection class moves.

(MERGE RE-BIND, 2026-07-30, `fix/short-answer-binds` x master: the two sections
above each recorded their own value on their own branch; over the merge commit
ONE digest stands, `35b4ae16…`, and it is the value on the header line. The
only in-scope path either side moved is the contract file, whose merged ceiling
is re-measured over this tree — census PASS, observed 75972 == maximum 61433,
zero headroom. No COG-4 implementation byte moved on either side.)
