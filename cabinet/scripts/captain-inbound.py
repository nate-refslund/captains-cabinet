#!/usr/bin/env python3
"""captain-inbound.py — CLI over the durable captain-inbound archive.

Thin skin on cabinet/scripts/lib/captain_inbound.py (ALL semantics live
there — dedup-last-wins, kind filters, both dm_id forms, the semantic
join). The archive is the verbatim truth surface the 30-entry redis ring
is not; this is the tool the Chair (or the operator) reaches for to see
what the Captain ACTUALLY said. Strictly READ-ONLY.

Usage:
  captain-inbound.py latest [-n N] [--kind K] [--json]
  captain-inbound.py get <dm_id|message_id> [--json]
  captain-inbound.py search <terms...> [-n N] [--kind K] [--semantic] [--json]

* latest — newest N rows (default 30), newest first.
* get — one row by full ``tg-<chat>-<mid>`` dm_id OR bare message_id;
  a bare mid ambiguous across chats prints the newest plus every match.
* search — case-insensitive ALL-terms match over text+quoted+file_name;
  --semantic routes through cabinet_memory (search-memory.sh) instead and
  joins hits back to verbatim archive rows.
* --kind repeats and/or takes comma lists (text|file|file-error|onboarding).

Human output is one line per message — dm_id, ts, kind, first 120 chars
(whitespace-flattened); ``get`` additionally prints the untruncated
text/quoted (the whole point of the archive). --json emits full rows,
ensure_ascii=False so Danish text stays verbatim.

Exit codes (the chair-recent-msgs.py contract — callers branch on this):
0 = hits printed; 2 = no match / empty archive / semantic unavailable.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

# lib/ has no __init__.py (see the CI workflow note on lib/tests
# collection) — underscore modules there import via a path insert, the
# same shape the lib test conftest uses.
_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import captain_inbound  # noqa: E402  (needs the sys.path insert above)


def _fmt_line(row: dict) -> str:
    """One human line per message: dm_id, ts, kind, first 120 chars.
    File rows without a caption fall back to the attachment name so the
    line is never blank."""
    body = str(row.get("text") or "")
    if not body and row.get("file_name"):
        body = "(%s: %s)" % (row.get("file_kind") or "file", row["file_name"])
    body = re.sub(r"\s+", " ", body).strip()[:120]
    return "%s  %s  %-10s  %s" % (row.get("dm_id", ""), row.get("ts", ""),
                                  row.get("kind", ""), body)


def _print_json(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _cmd_latest(args) -> int:
    rows = captain_inbound.latest(n=args.n, kinds=args.kind)
    if args.json:
        _print_json(rows)
        return 0 if rows else 2
    if not rows:
        print("captain-inbound archive: no rows", file=sys.stderr)
        return 2
    for row in rows:
        print(_fmt_line(row))
    return 0


def _print_get_human(row: dict) -> None:
    print(_fmt_line(row))
    if row.get("quoted"):
        print("  quoted: %s" % row["quoted"])
    if row.get("file_name"):
        print("  file: %s (%s)" % (row["file_name"],
                                   row.get("file_kind") or "file"))
    if row.get("text"):
        print("  text: %s" % row["text"])  # untruncated, may span lines
    matches = row.get("matches")
    if matches:
        print("  ambiguous message_id — %d chats match (newest shown above):"
              % len(matches))
        for m in matches:
            print("    %s" % _fmt_line(m))


def _cmd_get(args) -> int:
    row = captain_inbound.get(args.dm_id)
    if row is None:
        print("no archive row matches: %r" % args.dm_id, file=sys.stderr)
        return 2
    if args.json:
        _print_json(row)
    else:
        _print_get_human(row)
    return 0


def _cmd_search(args) -> int:
    query = " ".join(args.terms)
    if not args.semantic:
        rows = captain_inbound.search(query, n=args.n, kinds=args.kind)
        if args.json:
            _print_json(rows)
            return 0 if rows else 2
        if not rows:
            print("no archive rows match: %r" % query, file=sys.stderr)
            return 2
        for row in rows:
            print(_fmt_line(row))
        return 0
    res = captain_inbound.semantic_search(query, n=args.n)
    if res.get("available") and args.kind:
        # --kind means "Captain utterances of these kinds": keep only hits
        # whose ARCHIVE JOIN matches. Un-joined hits (officer replies,
        # pre-archive rows) have no kind to test — dropping them is the
        # only honest reading, and we say so rather than silently ignoring
        # the flag (review P2-4).
        ks = captain_inbound._kind_set(args.kind)
        before = len(res.get("results", []))
        res["results"] = [h for h in res.get("results", [])
                          if h.get("archive")
                          and h["archive"].get("kind") in ks]
        dropped = before - len(res["results"])
        if dropped:
            print("--kind: dropped %d hit(s) without a matching archive "
                  "row (officer replies / pre-archive rows carry no kind)"
                  % dropped, file=sys.stderr)
    if args.json:
        _print_json(res)
    if not res.get("available"):
        print("semantic search unavailable: %s" % res.get("reason", ""),
              file=sys.stderr)
        return 2
    hits = res.get("results", [])
    if not args.json:
        if not hits:
            print("no semantic hits for: %r" % query, file=sys.stderr)
        for hit in hits:
            print("[trust:%s] [%s] %s by %s @ %s (sim: %s, score: %s)"
                  % (hit.get("trust", ""), hit.get("source_type", ""),
                     hit.get("ref", ""), hit.get("officer", ""),
                     hit.get("when_at", ""), hit.get("similarity", ""),
                     hit.get("score", "")))
            if hit.get("preview"):
                print("  %s" % hit["preview"])
            if hit.get("archive"):
                print("  archive: %s" % _fmt_line(hit["archive"]))
    return 0 if hits else 2


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="captain-inbound.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_latest = sub.add_parser("latest", help="newest N rows, newest first")
    p_latest.add_argument("-n", type=int, default=30, metavar="N")
    p_latest.add_argument("--kind", action="append", metavar="K",
                          help="filter kinds; repeatable and/or comma list")
    p_latest.add_argument("--json", action="store_true",
                          help="full rows as JSON")
    p_latest.set_defaults(func=_cmd_latest)

    p_get = sub.add_parser("get", help="one row by dm_id or bare message_id")
    p_get.add_argument("dm_id", metavar="dm_id|message_id")
    p_get.add_argument("--json", action="store_true", help="full row as JSON")
    p_get.set_defaults(func=_cmd_get)

    p_search = sub.add_parser(
        "search", help="all-terms lexical search (--semantic for memory)")
    p_search.add_argument("terms", nargs="+", metavar="term")
    p_search.add_argument("-n", type=int, default=20, metavar="N")
    p_search.add_argument("--kind", action="append", metavar="K",
                          help="filter kinds; repeatable and/or comma list")
    p_search.add_argument("--semantic", action="store_true",
                          help="search cabinet_memory and join archive rows")
    p_search.add_argument("--json", action="store_true",
                          help="full rows / result dict as JSON")
    p_search.set_defaults(func=_cmd_search)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
