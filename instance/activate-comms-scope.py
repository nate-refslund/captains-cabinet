#!/usr/bin/env python3.12
"""Apply the Captain-approved Comms Officer germline edits (2026-06-24).

Run by Nate (the Captain) via the session's `!` prefix, since mcp-scope.yml +
officer-capabilities.conf are germline (officers can't edit them; only the
Captain applies scope changes). Idempotent — safe to run twice.
"""
import pathlib

root = pathlib.Path("/Users/nate/captains-cabinet")
scope = root / "cabinet/mcp-scope.yml"
caps = root / "cabinet/officer-capabilities.conf"

# 1) mcp-scope.yml — add comms-officer to the agents block (before scaffolds).
s = scope.read_text()
if "comms-officer:" not in s:
    block = (
        "  # Comms Officer (portfolio/hq) — owns Nate's Outlook + Teams comms.\n"
        "  # Telegram-dark: surfaces ONLY through the Chair. Captain-approved (2026-06-24).\n"
        "  comms-officer:\n"
        "    mcps: [make, brain, library, telegram]\n"
        "    rationale: >\n"
        "      make: Graph-proxy folder-WRITE edit (3902068) + filing/archiving mailbox\n"
        "      MOVES through the Make proxy — never a human-bound send. brain:\n"
        "      gather-then-decide + the queue_draft outbound gate (approve-only). No\n"
        "      neon/vercel/corridor. External comms + spend + mail-delete stay\n"
        "      propose-only. telegram = warroom broadcast only; Telegram-dark.\n\n"
    )
    anchor = "# Scaffolded agents (not hired, scope reserved):"
    s = s.replace(anchor, block + anchor, 1)
    scope.write_text(s)
    print("✓ mcp-scope.yml: comms-officer added (make, brain, library, telegram)")
else:
    print("• mcp-scope.yml: comms-officer already present — skipped")

# 2) officer-capabilities.conf — comms-officer logs Captain decisions.
c = caps.read_text()
if "comms-officer:logs_captain_decisions" not in c:
    caps.write_text(
        c.rstrip()
        + "\n\n# Comms Officer (portfolio) — Telegram-dark; logs Captain decisions; "
          "no deploy, no bot.\ncomms-officer:logs_captain_decisions\n"
    )
    print("✓ officer-capabilities.conf: comms-officer:logs_captain_decisions added")
else:
    print("• officer-capabilities.conf: capability already present — skipped")

print("\nDone. Tell the Chair 'scope applied' and it will boot the Comms Officer.")
