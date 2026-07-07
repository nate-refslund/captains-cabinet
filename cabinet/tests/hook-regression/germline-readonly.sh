#!/bin/bash
# germline-readonly harness: Section 5 GERMLINE protection coverage.
# The germline set is the files that JUDGE officer/loop behavior — golden
# evals, the typed policy engine + framework/policies/, mcp-scope,
# officer-capabilities, the brain-bridge + courses-of-action rules, and
# instance/config/autonomy.yml. Edit/Write must BLOCK (exit 2) for EVERY
# officer (including cos): no loop may edit its own judge.
#
# BLOCK probes (germline classes incl. the suffix-anchored
# framework/authority/ judge modules classifier.py + lane.py + matrix.py, the
# authority-matrix.yml DATA floor (T8) + the germline instance policy layer
# instance/config/policies/ authority overlay (D8, no officer self-escalation
# by dropping a widening policy file), and — added 2026-07-04 per build-
# checkpoint hard-blocker #2 (safety-perimeter CRITICAL: captain-vetoes.yml
# was empirically Edit→ALLOWED) — the ACTING-PLANE JUDGES: captain-vetoes.yml,
# act-first-surfaces.yml and the frontdoor/acting executor+gate modules,
# x Edit/Write/officer/path-form variants + constitution regression pin +
# double-slash normalization) + ALLOW probes (false-positive guards:
# siblings, own tier2, shared interfaces,
# the authority judges' own editable tests incl. test_matrix.py, and the
# acting-plane FP guards: composer.py/loop.py siblings, frontdoor+acting
# tests, .yml.example sibling, rename-staged veto proposal).
# 2026-07-07 captain-law hardening: FP3 (evolved skill Write) and FP6
# (captain-decisions.md Write) flipped ALLOW→BLOCK — the ledgers are
# append-only via append-interface.sh, memory/skills/** is Captain-applied.
# Counts drift with hardening waves — trust the probe lines, not a number.
#
# The BASH-side write bypass of this same set (redirect/tee/sed -i/cp/mv/
# install/truncate/dd of=/python -c) is pinned by the sibling harness
# germline-bash-write.sh (pre-tool-use.sh sec 5b).
#
# Accepted FP (documented, fail-closed): staging a germline-named file
# under a mirrored directory tail (e.g. /tmp/cabinet/mcp-scope.yml) is
# blocked by the suffix anchor — stage proposals under a different name
# (e.g. /tmp/mcp-scope-proposed.yml) instead. Same class as the
# constitution/ contains-pattern blocking /tmp/constitution/x.
#
# CABINET_HOOK_TEST_MODE=1 must be set inline per every probe (no global
# export) per feedback_test_harness_production_sinks.md.
# Resolve HOOK relative to this script's repo root (works in main repo or any worktree)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
HOOK="$REPO_ROOT/cabinet/scripts/hooks/pre-tool-use.sh"
PASS=0; FAIL=0

probe() {
  local label="$1" officer="$2" tool="$3" fpath="$4" expected="$5"
  local result
  result=$(printf '{"tool_name":"%s","tool_input":{"file_path":"%s"}}' "$tool" "$fpath" | CABINET_HOOK_TEST_MODE=1 OFFICER_NAME="$officer" bash "$HOOK" 2>/dev/null; echo "EXIT:$?")
  local exit_code="${result##*EXIT:}"
  local verdict
  if [ "$expected" = "BLOCK" ]; then
    if [ "$exit_code" = "2" ]; then verdict="PASS"; PASS=$((PASS+1)); else verdict="FAIL"; FAIL=$((FAIL+1)); fi
  else
    if [ "$exit_code" = "0" ]; then verdict="PASS"; PASS=$((PASS+1)); else verdict="FAIL"; FAIL=$((FAIL+1)); fi
  fi
  printf "%-6s | %-58s | exit=%s\n" "$verdict" "$label" "$exit_code"
}

# ------------------------------------------------------------------
# BLOCK: germline set (must BLOCK for every officer, Edit AND Write)
# ------------------------------------------------------------------
echo "=== BLOCK: germline set ==="
probe "G1 Edit golden-eval (cto)"          cto Edit  'memory/golden-evals/eval-001-kill-switch.md'                 BLOCK
probe "G2 Write golden-eval subdir (cpo)"  cpo Write 'memory/golden-evals/framework/new-eval.md'                   BLOCK
probe "G3 Edit policy_engine.py (cto)"     cto Edit  'cabinet/scripts/lib/policy_engine.py'                        BLOCK
probe "G4 Edit framework policy (coo)"     coo Edit  'framework/policies/base-safety.yml'                          BLOCK
probe "G5 Write new framework policy"      cto Write 'framework/policies/new-policy.yml'                           BLOCK
probe "G6 Edit mcp-scope.yml (cto)"        cto Edit  'cabinet/mcp-scope.yml'                                       BLOCK
probe "G7 Edit mcp-scope.yml (cos!)"       cos Edit  'cabinet/mcp-scope.yml'                                       BLOCK
probe "G8 Write capabilities conf (cto)"   cto Write 'cabinet/officer-capabilities.conf'                           BLOCK
probe "G9 Edit brain-bridge rule (cos)"    cos Edit  '.claude/rules/brain-bridge.md'                               BLOCK
probe "G10 Edit courses-of-action (cto)"   cto Edit  '.claude/rules/courses-of-action.md'                          BLOCK
probe "G11 Write autonomy.yml (cos)"       cos Write 'instance/config/autonomy.yml'                                BLOCK
probe "G12 abs-path mcp-scope (cto)"       cto Edit  '/opt/founders-cabinet/cabinet/mcp-scope.yml'                 BLOCK
probe "G13 abs-path golden-evals (cro)"    cro Write '/opt/founders-cabinet/memory/golden-evals/eval-002.md'       BLOCK
# Double-slash normalization (suffix-anchor bypass closed by tr -s '/')
probe "G14 dbl-slash policy_engine (cto)"  cto Edit  'cabinet/scripts/lib//policy_engine.py'                       BLOCK
probe "G15 dbl-slash autonomy.yml (cos)"   cos Write 'instance/config//autonomy.yml'                               BLOCK
# Authority judge modules — the shared classifier/lane join key (T1), each
# suffix-anchored as an exact file (like policy_engine.py) so the modules are
# germline but their tests stay editable. Future judges
# (thermostat/veto/deploy_classifier) get added by name when created [FIX-8].
probe "G16 Edit authority classifier (cto)" cto Edit  'framework/authority/classifier.py'                          BLOCK
probe "G17 Write authority lane (cos!)"     cos Write 'framework/authority/lane.py'                                 BLOCK
probe "G18 abs-path authority judge (cro)"  cro Edit  '/opt/founders-cabinet/framework/authority/classifier.py'    BLOCK
# Authority matrix loader/validator (T5) — the new judge module that
# schema-checks authority-matrix.yml; suffix-anchored like the other judges.
probe "G18b Edit authority matrix.py (cto)" cto Edit  'framework/authority/matrix.py'                              BLOCK
probe "G18c Write authority matrix.py (cos!)" cos Write 'framework/authority/matrix.py'                            BLOCK
# authority-matrix.yml — the matrix-as-DATA floor (T8). The single source of
# truth for verdicts/bars/ceilings the gate reads; an officer editing it could
# silently widen autonomy or drop a hard ceiling, so the framework floor is
# germline. Covered by the framework/policies/ dir-match; these probes PIN that
# coverage so a future edit to the germline glob that drops it is caught [FIX-8].
probe "G20 Edit authority-matrix.yml (cto)" cto Edit  'framework/policies/authority-matrix.yml'                    BLOCK
probe "G21 Write authority-matrix.yml (cos!)" cos Write 'framework/policies/authority-matrix.yml'                  BLOCK
probe "G22 abs-path authority-matrix.yml (cro)" cro Edit '/opt/founders-cabinet/framework/policies/authority-matrix.yml' BLOCK
# ACTING-PLANE JUDGES (2026-07-04 — build-checkpoint hard-blocker #2,
# safety-perimeter CRITICAL). The checkpoint proved captain-vetoes.yml was
# empirically Edit→ALLOWED: an officer could forge the veto registry — the
# sharpest demotion tooth — or widen act-first-surfaces.yml. These probes
# pin the closure: the veto registry, the act-first surface allowlist, and
# the frontdoor/acting executor+gate modules are germline for EVERY officer.
probe "G23 Edit captain-vetoes.yml (cro)"   cro Edit  'shared/interfaces/captain-vetoes.yml'                       BLOCK
probe "G24 Write captain-vetoes.yml (cos!)" cos Write 'shared/interfaces/captain-vetoes.yml'                       BLOCK
probe "G25 abs-path captain-vetoes (cto)"   cto Edit  '/opt/founders-cabinet/shared/interfaces/captain-vetoes.yml' BLOCK
probe "G26 Edit act-first-surfaces (cpo)"   cpo Edit  'instance/config/act-first-surfaces.yml'                     BLOCK
probe "G27 Write act-first-surfaces (cos!)" cos Write 'instance/config/act-first-surfaces.yml'                     BLOCK
probe "G28 dbl-slash act-first-surfaces"    cro Edit  'instance/config//act-first-surfaces.yml'                    BLOCK
probe "G29 Edit action_exec.py (cto)"       cto Edit  'framework/frontdoor/action_exec.py'                         BLOCK
probe "G30 Write action_undo.py (coo)"      coo Write 'framework/frontdoor/action_undo.py'                         BLOCK
probe "G31 Edit actfirst_canary.py (cro)"   cro Edit  'framework/frontdoor/actfirst_canary.py'                     BLOCK
probe "G32 Edit veto_registry.py (cos!)"    cos Edit  'framework/frontdoor/veto_registry.py'                       BLOCK
probe "G33 Write tell_surface.py (cto)"     cto Write 'framework/frontdoor/tell_surface.py'                        BLOCK
probe "G34 Edit calendar_template.py (cpo)" cpo Edit  'framework/frontdoor/calendar_template.py'                   BLOCK
probe "G35 Edit action_lane.py (cto)"       cto Edit  'framework/acting/action_lane.py'                            BLOCK
probe "G36 Write run_action_lane.py (cos!)" cos Write 'framework/acting/run_action_lane.py'                        BLOCK
probe "G37 abs-path action_lane.py (cro)"   cro Edit  '/opt/founders-cabinet/framework/acting/action_lane.py'      BLOCK
# Regression pin: pre-existing constitution protection unchanged
probe "G19 constitution pin (cto)"         cto Edit  'constitution/CONSTITUTION.md'                                BLOCK

# ------------------------------------------------------------------
# ALLOW: false-positive guards (must NOT block)
# ------------------------------------------------------------------
echo ""
echo "=== ALLOW: germline FP guards ==="
# Suffix anchor leaves the .example sibling editable
probe "FP1 autonomy.yml.example (cos)"     cos Edit  'instance/config/autonomy.yml.example'                        ALLOW
# Trailing-slash dir anchor leaves sibling-named files editable
probe "FP2 golden-evals-notes.md (cto)"    cto Write 'memory/golden-evals-notes.md'                                ALLOW
# CAPTAIN-LAW hardening 2026-07-07 (pre-tool-use.sh §5 captain-law arm):
# memory/skills/** (evolved/ included) is always-injected officer law, so
# direct officer Write is BLOCKED — skills changes go through the
# evolution loop as Captain-applied proposals (was ALLOW pre-hardening).
probe "FP3 evolved skill draft (cro)"      cro Write 'memory/skills/evolved/draft-skill.md'                        BLOCK
# Own tier2 writes still allowed (tier2 arm regression pin)
probe "FP4 own tier2 notes (cto)"          cto Edit  'instance/memory/tier2/cto/notes.md'                          ALLOW
# Hooks ARE germline (2026-07-04 enforcer self-protection fix): the whole
# cabinet/scripts/hooks/ dir + .claude/settings.json + policy-shadow.py are the
# ENFORCER — an officer that could rewrite them neuters the perimeter itself.
# Now read-only for officers/loops (Captain applies hook changes deliberately;
# the filesystem lock enforces the same set at the OS layer).
probe "FP5 enforcer hook protected (cos)"  cos Edit  'cabinet/scripts/hooks/post-tool-use.sh'                      BLOCK
# Shared interfaces unaffected
# Enforcer self-protection (2026-07-04): the perimeter's own files are germline
probe "FP5b Write pre-tool-use.sh (cro)"    cro Write 'cabinet/scripts/hooks/pre-tool-use.sh'                      BLOCK
probe "FP5c Write settings.json (cro)"      cro Write '.claude/settings.json'                                     BLOCK
probe "FP5d Write policy-shadow.py (cos)"   cos Write 'cabinet/scripts/policy-shadow.py'                           BLOCK
probe "FP5e Write kill-switch.sh (cro)"     cro Edit  'cabinet/scripts/kill-switch.sh'                             BLOCK
# CAPTAIN-LAW hardening 2026-07-07: the three captain-law ledgers are
# append-only via cabinet/scripts/append-interface.sh — direct Write is
# BLOCKED for every officer (was ALLOW pre-hardening).
probe "FP6 captain-decisions.md (cos)"     cos Write 'shared/interfaces/captain-decisions.md'                      BLOCK
# Other lib files are not the judge — only policy_engine.py is germline
probe "FP7 other lib file (cto)"           cto Edit  'cabinet/scripts/lib/triggers.sh'                             ALLOW
# Authority judges are suffix-anchored (classifier.py / lane.py) — their TESTS
# are the officers' verification surface and stay editable (mirrors how
# cabinet/scripts/lib/tests/ stays editable while policy_engine.py is germline)
probe "FP8 authority test file (cro)"      cro Write 'framework/authority/tests/test_classifier.py'                ALLOW
probe "FP8b matrix test file (cro)"        cro Write 'framework/authority/tests/test_matrix.py'                    ALLOW
probe "FP9 authority sibling note (cro)"   cro Write 'framework/authority-notes.md'                                ALLOW
# BOTH the framework FLOOR authority-matrix.yml AND the instance policy layer
# instance/config/policies/ are germline. Under the sovereign posture (D8
# amendment 2026-07-05) an instance authority-matrix overlay is authority-
# DEFINING: an officer dropping a widening policy file there would self-escalate,
# so the whole instance/config/policies/ dir is schg-locked + hook-blocked (see
# germline-lock.sh D8, immutable-core.yml, base-safety.yml, the dir README). The
# Captain adds instance policies only inside a germline unlock window.
probe "G38 instance policy-layer authority overlay (cos!)" cos Write 'instance/config/policies/authority-matrix.yml' BLOCK
# Acting-plane additions are SUFFIX-anchored files, not dir globs: sibling
# modules, their tests, .example siblings and rename-staged proposals stay
# the officers' write surface.
probe "FP11 act-first-surfaces example (cos)" cos Edit 'instance/config/act-first-surfaces.yml.example'           ALLOW
probe "FP12 captain-vetoes proposal (cos)"  cos Write 'shared/interfaces/captain-vetoes-proposed.yml'             ALLOW
probe "FP13 frontdoor sibling composer.py" cro Edit  'framework/frontdoor/composer.py'                            ALLOW
probe "FP14 acting sibling loop.py (cto)"  cto Edit  'framework/acting/loop.py'                                   ALLOW
probe "FP15 frontdoor test file (cro)"     cro Write 'framework/frontdoor/tests/test_action_exec.py'              ALLOW
probe "FP16 acting test file (cro)"        cro Write 'framework/acting/tests/test_action_lane.py'                 ALLOW

echo ""
echo "=== Summary: PASS=$PASS  FAIL=$FAIL ==="
exit $FAIL
