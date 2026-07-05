# INSTANCE-EXTRACT — Flavor-A data & code out of `framework/` (E4 record) — 2026-07-05

**Ruling realized:** FOUNDATION-FIRST + EVOLUTION ENGINE GO
(`shared/interfaces/captain-decisions.md`, 2026-07-05 ~00:45), clause (a) +
clause (4): *"anything Nate-specific (vault paths, screenpipe, Monday board IDs,
officer names) belongs in `instance/` or adapters, never `framework/` … launcher
genericization is IN-SCOPE core work."* `framework/` is the universal base for
any captain and either flavor; this deployment (captain **Nate**, Flavor-A) is
the first instance and proving ground, not the product.

This E4 lane is the DIRECT continuation of the DE-NATE sweep
(`docs/plans/de-nate-foundation-2026-07-05.md`). De-nate parameterized the
captain NAME and deliberately LEFT three launcher DATA couplings in place,
FLAGGED for follow-up (that doc §4). **This run discharges those flags** and
lifts one more of the same kind. Reinforced by the EXTERNAL-COMMS-GRANTABILITY
ruling (2026-07-05): *org identity is instance-scoped, not framework-structural*
— the internal-domain list is instance data by that ruling too.

**Branch:** `feat/instance-extract` (worktree
`.claude/worktrees/instance-extract`, base `fa6c3032`). **Germline subset
(3 files):** governed by
`docs/proposals/germline-amendment-instance-extract-2026-07-05.md`
(`apply instance-extract`). **Non-germline subset:** merges with no unlock,
recorded here.

## 1 · What MOVED to `instance/` — the Flavor-A autoreply cell (de-nate flag 1)

`framework/autoreply/` → `instance/flavor-a/autoreply/` (git-tracked rename,
5 files: `__init__.py`, `kristoffer_uat.py`, `wiring.py`, `tests/__init__.py`,
`tests/test_kristoffer_uat.py`). It is the scoped **Kristoffer-Møller-Nielsen**
UAT auto-reply cell — named after a specific colleague, carrying instance-only
identifiers (`copy_to_nate` / `nate_copy` params, `nate_model`, `KRISTOFFER_*`
slugs). Flavor-A-instance-specific *by construction*: a colleague-scoped
auto-reply is deployment config, not framework base. De-nate §4 flag 1 marked
it `TODO(DN): MOVE to instance/`; this run performs the move. Its 46 tests run
green in the new location (`pytest instance/flavor-a/autoreply/tests` → 46
passed). **Nothing under `framework/` imported it** (verified — grep clean), so
the move needs no framework edit and the layer-separation gate stays honest
(§6).

## 2 · What became CONFIG — three `framework.env` resolvers (de-nate flags 2 & 5 + one more)

The resolver precedent is `framework.env.captain_name()` (shipped by de-nate:
reads `instance/config/platform.yml`, cached, fail-closed to `"Captain"`). This
run mirrors it three times. Each resolver reads `instance/config/platform.yml`
(else `product.yml` / nested `product.<key>`), caches once per process, and
fails closed to a GENERIC value — so a clean-room deployment inherits none of
Nate's data.

| resolver (`framework/env.py`) | reads config key | fail-closed default | consumer(s) — was hardcoded | de-nate flag |
|---|---|---|---|---|
| `captain_role(default="the Captain")` | `captain_role` (`Head-of-Tech`) | `"the Captain"` | `framework/fidelity/decision_cell.py` — the F3-intent decision-cell clone prompt + `types.DecisionCase` docstring (was the literal `"Head-of-Tech"`). **Non-germline.** | flag 2 |
| `org_domains(default=())` | `org_domains` (six domains) | `()` (every recipient external) | `framework/authority/classifier.py` `_INTERNAL_DOMAINS` — the internal-vs-external recipient list (was a six-tuple literal). **Germline.** | (same pattern; reinforced by the EXTERNAL-COMMS-GRANTABILITY ruling) |
| `tasks_board(default="")` | `tasks_board` (`5091706356`), env `CABINET_TASKS_BOARD` overrides | `""` (`isdigit()` guard refuses) | `framework/frontdoor/action_exec.py` `DEFAULT_TASKS_BOARD` + `framework/frontdoor/actfirst_canary.py` `_DEFAULT_BOARD` (was `"5091706356"` in both). **Germline.** | flag 5 |

New keys in `instance/config/platform.yml`: `captain_role`, `org_domains`,
`tasks_board` (each with an explanatory comment block naming its resolver and
fail-closed behavior). These keys live in the INSTANCE layer, not `framework/`.

## 3 · Germline vs non-germline split

- **Germline (3 files, → the amendment):** `authority/classifier.py`,
  `frontdoor/action_exec.py`, `frontdoor/actfirst_canary.py`. Each swaps a data
  literal for `env.<resolver>()` + one import; NO classification / verdict /
  board-routing logic change; byte-identical on this instance. Captain applies
  via `apply instance-extract` (they are schg-locked in live).
- **Non-germline (merge with no unlock, recorded here):** `framework/env.py`
  (+3 resolvers, +cache sentinels), `framework/fidelity/decision_cell.py`
  (`captain_role` consumer, byte-identical — `_ROLE = captain_role()` injected
  into the clone prompt), `framework/fidelity/types.py` (docstring
  generalization `Head-of-Tech` → `Captain`), `framework/tests/test_env.py`
  (+17 resolver tests: `TestCaptainRole` / `TestOrgDomains` / `TestTasksBoard`),
  `instance/config/platform.yml` (+3 keys), the autoreply move (§1), and the
  ratchet-allowlist shrink (§4).

## 4 · The ratchet extension (`framework/tests/test_no_launcher_hardcode.py`)

The clean-room ratchet (DN-6) had ONE whole-file allowlist entry:
`_ALLOWLISTED_FILES["framework/autoreply/kristoffer_uat.py"]` — de-nate
pre-authorized the Flavor-A cell's launcher identifiers *pending its move to
`instance/`*. **That move happened in §1, so the entry is now dead cover and
MUST be deleted.** With autoreply gone, `framework/` no longer contains any
Flavor-A colleague cell, so the ratchet scans a strictly SMALLER `framework/`
tree with an EMPTY whole-file allowlist (only the two line-scoped anti-pattern
doc exemptions remain, both already empty). The ratchet's own forcing-function
`test_every_allowlisted_path_exists` requires this deletion — it goes RED while
a stale entry points at the moved file. This deletion is the mechanical
consequence of the move and belongs to the same (non-germline) unit of work;
until it lands the ratchet suite is red on exactly that self-test (see §8).

Net effect: the ratchet now proves `framework/` carries **no** launcher name,
home path, OR Flavor-A colleague cell — the allowlist may only ever shrink, and
this run shrinks it to fully generic.

## 5 · Safety invariant (correctness proof for the whole run)

On this deployment the resolvers return the launcher's exact values
(`org_domains()` → the six domains, `tasks_board()` → `"5091706356"`,
`captain_role()` → `"Head-of-Tech"`), so every parameterized runtime site
renders BYTE-IDENTICAL to `fa6c3032`. Proof: the tests pinning classification,
board-routing, and the decision-cell prompt stay green with no edit —
`pytest framework/authority/tests/test_classifier.py
framework/frontdoor/tests/test_action_exec.py
framework/frontdoor/tests/test_actfirst_canary.py
framework/fidelity/tests/test_decision_cell.py` → **242 passed**; the resolvers
are pinned by **22 passed** in `test_env.py` (17 new), including byte-identity
guards asserting this worktree's `platform.yml` yields the six domains /
`5091706356` / `Head-of-Tech` with `CABINET_ROOT` unset. Where a test hardcoded
a value it was fixed to read the resolver the same way — never by weakening the
assertion.

## 6 · Layer separation (`framework/ → instance/` one-way)

`framework/` must NEVER import `instance/`. Verified for this run: no
`framework/**/*.py` imports the moved `autoreply` package or any
`instance/flavor-a/...` module (grep clean). The three resolvers reach instance
config the SANCTIONED way — `framework/env.py` reading
`instance/config/platform.yml` by a single path literal, the same seam
`captain_name()` already used — and add ZERO new `check-layer-separation.sh`
violations (the gate attributes its only two current `FRAMEWORK_PATH_INSTANCE`
entries to `framework/acting/screenpipe_adapter.py` and
`framework/tests/test_clean_room.py`, both UNMODIFIED by this run and present
verbatim at base `fa6c3032` — inherited from the de-nate merge, not caused here;
see §8). The read-side data coupling those two files represent is exactly what
the source-adapter seam (§7) is designed to eliminate.

## 7 · Next foundation build — the SOURCE-ADAPTER boundary (D2)

Data-extraction discharges the launcher CONSTANTS (name, role, domains, board).
It does NOT discharge the launcher BEHAVIORAL coupling that de-nate §4 also
flagged: the screenpipe / Obsidian-vault / `BrainAdapter` read side (vault
search, person intel, commitments, drafting lessons, voice/`nate_model`
priors), the product-repo list, and `~/.screenpipe` state. Those are an
interface, not a constant — you cannot lift them with a `yaml.safe_load`.

The design that discharges them is
**`docs/plans/source-adapter-boundary-2026-07-05.md`** (E4 · D2 — RATIFIABLE
SPEC, design only). It defines a personal-sensing **source adapter**: framework
CORE depends on a narrow read interface, and the Flavor-A screenpipe brain
becomes an instance-bound backend selected by `flavor` / `deployment_target`
(the slot the axes contract already reserves: *flavor selects "evidence
supply"*, *target selects "source/actuator bindings"* —
`docs/plans/cabinet-axes-spec-2026-07-05.md` §6). A clean-room / Flavor-B
deployment then binds a different — or NULL — backend without editing
`framework/`. That is the next foundation build after this one.

## 8 · Known state at hand-off (for the merge/apply session)

- **Ratchet self-test RED until §4 lands.** `test_no_launcher_hardcode.py::
  TestAllowlistDiscipline::test_every_allowlisted_path_exists` fails while the
  moved `kristoffer_uat.py` still has its stale whole-file allowlist entry. The
  fix is the one-line deletion described in §4 (same unit of work as the move).
  `pytest framework/` is green only once it lands.
- **Layer-sep gate RED is INHERITED, not caused here.** `check-layer-separation.sh`
  reports `new=2` — both `framework/acting/screenpipe_adapter.py:905`
  (`os.path.join(root, "instance", "config", "platform.yml")`) and
  `framework/tests/test_clean_room.py:37` (`root / "instance" / "config"`),
  UNMODIFIED by this run and present verbatim at `fa6c3032` (from the de-nate
  merge), absent from the committed `.layer-separation-baseline`. This run adds
  ZERO new violations. Discharging it properly is the source-adapter build (§7);
  baselining it (Captain-approved) is the stopgap. Out of this lane's scope.
