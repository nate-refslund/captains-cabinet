# Germline amendment proposal — DE-NATE FOUNDATION — 2026-07-05

**Status:** AWAITING CAPTAIN. Every germline file named below is
Captain-applied only. Reply **"apply de-nate"** and the session executes the
apply ritual (§5) exactly: unlock → merge `feat/de-nate` → re-lock → verify.
Nothing in this package changes live behavior at all — it is a
launcher-agnosticism sweep whose entire correctness proof is that, on THIS
instance, it renders byte-identical to today.

**Branch of record:** `feat/de-nate` (worktree `.claude/worktrees/de-nate`,
base `67fc5ae6`). The branch is the diff; this document is its
Captain-readable contract for the **germline** subset (11 files). The branch
also carries ~45 NON-germline framework parameterizations (other DE-NATE
lanes) that merge with no unlock and are recorded in
`docs/plans/de-nate-foundation-2026-07-05.md`, not here.

**Encodes (already-ruled, logged live in
`shared/interfaces/captain-decisions.md` on 2026-07-05 — reference only, do
NOT re-paste):**

- **FOUNDATION-FIRST + EVOLUTION ENGINE GO (2026-07-05 ~00:45,
  Captain-ruled, in-session)** — the target artifact is the FRAMEWORK:
  universal, launcher-agnostic, for any captain, either flavor; Nate's
  deployment is the first instance and proving ground, not the product.
  Framework-vs-instance layering is goal-critical, not hygiene: anything
  captain-specific (name, vault paths, board ids) belongs in `instance/` or
  adapters, never `framework/`. Launcher genericization is IN-SCOPE core
  work. This amendment realizes clause (a) for the 11 germline files.

## §0 · What this changes, in one paragraph

`framework/` code that addressed the launcher by a hardcoded name now
addresses it through the shipped resolver
`framework.env.captain_name()` (base `67fc5ae6`; reads `captain_name` from
`instance/config/platform.yml`, else `product.yml`, fallback `"Captain"`).
Across these 11 germline files that means: **two** runtime NAME-STRING sites
interpolate the resolver (the `PROPOSER_SYSTEM` action-proposer prompt via a
replay-stable `%%CAPTAIN%%` slot; the `captain-vetoes.yml` fallback file
header via `_default_header()`), and **nine** files carry
comment/docstring-only generalizations (`Nate` → "the Captain"). No verdict
table, threshold, authority path, event vocabulary, or control flow is
touched. Because `captain_name()` resolves to `"Nate"` on this deployment,
every runtime byte is identical to `67fc5ae6` — which is the correctness
proof: the existing tests that pin prompt/header/message text stay green
unchanged, and the clean-room ratchet
(`framework/tests/test_no_launcher_hardcode.py`) proves no launcher name or
`/Users/nate` path remains in `framework/`.

## §1 · Per-file inventory (the branch is the diff)

Export the exact germline diff set for review:

```bash
git -C /Users/nate/captains-cabinet/.claude/worktrees/de-nate \
  diff 67fc5ae6 -- \
  framework/acting/action_lane.py framework/acting/run_action_lane.py \
  framework/authority/veto.py framework/authority/grants.py \
  framework/frontdoor/veto_registry.py framework/frontdoor/binder_wire.py \
  framework/frontdoor/action_exec.py framework/frontdoor/actfirst_canary.py \
  framework/learning/gate.py framework/events/emitter.py \
  framework/fidelity/consequence.py
```

| file | change (comment/string parameterization only, no logic change) | germline |
|---|---|---|
| `framework/acting/action_lane.py` | RUNTIME prompt string: `PROPOSER_SYSTEM` addresses the captain via a replay-stable `%%CAPTAIN%%` slot filled with `captain_name()` at compose (`+from framework.env import captain_name`); + docstring/comment generalization. Byte-identical prompt on this instance; no logic change | yes |
| `framework/acting/run_action_lane.py` | Comment/docstring generalization only (incl. a historical ledger-spelling example inside a comment); no import, no code change | yes |
| `framework/authority/veto.py` | Module docstring + `compose_veto_notice` docstring generalization only; veto-window/enqueue/TTL logic untouched | yes |
| `framework/authority/grants.py` | Module docstring generalization only; the `never_grant`/external-comms loader logic is UNCHANGED (that lives in the axes amendment, not here) | yes |
| `framework/frontdoor/veto_registry.py` | RUNTIME file-header string: module const `_DEFAULT_HEADER` → `_default_header()` interpolating `captain_name()` (`+from framework.env import captain_name`), both call sites updated; + module docstring generalization. Byte-identical header on this instance; monotonic/lift-only registry logic untouched | yes |
| `framework/frontdoor/binder_wire.py` | Comment generalization only (the DARK-by-default `captain_verified` gate comment); grammar/write-gate logic untouched | yes |
| `framework/frontdoor/action_exec.py` | Comment generalization only; the `DEFAULT_TASKS_BOARD = "5091706356"` Monday-id literal is UNCHANGED (flagged instance-specific in the foundation plan, env-overridable via `ACTION_LANE_DEFAULT_BOARD`) | yes |
| `framework/frontdoor/actfirst_canary.py` | Comment generalization only (the status/color column-type note); cap/freeze/canary logic untouched | yes |
| `framework/learning/gate.py` | Module docstring generalization only; the DARK gate-apply lane and `ratify()` semantics untouched | yes |
| `framework/events/emitter.py` | Comment generalization only; `VALID_EVENT_TYPES` set is byte-identical (no event added/removed) | yes |
| `framework/fidelity/consequence.py` | `SimQuarantineError` docstring generalization only; the SIE-7 sim/live quarantine fence logic untouched | yes |

Two files add exactly one import line (`from framework.env import
captain_name`); the other nine add none. No file changes a signature, a
return type, a branch, a constant that reaches a verdict, or a test's
expected value.

## §2 · What this amendment does NOT do

- **No verdict / authority / threshold change.** No posture table, no
  confidence state, no cap, no graduation floor, no `action_type`
  classification, no `never_grant` behavior — untouched. `grants.py`'s only
  edit is a docstring.
- **Guardian, sovereign, AND earn_up stay byte-identical.** Nothing here
  enters resolution; posture is not read; the three autonomy levels resolve
  exactly as at `67fc5ae6` (this sweep is orthogonal to the axes amendment).
- **Golden evals unchanged.** No `memory/golden-evals/*` file is touched;
  every eval spine passes against identical rendered strings (the runtime
  interpolation yields `"Nate"` here).
- **No new event types, no new config keys, no new control flow.**
  `emitter.py`'s vocabulary set is byte-identical; the two interpolation
  sites add no branch.
- **No brain-artifact rename.** `nate_model`, `me_signal`, `voice`-profile,
  and the `NATE MODEL` CLONE_PAYLOAD label are real Flavor-A screenpipe
  artifact identifiers — KEPT verbatim (they are lowercase/hyphenated
  external names, not the captain's display name; the case-sensitive ratchet
  never matches them). DN-6 allowlists them as the audit trail.
- **No instance-specific data forced into `captain_name()`.** A colleague's
  name, a Monday board id, a git-repo path, or the Flavor-A vault layout is
  NOT the captain's display name; those are left as-is and FLAGGED (foundation
  plan §instance-specific) as candidates to move to `instance/` — never
  mis-parameterized.

## §3 · The correctness proof (why byte-identical == changed no behavior)

`captain_name()` == `"Nate"` on this deployment (it reads
`instance/config/platform.yml`). Therefore every runtime site this amendment
parameterizes renders the SAME bytes it did at `67fc5ae6`. The proof that no
behavior changed is that **the tests which pin prompt / header / message text
stay green with no edit** — a red pinned-text test would mean a byte moved,
i.e. the parameterization was done wrong. Where a test itself hardcoded the
name, it was fixed to read `captain_name()` the same way (never by weakening
the assertion). The forward-looking guarantee is the ratchet in §4.

## §4 · CI proofs

| Proof | Where it lives | Asserts |
|---|---|---|
| R1 | `framework/tests/test_no_launcher_hardcode.py` | THE RATCHET: no bare `\bNate\b` / `/Users/nate` in `framework/**/*.py` outside a documented shrink-only allowlist; engine self-tests (flags bare name + home path, ignores lowercase brain-artifacts, skips tests/, whole-file + line allowlist, symlink-escape refused); `_TEMPORARY_RESIDUALS` empty, `_TEMP_BASELINE_MAX == 0` |
| R2 | the pinned-text tests already in `framework/**/tests/*` | byte-identical render on this instance (the action-lane proposer suite, the veto-registry header/roundtrip suite, etc.) — green with NO edit is the §3 proof |

## §5 · APPLY-GATE evidence pack (all green before you reply) + apply ritual

**a. Suites green — run the three roots SEPARATELY.** A combined
`framework/ cabinet/scripts/lib/tests` invocation errors at collection
(`cabinet/scripts/lib/tests` and `cabinet/scripts/gates/tests` both claim the
top-level `tests` package — **NEVER use the combined form**). Baseline for
reference: framework 3334 passed / 17 skipped · lib 470 · gates 6.

```bash
python3.12 -m pytest framework/ -q -p no:cacheprovider
python3.12 -m pytest cabinet/scripts/lib/tests -q -p no:cacheprovider
python3.12 -m pytest cabinet/scripts/gates/tests -q -p no:cacheprovider
```

**b. Ratchet strict-fire probe** — `python3.12
framework/tests/test_no_launcher_hardcode.py` prints every offender and exits
non-zero on any leak; on this branch it prints
`OK: framework/ is launcher-agnostic` and exits 0.

**c. Apply ritual (one sitting):**

```bash
sudo bash cabinet/scripts/germline-lock.sh unlock
git merge feat/de-nate            # or FF; the 11 germline files above are why
                                  # the unlock is needed. The ~45 non-germline
                                  # framework parameterizations merge in the
                                  # same commit with no special handling.
sudo bash cabinet/scripts/germline-lock.sh lock
bash cabinet/scripts/germline-lock.sh status && bash cabinet/scripts/germline-lock.sh verify
# re-run §5a suites post-merge; all three roots green, no count regression.
```

**One-revert rollback:** revert the merge commit. Because every change is a
comment/docstring generalization or a byte-identical `captain_name()`
interpolation, reverting restores all 11 germline files (and the non-germline
set) to `67fc5ae6` verbatim; there is no state file to delete, no config to
unwind, and nothing was ever behaviorally live to quiesce.

## §6 · captain-decisions.md — ledger state + the ONE paste-ready apply record

**Already logged live (2026-07-05, reference only — do NOT re-paste):**
`## FOUNDATION-FIRST + EVOLUTION ENGINE GO (2026-07-05 ~00:45, Captain-ruled,
in-session)` landed in `shared/interfaces/captain-decisions.md` on 2026-07-05.
On apply, add one line under it: *"Realized (clause a, 11 germline files) by:
germline amendment de-nate 2026-07-05 (`apply de-nate`)."*

**Apply record — paste-ready** (paste when you apply):

```markdown
## DE-NATE FOUNDATION APPLIED (2026-07-05, Captain apply token: `apply de-nate`)

**What:** Applied the de-nate germline amendment
(docs/proposals/germline-amendment-de-nate-2026-07-05.md): 11 germline
framework files made launcher-agnostic — two runtime NAME-STRING sites
(action_lane PROPOSER_SYSTEM, veto_registry header) interpolate
framework.env.captain_name(), nine files carry comment/docstring-only
generalizations. No verdict/authority/threshold/event change; guardian,
sovereign, and earn_up byte-identical; golden evals unchanged. Correctness
proof: captain_name()=="Nate" here ⇒ byte-identical render ⇒ pinned-text
tests green unchanged; the clean-room ratchet
(framework/tests/test_no_launcher_hardcode.py) enforces it forward in CI.

**Why:** Realizes clause (a) of FOUNDATION-FIRST (2026-07-05) — the framework
is the universal, launcher-agnostic artifact; the captain's name belongs in
instance/config, never in framework/ code. Reference only, full text in that
entry.

**Captain:** Nate.
```

Reply **"apply de-nate"** to apply exactly the above.
