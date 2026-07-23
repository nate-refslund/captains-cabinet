#!/usr/bin/env python3.12
"""cog3-rebuild.py — rebuild the objectives graph from the Captain-direction roots.

The CLI OWNS yaml parsing (§7.6 layer-sep law): framework/objectives/ carries NO
`instance/` path literal and NEVER imports yaml — this wrapper `yaml.safe_load`s
the roots file (default `instance/config/directions.yml`, resident HERE, never in
framework), then INJECTS the parsed structure as a canonical JSON file the pure
fold reads stdlib-only. `build_graph` stays env-free (A-M6): every input is a
declared parameter recorded in the manifest.

Usage:
    cog3-rebuild.py --cutoff <YYYY-MM-DDTHH:MM:SSZ> [--roots F] [--cache DIR]
                    [--cabinet-id ID] [--json]

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

import yaml  # noqa: E402  (the CLI owns yaml — framework/objectives never does)

from framework.objectives import graph  # noqa: E402

# The default roots path lives HERE in the CLI (§7.6) — never inside framework.
_DEFAULT_ROOTS = _REPO_ROOT / "instance" / "config" / "directions.yml"
_DEFAULT_CACHE = _REPO_ROOT / "cabinet" / "cache" / "objectives"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="COG-3 objectives graph rebuild")
    parser.add_argument("--roots", default=str(_DEFAULT_ROOTS),
                        help="Captain-direction roots file (yaml; CLI-owned parse)")
    parser.add_argument("--cache", default=str(_DEFAULT_CACHE),
                        help="objectives cache dir to write graph.jsonl + manifest")
    parser.add_argument("--cabinet-id", default="main",
                        help="local cabinet_id for the mandatory as_of scope")
    parser.add_argument("--cutoff", required=True,
                        help="the canonical build cutoff (one per build, §5.1)")
    parser.add_argument("--json", action="store_true",
                        help="print the build result + chained graph hash as JSON")
    args = parser.parse_args(argv)

    # CLI-side yaml parse (§7.6) — framework/objectives never parses yaml.
    parsed = yaml.safe_load(Path(args.roots).read_text(encoding="utf-8")) or {}
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)

    # INJECT the parsed structure as the canonical JSON file the pure fold reads.
    injected = cache / "objectives-input.json"
    injected.write_text(
        json.dumps(parsed, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")

    result = graph.build_graph(str(injected), str(cache),
                               {"cabinet_id": args.cabinet_id}, args.cutoff)
    if args.json:
        result = {**result, "graph_hash": graph.chained_graph_hash(str(cache))}
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
