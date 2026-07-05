#!/bin/bash
# grant-apply.sh — the ONE writer of instance/config/standing-grants.yml (D7).
#
# A standing grant changes ONLY here, in a Captain unlock window: the Telegram
# binder's `grant NEED-<hex>` verb marks the need `approved_pending_apply` and
# renders this one paste — it can never write the grants file itself (the
# Telegram-sealed grant writer was KILLED: a chat session must never be a
# network-reachable authority-minting credential).
#
#   sudo bash cabinet/scripts/grant-apply.sh NEED-<8hex> [--ceiling-ack]
#
# Sequence (D7): root re-exec guard → load the NEED from the ledger → refuse
# unless approved_pending_apply → refuse scope-mismatch vs the recorded need
# (a tampered/widened proposed_grant_line cannot apply) → refuse a ceiling
# class without --ceiling-ack (all grants are ceilings-only, so this is the
# deliberate root-side confirmation — the machine-effective scope prints FIRST
# and the ack is a re-run, never a default) → SCOPED germline unlock of the
# grants file only (the estate stays locked/postured) → append → validate the
# whole file via grants.py's own validators (ABORT + byte-identical RESTORE on
# any failure) → commit → re-lock → mark(granted) → receipt.
#
# Structural ACT-AND-DRAFT refusal: an external_comms grant applies only when
# the ATTESTED posture ruling says flavor=org — the Captain's personal outbound
# surfaces keep per-item approval in every posture.
#
# Exit codes: 0 applied · 2 usage · 3 need-state refusal · 4 scope/ack/flavor
# refusal · 5 post-append validation failed (file restored).
#
# TEST MODE (CABINET_GRANT_APPLY_TEST=1): skips the root re-exec, the germline
# unlock/lock and the git commit ONLY — every refusal + restore path runs
# non-root against a CABINET_ROOT-pointed tmp tree (the SOV-6 tests).
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"

TEST_MODE="${CABINET_GRANT_APPLY_TEST:-0}"
NEED_ID=""
ACK=0
usage() {
  echo "usage: sudo bash cabinet/scripts/grant-apply.sh NEED-<8hex> [--ceiling-ack]" >&2
}
for a in "$@"; do
  case "$a" in
    --ceiling-ack) ACK=1 ;;
    -h|--help) usage; exit 0 ;;
    *)
      if [ -z "$NEED_ID" ]; then NEED_ID="$a"
      else echo "REFUSED: unexpected argument '$a'" >&2; usage; exit 2; fi ;;
  esac
done
# Strict id shape BEFORE anything runs — the binder grammar's hex-only ids.
case "$NEED_ID" in
  NEED-[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;;
  *) echo "REFUSED: need id must be NEED-<8 lowercase hex> (got: '${NEED_ID:-<none>}')" >&2
     usage; exit 2 ;;
esac

# Root re-exec guard: schg + the grants file demand root; a plain invocation
# self-elevates so the binder's one paste works with or without the sudo prefix.
if [ "$TEST_MODE" != "1" ] && [ "$(id -u)" != "0" ]; then
  exec sudo bash "$0" "$@"
fi

export PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}"
PY=python3.12
GRANTS_REL="instance/config/standing-grants.yml"

_driver() { "$PY" - "$1" "$NEED_ID" "$ACK" <<'PYEOF'
"""grant-apply driver — phases: check | apply | mark.

Validation reuses framework.authority.grants' OWN validators (one source of
row truth); the need is read from the FI-3 ledger. The machine-effective
scope prints at the ROOT step from the machine grant line only — never the
requester's why prose (poisoned-need fix, same rule as the digest/receipt).
"""
import os
import re
import sys

phase, need_id, ack = sys.argv[1], sys.argv[2], sys.argv[3] == "1"

import yaml
from framework.authority import grants, needs

ROOT = os.environ.get("CABINET_ROOT") or None


def die(code: int, msg: str) -> None:
    print("REFUSED: " + msg, file=sys.stderr)
    sys.exit(code)


def load_checked():
    """The (need_row, grant_doc, grant_line) triple, every refusal enforced.
    Re-run in EVERY phase (cheap, and TOCTOU-safe across the unlock window)."""
    row = needs._merged(needs.ledger_path(ROOT)).get(need_id)
    if row is None:
        die(3, f"unknown need id {need_id} — nothing recorded in the ledger")
    if row.get("status") != "approved_pending_apply":
        die(3, f"need {need_id} status is '{row.get('status')}' — only "
               f"approved_pending_apply applies (reply `grant {need_id}` "
               "on Telegram first)")
    if row.get("kind") != "standing_grant":
        die(3, f"need {need_id} kind is '{row.get('kind')}' — grant-apply.sh "
               "writes standing grants only; fulfil this kind manually")
    if row.get("deployment") != needs.cabinet_id():
        die(3, f"need {need_id} was filed for deployment "
               f"'{row.get('deployment')}' — this machine is "
               f"'{needs.cabinet_id()}'")
    line = (row.get("proposed_grant_line") or "").strip()
    if not line:
        die(3, "need has no proposed_grant_line — author the grant row by "
               "hand in an unlock window")
    try:
        doc = yaml.safe_load(line[2:] if line.startswith("- ") else line)
    except Exception as exc:
        die(3, f"proposed_grant_line unparseable: {exc}")
    if not isinstance(doc, dict):
        die(3, "proposed_grant_line is not a mapping")
    err = grants._row_error(doc)
    if err:
        die(3, f"grant row invalid: {err}")
    expires = grants._to_dt(doc.get("expires"))
    if expires is None or grants._now() >= expires:
        die(3, "grant line already expired — re-file the need for a fresh "
               "90d window")

    # SCOPE-MISMATCH vs the recorded need: the appendable line must be exactly
    # the NARROWEST row for the blocked step — a widened/tampered ledger line
    # (extra action_types, extra lanes, foreign basis) cannot apply.
    checks = [
        (doc.get("risk_class") == row.get("risk_class"), "risk_class"),
        (doc.get("action_types") == [row.get("action_type")], "action_types"),
        (doc.get("lanes") == [row.get("lane")], "lanes"),
        (doc.get("deployment") == row.get("deployment"), "deployment"),
        (doc.get("basis") == need_id, "basis"),
    ]
    bad = [name for ok, name in checks if not ok]
    if bad:
        die(4, "scope-mismatch vs the recorded need on: " + ", ".join(bad)
               + " — refusing (never widen; file a fresh need for a "
               "different scope)")

    # Machine-effective scope, printed at the ROOT step (never why-prose).
    scope = doc.get("scope") or {}
    rc = doc["risk_class"]
    if rc == "external_comms":
        eff = "to " + (", ".join(scope.get("recipient_allowlist") or [])
                       or "NO recipients (inert)")
    elif rc == "spend":
        eff = f"max {scope.get('max_eur_per_day')} EUR/day"
    else:
        eff = "vendors: " + (", ".join(scope.get("vendor_allowlist") or [])
                             or "NONE (inert)")
    print(f"GRANT {doc['id']}: {', '.join(doc['action_types'])} ({rc}), "
          f"lanes {', '.join(doc['lanes'])}, {eff}, "
          f"max {doc['rate']['max_per_day']}/day, until {doc['expires']}")

    if rc in grants.CEILING_RISK_CLASSES and not ack:
        die(4, f"'{rc}' is a hard-ceiling class — review the scope above, "
               "then confirm with: sudo bash cabinet/scripts/grant-apply.sh "
               f"{need_id} --ceiling-ack")

    if rc == "external_comms":
        # Structural ACT-AND-DRAFT refusal: only an ATTESTED flavor=org ruling
        # may carry external_comms grants (unattested/absent/personal refuse).
        cfg = None
        try:
            from framework.authority import posture
            cfg = posture.load_posture_config(ROOT, file_needs=False)
        except Exception:
            cfg = None
        if not cfg or cfg.get("flavor") != "org":
            die(4, "external_comms grants are structurally refused unless the "
                   "ATTESTED posture ruling says flavor=org (ACT-AND-DRAFT: "
                   "personal outbound keeps per-item Captain approval)")
    return row, doc, line


def validate_file_text(text: str) -> str | None:
    """First violation in a full standing-grants.yml text, or None — the SAME
    shape rules load_grants enforces + grants._row_error per row."""
    try:
        data = yaml.safe_load(text)
    except Exception as exc:
        return f"unparseable YAML: {exc}"
    if (not isinstance(data, dict) or data.get("version") != 1
            or isinstance(data.get("version"), bool)
            or not isinstance(data.get("grants"), list)
            or set(data) - {"version", "grants"}):
        return "file shape must be exactly {version: 1, grants: [...]}"
    for g in data["grants"]:
        err = grants._row_error(g)
        if err:
            gid = g.get("id") if isinstance(g, dict) else "<row>"
            return f"{gid}: {err}"
    return None


row, doc, line = load_checked()
gpath = grants.grants_path(ROOT)

if phase == "check":
    print(f"CHECK OK: {need_id} → {doc['id']} (append target: {gpath})")
    sys.exit(0)

if phase == "apply":
    existed = gpath.exists()
    orig = gpath.read_text() if existed else None
    base = orig if orig is not None else "version: 1\ngrants:\n"
    # Idempotence: a re-pasted apply must never double-append the same grant.
    try:
        cur = yaml.safe_load(base)
    except Exception as exc:
        die(5, f"existing {gpath} is unparseable ({exc}) — repair it in an "
               "unlock window before applying")
    if isinstance(cur, dict) and any(
            isinstance(g, dict) and g.get("id") == doc["id"]
            for g in (cur.get("grants") or [])):
        print(f"APPLY: {doc['id']} already present — nothing appended "
              "(idempotent re-run)")
        sys.exit(0)
    text = re.sub(r"(?m)^grants:\s*\[\s*\]\s*$", "grants:", base)
    if not text.endswith("\n"):
        text += "\n"
    text += "  " + (line if line.startswith("- ") else "- " + line) + "\n"
    err = validate_file_text(text)
    if err is None:
        gpath.parent.mkdir(parents=True, exist_ok=True)
        gpath.write_text(text)
        err = validate_file_text(gpath.read_text())   # validate what LANDED
    if err is not None:
        # ABORT + byte-identical restore — a grants file that fails its own
        # loader's validation must never survive the window.
        if existed:
            gpath.write_text(orig)
        elif gpath.exists():
            gpath.unlink()
        die(5, f"post-append validation failed ({err}) — file restored")
    print(f"APPLY OK: appended {doc['id']} to {gpath}")
    sys.exit(0)

if phase == "mark":
    marked = needs.mark(need_id, "granted", by="grant-apply",
                        reason=doc["id"], root=ROOT)
    if marked is None:
        die(3, f"could not mark {need_id} granted — ledger row vanished?")
    print(f"RECEIPT: {need_id} → granted via {doc['id']}. Remember: the file "
          "is live only after re-lock (schg) — `bash cabinet/scripts/"
          "germline-lock.sh status` must show it locked.")
    sys.exit(0)

die(2, f"unknown phase '{phase}'")
PYEOF
}

# Phase 1 — CHECK (no writes): every refusal fires BEFORE any unlock.
_driver check

if [ "$TEST_MODE" != "1" ]; then
  # SCOPED unlock — the grant window never de-postures the rest of the estate
  # (posture.yml stays locked, so flavor attestation keeps working mid-window).
  if [ -e "$GRANTS_REL" ]; then
    bash cabinet/scripts/germline-lock.sh unlock "$GRANTS_REL"
  fi
  # Whatever happens next, the estate re-arms on exit.
  trap 'bash cabinet/scripts/germline-lock.sh lock >/dev/null 2>&1 || true' EXIT
fi

# Phase 2 — APPLY: append → validate via grants.py's validators → restore on fail.
_driver apply

if [ "$TEST_MODE" != "1" ]; then
  # Commit as the invoking Captain (never root-owned objects), hooks disabled
  # for determinism inside the root window (D15 root-apply precedent).
  GIT_USER="${SUDO_USER:-$(id -un)}"
  if ! sudo -u "$GIT_USER" git -c core.hooksPath=/dev/null diff --quiet -- "$GRANTS_REL" \
     || ! sudo -u "$GIT_USER" git -c core.hooksPath=/dev/null ls-files --error-unmatch "$GRANTS_REL" >/dev/null 2>&1; then
    sudo -u "$GIT_USER" git -c core.hooksPath=/dev/null add "$GRANTS_REL"
    sudo -u "$GIT_USER" git -c core.hooksPath=/dev/null commit -m "grant-apply: $NEED_ID" -- "$GRANTS_REL"
  fi
  bash cabinet/scripts/germline-lock.sh lock
  trap - EXIT
fi

# Phase 3 — MARK: close the need (granted) + receipt.
_driver mark

echo "DONE: $NEED_ID applied."
