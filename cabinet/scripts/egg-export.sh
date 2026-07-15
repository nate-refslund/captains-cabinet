#!/usr/bin/env bash
# egg-export.sh — cut the PUBLIC egg as a FRESH export from git HEAD (PC-C).
#
# The public artifact is NEVER this repo flipped: tracked personal/employer
# data contaminates git history, so the egg is a clean TREE cut from HEAD
# (`git archive`), then shaped by the deterministic exclusion/transform pass
# encoded in cabinet/scripts/egg-export-manifest.txt (the R116 packaging
# manifest — every rule cites its operative-egg ledger row).
#
# SAFETY CONTRACT:
#   * the source checkout is STRICTLY READ-ONLY — content comes from
#     `git archive HEAD`, and every write lands under --out (or is a
#     sibling "<file>.egg-tmp" inside --out, mv'd into place);
#   * --out must resolve OUTSIDE the repo tree (and must not contain it);
#   * a non-empty --out is refused without --force; --force clears the
#     directory CONTENTS only, and only after the outside-repo check passed;
#   * gitignored files (LimeZu world assets, node_modules, runtime ledgers)
#     never reach the export — `git archive` ships tracked content only.
#
# The result is PRIVATE-SIDE PREP. Publishing the export anywhere remains
# CG-7 Captain-gated; run cabinet/scripts/egg-publish-gate.sh over the export
# before it is ever shown, and even a GREEN gate does not lift CG-7.
#
# Usage:
#   bash cabinet/scripts/egg-export.sh --out /path/outside/repo/egg [--force]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd -P)"
MANIFEST="$SCRIPT_DIR/egg-export-manifest.txt"

usage() {
  cat <<'EOF'
egg-export.sh — cut the public egg as a fresh tree from git HEAD

  --out DIR    REQUIRED. Destination directory. Must resolve OUTSIDE the
               repo tree; its parent must exist. Created if absent.
  --force      Clear a non-empty --out directory (contents only) first.
  -h, --help   This help.

The exclusion/transform pass is data-driven from
cabinet/scripts/egg-export-manifest.txt (row-cited: R059 R088 R116 R120
R122 R123 R124 R125 R126 R127 R128 R145 R159 R160 R161 R162 R167 — incl.
the PC-E transforms launchd-portable-only, claude-egg-swap,
framework-docs-archive and the R167 proposals-archive). Writes
egg-manifest.json into the export root and prints a one-screen summary.

PRIVATE-SIDE PREP ONLY — publishing remains CG-7 Captain-gated.
EOF
}

fail() { echo "egg-export: FAIL — $*" >&2; exit 1; }

# --- args ---------------------------------------------------------------------
OUT_ARG=""
FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --out) [ $# -ge 2 ] || fail "--out needs a value"; OUT_ARG="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "egg-export: unknown argument '$1'" >&2; usage >&2; exit 2 ;;
  esac
done
[ -n "$OUT_ARG" ] || { echo "egg-export: --out DIR is required" >&2; usage >&2; exit 2; }
[ -f "$MANIFEST" ] || fail "manifest not found: $MANIFEST"

# --- output-dir safety (canonicalize WITHOUT requiring the dir to exist) -------
case "$OUT_ARG" in
  /*) OUT_RAW="$OUT_ARG" ;;
  *)  OUT_RAW="$PWD/$OUT_ARG" ;;
esac
OUT_PARENT="$(dirname "$OUT_RAW")"
OUT_BASE="$(basename "$OUT_RAW")"
[ -d "$OUT_PARENT" ] || fail "parent of --out must exist: $OUT_PARENT"
[ "$OUT_BASE" != "." ] && [ "$OUT_BASE" != ".." ] && [ "$OUT_BASE" != "/" ] \
  || fail "unusable --out basename: '$OUT_BASE'"
OUT_PARENT="$(cd "$OUT_PARENT" && pwd -P)"
OUT="$OUT_PARENT/$OUT_BASE"
# a root parent joins to '//<base>' (and '//'-prefixed input survives pwd -P
# on macOS) — collapse duplicate leading slashes, or every case-pattern
# safety check below (incl. the inside-the-repo refusal) can be dodged
while case "$OUT" in //*) : ;; *) false ;; esac; do OUT="${OUT#/}"; done
if [ -L "$OUT" ]; then
  fail "--out is a symlink — refuse (point at the real directory): $OUT"
fi
if [ -e "$OUT" ] && [ ! -d "$OUT" ]; then
  fail "--out exists and is not a directory: $OUT"
fi
[ -d "$OUT" ] && OUT="$(cd "$OUT" && pwd -P)"

# outside-the-repo checks (both directions), plus obvious footguns
case "$OUT/" in
  "$REPO_ROOT/"*) fail "--out resolves INSIDE the repo tree ($REPO_ROOT) — the export must live outside it: $OUT" ;;
esac
[ "$OUT" != "$REPO_ROOT" ] || fail "--out is the repo root itself"
case "$REPO_ROOT/" in
  "$OUT/"*) fail "--out CONTAINS the repo tree — refuse (--force would delete the repo): $OUT" ;;
esac
[ "$OUT" != "/" ] || fail "--out is /"
[ "$OUT" != "${HOME:-/nonexistent}" ] || fail "--out is \$HOME itself"
# well-known system directories: a '--out /tmp --force' must never be able to
# empty /tmp — refuse BEFORE the --force clearing below (checked on the
# canonicalized path; macOS /tmp and /var are symlinks and already refused)
case "$OUT" in
  /tmp|/var/tmp|/private/tmp|/private/var/tmp|/private/var|/private|/var|/usr|/usr/local|/etc|/opt|/srv|/home|/Users|/Volumes|/Library|/System|/Applications|/dev|/bin|/sbin)
    fail "--out is a well-known system directory — refuse, even with --force: $OUT" ;;
esac

# non-empty refusal / --force clears CONTENTS only (after the checks above)
if [ -d "$OUT" ] && [ -n "$(ls -A "$OUT" 2>/dev/null)" ]; then
  if [ "$FORCE" -eq 1 ]; then
    echo "egg-export: --force — clearing contents of $OUT"
    find "$OUT" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
  else
    fail "--out is not empty (use --force to clear it): $OUT"
  fi
fi
mkdir -p "$OUT"

# --- fresh cut from HEAD (source repo read-only from here on) -------------------
SRC_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD)"
SRC_COMMIT_DATE="$(git -C "$REPO_ROOT" log -1 --format=%cI HEAD)"  # commit clock, not wall clock
echo "egg-export: cutting HEAD $SRC_COMMIT into $OUT"
git -C "$REPO_ROOT" archive --format=tar HEAD | tar -xf - -C "$OUT"

# --- manifest-driven pass -------------------------------------------------------
# pattern hygiene: relative, no '..', no '**' (bash-3.2-portable — recursive
# needs go through delete-name/expect-absent-name), conservative charset.
_pat_ok() {
  case "$1" in
    /*|*..*|*'**'*|*' '*|'') return 1 ;;
  esac
  case "$1" in
    *[!A-Za-z0-9._/*-]*) return 1 ;;
  esac
  return 0
}

# expand a glob relative to $OUT; prints one match per line (empty if none)
_matches() {
  ( cd "$OUT" && set +f
    # shellcheck disable=SC2086  # glob expansion of the manifest pattern is the point
    set -- $1
    if [ "$#" -gt 0 ] && { [ -e "$1" ] || [ -L "$1" ]; }; then printf '%s\n' "$@"; fi )
}

VERIFY_FAILS=0
verify_fail() { echo "egg-export: VERIFY FAIL — $*" >&2; VERIFY_FAILS=$((VERIFY_FAILS + 1)); }

# keep the leading comment header (comments + blanks, minus stale '# N entries'
# counter lines), drop the body, append the canonical empty body via stdin.
_header_only() {
  local file="$1" tmp
  [ -f "$file" ] || { verify_fail "interface file missing: ${file#"$OUT/"}"; return 0; }
  tmp="$file.egg-tmp"
  awk '
    /^#/ || /^[[:space:]]*$/ {
      if ($0 ~ /^# [0-9]+ entries$/) next
      print; next
    }
    { exit }
  ' "$file" > "$tmp"
  cat >> "$tmp"
  mv "$tmp" "$file"
}

t_interfaces_header_only() {
  local dir="$OUT/shared/interfaces" f rel
  _header_only "$dir/captain-vetoes.yml" <<'EOF'
version: 1
next_id: 1
vetoes: []
EOF
  _header_only "$dir/captain-rules-index.yaml" <<'EOF'
# 0 entries (emptied at egg export per R116 — captain rules are instance data;
# a live deployment regenerates this via cabinet/scripts/captain-rules/index.sh)
entries: []
EOF
  _header_only "$dir/captain-knowledge-classification.yml" <<'EOF'
# (classification entries emptied at egg export per R116 — captain knowledge
#  is instance data; the header above is the shipped interface contract)
EOF
  # fail-closed R116: only the known interface set may ship
  while IFS= read -r f; do
    rel="${f#"$OUT/"}"
    case "$rel" in
      shared/interfaces/captain-vetoes.yml) : ;;
      shared/interfaces/captain-rules-index.yaml) : ;;
      shared/interfaces/captain-knowledge-classification.yml) : ;;
      shared/interfaces/deployment-status.md) : ;;
      shared/interfaces/*/.gitkeep) : ;;
      *) verify_fail "unexpected shared/interfaces file (add a manifest rule): $rel" ;;
    esac
  done < <(find "$dir" -type f | sort)
}

t_plans_archive() {
  local dir="$OUT/docs/plans" entry base
  [ -d "$dir" ] || { verify_fail "docs/plans missing from archive cut"; return 0; }
  for entry in "$dir"/* "$dir"/.[!.]*; do
    [ -e "$entry" ] || continue
    base="$(basename "$entry")"
    case "$base" in
      cabinet-axes-spec-2026-07-05.md) : ;;          # germline-pinned normative spec
      evolution-engine-spec-2026-07-05.md) : ;;      # germline-pinned normative spec
      sovereign-build-spec-2026-07-04.md) : ;;       # germline-pinned normative spec
      *) rm -rf "$entry" ;;
    esac
  done
  cat > "$dir/ARCHIVED-NOTE.md" <<'EOF'
# docs/plans — archived at egg export (R145)

The launching deployment's planning and coordination documents (migration
plans, execution-status ledgers, and the operative-egg plan/ledger pair that
drove the packaging itself) are INSTANCE artifacts: they are archived out of
the public egg at export time and stay with the source instance.

What remains here is the NORMATIVE spec set pinned by germline artifacts:

- cabinet-axes-spec-2026-07-05.md
- evolution-engine-spec-2026-07-05.md
- sovereign-build-spec-2026-07-04.md

R167 amendment (2026-07-15): source-adapter-boundary-2026-07-05.md dropped
from this keep-list — it is a dated screenpipe-coupling CENSUS (the same
"instance history" class this rule already archives rather than rewords),
nothing in the shipped egg requires its presence, and it carried the
launching deployment's vault-path literals. It archives like the rest of
docs/plans instead of shipping un-scrubbed.
EOF
}

# PC-E (Wave-E integrator, R162): the DATED framework/docs design snapshots
# are instance history — authored on the launching deployment, they cite its
# absolute paths, live lane names and the Captain by name throughout, and
# rewording a dated design record would falsify it (same doctrine as R145).
# The undated LIVING contract docs (work-model.md — cited by the shipping
# guide —, consequence-ledger.md, outcome-watchdog.md) stay and are scrubbed
# at source instead.
t_framework_docs_archive() {
  local dir="$OUT/framework/docs" entry base
  [ -d "$dir" ] || { verify_fail "framework/docs missing from archive cut"; return 0; }
  for entry in "$dir"/*; do
    [ -e "$entry" ] || continue
    base="$(basename "$entry")"
    case "$base" in
      *-2026-*.md) rm -f "$entry" ;;   # dated design snapshot — instance history
      *) : ;;                          # living contract docs ship
    esac
  done
  cat > "$dir/ARCHIVED-NOTE.md" <<'EOF'
# framework/docs — dated design snapshots archived at egg export (R162)

The launching deployment's DATED design documents (authority-matrix,
fidelity-harness, cohesive-architecture, meta-cognition direction snapshots)
are instance history: they cite that deployment's absolute paths, live lane
names and its Captain throughout, and stay with the source instance. Code
comments citing them by filename refer to that instance's design record.

The undated LIVING contract docs ship here unchanged:

- work-model.md (the work-classes contract the guide references)
- consequence-ledger.md
- outcome-watchdog.md
EOF
}

# R167 (personal-clean wave, 2026-07-15): fills the gap R146 named but never
# implemented — "non-amendment proposals (calendar runbooks etc.) archive."
# The 18 docs/proposals/germline-amendment-*.md docs are ratified FOUNDING
# AMENDMENTS (R031/R146: frozen constitutional record, same class as
# LICENSE's copyright line — never reworded) and ship verbatim; every other
# file in docs/proposals/ (addenda, activation runbooks — no ratified ship
# requirement) is instance history and archives with a stub, same shape as
# t_plans_archive / t_framework_docs_archive.
t_proposals_archive() {
  local dir="$OUT/docs/proposals" entry base
  [ -d "$dir" ] || { verify_fail "docs/proposals missing from archive cut"; return 0; }
  for entry in "$dir"/*; do
    [ -e "$entry" ] || continue
    base="$(basename "$entry")"
    case "$base" in
      germline-amendment-*.md) : ;;   # ratified founding amendment — ships verbatim
      *) rm -f "$entry" ;;
    esac
  done
  cat > "$dir/ARCHIVED-NOTE.md" <<'EOF'
# docs/proposals — non-amendment proposals archived at egg export (R146/R167)

R146 ratified that `docs/proposals/germline-amendment-*.md` docs ship as
FOUNDING AMENDMENTS — a frozen constitutional record of how this instance's
germline was amended over time (same class as LICENSE's copyright line:
rewording would falsify a ratified decision). Every other file here (addenda,
activation runbooks — no ratified ship requirement, and several cited the
launching deployment's absolute paths / real employer domains) is instance
history: archived out of the public egg at export time, same shape as
docs/plans (R145) and framework/docs (R162).

The founding amendments ship unchanged in this directory.
EOF
}

t_ci_retarget_master() {
  local wf tmp bad
  for wf in "$OUT"/.github/workflows/*.yml "$OUT"/.github/workflows/*.yaml; do
    [ -f "$wf" ] || continue
    tmp="$wf.egg-tmp"
    # bracketed trigger form first, THEN any remaining prose/comment mention
    # of the private integration branch (instance history must not name it)
    awk '{ gsub(/\[master, feat\/fidelity-harness-design\]/, "[master]");
           gsub(/feat\/fidelity-harness-design/, "the pre-export integration branch");
           print }' "$wf" > "$tmp"
    mv "$tmp" "$wf"
    # fail-closed: every branch-trigger line must now be exactly [master]
    bad="$(grep -nE '^[[:space:]]*branches:' "$wf" | grep -v 'branches: \[master\]' || true)"
    if [ -n "$bad" ]; then
      verify_fail "CI trigger not retargeted to [master] in ${wf#"$OUT/"}: $bad"
    fi
    # fail-closed: the private branch name must be gone everywhere in the file
    if grep -q 'fidelity-harness-design' "$wf"; then
      verify_fail "private integration-branch name survived in ${wf#"$OUT/"}"
    fi
  done
}

# keep only the named survivors inside a directory (top-level entries)
_prune_dir_keep() {
  local dir="$1"; shift
  local entry base keep k
  [ -d "$dir" ] || { verify_fail "expected directory missing: ${dir#"$OUT/"}"; return 0; }
  for entry in "$dir"/* "$dir"/.[!.]*; do
    [ -e "$entry" ] || continue
    base="$(basename "$entry")"
    keep=0
    for k in "$@"; do [ "$base" = "$k" ] && keep=1; done
    [ "$keep" -eq 1 ] || rm -rf "$entry"
  done
}

# R124 + Wave G (lane-name instance-split): _default.yml stays, plus the two
# synthetic Testburg lane-declaration .example twins — the fresh-hatch model
# for the lane resolvers (env.lanes() / lanes.sh cabinet_lanes / dashboard
# declaredLanes()). `.example` matches no *.yml glob: never a live lane.
t_contexts_prune()       { _prune_dir_keep "$OUT/instance/config/contexts" "_default.yml" "bakery-site.yml.example" "newsletter.yml.example"; }
t_projects_prune()       { _prune_dir_keep "$OUT/instance/config/projects" "_template.yml"; }
t_officer_skills_prune() { _prune_dir_keep "$OUT/instance/officer-skills" "README.md"; }

# R126 + germline lockstep: ship the scrubbed .example twin's bytes AS
# act-first-surfaces.yml (a wired germline FILES entry the lockstep suite
# requires on disk; the twin ships empty/unratified and is fail-closed by
# its own corruption-honesty contract).
t_act_first_default() {
  local ex="$OUT/instance/config/act-first-surfaces.yml.example"
  [ -f "$ex" ] || { verify_fail "act-first-surfaces.yml.example missing — cannot materialize the shipped default"; return 0; }
  cp "$ex" "$OUT/instance/config/act-first-surfaces.yml"
}

# R120 + R126-class, gate (b) null-hatch fix: instance/config/egress.yml is
# ALSO a wired germline FILES entry (framework/tests/
# test_germline_lockstep_consistency.py::test_wired_locked_entries_exist_on_disk
# requires it on disk — it is not in that test's deployment-created
# exemptions), and that suite runs INSIDE null-hatch.sh (gate b) against the
# export tree. The R120 delete above (this Captain's real enforced-egress
# ruling) previously left the export with NO file at that path at all,
# bricking gate (b) exactly like the gate-apply.plist case above. Same fix
# shape as act-first-default: ship the already-fail-closed .example twin's
# bytes (enforce: true, empty allow_hosts) AS the live file — a fresh egg
# gets a safe default and must apply its own allowlist during hatch, per the
# R120 comment above.
t_egress_default() {
  local ex="$OUT/instance/config/egress.yml.example"
  [ -f "$ex" ] || { verify_fail "egress.yml.example missing — cannot materialize the shipped default"; return 0; }
  cp "$ex" "$OUT/instance/config/egress.yml"
}

t_bin_mount() {
  mkdir -p "$OUT/bin"
  : > "$OUT/bin/.gitkeep"
}

# PC-E scrub-paths: the static committed cabinet/launchd/*.plist files are
# THIS deployment's rendered artifacts (absolute /Users/... paths, the live
# officer roster, incl. the germline-locked gate-apply plist) and are
# live-consumed via ~/Library/LaunchAgents copies — never edited for scrub.
# The egg ships the portable .template.plist twins + officer-entitlements
# (generic hardened-runtime entitlements) + INSTALL-flip.md (scrubbed doc);
# a fresh deployment renders its fleet from cabinet/services.yml
# (generate-plists.py) and the templates (deploy-mac.sh).
t_launchd_portable_only() {
  local dir="$OUT/cabinet/launchd" f base plists
  [ -d "$dir" ] || { verify_fail "cabinet/launchd missing from archive cut"; return 0; }
  # collect-then-delete: enumerate BEFORE unlinking so rm never mutates the
  # directory an open find stream is still reading (readdir-mutation skips;
  # the recursive fail-closed sweep below would catch a miss, but the delete
  # loop should not rely on it)
  plists="$(find "$dir" -maxdepth 1 -type f -name '*.plist' | sort)"
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    base="$(basename "$f")"
    case "$base" in
      *.template.plist) : ;;               # portable twins ship
      officer-entitlements.plist) : ;;     # generic entitlements — ships
      com.cabinet.gate-apply.plist)
        # GERMLINE-LOCKSTEP EXCEPTION (R160 amendment, Wave-E integrator):
        # this DARK root-daemon definition is a WIRED germline FILES entry —
        # the export's own lockstep suite (test_germline_lockstep_
        # consistency.py, run by gate (b) null-hatch) requires it ON DISK
        # and enumerated as the one LaunchDaemons plist, so deleting it
        # bricked gate (b). It ships PORTABLE-DARK instead: instance-absolute
        # paths rewritten to the deploy-mac envsubst placeholders (the
        # .template.plist convention), DARK semantics (Disabled=true,
        # RunAtLoad=false, Label, ritual comment) byte-preserved. sed writes
        # an .egg-tmp sibling inside --out, mv'd into place (safety
        # contract). Content is fail-closed verified below. The germline-
        # locked SOURCE plist is never touched.
        sed -E \
          -e 's|/Users/[^/<"]+/captains-cabinet|${REPO_ROOT}|g' \
          -e 's|/Users/[^/<"]+/|${HOME}/|g' \
          "$f" > "$f.egg-tmp" && mv "$f.egg-tmp" "$f" \
          || verify_fail "gate-apply portable rewrite failed"
        ;;
      *.plist) rm -f "$f" ;;               # rendered live artifact — leaves
      *) : ;;                              # non-plist files (docs) ship
    esac
  done <<< "$plists"
  # fail-closed: the portable set must have survived, the rendered set must
  # not. The verification sweep is RECURSIVE (unlike the top-level delete
  # loop above): a future TRACKED plist in any cabinet/launchd subdirectory
  # fails the export until a manifest rule adjudicates it — it can never
  # ship unchecked. (cabinet/launchd/generated/ is gitignored today, so no
  # rendered output reaches a HEAD cut; this guards the rule, not the path.)
  [ -f "$dir/com.cabinet.officer.template.plist" ] \
    || verify_fail "officer template plist must ship: cabinet/launchd/com.cabinet.officer.template.plist"
  [ -f "$dir/officer-entitlements.plist" ] \
    || verify_fail "entitlements plist must ship: cabinet/launchd/officer-entitlements.plist"
  # gate-apply portable-dark content contract: present, no absolute home
  # path survived the rewrite, placeholder present, DARK flag key intact
  local ga="$dir/com.cabinet.gate-apply.plist"
  if [ ! -f "$ga" ]; then
    verify_fail "gate-apply portable-dark plist must ship: cabinet/launchd/com.cabinet.gate-apply.plist"
  else
    if grep -q '/Users/' "$ga"; then
      verify_fail "gate-apply plist still carries an absolute home path after the portable rewrite"
    fi
    grep -q '{REPO_ROOT}' "$ga" \
      || verify_fail "gate-apply plist rewrite did not produce the REPO_ROOT placeholder"
    grep -q '<key>Disabled</key>' "$ga" \
      || verify_fail "gate-apply plist lost its Disabled key — DARK contract broken"
  fi
  while IFS= read -r f; do
    base="$(basename "$f")"
    case "$base" in
      *.template.plist|officer-entitlements.plist|com.cabinet.gate-apply.plist) : ;;
      *) verify_fail "rendered live plist survived the pass: ${f#"$OUT/"}" ;;
    esac
  done < <(find "$dir" -type f -name '*.plist' | sort)
}

# PC-E scrub-paths: the repo-root CLAUDE.md is officer-loaded LIVE deployment
# context (deployment facts, absolute paths, live lane names) — never
# semantically edited for scrub (live-coupling rule). The egg ships the
# captain-agnostic operating context docs/templates/CLAUDE-egg.md AS
# CLAUDE.md instead. Until the template is tracked at HEAD the swap cannot
# fire on a fresh cut — print a LOUD note rather than fail (the publish gate
# stays the fail-closed backstop: an unswapped live CLAUDE.md is gate-RED).
t_claude_egg_swap() {
  local tpl="$OUT/docs/templates/CLAUDE-egg.md"
  if [ -f "$tpl" ]; then
    mv "$tpl" "$OUT/CLAUDE.md"
    rmdir "$OUT/docs/templates" 2>/dev/null || true
  else
    echo "egg-export: NOTE — docs/templates/CLAUDE-egg.md not in HEAD yet; CLAUDE.md ships UNSWAPPED (pre-integration cut; publish gate will flag it)"
  fi
}

t_instance_verify() {
  local f rel bad=0
  [ -d "$OUT/instance" ] || { verify_fail "instance/ missing from export"; return 0; }
  while IFS= read -r f; do
    rel="${f#"$OUT/"}"
    case "$rel" in
      *.example) : ;;                                    # R120: twins ship
      */.gitkeep) : ;;                                   # structure
      instance/config/contexts/_default.yml) : ;;        # R124 keep
      instance/config/projects/_template.yml) : ;;       # R125 keep
      instance/config/act-first-surfaces.yml) : ;;       # R126: materialized from the .example twin (act-first-default)
      instance/config/egress.yml) : ;;                   # R120/R126-class: materialized from the .example twin (egress-default, gate-b fix)
      instance/config/policies/*) : ;;                   # R123 germ-keep
      instance/config/posture-presets/*) : ;;            # R122 germ-keep
      instance/officer-skills/README.md) : ;;            # surface doc
      *) echo "egg-export: LIVE INSTANCE FILE SURVIVED THE PASS: $rel" >&2; bad=$((bad + 1)) ;;
    esac
  done < <(find "$OUT/instance" -type f | sort)
  [ "$bad" -eq 0 ] || verify_fail "$bad non-structural file(s) under instance/ — extend the manifest, never ship live values"
}

run_transform() {
  case "$1" in
    interfaces-header-only) t_interfaces_header_only ;;
    plans-archive)          t_plans_archive ;;
    framework-docs-archive) t_framework_docs_archive ;;
    proposals-archive)      t_proposals_archive ;;
    ci-retarget-master)     t_ci_retarget_master ;;
    contexts-prune)         t_contexts_prune ;;
    projects-prune)         t_projects_prune ;;
    officer-skills-prune)   t_officer_skills_prune ;;
    act-first-default)      t_act_first_default ;;
    egress-default)         t_egress_default ;;
    bin-mount)              t_bin_mount ;;
    launchd-portable-only)  t_launchd_portable_only ;;
    claude-egg-swap)        t_claude_egg_swap ;;
    instance-verify)        t_instance_verify ;;
    *) fail "unknown transform in manifest: '$1'" ;;
  esac
}

DELETES=0
TRANSFORMS=""
lineno=0
while IFS= read -r line || [ -n "$line" ]; do
  lineno=$((lineno + 1))
  case "$line" in ''|'#'*) continue ;; esac
  directive="${line%% *}"
  arg="${line#* }"
  [ "$arg" != "$line" ] || arg=""
  case "$directive" in
    delete)
      _pat_ok "$arg" || fail "manifest:$lineno bad pattern '$arg'"
      while IFS= read -r m; do
        [ -n "$m" ] || continue
        rm -rf "$OUT/$m"
        DELETES=$((DELETES + 1))
      done < <(_matches "$arg")
      ;;
    delete-name)
      _pat_ok "$arg" || fail "manifest:$lineno bad name '$arg'"
      case "$arg" in */*|*'*'*) fail "manifest:$lineno delete-name takes a bare basename: '$arg'" ;; esac
      while IFS= read -r m; do
        [ -n "$m" ] || continue
        rm -rf "$m"
        DELETES=$((DELETES + 1))
      done < <(find "$OUT" -name "$arg" -prune 2>/dev/null)
      ;;
    transform)
      run_transform "$arg"
      TRANSFORMS="$TRANSFORMS $arg"
      ;;
    expect-present)
      _pat_ok "$arg" || fail "manifest:$lineno bad path '$arg'"
      [ -e "$OUT/$arg" ] || verify_fail "expected in export but missing: $arg"
      ;;
    expect-absent)
      _pat_ok "$arg" || fail "manifest:$lineno bad pattern '$arg'"
      m="$(_matches "$arg")"
      [ -z "$m" ] || verify_fail "must not ship but present: $m"
      ;;
    expect-absent-name)
      _pat_ok "$arg" || fail "manifest:$lineno bad name '$arg'"
      m="$(find "$OUT" -name "$arg" -prune 2>/dev/null | head -5 || true)"
      [ -z "$m" ] || verify_fail "must not ship but present (by name '$arg'): $m"
      ;;
    *)
      fail "manifest:$lineno unknown directive '$directive'"
      ;;
  esac
done < "$MANIFEST"

# --- egg-manifest.json + summary ------------------------------------------------
FILE_COUNT="$(find "$OUT" -type f ! -name egg-manifest.json | wc -l | tr -d ' ')"
RULE_IDS="$(grep -oE 'R[0-9]{3}' "$MANIFEST" | sort -u || true)"
RULES_JSON=""
for r in $RULE_IDS; do RULES_JSON="$RULES_JSON\"$r\", "; done
for t in $TRANSFORMS; do RULES_JSON="$RULES_JSON\"transform:$t\", "; done
RULES_JSON="${RULES_JSON%, }"

cat > "$OUT/egg-manifest.json" <<EOF
{
  "artifact": "captains-cabinet egg (fresh-cut export, never a repo flip)",
  "source_commit": "$SRC_COMMIT",
  "source_commit_date": "$SRC_COMMIT_DATE",
  "file_count": $FILE_COUNT,
  "applied_rules": [$RULES_JSON],
  "exporter": "cabinet/scripts/egg-export.sh",
  "exclusion_manifest": "cabinet/scripts/egg-export-manifest.txt (private-side, not shipped)",
  "publish_gate": "cabinet/scripts/egg-publish-gate.sh must be GREEN; publishing remains CG-7 Captain-gated regardless"
}
EOF

echo "-------------------------------------------------------------------------"
echo "egg-export summary"
echo "  source commit : $SRC_COMMIT ($SRC_COMMIT_DATE)"
echo "  export dir    : $OUT"
echo "  files shipped : $FILE_COUNT (+ egg-manifest.json)"
echo "  deletes       : $DELETES path(s) removed by manifest rules"
echo "  transforms    :${TRANSFORMS}"
echo "  rules encoded : $(echo "$RULE_IDS" | tr '\n' ' ')"
if [ "$VERIFY_FAILS" -gt 0 ]; then
  echo "  VERIFY        : $VERIFY_FAILS FAILURE(S) — export is NOT a valid egg" >&2
  echo "-------------------------------------------------------------------------"
  exit 1
fi
echo "  verify        : PASS (all expect-present/expect-absent rules hold)"
echo "  next          : bash cabinet/scripts/egg-publish-gate.sh --export $OUT"
echo "  REMINDER      : publishing remains CG-7 Captain-gated."
echo "-------------------------------------------------------------------------"
