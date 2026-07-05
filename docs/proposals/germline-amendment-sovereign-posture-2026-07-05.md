# Germline amendment proposal — SOVEREIGN POSTURE — 2026-07-05

**Status:** AWAITING CAPTAIN. Every germline file named below is
Captain-applied only. Reply **"apply sovereign posture"** and the session
executes the apply ritual (§8) exactly: unlock → rebase-before-merge →
merge `feat/sovereign-posture` → create the instance attestation files →
commit → re-lock → verify. Nothing in this package changes live behavior
before that ritual, and nothing acts sovereign after it until YOU lock a
posture ruling (the lock IS the signature, D5).

**Branch of record:** `feat/sovereign-posture` (worktree
`.claude/worktrees/sovereign-posture`). The germline edits are authored as
worktree commits AND exported as diffs by the command in §2 — the branch is
the diff; this document is its Captain-readable contract.

**SUPERSEDES (each staged in this same branch):**

1. **cabinet-init SKILL §4 "Autonomy posture — NOT negotiable at init"** →
   guardian at init, always; **sovereign is a post-init Captain
   ratification** (the generator renders an INERT `posture.yml` scaffold;
   the schg lock is the ratification act).
2. **Golden evals 011/012/013/015 wording** — guardian text byte-unchanged;
   the invariant is precisified to **"never UNCONDITIONAL auto"**: a
   sovereign ceiling allow must cite a signed `grant_id` from the locked
   grants file with its hard-scope satisfied, else block + deduped NEED.
3. **Golden eval-014's letter** — explicitly ratified: unmeasured-cannot-auto
   is (a) a **root/guardian invariant forever** and (b) a **ceiling
   invariant in every posture**; the sovereign **non-ceiling**
   unmeasured→auto/notify_after is a Captain-ratified supersession (bars
   define proof; posture defines what unproven states unlock — D9).
4. **courses-of-action.md §2 "This is the ONLY relaxation"** → posture-
   conditional: guardian keeps it as the only relaxation; an attested
   sovereign posture relaxes per the `postures.sovereign` table instead
   (external recipients stay per-item Captain-approved in every posture —
   ACT-AND-DRAFT).

**Encodes (already-ruled, logged live in `shared/interfaces/
captain-decisions.md` on 2026-07-04 — referenced, not re-pasted):**
- **SOVEREIGN POSTURE (2026-07-04, Captain-ruled)** — all four decisions
  ratified: build all 9 lanes; ceilings = standing grants; self-improvement
  = evidence Gate + Ring-0 kernel; root privileged daemons stay DARK.
- **ACT-AND-DRAFT (2026-07-04, Captain-ruled — supersedes ACT-NOT-DRAFT)** —
  internal recipients: autonomous sends per the posture matrix; EXTERNAL
  recipients: per-item Captain approval ALWAYS (the flavor=personal
  external_comms standing-grant refusal is STRUCTURAL, never grantable);
  drafting is re-enabled as a first-class act alongside acting.
  `queue_draft` remains the only outbound transport.
- The only paste-ready decisions text in this package is the **Decision-B
  backfill** (§7) — that filesystem-lock ruling is absent from the ledger.

**Precondition:** none. The package is additive + dark: guardian is
byte-identical with no posture config (P1-P6), the needs binder verbs are
dark behind `CABINET_NEEDS_WIRED`, and the gate-apply root daemon ships DARK
(D15). It is independent of the authority-enforcing flip and of the
act-first state.

---

## §0 · What this changes, in one paragraph

Posture becomes a **selection dimension of the ONE authority matrix** —
never a second enforcement story. The germline floor gains a full
`postures.sovereign` verdicts table (root/guardian table byte-untouched;
`postures.guardian` is validator-REJECTED); posture *selection* lives in
Captain-locked `instance/config/posture.yml`, ceiling *grants* in
Captain-locked `instance/config/standing-grants.yml`, and both attest via
macOS `schg` (`resolve_posture` demands present ∧ schema-valid ∧
`deployment==CABINET_ID` ∧ locked; env may only NARROW). Under an attested
sovereign posture: reversibles auto (journaled where inverses exist),
pm/calendar keep act_with_undo, internal_comms/deploy_nonprod act-and-tell
(`notify_after` — the tell IS the audit), and the six hard ceilings resolve
`standing_grant` — auto **only** under a Captain-signed, locked, unexpired,
unrevoked grant with a satisfied hard-scope predicate; otherwise the step
gates, files a deduped NEED to the ONE needs ledger, and the chain proceeds.
Caps become alarms with a 10× mechanical freeze hard-stop; the silence
breaker forces canary + LLM content-audit (never consent-by-silence);
frozen kinds gain `unfreeze`/`rearm`; self-improvement runs the Evidence
Gate live while germline CODE auto-apply stays DARK. **Demote always
narrows: evidence beats posture.** Rolling back is one revert plus deleting
the instance posture file — absent ⇒ inert.

---

## §1 · Frozen interfaces this package implements

FI-1 `posture.yml` closed-key schema + fail-safe resolution ·
FI-2 `standing-grants.yml` fail-closed loader + hard-scope `check()` +
flavor=personal external_comms structural refusal (ACT-AND-DRAFT) ·
FI-3 ONE needs ledger (`shared/interfaces/needs-ledger.jsonl`, O_APPEND,
content-fingerprint `NEED-<8hex>` ids, `needs_enabled()` short-circuit) ·
FI-4 binder grant/deny/later/snooze/rearm grammar (hex ids, dark behind
`CABINET_NEEDS_WIRED`) · FI-5 runaway `caps.hard_multiplier` (default 10) +
`immutable-core.yml` as THE single source of Ring-0 paths, enforced by the
lockstep meta-test across all four germline lists.

---

## §2 · Per-file exact diffs — export command

The branch is the diff. Export the exact germline diff set for review:

```bash
git -C /Users/nate/captains-cabinet/.claude/worktrees/sovereign-posture \
  diff 01015e5c -- \
  framework/policies/authority-matrix.yml framework/authority/matrix.py \
  cabinet/scripts/lib/policy_engine.py cabinet/scripts/policy-shadow.py \
  framework/acting/run_action_lane.py framework/frontdoor/action_exec.py \
  framework/frontdoor/actfirst_canary.py framework/frontdoor/action_undo.py \
  framework/frontdoor/tell_surface.py framework/fidelity/consequence.py \
  cabinet/scripts/hooks/pre-tool-use.sh framework/policies/base-safety.yml \
  cabinet/scripts/germline-lock.sh .claude/rules/courses-of-action.md \
  'memory/golden-evals/eval-01*.md'
git -C /Users/nate/captains-cabinet/.claude/worktrees/sovereign-posture \
  status --short             # NEW files (untracked): kernel, gate, evals 016-019, tests
```

The full per-file inventory with change summaries is the Appendix table;
every germline row there is covered by the export above plus the NEW
germline set (`posture.py`, `grants.py`, `needs.py`, `gate.py`,
`apply_watch.py`, `immutable-core.yml`, `grant-apply.sh`, `gate-apply.sh`,
`com.cabinet.gate-apply.plist` — and, created at apply time,
`instance/config/posture.yml` + `standing-grants.yml`; created at the first
Captain-armed apply, `shared/interfaces/gate-apply-watch.jsonl`).

### Ring-0 enumeration of record (`framework/policies/immutable-core.yml`)

The lockstep meta-test drives all four germline lists off this enumeration
— the amendment closes every previously-pending pair (base-safety
enforcer-triad lag + the new sovereign set), so it now asserts HARD:

- **enforcer plane:** `.claude/settings.json`,
  `cabinet/scripts/policy-shadow.py`, `cabinet/scripts/kill-switch.sh`,
  `cabinet/scripts/germline-lock.sh`, dir `cabinet/scripts/hooks/`.
- **judged authority code:** `framework/authority/classifier.py`,
  `lane.py`, `matrix.py`, `veto.py`, `deploy_classifier.py`,
  `framework/fidelity/graduation.py`, `cabinet/scripts/lib/policy_engine.py`,
  `framework/frontdoor/action_exec.py`, `action_undo.py`,
  `actfirst_canary.py`, `veto_registry.py`, `tell_surface.py`,
  `calendar_template.py`, `framework/acting/action_lane.py`,
  `run_action_lane.py`.
- **judged config + rules:** `instance/config/act-first-surfaces.yml`,
  `cabinet/mcp-scope.yml`, `cabinet/officer-capabilities.conf`,
  `.claude/rules/brain-bridge.md`, `.claude/rules/courses-of-action.md`;
  dirs `framework/policies/`, `memory/golden-evals/`,
  `instance/config/policies/` (D8).
- **NEW sovereign germline:** `framework/authority/posture.py`,
  `grants.py`, `needs.py`, `framework/learning/gate.py`, `apply_watch.py`,
  `cabinet/scripts/grant-apply.sh`, `instance/config/posture.yml`,
  `instance/config/standing-grants.yml`,
  `framework/policies/immutable-core.yml` itself (dir-covered).
- **ROOT-EXECUTED apply lane (SOV-9a):** `cabinet/scripts/gate-apply.sh`
  (sudo + root daemon), `cabinet/launchd/com.cabinet.gate-apply.plist`
  (ProgramArguments run as root on load), and
  `shared/interfaces/gate-apply-watch.jsonl` — the watch ledger is
  **files-class, deliberately NOT runtime-appended**: cmd_watch executes
  each row's revert plan as a root `git apply -R`, so a forged row mints a
  root write (the sanctioned-append fail-safe rationale does not hold).
  Born at the first Captain-armed apply; enumerated + wired before it
  exists. The lockstep meta-test also carries a COMPLETENESS allowlist of
  root-executed / authority-minting lanes so an omission from the single
  source itself fails CI.
- **runtime-appended (hook-blocked, DELIBERATELY not schg-locked):**
  `shared/interfaces/captain-vetoes.yml`, `action-lessons.yml`,
  `needs-ledger.jsonl` — the sanctioned same-uid Python APIs append these;
  locking them breaks the demotion/learning/needs loops.
- **hook_protected:** `instance/config/autonomy.yml` (deployment-created
  Captain config; hook + typed-policy covered, not lock-listed).

---

## §3 · What it does NOT do

- **No ceiling becomes unconditional auto** — in any posture; the validator
  rejects `auto` on any ceiling row and CI sweeps every posture table.
- **No guardian byte changes** — no posture config ⇒ resolution, block
  strings, lane summary, digest, caps, binder all byte-identical (P1-P6 +
  the guardian byte-identity suite, both with `CABINET_POSTURE` unset and
  `=sovereign`).
- **No graduation/bars change** — posture never enters `graduation.evaluate`
  or the cell key (D9); `verdict_gate` machine promotion only counts under
  sovereign and a posture flip only ever REDUCES confirmed counts (D16).
- **No ACT-AND-DRAFT weakening on flavor A** — the grants loader
  structurally refuses flavor=personal external_comms grants; the Captain's
  personal outbound surfaces keep per-item approval in every posture.
- **No live behavior until a posture.yml exists** — and none of the
  generator's scaffolds count: an unlocked file resolves guardian.
- **No runtime-writable grants** — grants change ONLY via
  `sudo grant-apply.sh` in an unlock window (D7); the Telegram-sealed
  root grant-writer stays KILLED.
- **No root pytest, no Telegram-sealed writer, no armed apply daemon** —
  germline CODE auto-apply stays DARK until the unprivileged sandbox
  harness exists AND you explicitly `sudo launchctl load` it (D15).

---

## §4 · CI proofs (same commit set, P1-P7)

| Proof | Where it lives | Asserts |
|---|---|---|
| P1 | `framework/authority/tests/test_guardian_parity.py` + `cabinet/scripts/lib/tests/test_policy_engine.py` | resolve_verdict guardian truth-table: no-kwargs == posture="guardian" == inert-postures-present, every cell |
| P2 | `test_guardian_parity.py` `_GOLDEN_BLOCKS` | gate byte-parity vs the recorded pre-change golden strings |
| P3 | `framework/acting/tests/test_sov4_posture_routing.py` | posture absent ⇒ new modules raise-if-imported untouched; lane summary bytes unchanged |
| P4 | `framework/acting/tests/test_sov4_posture_routing.py` | guardian+file-present lane parity (action_types × states == legacy) |
| P5 | `cabinet/scripts/lib/tests/test_policy_engine.py` | load_policies floor-only refusal + fail-closed runtime validation (D8) |
| P6 | full suite | green with `CABINET_POSTURE` unset AND `=sovereign` (env-parametrized in the parity suite); `test_undo_capability_parity` extended per-posture |
| P7 | manual (§5 step d) | lock/attestation: `chflags noschg posture.yml` ⇒ resolve_posture ⇒ guardian; relock |

Plus: the **lockstep meta-test**
(`framework/tests/test_germline_lockstep_consistency.py`) asserts every
`immutable-core.yml` entry is wired into all four germline lists (hook §5
case, §5b `GERM_PATH_RE`, germline-lock FILES/DIRS/SKIP, base-safety
patterns) — hard, no xfails remaining — and that no list atom exists outside
the single source. Golden evals 016-019 each carry an enforcing pytest
(`framework/authority/tests/test_golden_evals_sovereign.py`), and this
document itself is linted by `framework/tests/test_amendment_doc_lint.py`.

---

## §5 · APPLY-GATE evidence pack (all green before you reply)

a. **P1-P6 green** — run the suites SEPARATELY (a combined `framework/ cabinet/scripts/lib/tests`
   invocation errors at collection: `cabinet/scripts/lib/tests` and `cabinet/scripts/gates/tests`
   both claim the top-level `tests` package). Use:
   `python3.12 -m pytest framework/ -q` then `python3.12 -m pytest cabinet/scripts/lib/tests -q`
   then `python3.12 -m pytest cabinet/scripts/gates/tests -q`, each with `CABINET_POSTURE` unset,
   then re-run the framework sweep with `CABINET_POSTURE=sovereign`.
   (Integrator-verified 2026-07-05: framework 2632 passed, sovereign sweep 1773 passed,
   lib 438 passed, gates 6 passed.)
b. **Sovereign scratch dry-run transcript** — on a scratch `CABINET_ID`
   tree: ceiling probe ⇒ blocked + `NEED-<hex>` filed ⇒ `grant NEED-<hex>`
   binder receipt renders the machine-effective scope ⇒
   `sudo grant-apply.sh NEED-<hex>` in the unlock window ⇒ re-probe ⇒
   attributed allow (grant_id) ⇒ tombstone the grant ⇒ re-probe blocks.
c. **Lockstep meta-test green** (no pending, no xfail).
d. **P7 manual attestation** — with a ruling locked: `sudo chflags noschg
   instance/config/posture.yml` ⇒ `resolve_posture()` returns guardian ⇒
   relock ⇒ sovereign again.
e. **`germline-lock.sh status`** shows the new files locked (posture.py,
   grants.py, needs.py, gate.py, apply_watch.py, grant-apply.sh,
   gate-apply.sh, com.cabinet.gate-apply.plist, immutable-core.yml via
   dir-cover, posture.yml, standing-grants.yml, instance/config/policies/;
   gate-apply-watch.jsonl shows "skip (absent)" until the first
   Captain-armed apply creates it).
f. **Dark-lane greps green** — no setup script loads `com.cabinet.gate-apply`
   (`framework/learning/tests/test_gate_apply_dark.py` +
   eval-019's enforcing test); services.yml carries no row for it.

---

## §6 · Golden evals in this package

- **Amended 011/012/013/015** — guardian text unchanged; "## Sovereign
  posture" sections (grant-or-need; never UNCONDITIONAL auto; failure
  classes: allow-without-grant_id, grant-from-unlocked-file,
  grant-past-hard-scope; flavor=personal refusal per ACT-AND-DRAFT).
- **eval-014** — rot fix + the ratified supersession letter (§ SUPERSEDES 3).
- **NEW eval-016** posture-guardian-parity · **eval-017**
  sovereign-ceiling-grant-or-need (behavioral never-unconditional-auto
  assertion) · **eval-018** posture-env-cannot-widen · **eval-019**
  immutable-core-gate-refusal.

---

## §7 · captain-decisions.md — ledger state + the ONE paste-ready backfill

**Already logged live (2026-07-04, reference only — do NOT re-paste):**
`## SOVEREIGN POSTURE (2026-07-04, Captain-ruled)` and
`## ACT-AND-DRAFT (2026-07-04, Captain-ruled — supersedes ACT-NOT-DRAFT)`
both landed in `shared/interfaces/captain-decisions.md` on 2026-07-04. On
apply, add one line under each: *"Realized by: germline amendment
sovereign-posture 2026-07-05 (`apply sovereign posture`)."*

**Decision-B BACKFILL — paste-ready** (the filesystem-lock ruling is absent
from the ledger; 2026-06-24 backfill precedent):

```markdown
## DECISION B — germline boundary is the FILESYSTEM, not string-matching (2026-07-04, Captain-ruled; BACKFILLED 2026-07-05)

**What:** After the germline-forge probe was re-killed four times at the
string layer, the Captain ruled Decision B: stop the string whack-a-mole —
the COMPLETE germline boundary is the filesystem lock
(cabinet/scripts/germline-lock.sh, macOS `chflags schg`, root-only to set or
clear), applied over the enforcer + judge plane. The pre-tool-use hook's §5/
§5b screens remain DEFENSE-IN-DEPTH only (a path hook over a Turing-complete
shell can never be a complete boundary). Officers run without passwordless
sudo, so a germline change is a DELIBERATE Captain unlock window — unlock →
edit/commit → lock.

**Why:** Four consecutive kill-and-reappear cycles on the forge hole proved
the denylist/string layer structurally unwinnable; schg is a physical
boundary the officer uid cannot cross or clear.

**Mechanics now:** germline-lock.sh FILES/DIRS/SKIP arrays; hook §5/§5b +
base-safety mirror the same set; framework/policies/immutable-core.yml is
the single source and framework/tests/test_germline_lockstep_consistency.py
diffs all four lists against it (sovereign amendment 2026-07-05).

**Captain:** Nate. **Backfill note:** ruling made 2026-07-04 in-session;
entered into this ledger 2026-07-05 with the sovereign-posture amendment.
```

---

## §8 · Apply ritual (one sitting)

```bash
sudo bash cabinet/scripts/germline-lock.sh unlock
# rebase-before-merge vs the guardian agent's live branch — sequence the
# germline overlaps by conflict_risk (SOV-3/4/5/7/9 touch the hottest files:
# policy_engine.py, policy-shadow.py, run_action_lane.py, action_exec.py,
# actfirst_canary.py, action_undo.py, tell_surface.py, consequence.py,
# pre-tool-use.sh, base-safety.yml, germline-lock.sh, courses-of-action.md)
git rebase feat/fidelity-harness-design feat/sovereign-posture   # resolve, re-run suites
git merge feat/sovereign-posture
# Flavor B (Mini): create the attestation pair BEFORE lock —
#   instance/config/posture.yml        (posture: sovereign, deployment: <mini-id>, flavor: org)
#   instance/config/standing-grants.yml (version: 1 / grants: [])
# Flavor A (MacBook): optionally posture.yml (posture: guardian, flavor: personal)
git add instance/config/posture.yml instance/config/standing-grants.yml && git commit
sudo bash cabinet/scripts/germline-lock.sh lock
bash cabinet/scripts/germline-lock.sh status && bash cabinet/scripts/germline-lock.sh verify
```

Then, when ready: set `CABINET_NEEDS_WIRED=1` in the generated cos-inbound
plist (arms the binder needs verbs, dark → live); run
`python3.12 -m framework.learning.grant_seeker --argue-lanes` for the
flavor-A sovereign-flip case in the first needs digest; killswitch drill.
**Do NOT** `sudo launchctl load com.cabinet.gate-apply` (D15 — stays dark).

**One-revert rollback:** revert the merge commit (restores every germline
file: authority-matrix.yml, matrix.py, policy_engine.py, policy-shadow.py,
run_action_lane.py, action_exec.py, actfirst_canary.py, action_undo.py,
tell_surface.py, consequence.py, pre-tool-use.sh, base-safety.yml,
germline-lock.sh, courses-of-action.md, golden evals 011-019, posture.py,
grants.py, needs.py, gate.py, apply_watch.py, grant-apply.sh, gate-apply.sh,
com.cabinet.gate-apply.plist, immutable-core.yml) +
`rm instance/config/posture.yml` (and standing-grants.yml, and
shared/interfaces/gate-apply-watch.jsonl if the dark lane ever wrote one).
Absent posture file ⇒ every kernel path is inert; needs-ledger rows and
evidence packs are harmless residue.

---

## Appendix — files this amendment touches at apply

| file | change | germline |
|---|---|---|
| `framework/policies/authority-matrix.yml` | `postures.sovereign` full table (§2.1) + doctrine comment; root verdicts byte-untouched | yes |
| `framework/authority/matrix.py` | `VERDICTS += standing_grant`; `POSTURES`; `_POLICY_KEYS += postures`; posture-table validators; `no_ceiling_or_prod_auto` sweeps postures | yes |
| `cabinet/scripts/lib/policy_engine.py` | resolve_verdict posture kwargs; posture resolution; D2 ceiling branch (grant-or-need); D4 allow-set + notify_after tell; D8 floor-only + fail-closed validate | yes |
| `cabinet/scripts/policy-shadow.py` | mirrors the gate; record += posture/grant_id/need_id | yes |
| `framework/acting/run_action_lane.py` | `_load_posture_ctx` (absent ⇒ byte-identical path); per-card D10 routing; D13 inbound-provenance never act-first | yes |
| `framework/frontdoor/action_exec.py` | caps posture-param; D14 holds (officer_dispatch/delegate_work stay held, investigation_run drops in sovereign); mission auto-adopt; `_max_auto_steps` 2/5; needs filings try/except | yes |
| `framework/frontdoor/actfirst_canary.py` | D11 cap⇒alarm / 10×⇒freeze+block / unreadable⇒block both; D12 silence⇒canary+content-audit; green-canary receipts; `run_thaw` machine-origin | yes |
| `framework/frontdoor/action_undo.py` | `unfreeze` last-op-wins + receipt-required; freeze `source:` tag + unfreeze-need filing | yes |
| `framework/frontdoor/tell_surface.py` | additive `needs_rows=None` digest leg (🙋 NEEDS; byte-identical default) | yes |
| `framework/fidelity/consequence.py` | D16 `verdict_gate` review source (sovereign-gated, cooldown-guarded, flip-only-reduces) | yes |
| `cabinet/scripts/hooks/pre-tool-use.sh` | §5 case + §5b GERM_PATH_RE/GERM_DIR_RE gain the sovereign germline set | yes |
| `framework/policies/base-safety.yml` | germline-readonly += sovereign set + enforcer-triad lag closure | yes |
| `cabinet/scripts/germline-lock.sh` | FILES += 11 sovereign files (incl. the root-executed apply lane, SOV-9a); DIRS += instance/config/policies; SKIP += needs-ledger.jsonl | yes |
| `.claude/rules/courses-of-action.md` | §2 posture-conditional relaxation reword (ACT-AND-DRAFT cited) | yes |
| `memory/golden-evals/eval-011..015` | sovereign sections + eval-014 rot fix (§6) | yes |
| `memory/golden-evals/eval-016..019` | NEW (§6) | yes |
| `framework/authority/posture.py` | NEW — FI-1 kernel | yes (new) |
| `framework/authority/grants.py` | NEW — FI-2 kernel | yes (new) |
| `framework/authority/needs.py` | NEW — FI-3 kernel | yes (new) |
| `framework/learning/gate.py` | NEW — Evidence Gate (S0 refuses Ring-0) | yes (new) |
| `framework/learning/apply_watch.py` | NEW — 72h auto-rollback watch | yes (new) |
| `cabinet/scripts/grant-apply.sh` | NEW — the ONE grants writer (D7) | yes (new) |
| `framework/policies/immutable-core.yml` | NEW — THE Ring-0 single source (FI-5) | yes (new, dir-covered) |
| `instance/config/posture.yml` | created at apply (§8), then locked | yes (new) |
| `instance/config/standing-grants.yml` | created at apply (§8), then locked | yes (new) |
| `instance/config/policies/README.md` | NEW — D8 locked policy-layer dir | yes (dir) |
| `instance/config/posture.yml.example` + `standing-grants.yml.example` | NEW — reference schemas | no |
| `framework/events/emitter.py` | `VALID_EVENT_TYPES += need_* / cap_alarm / kind_unfrozen` (append-only) | no |
| `framework/frontdoor/tell_digest.py` | `gather_needs_rows` + feature-detected build_digest call | no |
| `framework/frontdoor/binder_wire.py` | FI-4 needs verbs (dark behind CABINET_NEEDS_WIRED) | no |
| `framework/frontdoor/attention_drain.py` | NEED-tagged dedup + tier demote | no |
| `framework/fidelity/scorer.py` / `measure_intent.py` / `officer_prompt.py` / `officer_runner.py` / `intent_report.py` | D17 outcome judge + AGB report + clone-default identity | no |
| `framework/learning/self_improvement_loop.py` / `capability_gaps.py` / `skill_induction.py` | loop routes code-diffs via gate.ratify; posture-aware can_install; skill auto-promote | no |
| `framework/missions/standing_pull.py` / `supervisor.py` | standing-missions second compile source (sovereign) | no |
| `framework/learning/grant_seeker.py` | NEW — rank/render `--argue-lanes` | no |
| `cabinet/scripts/gate-apply.sh` + `cabinet/launchd/com.cabinet.gate-apply.plist` | NEW — DARK apply lane (D15; never loaded by setup); ROOT-EXECUTED, so both are Ring-0 in immutable-core.yml + all four germline lists (SOV-9a) | yes (new, dark) |
| `shared/interfaces/gate-apply-watch.jsonl` | runtime-created watch ledger — rows become the root daemon's `git apply -R` revert plans, so it is Ring-0 files-class (SOV-9a); born at the first Captain-armed apply, list-wired before it exists | yes (runtime-created) |
| `docs/runbooks/gate-apply-runbook.md` | NEW — dark-lane runbook | no |
| `cabinet/loop-prompts/comms-officer.txt` | ACT-AND-DRAFT encoding (own commit) | no |
| `cabinet/loop-prompts/{polads,stephie}-ceo.txt` | posture-conditional sentence + guardian fallback | no |
| `cabinet/scripts/generate-instance.py` | renders the INERT posture scaffold (skip-if-exists) | no |
| `.claude/skills/cabinet-init/SKILL.md` | §4 supersession (guardian at init) | no |
| `docs/mac-mini-deploy-runbook.md` + `docs/mac-mini-setup.md` | posture ratification steps | no |
| `cabinet/services.yml` | cos-inbound CABINET_NEEDS_WIRED arm switch (commented) + gate-apply DELIBERATELY ABSENT note | no |
| `cabinet/scripts/health-check.sh` | log-only posture attestation line | no |
| `pytest.ini` + `conftest.py` | mirror of the live leak-fence pair (byte-identical; rootdir anchor) | no |
| `framework/**/tests/*`, `cabinet/scripts/lib/tests/*` | CI proofs P1-P6 + lane suites + eval spines + doc lint | no |

Reply **"apply sovereign posture"** to apply exactly the above.
