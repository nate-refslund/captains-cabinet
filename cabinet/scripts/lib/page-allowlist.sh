#!/usr/bin/env bash
# page-allowlist.sh — Spec 049 AC #15 (M3 origin-pinning) page-list allowlist.
# Sourced by the Gate-4 stagehand-runner: BEFORE invoking Stagehand, the requested
# page-list is intersected with visual_uat.allowed_paths and validated as safe
# path-only entries against the PINNED preview origin. Pages outside the allowlist
# OR carrying their own scheme/host OR traversal are rejected with a WARN.
#
# M3 (CRO): the allowlist globs PATHS, not origins — so an entry that resolves to a
# different host/scheme ("//evil", "https://evil/x", "..", encoded traversal) was an
# SSRF/exfil gap. The runner pins the origin (resolved Vercel preview host); this lib
# enforces that every page is a bare, traversal-free absolute path under that origin.
#
# NOTE: AC #15 parts (2) self-modifying-config approval and (3) base-branch trust-diff
# are Gate-3 diff-analysis concerns, NOT this runtime filter — out of scope here.
#
# Framework default allowlist: "/", "/dashboard", "/tasks/*" (widen per project via
# .cabinet/agent-instructions.md → visual_uat.allowed_paths). No hardcoded paths.

PAGE_ALLOWLIST_DEFAULT='/,/dashboard,/tasks/*'

# 0 if a safe path-only entry; 1 if it carries a scheme/host, traversal, or is not an
# absolute path. Catches literal AND percent-encoded "." "/" "\" traversal vectors.
page_allowlist_is_safe() {
  local p="${1:-}" lower
  [ -n "$p" ] || return 1
  case "$p" in
    *"://"*) return 1 ;;   # absolute URL (scheme://host)
    "//"*)   return 1 ;;   # protocol-relative //host
    /*)      : ;;          # must be an absolute path
    *)       return 1 ;;   # relative / bare token → reject
  esac
  case "$p" in
    *".."*|*'\'*) return 1 ;;          # literal traversal / backslash
  esac
  lower=$(printf '%s' "$p" | tr 'A-Z' 'a-z')
  case "$lower" in
    *"%2e"*|*"%2f"*|*"%5c"*) return 1 ;;   # encoded . / \ traversal vectors
  esac
  return 0
}

# 0 if <path> matches any of the remaining glob args (bash pattern match; an allowlist
# glob like /tasks/* is operator-controlled). Traversal already rejected upstream.
page_allowlist_match() {
  local p="${1:-}"; shift || true
  local g
  for g in "$@"; do
    [ -n "$g" ] || continue
    # shellcheck disable=SC2053  -- intentional glob match against the allowlist pattern
    [[ "$p" == $g ]] && return 0
  done
  return 1
}

# Filter requested pages against a CSV allowlist. Prints allowed paths (one per line);
# WARNs each rejected page to stderr with the reason. Returns 0 iff EVERY requested
# page was allowed; 1 if any was rejected (the runner decides: proceed with the safe
# subset, or block). Usage: page_allowlist_filter <allowlist-csv> <page> [page ...]
page_allowlist_filter() {
  local csv="${1:-$PAGE_ALLOWLIST_DEFAULT}"; shift || true
  local globs=() p i any_reject=0
  IFS=',' read -r -a globs <<< "$csv"
  for i in "${!globs[@]}"; do
    # trim surrounding whitespace from each glob
    globs[$i]="${globs[$i]#"${globs[$i]%%[![:space:]]*}"}"
    globs[$i]="${globs[$i]%"${globs[$i]##*[![:space:]]}"}"
  done
  for p in "$@"; do
    if ! page_allowlist_is_safe "$p"; then
      echo "WARN: page rejected (unsafe — scheme/host/traversal/non-path): $p" >&2
      any_reject=1; continue
    fi
    if page_allowlist_match "$p" "${globs[@]}"; then
      echo "$p"
    else
      echo "WARN: page rejected (outside allowlist [$csv]): $p" >&2
      any_reject=1
    fi
  done
  return $any_reject
}
