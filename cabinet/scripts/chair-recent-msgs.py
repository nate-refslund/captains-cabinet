#!/usr/bin/env python3
"""Chair-side resolver for the Captain recent-message ring.

The inbound poller (officer-inbound-poller.py) pushes {id, text, ts} for every
inbound Captain message onto the redis list `cabinet:captain:recent-msgs`
(newest at head, bounded to 30). This tool lets the Chair resolve ANY recent
Captain message to its Telegram message_id *by content* — so
`channel.send(reply_to=id)` can thread a reply onto a message that is NOT the
latest.

Root cause it fixes (verified 2026-07-09): the Chair previously only had
`cabinet:last-captain-msg-id` (the LATEST id), so every "reply to an earlier
message" silently fell back to the latest and mislabeled. See
instance/memory/tier2/cos/mission-tg-hardening-2026-07-09.md.

Usage:
  chair-recent-msgs.py --list
  chair-recent-msgs.py --resolve "<substring>"          # newest match -> one JSON obj
  chair-recent-msgs.py --resolve "<substring>" --all    # every match, newest first

Exit 0 on match/non-empty list; exit 2 on no-match / empty ring (callers branch
on this). Strictly READ-ONLY: never writes redis, never sends Telegram. It
resolves an id; the caller does the send with the already-proven
channel.send(reply_to=...) primitive and reads back reply_to_message to verify.
"""
import argparse
import json
import os
import subprocess
import sys

RING_KEY = "cabinet:captain:recent-msgs"


def _redis_host() -> str:
    return os.environ.get("REDIS_HOST", "localhost")


def _redis_port() -> str:
    return os.environ.get("REDIS_PORT", "6379")


def load_ring() -> list:
    """Return the ring as a list of dicts, newest first. Degrade-safe: an
    unreachable redis or a malformed entry yields [] / is skipped, never raises."""
    try:
        out = subprocess.run(
            ["redis-cli", "-h", _redis_host(), "-p", _redis_port(),
             "LRANGE", RING_KEY, "0", "-1"],
            capture_output=True, text=True, timeout=10)
    except Exception as e:  # redis down / binary missing — never block the caller
        print(f"redis unreachable: {e}", file=sys.stderr)
        return []
    entries = []
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue  # a non-JSON line is not a ring entry
        if isinstance(d, dict) and "id" in d:
            entries.append(d)
    return entries


def resolve(entries: list, needle: str) -> list:
    """Case-insensitive substring match on `text`, newest-first order preserved."""
    n = (needle or "").lower()
    return [e for e in entries if n in str(e.get("text", "")).lower()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true",
                    help="print the whole ring (newest first) as JSON")
    ap.add_argument("--resolve", metavar="SUBSTRING",
                    help="resolve the Captain message whose text contains SUBSTRING")
    ap.add_argument("--all", action="store_true",
                    help="with --resolve: print every match (newest first), not just newest")
    args = ap.parse_args()

    entries = load_ring()

    if args.list:
        print(json.dumps(entries, indent=2))
        return 0 if entries else 2

    if args.resolve is not None:
        matches = resolve(entries, args.resolve)
        if not matches:
            print(f"no recent Captain message matches: {args.resolve!r}", file=sys.stderr)
            return 2
        if args.all:
            print(json.dumps(matches, indent=2))
        else:
            print(json.dumps(matches[0]))  # newest match
        return 0

    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
