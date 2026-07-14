# DE-NATE FOUNDATION — the launcher-agnostic sweep (E4 record) — 2026-07-05

**Ruling realized:** FOUNDATION-FIRST + EVOLUTION ENGINE GO (captain-decisions.md,
2026-07-05 ~00:45), clause (a) + clause (4): *"we should aim for the best
possible foundation that another captain will benefit of… launcher
genericization is IN-SCOPE core work."* `framework/` is the universal base
for any captain and either flavor; this deployment (captain **Nate**) is the
first instance and proving ground, not the product. This record is the E4
foundation deliverable: what the de-Nate sweep did, what it deliberately did
NOT touch, and the ratchet that keeps `framework/` launcher-agnostic forever.

**Branch:** `feat/de-nate` (worktree `.claude/worktrees/de-nate`, base
`67fc5ae6`). **Germline subset (11 files):** governed by
`docs/proposals/germline-amendment-de-nate-2026-07-05.md` (`apply de-nate`).
**Non-germline subset:** merges with no unlock, recorded here.

## 1 · The resolver (shipped at base `67fc5ae6`)

`framework.env.captain_name(default="Captain")` — the FOUNDATION resolver.
Reads `captain_name` from `instance/config/platform.yml` (portfolio / live),
else `instance/config/product.yml` (single-product `work`), else falls back to
`"Captain"`. Cached once per process. Framework code that greets or represents
the captain in a runtime string calls this instead of a literal. Repo root is
`CABINET_ROOT` / a file-relative `Path(__file__).resolve().parents[N]` — never
a hardcoded home path (the resolver's own `_cabinet_root()` docstring cites the
old `/Users/nate/...` leak as the exact anti-pattern it avoids).

**The safety invariant (correctness proof for the whole sweep):**
`captain_name()` == `"Nate"` on this deployment, so every parameterized runtime
site renders BYTE-IDENTICAL to `67fc5ae6`. The proof that no behavior changed
is that the tests pinning prompt / header / message text stay green with no
edit. Where a test itself hardcoded the name, it was fixed to read
`captain_name()` the same way — never by weakening the assertion.

## 2 · What was swept — counts by category (aggregate across all DE-NATE lanes)

Measured in-worktree against `67fc5ae6` (`git diff … framework/**/*.py`,
classified by a diff parser — see §6 for the proxy definitions; these are the
sweep as landed, line-level, not a hand-audited per-occurrence census).

| Category | Count | What it is |
|---|---:|---|
| **(1) RUNTIME NAME STRING** → `captain_name()` interpolation | **24 call-sites across 14 framework modules** (+2 test files fixed to read `captain_name()`) | LLM prompt text, digest/briefing/message output, thread speaker labels — e.g. `action_lane.PROPOSER_SYSTEM` (`%%CAPTAIN%%` slot), `veto_registry._default_header()`, `officer_prompt` CLONE_PAYLOAD (`{cap}`), morning/recap/reconcile digests, watchdog registry |
| **(2) HARDCODED PATH** `/Users/nate/…` → `CABINET_ROOT`/`parents[N]` | **8 lines** | resolved to the repo-relative root; no literal home path remains |
| **(3) COMMENT / DOCSTRING** `Nate` → "the Captain" | **≈137 generalization lines** | context/example mentions generalized so the token is gone and the ratchet can be strict; sentence meaning preserved |
| **(4) BRAIN-ARTIFACT EXTERNAL NAME** — KEPT verbatim | **4 identifiers** (see §3) | real Flavor-A screenpipe artifact names, NOT the captain's display name |
| **(5) INSTANCE-SPECIFIC DATA** — left + FLAGGED | **5 flags** (see §4) | a colleague name / board id / repo path / vault layout — parameterizing the CAPTAIN name here would be wrong |

Scope: **56** `framework/**/*.py` files changed vs baseline (incl. a few test
files updated to read `captain_name()`); **257** removed lines carried a bare
`Nate` (gross, includes runtime strings that became interpolations). Ratchet
result: `framework/` is launcher-agnostic (`test_no_launcher_hardcode.py`
12 passed; CLI prints `OK`). The germline 11-file subset is two category-(1)
sites + nine category-(3) files — see the amendment.

## 3 · Brain-artifact allowlist (KEPT verbatim — DN-6 records them)

These are real Flavor-A screenpipe brain-artifact identifiers, not the
captain's display name. They are lowercase / hyphenated / uppercase-label
external names, so the case-sensitive `\bNate\b` ratchet never matches them —
they need no active allowlist entry and were deliberately NOT renamed (no
invented `captain_model`):

1. **`nate_model`** — `me_signal.nate_model('patterns')` call +
   `BrainAdapter.nate_model_patterns()` method + the `"nate_model patterns"`
   prompt label (e.g. `officer_prompt` `## How {cap} decides (nate_model
   patterns)`).
2. **`me_signal`** — the module import / reference.
3. **`voice` profile / `voice.md`** — the "voice profile" artifact (co-located
   with `nate_model` on `kristoffer_uat.py`; kept together).
4. **`NATE MODEL`** — the CLONE_PAYLOAD section label at
   `framework/fidelity/officer_prompt.py:52` (assembly-order comment).

DN-6 is the allowlist owner: `test_no_launcher_hardcode.py::_BRAIN_ARTIFACTS_KEPT`
carries the audit trail; a future substring-ratchet (if ever adopted) would add
an explicit exemption + an optional coordinated `copy_to_nate → copy_to_captain`
rename. Today none is needed.

## 4 · Instance-specific FLAGS (candidates to move to `instance/`)

These are signals the code is Flavor-A-instance-specific. The CAPTAIN name was
parameterized; the OTHER specific data was left as-is (it is NOT the captain's
display name — forcing it into `captain_name()` would be wrong) and is flagged:

1. **`framework/autoreply/kristoffer_uat.py`** — the scoped single-colleague
   auto-reply cell (colleague-scoped; `copy_to_nate`/`nate_copy` params,
   `nate_model`, `KRISTOFFER_*` slugs). Flavor-A-instance-specific by
   construction → **whole-file allowlisted** in the ratchet with a
   `TODO(DN): MOVE to instance/ (or a fixture)`. A colleague-scoped auto-reply
   is deployment config, not framework base.
2. **`Head-of-Tech` captain-role text** in a RUNTIME prompt
   (`decision_cell._DECISION_CLONE_SYSTEM` — *"You are {cap}'s clone, facing a
   real Head-of-Tech decision…"*) + docstrings (`decision_cell` module,
   `types.DecisionCase`). Left byte-identical — **no `captain_role()` resolver
   exists**; candidate for a future role resolver (cannot force into
   `captain_name()`).
3. **`decision_cell._DEFAULT_GIT_REPOS`** = `[~/v0-politiske-annoncer,
   ~/dev-tasks]` — the captain's specific product repos. Left as-is (uses
   `Path.home()`, overridable via `build_decision_corpus(repos=…)`); candidate
   to move to `instance/` config.
4. **Flavor-A vault structure** (left as-is — not a hardcoded home path; uses
   `Path.home()`/env): `decision_cell._DECISIONS_REL='5-Reflections/Decisions'`;
   `_vault_dir` + `officer_runner.read_note` default
   `OBSIDIAN_VAULT_PATH → ~/obsidian/screenpipe-brain`.
5. **`action_exec.DEFAULT_TASKS_BOARD`** = `"5091706356"` — the Monday Tasks
   board in the captain's AI Workspace. Left as-is (env-overridable via
   `ACTION_LANE_DEFAULT_BOARD`); candidate to move to `instance/` config.

## 5 · The clean-room ratchet design (`framework/tests/test_no_launcher_hardcode.py`)

DN-6. The forward guarantee that `framework/` stays launcher-agnostic after the
sweep. Design mirrors the sister axis-branch ratchet
(`framework/tests/test_axes_contract.py`):

- **What it enforces.** Text-walks every `framework/**/*.py` (skips `tests/`
  dirs, `__pycache__`, and `test_*`/`*_test.py`) and goes RED on any bare
  `\bNate\b` (case-sensitive, word-bounded) or any `/Users/nate` literal not
  covered by the documented allowlist. A DISPLAY-NAME + PATH ratchet,
  deliberately narrow: the case-sensitive name regex flags the captain's
  display name but never trips the lowercase brain-artifact compounds (§3).
- **Allowlist discipline — shrink-only.** Two tiers: `_ALLOWLISTED_FILES`
  (whole-file — reserved for instance-specific fixtures flagged to move, today
  just `kristoffer_uat.py`) and `_ALLOWLISTED_LINES` (needle-scoped — the two
  legit docstrings that NAME the anti-pattern to warn against it: `env.py`'s
  `_cabinet_root()` and `measure_intent.py`'s namespace-package note). A
  `_TEMPORARY_RESIDUALS` frozenset + `_TEMP_BASELINE_MAX = 0` is the sanctioned
  home for any FUTURE stopgap — **empty today**: the parallel lanes cleared all
  29 initial bare-`Nate` occurrences across the 11 germline files in-worktree,
  so a NEW hardcoded `Nate` is a CI failure, not an allowlist addition.
- **Forcing functions.** Self-tests assert every allowlist path exists, every
  line-needle is still present (no dead cover), temporary entries are
  registered, the temporary allowlist only ever shrinks, and a temporary entry
  whose file is now clean MUST be deleted.
- **Trustworthy engine.** stdlib-only, `import pytest`-guarded so it also runs
  under the system python (CLI mode: `python3 …test_no_launcher_hardcode.py`
  prints offenders + exits non-zero), read-ONLY (files are `read_text`-scanned,
  never imported/executed), and symlink-escape refused via `os.path.realpath`
  containment (a file resolving outside the scanned tree is itself a violation,
  fail-closed). Hermetic scanner-engine tests use their own tmp trees +
  injected allowlists, never the real framework allowlist.

CLAUDE.md now carries the prose contract (under the axes/foundation section):
framework code addresses the launcher via `framework.env.captain_name()`; the
ratchet enforces it in CI.

## 6 · Method note (how §2 was counted)

Category proxies over the `git diff 67fc5ae6 -- framework/**/*.py`:
(1) = added lines calling `captain_name(` ; (2) = removed lines containing
`/Users/nate` ; (3) = added lines gaining "the Captain"/"Captain's" ; (4)/(5)
= enumerated by hand from the lanes' deviations (they are keeps/flags, not
line rewrites). Aggregate, worktree-as-landed; the germline 11-file split is
exact (§ amendment). Parallel lanes share this worktree, so the census is the
whole DE-NATE sweep, not one lane.
