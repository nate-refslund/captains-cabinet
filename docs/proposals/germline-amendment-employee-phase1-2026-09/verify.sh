#!/usr/bin/env bash
# verify.sh — the germline bundle's own gate, runnable on the box that owns the
# locked bytes and in any clone of the repo that carries the bundle.
#
# WHY THIS EXISTS. The bundle is a set of PROPOSED bytes for schg-locked files.
# Nothing here may write one. So the only honest thing the bundle can offer the
# Captain before the unlock window is a mechanical answer to three questions,
# asked against the bytes that are actually there:
#
#   1. does each diff still apply to the locked file as it stands right now?
#      (drift ⇒ the bundle is REBUILT, never force-applied);
#   2. is the post-image a syntactically valid shell script?
#   3. did asking cost anything — is every locked path byte-identical after
#      this script ran?
#
# It also re-runs the golden evals, which is the ceremony's behavioural gate;
# that stage needs a Redis endpoint and is the only one --checks-only skips.
#
# ALREADY-APPLIED IS A PASS, NOT A SKIP. G1's bytes are landed on master
# (landed-then-ceremonied, CLAUDE.md §8), so in a clone of master the forward
# patch cannot apply and the REVERSE one can — that is the file already being
# at the target. On the Captain's box the same file is still the pre-image,
# because schg refuses the checkout, and the forward patch applies. Both are
# green; anything else is drift and exits non-zero.
#
# EXIT CODES
#   0   every row verified
#   10  a diff neither applies forward nor is already at the target (drift)
#   11  a post-image failed `bash -n`
#   12  a locked path changed while this script ran
#   13  the golden evals went red
#   64  this host cannot answer the question (no git, no sha256, no parseable
#       locked set, a target missing) — a boundary that cannot be read is
#       never reported as "nothing is locked"
#
# Usage: bash verify.sh [--repo DIR] [--checks-only]
set -u

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd -P)" || exit 64
REPO="$(cd "$SELF_DIR/../../.." && pwd -P)" || exit 64
CHECKS_ONLY=0

while [ $# -gt 0 ]; do
  case "$1" in
    --repo)
      shift
      [ $# -gt 0 ] || { echo "error: --repo needs a directory" >&2; exit 64; }
      REPO="$(cd "$1" 2>/dev/null && pwd -P)" || { echo "error: --repo not a directory: $1" >&2; exit 64; }
      ;;
    --checks-only) CHECKS_ONLY=1 ;;
    -h|--help) sed -n '1,40p' "$0"; exit 0 ;;
    *) echo "error: unknown argument: $1" >&2; exit 64 ;;
  esac
  shift
done

# --- THE BUNDLE TABLE — id | target path | post-image sha256 | state ---------
# Parsed by cabinet/scripts/tests/test_germline_bundle.py so the test and the
# ceremony can never describe different bundles. `landed` = the post-image is
# already on master; `proposed` = these bytes exist only here.
BUNDLE_ROWS="
G1|cabinet/scripts/start-officer-mac.sh|bd5dcd464e9b81b694c5a24d2f66d3db0a61473cbff9804b0606b1656d481345|landed
G3|cabinet/scripts/hooks/session-task-inject.sh|5f2e177b80d0e49949d9bde24b8ee7964aeea21b6281d6699913320e31934297|proposed
"

command -v git >/dev/null 2>&1 || { echo "REFUSED: git absent — no patch applier to ask" >&2; exit 64; }

_sha256() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
  else return 1; fi
}
_sha256 "$0" >/dev/null 2>&1 || { echo "REFUSED: no sha256 tool on this host" >&2; exit 64; }

PY="${CABINET_PYTHON:-python3.12}"
command -v "$PY" >/dev/null 2>&1 || PY=python3

# The locked set comes from the repo's own audited parser (which refuses a
# PARTIAL parse — a smaller boundary is not a boundary). No fallback: a
# boundary this script cannot read is a refusal, never an empty set.
_locked_digest() {
  "$PY" - "$REPO" <<'PYEOF'
import hashlib, sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root / "cabinet" / "scripts" / "lib"))
import update_bundle  # noqa: E402

locked = update_bundle.parse_locked_set(root / "cabinet/scripts/germline-lock.sh")
paths = []
for rel in locked["files"]:
    p = root / rel
    if p.is_file():
        paths.append(p)
for rel in locked["dirs"]:
    d = root / rel
    if d.is_dir():
        paths.extend(q for q in sorted(d.rglob("*")) if q.is_file())
if not paths:
    raise SystemExit("locked set resolved to zero existing paths")
h = hashlib.sha256()
for p in sorted(paths):
    h.update(str(p.relative_to(root)).encode())
    h.update(hashlib.sha256(p.read_bytes()).digest())
print("%s %d" % (h.hexdigest(), len(paths)))
PYEOF
}

LOCKED_BEFORE="$(_locked_digest)" || { echo "REFUSED: cannot read the locked set from $REPO" >&2; exit 64; }
echo "[verify] locked set before: $LOCKED_BEFORE"

SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/germline-bundle-verify.XXXXXX")" || exit 64
trap 'rm -rf "$SCRATCH"' EXIT

RC=0
N_APPLIES=0
N_ALREADY=0
N_ROWS=0

for row in $BUNDLE_ROWS; do
  [ -n "$row" ] || continue
  ID="${row%%|*}"; rest="${row#*|}"
  TARGET="${rest%%|*}"; rest="${rest#*|}"
  WANT_SHA="${rest%%|*}"
  STATE="${rest#*|}"
  N_ROWS=$((N_ROWS + 1))

  DIFF="$SELF_DIR/$ID.diff"
  [ -f "$DIFF" ] || { echo "[verify] $ID FAIL: diff missing at $DIFF" >&2; exit 64; }
  [ -f "$REPO/$TARGET" ] || { echo "[verify] $ID FAIL: target missing at $REPO/$TARGET" >&2; exit 64; }

  WORK="$SCRATCH/$ID"
  mkdir -p "$WORK/$(dirname "$TARGET")" || exit 64
  cp "$REPO/$TARGET" "$WORK/$TARGET" || exit 64

  VERDICT=""
  if ( cd "$WORK" && git apply --check "$DIFF" ) 2>"$SCRATCH/$ID.apply.err"; then
    ( cd "$WORK" && git apply "$DIFF" ) 2>>"$SCRATCH/$ID.apply.err" || { echo "[verify] $ID FAIL: apply --check passed but apply did not" >&2; RC=10; continue; }
    VERDICT="applies"
    N_APPLIES=$((N_APPLIES + 1))
  elif ( cd "$WORK" && git apply --check --reverse "$DIFF" ) 2>>"$SCRATCH/$ID.apply.err"; then
    VERDICT="already-at-target"
    N_ALREADY=$((N_ALREADY + 1))
  else
    echo "[verify] $ID FAIL: $TARGET is neither the pre-image nor the post-image — DRIFT." >&2
    echo "[verify]   rebuild the bundle against the current bytes; never force-apply." >&2
    sed 's/^/[verify]   /' "$SCRATCH/$ID.apply.err" >&2
    RC=10
    continue
  fi

  GOT_SHA="$(_sha256 "$WORK/$TARGET")" || exit 64
  if [ "$GOT_SHA" != "$WANT_SHA" ]; then
    echo "[verify] $ID FAIL: post-image sha256 $GOT_SHA != declared $WANT_SHA" >&2
    RC=10
    continue
  fi

  if ! bash -n "$WORK/$TARGET" 2>"$SCRATCH/$ID.syntax.err"; then
    echo "[verify] $ID FAIL: post-image is not valid shell" >&2
    sed 's/^/[verify]   /' "$SCRATCH/$ID.syntax.err" >&2
    RC=11
    continue
  fi

  echo "[verify] $ID OK ($VERDICT, state=$STATE, post-image sha256 $GOT_SHA) $TARGET"
done

[ "$N_ROWS" -gt 0 ] || { echo "REFUSED: the bundle table parsed to zero rows" >&2; exit 64; }

LOCKED_AFTER="$(_locked_digest)" || { echo "REFUSED: cannot re-read the locked set" >&2; exit 64; }
if [ "$LOCKED_BEFORE" != "$LOCKED_AFTER" ]; then
  echo "[verify] FAIL: a locked path changed while verify.sh ran ($LOCKED_BEFORE -> $LOCKED_AFTER)" >&2
  RC=12
fi
echo "[verify] locked set after:  $LOCKED_AFTER"

if [ "$CHECKS_ONLY" = "1" ]; then
  echo "[verify] golden evals SKIPPED (--checks-only; they need a Redis endpoint)"
else
  if bash "$REPO/cabinet/scripts/run-golden-evals.sh"; then
    echo "[verify] golden evals GREEN"
  else
    echo "[verify] FAIL: golden evals red" >&2
    RC=13
  fi
fi

if [ "$RC" = "0" ]; then
  echo "BUNDLE VERIFY GREEN (rows=$N_ROWS applies=$N_APPLIES already-at-target=$N_ALREADY checks_only=$CHECKS_ONLY)"
else
  echo "BUNDLE VERIFY FAIL (rc=$RC rows=$N_ROWS applies=$N_APPLIES already-at-target=$N_ALREADY)" >&2
fi
exit "$RC"
