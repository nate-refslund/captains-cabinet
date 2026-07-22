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


def _data_optional() -> bool:
    """CI/egg data-optional mode — the cabinet-ci.yml World-binding step sets
    CABINET_WORLD_DATA_OPTIONAL=1; live boxes never do. It licenses SKIPs for
    absent/unpopulated INSTANCE surfaces; on a live box (flag unset) the same
    absence stays a hard FAIL (dead-pixel doctrine unchanged)."""
    return os.environ.get("CABINET_WORLD_DATA_OPTIONAL") == "1"


def _stripped_instance_path(rel: str) -> bool:
    """True when a repo-relative path lives under instance/ — a per-deployment
    artifact the egg export strips (only .example twins ship). In data-optional
    mode an absent instance/ mechanism_path is missing INSTANCE DATA, not a
    stale codex; a live box (flag unset) still FAILs a vanished instance path."""
    norm = str(rel).replace("\\", "/").lstrip("./")
    return norm == "instance" or norm.startswith("instance/")


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
            # class-b tolerance: an absent instance/ mechanism_path under the
            # data-optional flag is a stripped instance artifact, not a stale
            # codex (the egg export prunes instance/ to its .example twins). The
            # entry's source_binding, reading the same absent instance surface,
            # then SKIPs in the data-optional branch of validate(). A live box
            # (flag unset) still FAILs a vanished mechanism_path; a missing
            # FRAMEWORK path FAILs even under the flag (only instance/ is stripped).
            if not mech_path.exists() and not (
                    _data_optional() and _stripped_instance_path(mech)):
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


def _sandbox_reject(args: List[str]) -> Optional[str]:
    """Read-only sandbox admission — shared by execute_binding and the
    data-optional count probe. Returns a rejection reason, or None when the argv
    is admissible.

    Metacharacter guard, TOKEN-level: execution is shell=False, so a `|` INSIDE
    a quoted jq filter is inert data — but a STANDALONE metachar token means
    someone wrote shell syntax expecting a pipe/redirect (and would go live if
    anyone ever "simplified" to shell=True), and `$(`/backtick anywhere is never
    legitimate in a read-only binding. Dot-commands (.shell/.system/.load/…) run
    arbitrary shell + load extensions even under sqlite3 -readonly — they live
    inside one quoted argv token the metachar guard misses, so refuse any token
    LINE whose lstripped form starts '.'+alpha ('./relative/path' stays legal).
    Every path argument must realpath-resolve inside the repo."""
    prog = os.path.basename(args[0])
    if prog not in ALLOWED_BINARIES:
        return (f"binary '{prog}' not in read-only allowlist "
                f"{ALLOWED_BINARIES}")
    _STANDALONE_META = {"|", "||", ";", "&", "&&", ">", ">>", "<", "<<"}
    for tok in args:
        if tok in _STANDALONE_META:
            return "shell metacharacters refused (shell=False sandbox)"
        if "$(" in tok or "`" in tok:
            return "shell metacharacters refused (shell=False sandbox)"
    if prog == "sqlite3":
        if "-readonly" not in args:
            return "sqlite3 without -readonly refused"
        for tok in args[1:]:
            for line in tok.splitlines():
                if re.match(r"\s*\.[A-Za-z]", line):
                    return ("sqlite3 dot-command refused (never "
                            "legitimate in a read-only binding)")
    containment = _resolve_containment(args)
    if containment:
        return containment
    return None


def execute_binding(binding: str) -> Tuple[bool, str]:
    """Run one source_binding inside the sandbox. (ok, value_or_reason)."""
    try:
        args = shlex.split(binding)
    except ValueError as e:
        return False, f"unparseable binding: {e}"
    if not args:
        return False, "empty binding"
    reason = _sandbox_reject(args)
    if reason is not None:
        return False, reason
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


# ---- data-optional row-COUNT tolerance (class-a: existing-but-0-row surface) --
# grep -c / wc emit the row count to stdout and (for grep) exit 1 on zero rows.
# A count of 0 over a PRESENT instance surface that carries its own egg-export
# emptied marker (e.g. the R116 comment on captain-rules-index.yaml) is an
# unpopulated instance surface, not a dead pixel. The emptied-marker is the
# DOUBLE-KEY: a framework surface counting 0 (no marker) still FAILs even under
# the data-optional flag, so real rot keeps full teeth.
_COUNT_INT_RE = re.compile(r"^\s*(\d+)")
_EMPTIED_MARKER_RE = re.compile(
    r"emptied\b.*\begg export\b|\begg export\b.*\bemptied\b|\bper R116\b",
    re.IGNORECASE)


def _is_count_binding(args: List[str]) -> bool:
    """A read-only ROW/LINE count: `grep -c …` or `wc …`, whose numeric stdout
    is meaningful even on a nonzero exit (grep -c prints 0 and exits 1 when the
    surface has zero matching rows)."""
    if not args:
        return False
    prog = os.path.basename(args[0])
    if prog == "wc":
        return True
    if prog == "grep":
        return any(a.startswith("-") and not a.startswith("--") and "c" in a[1:]
                   for a in args[1:])
    return False


def _count_binding_value(binding: str) -> Optional[int]:
    """Integer row-count for a COUNT binding, read from stdout regardless of exit
    code. Returns None when the binding is not a clean count (unparseable,
    non-count binary, sandbox-rejected, or no numeric stdout) so the caller falls
    back to full-teeth execute_binding. Runs through the SAME sandbox as
    execute_binding — no path escapes, no shell."""
    try:
        args = shlex.split(binding)
    except ValueError:
        return None
    if not args or not _is_count_binding(args):
        return None
    if _sandbox_reject(args) is not None:
        return None
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=TIMEOUT_S,
            cwd=_REPO_ROOT, shell=False)
    except (subprocess.TimeoutExpired, OSError):
        return None
    m = _COUNT_INT_RE.match(proc.stdout or "")
    return int(m.group(1)) if m else None


def _count_surface_emptied_marker(args: List[str]) -> bool:
    """DOUBLE-KEY for a zero-count SKIP: True when the counted surface FILE exists
    and carries its own egg-export/instance emptied marker (the R116 comment on
    an emptied index). A framework surface counting 0 has no such marker, so it
    FAILs even under the data-optional flag — teeth against real rot preserved."""
    for tok in args[1:]:
        if tok.startswith("-") or not _PATH_TOKEN_RE.match(tok):
            continue
        p = _REPO_ROOT / tok
        if not p.is_file():
            continue
        try:
            head = p.read_text(encoding="utf-8", errors="replace")[:4096]
        except OSError:
            continue
        if _EMPTIED_MARKER_RE.search(head):
            return True
    return False


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
        if _data_optional():
            try:
                toks = shlex.split(entry["source_binding"])
            except ValueError:
                toks = []
            miss = _missing_data_paths(toks) if toks else []
            if miss:
                findings.append(Finding(
                    eid, "SKIP", f"data absent on this box: {', '.join(miss)[:120]}"))
                continue
            # class-a: a row-COUNT binding over a PRESENT but unpopulated instance
            # surface (the egg's emptied captain-rules index: `grep -c '- id:'`
            # returns 0 / exit 1). Zero rows on a surface that carries its own
            # egg-export emptied marker is an unpopulated instance surface, not a
            # dead pixel — correct for the egg AND for any fresh captain who has
            # not yet populated it. n>0 renders live with teeth; n==0 WITHOUT the
            # marker (or a non-count binding) falls through to execute_binding, so
            # real rot (e.g. an emptied FRAMEWORK surface) stays a hard FAIL.
            if _is_count_binding(toks):
                n = _count_binding_value(entry["source_binding"])
                if n is not None and n > 0:
                    findings.append(Finding(eid, "OK", "binding live", str(n)))
                    continue
                if n == 0 and _count_surface_emptied_marker(toks):
                    findings.append(Finding(
                        eid, "SKIP",
                        "instance surface unpopulated: 0 rows over an emptied "
                        f"instance surface ({os.path.basename(toks[0])} count; "
                        "egg export empties it per its own marker, a live box "
                        "would FAIL)"))
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
