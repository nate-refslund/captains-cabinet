#!/usr/bin/env python3.12
"""cog2-verifier.py — Cortex store integrity: serve-time hash binding + gap taxonomy.

COG-2 UNIT 4. Plan: docs/plans/cognitive-core-phase-2-contract-2026-07-22.md
§6 (serve-time store-hash binding C-F15), §5.3 / §7.3 (frontier + no-prune
retention), §8 sim 5 (corruption + gap). Two operator instruments:

  verify   Re-derive the belief-store hash from the re-parsed beliefs.jsonl rows
           (framework.cortex.query.verify_store — never file bytes, A-m11) and
           REFUSE to serve on any mismatch. The disposable index is never trusted
           over the canonical store; recovery is rebuild-from-zero (cog2-rebuild).

  gaps     Regress the current fold manifest's outbox SEEN-SET against a prior
           manifest (§8 sim 5). A hole never seen in either fold is a benign
           rollback-burned BIGSERIAL id; an id seen before and gone now is a
           breach (seen-set regression); a genesis shift is a breach. The
           CONSEQUENCE seen-set is regressed too, on stable (day-file basename,
           line) coordinates — a deleted consequence day-file / row is a breach.
           Every gap is REPORTED, never bridged with a fabricated belief.

The pure classify_gaps() carries two documented mutant seams the §8 sim-5 gate
drives (never production values): mode="hole_as_breach" (flags the benign hole)
and mode="forward_window" (blind to a below-frontier deletion). write_quarantine
_receipts() persists the ingest fence's refusal receipts (§8 sim 7 receipt-to-
file) — untrusted reasons are scrubbed (printable, capped) before they land.

SHADOW: imports framework.cortex.query/belief/engine ONLY — NEVER
framework.cortex.adapters (no ingest path here); no authoritative write; the
store + receipts are the only files touched, both under cabinet/{cache,logs}/*.

Usage:
    cog2-verifier.py verify --cache-dir DIR
    cog2-verifier.py gaps   --cache-dir DIR --prior-manifest F [--frontier N]

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant.
"""
from __future__ import annotations

# Module top stays STDLIB-ONLY so the pure helpers (classify_gaps,
# write_quarantine_receipts) import without pulling framework; the serve-time
# verify path lazily imports framework.cortex.query inside main().
import argparse
import fcntl
import json
import sys
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# gap taxonomy — seen-set regression (§8 sim 5, A-M9/C-F14), PURE
# ---------------------------------------------------------------------------

def _expand(seen: dict) -> set[int]:
    """The inclusive [lo, hi] interval list -> the set of seen ids."""
    ids: set[int] = set()
    for lo, hi in seen.get("intervals", []) or []:
        ids.update(range(int(lo), int(hi) + 1))
    return ids


def _expand_lines(file_block: dict) -> set[int]:
    """A consequence per-file block's inclusive [lo, hi] LINE intervals -> the
    set of physical line numbers seen in that day-file."""
    ids: set[int] = set()
    for lo, hi in (file_block or {}).get("intervals", []) or []:
        ids.update(range(int(lo), int(hi) + 1))
    return ids


def _classify_consequence(prior: Optional[dict], current: Optional[dict]) -> dict:
    """Regress the CONSEQUENCE seen-set (§8 sim 5 day-file deletion; the C-F12
    no-prune retention tripwire). A day-file basename present in the PRIOR
    manifest and GONE now is a deleted day-file => BREACH; a surviving day-file
    whose line coverage SHRANK is a deleted row => BREACH. Reported, NEVER
    bridged with a fabricated belief.

    Keyed on stable (file, line): a re-enumerated dense id — the IDS-ONLY
    seen-set (engine.consequence_seen's seq mutant) — cannot express this. A
    day-file deletion masked by an append renumbers into the same range, so an
    id regression finds nothing and the deletion is MISSED (the negative
    control). Handed such an ids-only block, this regresses its ids and, count
    preserved, faithfully misses — which is exactly why the seen-set must key on
    (file, line), never a re-enumerated id."""
    prior = prior or {}
    current = current or {}
    if "files" in prior:
        prior_files = prior.get("files", {}) or {}
        current_files = current.get("files", {}) or {}
        deleted_files = sorted(set(prior_files) - set(current_files))
        regressed_lines: dict[str, list[int]] = {}
        for name, pf in prior_files.items():
            cf = current_files.get(name)
            if cf is None:
                continue                       # whole-file loss -> deleted_files
            gone = sorted(_expand_lines(pf) - _expand_lines(cf))
            if gone:
                regressed_lines[name] = gone
        breach = bool(deleted_files) or bool(regressed_lines)
        return {"checked": True, "keyed": "file_line", "breach": breach,
                "deleted_files": deleted_files, "regressed_lines": regressed_lines}
    if "intervals" in prior:
        # IDS-ONLY seen-set (the seq mutant): regress the dense index AS ids — a
        # count-preserving day-file deletion leaves the range intact -> missed.
        regressed = sorted(_expand(prior) - _expand(current))
        return {"checked": True, "keyed": "seq", "breach": bool(regressed),
                "regressions": regressed}
    return {"checked": False, "keyed": None, "breach": False}


def classify_gaps(prior_seen: dict, current_seen: dict, *,
                  frontier: Optional[int] = None,
                  mode: str = "regression",
                  prior_consequence: Optional[dict] = None,
                  current_consequence: Optional[dict] = None) -> dict:
    """Classify the outbox id-sequence delta between two fold manifests' seen
    blocks (§8 sim 5). Returns {status, regressions, genesis_shift, benign_holes,
    …}. NEVER fabricates a bridging belief — it only reports.

      * regression  an id folded in the prior manifest is ABSENT now (deleted
                    committed history) => BREACH.
      * genesis shift  the earliest seen id moved up (source truncated) => BREACH.
      * benign hole  a gap in the current sequence never seen in EITHER fold
                    (a rollback-burned BIGSERIAL id) => NOT a breach.

    MUTANT SEAMS (gate-only, never production):
      * mode="hole_as_breach"  ANY sequence hole is a breach — wrongly flags the
        benign rollback-burned hole (fails sim-5 seed a).
      * mode="forward_window"  only ids >= frontier are examined for regression,
        so a deleted row BELOW the frontier is invisible (fails sim-5 seed b)."""
    prior_ids = _expand(prior_seen)
    current_ids = _expand(current_seen)
    prior_gen = prior_seen.get("genesis")
    cur_gen = current_seen.get("genesis")
    cur_max = current_seen.get("max_seen")

    regressed = prior_ids - current_ids
    if mode == "forward_window" and frontier is not None:
        regressed = {i for i in regressed if i >= int(frontier)}
    regressions = sorted(regressed)

    genesis_shift = (cur_gen is not None and prior_gen is not None
                     and int(cur_gen) > int(prior_gen))

    all_holes: list[int] = []
    if cur_gen is not None and cur_max is not None:
        all_holes = sorted(set(range(int(cur_gen), int(cur_max) + 1)) - current_ids)
    # never-seen-in-either-fold => benign (rollback-burned); the rest are the
    # regressions already surfaced above.
    benign_holes = [h for h in all_holes if h not in prior_ids]

    breach = bool(regressions) or genesis_shift
    if mode == "hole_as_breach":
        breach = breach or bool(all_holes)

    # Consequence stream (§8 sim 5): a deleted day-file / row is a SEEN-SET
    # regression too, on stable (file, line) coordinates — never bridged.
    consequence = _classify_consequence(prior_consequence, current_consequence)
    breach = breach or consequence["breach"]

    return {
        "status": "breach" if breach else "ok",
        "regressions": regressions,
        "genesis_shift": genesis_shift,
        "benign_holes": benign_holes,
        "prior_genesis": prior_gen,
        "current_genesis": cur_gen,
        "mode": mode,
        "consequence": consequence,
    }


# ---------------------------------------------------------------------------
# quarantine receipts (§8 sim 7 receipt-to-file) — append-only, scrubbed
# ---------------------------------------------------------------------------

def _scrub(value: Any, cap: int = 200) -> str:
    """Untrusted refusal text -> inert, printable, capped string. Never raises."""
    clean = "".join(ch if ch.isprintable() else " " for ch in str(value))
    return clean[:cap] + ("…" if len(clean) > cap else "")


def _int_or_none(value: Any) -> Optional[int]:
    """Coerce a receipt's untrusted line field to a plain int, or None — a
    non-int (str, float, junk) never rides raw into the quarantine JSONL."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def write_quarantine_receipts(receipts: list[dict], path) -> int:
    """Append ingest-fence refusal receipts to a quarantine JSONL (flock; the
    cabinet/logs/* gitignored ledger idiom). Each receipt's reason is scrubbed
    (printable, capped) so untrusted envelope text never rides raw into the log.
    A silent skip is the pinned mutant — this makes every refusal auditable."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with open(path, "a", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        for r in receipts:
            line = {"line": _int_or_none(r.get("line")),
                    "reason": _scrub(r.get("reason", "")),
                    "event_id": _scrub(r.get("event_id"), cap=64)
                    if r.get("event_id") is not None else None}
            fh.write(json.dumps(line, sort_keys=True) + "\n")
            written += 1
        fh.flush()
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    return written


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_manifest(cache_dir: Path) -> dict:
    return json.loads((Path(cache_dir) / "fold-manifest.json").read_text(encoding="utf-8"))


def _cmd_verify(cache_dir: str) -> int:
    # lazy framework import: keeps the pure helpers stdlib-importable
    repo_root = str(Path(__file__).resolve().parents[2])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from framework.cortex.query import StoreCorruptError, verify_store
    try:
        verified = verify_store(cache_dir)
    except StoreCorruptError as exc:
        print(f"cog2-verifier: REFUSE {exc}")
        return 1
    print(f"cog2-verifier: OK {verified}")
    return 0


def _cmd_gaps(cache_dir: str, prior_manifest: str, frontier: Optional[int]) -> int:
    current_m = _load_manifest(Path(cache_dir))
    prior_m = json.loads(Path(prior_manifest).read_text(encoding="utf-8"))
    verdict = classify_gaps(
        prior_m.get("seen", {}), current_m.get("seen", {}), frontier=frontier,
        prior_consequence=prior_m.get("seen_consequence"),
        current_consequence=current_m.get("seen_consequence"))
    print(json.dumps(verdict, sort_keys=True))
    return 1 if verdict["status"] == "breach" else 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Cortex store integrity verifier (§8 sim 5)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    pv = sub.add_parser("verify", help="serve-time store-hash binding (C-F15)")
    pv.add_argument("--cache-dir", required=True)

    pg = sub.add_parser("gaps", help="outbox seen-set regression taxonomy (§8 sim 5)")
    pg.add_argument("--cache-dir", required=True, help="the CURRENT fold manifest dir")
    pg.add_argument("--prior-manifest", required=True, help="a prior fold-manifest.json")
    pg.add_argument("--frontier", type=int, default=None)

    args = parser.parse_args(argv)
    if args.cmd == "verify":
        return _cmd_verify(args.cache_dir)
    if args.cmd == "gaps":
        return _cmd_gaps(args.cache_dir, args.prior_manifest, args.frontier)
    return 2


if __name__ == "__main__":
    sys.exit(main())
