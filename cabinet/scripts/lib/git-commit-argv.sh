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
    # ^ branch tolerates LEADING WHITESPACE (Opus adversary HIGH): a single leading space/tab before
    # `git` must not defeat the anchor (indented commands / copy-paste are ubiquitous). Without the
    # ^[[:space:]]* the ` git commit` form missed BOTH detection and (via the per-segment gate) no-verify.
    local boundary='(^[[:space:]]*|[;&|(){}`'"${NL}"'][[:space:]]*)'
    # wrapper arg-consumer accepts -flag [value] AND a bare positional (timeout's duration, nice N).
    # ERE backtracking keeps `sudo git commit` working (consume zero); the wrapper allow-list +
    # the trailing `git ... commit` requirement prevent false detections (e.g. `sudo apt install git`).
    local prefix='((env|nohup|nice|time|timeout|exec|stdbuf|ionice|setsid|eval|command|builtin|sudo|doas|chronic)([[:space:]]+(-[^[:space:]]+([[:space:]]+[^-][^[:space:]]*)?|[^-][^[:space:]]*))*[[:space:]]+|[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*'
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
    local mflag='(-[a-zA-Z]*m|--message)'
    # -m / --message  'single-quoted'
    local re; re="(^|[[:space:]])${mflag}[[:space:]]+${_GCA_Q}([^${_GCA_Q}]*)${_GCA_Q}"
    if [[ "$cmd" =~ $re ]]; then printf '%s' "${BASH_REMATCH[3]%%$'\n'*}"; return 0; fi
    # -m / --message  "double-quoted" (escape-aware)
    re='(^|[[:space:]])(-[a-zA-Z]*m|--message)[[:space:]]+"(([^"\\]|\\.)*)"'
    if [[ "$cmd" =~ $re ]]; then v="${BASH_REMATCH[3]}"; printf '%s' "${v%%$'\n'*}"; return 0; fi
    # -m / --message  $'ansi-c'  (subject = up to the first \n ESCAPE in source)
    re='(^|[[:space:]])(-[a-zA-Z]*m|--message)[[:space:]]+\$'"$_GCA_Q"'(([^'"$_GCA_Q"'\\]|\\.)*)'"$_GCA_Q"
    if [[ "$cmd" =~ $re ]]; then v="${BASH_REMATCH[3]}"; printf '%s' "${v%%\\n*}"; return 0; fi
    # --message=VALUE / -m=VALUE  (= form: SQ / DQ / bare)
    re='(^|[[:space:]])(--message|-m)='"$_GCA_Q"'([^'"$_GCA_Q"']*)'"$_GCA_Q"
    if [[ "$cmd" =~ $re ]]; then printf '%s' "${BASH_REMATCH[3]%%$'\n'*}"; return 0; fi
    re='(^|[[:space:]])(--message|-m)="(([^"\\]|\\.)*)"'
    if [[ "$cmd" =~ $re ]]; then v="${BASH_REMATCH[3]}"; printf '%s' "${v%%$'\n'*}"; return 0; fi
    re='(^|[[:space:]])(--message|-m)=([^[:space:]]+)'
    if [[ "$cmd" =~ $re ]]; then printf '%s' "${BASH_REMATCH[3]}"; return 0; fi
    # -m / --message  bare single token (rare)
    re='(^|[[:space:]])(-[a-zA-Z]*m|--message)[[:space:]]+([^-'"$_GCA_Q"'"[:space:]][^[:space:]]*)'
    if [[ "$cmd" =~ $re ]]; then printf '%s' "${BASH_REMATCH[3]}"; return 0; fi
    # ATTACHED value (no space): -mfoo / -Smfoo / -am'foo' / -am"foo" (Opus ship-gate finding #2).
    # Restricted arg-less cluster [asqvueponiSG] before m so the greedy match cannot eat message
    # letters (the -mbadmsg→"sg" trap). Placed AFTER the space forms so `-m "x"` wins first.
    re='(^|[[:space:]])-[asqvueponiSG]*m'"$_GCA_Q"'([^'"$_GCA_Q"']*)'"$_GCA_Q"
    if [[ "$cmd" =~ $re ]]; then printf '%s' "${BASH_REMATCH[2]%%$'\n'*}"; return 0; fi
    re='(^|[[:space:]])-[asqvueponiSG]*m"(([^"\\]|\\.)*)"'
    if [[ "$cmd" =~ $re ]]; then v="${BASH_REMATCH[2]}"; printf '%s' "${v%%$'\n'*}"; return 0; fi
    re='(^|[[:space:]])-[asqvueponiSG]*m([^-'"$_GCA_Q"'"=[:space:]][^[:space:]]*)'
    if [[ "$cmd" =~ $re ]]; then printf '%s' "${BASH_REMATCH[2]}"; return 0; fi
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
# returns 0 if --no-verify (or a -n cluster) is a flag of the GIT-COMMIT invocation ITSELF.
# Scoped to the commit's OWN flags (CPO PR#104 review FP fix): a -n on a chained non-git command
# (head -n / grep -n / tail -n / sort -n) or a wrapper prefix (sudo -n / nice -n git commit) does
# NOT count. Quoted spans are stripped first so a -n INSIDE the message body doesn't count (advA4).
# (Remaining warn-mode-bounded edge: escaped-quote-in-DQ message body — disclosed, low-frequency.)
gca_has_no_verify() {
    local cmd="$1" stripped seg flags
    # Strip quoted spans AND backtick command-sub BODIES first. A -n INSIDE a message body (advA4) or
    # inside a `...` command-sub (Opus MEDIUM#4) must not count. Stripping the backtick BODY (mirroring
    # the SQ/DQ strip) rather than SPLITTING on the backtick is deliberate (Opus HIGH#5): a split severs
    # a real --no-verify that FOLLOWS the sub into its own segment -> missed no-verify = the worse direction.
    stripped="$(printf '%s' "$cmd" | sed -E "s/'[^']*'//g; s/\"[^\"]*\"//g" | sed -E 's/`[^`]*`//g')"
    # Split on statement boundaries (consume surrounding space). For the segment that invokes git commit,
    # check no-verify only on the part AFTER the `commit` token — so a -n belonging to a chained command
    # or a wrapper prefix, which lives in another segment or before `commit`, is excluded.
    local split
    split="$(printf '%s' "$stripped" | sed -E 's/[[:space:]]*(\&\&|\|\||;|\&|\||\(|\)|\{|\})[[:space:]]*/\n/g')"
    local re_long='(^|[[:space:]])--no-verify([[:space:]]|=|$)'
    # -n standalone OR inside a combined short-flag cluster (-nm, -anm) — Opus ship-gate #1.
    local re_short='(^|[[:space:]])-[a-zA-Z]*n[a-zA-Z]*([[:space:]]|=|$)'
    while IFS= read -r seg; do
        [ -n "$seg" ] || continue
        gca_invokes_git_commit "$seg" || continue
        # commit's own flags = after the `commit` subcommand token. Greedy `.*$` + the required
        # leading space land on the real subcommand (a "commit" inside an unquoted word/path isn't
        # a space-preceded token at end-of-segment).
        if [[ "$seg" =~ [[:space:]]commit([[:space:]].*)?$ ]]; then flags="${BASH_REMATCH[1]}"; else flags="$seg"; fi
        [[ "$flags" =~ $re_long ]] && return 0
        [[ "$flags" =~ $re_short ]] && return 0
    done <<< "$split"
    return 1
}
