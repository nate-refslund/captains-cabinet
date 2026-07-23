#!/usr/bin/env python3.12
"""cog3-rebuild.py — rebuild the objectives graph from the Captain-direction roots.

The CLI OWNS yaml parsing (§7.6 layer-sep law): framework/objectives/ carries NO
`instance/` path literal and NEVER imports yaml — this wrapper `yaml.safe_load`s
the roots file (default `instance/config/directions.yml`, resident HERE, never in
framework), NORMALIZES its lane-keyed `directions:` mapping into the canonical
entry-list shape the fold reads (_normalize_roots — the fold's own input shapes
stay untouched), then INJECTS the parsed structure as a canonical JSON file the
pure fold reads stdlib-only. `build_graph` stays env-free (A-M6): every input is a
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
from framework.objectives.adapters import (  # noqa: E402
    assemble, mission_inputs, product_spec, workgraph)

# The default roots path lives HERE in the CLI (§7.6) — never inside framework.
_DEFAULT_ROOTS = _REPO_ROOT / "instance" / "config" / "directions.yml"
_DEFAULT_CACHE = _REPO_ROOT / "cabinet" / "cache" / "objectives"


def _load_records(path: str, key: str) -> list:
    """CLI-side yaml read of an adapter source file (§7.6: the CLI owns ALL file
    reading + yaml; adapters consume the parsed structures only). A `{key: [...]}`
    mapping yields its list; a bare top-level list is used as-is."""
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if isinstance(doc, dict):
        return doc.get(key, []) or []
    return doc if isinstance(doc, list) else []


def _merge_adapter_sources(parsed: dict, *, workgraph_path, missions_path,
                           products_path) -> None:
    """W4A: run the workgraph/missions/products adapters on their CLI-parsed source
    files and MERGE the assembled fragment into the roots-derived `parsed` (which
    already carries the normalized `directions`). Default behavior — no flag — never
    calls this, so the roots-only output is byte-for-byte backward compatible. An
    absent source is DECLARED (never silent) via assemble's `declared_absent`."""
    fragments = {
        "workgraph": (workgraph.adapt(_load_records(workgraph_path, "tasks"))
                      if workgraph_path else None),
        "mission_inputs": (mission_inputs.adapt(_load_records(missions_path, "missions"))
                           if missions_path else None),
        "product_spec": (product_spec.adapt(_load_records(products_path, "products"))
                         if products_path else None),
    }
    extra = assemble(fragments)
    for category in ("objectives", "outcomes", "constraints", "nodes",
                     "indicates_edges", "causal_edges"):
        if extra.get(category):
            parsed[category] = list(parsed.get(category) or []) + extra[category]
    parsed["declared_absent"] = extra["declared_absent"]


def _normalize_roots(parsed: dict) -> None:
    """Reshape the Captain-direction roots into the canonical entry-list structure
    the pure fold reads — IN THE CLI, per the §7.6 layer law (the CLI owns yaml AND
    this reshape; the fold's two pinned input shapes stay untouched, and the corpus
    fixtures bypass the CLI so they are unaffected).

    The production `instance/config/directions.yml` carries `directions:` as a
    LANE-KEYED MAPPING ({stephie: {mission, instruments, bets, …}, polads: {…}, …}),
    but graph.py iterates `directions` as a LIST of {slug, statement, …} entries and
    would `AttributeError` on the lane-key strings. Here each lane KEY becomes a root
    entry slug (authoritative), carrying the lane's body, in DETERMINISTIC
    sorted-by-lane order. A `directions:` already in list shape (or absent) is left
    as-is; the sibling `org:` apex block is not folded by framework readers and is
    left untouched."""
    raw = parsed.get("directions")
    if not isinstance(raw, dict):
        return
    entries = []
    for lane_key in sorted(raw):
        body = raw[lane_key]
        entry = dict(body) if isinstance(body, dict) else {}
        entry["slug"] = lane_key          # the lane key is the authoritative slug
        entries.append(entry)
    parsed["directions"] = entries


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
    parser.add_argument("--workgraph", default=None,
                        help="optional tasks/intervention source (yaml; W4A adapter)")
    parser.add_argument("--missions", default=None,
                        help="optional mission outcome/constraint source (yaml; W4A)")
    parser.add_argument("--products", default=None,
                        help="optional product instrument source (yaml; W4A adapter)")
    parser.add_argument("--json", action="store_true",
                        help="print the build result + chained graph hash as JSON")
    args = parser.parse_args(argv)

    # CLI-side yaml parse (§7.6) — framework/objectives never parses yaml.
    parsed = yaml.safe_load(Path(args.roots).read_text(encoding="utf-8")) or {}
    # Reshape the lane-keyed `directions:` mapping into the canonical entry list the
    # fold reads (§7.6 — the CLI owns the reshape, not framework/objectives).
    _normalize_roots(parsed)
    # W4A: fold in the optional adapter sources (default — no flag — is untouched,
    # roots-only, backward compatible).
    if args.workgraph or args.missions or args.products:
        _merge_adapter_sources(parsed, workgraph_path=args.workgraph,
                               missions_path=args.missions, products_path=args.products)
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
