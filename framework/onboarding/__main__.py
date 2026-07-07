"""CLI — the Chair's onboarding entry point.

    python -m framework.onboarding <slug> <repo_path> [--tracker-ref REF] [--name N] [--new] [--apply]

Dry-run by default (prints what research found + the plan + the gated proposals).
``--apply`` writes the two SAFE artifacts (lane-CEO role def + readiness report).
It NEVER executes gated/external/germline actions — those print as proposals for
the Captain to approve.
"""
from __future__ import annotations

import argparse
import sys

from framework.onboarding import onboard


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="framework.onboarding")
    ap.add_argument("slug", help="lane slug (kebab-case, e.g. polads)")
    ap.add_argument("repo_path", help="local checkout path of the product repo")
    ap.add_argument("--tracker-ref", "--board", dest="tracker_ref", default=None,
                    help="opaque task-tracker ref (board/product id) — semantics "
                         "owned by the lane's task-tracking extension")
    ap.add_argument("--name", default=None, help="canonical display name (else from context/repo)")
    ap.add_argument("--new", action="store_true",
                    help="product does not exist yet → propose GH-repo / tracker-product creation")
    ap.add_argument("--apply", action="store_true",
                    help="write the lane-CEO role def + readiness report (no gated actions)")
    a = ap.parse_args(argv)

    rep = onboard.onboard_lane(a.repo_path, slug=a.slug, tracker_ref=a.tracker_ref,
                               name=a.name, existing=not a.new, apply=a.apply)
    pl = rep["plan"]
    print(f"{'APPLIED' if rep['applied'] else 'DRY-RUN'} — lane '{a.slug}' "
          f"({pl['answers_lane']['name']})")
    print(f"  stack: {rep['profile']['stack']} | plugins: {rep['profile']['plugins']}")
    print(f"  lane MCPs: {pl['lane_mcps']}")
    if rep["applied"]:
        print(f"  lane-CEO: {rep['lane_ceo_path']}")
        print(f"  report:   {rep['report_path']}")
    print("  needs your approval (gated — NOT executed):")
    for g in pl["gated_actions"] or [{"action": "(none)", "name": "", "reason": "existing product"}]:
        print(f"    - {g['action']} {g.get('name','')} — {g['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
