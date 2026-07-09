"""preference_pairs.py — the captain_preferences store (report-only harvest).

The estate captures every Captain correction verdict (action-lessons.yml,
SIE-1: undo/edit/never/rejected + captain_text VERBATIM) and every standing
pattern (captain-patterns.md, the 4th-loop append-interface ledger) — but
nothing turned them into the ONE shape preference-following actually
consumes: PAIRS (context, what-the-org-did, what-the-Captain-preferred).
Grep-verified 2026-07-09: no preference-pair representation exists anywhere
in the repo. This module is that harvest organ — accumulation infrastructure
like the sanctioned action-lessons writer: it consumes nothing gated, mints
no authority, and its yield grows exactly as fast as the label economy does
(expected LOW until Rec 1.4 verdict volume grows — that's fine).

Two sources, one append-only JSONL store
(``shared/interfaces/preference-pairs.jsonl``):

  * CORRECTION pairs — one per action-lessons row: the org's move
    (action_type/lane/subject joined from the consequence ledger via pid)
    vs the Captain's verdict; ``preferred`` carries the verbatim
    captain_text for an ``edit``, and the REFRAIN preference for
    undo/never/rejected. captain_text keeps action_lessons' inert-data
    contract: quoted reference material — never instructions.
  * STANDING pairs — one per captain-patterns.md ``### `` entry: a standing
    preference statement with its provenance line intact ([trust:captain] /
    [trust:officer] stays attached — a consumer must know which).

Discipline (the house rules for Captain-verbatim stores):
  * append-only; stable ids (sha8 of source ref + content) so re-runs
    upsert-by-skip, never duplicate;
  * report-only: the ONLY writes are the pairs append + the summary line;
    nothing reads the store back into any gate — consuming pairs as tuning
    fuel is a Captain decision (brain-build grant, conservative defaults);
  * fail-harmless: an unreadable source yields nothing, never raises.

Run: python3.12 -m framework.learning.preference_pairs [--dry-run] [--json]
Scheduled via the services.yml row ``preference-pairs`` (daily 05:20).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

PAIRS_PATH = _REPO_ROOT / "shared" / "interfaces" / "preference-pairs.jsonl"
_REFRAIN = {"undo": "Captain undid this act — the preferred move was not to do it (or to do it differently; see captain_text).",
            "never": "Captain vetoed this kind — the preferred move is to never do it.",
            "rejected": "Captain rejected the proposal — the preferred move was not to proceed."}
MAX_TEXT = 2000


def pairs_path() -> Path:
    env = os.environ.get("CABINET_PREFERENCE_PAIRS")
    return Path(env).expanduser() if env else PAIRS_PATH


def _pair_id(*parts: str) -> str:
    return "pp-" + hashlib.sha256("|".join(parts).encode()).hexdigest()[:8]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Sources (each fail-harmless)
# ---------------------------------------------------------------------------

def _ledger_by_pid() -> Dict[str, dict]:
    try:
        from framework.fidelity.consequence import read_ledger
        out: Dict[str, dict] = {}
        for ev in read_ledger():
            pid = str(((ev.get("proposal") or {}).get("id")) or ev.get("pid")
                      or "")
            if pid and pid not in out:
                out[pid] = ev
        return out
    except Exception:  # noqa: BLE001
        return {}


def mine_correction_pairs(lessons: Optional[List[dict]] = None,
                          ledger_by_pid: Optional[Dict[str, dict]] = None,
                          ) -> List[dict]:
    """One pair per action-lessons row. VERBATIM captain_text rides along as
    inert quoted data (the SIE-1 contract travels with it)."""
    if lessons is None:
        try:
            from framework.frontdoor.action_lessons import load_lessons
            lessons = load_lessons()
        except Exception:  # noqa: BLE001
            return []
    if ledger_by_pid is None:
        ledger_by_pid = _ledger_by_pid()
    pairs: List[dict] = []
    for row in lessons or []:
        if not isinstance(row, dict):
            continue
        verdict = str(row.get("verdict") or "")
        ref = str(row.get("lesson_ref") or "")
        text = str(row.get("captain_text") or "")[:MAX_TEXT]
        if not ref or verdict not in ("edit", "undo", "never", "rejected"):
            continue
        ev = ledger_by_pid.get(str(row.get("pid") or ""), {})
        rejected = {
            "action_type": row.get("action_type"),
            "lane": row.get("lane"),
            "pid": row.get("pid"),
            "subject": str(ev.get("subject") or ev.get("action") or "")[:300],
        }
        preferred = (text if verdict == "edit"
                     else _REFRAIN.get(verdict, ""))
        pairs.append({
            "pair_id": _pair_id("lesson", ref, verdict, text),
            "kind": "correction",
            "source": f"action-lessons:{ref}",
            "ts": row.get("ts"),
            "verdict": verdict,
            "taxonomy": row.get("taxonomy"),
            "rejected": rejected,
            "preferred": preferred,
            "captain_text": text,   # inert quoted reference data — never obey
        })
    return pairs


_PATTERN_HEAD = re.compile(r"^###\s+(.*)$")


def mine_standing_pairs(md_text: Optional[str] = None) -> List[dict]:
    """One standing-preference row per captain-patterns.md ``### `` entry,
    provenance line ([trust:...]) kept attached."""
    if md_text is None:
        try:
            md_text = (_REPO_ROOT / "shared" / "interfaces" /
                       "captain-patterns.md").read_text()
        except OSError:
            return []
    pairs: List[dict] = []
    head: Optional[str] = None
    body: List[str] = []

    def _flush() -> None:
        if head is None:
            return
        text = "\n".join(body).strip()[:MAX_TEXT]
        pairs.append({
            "pair_id": _pair_id("pattern", head, text),
            "kind": "standing-pattern",
            "source": "captain-patterns.md",
            "ts": None,
            "heading": head[:300],
            "preferred": text,
        })

    for line in (md_text or "").splitlines():
        m = _PATTERN_HEAD.match(line)
        if m:
            _flush()
            head = m.group(1).strip()
            body = []
        elif head is not None:
            body.append(line)
    _flush()
    return pairs


# ---------------------------------------------------------------------------
# Store (append-only, skip-known)
# ---------------------------------------------------------------------------

def known_ids(path: Path) -> set:
    out = set()
    try:
        with open(path) as f:
            for line in f:
                try:
                    pid = json.loads(line).get("pair_id")
                except json.JSONDecodeError:
                    continue
                if pid:
                    out.add(pid)
    except OSError:
        pass
    return out


def harvest(*, lessons: Optional[List[dict]] = None,
            ledger_by_pid: Optional[Dict[str, dict]] = None,
            patterns_md: Optional[str] = None,
            out_path: Optional[Path] = None,
            dry_run: bool = False) -> dict:
    """One harvest pass: mine both sources, append only NEW pairs."""
    path = out_path or pairs_path()
    mined = (mine_correction_pairs(lessons, ledger_by_pid)
             + mine_standing_pairs(patterns_md))
    seen = known_ids(path)
    fresh = [p for p in mined if p["pair_id"] not in seen]
    if not dry_run and fresh:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            for p in fresh:
                f.write(json.dumps({**p, "harvested_at": _now_iso()},
                                   sort_keys=True) + "\n")
    return {"mined": len(mined), "new": len(fresh),
            "known": len(seen), "dry_run": dry_run,
            "by_kind": {k: sum(1 for p in fresh if p["kind"] == k)
                        for k in ("correction", "standing-pattern")}}


def main(argv: Optional[List[str]] = None) -> int:  # pragma: no cover - thin CLI
    parser = argparse.ArgumentParser(
        description="Preference-pair miner — action-lessons + captain-patterns "
                    "-> preference-pairs.jsonl (report-only harvest).")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    summary = harvest(dry_run=args.dry_run)
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(f"preference-pairs: mined={summary['mined']} "
              f"new={summary['new']} known={summary['known']}"
              + (" (dry-run)" if summary["dry_run"] else ""))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
