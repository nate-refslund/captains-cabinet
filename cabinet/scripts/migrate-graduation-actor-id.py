#!/usr/bin/env python3
"""migrate-graduation-actor-id.py — A14 autonomy-cell id hygiene (one-shot).

WHY (operative-egg plan row A14, Part III step 2 / V 3.6-3): before the
canonical-actor germline batch (2026-07-04), emitters wrote the officer actor
as {"kind": "officer", "id": "officer:cos"}. The ledger/graduation plane
flattens actor to "kind:id" (framework/fidelity/graduation._cell_rows,
consequence.compute_ratios), so those rows landed in cells keyed
"officer:officer:cos" — cells the act-first gate (which composes
"officer:" + bare role -> "officer:cos"; policy_engine.py (framework/authority/, CG-14):1159,
run_action_lane.py _ACTOR) can NEVER read. The org's one real acted-row
negative label (monday_task_create 2026-07-04T15:44:20Z, silent-revert ->
review{wrong, verdict_judge}) sat stranded in that severed cell
(~/egg-agent-analysis-2026-07-06.md:1144).

WHAT IT MIGRATES (live state only — code was fixed 2026-07-04/05):
  1. Consequence ledger  ($CABINET_EVENT_LOG_DIR/consequence-events-*.jsonl):
     actor {"kind":"officer","id":"officer:cos"} -> id "cos". Base and
     superseding rows rewrite together, so read_ledger()'s last-write-wins
     identity pairing (kind:id | action | subject | ts) is preserved.
  2. Undo journal        ($CABINET_UNDO_DIR/undo-journal-*.jsonl): same actor
     rewrite. REQUIRED for the same lineage: action_reconcile.run_sweep()
     rebuilds the acted event FROM the journal row (acted_event copies
     row["actor"]) and looks the ledger up by proposal_id — which includes
     actor.id. Ledger-only migration would make that lookup miss and the next
     hourly undo-sweep would re-emit the acted row with the LEGACY actor,
     resurrecting the fossil. payload_sha256 on journal rows fingerprints the
     action PAYLOAD only (action_exec.py TOCTOU guard), never the actor.
  3. Transitions state   ($CABINET_GRADUATION_STATE_FILE, default
     ~/Library/Application Support/cabinet/state/graduation-transitions.json):
     cell keys '["officer:officer:cos", ...]' re-keyed to '["officer:cos",
     ...]'. States carry over unchanged, so the hourly
     emit-graduation-transitions sweep sees the SAME states under the clean
     keys and emits zero spurious transitions.

DELIBERATELY NOT TOUCHED:
  * events-*.jsonl (org-events family) — append-only org HISTORY; the
    graduation_transition event recorded under the old key is a true record
    of what happened. Graduation math never reads this family.
  * ledger-backups/purge-* — historical backups ARE the rollback plane.
  * the 'officer:officer:synthetic-test' fossil (2 rows, drill actor) — A14
    scopes to the single cos lineage.
  * repo test fixtures / regression-corpus cases / docstrings that cite the
    legacy literal — fenced fixtures + historical records.

SAFETY: every file to be modified is copied first into
  ~/Library/Application Support/cabinet/ledger-backups/a14-actor-id-<UTC>/
  (events/, undo/, state/ subdirs — same convention as the purge-* siblings).
Rewrites are line-preserving (non-matching lines are written back VERBATIM;
matching lines only have actor.id changed, json.dumps default separators
match the emitters') and atomic (tempfile in the same dir + os.replace, mode
preserved). Idempotent: a second --apply is a no-op. Collision-guard: refuses
to apply if any migrated identity tuple would collide with an existing
clean-actor row (checked, zero live collisions as of 2026-07-07).

RUN:
  python3.12 cabinet/scripts/migrate-graduation-actor-id.py            # dry-run report
  python3.12 cabinet/scripts/migrate-graduation-actor-id.py --apply    # backup + migrate
  python3.12 cabinet/scripts/migrate-graduation-actor-id.py --verify   # the A14 gate; exit 0 = pass

The --verify mode IS the row's gate_cmd made runnable: (a) single cos lineage
across ledger + journal + state (no legacy actor anywhere graduation-feeding),
(b) the stranded negative label readable through the gate's own composition
(graduation.evaluate(("officer:cos", "x", "task_create")) evidence shows the
scored wrong), (c) the backup exists. Rollback: copy the backup dir's files
back over the live ones.

System-python compatible (3.9 stdlib only; framework imports only in --verify).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]

LEGACY_KIND = "officer"
LEGACY_ID = "officer:cos"          # flattens to "officer:officer:cos"
CLEAN_ID = "cos"                   # flattens to "officer:cos" (gate-readable)
LEGACY_FLAT = "officer:officer:cos"
CLEAN_FLAT = "officer:cos"

# The stranded real negative label's cell AFTER migration (gate-visible form):
# the acted monday_task_create row, ts 2026-07-04T15:44:20Z, lane "x",
# review {wrong, verdict_judge} — see module docstring.
STRANDED_CELL = (CLEAN_FLAT, "x", "task_create")


def events_dir() -> Path:
    return Path(os.environ.get(
        "CABINET_EVENT_LOG_DIR",
        os.path.expanduser("~/Library/Application Support/cabinet/events")))


def undo_dir() -> Path:
    return Path(os.environ.get(
        "CABINET_UNDO_DIR",
        os.path.expanduser("~/Library/Application Support/cabinet/undo")))


def state_file() -> Path:
    return Path(os.environ.get(
        "CABINET_GRADUATION_STATE_FILE",
        os.path.expanduser(
            "~/Library/Application Support/cabinet/state/"
            "graduation-transitions.json")))


def backups_root() -> Path:
    return Path(os.path.expanduser(
        "~/Library/Application Support/cabinet/ledger-backups"))


def _is_legacy_actor(ev: Dict[str, Any]) -> bool:
    a = ev.get("actor")
    return (isinstance(a, dict) and a.get("kind") == LEGACY_KIND
            and a.get("id") == LEGACY_ID)


def _identity(ev: Dict[str, Any], flat: str) -> Tuple[str, str, str, str]:
    """read_ledger's dedup identity with the actor flat form substituted."""
    return (flat, str(ev.get("action", "")), str(ev.get("subject", "")),
            str(ev.get("ts", "")))


def _scan_jsonl(path: Path) -> Tuple[List[str], List[int]]:
    """Return (raw lines, indexes of lines carrying the legacy actor)."""
    lines = path.read_text().splitlines(keepends=True)
    hits: List[int] = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        try:
            ev = json.loads(s)
        except (ValueError, TypeError):
            continue
        if isinstance(ev, dict) and _is_legacy_actor(ev):
            hits.append(i)
    return lines, hits


def _rewrite_line(line: str) -> str:
    """Re-serialize ONE matching line with actor.id -> CLEAN_ID. Preserves key
    order (json object order == document order in py3.7+) and the emitters'
    json.dumps default separators; keeps the original newline."""
    nl = "\n" if line.endswith("\n") else ""
    ev = json.loads(line.strip())
    ev["actor"]["id"] = CLEAN_ID
    return json.dumps(ev, default=str) + nl


def _atomic_write(path: Path, content: str) -> None:
    st_mode = path.stat().st_mode & 0o7777
    fd, tmp = tempfile.mkstemp(dir=str(path.parent),
                               prefix="." + path.name + ".a14-")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.chmod(tmp, st_mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _jsonl_files() -> Dict[str, List[Path]]:
    return {
        "events": sorted(events_dir().glob("consequence-events-*.jsonl")),
        "undo": sorted(undo_dir().glob("undo-journal-*.jsonl")),
    }


def _collision_check() -> List[Tuple[str, str, str, str]]:
    """Identity tuples that would collide post-migration (must be empty)."""
    existing = set()
    migrated = set()
    for f in _jsonl_files()["events"]:
        for line in f.read_text().splitlines():
            s = line.strip()
            if not s:
                continue
            try:
                ev = json.loads(s)
            except (ValueError, TypeError):
                continue
            if not isinstance(ev, dict):
                continue
            a = ev.get("actor") or {}
            if not isinstance(a, dict):
                continue
            if a.get("kind") == LEGACY_KIND and a.get("id") == CLEAN_ID:
                existing.add(_identity(ev, CLEAN_FLAT))
            elif _is_legacy_actor(ev):
                migrated.add(_identity(ev, CLEAN_FLAT))
    return sorted(existing & migrated)


def _state_legacy_keys(doc: Dict[str, Any]) -> List[str]:
    cells = doc.get("cells") if isinstance(doc, dict) else None
    if not isinstance(cells, dict):
        return []
    out = []
    for key in cells:
        try:
            parts = json.loads(key)
        except (ValueError, TypeError):
            continue
        if (isinstance(parts, list) and len(parts) == 3
                and parts[0] == LEGACY_FLAT):
            out.append(key)
    return out


def run(apply: bool) -> int:
    files = _jsonl_files()
    plan: List[Tuple[Path, List[str], List[int]]] = []
    total_rows = 0
    for group in ("events", "undo"):
        for f in files[group]:
            lines, hits = _scan_jsonl(f)
            if hits:
                plan.append((f, lines, hits))
                total_rows += len(hits)
                print("%s %s: %d legacy row(s)"
                      % ("MIGRATE" if apply else "would-migrate", f, len(hits)))

    sf = state_file()
    state_doc: Optional[Dict[str, Any]] = None
    legacy_keys: List[str] = []
    if sf.exists():
        state_doc = json.loads(sf.read_text())
        legacy_keys = _state_legacy_keys(state_doc)
        if legacy_keys:
            print("%s %s: %d legacy cell key(s)"
                  % ("RE-KEY" if apply else "would-re-key", sf,
                     len(legacy_keys)))

    if not plan and not legacy_keys:
        print("nothing to migrate — single cos lineage already holds")
        return 0

    collisions = _collision_check()
    if collisions:
        print("REFUSED: %d migrated identity tuple(s) would collide with "
              "existing clean-actor rows:" % len(collisions), file=sys.stderr)
        for c in collisions:
            print("  %r" % (c,), file=sys.stderr)
        return 2

    if not apply:
        print("dry-run: %d ledger/journal row(s) + %d state key(s); "
              "run with --apply" % (total_rows, len(legacy_keys)))
        return 0

    # ---- backup FIRST (row A14: migration WITH backup copy) ----------------
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    bdir = backups_root() / ("a14-actor-id-%s-%d" % (stamp, os.getpid()))
    for sub, paths in (("events", [p for p, _, _ in plan
                                   if p.parent == events_dir()]),
                       ("undo", [p for p, _, _ in plan
                                 if p.parent == undo_dir()]),
                       ("state", [sf] if state_doc is not None else [])):
        (bdir / sub).mkdir(parents=True, exist_ok=True)
        for p in paths:
            shutil.copy2(p, bdir / sub / p.name)
    print("backup: %s" % bdir)

    # ---- ledger + journal rewrite (atomic per file) -------------------------
    for path, lines, hits in plan:
        hitset = set(hits)
        out = [(_rewrite_line(l) if i in hitset else l)
               for i, l in enumerate(lines)]
        _atomic_write(path, "".join(out))
        print("migrated %s (%d row(s))" % (path, len(hits)))

    # ---- transitions-state re-key (atomic; format matches write_state) ------
    if legacy_keys and state_doc is not None:
        cells = state_doc["cells"]
        for key in legacy_keys:
            parts = json.loads(key)
            parts[0] = CLEAN_FLAT
            new_key = json.dumps(parts, ensure_ascii=False)
            if new_key in cells:
                # never clobber an existing clean-cell entry; the sweep will
                # simply re-evaluate — drop the legacy key only.
                print("state: %s exists — dropping legacy key only" % new_key)
                cells.pop(key)
                continue
            cells[new_key] = cells.pop(key)
            print("state: %s -> %s" % (key, new_key))
        _atomic_write(sf, json.dumps(state_doc, ensure_ascii=False,
                                     sort_keys=True, indent=1))

    print("done: %d row(s) + %d key(s) migrated to the %r lineage"
          % (total_rows, len(legacy_keys), CLEAN_FLAT))
    return 0


def verify() -> int:
    """The A14 gate, runnable. Exit 0 = pass."""
    ok = True

    # (a) single cos lineage across every graduation-feeding surface.
    residue = 0
    for group, paths in _jsonl_files().items():
        for f in paths:
            _, hits = _scan_jsonl(f)
            if hits:
                residue += len(hits)
                print("FAIL lineage: %s carries %d legacy row(s)"
                      % (f, len(hits)))
    sf = state_file()
    if sf.exists():
        keys = _state_legacy_keys(json.loads(sf.read_text()))
        if keys:
            residue += len(keys)
            print("FAIL lineage: %s carries legacy key(s): %s" % (sf, keys))
    if residue == 0:
        print("PASS lineage: single cos lineage (ledger + undo journal + "
              "transitions state carry no %r)" % LEGACY_FLAT)
    else:
        ok = False

    # (b) the stranded negative label is visible to the gate's own read:
    # policy_engine composes "officer:" + bare role and calls
    # graduation.evaluate — replicate that read for the stranded cell.
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    try:
        from framework.fidelity import graduation
        res = graduation.evaluate(STRANDED_CELL)
        evd = res.get("evidence") or {}
        samples = evd.get("sample_count") or 0
        divergent = evd.get("divergent_last10") or 0
        if samples >= 1 and divergent >= 1:
            print("PASS gate-read: evaluate(%r) -> state=%s sample_count=%d "
                  "divergent_last10=%d (the stranded wrong is read)"
                  % (list(STRANDED_CELL), res.get("state"), samples,
                     divergent))
        else:
            print("FAIL gate-read: evaluate(%r) -> state=%s evidence=%s"
                  % (list(STRANDED_CELL), res.get("state"), evd))
            ok = False
    except Exception as e:  # noqa: BLE001 — a broken read fails the gate loudly
        print("FAIL gate-read: %s: %s" % (type(e).__name__, e))
        ok = False

    # (c) the backup exists (rollback plane for this migration).
    backups = sorted(backups_root().glob("a14-actor-id-*"))
    live = [b for b in backups
            if any((b / "events").glob("consequence-events-*.jsonl"))
            and any((b / "undo").glob("undo-journal-*.jsonl"))
            and (b / "state" / "graduation-transitions.json").exists()]
    if live:
        print("PASS backup: %s" % live[-1])
    else:
        print("FAIL backup: no a14-actor-id-* backup with events/ + undo/ + "
              "state/ under %s" % backups_root())
        ok = False

    print("A14 gate: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true",
                   help="backup, then migrate (default: dry-run report)")
    g.add_argument("--verify", action="store_true",
                   help="run the A14 gate; exit 0 = pass")
    args = ap.parse_args(argv)
    if args.verify:
        return verify()
    return run(apply=args.apply)


if __name__ == "__main__":
    sys.exit(main())
