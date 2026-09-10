#!/usr/bin/env python3
"""One proposed outcome card, on a hermetic deployment root — for evals only.

WHY THIS EXISTS.  ``framework/outcomes/ratify.py`` is the single writer of both
outcome files, and it refuses two things on purpose:

* a root that is a git worktree — a deployment's ``instance/config/outcomes.yml``
  is TRACKED there, so a tap against a checkout would commit mission state into
  source control and hand it to everyone who pulls the branch;
* an id with no proposed card behind it.

``org-runtime.py outcomes propose`` writes only the org-runtime store, so an
eval that proposes there and then ratifies is asking the authoritative writer to
ratify a card that does not exist, at a root it is right to refuse.  Both
refusals are the guard working; the setup was what was wrong.

So the evals stand up what a ratification actually needs: a scratch deployment
root that is NOT a checkout, carrying one proposed card written through
genesis's own merge writer.  Never hand-rolled YAML — a fixture that spells the
row itself keeps passing after the real writer's shape moves, which is the
stub-encodes-the-broken-contract shape this repo has paid for repeatedly.

Names nothing: the card's text is generic filler and the caller supplies the id,
so no product, person or vendor enters an eval fixture.

Usage, from a shell eval or a test::

    python3 cabinet/scripts/lib/proposed_card_fixture.py --root DIR --id ID

Prints the path of the proposals file it wrote.  Exits non-zero — loudly —
when the card did not land, because a fixture that quietly seeds nothing turns
the eval that depends on it into a test of the refusal path.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


def seed(root: Path, card_id: str) -> str:
    """Write one proposed card with ``card_id`` under ``root``; return its path.

    Idempotent by the merge writer's own rule: an id already present wins and is
    left verbatim, so a second call never clobbers a card an earlier stage
    stamped.
    """
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from framework.onboarding import genesis  # noqa: E402  (path set above)

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if (root / ".git").exists():
        raise SystemExit(
            "proposed_card_fixture: %s is a git worktree — the tap refuses one by "
            "design, so seeding a card there would only move the refusal later" % root
        )
    card = {
        "id": card_id,
        "name": "Eval fixture card %s" % card_id,
        "lane": "eval-lane",
        "what": "carry one declared responsibility end to end",
        "why": "the eval needs a real proposed card to ratify",
        "proof_expected": "a receipt the operator can read",
        "proposed_by": "eval-fixture",
    }
    result = genesis.merge_proposals([card], root)
    path = Path(result["path"])
    doc = _read_ids(path)
    if card_id not in doc:
        raise SystemExit(
            "proposed_card_fixture: %s carries no card %r after the merge writer "
            "reported %r — nothing to ratify"
            % (path, card_id, result.get("status"))
        )
    return str(path)


def _read_ids(path: Path) -> set:
    import yaml

    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows = doc.get("outcomes")
    if not isinstance(rows, list):
        return set()
    return {str(row.get("id")) for row in rows if isinstance(row, dict)}


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", required=True,
                        help="the scratch deployment root to seed (must not be a checkout)")
    parser.add_argument("--id", required=True, dest="card_id",
                        help="the proposal id the eval will ratify")
    args = parser.parse_args(argv)
    print(seed(Path(args.root), args.card_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
