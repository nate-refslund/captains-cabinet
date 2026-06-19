#!/bin/bash
# germline-readonly harness: Section 5 GERMLINE protection coverage.
# The germline set is the files that JUDGE officer/loop behavior — golden
# evals, the typed policy engine + framework/policies/, mcp-scope,
# officer-capabilities, the brain-bridge + courses-of-action rules, and
# instance/config/autonomy.yml. Edit/Write must BLOCK (exit 2) for EVERY
# officer (including cos): no loop may edit its own judge.
#
# 19 BLOCK probes (9 germline classes incl. the suffix-anchored
# framework/authority/ judge modules classifier.py + lane.py, x
# Edit/Write/officer/path-form variants + constitution regression pin +
# double-slash normalization) + 9 ALLOW probes (false-positive guards:
# siblings, evolved skills, own tier2, non-germline hooks, shared interfaces,
# the authority judges' own editable tests).
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
# Evolved skills remain the officers' write surface
probe "FP3 evolved skill draft (cro)"      cro Write 'memory/skills/evolved/draft-skill.md'                        ALLOW
# Own tier2 writes still allowed (tier2 arm regression pin)
probe "FP4 own tier2 notes (cto)"          cto Edit  'instance/memory/tier2/cto/notes.md'                          ALLOW
# Hooks are NOT germline — CoS hook ownership stands
probe "FP5 non-germline hook (cos)"        cos Edit  'cabinet/scripts/hooks/post-tool-use.sh'                      ALLOW
# Shared interfaces unaffected
probe "FP6 captain-decisions.md (cos)"     cos Write 'shared/interfaces/captain-decisions.md'                      ALLOW
# Other lib files are not the judge — only policy_engine.py is germline
probe "FP7 other lib file (cto)"           cto Edit  'cabinet/scripts/lib/triggers.sh'                             ALLOW
# Authority judges are suffix-anchored (classifier.py / lane.py) — their TESTS
# are the officers' verification surface and stay editable (mirrors how
# cabinet/scripts/lib/tests/ stays editable while policy_engine.py is germline)
probe "FP8 authority test file (cro)"      cro Write 'framework/authority/tests/test_classifier.py'                ALLOW
probe "FP9 authority sibling note (cro)"   cro Write 'framework/authority-notes.md'                                ALLOW

echo ""
echo "=== Summary: PASS=$PASS  FAIL=$FAIL ==="
exit $FAIL
