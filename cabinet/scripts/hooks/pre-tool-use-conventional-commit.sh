#!/usr/bin/env bash
# cabinet/scripts/hooks/pre-tool-use-conventional-commit.sh — Spec 049 Phase 5 (C3).
#
# PreToolUse Bash hook. On a `git commit` invocation it WARNS (default) when the message is not
# Conventional Commits, when --no-verify/-n is used, or when the message can't be extracted.
#
# ANTI-FW-042 BRICK-PROTECTION: WARN mode is the default — it NEVER blocks. It only blocks when
# CONVENTIONAL_COMMIT_MODE=enforce (a later, deliberate flip after the FP rate is validated from
# the JSONL log). CONVENTIONAL_COMMIT_ENABLED=0 disables it entirely. A missing/sourcing-failed
# lib is a silent no-op — this hook must NEVER break a session.
#
# Detection/extraction is delegated to cabinet/scripts/lib/git-commit-argv.sh (the FW-029/041/
# 043/045-hardened parser; corpus: cabinet/tests/fixtures/c3-commit-corpus.md).

set -uo pipefail

[ "${CONVENTIONAL_COMMIT_ENABLED:-1}" = "0" ] && exit 0

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="${CONVENTIONAL_COMMIT_LIB:-${_DIR}/../lib/git-commit-argv.sh}"
[ -r "$LIB" ] || exit 0   # lib missing -> no-op (fail-safe: never break the session)
# shellcheck source=/dev/null
source "$LIB" 2>/dev/null || exit 0

MODE="${CONVENTIONAL_COMMIT_MODE:-warn}"
LOG="${CONVENTIONAL_COMMIT_LOG:-${_DIR}/../../logs/hook-fires/conventional-commit.jsonl}"

input="$(cat 2>/dev/null)"
command -v jq >/dev/null 2>&1 || exit 0
tool="$(printf '%s' "$input" | jq -r '.tool_name // empty' 2>/dev/null)"
[ "$tool" = "Bash" ] || exit 0
cmd="$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null)"
[ -n "$cmd" ] || exit 0

gca_invokes_git_commit "$cmd" || exit 0   # not a git commit -> pass silently

violation=""; reason=""; valid="n/a"; subj=""
if gca_has_no_verify "$cmd"; then
    violation="no_verify"
    reason="--no-verify/-n bypasses /self-review + pre-commit hooks (Spec 049 anti-pattern)."
else
    subj="$(gca_commit_subject "$cmd")"; st=$?
    case "$st" in
        1) exit 0 ;;  # reuse (-c/-C) / editor commit — no inline message to validate
        2) violation="unextractable"
           reason="could not extract the commit message (ambiguous form); fail-closed — use -m \"type(scope): subject\"." ; valid="unknown" ;;
        0) if gca_validate_subject "$subj"; then valid="yes"
           else violation="bad_subject"; valid="no"
                reason="subject is not Conventional Commits — want ^(feat|fix|refactor|docs|test|chore|perf|style)(scope)?: subject. Got: ${subj}" ; fi ;;
    esac
fi

# FP-rate tracking (best-effort; logs subject LENGTH not content — no message/PII in the log).
mkdir -p "$(dirname "$LOG")" 2>/dev/null || true
printf '{"ts":"%s","mode":"%s","detected":true,"violation":"%s","valid":"%s","subject_len":%d}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$MODE" "${violation:-none}" "$valid" "${#subj}" >> "$LOG" 2>/dev/null || true

[ -z "$violation" ] && exit 0   # compliant -> pass

if [ "$MODE" = "enforce" ]; then
    echo "[conventional-commit] BLOCK: ${reason}" >&2
    exit 2   # PreToolUse deny (reason surfaced via stderr)
else
    echo "[conventional-commit] WARN: ${reason} (warn-mode; CONVENTIONAL_COMMIT_MODE=enforce to block, CONVENTIONAL_COMMIT_ENABLED=0 to disable)" >&2
    exit 0   # warn-mode: surface + allow
fi
