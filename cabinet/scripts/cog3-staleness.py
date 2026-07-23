#!/usr/bin/env python3.12
"""cog3-staleness.py — the §5.1(7) staleness INSTRUMENT (COG-3 contract rev-1).

Staleness is an INSTRUMENT, never a build input (A-m8): it takes `--now
<canonical-ts>` as a DECLARED argument (never an environment clock read — A-M6
purity intact) and diffs TWO FENCED `as_of` answers per bound subject — the
subject's bound cutoff (recorded in the built graph-manifest) vs the declared now.
A bound subject whose fenced head MOVED between the two cutoffs is reported stale.
Never inside build_graph, never a cached view (both queries are fenced through the
ONE cortex read path).

It reads the BUILT graph-manifest for its (bound subject, bound cutoff) source, so
the graph must be built first. Output feeds SIM-2 and the manifest staleness flags.

Usage:
    cog3-staleness.py --now <YYYY-MM-DDTHH:MM:SSZ> --cache <objectives cache dir>

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; U2 (the objectives instruments/CLIs).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# The CLI is outside the framework/objectives import pin (§6.5 allowlist covers
# cog3-*.py); it uses the sanctioned cortex read path directly, defaults-only.
from framework.cortex.query import as_of, load_beliefs_verified  # noqa: E402


def _fenced(beliefs, subject_key, scope, cutoff):
    """One FENCED as_of answer (defaults-only) reduced to its comparable head —
    the ordered value list + status. A moved head changes this tuple."""
    result = as_of(beliefs, subject_key, scope=scope, observation=cutoff)
    return ([view.value for view in result.views], result.status)


def run(now: str, cache: str) -> dict:
    cache_dir = Path(cache)
    manifest = json.loads((cache_dir / "graph-manifest.json").read_text(encoding="utf-8"))
    epoch = manifest.get("epoch", {}) if isinstance(manifest, dict) else {}
    scope = epoch.get("scope") or {}
    bound_cutoff = manifest.get("bound_cutoff") or epoch.get("cutoff")
    bound_subjects = manifest.get("bound_subjects", []) or []

    cortex_dir = cache_dir.parent / "cortex"
    beliefs = (load_beliefs_verified(cortex_dir)
               if (cortex_dir / "fold-manifest.json").exists() else [])

    stale = []
    for subject_key in bound_subjects:
        bound_head = _fenced(beliefs, subject_key, scope, bound_cutoff)
        now_head = _fenced(beliefs, subject_key, scope, now)
        if bound_head != now_head:
            stale.append({"subject_key": subject_key,
                          "bound_cutoff": bound_cutoff, "now": now})

    return {
        "now": now,
        "bound_cutoff": bound_cutoff,
        "stale": stale,
        # the manifest staleness-flags surface (§11 row 2): the moved subjects.
        "staleness_flags": [entry["subject_key"] for entry in stale],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="COG-3 staleness instrument (§5.1(7))")
    parser.add_argument("--now", required=True,
                        help="declared canonical cutoff to diff against the bound cutoff")
    parser.add_argument("--cache", required=True,
                        help="the objectives cache dir holding graph-manifest.json")
    args = parser.parse_args(argv)
    print(json.dumps(run(args.now, args.cache)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
