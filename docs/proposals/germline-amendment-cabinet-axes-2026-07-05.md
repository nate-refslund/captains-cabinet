# Germline amendment proposal — CABINET AXES — 2026-07-05

**Status:** AWAITING CAPTAIN. Every germline file named below is
Captain-applied only. Reply **"apply cabinet axes"** and the session
executes the apply ritual (§7) exactly: unlock → merge `feat/cabinet-axes`
→ commit → re-lock → verify. Nothing in this package changes live behavior
before that ritual — and nothing behaves differently after it until YOU
opt a deployment into an axis point (an `earn_up` ruling, a `never_grant:`
line, a `deployment_target:` key, or a preset copy).

**Branch of record:** `feat/cabinet-axes` (worktree
`.claude/worktrees/cabinet-axes`, base `6e104dca`). The branch is the
diff; this document is its Captain-readable contract.

**Encodes (already-ruled, logged live in
`shared/interfaces/captain-decisions.md` on 2026-07-05 — reference only,
do NOT re-paste):**

- **THREE AUTONOMY LEVELS × FLAVORS × DEPLOYMENTS (2026-07-05,
  Captain-directed, in-session)** — `earn_up | guardian | sovereign` as
  first-class postures × `flavor: personal|org` × `deployment_target:
  macbook|mac_mini|docker`; axes are DATA through resolvers/tables, never
  code branches; presets are the UX; trust_ladder.py returns as the
  OPT-IN earn_up surface, not as doctrine.
- **EXTERNAL-COMMS GRANTABILITY IS INSTANCE-SCOPED, NOT FLAVOR-STRUCTURAL
  (2026-07-05, Captain-ruled, in-session)** — grants.py's
  `flavor=personal ⇒ external_comms refused` gate was Nate's instance
  policy encoded as framework law; the replacement is the Captain-locked
  `never_grant:` list in posture.yml. Nate's personal instance keeps
  today's exact behavior via `never_grant: [external_comms]`
  (ACT-AND-DRAFT stays his instance line); channel adapters become
  optional framework plugins.

The only paste-ready decisions text in this package is the **apply
record** (§6) — it cites both rulings by heading and is pasted only when
you apply.

**Precondition:** none. The package is additive + dark: guardian AND
sovereign resolution, block strings, digests, and grants behavior are
byte-identical when no earn_up/never_grant/deployment_target config is
present (the guardian byte-parity suites + the 18-combo invariant sweep
prove it per commit). It is independent of the authority-enforcing flip,
the act-first state, and the sovereign amendment's dark lanes.

---

## §0 · What this changes, in one paragraph

The cabinet becomes configurable along **three orthogonal axes — all
data, never code branches**. *Level:* the ONE authority matrix gains a
`postures.earn_up` static table (every non-ceiling class `propose_only`
at all five confidence states; six ceilings `always_gated`) validated to
only-narrow vs the root table, selected by the same attestation chain
that ships today — `sovereign` still requires the locked ruling, while
`earn_up` is a NARROWING choice honored even unattested, and the new
`instance/config/posture-narrow` file + `CABINET_POSTURE` env can only
cap DOWN (min by permissiveness). All autonomy above the earn_up floor
comes from the resurrected trust-ladder overlay
(`framework/learning/trust_ladder.py`): rungs
`would-like-to → intend-to → ive-done → ive-been-doing` map to
`propose_only → auto_with_veto_window → notify_after → auto`, lift ONLY
graduated cells in Captain-granted lanes, never lift ceilings, and
fail-closed to the floor on a missing/corrupt ladder file — the Captain
grants every rung from a one-tap card; the system never self-promotes.
*Flavor:* grants.py drops the flavor-structural external gate for the
instance-scoped `never_grant:` list (rows in a never-granted class are
dropped fail-closed at load + ONE deduped `kind=decision` need per
class). *Target:* posture attestation becomes a pluggable backend keyed
on `deployment_target` — `schg` on macbook/mac_mini (today's st_flags
check, unchanged), `ro_mount` in docker (write-probe + /proc/mounts ro
flag; the unlock ritual happens HOST-side), both fail-closed to
guardian — with a docker preset (Dockerfile + compose ro-mounts + a cron
renderer off the same services.yml). The **axes contract** makes the
doctrine mechanical: an AST linter rejects any axis comparison outside
the germline-pinned `axes-allowlist.yml`, an 18-combo invariant suite
proves every level×flavor×target point per commit,
`validate-extension.sh` + the manifest schema refuse axis-branching or
path-escaping extensions, `.claude/rules/axes-contract.md` binds LLM
authors, and the whole kernel joins the germline lock set in lockstep
(§3). Rolling back is one revert (§7).

---

## §1 · What it does NOT do

- **No guardian OR sovereign byte changes.** With no
  earn_up/never_grant/deployment_target config present, resolution,
  block strings, lane summaries, digests, caps, and binder behavior are
  byte-identical — pinned by the existing guardian parity suites
  (eval-016) and swept across all 18 combos
  (`framework/tests/test_axes_invariants.py`): flavor and target NEVER
  change verdict resolution.
- **earn_up is opt-in, never a new default.** Absent/corrupt/unattested
  config still resolves guardian; `CABINET_POSTURE=sovereign` is still
  ignored; nothing ships with an earn_up ruling. The rung ladder is inert
  in guardian and sovereign (its events cannot be emitted there).
- **No ceiling becomes liftable.** The earn_up table's six ceilings are
  `always_gated` at every confidence state; the ladder overlay never
  lifts a ceiling; `standing_grant` stays ceiling-row-only and is
  validator-REJECTED in earn_up and in the root table.
- **No self-grant path.** `trust_rung_granted` is recorded ONLY from the
  Captain surface (`trust_ladder.grant_rung`); the propose path
  physically cannot emit it. Rung grants live in Captain-locked
  `instance/config/trust-ladder.yml` (germline files-class the moment it
  is born; the `.example` stays unlocked).
- **external_comms stays exactly as Nate ruled it — per instance.** The
  framework stops encoding one captain's policy; Nate's personal
  deployment sets `never_grant: [external_comms]` in its posture.yml at
  apply, preserving today's behavior verbatim (ACT-AND-DRAFT: external
  recipients per-item Captain-approved on HIS instance). Any other
  captain may grant external_comms on their instance — the class is
  grantable ONLY where a captain doesn't never_grant it.
- **The dashboard posture tile is render-only + narrow-only.** It shows
  `posture-status.py` output and can offer the DOWNGRADE verb; for any
  upgrade it prints the attested ritual. No state-changing autonomy
  control exists in the dashboard, and no officer surface can widen — a
  "go sovereign" button is a forge vector and is structurally refused by
  the resolver (attestation, not UI, is the gate).
- **Docker gains no self-unlock.** The `ro_mount` backend attests
  read-only bind mounts the container cannot remount at any privilege;
  editing germline/posture/grants happens on the HOST (where schg may
  additionally arm). `germline-lock.sh --backend ro-mount` is a
  deliberate no-op that prints the host-side ritual.
- **No sovereign-amendment re-litigation.** posture.yml's closed-key
  schema only GROWS two optional keys (`never_grant`,
  `deployment_target`); old files stay valid; unknown keys still reject
  fail-closed. The needs ledger, grants writer discipline (D7), dark
  gate-apply lane (D15), and graduation/bars (D9) are untouched.

---

## §2 · Per-file inventory (the branch is the diff)

Export the exact germline diff set for review:

```bash
git -C /Users/nate/captains-cabinet/.claude/worktrees/cabinet-axes \
  diff 6e104dca -- \
  framework/policies/authority-matrix.yml framework/authority/matrix.py \
  framework/authority/posture.py framework/authority/grants.py \
  cabinet/scripts/lib/policy_engine.py cabinet/scripts/hooks/pre-tool-use.sh \
  framework/policies/base-safety.yml cabinet/scripts/germline-lock.sh \
  framework/policies/immutable-core.yml
git -C /Users/nate/captains-cabinet/.claude/worktrees/cabinet-axes \
  status --short        # NEW files: ladder, allowlist, contract rule, gate pair, presets, channels, deploy, tests
```

| file | change | germline |
|---|---|---|
| `framework/policies/authority-matrix.yml` | `postures.earn_up` static table (all non-ceiling cells propose_only; six ceilings always_gated); root + sovereign tables byte-untouched | yes |
| `framework/authority/matrix.py` | earn_up-only-narrows validator on the frozen permissiveness ordering (always_gated < propose_only < classifier < auto_with_veto_window < {act_with_undo, notify_after} < auto; standing_grant ceiling-row-only, forbidden in earn_up and root) | yes |
| `framework/authority/posture.py` | 3-level enum + POSTURE_PERMISSIVENESS; narrow-only selection (env + `posture-narrow` cap, min-permissiveness); earn_up honored unattested; `never_grant` + `deployment_target` optional closed-schema keys; pluggable `is_locked()` attestation backends (schg / ro_mount), symlink/realpath-contained, fail-closed to guardian | yes |
| `framework/authority/grants.py` | flavor-structural external gate REMOVED; `never_grant:` loader — rows dropped fail-closed + ONE deduped kind=decision need per class | yes |
| `cabinet/scripts/lib/policy_engine.py` | earn_up posture-table selection + trust-ladder overlay wire at verdict resolution (lift only when posture==earn_up ∧ cell graduated ∧ Captain-granted rung; ceilings never lifted) | yes |
| `cabinet/scripts/hooks/pre-tool-use.sh` | §5 case + §5b GERM_PATH_RE/GERM_DIR_RE gain the axes kernel set (§3) | yes |
| `framework/policies/base-safety.yml` | germline-readonly += the axes kernel set (§3) | yes |
| `cabinet/scripts/germline-lock.sh` | FILES += trust_ladder.py, axes-contract.md, extension-manifest.schema.json, validate-extension.sh, trust-ladder.yml; DIRS += instance/config/posture-presets; `--backend ro-mount` no-op mode with host-side instructions (AX-4) | yes |
| `framework/policies/immutable-core.yml` | axes Ring-0 enumeration (§3) + posture-narrow / generate-services-cron.py non-entries documented | yes |
| `framework/policies/axes-allowlist.yml` | NEW — THE sanctioned axis-branching surface (closed schema, fail-closed to EMPTY, widening = Captain amendment); `pending: AX-8` flag cleared in this same change (eval-020 flip discipline) | yes (new) |
| `framework/learning/trust_ladder.py` | NEW — earn_up rung map + climb cards + Captain grant surface; fail-closed to the propose_only floor | yes (new) |
| `.claude/rules/axes-contract.md` | NEW — the contract in prose for every officer/loop/captain extension | yes (new) |
| `framework/schemas/extension-manifest.schema.json` | NEW — closed-key manifest schema (kind/risk_classes/axis_compat enums pinned to kernel vocab; undo_contract pattern) | yes (new) |
| `cabinet/scripts/validate-extension.sh` | NEW — manifest schema + entrypoint realpath containment + strict axis lint (EMPTY allowlist) over extension files; read-only, never executes manifest content | yes (new) |
| `instance/config/posture-presets/` | NEW dir — `personal-macbook.yml`, `org-macmini.yml`, `org-docker.yml` (pre-filled posture.yml templates; locked -R so no officer can seed a widened ruling) | yes (new dir) |
| `memory/golden-evals/eval-020-axes-contract.md` | NEW — linter + allowlist + Ring-0 coverage judge (dir-covered) | yes (new) |
| `instance/config/trust-ladder.yml` | deployment-created at the first Captain `grant rung`, then locked — enumerated + list-wired BEFORE it exists (like posture.yml); rung rows MINT authority ⇒ files-class, never SKIP | yes (deployment-created) |
| `framework/events/emitter.py` | `VALID_EVENT_TYPES += trust_rung_proposed / trust_rung_granted` (re-registered for the opt-in earn_up surface; append-only) | no |
| `framework/frontdoor/binder_wire.py` | AX-7 narrow-only `posture guardian\|earn_up\|clear` verb writing `posture-narrow` (dark behind `CABINET_NEEDS_WIRED`). NO rung-grant verb: rung grants MINT authority, so — mirroring the killed Telegram-sealed grant-writer (sovereign D7/R1) — they are applied ONLY to the schg-locked `instance/config/trust-ladder.yml` via the Captain's unlock ritual, never a chat verb; `trust_rung_proposed` surfaces the earned rung as a one-tap card, the grant itself is a locked-file edit | no |
| `framework/channels/` | NEW — channel-adapter contract (`send/classify/undo_contract/capabilities`) + Teams/Outlook refactor + Slack adapter + sim mocks (AX-5); adapters receive resolved axis values, never read axis config | no |
| `instance/config/channels.yml.example` + `trust-ladder.yml.example` | NEW reference schemas (deliberately unlocked) | no |
| `instance/config/posture.yml.example` + `standing-grants.yml.example` | +`never_grant:` / `deployment_target:` documented keys | no |
| `cabinet/deploy/docker/` | NEW — Dockerfile + compose with germline/posture/grants **read-only host mounts** + README (host-side unlock ritual); clean-room CI gate | no |
| `cabinet/scripts/generate-services-cron.py` | NEW — cron renderer off the same `cabinet/services.yml` for the docker target (render-only; NOT germline — §3 justification) | no |
| `cabinet/scripts/posture-status.py` | NEW — read-only one-JSON posture/axes status via the ONE resolver chain | no |
| `cabinet/dashboard/.../posture/page.tsx` | NEW — posture tile: render + narrow-only offer; upgrade prints the ritual | no |
| `.claude/skills/cabinet-init/SKILL.md` | axes interview (level/flavor/target, default guardian) + preset activation | no |
| `CLAUDE.md` | axes-contract pointer paragraph + rules-list mention | no |
| `docs/mac-mini-deploy-runbook.md` + `docs/mac-mini-setup.md` | posture/axes notes (presets, narrow cap, ro-mount pointer) | no |
| `shared/interfaces/captain-rules-index.yaml` | re-generated (byte-identical — index sources are captain-patterns/intents, untouched here) | no |
| `framework/**/tests/*`, `cabinet/scripts/lib/tests/*` | axis linter + 18-combo invariants + ladder/targets/grants/presets/binder/channels suites + lockstep extension + this doc's lint | no |

### Ring-0 additions of record (`framework/policies/immutable-core.yml`)

The lockstep meta-test
(`framework/tests/test_germline_lockstep_consistency.py`) drives all four
germline lists (germline-lock FILES/DIRS/SKIP · hook §5 case · §5b
GERM_PATH_RE · base-safety patterns) off the enumeration — every axes
entry below entered ALL FOUR LISTS in this same change, no `pending:`
remains anywhere, and every entry asserts HARD:

- **files:** `framework/learning/trust_ladder.py` (a forged rung map
  LIFTS verdicts — judged authority code),
  `framework/policies/axes-allowlist.yml` (the sanctioned branching
  surface; dir-covered by `framework/policies/`, enumerated so eval-020's
  allowlist ⊆ immutable-core check is explicit),
  `.claude/rules/axes-contract.md`,
  `framework/schemas/extension-manifest.schema.json` +
  `cabinet/scripts/validate-extension.sh` (a forged schema or gate script
  admits axis-branching extensions), `instance/config/trust-ladder.yml`
  (deployment-created; also added to the meta-test's authority-minting
  completeness allowlist).
- **dirs:** `instance/config/posture-presets/` (locked -R — a forged
  preset seeds a widened ruling at ratification time).

---

## §3 · Lockstep detail + two deliberate NON-entries

**Deliberately unlocked #1 — `instance/config/posture-narrow`.** The
narrow-only runtime cap (single word `guardian|earn_up`) read by
`resolve_posture` as a CAP applied after file+env resolution (min by
permissiveness). It appears in NO lock list and NO hook arm: it can only
NARROW, so tampering is fail-safe by construction, and the Captain's
binder verb writes it at runtime — locking or hook-blocking it would
break the instant-downgrade surface (axes spec §1). Documented in
immutable-core.yml comments; every failure mode of the file is a
narrowing or a no-op.

**Deliberately unlocked #2 — `cabinet/scripts/generate-services-cron.py`
(decide + justify).** Decision: NOT germline. It renders **operational
schedule rows only** from `cabinet/services.yml` — no verdict, grant, or
authority content ever passes through it — and it is render-only by
contract (it never installs the crontab; installation is a separate
deliberate step: the docker preset's CMD or a host `crontab <file>`).
Locking it while `generate-plists.py` — its launchd twin, whose output IS
live-loaded on the Macs — stays unlocked would be lock theater. What
EXECUTES stays governed where it always was: the root LaunchDaemon
definition is Ring-0, and on docker the germline boundary is the host's
ro-mounts, not the renderer.

**The `.example` discipline.** `instance/config/trust-ladder.yml.example`
(like `posture.yml.example`) stays unlocked and editable via the Write
tool: the lock is exact-path, the hook §5 arm is suffix-anchored, and
only the LIVE file mints authority. (§5b's bash-write screen
substring-blocks `.example` bash writes too — the same accepted
fail-toward-blocking FP that already applies to `posture.yml.example`;
use the Write tool.)

**Layer-separation gate state (declared, not hidden).** Three axes test
files (`test_posture_earnup.py`, `test_posture_targets.py`,
`test_axes_invariants.py`) tripped
`cabinet/scripts/check-layer-separation.sh`'s literal-token check and got
the same neutral-token treatment trust_ladder.py uses (paths built from
the kernel's own `posture_path()`/`narrow_cap_path()`/`grants_path()`
resolvers — no test weakened; `test_posture.py`, already baselined,
still pins the literal locations). Six hits remain from the AX-5/AX-7
lanes (`framework/channels/contract.py` + its three test files,
`test_ax7_presets.py`, `test_ax7_binder_posture.py`) — resolve before or
at apply: same neutral-token treatment where the file is a test, or a
Captain-ratified `.layer-separation-baseline` growth for
`framework/channels/contract.py` if its instance-config read
(`channels.yml`) is ruled by-design (the same class as the ratified
posture.py/grants.py entries).

---

## §4 · CI proofs

| Proof | Where it lives | Asserts |
|---|---|---|
| A1 | `framework/tests/test_axes_contract.py` | the axis linter engine fires (never vacuous), the framework tree is green under the allowlist, the allowlist loads fail-closed (ANY malformation ⇒ EMPTY), allowlist ⊆ immutable-core with NO pending flags (eval-020 spine) |
| A2 | `framework/tests/test_axes_invariants.py` | all 18 level×flavor×target combos: ceilings never unconditional-auto; earn_up ≤ root cell-by-cell + all-propose_only floor; never_grant rows dropped in every combo; sovereign requires attestation / earn_up honored unattested; flavor/target never change verdict resolution (byte-equal maps) |
| A3 | `framework/authority/tests/test_posture_earnup.py` + `test_matrix_earnup.py` + `cabinet/scripts/lib/tests/test_policy_engine.py` | narrow-only selection rules (env + posture-narrow cap), earn_up table validation, ladder overlay lift bounds (graduated + granted only; ceilings never) |
| A4 | `framework/authority/tests/test_posture_targets.py` | attestation backends: schg st_flags, ro_mount write-probe + /proc/mounts, both fail-closed to guardian; symlink/realpath containment |
| A5 | `framework/authority/tests/test_grants.py` | never_grant drop + ONE deduped decision-need per class; flavor gate removal proven grantable-elsewhere |
| A6 | `framework/learning/tests/test_trust_ladder.py` | rung→verdict map, one-rung-at-a-time climb cards, Captain-only grant surface, fail-closed floor on missing/corrupt ladder |
| A7 | `framework/tests/test_germline_lockstep_consistency.py` | every axes Ring-0 entry wired into all four germline lists, reverse-mapped, deployment-created exemptions exact, authority-minting completeness includes trust-ladder.yml — hard, no xfails |
| A8 | `framework/channels/tests/*` + `framework/authority/tests/test_ax7_presets.py` + `framework/frontdoor/tests/test_ax7_binder_posture.py` | adapter contract + mocks (no live sends), presets are valid inert posture.yml templates, binder verb narrows only |
| A9 | `framework/tests/test_axes_amendment_doc_lint.py` | THIS document stays honest against the tree (token, inventory, rollback, non-entries, decisions references) |

---

## §5 · APPLY-GATE evidence pack (all green before you reply)

a. **Suites green — run the three roots SEPARATELY** (a combined
   `framework/ cabinet/scripts/lib/tests` invocation errors at
   collection: `cabinet/scripts/lib/tests` and
   `cabinet/scripts/gates/tests` both claim the top-level `tests`
   package — NEVER use the combined form). Pre-build baseline for
   reference: framework 2836 passed / 17 skipped · lib 444 · gates 6.
   ```bash
   python3.12 -m pytest framework/ -q -p no:cacheprovider
   python3.12 -m pytest cabinet/scripts/lib/tests -q -p no:cacheprovider
   python3.12 -m pytest cabinet/scripts/gates/tests -q -p no:cacheprovider
   ```
   Then re-run the framework sweep with `CABINET_POSTURE=earn_up` (must
   only narrow — nothing widens or errors) and with
   `CABINET_POSTURE=sovereign` (still ignored — env cannot widen).
b. **Axis linter strict-fire probe** — `python3.12
   framework/tests/test_axes_contract.py --scan framework/authority
   --rel-to .` reports the sanctioned kernels (non-zero exit proves the
   engine fires); the pytest tree-green test proves the allowlist covers
   exactly those.
c. **Extension gate probe** — `bash cabinet/scripts/validate-extension.sh
   <tmp ext>` passes a clean manifest+adapter and refuses each of:
   axis-branching code, schema-invalid manifest, symlinked manifest,
   traversal entrypoint (the test class runs all of these; a manual spot
   check is one command).
d. **Lockstep meta-test green** (A7 — no pending, no xfail anywhere).
e. **`germline-lock.sh status`** shows the axes files locked after the
   ritual (trust_ladder.py, axes-allowlist.yml via dir-cover,
   axes-contract.md, extension-manifest.schema.json,
   validate-extension.sh, posture-presets/;
   trust-ladder.yml shows "skip (absent)" until the first Captain rung
   grant creates it) — then `germline-lock.sh verify` proves a write
   bounces.
f. **Guardian/sovereign byte-parity** — with NO
   earn_up/never_grant/deployment_target config present, the parity
   suites pass byte-identical (A2's fixed-level byte-equal verdict maps
   + the existing guardian golden blocks).
g. **Layer-separation gate** — `bash
   cabinet/scripts/check-layer-separation.sh` reports no NEW violations
   (§3: the six remaining AX-5/AX-7 hits resolved by their owners or
   Captain-ratified baseline growth in the apply window).

---

## §6 · captain-decisions.md — ledger state + the ONE paste-ready apply record

**Already logged live (2026-07-05, reference only — do NOT re-paste):**
`## THREE AUTONOMY LEVELS × FLAVORS × DEPLOYMENTS (2026-07-05,
Captain-directed, in-session)` and `## EXTERNAL-COMMS GRANTABILITY IS
INSTANCE-SCOPED, NOT FLAVOR-STRUCTURAL (2026-07-05, Captain-ruled,
in-session)` both landed in `shared/interfaces/captain-decisions.md` on
2026-07-05. On apply, add one line under each: *"Realized by: germline
amendment cabinet-axes 2026-07-05 (`apply cabinet axes`)."*

**Apply record — paste-ready** (paste when you apply; it references the
two rulings, it does not duplicate them):

```markdown
## CABINET AXES APPLIED (2026-07-05, Captain apply token: `apply cabinet axes`)

**What:** Applied the cabinet-axes germline amendment
(docs/proposals/germline-amendment-cabinet-axes-2026-07-05.md): the
3-level × 2-flavor × 3-target axes as data — postures.earn_up table +
trust-ladder overlay (opt-in), never_grant instance-scoped grantability,
deployment_target attestation backends (schg / ro_mount), the axes
contract (linter + allowlist + 18-combo invariants + extension gate +
axes-contract.md rule + eval-020), and the lockstep germline additions.
Guardian and sovereign behavior byte-identical absent new config; my
personal instance keeps `never_grant: [external_comms]`.

**Why:** Realizes the two rulings logged above on 2026-07-05 — "THREE
AUTONOMY LEVELS × FLAVORS × DEPLOYMENTS" (Captain-directed) and
"EXTERNAL-COMMS GRANTABILITY IS INSTANCE-SCOPED, NOT FLAVOR-STRUCTURAL"
(Captain-ruled) — reference only, full text in those entries.

**Captain:** Nate.
```

---

## §7 · Apply ritual (one sitting) + rollback

```bash
sudo bash cabinet/scripts/germline-lock.sh unlock
git merge feat/cabinet-axes            # or FF; resolve, re-run §5a suites
# Nate's personal instance line (preserves ACT-AND-DRAFT verbatim):
#   ensure instance/config/posture.yml carries `never_grant: [external_comms]`
#   (absent list = all six ceiling classes grantable in sovereign — framework
#   default, NOT Nate's instance default)
sudo bash cabinet/scripts/germline-lock.sh lock
bash cabinet/scripts/germline-lock.sh status && bash cabinet/scripts/germline-lock.sh verify
```

Optional, any time later (each independently opt-in): copy a
`instance/config/posture-presets/*.yml` preset over posture.yml (then
lock — the ritual is the ratification); rule `posture: earn_up` (honored
even unattested — it only narrows); write `deployment_target: docker` on
a container deployment (host mounts germline/posture/grants `:ro` per
`cabinet/deploy/docker/README.md`); bind channel adapters in
extensions.yml (every adapter passes `validate-extension.sh` or its
loader skips it fail-closed).

**One-revert rollback:** revert the merge commit — this restores every
germline file (authority-matrix.yml, matrix.py, posture.py, grants.py,
policy_engine.py, pre-tool-use.sh, base-safety.yml, germline-lock.sh,
immutable-core.yml) and removes the new germline set (axes-allowlist.yml,
trust_ladder.py, axes-contract.md, extension-manifest.schema.json,
validate-extension.sh, posture-presets/, eval-020-axes-contract.md) plus
the non-germline additions (channels/, deploy/docker/,
generate-services-cron.py, posture-status.py, the dashboard tile, the
binder verbs, emitter event types, examples, tests, docs). Then
`rm -f instance/config/posture-narrow instance/config/trust-ladder.yml`
(if either was ever written). Absent ladder/narrow files ⇒ every new
path is inert; a reverted tree resolves guardian exactly as today.

Reply **"apply cabinet axes"** to apply exactly the above.
