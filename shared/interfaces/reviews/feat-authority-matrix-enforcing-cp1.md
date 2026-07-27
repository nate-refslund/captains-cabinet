# Checkpoint review — feat/authority-matrix-enforcing — cp1 (2026-07-27)

**Two passes: a fresh-context adversarial reviewer (Opus 5, own clone, zero
session priors) and the builder's own attack on the surface it had just built.**

Reviewer verdict: **approve-with-fixes** — 3 blockers, 5 should-fix, 5 nits.
Every blocker is addressed below or converted into a Captain proposal with the
reason it cannot be a session change. The DO-NOT-FLIP call reproduced
independently.

## Blockers

**B1 — the Captain's only "not that" control is erasable by an ordinary officer
tool call, and the surface's own docs said otherwise.**
`instance/config/authority-exceptions.yml` is on neither `pre-tool-use.sh`
protected list. Measured through the real hook: `Write` → exit 0;
`echo 'denylist: []' >` → exit 0; `rm -f` → exit 0; contrast `Write` to
`act-first-surfaces.yml` → exit 2. Four erasures are SILENT.

*Disposition: claims corrected, fix proposed, NOT applied.* The reviewer called
the fix "free and precedented". The precedent is right —
`shared/interfaces/captain-vetoes.yml` is hook-protected and deliberately not
schg-locked (`germline-lock.sh` `SKIP=`) — and the cost estimate is not. The
hook lists are reverse-enforced against `framework/policies/immutable-core.yml`
by `test_germline_lockstep_consistency.py`, so the path must be enumerated
there first, and that file's own header reserves such edits to the Captain:
*"Officers/loops propose changes to the Captain; only the Captain applies them
in a germline-lock unlock window."* Adding a path changes the Ring-0 **set**,
not germline content — doctrine separates the two. Proposed with the exact
edits and acceptance arms in
`docs/proposals/authority-exceptions-hook-protection-2026-07-27.md`; it rides
the relock this deployment already needs, so it costs no extra window. Every
overstated claim ("holds against an officer's ordinary tool calls", "erasure is
loud rather than silent") is now corrected in the report §5.2 and in the
shipped `.example` header, with the probe table.

**B2 — a row could load clean and never fire.** The loader validated predicate
truthiness, never type. `command_contains: ["echo hello"]`, `tool: [Bash]`,
`command_contains: true`, `action_type: nonexistent_type` all loaded with no
error and matched nothing — the Captain gets no error and believes the deny is
live. *FIXED:* non-string / empty-string predicates, a non-string `id`, and an
`action_type` outside `classifier.ACTION_TYPES` are refused at load, naming the
row and the problem. Ordering corrected too (value errors are reported as value
errors, not as "has no predicate"). 9 new arms.

**B3 — the egg manifest deleted a file two shipped tests assert exists**, with
no materialize transform (unlike the `act-first-default` sibling) → a hatched
egg's suite would be red. *FIXED by not shipping the live file at all.* ABSENT
is documented as identical in behaviour to an empty denylist, so only the
`.example` ships. This also removes SF5: with the file present, the loader
reaches `import yaml` on every call, so a deployment missing PyYAML would go
from "degrades to the regex fallback" to "every tool call blocked, including
Read". The manifest line and the residuals-register line-cite re-anchor it
forced were both reverted — net zero touch on those two files.

## Should-fix

**SF1 — the instrument's READ-ONLY claim was false outside guardian posture.**
The candidate arm calls the gate path, which on a ceiling row under sovereign
calls `standing_grant_resolution(act=True)` — filing needs and consuming grant
budget, the very side effect the report's §4.7 warns about. Guardian saved the
run, but §7 mandates re-running this instrument as a flip precondition, by which
time the posture may differ. *FIXED:* `_install_side_effect_guards()` forces
`act=False` and no-ops `_emit_gate_tell`; the run aborts if posture is not
guardian and the guards could not be installed. Both guards and the resolved
posture are printed and recorded in the JSON.

**SF4 — timeouts were arithmetically treated as "allow"** while the
`EngineTimeout` docstring claimed they never are. *FIXED:* a timed-out record
has no verdict and is excluded from the denominator, reported on its own line.
Headline moved 75.60% → 75.66% on the re-run.

**SF2 / SF3 — predicate reach and substring evasion.** `path_contains` reads
only `file_path`/`path`, so the `.example`'s own `/billing/` row blocks
`Edit` but not `Bash: echo p >> /srv/app/billing/x.py`; `command_contains` is
substring-over-raw-text and loses to `echo  hello` / `echo "hello"` /
`H=hello; echo $H`. *Accepted and documented, not fixed.* This is the same
content-vs-action confusion the report names as a live bug in §4.6/§6.2 — fixing
it properly means classifying the invocation, which is the backlog item, not a
patch here. Recorded in the report and BACKLOG.

## Confirmed by the reviewer

- **Deny-only by construction**: no yml shape turns a typed block into an allow.
- **Empty path is a strict no-op**: `decision()` JSON byte-identical to HEAD's
  across 9 representative calls.
- **Ordering**: exceptions consulted before typed policies; no typed policy
  short-circuits them.
- Fail-closed arms hold: chmod 000, top-level list/scalar, `denylist:` mapping,
  `[null]`, missing `id`, `!!python/object/apply` (safe_load), symlink,
  directory.
- **Both-directions sensor**: harness against HEAD's `policy-shadow.py` →
  PASS=10 FAIL=7; unit tests → 16 failed, 3 passed. Matches the report exactly.
- Report §4.5 all 8 commands reproduce `ambiguous`; §4.6 5 of 6 reproduce;
  §4.8 `_act_with_undo_gap` is None for all 7.
- "Monotone-narrowing" is true — `_first_block` short-circuits on first match.
- Harness temp-root never touches a live control surface.

## Builder's own attack (independent of the review)

Found and fixed before the review returned: the loader used `path.is_file()`, so
`ln -sf /dev/null <path>` read as ABSENT — an empty denylist, no error, every
exclusion gone. Presence-in-any-form with the wrong shape now fails closed and
names the shape.

## Not closed

- B1's hook protection — Captain proposal, above.
- SF2/SF3 predicate reach — backlog, same root cause as the §6.2 live bug.
- Reviewer could not verify the corpus numbers (corpus JSONL is not in the
  clone), §4.9's hook-regression 115/183 figure, or §6.1's ReDoS repro. All
  three are reproducible from the instrument + the live event store; the corpus
  extraction is scripted in the report §2.
- One reviewer nit stands as a known gap: NFC/NFD — `path_contains: "café"`
  written NFC does not match an NFD path, and macOS returns NFD.

## Batteries re-run by the reviewer itself

- `pytest test_captain_exceptions.py test_policy_shadow.py -q` → 41 passed
  (now 50 after the B2 arms).
- `bash cabinet/tests/hook-regression/captain-exceptions.sh` → PASS=19 FAIL=0.
- Same two against HEAD's `policy-shadow.py` in an isolated tree → FAIL=7 and
  16 failed. The sensors are real.
- 23 adversarial probes through the real hook (`attack3.sh`).
