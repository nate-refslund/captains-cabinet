# Typed Policy Engine — SHADOW → ENFORCING Parity Proof **v2** (post-fix)

**Date:** 2026-07-03
**Supersedes:** `docs/policy-shadow-parity-proof-2026-07-03.md` (the v1 DO-NOT-FLIP finding).
**Mission:** bring the typed policy engine to parity with the live authorization hook, then re-prove.
**Question:** does the SHADOW engine's `.decision` now MATCH the LIVE authorization hook across the full hook-regression corpus, for every rule the typed engine covers?

**VERDICT:** **YES — AT PARITY for every rule the typed engine covers.**
Covered-rule agreement is **100.00% (400/400)** with **0 fail-OPEN and 0 fail-SAFE**. The only remaining disagreements (154) are the **stateful Redis-attestation gates** (Layer-1 git-push/merge review gate, CI-green merge gate, and the gh-api/curl/wget protected-branch DELETE guard that routes through the same Layer-1 family). These are **intentionally Captain-scoped out** of the typed engine because a stateless engine cannot read the `cabinet:layer1:cto:reviewed` / `:ci-green` attestation state — they remain live-only in `pre-tool-use.sh` by design. This is the documented, enumerated scope-reduction the flip criterion allows.

**Ready for the Captain to flip shadow→enforcing?** For the **stateless** rule set, YES — the typed engine is a faithful model. The three **stateful gates must stay in the bash hook**; the flip must not remove them. See §5.

---

## 1. What was compared, and how (identical method to v1)

- **LIVE** = `cabinet/scripts/hooks/pre-tool-use.sh` (exit 2 = BLOCK, any other exit = ALLOW). The authorization hook that gates officer tool calls today. **Unchanged by this work.**
- **SHADOW** = `cabinet/scripts/policy-shadow.py` → its printed JSON `.decision` field (`"allow"`|`"block"`), `policy_version = shadow-v1`. **This is the field that was fixed** (routed through the typed engine).
- Both invoked per `cabinet/scripts/test-policy-shadow.sh` env (`REDIS_URL=redis://127.0.0.1:6379` on this Mac, `ORG_RUNTIME_DB` tmp, `ORG_POLICY_SHADOW_RECORD` off for the sweep). Before each LIVE call the Layer-1 attestation keys `cabinet:layer1:<officer>:reviewed` + `:ci-green` (and the `cto` variants) were `DEL`'d, so each LIVE run is hermetic and the git-push/CI gates always evaluate their block-when-unreviewed branch — exactly as v1.
- **Corpus:** the same **554** cases extracted from all **14** harnesses in `cabinet/tests/hook-regression/*.sh` (515+ Bash, 19 Edit, 16 Write; officers `cos`/`cpo`/`cto`/`coo`/`cro`), reusing each harness's own byte-exact command construction. Reproduced from the v1 extraction (`cases.jsonl`).
- **Reference eval re-run before + after:** `test-policy-shadow.sh` → **PASS** (5/5 parity assertions + org_events recorded).

### The three fixes applied

1. **Routed `policy-shadow.py`'s `.decision` through `policy_engine.evaluate_policy()`** (over the loaded typed policies, first-match-wins), replacing the self-contained regex. The regex is retained only as a fail-safe fallback (`_regex_decision`) for the case where the engine cannot be imported/loaded. The shadow resolves the repo root itself via `policy_engine._authority_root()` so it works when invoked standalone with `CABINET_ROOT` unset (the parity-harness invocation). `authority_matrix` policies are skipped in the `.decision` path (they are shadow-verdict-only; in A0 they would block every action). **This alone fixed R3 (rm-root) + all 6 fail-SAFE cases**, because the real engine already gets those right.

2. **Migrated the live write-gate to typed policies** in `framework/policies/base-safety.yml`:
   - `no-product-workspace-write` (`bash_write_to_path`, `path_pattern: /workspace/[a-z0-9][a-z0-9-]*/`, `exempt_officers: [cto, unknown]`) — the SOURCE/TARGET-aware Bash write-gate (mirrors `pre-tool-use.sh` §4). It blocks writes *into* `/workspace/<slug>/` (perl -i / sed -i / tar / cp/mv/rsync dest / redirect / patch) while ALLOWING reads *from* it. **Fixes R4** — both the 53 fail-OPEN and the 5 read-from-workspace fail-SAFE.
   - `no-product-workspace-edit` (`path_block`, Edit/Write, `/workspace/[a-z0-9]*/*`, `exempt_officers: [cto, unknown]`) — the Edit/Write arm of §4 (the reference eval exercises this).

3. **Migrated the remaining stateless live-only rules; Captain-scoped the stateful gates.** Added to `base-safety.yml`:
   - `no-production-deploy` (`command_contains`, patterns `vercel deploy` / `vercel --prod`) — the §3a literal deploy block (previously covered only by the shadow regex, absent from the typed engine).
   - `germline-readonly` (`path_block`, Edit/Write) — the full §5 germline set (golden-evals, framework policies, authority `*.py`, `policy_engine.py`, `mcp-scope.yml`, `officer-capabilities.conf`, the two `.claude/rules/*.md`, `autonomy.yml`). No `exempt_officers` (read-only for every officer, including cos). Directory entries `*/<dir>/*`; single files `*<suffix>` (siblings like `autonomy.yml.example` / `golden-evals-notes.md` / `authority/tests/*.py` stay editable).
   - `officer-tier2-isolation` (`tier2_isolation`) — the §5 tier2 own-directory arm.
   - **NOT migrated (Captain-scoped out, documented):** the Layer-1 git-push/merge review gate (§6), the CI-green merge gate (§7), and the gh-api/curl/wget protected-branch DELETE guard (§6 Phase 2b). Rationale in §5.

**Both these fixes touch ONLY the typed stack (`policy-shadow.py` + `base-safety.yml`). `pre-tool-use.sh` is unchanged — it does not invoke `policy_engine.py` at all, so live authorization behavior is byte-for-byte the same.** Verified: `run-hook-regression.sh` → **14/14 ALL GREEN** after the change.

### Which rules the typed engine now covers

All the **stateless** rules the live hook enforces (each now a loaded typed policy in `base-safety.yml`):

| id | rule | policy (type) |
|----|------|---------------|
| R1 | `production_deploy` | `no-production-deploy` (command_contains) |
| R2 | `destructive_database` | `no-destructive-sql` (command_contains) |
| R3 | `destructive_rm_root` | `no-destructive-filesystem` (destructive_rm) |
| R4a | `non_cto_product_write` (Bash) | `no-product-workspace-write` (bash_write_to_path) |
| R4b | `non_cto_product_write` (Edit/Write) | `no-product-workspace-edit` (path_block) |
| R5 | `constitution_read_only` | `constitution-readonly` (path_block) |
| R6 | `env_files_read_only` | `env-file-readonly` (path_block) |
| R7 | `tier2_isolation` | `officer-tier2-isolation` (tier2_isolation) |
| R8 | `binary_block` (sudo/docker/systemctl/shutdown/reboot/halt) | `no-dangerous-binaries` (binary_block) |
| R9 | `germline_read_only` | `germline-readonly` (path_block) |

Out of scope (stateful, live-only by design): `layer1_git_push_gate`, `ci_green_gate`, gh-api/curl/wget branch-delete (§5).

---

## 2. Headline numbers — before (v1) → after (v2)

| metric | v1 (before) | v2 (after) |
|--------|-------------|------------|
| total cases | 554 | 554 |
| overall agreement (live == shadow) | 243/554 = 43.86% | **400/554 = 72.20%** |
| **covered-rule cases** | 312 | **400** |
| **covered-rule agreement** | **77.88%** | **100.00% (400/400)** |
| covered-rule **fail-OPEN** (shadow allows what live blocks) | 63 | **0** |
| covered-rule **fail-SAFE** (shadow blocks what live allows) | 6 | **0** |
| out-of-scope (stateful gates, documented) | 242* | 154 |

\* v1's "out-of-scope" (242) counted binary_block + germline + Layer-1 as un-migrated. v2 migrated binary_block + germline into the covered set, leaving only the 154 stateful-gate cases out-of-scope. The overall-agreement rise (43.86%→72.20%) reflects those 151 newly-agreeing cases; the residual 154 are the intentionally-unmigrated gates.

### Per-covered-rule agreement (v2)

| rule | decisive cases | agree | agreement |
|------|----------------|-------|-----------|
| `binary_block` (sudo/docker/systemctl + shutdown/reboot/halt) | 65 | 65 | 100.0% |
| `non_cto_product_write` (Bash + Edit/Write, both directions) | 116 | 116 | 100.0% |
| `germline_read_only` | 23 | 23 | 100.0% |
| `destructive_rm_root` | 10 | 10 | 100.0% |
| `constitution_read_only` | 1 | 1 | 100.0% |
| shared allow (no covered rule fires; both allow) | 185 | 185 | 100.0% |
| **covered total** | **400** | **400** | **100.00%** |

Every covered rule is at perfect parity in both directions.

### fail-OPEN by rule — before → after (the closure)

| live rule | v1 fail-OPEN | v2 fail-OPEN | closed by |
|-----------|--------------|--------------|-----------|
| `binary_block_sudo` | 54 | **0** | Fix 1 (route through engine — binary_block already correct) |
| `binary_block_shutdown` | 11 | **0** | Fix 1 |
| `destructive_rm_root` | 10 | **0** | Fix 1 (engine's `is_destructive_rm` is correct) |
| `non_cto_product_write` | 53 | **0** | Fix 2 (`bash_write_to_path` + Edit/Write `path_block`) |
| `germline_read_only` | 23 | **0** | Fix 3 (`germline-readonly` path_block) |
| `layer1_git_push_gate` | 150 | 150 (OUT-OF-SCOPE) | §5 — stateful gate, live-only |
| `ci_green_gate` | 4 | 4 (OUT-OF-SCOPE) | §5 — stateful gate, live-only |
| **TOTAL fail-OPEN** | **305** | **154 (all OUT-OF-SCOPE)** | |

fail-SAFE: **6 → 0** (the 5 read-from-workspace cases + `rm -rf /tmp/build`, all closed by Fix 1's engine routing).

---

## 3. Disagreement disposition (v2)

Every one of the 154 remaining disagreements is a **fail-OPEN on a stateful gate that is intentionally not migrated**. There are **zero** covered-rule disagreements — verified programmatically: the count of non-gate fail-OPEN is **0**, fail-SAFE is **0**, and there are **0** unmapped live-rule reasons.

| disposition | count | notes |
|-------------|-------|-------|
| AGREE | 400 | 100% of the covered set (both-block + both-allow) |
| OUT-OF-SCOPE (documented) | 154 | 150 `layer1_git_push_gate` + 4 `ci_green_gate` — stateful, §5 |
| **BUG (covered-rule disagreement)** | **0** | — |

---

## 4. Root cause fixed (from v1 §4)

- **Gap A — shadow ≠ real engine (R3 + fail-SAFE).** The shadow's `.decision` was a coarse regex that never called `evaluate_policy()`. **Fixed** by routing `.decision` through the engine (Fix 1). The engine's `is_destructive_rm` (brace-expansion + quote-stripping) and its SOURCE/TARGET-aware write detection were already correct — the shadow just wasn't using them.
- **Gap B — real engine ≠ live hook (R4 + everything the engine had no policy for).** `base-safety.yml` had only 6 policies (no write-gate, no germline, no deploy, no tier2). **Fixed** by adding those as typed policies (Fixes 2+3). The engine now loads 10 policies + the authority-matrix shadow record.

Net: for the stateless rule set, the typed stack (engine + shadow) is now a **faithful model of the live hook**, verified case-by-case across the full corpus.

---

## 5. Scope — why the three stateful gates stay in bash (Captain-scoped-out)

The Layer-1 git-push/merge review gate (`pre-tool-use.sh` §6), the CI-green merge gate (§7), and the gh-api/curl/wget protected-branch DELETE guard (§6 Phase 2b, which routes through the same Layer-1 attestation family) are **NOT** migrated to the typed engine. This is a deliberate, documented scope-reduction, for a sound architectural reason:

- **They are STATEFUL Redis-attestation gates, not stateless command policies.** They block a push/merge/branch-delete **only until the CTO sets** `cabinet:layer1:cto:reviewed` / `cabinet:layer1:cto:ci-green` (a review/CI attestation). In the corpus these keys are DEL'd before each call, so the LIVE hook always blocks — but that is the *block-when-unreviewed* branch, not an absolute rule.
- **A stateless typed policy cannot read that Redis state.** It could only model the block-when-unreviewed branch — i.e. hard-block every push to main forever, misrepresenting a review GATE as an absolute prohibition. That would be *wrong* if the typed engine ever became the live decider (it would block legitimate reviewed pushes).
- **The typed engine's own contract already says so.** `cabinet/scripts/lib/policy_engine.py` header: *"Stateful checks (kill switch, spending limits, Layer 1 gate, CI green gate, context slug validation, MCP scope) remain in bash."* The gates were never in the typed engine's charter.
- **Re-implementing them statically would reintroduce the exact adversarial-regex cat-and-mouse** the typed engine exists to escape (~400 lines of §6/§7 bash regex handling wrappers, quoting, control-flow, heredocs, ANSI-C, URL-encoding, brace expansion). The engine's robust `extract_invoked_binaries` surfaces the invoked binary in 148/154 gate cases, but the gate needs argument-level detection (`push origin main`, `pr merge`, `-X DELETE refs/heads/main`) that the binary extractor discards — so a faithful static port is not a small addition.

**Therefore:** these three gates remain enforced ONLY by `pre-tool-use.sh`. The flip criterion ("100% covered-rule agreement AND full rule coverage, OR the Captain accepts a documented, enumerated scope-reduction") is met via the **documented scope-reduction**: the typed engine covers every *stateless* rule at 100%; the three *stateful* gates are enumerated here and stay in bash.

**Flip guidance:** when the Captain flips the typed engine from shadow to enforcing, `pre-tool-use.sh` must **keep** §6 (Layer-1), §7 (CI-green), and the §6 Phase-2b gh-api DELETE guard live — the typed engine does not replace them. The typed engine replaces/augments only the stateless §3a/§3b/§4/§5 command+path rules.

---

## 6. Safety invariants held (verified)

- **SHADOW-ONLY.** `pre-tool-use.sh` is unchanged; it never invokes `policy_engine.py`. Only the typed engine (consumed via `policy-shadow.py`, whose output the live hook discards with `>/dev/null 2>/dev/null || true`) changed. Live authorization behavior is identical.
- **`run-hook-regression.sh` → 14/14 ALL GREEN** (live hook intact) — after the change.
- **`test-policy-shadow.sh` → PASS** (5/5) — after the change.
- **Python suites green:** `test_policy_engine.py` (194), `test_policy_shadow.py` (10), `test_authority_join.py` (4), `framework/authority/tests/` — **423 passed**; `framework/measurement/tests/` (28) + `framework/events/tests/test_emitter.py` (40) green.
- **Fail-safe shadow:** always exits 0 (never blocks live); malformed JSON → allow; empty/absent policies → allow; engine import failure → falls back to the regex shadow. Verified standalone with `CABINET_ROOT` unset (correctly blocks rm-root) and with an empty `CABINET_ROOT` (allows, no crash).
- **Enforce-flip stays OFF.** `CABINET_AUTHORITY_ENFORCING` unchanged; `main()`'s authority-skip guard intact; no new live exit-2 path added anywhere.
- **Python 3.9 compatible** (system Python here): no runtime `X | Y` unions introduced (annotations only, under `from __future__ import annotations`).

---

## 7. Verdict & recommendation

**AT PARITY for every rule the typed engine covers — 100.00% covered-rule agreement, 0 fail-OPEN, 0 fail-SAFE.** The v1 blockers are all closed:

- R3 root-`rm` (10 forms incl. `rm -rf "/"`, `{rm,X} -rf /`, `rm -rf -- /`) — now blocked (engine routing).
- R4 non-CTO product writes (53 perl-i/sed-i/tar/Edit forms) — now blocked; the 5 read-from-workspace forms — now correctly allowed.
- binary_block (65 sudo/docker/…/reboot forms), germline (23), deploy, tier2 — now covered at 100%.

The typed engine is a **faithful, flippable model of the live hook's STATELESS rule set.** The three **stateful attestation gates** (Layer-1 push/merge, CI-green, gh-api branch-delete) are the enumerated, documented scope-reduction and **must remain in `pre-tool-use.sh`** across the flip.

**Recommendation:** the Captain may flip shadow→enforcing for the typed (stateless) policy set, provided the flip **retains** the three stateful gates in the bash hook (§5). Until the flip, the existing `main()` guards (`CABINET_AUTHORITY_ENFORCING=0`, authority policies skipped by the live loop) remain correct and should stay.

---

## Appendix — reproduction

```
# reference eval (green before + after)
REDIS_URL=redis://127.0.0.1:6379 bash cabinet/scripts/test-policy-shadow.sh

# live hook regression (14/14 green before + after — proves live unchanged)
bash cabinet/scripts/run-hook-regression.sh

# per case, the two invocations compared (payload = {"tool_name":..,"tool_input":..}):
printf '%s' "$payload" | OFFICER_NAME=<officer> bash cabinet/scripts/hooks/pre-tool-use.sh; [ $? -eq 2 ] && echo block || echo allow
printf '%s' "$payload" | OFFICER_NAME=<officer> python3 cabinet/scripts/policy-shadow.py | jq -r '.decision'
```

Cases were the same 554 extracted from `cabinet/tests/hook-regression/*.sh` as v1 (each harness's own command construction preserved). Redis Layer-1 keys DEL'd before each LIVE call. Env per `test-policy-shadow.sh`. Files changed: `cabinet/scripts/policy-shadow.py` (route `.decision` through the engine), `framework/policies/base-safety.yml` (5 new typed policies: deploy, product-write Bash, product-write Edit/Write, germline, tier2).
