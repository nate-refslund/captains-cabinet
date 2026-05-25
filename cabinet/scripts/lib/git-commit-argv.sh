#!/usr/bin/env bash
# cabinet/scripts/lib/git-commit-argv.sh — Spec 049 Phase 5 (C3) git-commit argv parser.
#
# SOURCE this (do not execute). Provides the hardened building blocks the conventional-commit
# PreToolUse hook uses to (a) detect a `git commit` invocation in a Bash command STRING,
# (b) extract the commit subject (first line) for validation, (c) detect --no-verify/-n.
#
# Follows the FW-029/041/043/045 discipline (see cabinet/scripts/hooks/pre-tool-use.sh):
#   - statement-boundary anchor (FW-043): match `git commit` only at line-start or after a
#     shell statement-boundary char (; & | ( ) { } `), so substring mentions inside echo/grep
#     args (the FW-029 amplification class) do NOT trip it.
#   - flag-tolerant git globals (FW-041): `git -c k=v / -C path commit` accepted.
#   - prefix-consumers (FW-045): env / VAR=val / nohup|nice|time|exec|stdbuf|... before git.
#   - escape-aware DQ span (FW-041 hotfix-4): `"([^"\\]|\\.)*"` so an escaped quote inside the
#     message doesn't terminate extraction early.
#   - fail-CLOSED, never fail-open: an unextractable message returns status 2 (caller warns).
#
# REGEX QUOTING: regexes are built from single-quoted chunks (literal) + $Q (a single-quote
# char) so no double-quote/backslash escaping hell. Each is assigned to a var, then `[[ =~ $re ]]`.
#
# Corpus / golden-eval spec: cabinet/tests/fixtures/c3-commit-corpus.md. Hardened by ≥2 adversary
# passes + Opus ship-gate before any enforce-mode flip; the hook defaults to WARN mode regardless.

GCA_SCOPE_CHARSET="${GCA_SCOPE_CHARSET:-a-z0-9_-}"
_GCA_Q="'"   # a single literal single-quote, for building regexes that match '

# ── subject validation (AC#7 conventional-commit regex) ──────────────────────
gca_validate_subject() {
    local s="$1"
    local re="^(feat|fix|refactor|docs|test|chore|perf|style)(\\([${GCA_SCOPE_CHARSET}]+\\))?: .+$"
    [[ "$s" =~ $re ]]
}

# ── detection: does CMD invoke `git commit` at a statement boundary? ─────────
# returns 0 (yes) / 1 (no).
gca_invokes_git_commit() {
    local cmd="$1"
    # statement boundary: line-start OR after ; & | ( ) { } ` OR a NEWLINE (multiline command —
    # adversary pass 2: `cd /repo\ngit commit ...` was missed by string-mode ^). Per FW-043 this
    # accepts the heredoc-body FP (warn-mode bounds it; under-detection is the worse failure).
    local NL=$'\n'
    local boundary='(^|[;&|(){}`'"${NL}"'][[:space:]]*)'
    local prefix='((env|nohup|nice|time|exec|stdbuf|ionice|setsid|eval|command|builtin)([[:space:]]+-[^[:space:]]+([[:space:]]+[^-][^[:space:]]*)?)*[[:space:]]+|[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*'
    local gitcommit='git([[:space:]]+-[^[:space:]]+([[:space:]]+[^-][^[:space:]]*)?)*[[:space:]]+commit([[:space:]]|$)'
    local re="${boundary}${prefix}${gitcommit}"
    [[ "$cmd" =~ $re ]] && return 0
    # wrapper-exec: bash|sh|zsh -c "<arg>" runs <arg> as shell — recurse into the quoted arg.
    local warg; warg="$(_gca_dash_c_arg "$cmd")"
    if [ -n "$warg" ] && [[ "$warg" =~ $re ]]; then return 0; fi
    return 1
}

# extract the quoted arg of `(bash|sh|zsh) -c <quoted>` (one level); echoes it or empty.
_gca_dash_c_arg() {
    local cmd="$1"
    local re_sq='(^|[;&|(){}`[:space:]])(bash|sh|zsh)[[:space:]]+(-[a-z]*c|--command)[[:space:]]+'"$_GCA_Q"'([^'"$_GCA_Q"']*)'"$_GCA_Q"
    [[ "$cmd" =~ $re_sq ]] && { printf '%s' "${BASH_REMATCH[4]}"; return 0; }
    local re_dq='(^|[;&|(){}`[:space:]])(bash|sh|zsh)[[:space:]]+(-[a-z]*c|--command)[[:space:]]+"(([^"\\]|\\.)*)"'
    [[ "$cmd" =~ $re_dq ]] && { printf '%s' "${BASH_REMATCH[4]}"; return 0; }
    # eval '<arg>' / eval "<arg>" — eval runs its arg as shell (adversary A1)
    local re_evsq='(^|[;&|(){}`[:space:]])eval[[:space:]]+'"$_GCA_Q"'([^'"$_GCA_Q"']*)'"$_GCA_Q"
    [[ "$cmd" =~ $re_evsq ]] && { printf '%s' "${BASH_REMATCH[2]}"; return 0; }
    local re_evdq='(^|[;&|(){}`[:space:]])eval[[:space:]]+"(([^"\\]|\\.)*)"'
    [[ "$cmd" =~ $re_evdq ]] && { printf '%s' "${BASH_REMATCH[2]}"; return 0; }
    printf ''
}

# ── extract the commit subject (first line of the message) ───────────────────
# echoes the subject; exit 0 = extracted (validate it) / 1 = no inline message (reuse/editor —
# skip) / 2 = present but UNEXTRACTABLE -> caller treats as fail-closed (warn).
gca_commit_subject() {
    local cmd="$1" v
    local mflag='(-[a-z]*m|--message)'
    # -m / --message  'single-quoted'
    local re; re="(^|[[:space:]])${mflag}[[:space:]]+${_GCA_Q}([^${_GCA_Q}]*)${_GCA_Q}"
    if [[ "$cmd" =~ $re ]]; then printf '%s' "${BASH_REMATCH[3]%%$'\n'*}"; return 0; fi
    # -m / --message  "double-quoted" (escape-aware)
    re='(^|[[:space:]])(-[a-z]*m|--message)[[:space:]]+"(([^"\\]|\\.)*)"'
    if [[ "$cmd" =~ $re ]]; then v="${BASH_REMATCH[3]}"; printf '%s' "${v%%$'\n'*}"; return 0; fi
    # -m / --message  $'ansi-c'  (subject = up to the first \n ESCAPE in source)
    re='(^|[[:space:]])(-[a-z]*m|--message)[[:space:]]+\$'"$_GCA_Q"'(([^'"$_GCA_Q"'\\]|\\.)*)'"$_GCA_Q"
    if [[ "$cmd" =~ $re ]]; then v="${BASH_REMATCH[3]}"; printf '%s' "${v%%\\n*}"; return 0; fi
    # --message=VALUE / -m=VALUE  (= form: SQ / DQ / bare)
    re='(^|[[:space:]])(--message|-m)='"$_GCA_Q"'([^'"$_GCA_Q"']*)'"$_GCA_Q"
    if [[ "$cmd" =~ $re ]]; then printf '%s' "${BASH_REMATCH[3]%%$'\n'*}"; return 0; fi
    re='(^|[[:space:]])(--message|-m)="(([^"\\]|\\.)*)"'
    if [[ "$cmd" =~ $re ]]; then v="${BASH_REMATCH[3]}"; printf '%s' "${v%%$'\n'*}"; return 0; fi
    re='(^|[[:space:]])(--message|-m)=([^[:space:]]+)'
    if [[ "$cmd" =~ $re ]]; then printf '%s' "${BASH_REMATCH[3]}"; return 0; fi
    # -m / --message  bare single token (rare)
    re='(^|[[:space:]])(-[a-z]*m|--message)[[:space:]]+([^-'"$_GCA_Q"'"[:space:]][^[:space:]]*)'
    if [[ "$cmd" =~ $re ]]; then printf '%s' "${BASH_REMATCH[3]}"; return 0; fi
    # -F / --file FILE -> first line (fail-closed if unreadable)
    re='(^|[[:space:]])(-F|--file)(=|[[:space:]]+)'"$_GCA_Q"'?([^'"$_GCA_Q"'"[:space:]]+)'"$_GCA_Q"'?'
    if [[ "$cmd" =~ $re ]]; then
        local f="${BASH_REMATCH[4]}"
        if [ -r "$f" ]; then head -n1 "$f" 2>/dev/null | tr -d '\n'; return 0; else return 2; fi
    fi
    # -c/-C/--reuse-message/--reedit-message -> reuse existing (presumed-valid) message -> skip
    re='(^|[[:space:]])(-c|-C|--reuse-message|--reedit-message)([[:space:]]|=)'
    if [[ "$cmd" =~ $re ]]; then return 1; fi
    # git commit with no recognized inline message (editor / -a only) -> nothing to validate
    return 1
}

# ── --no-verify / -n detection on git commit/push ────────────────────────────
# returns 0 if present. NOTE (v1 limitation, warn-mode-bounded): a `-n` token INSIDE a quoted
# message body can false-positive; the FP-rate JSONL surfaces it + an adversary pass will strip
# quoted spans before this check. --no-verify (long form) is low-FP.
gca_has_no_verify() {
    local cmd="$1" stripped
    # strip quoted spans first so a -n / --no-verify INSIDE a commit message body does not
    # false-positive (adversary A4). Naive SQ/DQ strip is sufficient for the common FP; an
    # escaped-quote-in-DQ edge remains (warn-mode bounds it).
    stripped="$(printf '%s' "$cmd" | sed -E "s/'[^']*'//g; s/\"[^\"]*\"//g")"
    local re_long='(^|[[:space:]])--no-verify([[:space:]]|=|$)'
    [[ "$stripped" =~ $re_long ]] && return 0
    local re_short='(^|[[:space:]])-n([[:space:]]|$)'
    [[ "$stripped" =~ $re_short ]] && return 0
    return 1
}
