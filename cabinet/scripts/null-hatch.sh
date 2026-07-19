#!/usr/bin/env bash
# null-hatch.sh — Proof-1: the NULL HATCH (operative-egg plan row A15, proof row P1, decision D2).
#
# ONE named runnable gate composing the two existing clean-room proofs:
#   * the Testburg render      (clean-room-foundation CI job: launcher-agnostic
#     ratchet + runtime identity proof — framework renders "Testburg"/"Captain",
#     never a baked-in captain), and
#   * the clean-room source job (SRC-5: no source binding + unreadable
#     ~/.screenpipe ⇒ resolver fail-closed to NullPersonalSource, honest
#     empties everywhere, framework CORE imports + null-path suite subset).
#
# The claim it proves: the egg boots with NO captain data, NO screenpipe, NO
# instance source binding, adapters absent → NullPersonalSource honest-empties
# everywhere. Exit 0 = Proof 1 holds.
#
# Hermetic by construction — safe on a LIVE deployment box:
#   * the proof runs against a sandbox copy of the COMMITTED tree
#     (`git archive HEAD`), never the working tree — on a clean checkout (CI)
#     the two are identical, which is exactly the P1 acceptance condition;
#   * HOME is redirected to a throwaway dir whose ~/.screenpipe is
#     present-but-UNREADABLE (mode 000), so a latent screenpipe/vault read
#     anywhere in framework CORE raises PermissionError LOUDLY instead of
#     passing by accident on a box where the path merely doesn't exist;
#   * CABINET_ROOT / PYTHONPATH / CABINET_* env are scrubbed so the live
#     deployment root cannot leak into the clean-room premise
#     (framework/env.py: the CABINET_ROOT env var wins over file-relative
#     resolution).
#
# Usage: bash cabinet/scripts/null-hatch.sh        (PYTHON=... to pin interpreter)
# Wired as the `null-hatch` job in .github/workflows/cabinet-ci.yml.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# --- interpreter ------------------------------------------------------------
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for cand in python3.12 python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
  done
fi
if [ -z "$PY" ]; then
  echo "null-hatch: FAIL — no python interpreter found (set PYTHON=...)" >&2
  exit 1
fi
if ! "$PY" -c "import pytest, yaml" >/dev/null 2>&1; then
  echo "null-hatch: FAIL — $PY lacks pytest/pyyaml (pip install pytest pyyaml)" >&2
  exit 1
fi

# --- throwaway sandbox (repo copy + fake HOME) --------------------------------
WORK="$(mktemp -d "${TMPDIR:-/tmp}/null-hatch.XXXXXX")"
cleanup() {
  # the sandbox deliberately contains a mode-000 dir; reopen before removal
  chmod -R u+rwX "$WORK" 2>/dev/null || true
  rm -rf "$WORK" 2>/dev/null || true
}
trap cleanup EXIT

EGG="$WORK/egg"
mkdir -p "$EGG" "$WORK/home"
# Export the tree into the sandbox. Prefer `git archive HEAD` (committed tree,
# excludes .gitignored runtime cruft) when REPO_ROOT is a git work tree. But a
# DELIVERED egg has no .git, and hatch.sh --clean-room's own scratch export is
# likewise gitless — there `git archive` dies "not a git repository" and the
# whole clean-room proof fails at proof-a. Fall back to a straight tree copy
# (minus VCS metadata) so the proof runs on the egg exactly as a stranger gets
# it. The env scrub + unreadable ~/.screenpipe below still enforce the
# clean-room premise regardless of export path.
if git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git -C "$REPO_ROOT" archive --format=tar HEAD | tar -xf - -C "$EGG"
else
  tar -cf - -C "$REPO_ROOT" --exclude='./.git' . | tar -xf - -C "$EGG"
fi

export HOME="$WORK/home"

# scrub the live deployment out of the environment (clean-room premise)
while IFS='=' read -r _name _; do
  case "$_name" in CABINET_*) unset "$_name" 2>/dev/null || true ;; esac
done < <(env)
unset PYTHONPATH 2>/dev/null || true

# ~/.screenpipe present-but-UNREADABLE (stronger than absent — a latent read
# raises PermissionError loudly instead of passing on a bare box)
mkdir -p "$HOME/.screenpipe"
: > "$HOME/.screenpipe/POISON"
chmod 000 "$HOME/.screenpipe/POISON"
chmod 000 "$HOME/.screenpipe"
if ls "$HOME/.screenpipe" >/dev/null 2>&1; then
  echo "null-hatch: FAIL — expected \$HOME/.screenpipe to be present-but-unreadable" >&2
  exit 1
fi

# adapters absent: no personal-source binding in the sandbox instance
cd "$EGG"
rm -f instance/config/sources.yml
if [ -e instance/config/sources.yml ]; then
  echo "null-hatch: FAIL — instance/config/sources.yml still present" >&2
  exit 1
fi
echo "null-hatch: sandbox staged (committed tree, no sources.yml, poisoned \$HOME/.screenpipe)"

# --- stage 1/4 · Testburg render (launcher-agnostic ratchet + runtime identity)
echo "null-hatch: [1/4] Testburg render — identity is launcher-driven, not baked"
"$PY" -m pytest framework/tests/test_no_launcher_hardcode.py framework/tests/test_clean_room.py -q

# --- stage 2/4 · null personal-source imports + runs without crash ------------
echo "null-hatch: [2/4] NullPersonalSource honest-empties + null dispatch no-ops"
"$PY" - <<'PY'
import framework.sources as S
src = S.get_source()
assert type(src).__name__ == "NullPersonalSource", type(src).__name__
assert src.available() is False
assert src.search("anyone") == {"hits": [], "topic_terms": None}
assert src.find_reply_candidates() == []
assert src.person_intel("x") == "" and src.voice_profile() == ""
assert src.model_patterns() == "" and src.open_commitments("owed_by") == []
assert src.drafting_lessons("2026-01-01T00:00:00Z") == ""
raised = False
try:
    src.read_note("anything")
except FileNotFoundError:
    raised = True
assert raised, "read_note must raise FileNotFoundError on the null source"
d = S.NullPersonalDispatch()
assert d.queue_draft() is None and d.deliver() is None
assert d.append_note("x", "y") is None and d.log_reasoning() is None
print("OK: clean-room null source imports + runs without crash")
PY

# --- stage 3/4 · framework CORE modules import under the null source ----------
echo "null-hatch: [3/4] framework CORE import slice under the null source"
"$PY" - <<'PY'
import importlib
import framework.sources as S
assert type(S.get_source()).__name__ == "NullPersonalSource"
mods = [
    "framework.env", "framework.sources.base", "framework.sources.null",
    "framework.acting.action_lane", "framework.acting.lane_dedup",
    "framework.fidelity.benchmark", "framework.fidelity.retro",
    "framework.frontdoor.chair_drafts", "framework.frontdoor.daily_recap",
    "framework.frontdoor.action_exec", "framework.frontdoor.actfirst_canary",
    "framework.frontdoor.binder_wire", "framework.frontdoor.morning_synthesis",
    "framework.watchdog.registry", "framework.watchdog.check",
    "framework.authority.posture", "framework.authority.matrix",
    "framework.evolution.contracts",
]
for m in mods:
    importlib.import_module(m)
print("OK: %d framework CORE modules import under the null source" % len(mods))
PY

# --- stage 4/4 · null-path suite subset (meta-ratchets + resolver, no data dep)
echo "null-hatch: [4/4] null-path suite subset + enduring cognitive architecture gate"
"$PY" -m pytest framework/sources framework/tests -q
CABINET_PYTHON="$PY" bash cabinet/scripts/verify-cognitive-architecture.sh

echo "null-hatch: PROOF 1 — NULL HATCH: PASS (egg boots with no captain data, no screenpipe, no instance source, adapters absent)"
