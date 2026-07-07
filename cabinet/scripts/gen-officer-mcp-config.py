#!/usr/bin/env python3
"""gen-officer-mcp-config.py — per-officer STRUCTURAL MCP scoping at boot.

Audit 2026-07-07 finding #4 (non-germline half): officers used to launch with
the full merged .mcp.json union and rely solely on pre-tool-use.sh §9 to
reject out-of-scope MCP *calls* — a call-time gate that fails open when the
officer identity is unset/unlisted, and that never stops an unscoped server
from BOOTING at all. This helper makes the scope structural: it reads
cabinet/mcp-scope.yml (READ-ONLY — the scope file is germline, schg-locked)
and emits

  1. a per-officer MCP config: the input (merged) config filtered down to the
     officer's granted server set — passed to `claude --mcp-config <file>
     --strict-mcp-config` so nothing outside the grant set even starts;
  2. a per-officer settings overlay mirroring the grants into
     `allowedMcpServers` (+ `enableAllProjectMcpServers: false`) — passed via
     `claude --settings <file>` so the session cannot union the project
     .mcp.json (or any drifted config source) back in.

FAIL CLOSED, never open: a missing/corrupt/unparseable scope file, or an
officer with no `agents:`/`scaffolds:` entry, yields an EMPTY server set
(empty mcpServers + empty allowedMcpServers) with a loud [ERROR] on stderr —
the exact inverse of the hook's warn-and-allow path this finding flagged.
The pre-tool-use.sh §9 call-time check stays as defense-in-depth.

The scope parser below MIRRORS the hook's parser (pre-tool-use.sh §9 cache
builder) line-for-line in semantics: same section/agent/mcps regexes, same
`universal:` merge, same case-insensitive membership — so the structural
plane and the call-time plane can never disagree about what a grant means.

--extra-allow is the launcher's INFRA pass-through (not a capability grant):
delivery-plane servers an officer session cannot function without but which
the germline scope file does not (yet) list — e.g. redis-trigger-channel,
the trigger-delivery MCP. The pass-through is declared visibly on the
start-officer-mac.sh call site and is IGNORED whenever the scope parse
fails (fail-closed swallows it too). Getting these into mcp-scope.yml
`universal:` is a Captain germline amendment — see
docs/proposals/germline-addendum-claude-code-audit-2026-07-07.md.

Stdlib-only on purpose (no pyyaml): this runs on every officer boot,
including clean-room hatches where only the system python exists.

Usage:
  gen-officer-mcp-config.py --officer cos \
      --scope cabinet/mcp-scope.yml \
      --input ~/Library/Caches/cabinet/merged-mcp-cos.json \
      --out-mcp ~/Library/Caches/cabinet/officer-mcp-cos.json \
      --out-settings ~/Library/Caches/cabinet/officer-settings-cos.json \
      [--extra-allow redis-trigger-channel,cua]

Exit codes: 0 = outputs written (including the fail-closed empty set);
non-zero only when the outputs themselves could not be written (the shell
caller then writes empty configs itself — fail closed all the way down).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile


def log_err(msg: str) -> None:
    sys.stderr.write("[ERROR] gen-officer-mcp-config: %s\n" % msg)


def parse_scope(text: str) -> dict:
    """Parse mcp-scope.yml into {agent: [mcps...]} with universal merged in.

    Semantics mirror pre-tool-use.sh §9's cache builder exactly (same
    regexes, same universal merge, agents AND scaffolds sections). Returns
    {} when nothing parses — callers treat {} as fail-closed.
    """
    out: dict = {}
    section = None
    cur_agent = None
    universals: list = []
    # First pass: collect universals (inline bracket-list style only — the
    # documented format the hook's parser reads).
    for line in text.splitlines():
        m = re.match(r"^universal:\s*\[([^\]]*)\]", line)
        if m:
            universals = [x.strip() for x in m.group(1).split(",") if x.strip()]
            break
    # Second pass: parse agents/scaffolds
    for line in text.splitlines():
        if re.match(r"^(agents|scaffolds):\s*$", line):
            section = line.split(":", 1)[0]
            continue
        # Reset section when any other top-level key is hit
        if re.match(r"^[A-Za-z]", line):
            if not re.match(r"^(agents|scaffolds):\s*$", line):
                section = None
            continue
        if section and re.match(r"^  [A-Za-z][A-Za-z0-9_-]*:\s*$", line):
            cur_agent = line.strip().rstrip(":")
            continue
        if cur_agent and re.match(r"^\s+mcps:\s*\[", line):
            mcps_raw = line.split("[", 1)[1].split("]", 1)[0]
            mcps = [m.strip() for m in mcps_raw.split(",") if m.strip()]
            seen = set(mcps)
            for u in universals:
                if u not in seen:
                    mcps.append(u)
                    seen.add(u)
            out[cur_agent] = mcps
            cur_agent = None
    return out


def resolve_allowed(officer: str, scope_path: str, extra_allow: list) -> list:
    """Return the officer's allowed server-name list, or [] fail-closed.

    extra_allow is honored ONLY when the scope parse succeeded AND the
    officer has an entry — a failed parse must not leak even infra servers
    (the caller's empty-set boot is the loud, visible failure mode that
    gets fixed, not silently half-worked around).
    """
    try:
        with open(scope_path, "r") as fh:
            text = fh.read()
    except OSError as exc:
        log_err("scope file unreadable (%s: %s) — FAIL CLOSED, empty server set" % (scope_path, exc))
        return []
    try:
        scope_map = parse_scope(text)
    except Exception as exc:  # regex parser is total, but never fail open
        log_err("scope parse failed (%s) — FAIL CLOSED, empty server set" % exc)
        return []
    if not scope_map:
        log_err("scope file %s parsed to an EMPTY agent map (corrupt?) — FAIL CLOSED, empty server set" % scope_path)
        return []
    if officer not in scope_map:
        log_err(
            "officer '%s' has no entry in %s — FAIL CLOSED, empty server set "
            "(the call-time hook used to warn-and-allow here; structural scoping does not)"
            % (officer, scope_path)
        )
        return []
    allowed = list(scope_map[officer])
    seen = set(allowed)
    for extra in extra_allow:
        if extra and extra not in seen:
            allowed.append(extra)
            seen.add(extra)
    return allowed


def filter_config(input_path: str, allowed: list) -> dict:
    """Filter the merged MCP config down to the allowed server set.

    Non-mcpServers top-level keys are preserved. "_"-prefixed pseudo-server
    keys (comment/doc entries) are stripped — mirrors the jq merge pass, and
    covers the single-layer path where that jq pass never ran. Membership is
    case-insensitive, mirroring the hook's `grep -qi`.
    """
    empty = {"mcpServers": {}}
    if not allowed:
        return empty
    try:
        with open(input_path, "r") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError) as exc:
        log_err("input MCP config unusable (%s: %s) — FAIL CLOSED, empty server set" % (input_path, exc))
        return empty
    if not isinstance(cfg, dict):
        log_err("input MCP config %s is not a JSON object — FAIL CLOSED, empty server set" % input_path)
        return empty
    servers = cfg.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    allowed_lc = {a.lower() for a in allowed}
    kept = {}
    dropped = []
    for name, spec in servers.items():
        if name.startswith("_"):
            continue  # pseudo-server comment key, never bootable
        if name.lower() in allowed_lc:
            kept[name] = spec
        else:
            dropped.append(name)
    if dropped:
        sys.stderr.write(
            "gen-officer-mcp-config: scoped OUT unscoped server(s): %s\n" % ", ".join(sorted(dropped))
        )
    out = dict(cfg)
    out["mcpServers"] = kept
    return out


def write_atomic(path: str, obj: dict) -> None:
    """0600, atomic replace — the config may embed API keys from cabinet/.env."""
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".gen-mcp.")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump(obj, fh, indent=2, sort_keys=False)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--officer", required=True)
    ap.add_argument("--scope", required=True, help="cabinet/mcp-scope.yml (read-only)")
    ap.add_argument("--input", required=True, help="merged MCP config to filter")
    ap.add_argument("--out-mcp", required=True)
    ap.add_argument("--out-settings", required=True)
    ap.add_argument(
        "--extra-allow",
        default="",
        help="csv of launcher infra pass-through servers (ignored on scope-parse failure)",
    )
    args = ap.parse_args(argv)

    os.umask(0o077)

    extra = [x.strip() for x in args.extra_allow.split(",") if x.strip()]
    allowed = resolve_allowed(args.officer, args.scope, extra)
    mcp_cfg = filter_config(args.input, allowed)

    # Settings overlay mirrors the GRANTS (not merely the servers present in
    # today's input) so a server later added to a config layer without a
    # scope grant stays capped by allowedMcpServers as well.
    # Shape (2.1.202): each entry MUST be an object — {"serverName": ...}
    # (string entries fail settings validation and BLOCK officer boot with an
    # interactive "Invalid entry" dialog; found live on the 2026-07-07 rolling
    # restart). Note the binary also documents allowedMcpServers as honored
    # ONLY from managed settings — from this --settings overlay it is
    # defense-in-depth documentation of the grant set; the enforced scoping
    # is the filtered --mcp-config + --strict-mcp-config pair.
    settings = {
        "allowedMcpServers": [{"serverName": s} for s in sorted(allowed)],
        "enableAllProjectMcpServers": False,
    }

    try:
        write_atomic(args.out_mcp, mcp_cfg)
        write_atomic(args.out_settings, settings)
    except OSError as exc:
        log_err("could not write outputs (%s) — caller must fail closed" % exc)
        return 1

    kept = sorted(mcp_cfg.get("mcpServers", {}))
    sys.stderr.write(
        "gen-officer-mcp-config: officer=%s allowed=%d server(s) booted=%s\n"
        % (args.officer, len(allowed), ",".join(kept) if kept else "(none)")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
