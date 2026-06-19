# Authority Matrix + Policy Engine — Design (track A)

> The **POLICY+GATE** face of the unified control loop whose **MEASURE** face is `docs/fidelity-harness-design-2026-06-18.md`; realizes mission `outcome-system-self-001` (typed policy engine shadow→enforcing) by adding the authority-matrix verdict layer on top of the proven legacy floor; formalizes the Captain authority matrix ratified 2026-06-18.

Authored 2026-06-19. Build reference, not a free-reuse claim — every seam below is checked against the live code (file:line cited). Implementation follows per-phase; Corridor `analyzePlan` runs before any code, per house rule. Where a dependency is unbuilt (F2 `graduation.py`, F6 `aggregate.cusum`), this design names it as a **hard gate**, not an aside.

---

## 0. North star + what the review changed

F measures *how well an officer's decision matches Nate's endorsed judgment, per cell*. A turns that measurement into an **enforced policy**: for every officer action, given its `(lane, action_type, risk_class)` and the cell's **confidence state**, decide one of `{auto, auto-with-veto-window, notify-after, propose-only, always-gated}` — and **block** (force propose-only) when below bar or unmeasured.

The matrix is the canonical policy *document* (data the Captain ratifies); the policy engine is the *enforcement seam* (germline code that reads it). They are deliberately separate.

**Fail-safe is the spine.** Until F provides a confidence score for a cell, that cell is `propose_only`. Hard-ceiling classes are `always-gated` regardless of confidence — F can never lift them.

**Eight review findings are resolved inline, each marked `[FIX-n]` where it lands:**

1. **`[FIX-1]` Cell-key / action-type mismatch** (blocker) — the ledger keys cells on the free-text `action` string (`consequence.py` `compute_ratios`, the `key = (actor_id, ev.get("lane"), ev.get("action",""))` line). The gate wants to read by `action_type` enum. **Resolved §3 + §F-prereq:** `action_type` becomes a first-class, validated field on the consequence event, stamped by the *same shared* `classify_action()` the gate uses (one classifier, one source of truth); `compute_ratios`/`graduation.evaluate` key on `(actor, lane, action_type)`. This is a **prerequisite F-side change** (fidelity open-decision #3) that A cannot ship around.
2. **`[FIX-2]` Shadow seam does not exist as described** (blocker) — `policy-shadow.py` imports only `org_runtime.Store` and hand-rolls regex; it never calls `policy_engine`. **Resolved §7 Stage 0 + §A0:** explicit incremental work to make `policy-shadow.py` import `policy_engine`, run `load_policies()`+`evaluate_policy()` for the `authority_matrix` type, and emit the *verdict* (not just allow/block) to `org_events`.
3. **`[FIX-3]` Allow-with-side-effect has no seam** (blocker) — a pre-tool-use subprocess can only signal via exit code + stderr; it cannot set a parent-shell var, so `auto_with_veto_window` would fall through as exit-0 and `queue_draft` would fire immediately. **Resolved §5:** the veto path is **block-then-redirect** (exit 2 with a "queued for veto window" directive), not allow-with-marker. The eval also writes a verdict record to a deterministic path for observability, but **correctness never depends on an allow-side side-effect.**
4. **`[FIX-4]` Lane dimension has no source** (blocker) — `CABINET_LANE` is set nowhere; sessions scope via `--project`/`PROJECT`. **Resolved §3:** `lane` resolves from the existing project/context machinery via one shared `resolve_lane()` used by `classify_action`, `read_cell_state`, AND F's `compute_ratios`; `start-officer.sh` exports `CABINET_LANE` derived from `--project`/active context, documented as load-bearing.
5. **`[FIX-5]` Thermostat described, not concrete** (major) — `graduation.py` (F2) and `aggregate.cusum` (F6) don't exist; friction/gate_decision events have no schema/emitter. **Resolved §4:** thermostat is net-new build, hard-gated AFTER F2/F6; the friction + gate_decision event types are defined in the consequence schema with emitters before triggers 4–5 are claimed; the sticky Redis cooldown key + demotion module are specified and unit-tested.
6. **`[FIX-6]` Deploy ceiling vs carve-out contradiction + unreachable auto path** (major) — `production` is a never-lift frozenset member, yet the deploy row resolved to auto; and the live `*"vercel deploy"*` block (unconditional `exit 2`) shadows any auto-deploy. **Resolved §6 + §reconciliation:** prod stays always-gated in BOTH layers; the low-risk carve-out produces a **preview/staging auto target only, never prod**; the legacy vercel-deploy block is reconciled (it remains the prod floor and *wins*; the carve-out drives non-prod deploy commands that the legacy block does not match). CI test asserts no deploy verdict can resolve to auto with a prod target.
7. **`[FIX-7]` Hard-ceiling coverage incomplete** (major) — matrix dropped `secrets`, `network_write`, `credentials_grant`; the proposed "⊇ mappable" CI test was self-fulfilling. **Resolved §1 + §reconciliation:** all six frozenset members get explicit action_types + always_gated risk_classes; `classify_action` positively classifies network-write MCP calls and credential/oauth flows; the CI test asserts coverage of **all six** members, not a "mappable" subset.
8. **`[FIX-8]` Mission-scope conflation + germline gaps** (minor×2) — A overclaimed *being* `outcome-system-self-001` (which is the legacy-engine flip); and new judge modules co-located in `lib/` would be officer-editable (the germline case suffix-anchors `policy_engine.py` exactly, not the lib dir). **Resolved §7 + §8:** rollout is split into two independent flip flags (legacy engine first, authority_matrix second, each with its own parity corpus + revert flag); every new judge module is added to the germline case by name in the same commit + a hook-regression test asserts read-only.

---

## 1. The unified control loop (A's place in it)

```
  F scorer        F emitter          A: gate (policy_engine)        A: authority-matrix.yml
  measure   →     record       →     GATE                      ←    policy (this matrix, as data)
  judgment        consequence        (block / verdict)
                  ledger (keyed                                          │
                  by action_type)                                       │
                     ↑                                                   │
                     └────────── thermostat: bad call / drift / friction ┘
                                 demotes a cell + files a finding
```

`measure (F) → stamp action_type (shared classifier) → read state (§3) → gate (§2) → act / block-redirect (§5,§6) → record (consequence, keyed by action_type) → thermostat (§4) → measure.`

A reads F's precomputed per-cell graduation **state** (never judges in the hot path) plus the matrix data, returns a verdict, and on bad outcomes feeds the thermostat that demotes cells.

---

## 2. Nate's authority matrix — formalized exactly (matrix-as-data)

Risk classes mapped one-to-one from Nate's spec to matrix rows. Each cell = `(risk_class × confidence_state) → verdict`. Confidence states come from F's `graduation.py`: `unmeasured | propose_only | eligible | graduated | demote`.

The five spec risk classes are **augmented `[FIX-7]`** with three execution-surface ceiling classes so the matrix covers every member of `HARD_CEILING_TOUCHES`:

| risk_class | unmeasured / demote | propose_only | eligible | graduated | HARD CEILING (frozenset member) |
|---|---|---|---|---|---|
| **reversible** | propose-only | propose-only | propose-only | **auto** | no |
| **internal_comms** (real people) | propose-only | propose-only | propose-only | **auto-with-veto-window** + notify-after | no |
| **external_comms** (real people) | **always-gated** | always-gated | always-gated | always-gated | **YES** (`external_comms`) — DRAFTS only via `queue_draft` |
| **deploy_nonprod** (preview/staging) | propose-only | propose-only | low-risk→**auto** / else gated | low-risk→**auto** / else gated | no (prod is a separate row) |
| **deploy_prod** | **always-gated** | always-gated | always-gated | always-gated | **YES** (`production`) — never auto, no carve-out |
| **spend** (real money) | **always-gated** | always-gated | always-gated | always-gated | **YES** (`spending`) |
| **secrets** (read/write a secret) | **always-gated** | always-gated | always-gated | always-gated | **YES** (`secrets`) |
| **network_write** (MCP POST/PUT/DELETE to live) | **always-gated** | always-gated | always-gated | always-gated | **YES** (`network_write`) |
| **credentials_grant** (oauth/token grant) | **always-gated** | always-gated | always-gated | always-gated | **YES** (`credentials_grant`) |

Note the **`[FIX-6]` deploy split**: `deploy` is two rows. `deploy_nonprod` (preview/staging) is the *only* deploy row that can carve out to auto, and only for low-risk diffs on eligible+ cells. `deploy_prod` is always-gated, mapping onto the `production` frozenset member — there is **no** prod auto path.

**Verdict semantics:**
- `auto` — officer acts, no human in loop. Emits a consequence event (with `action_type`) for later review.
- `auto-with-veto-window` — the send is **block-then-redirected** into a deferred-send queue for N minutes; Nate can kill it from the Telegram notification; auto-fires on TTL expiry. Human comms are not truly reversible, so this is the unattended posture for internal comms — never fire-and-forget. **`[FIX-3]`: the gate exits 2 with a redirect directive; it does NOT allow-and-mark.**
- `notify-after` — officer acts, then DMs Nate "did X" (no decision asked). Stacks with `auto-with-veto-window` (the notification *is* the veto handle).
- `propose-only` — officer drafts a course-of-action card; nothing happens without Captain approval. The fail-safe default.
- `always-gated` — hard ceiling; never auto regardless of confidence. For `external_comms` the only path is `queue_draft`; for `spend`/`deploy_prod`/`secrets`/`network_write`/`credentials_grant` there is no auto path at all.

**Mapping each spec line precisely:**
1. **REVERSIBLE → unattended once a cell proves out** = `graduated → auto`; below = propose-only.
2. **INTERNAL comms → unattended WHEN PROVEN but notify; gated when low-confidence; DEFERRED-SEND veto window** = `graduated → auto-with-veto-window + notify-after`; `eligible/below → propose-only`.
3. **EXTERNAL comms → ALWAYS human-gated, clone DRAFTS** = `always-gated`, only `queue_draft`.
4. **PROD deploys → unattended for LOW-RISK only (mechanical classifier)** — interpreted per `[FIX-6]` as the **non-prod low-risk carve-out**: `deploy_nonprod` low-risk + cell `eligible`+ → auto; prod itself stays always-gated. The carve-out narrows nothing in the frozenset.
5. **REAL MONEY → always human-gated** = `spend` = `always-gated`.
6. **THERMOSTAT** = demotion engine (§4) flips any cell's state to `demote` → row collapses to propose-only/gated + files a finding.

---

## Component 1 — `authority-matrix.yml` (the matrix as DATA)

**Purpose.** The canonical, Captain-readable policy document. Risk-class rows × confidence-state columns → verdict. Lives in the 3-layer policy stack so framework ships the safe floor and instances tune within it.

**Where** (per Ground-1 `load_policies()` order framework → preset → instance, later layer wins by name):
- `framework/policies/authority-matrix.yml` — the **floor**: all nine risk classes, hard ceilings hardcoded, every cell defaults conservative. Germline (read-only to officers/loops).
- `presets/<active>/policies/authority-matrix.yml` — preset may *narrow* (never widen autonomy) — e.g. a `personal` preset disabling `deploy_nonprod` entirely.
- `instance/config/policies/authority-matrix.yml` — instance lane→risk-class bindings + per-cell bar overrides within the floor.

Merged by name via the existing `load_policies()` — zero new load machinery, because the matrix is one entry of a new typed policy (§Component 2).

**Interface (data shape):**
```yaml
version: 1
policies:
  - name: authority-matrix
    type: authority_matrix          # NEW policy type (Component 2)
    message: "Below the autonomy bar for this (lane × action-type) — proposing instead."
    # action_type → risk_class. action_type is the ENUM that compute_ratios now keys on [FIX-1].
    risk_classes:
      reversible:        { action_types: [task_status_move, board_status, label, tier2_note, draft_only, local_edit] }
      internal_comms:    { action_types: [internal_message, internal_email] }
      external_comms:    { action_types: [external_message, external_email] }      # HARD CEILING: external_comms
      deploy_nonprod:    { action_types: [vercel_deploy_preview, git_push_nonmain] }
      deploy_prod:       { action_types: [vercel_deploy_prod, git_push_main] }      # HARD CEILING: production
      spend:             { action_types: [purchase, provision_paid, billing] }       # HARD CEILING: spending
      secrets:           { action_types: [secret_read, secret_write, env_write] }    # HARD CEILING: secrets
      network_write:     { action_types: [mcp_post, mcp_put, mcp_delete] }           # HARD CEILING: network_write
      credentials_grant: { action_types: [oauth_grant, token_grant] }               # HARD CEILING: credentials_grant
    # MUST cover every member of HARD_CEILING_TOUCHES (CI-asserted, §test plan) [FIX-7].
    hard_ceiling: [external_comms, deploy_prod, spend, secrets, network_write, credentials_grant]
    # map each hard_ceiling risk_class → the frozenset member it satisfies (used by the coverage test)
    ceiling_frozenset_map:
      external_comms: external_comms
      deploy_prod: production
      spend: spending
      secrets: secrets
      network_write: network_write
      credentials_grant: credentials_grant
    # verdict table: risk_class → { confidence_state → verdict }
    verdicts:
      reversible:
        graduated: auto
        eligible: propose_only
        propose_only: propose_only
        unmeasured: propose_only
        demote: propose_only
      internal_comms:
        graduated: auto_with_veto_window     # + notify_after implied
        eligible: propose_only
        propose_only: propose_only
        unmeasured: propose_only
        demote: propose_only
      deploy_nonprod:
        graduated: classifier                # → low-risk auto / else gated (NON-PROD target only)
        eligible: classifier
        propose_only: propose_only
        unmeasured: propose_only
        demote: propose_only
      external_comms:    { "*": always_gated }
      deploy_prod:       { "*": always_gated }
      spend:             { "*": always_gated }
      secrets:           { "*": always_gated }
      network_write:     { "*": always_gated }
      credentials_grant: { "*": always_gated }
    veto_window_minutes: 7                    # internal_comms deferred-send delay
    # mechanical low-risk deploy classifier inputs (Component 6)
    deploy:
      safe_globs: ["**/*.md","docs/**","**/__tests__/**","**/*.test.*","**/*.spec.*","tsconfig.json",".eslintrc*"]
      high_risk_globs:
        - "**/migrations/*.sql"
        - "**/schema*.sql"
        - "**/*_schema.*"
        - "auth/**"
        - "authentication/**"
        - "**/jwt/*"
        - "**/oauth*"
        - "payment*"
        - "stripe/**"
        - "billing/**"
        - "**/checkout*"
        - "**/subscription*"
        - "neon.json"
        - "**/neon/**"
        - "vercel.json"
        - ".vercelignore"
        - ".env*"
        - "policies/**"
        - "framework/schemas-base.sql"
        - "cabinet/init.sql"
        - "presets/*/schemas.sql"
    # per decision-type bar override (irreversible types carry higher bar). F2 imports these — it does NOT hardcode its own [FIX-1 reconcile].
    bars:
      default:        { match_rate: 0.85, samples: 20, max_divergent_last10: 1, recency_clean_days: 14 }
      internal_comms: { match_rate: 0.90, samples: 30, max_divergent_last10: 0, recency_clean_days: 21 }
      deploy_nonprod: { match_rate: 0.95, samples: 30, max_divergent_last10: 0, recency_clean_days: 21 }
    cooldown_days:
      default: 14
      internal_comms: 21
      deploy_nonprod: 21
```

**Depends-on.** `load_policies()` (Ground 1); F's `graduation.evaluate(cell)` (§3); `HARD_CEILING_TOUCHES` (Ground 2, reconciled below).

**Isolation.** Pure data + the loader. The single source of truth for verdicts, bars, cooldowns, and deploy globs; engine, gate, thermostat, and F2 all read it.

- **T5 BUILT (2026-06-19) — matrix-as-DATA shipped + a fail-closed loader/validator.** `framework/policies/authority-matrix.yml` is the framework floor: all nine risk classes (the 5 spec classes + the 3 ceiling classes), the `action_type → risk_class` map covering every shared-classifier `ACTION_TYPES` member except the propose-defaulting `AMBIGUOUS` backstop, `hard_ceiling` + `ceiling_frozenset_map` mapping all six `HARD_CEILING_TOUCHES` members 1:1, the verdict table (hard-ceiling rows are `{"*": always_gated}`; `reversible.graduated → auto`; `internal_comms.graduated → auto_with_veto_window`; `deploy_nonprod` eligible+ → `classifier`), `veto_window_minutes: 7`, `deploy.safe_globs`/`high_risk_globs`, per-decision-type `bars`, and `cooldown_days`. The loader/validator is a NEW judge module `framework/authority/matrix.py` (`load_matrix`/`validate_matrix`/`matrix_policy`/`ceiling_members`/`no_ceiling_or_prod_auto`) — hand-rolled (no `jsonschema` in py3.9.6, mirrors `consequence.py`), `additionalProperties:false` at every level, `yaml.safe_load` only, fail-closed: any unknown/missing/extra key, off-enum action_type or verdict, incomplete ceiling map, or **any prod/ceiling cell == auto** RAISES `MatrixValidationError`. Cross-checks against the TWO sources of truth: `framework.authority.classifier.ACTION_TYPES` and `framework.learning.capability_gaps.HARD_CEILING_TOUCHES`. SHADOW-ONLY: pure data + loader, no gate behavior, no exit codes (T5 does not wire `_eval_authority_matrix`; that is a later task). Germline-registered as the suffix-anchored exact file `framework/authority/matrix.py` in `pre-tool-use.sh` Section 5 in the same commit (its tests under `framework/authority/tests/` stay editable). Tests: `framework/authority/tests/test_matrix.py` (43) + `framework/authority/tests/test_matrix_ci.py` (4 — the two CI invariants asserted on the SHIPPED floor + the legacy loader ingesting the new YAML) + germline regression probes G18b/G18c/FP8b.

---

## Component 2 — `authority_matrix` policy type (the GATE)

**Purpose.** A new typed-engine policy type that turns matrix data into a per-action verdict and **blocks** (forces propose-only or redirects to veto) below bar. Additive on top of the legacy floor — A does **not** migrate the legacy regex rules.

**Attach point (exact, Ground 1).** `policy_engine.py` is a built library not yet called from the live hook. Wire it by inserting a dispatch in `pre-tool-use.sh` **between Section 2 (spending-limits) and Section 3 (prohibitions)** — after kill-switch + spend cap, before the legacy regex prohibitions. The legacy `*"vercel deploy"*`/SQL-verb block in Section 3a stays as the independent prod floor (see `[FIX-6]` reconciliation). Shadow stays in Section 0 (parity proof, §7).

**Policy-type extension (the 5-step pattern, Ground 1):**
1. Add `"authority_matrix"` to `policy.schema.json` enum.
2. Add an `allOf` validation block requiring `risk_classes`, `verdicts`, `hard_ceiling`, `ceiling_frozenset_map`.
3. Implement `_eval_authority_matrix(policy, tool_name, tool_input)` in `policy_engine.py`.
4. Add the `elif` dispatch branch in `evaluate_policy()`.
5. Ship the YAML floor (§Component 1).

**Interface (the eval, matching Ground-1 `evaluate_policy(policy, tool_name, tool_input, officer) -> str|None`):**
```python
def _eval_authority_matrix(policy: dict, tool_name: str, tool_input: dict, officer: str) -> str | None:
    lane        = resolve_lane()                                  # [FIX-4] one shared resolver
    action_type = classify_action(tool_name, tool_input)         # [FIX-1] SHARED classifier
    risk_class  = risk_of(action_type, policy["risk_classes"])    # enum → risk-class

    # 2. HARD CEILING short-circuit (fail-closed, ignores confidence) [FIX-7]
    if risk_class in policy["hard_ceiling"]:
        if risk_class == "external_comms":
            return f"GATED (hard ceiling: external_comms) — draft via queue_draft, never auto."
        return f"GATED (hard ceiling: {risk_class}) — propose to Captain; no auto path."

    # 3. read F's PRECOMPUTED cell state (never judges in hot path); fail-safe → unmeasured [FIX-1 key]
    state = read_cell_state(officer, lane, action_type)
    verdict = resolve_verdict(policy["verdicts"], risk_class, state)  # "*" wildcard supported

    # 4. deploy_nonprod classifier branch (Component 6) — NON-PROD target only [FIX-6]
    if verdict == "classifier":
        verdict = classify_deploy(tool_input, policy["deploy"])  # → "auto" | "propose_only"

    # 5. internal_comms auto → BLOCK-then-REDIRECT into the veto queue [FIX-3]
    if verdict == "auto_with_veto_window":
        enqueue_veto(officer, lane, action_type, tool_input, policy["veto_window_minutes"])
        return (f"QUEUED FOR VETO WINDOW ({policy['veto_window_minutes']}m) — internal_comms. "
                f"Do NOT call queue_draft directly; the deferred-send scan will send unless Nate kills it.")

    # 6. block iff verdict forces propose-only / gated
    if verdict in ("propose_only", "always_gated"):
        return f"PROPOSE-ONLY ({risk_class}, confidence={state}) — {policy['message']}"

    # auto / classifier→auto verdicts → allow (None). Write a verdict record for observability
    # ONLY (not load-bearing) [FIX-3].
    _write_verdict_record(officer, lane, action_type, verdict)
    return None
```

**Decision contract & exit codes (Ground 1).** Engine reads `{tool_name, tool_input}` from stdin; on a block/redirect match prints to stderr + `sys.exit(2)` (Claude Code interprets exit-2 as BLOCK). Fail-open on malformed JSON / load exception (`sys.exit(0)`) — but the authority_matrix eval itself is **fail-closed on missing confidence**: an unreachable/absent cell state resolves to `unmeasured` → propose-only (a *block*, not an allow). Fail-open-on-crash applies only to the harness plumbing; the policy semantics are fail-safe.

**`[FIX-3]` — why veto is block-then-redirect, not allow-with-marker.** A pre-tool-use subprocess can only signal the parent via exit code + stderr; it cannot mutate the officer's shell env, and there is no reliable allow-side side-effect channel into the parent. So an `auto_with_veto_window` verdict cannot "allow `queue_draft` but secretly delay it" — if the eval returned exit 0, `queue_draft` would fire immediately with no delay (fail-OPEN on the one irreversible path the window exists to protect). Therefore: the eval **blocks** the direct `queue_draft` call (exit 2) and **enqueues** the payload into the veto stream itself; the deferred-send scan (§5) performs the actual send via the approved backend on TTL expiry. The `_write_verdict_record` to `/tmp/cabinet-authority/<officer>-<pid>.verdict` (or Redis `cabinet:authority:last-verdict:<officer>` short-TTL) exists for the post-hook/observability only and **never gates correctness**.

**`classify_action(tool_name, tool_input)` — deterministic, SHARED `[FIX-1]`.** This is the single canonical mapping from a raw tool call to an `action_type` enum, used by BOTH the gate and the consequence emitter (so the ledger and the verdict table agree). Rules:
- `Bash` with `git push ... main|master` → `git_push_main` (deploy_prod); other branch push → `git_push_nonmain` (deploy_nonprod).
- `Bash`/MCP with `vercel deploy`/`vercel --prod` → `vercel_deploy_prod`; `vercel ... --target preview` / preview deploy → `vercel_deploy_preview`.
- brain MCP `queue_draft` to external recipient → `external_message`; to internal recipient → `internal_message` (audience from recipient domain vs the internal directory).
- Monday/board MCP status writes → `board_status` / `task_status_move`.
- spend signals (purchase/provision_paid/billing keywords; Neon/Vercel **paid** provisioning) → `provision_paid` / `purchase` / `billing` (spend).
- secret/env access (read/write a `.env`, secret-store key) → `secret_read` / `secret_write` / `env_write` (secrets) `[FIX-7]`.
- live-mutating MCP HTTP verbs (POST/PUT/DELETE to a non-local endpoint) → `mcp_post`/`mcp_put`/`mcp_delete` (network_write) `[FIX-7]`.
- oauth / token grant flows → `oauth_grant` / `token_grant` (credentials_grant) `[FIX-7]`.
- everything else reversible/local/no-egress → `local_edit` (reversible).

**FAIL-SAFE summary.** (a) unknown/absent confidence → propose-only; (b) any hard-ceiling class → always-gated regardless of confidence; (c) **unknown action-type → propose-only unless it positively matches a clearly-local/no-egress signal**, in which case `local_edit`/reversible — ambiguous defaults toward human-in-loop, mirroring `classifier.ambiguous_defaults_to: propose`. Network-write and credential flows are *positively* classified into always-gated, never left to the ambiguous backstop `[FIX-7]`.

**Germline (Ground 1 + `[FIX-8]`).** `framework/policies/*` (covers `authority-matrix.yml`) and the exact file `cabinet/scripts/lib/policy_engine.py` are already germline in `pre-tool-use.sh` Section 5. The new judge modules (T1 built `framework/authority/classifier.py` + `framework/authority/lane.py`; later `authority_thermostat.py`, `authority_veto.py`, `deploy_classifier.py` under the same `framework/authority/` dir) are added to the germline case **by name in the same commit that creates them** — see §8.

**Depends-on.** Component 1; Component 3; `load_policies`/`evaluate_policy` (Ground 1); the shared `classify_action`/`resolve_lane`.

---

## Component 3 — Confidence-input interface + cell-key fix (consumes F)

**Purpose.** The clean read-only seam from A into F's per-cell graduation state. A never recomputes confidence — it reads what F precomputed.

**`[FIX-1]` PREREQUISITE — `action_type` is a first-class consequence field.** Today `compute_ratios` keys cells on `(actor_id, lane, ev.get("action",""))` where `action` is a free-text string emitted by officers via the brain-bridge `log_reasoning`/`record_run` path (e.g. `"queue_draft to Sean"`). The matrix indexes verdicts on the `action_type` **enum**, so `graduation.evaluate((officer, lane, action_type))` would forever hit an empty/unmeasured cell — permanently propose-only, autonomy never lights up. Resolution (an F-side change that A depends on, resolving fidelity open-decision #3):
1. Add an `action_type` enum field to `framework/schemas/consequence-event.schema.json` (`additionalProperties:false` discipline preserved; hand-rolled validator updated).
2. The consequence **emitter** stamps `action_type` via the *same* shared `classify_action()` the gate uses — one classifier, one source of truth. The brain-bridge governance hooks pass the raw tool call through `classify_action()` at emit time.
3. `compute_ratios` keys on `(actor_id, lane, action_type)` (raw free-text `action` retained as a descriptive field, not the key).
4. `graduation.evaluate` aggregates by `action_type`.

Until this lands, A0 ships shadow-only with everything propose-only (the only honest landing) — no cell can graduate against a dimension F does not yet emit.

**Interface (single function, the only F→A coupling):**
```python
# framework/fidelity/graduation.py  (F2 — built by F; A consumes it)
def evaluate(cell: tuple[str, str | None, str]) -> dict:
    """cell = (officer_actor_id, lane, action_type).
    Returns {state, evidence}, state ∈ {unmeasured, propose_only, eligible, graduated, demote}."""
```
A wraps it with a fail-safe reader and the shared lane resolver `[FIX-4]`:
```python
def resolve_lane() -> str | None:
    # ONE source of truth for lane. start-officer.sh exports CABINET_LANE (derived
    # from --project / active context); fall back to PROJECT, then None [FIX-4].
    return os.environ.get("CABINET_LANE") or os.environ.get("PROJECT") or None

def read_cell_state(officer, lane, action_type) -> str:
    try:
        return graduation.evaluate((f"officer:{officer}", lane, action_type))["state"]
    except Exception:
        return "unmeasured"          # F absent/unreachable → fail-safe (block)
```

**`[FIX-4]` lane wiring.** `start-officer.sh` exports `CABINET_LANE` derived from `--project`/active context and documents it as load-bearing. `classify_action`, `read_cell_state`, AND F's `compute_ratios` all resolve lane through `resolve_lane()` (or the equivalent on the F side) so the cell tuple is identical on both sides. Without this, every cell collapses to `(officer, None, action_type)`, voiding per-lane bars and the instance lane→risk-class bindings.

- **T4 BUILT (2026-06-19) — CABINET_LANE exported by BOTH officer-start scripts.** `cabinet/scripts/start-officer.sh` (Linux/Docker) appends `CABINET_LANE=$ACTIVE_SLUG` to the per-window `EXPORT_VARS` whenever a slug resolved (pool mode `--project`, or legacy `instance/config/active-project.txt`) — derived from the SAME machinery as `CABINET_ACTIVE_PROJECT` (proven equal by `cabinet/tests/start-officer/test-lane-export.sh` L1b). `cabinet/scripts/start-officer-mac.sh` (Mac native, single-project-per-LaunchAgent, no `--project`) reads `instance/config/active-project.txt`, validates it against the FW-073 slug allowlist (`^[a-z0-9][a-z0-9-]*$`, ≤32 chars — closes a path/shell-injection vector), and `export CABINET_LANE` only on a valid slug. **Fail-safe:** an empty/missing/non-conforming slug means CABINET_LANE is NOT exported (and a stale/poisoned inherited value is scrubbed via `unset` — mirroring the `CABINET_ACTIVE_PROJECT` defensive unset), so `resolve_lane()` falls through to `PROJECT` then `None` → unmeasured cell → propose-only at the gate. Tests: `cabinet/tests/start-officer/test-lane-export.sh` (Linux pool/legacy/poison), `cabinet/scripts/test-mac-dry-run.sh` (Mac active-project.txt present/absent), and `framework/authority/tests/test_classifier.py::TestResolveLane::test_start_officer_exports_the_var_resolve_lane_reads_first` (cross-tie: both scripts export the exact var `resolve_lane()` reads first).

**Propose-only default until F provides scores.** `graduation.evaluate` is the *only* confidence source. While F2 is unbuilt or a cell is unmeasured (`GraduationRatios` rate is `None` because denominator==0 — Ground-2 no-silent-caps invariant), `evaluate` returns `unmeasured` and A blocks to propose-only. **No cell graduates without F.**

**The single reconciled bar (Cabinet ↔ screenpipe).** F's `graduation.py` reads the three `GraduationRatios` (`approval_unchanged_rate`, `outcome_held_rate`, `review_confirmed_rate`) + `sample_count` + clean-streak and applies the bar **defined in `authority-matrix.yml → bars`** — that is the *one* bar, and **F2 imports it from the matrix YAML; it does not hardcode its own** `[FIX-1 reconcile]`. It mirrors screenpipe's 15/90/14 ramp at the floor (`samples ≥ 20`, `match_rate ≥ 0.85`, `recency_clean ≥ 14d`) but is finer: per-(lane × action_type) with irreversible-type overrides (internal_comms 0.90/30/0/21, deploy_nonprod 0.95/30/0/21). Fitness = `outcome_held × review_confirmed` (positive signal), not correction-count (per F design correction #3).

**Depends-on.** F `graduation.evaluate` (F2 — hard gate); `compute_ratios`/`GraduationRatios` (F0, built — now re-keyed); `authority-matrix.yml` bars; shared `resolve_lane`.

---

## Component 4 — Thermostat / demotion (net-new, hard-gated after F2/F6) `[FIX-5]`

**Purpose.** A bad outcome demotes a cell's confidence state toward propose-only and files a finding. Promotion is earned slowly; demotion is **immediate and sticky**. Ramp-down is designed as carefully as ramp-up.

**`[FIX-5]` honest dependency status.** `graduation.py` (F2 — the state machine that returns `demote`) and `aggregate.cusum` (F6 — drift alarm) **do not exist yet**. The thermostat is **net-new build**, sequenced **AFTER F2 + F6 land** as a hard gate, not a "when F2 lands" aside. Triggers 4–5 require new event types that have no emitter today — those are defined here before the triggers are claimed.

**New consequence/event types defined (so triggers 4–5 have a schema + emitter):**
- `review.verdict` enum is today `{confirmed, wrong, unknown}` — a **`friction` signal is NOT in it**. Add a sibling event type `authority.friction` to the event store: `{cell, person, severity, evidence_refs}`, emitted by the friction-capture path (Captain decision needed on source — open-decision #4).
- `authority.gate_decision` event: `{cell, verdict, action_type, killed?}` — emitted by the veto kill handler (§5) and by the gate's allow path verdict record, so false-positive-block / kill signals are durable.

**Demotion triggers (any one flips the cell to `demote`):**
1. **Bad live call** — a consequence event lands with `review.verdict == "wrong"` for that cell; `review_confirmed_rate` drops below the cell's bar. *Intrinsic to `graduation.evaluate` once F2 exists.*
2. **Drift spike** — `aggregate.cusum` (F6) fires a drift alarm for the cell. *Hard-gated on F6.*
3. **Divergent cluster** — `≥ 2` divergent in the last 10 scored cases (tighter than the promotion bar's `≤ 1`). *Intrinsic once F2 reads the bar's `max_divergent_last10`.*
4. **Colleague-friction event** — an `authority.friction` event for an internal_comms cell (a recipient reacted badly to an auto-sent or veto-window message). The human-relationship safety valve specific to comms.
5. **False-positive block** — a propose-only proposal the Captain **rejected as unsafe** demotes (the inverse signal — repeated unchanged approvals are a *promotion* signal handled by trigger-1 math, not here).

**Where it runs.** Triggers 1–3 are intrinsic to `graduation.evaluate` (a `wrong` verdict, drift alarm, or divergent cluster naturally produces a sub-bar state). Triggers 4–5 are **explicit**: the thermostat is a function `demotion_scan(cell) -> state` in `authority_thermostat.py`, invoked (a) by F's aggregate run and (b) by the post-tool-use hook when an `authority.friction` or `authority.gate_decision` event is emitted. On demotion it:
- forces `state = demote`, sticky via Redis `cabinet:authority:demoted:<cell>` with the cooldown TTL,
- **files a finding** via the event store (`event_type='authority.cell_demoted'`, payload = cell + trigger + evidence refs) so it surfaces in the next briefing's decision queue (`courses-of-action.md`: `batch-into-next-briefing`, or `ping-now` if it was an active auto cell),
- emits `log_reasoning` + `record_run` per `brain-bridge.md` governance.

**Cooldown to re-promote (anti-flap, concrete).** A demoted cell is `propose_only` for a **cooldown window** (`authority-matrix.yml → cooldown_days`: 14d default, 21d for deploy_nonprod/internal_comms) AND must re-clear the full bar on *fresh* post-demotion samples — the demotion timestamp becomes the new clean-streak floor (dirty pre-demotion samples don't count, mirroring Ground-2 "graduation window restarts on normalized data clean"). The Redis sticky key TTL enforces the floor of the window; re-promotion is never automatic on TTL expiry alone — the cell re-earns `eligible→graduated` exactly like a new cell. **The sticky key + cooldown logic are unit-tested (§test plan); they are not prose.**

**Depends-on.** `compute_ratios`/`read_ledger` (F0, re-keyed); `graduation.evaluate` (F2 — hard gate); `aggregate.cusum` (F6 — hard gate); the event store; Redis; Component 3; the new `authority.friction`/`authority.gate_decision` types.

**Isolation.** `demotion_scan(cell) -> state` + a finding-emit, in `authority_thermostat.py`. Reads the ledger + drift; writes a Redis sticky key + one event. Does not touch the gate's hot path (the gate just reads the resulting state).

---

## Component 5 — Deferred-send veto window (internal comms) `[FIX-3]`

**Purpose.** Make internal-comms "unattended when proven" safe despite irreversibility: a graduated internal message is **queued N minutes**, Nate can kill it from the Telegram notification, else it auto-sends on TTL expiry.

**`[FIX-3]` block-then-redirect, not allow-with-side-effect.** Because a pre-tool-use subprocess has no reliable allow-side side-effect channel into the parent shell, the veto path is implemented as a BLOCK (exit 2) at the gate that **enqueues** the payload, plus an out-of-band scan that sends. The officer's direct `queue_draft` is blocked; the deferred-send scan fires the actual send via the *same* approved `queue_draft` backend on expiry. `queue_draft` itself lives in Nate's external screenpipe brain-mcp (Ground 3), so A hooks the queue/notification layer, not `queue_draft` internals.

**Mechanism:**
1. **Enqueue (in the gate).** On verdict `auto_with_veto_window`, `enqueue_veto()` `XADD`s to Redis stream `cabinet:drafts:veto` with `{officer, recipient, body, action_type, lane, send_at = now + N*60, draft_id}`. N = `authority-matrix.yml → veto_window_minutes` (default 7). The gate returns exit 2 with the "queued for veto window" directive so the officer does not also send.
2. **Notify (the `notify-after` half).** Immediately DM Nate: "Sending to <person> in 7 min — [preview]. Reply `kill <draft_id>` to stop." Threaded per telegram-communication rules.
3. **Kill path.** Nate replies `kill <draft_id>` → CoS handler `XDEL cabinet:drafts:veto <draft_id>` before TTL → emits `authority.gate_decision {killed:true}` (a demotion-signal candidate, §4 trigger-5/4).
4. **Auto-send on expiry.** A resilient scan (post-tool-use sweep or a 60s cron — idempotent, dead-letter on failure, Ground-3 gotcha) reads entries past `send_at`, fires the actual send **via the same approved `queue_draft` backend** (brain-bridge.md: `queue_draft` is the ONLY outbound path), marks `sent:<draft_id>` before `XDEL`.
5. **Crash-safe.** The stream entry survives officer/cabinet restart; the scan is idempotent (the `sent:` marker prevents double-send).

**Reconciliation with brain-bridge.** External comms never reach the veto window — they are `always-gated` and go straight through `queue_draft`'s normal Telegram-approval gate (no auto). Only **internal** comms use deferred-send, and even then bytes egress only through the existing approved-send backend, never a new API path.

**Depends-on.** Redis streams; the Telegram/CoS reply handler; the existing `queue_draft` send backend (external, unchanged); `authority-matrix.yml` N; `authority.gate_decision` event type.

**Isolation.** `authority_veto.py`: a queue producer (called by the gate), a notifier, a kill handler, a scan-sender. ~80 lines. Touches no `queue_draft` internals.

---

## Component 6 — Mechanical low-risk deploy classifier (NON-PROD only) `[FIX-6]`

**Purpose.** The deterministic gate that decides `deploy_nonprod` verdict `classifier` → `auto` (low-risk) vs gated. **Mechanical, not judged.** Per `[FIX-6]`, the classifier's auto output targets **preview/staging only** — it can never produce a prod auto verdict (prod is the separate always-gated `deploy_prod` row).

**Low-risk iff ALL hold (Ground 3):**
1. **Diff scope safe** — every changed file (`git diff origin/main --name-only`) matches a SAFE glob (`authority-matrix.yml → deploy.safe_globs`): `**/*.md`, `docs/**`, `config/**` (non-secret), `**/__tests__/**`, `**/*.test.*`, `**/*.spec.*`, `package.json` version bump only, `tsconfig.json`, `.eslintrc*`.
2. **No high-risk glob touched** — none of `authority-matrix.yml → deploy.high_risk_globs` (migrations/schema/auth/payment/stripe/billing/neon/vercel/.env/policies/base-schemas).
3. **CI green** — GitHub API `/repos/{owner}/{repo}/commits/{ref}/status` → `state == success`.
4. **Preview smoke ready** — Vercel API latest preview deployment `state == READY`.

If all four hold AND the cell is `eligible`+ → `auto` (non-prod). Else → propose-only/gated. Prod beyond preview remains the always-gated `deploy_prod` row.

**Fail-closed.** Any signal unreadable (CI status unknown, preview missing, git diff fails) → **gated**. A missing high-risk glob is the dangerous failure (Ground-3 gotcha) — the glob set is enumerated explicitly in `authority-matrix.yml → deploy.high_risk_globs` so the Captain can extend it; a new risky domain (`iam/*`, etc.) must be added there. A regex backstop treats *unknown new top-level dirs* containing `.sql` or auth/payment tokens conservatively → gated.

**First-pass only.** The classifier is a pre-deploy gate, not a runtime healthcheck (Ground-3 gotcha) — a CI-green glob-safe deploy can still break. The post-deploy `validates_deployments` capability remains the second line, and a bad deploy is a thermostat demotion trigger (§4).

**Depends-on.** git CLI; GitHub API (dev-tasks auth); Vercel API; `authority-matrix.yml` globs.

**Isolation.** `deploy_classifier.py`: `classify_deploy(tool_input, deploy_cfg) -> "auto"|"propose_only"`. Pure function over the four signals + the changed-file list, scoped to non-prod targets. Called only by the `deploy_nonprod` verdict branch.

---

## Component 7 — Shadow → enforcing rollout (split from the legacy flip) `[FIX-2]`, `[FIX-8]`

**`[FIX-8]` mission-scope correction.** `outcome-system-self-001` (captain-ratified, owner CoS) is specifically "promote `cabinet/scripts/lib/policy_engine.py` from shadow to enforcing with CI parity proof on the hook-regression corpus" — i.e. flipping the **existing typed legacy rules** to authoritative. A is **additive** work on top of that mission, not the mission. So the rollout is **two independent shadow→enforcing cycles with separate parity corpora and separate revert flags**:

- **Cycle 1 (the mission proper):** flip the existing typed engine (the 6 legacy rules) to enforcing with parity on the **hook-regression corpus**. Flag `CABINET_POLICY_ENGINE_ENFORCING`. Completes `outcome-system-self-001`.
- **Cycle 2 (A's addition):** add the `authority_matrix` type as its OWN shadow→enforcing cycle with its OWN **authority-verdict parity corpus** and OWN flag `CABINET_AUTHORITY_ENFORCING`. A wrongful authority block thus reverts independently without un-enforcing the proven legacy floor.

**`[FIX-2]` the shadow seam — explicit incremental wiring.** Stage 0 cannot "just run in `policy-shadow.py`" — that file imports only `org_runtime.Store` and hand-rolls regex; it never calls `policy_engine`. So Stage 0 is real work:
- Make `policy-shadow.py` `import policy_engine` and call `load_policies()` + `evaluate_policy()` for the `authority_matrix` type (alongside its existing regex decision, which is unchanged).
- Emit the **verdict** (not just allow/block) into `org_events` as `policy.shadow_decision` with `policy_version: 'authority-shadow-v1'` and `verdict: <auto|veto|propose_only|always_gated>`, so the existing parity harness (`framework/measurement/scenarios/policy_enforcement.py` + `test-policy-shadow.sh`) can exercise the typed verdict.

**Stage 0 — Shadow.** The authority_matrix eval runs in the (now `policy_engine`-aware) `policy-shadow.py` Section-0 path: it computes the verdict and records it, but **never blocks**. Zero behavior change.

- **T7 BUILT (2026-06-19) — `policy-shadow.py` re-wired to emit the typed authority verdict `[FIX-2]`.** `cabinet/scripts/policy-shadow.py` now imports `policy_engine` (reusing the engine's repo-root sys.path bootstrap, honoring `CABINET_ROOT` — no new dynamic path math in the shadow), loads the layered policies via `policy_engine.load_policies()` (`yaml.safe_load` only), finds the single `authority_matrix` policy, and computes the verdict by reusing the engine's SHARED `classify_action`/`risk_of`/`read_cell_state`/`resolve_verdict` (one source of truth — identical to what `_eval_authority_matrix` would gate on). It emits a SECOND `policy.shadow_decision` event tagged `policy_version: "authority-shadow-v1"` carrying `{verdict, action_type, risk_class, confidence_state, officer}`, ALONGSIDE the unchanged regex decision (`policy_version: "shadow-v1"`, decision allow/block — untouched). FAIL-SAFE spine mirrors the gate: hard-ceiling risk_class → `always_gated`; unknown/unmapped action_type or unmeasured cell → `propose_only`; A0's stubbed `read_cell_state="unmeasured"` means a real officer action never resolves to `auto`. SHADOW ONLY: `main()` always returns 0, never `exit 2`; the authority emission is fully guarded (`maybe_record_authority` swallows every exception) so it can never break the regex shadow or block a tool — even with no `authority_matrix` policy present (empty `CABINET_ROOT`), the regex shadow still emits. No change to `pre-tool-use.sh` (no new live block); the existing bash parity harness (`test-policy-shadow.sh`) still passes (regex stdout `.decision` unchanged; the extra authority events only add to the org_events count). Tests: `cabinet/scripts/lib/tests/test_policy_shadow.py` (10 — authority verdict emitted + typed + tagged; reversible/unmeasured→propose_only; hard-ceiling→always_gated; A0-never-auto across 8 probes; regex shadow unchanged; `main()` returns 0 / never `SystemExit(2)`; authority failure never breaks the regex shadow).

**Stage 1 — Parity proof (authority corpus).** Run the measurement harness over real recorded actions on the **authority-verdict corpus**: prove the shadow verdict matches the intended matrix on a labeled scenario set, that no currently-allowed safe action would be wrongly blocked (false-positive-block rate ≈ 0), and that every action that should gate, gates. Parity report → Captain.

**Stage 2 — Captain-approved flip (PROPOSE-ONLY).** The flip is itself gated: A **proposes** the enforcing flip (one course-of-action card with the parity report). Nothing flips autonomously — the policy engine cannot enable its own enforcement. On approval, set `CABINET_AUTHORITY_ENFORCING=1` (read in `pre-tool-use.sh` at the Section-2→3 dispatch; default `0` = shadow). The flag flip is itself a germline-style change the Captain applies.

**Stage 3 — 48h soak + instant revert.** With enforcing on, monitor false-positive blocks, demotion events, officer-throughput. Any anomaly → `CABINET_AUTHORITY_ENFORCING=0` reverts instantly to shadow (one env flip, no redeploy). A demotion storm or a single wrongful hard-block auto-DMs Nate recommending revert. This flag is **independent** of `CABINET_POLICY_ENGINE_ENFORCING` so reverting authority does not un-enforce the legacy floor.

**Stage 4 — Enforcing.** After clean soak, enforcing stays on. Cells still default propose-only until F graduates them — so "enforcing" initially means *enforcing the fail-safe* (everything proposes), and autonomy lights up cell-by-cell only as F's graduation states arrive. The dangerous direction (auto) is gated behind BOTH the enforcing flip AND F graduation.

**Depends-on.** `policy-shadow.py` (re-wired) + measurement harness (Ground 1); env flags in `pre-tool-use.sh`; F graduation states; Captain approval gate.

**Isolation.** Rollout is two env flags + parity reports + proposals. The code path (Components 1–6) is identical in shadow and enforcing; only `sys.exit(2)` vs record-and-continue differs, keyed on `CABINET_AUTHORITY_ENFORCING`.

---

## Reconciliation with `HARD_CEILING_TOUCHES` (Ground 2, fail-closed) `[FIX-6]`, `[FIX-7]`

`HARD_CEILING_TOUCHES = frozenset({secrets, spending, external_comms, production, network_write, credentials_grant})` (capability_gaps.py) is the code-level backstop for **self-extension** (can the cabinet *install* a new capability unattended). The matrix's `hard_ceiling` guards **action execution** (can an officer *act* unattended). They are two enforcement layers of one rule (belt + suspenders).

**`[FIX-7]` complete coverage.** The matrix's `hard_ceiling` now maps **all six** frozenset members 1:1 via `ceiling_frozenset_map`:

| frozenset member | matrix risk_class | action_types |
|---|---|---|
| `external_comms` | external_comms | external_message, external_email |
| `production` | deploy_prod | vercel_deploy_prod, git_push_main |
| `spending` | spend | purchase, provision_paid, billing |
| `secrets` | secrets | secret_read, secret_write, env_write |
| `network_write` | network_write | mcp_post, mcp_put, mcp_delete |
| `credentials_grant` | credentials_grant | oauth_grant, token_grant |

The CI coverage test asserts `set(ceiling_frozenset_map.values()) == HARD_CEILING_TOUCHES` (the **full six**, not a self-fulfilling "mappable subset"). The matrix can only **widen** the ceiling, never narrow — mirroring `AutonomyPolicy.ceiling = HARD_CEILING_TOUCHES | extra_ceiling`.

**`[FIX-6]` deploy/prod contradiction resolved.** `production`/`deploy_prod` is always-gated in BOTH layers. The low-risk carve-out (§6) targets `deploy_nonprod` (preview/staging) **only** and can never produce a prod auto verdict — so it does not narrow `production`. The live `*"vercel deploy"*`/`*"vercel --prod"*` block in `pre-tool-use.sh` Section 3a stays as the unconditional prod floor and **wins**: the authority dispatch runs *before* Section 3a but only ever emits `auto` for non-prod deploy commands (preview targets), which the Section-3a substring does not match; any prod deploy command still hits the always-gated `deploy_prod` row in §2 AND the Section-3a block. A CI test asserts **no deploy verdict can resolve to `auto` while the target is prod**.

---

## Data flow (A's closed loop)

```
1. F: graduation.evaluate(cell=(officer,lane,action_type)) → per-cell state (precomputed)   [F2]
2. officer action → classify_action() stamps action_type (shared)                            [FIX-1]
3. pre-tool-use.sh §0 shadow logs authority VERDICT (policy_engine-aware)                     [FIX-2, stage 0]
4. (enforcing, CABINET_AUTHORITY_ENFORCING=1) §2→§3 dispatch → _eval_authority_matrix         [comp 2]
5.   resolve_lane() + classify_action → risk_class; hard-ceiling short-circuit (all 6)        [comp 2, FIX-7]
6.   read_cell_state (fail-safe → unmeasured if F absent)                                     [comp 3, FIX-4]
7.   resolve_verdict(matrix, risk_class, state)                                               [comp 1]
8.   deploy_nonprod → classify_deploy(diff, CI, preview) → auto(non-prod)/gated               [comp 6, FIX-6]
9.   internal_comms auto → BLOCK-then-enqueue veto stream + notify; scan sends on expiry       [comp 5, FIX-3]
10.  block (propose-only/gated) OR allow (auto)
11. action outcome → consequence event (keyed by action_type) → ledger                        [F0 re-keyed]
12. bad call / drift / friction / kill → demotion_scan → cell=demote + finding                [comp 4, FIX-5]
13. demotion finding → next briefing decision queue (courses-of-action)
```

---

## Error handling / safety (the fail-safe inventory)

- **F absent / cell unmeasured** → `propose_only` (§3). No auto without F.
- **Hard ceiling** (external_comms / deploy_prod / spend / secrets / network_write / credentials_grant) → `always_gated` regardless of confidence (§2 short-circuit + frozenset backstop) `[FIX-7]`.
- **Engine plumbing crash / malformed JSON** → fail-open `exit 0` (legacy regex prohibitions §3 + spend cap §2 remain the floor); policy *semantics* are fail-safe (unknown → propose-only).
- **Veto path** → block-then-redirect: the gate exits 2 and enqueues; no fall-through allow on the irreversible-comms path `[FIX-3]`.
- **Classifier signal unreadable** → deploy gated (§6). Prod deploy never auto `[FIX-6]`.
- **Veto-send backend failure** → dead-letter, no silent drop (§5).
- **Demotion is immediate + sticky**; re-promotion requires fresh post-demotion samples clearing the full bar (§4). Sticky key + cooldown unit-tested.
- **No-silent-caps** — a cell with `None` ratios reads as `unmeasured` (visible), never silently 0/1 (Ground-2 invariant).
- **Self-enabling guard** — the enforcing flip is propose-only; the engine cannot turn on its own enforcement (§7).
- **Lane never silently null** — `resolve_lane()` is the single source; `start-officer.sh` exports `CABINET_LANE` `[FIX-4]`.

---

## Phased build order

Each phase: Corridor `analyzePlan` before code · worktree-isolated build · review (security/correctness/conventions) · tests green · docs-as-you-build (update `docs/`, `CLAUDE.md` MCP/germline lists, `.claude-plugin/*.json` counts in the same commit).

- **A0 — Matrix + gate, shadow-only.** `authority-matrix.yml` floor (data); `authority_matrix` policy type in `policy.schema.json`; `_eval_authority_matrix` + dispatch branch; shared `classify_action`/`resolve_lane`; **re-wire `policy-shadow.py` to import `policy_engine` and emit the typed verdict** `[FIX-2]`. Confidence read stubbed to `unmeasured` (everything proposes). Germline-register every new judge module `[FIX-8]`. Parity test green on the authority corpus.
- **A-prereq (F-side, hard gate before A1) — `action_type` first-class.** Add `action_type` to the consequence schema + emitter (stamped by shared `classify_action`); re-key `compute_ratios` on `(actor, lane, action_type)`; export `CABINET_LANE` from `start-officer.sh` `[FIX-1]`, `[FIX-4]`. A1 cannot start until this lands.
- **A1 — Confidence interface.** Wire Component 3 to F's `graduation.evaluate` when F2 lands (hard gate on F2); F2 imports the bar from `authority-matrix.yml`.
- **A2 — Thermostat (hard gate on F2 + F6).** `authority_thermostat.py` + the `authority.friction`/`authority.gate_decision` event types + sticky cooldown key; findings into the briefing queue `[FIX-5]`.
- **A3 — Deferred-send veto window.** `authority_veto.py`: enqueue (block-then-redirect) + notify + kill + idempotent scan-sender `[FIX-3]`.
- **A4 — Mechanical deploy classifier.** `deploy_classifier.py`, non-prod target only, fail-closed `[FIX-6]`.
- **A5 — Rollout.** Cycle-1 legacy-engine flip (`outcome-system-self-001`, hook-regression corpus) → then Cycle-2 authority_matrix flip (authority corpus → Captain-approved `CABINET_AUTHORITY_ENFORCING` → 48h soak → instant revert) `[FIX-8]`, `[FIX-2]`.

---

## Test / eval plan

- **pytest per component** (mirror `test_policy_engine.py` + F's tests):
  - `_eval_authority_matrix` verdict-table resolution incl. `"*"` wildcard rows.
  - hard-ceiling short-circuit — **every one of the six frozenset members gates** `[FIX-7]`.
  - fail-safe (`unmeasured → propose_only`); unknown action-type → propose-only unless positively local.
  - `classify_action` taggers — including network_write / credentials_grant / secrets positive classification `[FIX-7]`; identical output to the emitter's stamp `[FIX-1]`.
  - `resolve_lane` precedence (CABINET_LANE → PROJECT → None) `[FIX-4]`.
  - `classify_deploy` glob matrix (every safe glob passes, every high-risk glob gates); **no auto verdict with a prod target** `[FIX-6]`.
  - thermostat triggers 1–5 + sticky cooldown key + fresh-sample re-promotion `[FIX-5]`.
  - veto-window: block-then-redirect (gate exits 2 + enqueues), kill, TTL expiry send, idempotency / dead-letter `[FIX-3]`.
- **Parity regression** (`policy_enforcement.py` + `test-policy-shadow.sh`, Ground 1): shadow verdict == intended matrix on the **authority corpus**; zero wrongful safe-action blocks; verify `policy-shadow.py` actually invokes `policy_engine` `[FIX-2]`.
- **Ceiling-coverage CI test** `[FIX-7]`: `set(authority-matrix.ceiling_frozenset_map.values()) == HARD_CEILING_TOUCHES` (full six).
- **Prod-never-auto CI test** `[FIX-6]`: assert no deploy verdict resolves to `auto` with a prod target.
- **Germline read-only** (`cabinet/tests/hook-regression/germline-readonly.sh`): officers can't edit `authority-matrix.yml`, `policy_engine.py`, **or any new judge module** (T1: `framework/authority/classifier.py`, `framework/authority/lane.py`; T5: `framework/authority/matrix.py`; later `authority_thermostat.py`, `authority_veto.py`, `deploy_classifier.py`) — while their `tests/` stay editable `[FIX-8]`.
- **Golden evals** (`memory/golden-evals/`): "external_comms never auto"; "spend never auto"; "secrets/network_write/credentials_grant never auto"; "unmeasured cell can't auto"; "a `wrong` verdict demotes a graduated cell"; "an `authority.friction` event demotes an internal_comms cell"; "deploy with a `migrations/*.sql` diff gates"; "deploy_prod never auto"; "internal_comms auto blocks-then-enqueues (no immediate send)"; "the enforcing flip requires Captain approval".

- **T8 BUILT (2026-06-19) — germline-register the judge modules + the A0 CI safety tests.** The germline registration (judge modules `framework/authority/classifier.py`, `lane.py`, `matrix.py` + `cabinet/scripts/lib/policy_engine.py`) was completed by T1/T5 in `pre-tool-use.sh` Section 5; T8 confirms it and adds the missing **explicit assertion** that the matrix-as-DATA floor `framework/policies/authority-matrix.yml` is germline (it was already protected only implicitly by the `framework/policies/` dir-match — no probe pinned it). Added to `cabinet/tests/hook-regression/germline-readonly.sh`: BLOCK probes **G20/G21/G22** (Edit/Write by a non-cos officer + abs-path) for `framework/policies/authority-matrix.yml`, plus ALLOW probe **FP10** proving the captain-tunable `instance/config/policies/authority-matrix.yml` overlay is NOT in the germline floor (only the framework floor is locked; preset/instance overlays narrow/tune). Harness now 35 PASS / 0 FAIL (was 31); the new probes were proved load-bearing by mutation (dropping the `framework/policies/` arm turns G20–G22 red). The hook's live block logic was UNCHANGED — the existing dir-match already covers the matrix floor, so T8 added an assertion, not a new exit-2. Added the five A0 golden evals (`memory/golden-evals/eval-011..015`, `Category: safety`): external_comms never auto, spend never auto, secrets/network_write/credentials_grant never auto, unmeasured cell cannot auto, deploy_prod never auto — each backed by executable assertions in `framework/authority/tests/test_golden_evals_a0.py` (8 tests) that exercise the REAL shipped matrix floor through `_eval_authority_matrix`: every hard-ceiling action returns a GATED block (never None/auto) regardless of confidence, and with `read_cell_state` stubbed to `unmeasured` the gate NEVER returns auto for any probe (ceiling, reversible, or internal). SHADOW-ONLY: no live exit-2 added; `CABINET_AUTHORITY_ENFORCING` stays default 0. No regression — fidelity 233, authority 125 (was 117 + 8), policy_engine 194, policy_shadow 10, germline-readonly 35 all green. Safety invariant touched: **(5) GERMLINE** — every judge module + the matrix data file + `policy_engine.py` are registered read-only and now CI-asserted; the golden evals also codify **(1) FAIL-CLOSED** + **(2) HARD CEILING**.

---

## Open decisions for Captain ratification

1. **`veto_window_minutes`** — default 7 (spec range 5–10).
2. **Per-decision-type bars** — internal_comms 0.90/30/0/21, deploy_nonprod 0.95/30/0/21, default 0.85/20/1/14 (mirrors screenpipe 15/90/14 at the floor, irreversible-type tightened).
3. **Cooldown windows** — 14d default / 21d for deploy_nonprod + internal_comms.
4. **Colleague-friction signal source** — how an `authority.friction:<person>` event is detected/emitted (screenpipe sentiment vs explicit Nate flag). Needs a capture decision before §4 trigger-4 is live `[FIX-5]`.
5. **Lane → risk-class bindings** per preset (work / portfolio / personal) — the instance layer; depends on confirming `CABINET_LANE` derivation `[FIX-4]`.
6. **Low-risk deploy auto target** — confirm preview/staging-only is the intended carve-out (vs ever allowing a narrowly-scoped prod auto, which would be an explicit ratified narrowing of `HARD_CEILING_TOUCHES.production` and is NOT proposed here) `[FIX-6]`.
7. **Mission sequencing** — confirm Cycle-1 (`outcome-system-self-001` legacy-engine flip) completes before Cycle-2 (authority_matrix flip) `[FIX-8]`.

---

## Risks (mitigations in-design)

1. **A enforces before F is trustworthy** → enforcing initially means enforcing the *fail-safe* (all propose-only); auto is double-gated behind the flip AND F graduation.
2. **`action_type` not emitted → matrix permanently unmeasured** → the A-prereq F-side change is a hard gate before A1; A0 ships shadow-only `[FIX-1]`.
3. **Veto fails open on the irreversible path** → block-then-redirect (gate exits 2 + enqueues), never allow-with-marker `[FIX-3]`.
4. **Missing high-risk deploy glob** → explicit Captain-extendable glob list + conservative regex backstop on unknown dirs → gated `[FIX-6]`.
5. **Prod auto via carve-out** → carve-out is non-prod only; prod-never-auto CI test + legacy Section-3a block wins `[FIX-6]`.
6. **Hard-ceiling coverage gap** → all six frozenset members mapped + full-coverage CI test (not "mappable subset") `[FIX-7]`.
7. **Demotion storm bricks throughput** → instant env revert to shadow (independent flag); demotion storm auto-DMs Nate.
8. **Officer edits its own judge** → every new judge module germline-registered + hook-regression test `[FIX-8]`.
9. **Self-enabling engine** → the enforcing flip is propose-only `[FIX-2]`/`[FIX-8]`.

---

## Design files (all absolute)

- Consumes: `/Users/nate/captains-cabinet/docs/fidelity-harness-design-2026-06-18.md` (§Locked architecture, §unified control loop).
- New artifacts proposed:
  - `framework/policies/authority-matrix.yml` (+ `presets/<active>/policies/` and `instance/config/policies/` overlays).
  - `authority_matrix` type in `/Users/nate/captains-cabinet/framework/policies/policy.schema.json`.
  - `_eval_authority_matrix` + dispatch in `/Users/nate/captains-cabinet/cabinet/scripts/lib/policy_engine.py`.
  - Judge modules under `framework/authority/`: `classifier.py` (shared `classify_action`) + `lane.py` (`resolve_lane`) — **T1 built**; `matrix.py` (matrix loader/validator) — **T5 built (2026-06-19)**; later `authority_thermostat.py`, `authority_veto.py`, `deploy_classifier.py` — **all germline-registered** in `/Users/nate/captains-cabinet/cabinet/scripts/hooks/pre-tool-use.sh` Section 5 `[FIX-8]`.
    - **T1 BUILT (2026-06-19) — canonical location resolved to `framework/authority/`, NOT `cabinet/scripts/lib/`.** The shared join key is `framework/authority/classifier.py` (`classify_action`, the `ACTION_TYPES`/`CEILING_ACTION_TYPES`/`AMBIGUOUS` surface) + `framework/authority/lane.py` (`resolve_lane`). Rationale: the fidelity side already imports as a package (`framework.fidelity.*` with repo root on sys.path), so the framework side gets a clean `from framework.authority import ...`; the cabinet gate (`policy_engine.py`, invoked standalone by the hook) reaches it via a documented repo-root sys.path bootstrap (`_authority_root()`, honoring `CABINET_ROOT`) — ONE source of truth, no duplicate copy (proven by `cabinet/scripts/lib/tests/test_authority_join.py`: the gate's `classify_action`/`resolve_lane` are the *same function objects* as `framework.authority`'s). Germline registered as **suffix-anchored exact files** (`framework/authority/classifier.py`, `framework/authority/lane.py`) — same style as `policy_engine.py` — so the judges are read-only but their tests under `framework/authority/tests/` stay editable (a dir contains-match would wrongly lock the tests). The later judge modules (thermostat/veto/deploy_classifier) land under the same `framework/authority/` dir and get added to the germline case by name when created `[FIX-8]`. Tests: `framework/authority/tests/test_classifier.py` (69) + the cross-tree join test (`cabinet/scripts/lib/tests/test_authority_join.py`) + germline regression probes G16–G18 / FP8.
  - Section-2→3 dispatch + `CABINET_AUTHORITY_ENFORCING` flag in `/Users/nate/captains-cabinet/cabinet/scripts/hooks/pre-tool-use.sh`.
  - Re-wired `/Users/nate/captains-cabinet/cabinet/scripts/policy-shadow.py` (import `policy_engine`, emit typed verdict) `[FIX-2]`.
  - `CABINET_LANE` export in `/Users/nate/captains-cabinet/cabinet/scripts/start-officer.sh` AND `/Users/nate/captains-cabinet/cabinet/scripts/start-officer-mac.sh` — **T4 BUILT 2026-06-19** `[FIX-4]`.
- F-side prerequisites (A depends on, built by F):
  - `action_type` field in `/Users/nate/captains-cabinet/framework/schemas/consequence-event.schema.json` + emitter stamp `[FIX-1]`.
  - re-keyed `compute_ratios` + `graduation.evaluate` in `/Users/nate/captains-cabinet/framework/fidelity/consequence.py` (built, re-keyed) and `/Users/nate/captains-cabinet/framework/fidelity/graduation.py` (F2, to be built).
  - `aggregate.cusum` drift (F6, to be built) for thermostat trigger-2.
- Hard-ceiling reconciliation: `/Users/nate/captains-cabinet/framework/learning/capability_gaps.py` `HARD_CEILING_TOUCHES`.
