#!/usr/bin/env python3.12
"""world-binding-validator.py — the binding executor (Cabinet World E1).

Growth doc §2 (ratified 2026-07-07): "every mapping's source_binding command
executes at PR time and every render tick in a read-only allowlisted sandbox
… errors/empty/non-monotonic-for-accretive = cannot merge. Hallucinated or
dead pixels are structurally impossible."

This validator makes that mechanical for cabinet/world/morphology.yml:

  * SCHEMA — every entry must carry id / represents / source_binding /
    scope(org-global|per-officer|dark) / tier(T0..T3) / replay
    (ledger|git|none) / codex{represents, mechanism_path, day0}. Untiered or
    unreplayed bindings are REJECTED (S1-F2/F5 doctrine: privacy and replay
    honesty live in schema the validator can refuse, never in reviewer
    discipline).
  * CODEX LINT — mechanism_path must EXIST in the repo (a moved/deleted
    mechanism flags the codex stale); codex.represents must not merely
    restate the entry id.
  * SANDBOX EXECUTION — source_binding runs with shell=False after strict
    tokenization; argv[0] must be in the ALLOWLIST (sqlite3 with -readonly
    ENFORCED **and dot-commands refused** — .shell/.system/.load run
    shell/extensions even under -readonly; wc, ls, jq, grep); every path
    argument must realpath-resolve INSIDE the repo (no traversal, no symlink escape, no /etc reads);
    10s timeout; non-zero exit or empty stdout = FAIL (dead pixel).
  * DARK SCOPE — entries with scope: dark skip execution (dark mechanisms
    render dark; they still need schema + codex).

Runs ON-BOX (S1-F8 — CI never holds prod credentials; there are none here
anyway: the allowlist is local read-only tools). Exit 0 = every binding
green; exit 1 = any failure, with one line per finding.

Usage:
  python3.12 cabinet/scripts/world-binding-validator.py [morphology.yml]
  python3.12 cabinet/scripts/world-binding-validator.py --json  # machine out
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

_REPO_ROOT = Path(os.environ.get("CABINET_ROOT")
                  or Path(__file__).resolve().parents[2])

DEFAULT_MORPHOLOGY = _REPO_ROOT / "cabinet" / "world" / "morphology.yml"

# The ratified read-only sandbox allowlist (growth doc §2; grep added for
# the captain-rules '- id:' count class — still read-only line counting).
ALLOWED_BINARIES = ("sqlite3", "wc", "ls", "jq", "grep")

SCOPES = ("org-global", "per-officer", "dark")
TIERS = ("T0", "T1", "T2", "T3")
REPLAYS = ("ledger", "git", "none")

TIMEOUT_S = 10


class Finding:
    def __init__(self, entry_id: str, level: str, message: str,
                 value: Optional[str] = None):
        self.entry_id = entry_id
        self.level = level          # OK | FAIL
        self.message = message
        self.value = value

    def as_dict(self) -> Dict[str, Any]:
        return {"id": self.entry_id, "level": self.level,
                "message": self.message, "value": self.value}


def check_schema(entry: Any) -> List[str]:
    """Schema violations for one entry (empty list = clean)."""
    problems: List[str] = []
    if not isinstance(entry, dict):
        return ["entry is not a mapping"]
    eid = entry.get("id")
    if not isinstance(eid, str) or not re.fullmatch(r"[a-z0-9_.-]{1,64}", eid):
        problems.append("id missing/malformed")
    if not isinstance(entry.get("represents"), str):
        problems.append("represents missing")
    if not isinstance(entry.get("source_binding"), str):
        problems.append("source_binding missing")
    if entry.get("scope") not in SCOPES:
        problems.append(f"scope must be one of {SCOPES}")
    if entry.get("tier") not in TIERS:
        problems.append("untiered binding rejected (tier T0..T3 required)")
    if entry.get("replay") not in REPLAYS:
        problems.append("replay (ledger|git|none) required — a binding "
                        "without a replay stance lies under ?at=")
    codex = entry.get("codex")
    if not isinstance(codex, dict):
        problems.append("codex required (human-authored; no LLM between "
                        "ledger and explanation)")
    else:
        for field in ("represents", "mechanism_path", "day0"):
            if not isinstance(codex.get(field), str) or not codex[field]:
                problems.append(f"codex.{field} missing")
        mech = codex.get("mechanism_path")
        if isinstance(mech, str) and mech:
            mech_path = (_REPO_ROOT / mech)
            if not mech_path.exists():
                problems.append(
                    f"codex.mechanism_path does not exist: {mech} "
                    f"(moved/deleted mechanism = stale codex)")
        rep = codex.get("represents")
        if (isinstance(rep, str) and isinstance(eid, str)
                and rep.strip().lower().replace("_", " ")
                == eid.strip().lower().replace("_", " ")):
            problems.append("codex.represents merely restates the entry id")
    return problems


def _resolve_containment(args: List[str]) -> Optional[str]:
    """Every path-looking argument must realpath inside the repo."""
    for arg in args[1:]:
        if arg.startswith("-"):
            continue
        # jq filter strings etc. are not paths; treat as path when it exists
        # relative to repo or is absolute.
        candidate: Optional[Path] = None
        if arg.startswith("/") or arg.startswith("~"):
            candidate = Path(os.path.expanduser(arg))
        elif "/" in arg or Path(_REPO_ROOT / arg).exists():
            candidate = _REPO_ROOT / arg
        if candidate is None:
            continue
        real = Path(os.path.realpath(candidate))
        try:
            real.relative_to(Path(os.path.realpath(_REPO_ROOT)))
        except ValueError:
            return (f"path argument escapes the repo: {arg} -> {real} "
                    f"(realpath containment)")
    return None


_PATH_TOKEN_RE = re.compile(r"^[\w.-]+(/[\w.-]+)+$")


def _missing_data_paths(args: List[str]) -> List[str]:
    """Repo-relative path-shaped argv tokens that do not exist on disk.

    Used ONLY by the data-optional mode: a binding over a RUNTIME artifact
    (chronicle jsonl, memory store) can never find its data on a CI runner —
    that is absent DATA, not broken GRAMMAR. Deterministic token shape check
    (contains '/', no leading '-', pure word/dot/dash segments), never output
    parsing. jq filters ('.x | length') and flags never match the shape."""
    out = []
    for tok in args[1:]:
        if tok.startswith("-") or not _PATH_TOKEN_RE.match(tok):
            continue
        if not (_REPO_ROOT / tok).exists():
            out.append(tok)
    return out


def execute_binding(binding: str) -> Tuple[bool, str]:
    """Run one source_binding inside the sandbox. (ok, value_or_reason)."""
    try:
        args = shlex.split(binding)
    except ValueError as e:
        return False, f"unparseable binding: {e}"
    if not args:
        return False, "empty binding"
    prog = os.path.basename(args[0])
    if prog not in ALLOWED_BINARIES:
        return False, (f"binary '{prog}' not in read-only allowlist "
                       f"{ALLOWED_BINARIES}")
    # Metacharacter guard, TOKEN-level: execution is shell=False, so a `|`
    # INSIDE a quoted jq filter is inert data — but a STANDALONE metachar
    # token means someone wrote shell syntax expecting a pipe/redirect
    # (and would go live if anyone ever "simplified" to shell=True), and
    # `$(`/backtick anywhere is never legitimate in a read-only binding.
    _STANDALONE_META = {"|", "||", ";", "&", "&&", ">", ">>", "<", "<<"}
    for tok in args:
        if tok in _STANDALONE_META:
            return False, "shell metacharacters refused (shell=False sandbox)"
        if "$(" in tok or "`" in tok:
            return False, "shell metacharacters refused (shell=False sandbox)"
    if prog == "sqlite3":
        if "-readonly" not in args:
            return False, "sqlite3 without -readonly refused"
        # Dot-commands (.shell/.system/.load/.once/.import/.output/…) run
        # arbitrary shell + load extensions even under -readonly — the
        # metachar guard misses them because they live inside one quoted
        # argv token with no standalone metacharacter. Refuse any token
        # LINE whose lstripped form starts '.'+alpha: covers whole-token
        # dot-commands AND a '.shell' smuggled behind a newline inside a
        # SQL token. './relative/path' (dot + slash) stays legal.
        for tok in args[1:]:
            for line in tok.splitlines():
                if re.match(r"\s*\.[A-Za-z]", line):
                    return False, ("sqlite3 dot-command refused (never "
                                   "legitimate in a read-only binding)")
    containment = _resolve_containment(args)
    if containment:
        return False, containment
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=TIMEOUT_S,
            cwd=_REPO_ROOT, shell=False)
    except subprocess.TimeoutExpired:
        return False, f"binding timed out (> {TIMEOUT_S}s)"
    except OSError as e:
        return False, f"binding failed to execute: {e}"
    if proc.returncode != 0:
        return False, (f"exit {proc.returncode}: "
                       f"{(proc.stderr or '').strip()[:120] or 'no stderr'}")
    out = proc.stdout.strip()
    if not out:
        return False, "empty output = dead pixel (cannot merge)"
    return True, out[:200]


def validate(morphology_path: Path) -> List[Finding]:
    findings: List[Finding] = []
    try:
        doc = yaml.safe_load(morphology_path.read_text())
    except (OSError, yaml.YAMLError) as e:
        return [Finding("-", "FAIL", f"morphology unreadable: {e}")]
    if not isinstance(doc, dict) or not isinstance(doc.get("version"), int):
        return [Finding("-", "FAIL", "morphology.yml missing integer version")]
    entries = doc.get("entries")
    if not isinstance(entries, list) or not entries:
        return [Finding("-", "FAIL", "morphology.yml has no entries")]
    for entry in entries:
        eid = str(entry.get("id", "?")) if isinstance(entry, dict) else "?"
        problems = check_schema(entry)
        if problems:
            for p in problems:
                findings.append(Finding(eid, "FAIL", p))
            continue
        if entry["scope"] == "dark":
            findings.append(Finding(eid, "OK", "dark scope — renders dark, "
                                               "execution skipped"))
            continue
        # DATA-OPTIONAL mode (CI, 2026-07-09): runtime artifacts (chronicle
        # jsonl, memory store, ledgers) exist only on a live box — on a
        # runner their absence is missing DATA, not broken grammar. The
        # armed gate was permanently red on every fresh checkout (unmasked
        # when the earlier pytest red was fixed). Live boxes do NOT set the
        # env var, so a vanished chronicle there stays a hard FAIL
        # (dead-pixel doctrine unchanged).
        if os.environ.get("CABINET_WORLD_DATA_OPTIONAL") == "1":
            try:
                miss = _missing_data_paths(shlex.split(entry["source_binding"]))
            except ValueError:
                miss = []
            if miss:
                findings.append(Finding(
                    eid, "SKIP", f"data absent on this box: {', '.join(miss)[:120]}"))
                continue
        ok, value = execute_binding(entry["source_binding"])
        if ok:
            findings.append(Finding(eid, "OK", "binding live", value))
        else:
            findings.append(Finding(eid, "FAIL", value))
    return findings


def main(argv: List[str]) -> int:
    as_json = "--json" in argv
    paths = [a for a in argv if not a.startswith("--")]
    morphology = Path(paths[0]) if paths else DEFAULT_MORPHOLOGY
    if not morphology.exists():
        msg = (f"morphology not found at {morphology} — grammar law not yet "
               f"merged (fail-closed: nothing to validate is a FAIL at PR "
               f"time, a SKIP for the fleet)")
        if as_json:
            print(json.dumps({"status": "absent", "message": msg}))
        else:
            print(f"WORLD_BINDINGS ABSENT — {msg}")
        return 0 if os.environ.get("CABINET_WORLD_REQUIRE_GRAMMAR") != "1" else 1
    findings = validate(morphology)
    fails = [f for f in findings if f.level == "FAIL"]
    skips = [f for f in findings if f.level == "SKIP"]
    if as_json:
        print(json.dumps({
            "status": "fail" if fails else "ok",
            "findings": [f.as_dict() for f in findings],
        }, indent=2))
    else:
        for f in findings:
            val = f" = {f.value}" if f.value else ""
            print(f"{f.level:4} {f.entry_id}: {f.message}{val}")
        print(f"WORLD_BINDINGS {'FAIL' if fails else 'GREEN'} "
              f"(entries={len(findings)}, fails={len(fails)}, "
              f"data-skips={len(skips)})")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
