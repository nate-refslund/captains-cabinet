#!/usr/bin/env python3.12
"""workaround-retest.py — sandboxed retest runner for the workarounds registry.

Given workaround ids (or --all, or --from-delta <radar-delta.json>), runs each
row's ``retest_cmd`` from cabinet/config/workarounds.yml and emits ONE JSON
verdict line per row on stdout:

    {"id": "...", "verdict": "still_needed" | "fix_confirmed" | "inconclusive", ...}

Verdict contract (pinned by cabinet/scripts/tests/test_workaround_retest.py):
    probe exit 0  -> still_needed   (defect reproduced; keep the workaround)
    probe exit 1  -> fix_confirmed  (defect absent; retirement proposable)
    anything else -> inconclusive   (incl. timeout, spawn failure, refusal)

SAFETY MODEL — three honest layers, no false guarantee:
  1. REVIEWED CONFIG is the first trust boundary. The registry is tracked
     and only changes by reviewed PR; retest_cmds are authored, not fetched.
  2. SCREEN is a fast drift/typo filter — NOT a complete security boundary.
     It requires (a) a read-only allowlisted first binary, (b) no mutation
     verbs literal OR path-qualified (rm/mv/kill/launchctl/redis-cli/git/
     curl/sudo/... — a `/`-boundary-aware word scan plus a per-token basename
     check), (c) no redirection/backgrounding, (d) the house interpreter
     only. Rows that fail are REFUSED (never executed; verdict inconclusive,
     ``refused: true``; process exit 3). What the screen CANNOT catch: a
     value handed to ``bash -c`` can reassemble a verb at runtime via
     quote-removal / var-splice (``$a$b``, ``${g}${t}``) that a static string
     scan never sees. So the screen stops drift and typos, not a determined
     author — layer 3 is what actually contains execution.
  3. SANDBOX is the execution containment. On macOS every probe runs under
     ``sandbox-exec`` with deny file-write* (except a per-run scratch dir),
     deny network*, deny signal — so even a screen-bypassing verb cannot
     mutate the fleet, exfiltrate, or signal a process. Each verdict is
     stamped ``sandboxed: true|false``. Where no OS sandbox exists (non-macOS,
     e.g. the Linux CI runner) the stamp is ``false`` and execution is
     unconfined: there layer 1 (reviewed config) is the only boundary, by
     construction — never claim otherwise. Residual even under the profile:
     mach-service mutation (launchctl) is not fully confined by deny-signal;
     the screen's literal+path-qualified catch is the guard for it, which is
     one more reason the registry stays reviewed config.
  * CONSTRUCTED env. Probes run with a minimal env (PATH + scratch HOME/
    TMPDIR, LC_ALL=C, PYTHONDONTWRITEBYTECODE=1) — the parent environment is
    NEVER inherited, so credentials / REDIS_* / NEON_* never reach a probe.
  * SCRUBBED output. stdout/stderr tails are redacted of common secret shapes
    (url creds, KEY=/TOKEN=/PASSWORD=/CONNECTION= assignments, Bearer, AWS
    keys) before journaling; only a length + sha256 of the raw output — never
    the text — propagates to the propose-only proposals ledger.
  * Hard timeout per probe (default 60s; --timeout / CABINET_RETEST_TIMEOUT).

UNTRUSTED-DATA MODEL (--from-delta): the radar delta file is fetched-content
derived and therefore UNTRUSTED. It is parsed with the json module only;
component names are compared by plain string equality against registry
version_condition components; versions are compared segment-numerically, and
only VERSION-SHAPED new_version values (optional v prefix + dotted numerals
+ optional dot/dash/plus alphanumeric qualifiers, <=120 chars) can match a
comparator condition — the radar's sha256:<hash> content stamps and probe
status words never do (the sha-false-fire guard; see is_version_shaped).
NOTHING from the delta file is ever interpolated into a command line,
executed, or evaluated — delta text can only ever appear json-encoded inside
verdict/evidence output. The command executed for a matched row is always the
registry's own (screened) retest_cmd.

PROPOSE ONLY: a fix_confirmed verdict appends an evidence-attached retirement
proposal to shared/interfaces/workaround-retire-proposals.jsonl using the
needs-ledger pattern (content-fingerprint id ``WPROP-<sha8>``, append-only
O_APPEND JSONL, last-write-wins per id, re-filing bumps count/last_seen
instead of duplicating). This runner never edits the registry, never
restarts/installs/upgrades anything, and never touches the network. Humans
retire a row via a reviewed PR after the proposal is judged.

ACTION SEAM (Captain law 2026-07-17): the retirement DISPOSITION is no
longer a hardcoded v1 constant — it is asked of the autonomy-graded action
seam (``framework/authority/action_mode.py``, THE law for autonomous-
mutation modes) and stamped into the verdict + proposal row as
``action_mode`` (+ ``captain_card``). Under guardian/earn_up the seam
answers ``propose`` and behavior is IDENTICAL to v1. A future attested
sovereign posture may answer ``go`` — acting on it would additionally
require a Captain-PRE-ratified trivial class (``_PRERATIFIED_AUTO_CLASSES``,
empty until a recorded ratification exists) and an applier that lives
elsewhere; this runner files propose-only rows in every mode. Ring-0
components (the claude binary, officer model routing — GATE 3) classify as
Ring-0 categories, so their disposition is propose + captain-card under
EVERY posture. Consult-the-seam can only tighten, never widen.

Runtime outputs (all gitignored):
  cabinet/logs/workaround-retests.jsonl                — verdict journal
  shared/interfaces/workaround-retire-proposals.jsonl  — proposals ledger

Doctrine: docs/runbooks/platform-adoption-gating.md. Officer entry point:
cabinet/scripts/workaround-retest.sh. Registry: cabinet/config/workarounds.yml.

Exit codes: 0 ran (verdicts on stdout) · 2 usage · 3 >=1 row refused by the
screen · 4 registry missing/invalid/unknown id · 5 delta unreadable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------
# Roots + constants
# --------------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).resolve().parent          # cabinet/scripts
_DEFAULT_ROOT = _SCRIPT_DIR.parents[1]                 # repo root

REGISTRY_REL = Path("cabinet/config/workarounds.yml")
LOG_REL = Path("cabinet/logs/workaround-retests.jsonl")
PROPOSALS_REL = Path("shared/interfaces/workaround-retire-proposals.jsonl")

VERDICT_STILL = "still_needed"
VERDICT_FIXED = "fix_confirmed"
VERDICT_INCONCLUSIVE = "inconclusive"

REQUIRED_FIELDS = (
    "id", "symptom", "cause", "workaround",
    "version_condition", "retest_cmd", "owner_surface", "recorded",
)

_ID_RE = re.compile(r"^WA-\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9-]*$")
_RECORDED_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Read-only binaries a retest_cmd may START with (basename of first token).
# `find` is deliberately absent: its -exec/-delete flag-verbs dodge the
# hyphen-tolerant word-boundary scan below.
ALLOWED_FIRST_TOKENS = frozenset({
    "grep", "python3.12", "bash", "sh", "env", "awk", "readlink", "stat",
    "cat", "head", "tail", "wc", "cut", "sort", "uniq", "diff", "cmp",
    "printf", "echo", "test", "[", "command", "true", "false",
    "file", "basename", "dirname",
})

# Mutation / fleet-touching / network verbs a retest_cmd may NEVER contain
# (word-boundary scan over the WHOLE string — chaining cannot hide them).
FORBIDDEN_VERBS = (
    "rm", "rmdir", "mv", "cp", "dd", "tee", "truncate", "shred",
    "mkdir", "mkfifo", "mknod", "touch", "ln", "link", "unlink",
    "chmod", "chown", "chgrp", "chflags", "xattr",
    "kill", "killall", "pkill", "launchctl", "bootout", "kickstart",
    "tmux", "git", "gh", "redis-cli", "psql", "sqlite3", "mysql",
    "curl", "wget", "nc", "ncat", "telnet", "socat", "ssh", "scp",
    "sftp", "rsync", "sudo", "doas", "su", "osascript", "defaults",
    "systemsetup", "networksetup", "pmset", "reboot", "shutdown", "halt",
    "open", "brew", "port", "apt", "apt-get", "yum", "dnf",
    "npm", "npx", "yarn", "pnpm", "bun", "node", "deno",
    "pip", "pip3", "gem", "cargo", "make", "install",
    "mount", "umount", "diskutil", "hdiutil", "csrutil", "spctl",
    "crontab", "at", "batch", "perl", "ruby",
    "eval", "exec", "source", "trap", "nohup", "disown", "setsid",
)
_FORBIDDEN_VERB_SET = frozenset(FORBIDDEN_VERBS)
# Lookbehind EXCLUDES `/` from the boundary class on purpose so a
# path-qualified mutation binary (/bin/rm, /usr/bin/curl, ./x/rm) is CAUGHT:
# `/` ends a word here. It still exempts file.rm / x-rm (verb glued to
# `\w`/`.`/`-`). The per-token basename check in screen_cmd() is the belt.
_FORBIDDEN_RE = re.compile(
    r"(?<![\w.-])(?:" + "|".join(re.escape(v) for v in FORBIDDEN_VERBS) + r")(?![\w.-])",
    re.IGNORECASE,
)
# python/python2/python3/python3.x may write files via -c; only python3.12
# (the house interpreter, allowlisted above as a FIRST token for file-based
# probes) is tolerated anywhere in the string. `/`-boundary-aware (same P2 fix
# as _FORBIDDEN_RE) so a path-qualified /usr/bin/python3.13 cannot slip the
# interpreter pin; /opt/homebrew/bin/python3.12 still resolves to the house id.
_ANY_PYTHON_RE = re.compile(r"(?<![\w.-])(python[\w.]*)", re.IGNORECASE)
_FIND_FLAG_VERBS_RE = re.compile(
    r"-(?:exec(?:dir)?|delete|ok(?:dir)?|fprintf?|fprint0?)\b", re.IGNORECASE)

_VC_COMPARATOR_RE = re.compile(
    r"^\s*([A-Za-z0-9._-]+)\s*(>=|<=|==|!=|>|<)\s*([A-Za-z0-9._+-]+)\s*$"
)

# UNTRUSTED new_version gate for comparator conditions (the sha-false-fire
# P2). The radar's observe half stamps content-only changelog deltas as
# new_version="sha256:<12hex>" mirror rows, and probe rows can carry status
# words ("FAIL", "never-checked") when no banner version parses.
# compare_versions()'s fallback ranks ANY non-numeric segment AFTER every
# numeric one, so without this gate such strings would satisfy
# `<component> > <pin>` for EVERY numeric pin — pure content churn would
# false-queue comparator retests nightly. Comparator conditions therefore
# only ever match VERSION-SHAPED delta values: the shape registry pins and
# real component versions actually take (2.1.230, v2.2, 1.2.3-beta.1,
# 1.2.3+build.5) — optional v/V prefix, dotted numerals, then optional
# dot/dash/plus-joined alphanumeric qualifiers. `fixed-in:` rows are never
# auto-matched at all and the grammar has no existence-style conditions, so
# a non-version-shaped delta value simply never matches anything.
# Length-cap BEFORE the regex: the value rides an untrusted delta file and
# the anchored scan must stay trivially linear even on flood-sized strings
# (same bounded-input discipline as the radar's 120-char banner cap).
_VERSION_SHAPED_MAX_LEN = 120
_VERSION_SHAPED_RE = re.compile(r"^[vV]?\d+(?:\.\d+)*(?:[.+-][A-Za-z0-9]+)*$")


def is_version_shaped(value) -> bool:
    """True when an (untrusted) delta version string is version-shaped."""
    if not isinstance(value, str):
        return False
    v = value.strip()
    return 0 < len(v) <= _VERSION_SHAPED_MAX_LEN and bool(_VERSION_SHAPED_RE.match(v))

# --------------------------------------------------------------------------
# Secret scrubbing (probe stdout/stderr is DATA and may hold a read secret)
# --------------------------------------------------------------------------
# A probe can `cat` a file the sandbox lets it READ (reads are allowed;
# writes/network/signals are not), so a careless/hostile probe can print a
# credential. These tails are journaled — redact common secret shapes before
# they are stored, and never propagate the raw text to the proposals ledger.
_REDACT = "[REDACTED]"
_SECRET_SUBS = (
    # scheme://[user]:password@host  ->  keep scheme+user, drop the password.
    # user part is OPTIONAL (redis://:pass@host is password-only).
    (re.compile(r"\b([a-z][a-z0-9+.\-]*://[^\s:/@]*):[^\s@]+@", re.IGNORECASE),
     r"\1:" + _REDACT + "@"),
    # KEY= / TOKEN= / PASSWORD= / SECRET= / CONNECTION= / API_KEY= ... = <value>
    (re.compile(
        r"(?i)\b([A-Za-z0-9_.\-]*"
        r"(?:passwd|password|secret|token|api[_-]?key|apikey|access[_-]?key|"
        r"private[_-]?key|credential|connection[_-]?string|conn[_-]?str|pwd|key)"
        r"[A-Za-z0-9_.\-]*)\s*=\s*\"?[^\s\"'`]+",
        ),
     r"\1=" + _REDACT),
    # Bearer <token> — redact the TOKEN that follows the scheme word (not the
    # word). Catches a bare `Bearer eyJ...` and the `Authorization: Bearer ...`
    # header alike (the token is what leaks).
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-+/=]{6,}"), "Bearer " + _REDACT),
    # Authorization: <value> with no Bearer scheme word.
    (re.compile(r"(?i)\b(authorization)\s*:\s*[A-Za-z0-9._\-+/=]{6,}"),
     r"\1: " + _REDACT),
    # AWS access-key id
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), _REDACT),
    # PEM private-key blocks (single-line collapse tolerant)
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
                re.DOTALL), _REDACT),
)


def _scrub_secrets(text: str) -> str:
    """Redact common secret shapes from probe output. Conservative by design:
    keys on secret-ish NAMES / url-cred / bearer / AWS / PEM shapes, so benign
    output (e.g. a grep hit like MEM_REDIS_HOST=\"${REDIS_HOST:-redis}\") is
    left intact. Not a guarantee that every secret is caught — the primary
    control is the constructed env (creds never reach a probe via ENV); this
    covers the residual disk-read path."""
    if not text:
        return text
    for pattern, repl in _SECRET_SUBS:
        text = pattern.sub(repl, text)
    return text


# --------------------------------------------------------------------------
# Execution sandbox availability (macOS sandbox-exec; honest stamp elsewhere)
# --------------------------------------------------------------------------
# The screen (above) is a drift/typo filter, not a containment boundary — a
# value handed to `bash -c` can reassemble a verb at runtime. The REAL
# containment is an OS sandbox around execution. macOS ships `sandbox-exec`;
# we resolve it once. On any platform without it the verdict is stamped
# sandboxed=false and execution is unconfined (reviewed-config trust only).
_SANDBOX_EXEC = shutil.which("sandbox-exec") if sys.platform == "darwin" else None
_WARNED_NO_SANDBOX = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cabinet_id() -> str:
    # Mirrors framework/authority/needs.py — proposal fingerprints are
    # per-cabinet so two cabinets never dedup against each other.
    return os.environ.get("CABINET_ID", "main")


# --------------------------------------------------------------------------
# Registry load + validation
# --------------------------------------------------------------------------

def load_registry(path: Path) -> list[dict]:
    """Parse the registry; raises ValueError with a named reason on any shape
    problem (the caller maps that to exit 4). Uses yaml.safe_load ONLY."""
    try:
        import yaml  # standing repo dep (generate-plists.py imports it too)
    except ImportError as exc:  # pragma: no cover - environment problem
        raise ValueError(f"pyyaml unavailable: {exc}") from exc
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"registry unreadable: {path}: {exc}") from exc
    try:
        doc = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ValueError(f"registry not valid YAML: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("workarounds"), list):
        raise ValueError("registry must be a mapping with a `workarounds` list")
    rows = doc["workarounds"]
    seen: set[str] = set()
    for i, row in enumerate(rows):
        errs = validate_row(row)
        if errs:
            raise ValueError(f"workarounds[{i}] invalid: " + "; ".join(errs))
        if row["id"] in seen:
            raise ValueError(f"duplicate workaround id: {row['id']}")
        seen.add(row["id"])
    return rows


def validate_row(row) -> list[str]:
    """Field-level validation for one registry row. Returns [] when valid."""
    errs: list[str] = []
    if not isinstance(row, dict):
        return ["row is not a mapping"]
    for field in REQUIRED_FIELDS:
        val = row.get(field)
        if field == "recorded" and val is not None and not isinstance(val, str):
            # yaml parses bare dates as datetime.date; the registry quotes
            # them, but tolerate + normalize for validation purposes.
            val = str(val)
        if not isinstance(val, str) or not val.strip():
            errs.append(f"missing/empty field `{field}`")
    if errs:
        return errs
    if not _ID_RE.match(row["id"]):
        errs.append(f"id `{row['id']}` not WA-YYYY-MM-DD-<kebab-slug>")
    if not _RECORDED_RE.match(str(row["recorded"])):
        errs.append(f"recorded `{row['recorded']}` not YYYY-MM-DD")
    if parse_version_condition(row["version_condition"]) is None:
        errs.append(
            f"version_condition `{row['version_condition']}` is neither "
            "`<component> <op> <version>` nor `fixed-in: <text>`"
        )
    return errs


# --------------------------------------------------------------------------
# version_condition grammar + comparison
# --------------------------------------------------------------------------

def parse_version_condition(cond: str):
    """-> ("comparator", component, op, version) | ("fixed-in", text) | None."""
    if not isinstance(cond, str) or not cond.strip():
        return None
    text = " ".join(cond.split())  # YAML folded scalars fold to single spaces
    if text.lower().startswith("fixed-in:"):
        rest = text[len("fixed-in:"):].strip()
        return ("fixed-in", rest) if rest else None
    m = _VC_COMPARATOR_RE.match(text)
    if not m:
        return None
    return ("comparator", m.group(1), m.group(2), m.group(3))


def _version_key(version: str) -> list:
    parts = version.strip().lstrip("vV").split(".")
    key: list = []
    for part in parts:
        # (0, int) sorts before (1, str): purely numeric segments compare
        # numerically; anything else falls back to string comparison.
        key.append((0, int(part)) if part.isdigit() else (1, part))
    return key


def compare_versions(a: str, b: str) -> int:
    """-1 / 0 / 1 with zero-fill (2.1 == 2.1.0)."""
    ka, kb = _version_key(a), _version_key(b)
    pad = max(len(ka), len(kb))
    ka += [(0, 0)] * (pad - len(ka))
    kb += [(0, 0)] * (pad - len(kb))
    return (ka > kb) - (ka < kb)


def condition_matches_delta(cond: str, component: str, new_version: str) -> bool:
    """True when a radar delta component satisfies a comparator condition.

    ``component`` / ``new_version`` come from the UNTRUSTED delta file: they
    are only ever string-compared here — never executed, never interpolated.
    Comparators additionally require a VERSION-SHAPED ``new_version`` (see
    ``is_version_shaped``): the radar's sha256:<hash> content stamps and
    probe status words must never false-fire a version pin.
    """
    parsed = parse_version_condition(cond)
    if not parsed or parsed[0] != "comparator":
        return False  # fixed-in rows are never auto-matched
    _, comp, op, pinned = parsed
    if not isinstance(component, str) or not isinstance(new_version, str):
        return False
    if component.strip().lower() != comp.lower():
        return False
    if not is_version_shaped(new_version):
        # sha256:<hash> content stamps, probe status words ("FAIL"), and any
        # other non-version-shaped delta value NEVER match a comparator —
        # compare_versions' string fallback would otherwise rank them above
        # every numeric pin (the sha-false-fire P2).
        return False
    try:
        c = compare_versions(new_version, pinned)
    except Exception:
        return False
    return {
        ">": c > 0, ">=": c >= 0, "==": c == 0,
        "!=": c != 0, "<=": c <= 0, "<": c < 0,
    }[op]


# --------------------------------------------------------------------------
# Command screen (read-only shape enforcement)
# --------------------------------------------------------------------------

def screen_cmd(cmd) -> tuple[bool, str]:
    """(ok, reason). Refuses anything that is not a read-only probe SHAPE:
    allowlisted first binary, no mutation verbs anywhere, no redirection."""
    if not isinstance(cmd, str) or not cmd.strip():
        return False, "empty retest_cmd"
    if "\x00" in cmd:
        return False, "NUL byte in retest_cmd"
    if ">" in cmd or "<" in cmd:
        return False, "redirection characters are not allowed (probes print, never write)"
    if re.search(r"&(?!&)", cmd):
        return False, "backgrounding `&` is not allowed"
    try:
        tokens = shlex.split(cmd, posix=True)
    except ValueError as exc:
        return False, f"unparseable command: {exc}"
    if not tokens:
        return False, "empty retest_cmd"
    first = os.path.basename(tokens[0])
    if first not in ALLOWED_FIRST_TOKENS:
        return False, f"first token `{first}` not in the read-only allowlist"
    # Belt for the path-qualified case: a bare path token whose basename is a
    # mutation verb (/bin/rm, ./x/curl). Skip tokens carrying whitespace —
    # those are quoted `bash -c` payloads, scanned in-string by _FORBIDDEN_RE.
    for tok in tokens:
        if any(c.isspace() for c in tok):
            continue
        base = os.path.basename(tok).lower()
        if base in _FORBIDDEN_VERB_SET:
            return False, f"mutation verb `{base}` (path-qualified token `{tok}`)"
    hit = _FORBIDDEN_RE.search(cmd)
    if hit:
        return False, f"mutation verb `{hit.group(0)}`"
    for m in _ANY_PYTHON_RE.finditer(cmd):
        if m.group(1).lower() != "python3.12":
            return False, (f"interpreter `{m.group(1)}` not allowed "
                           "(use python3.12)")
    hit = _FIND_FLAG_VERBS_RE.search(cmd)
    if hit:
        return False, f"flag verb `{hit.group(0)}` not allowed"
    return True, ""


# --------------------------------------------------------------------------
# Sandboxed execution
# --------------------------------------------------------------------------

def _sandbox_env(scratch: Path) -> dict:
    """Constructed-from-scratch env: interpreter dir + system dirs only.
    The parent env is NOT inherited — no credentials, no REDIS_*/NEON_*."""
    py_dir = os.path.dirname(shutil.which("python3.12") or sys.executable)
    path_dirs = [py_dir, "/usr/bin", "/bin", "/usr/sbin", "/sbin",
                 "/opt/homebrew/bin", "/usr/local/bin"]
    home = scratch / "home"
    tmp = scratch / "tmp"
    home.mkdir(parents=True, exist_ok=True)
    tmp.mkdir(parents=True, exist_ok=True)
    return {
        "PATH": ":".join(dict.fromkeys(d for d in path_dirs if d)),
        "HOME": str(home),
        "TMPDIR": str(tmp),
        "LC_ALL": "C",
        "LANG": "C",
        # Deny-file-write* would block a python probe's __pycache__ write; keep
        # bytecode off so the house interpreter runs clean under the sandbox.
        "PYTHONDONTWRITEBYTECODE": "1",
        "CABINET_WORKAROUND_RETEST": "1",
    }


def _sandbox_profile(scratch_real: str) -> str:
    """macOS sandbox-exec profile: allow reads + exec, DENY all file writes
    (except the per-run scratch dir + /dev/null), DENY network, DENY signals.
    A screen-bypassing verb reassembled at runtime cannot mutate the fleet,
    exfiltrate, or signal a process from inside this profile."""
    return (
        "(version 1)"
        "(allow default)"
        "(deny file-write*)"
        f'(allow file-write* (subpath "{scratch_real}"))'
        '(allow file-write-data (literal "/dev/null"))'
        "(deny network*)"
        "(deny signal)"
    )


def _confine_argv(cmd: str, scratch: Path) -> tuple[list[str], bool]:
    """Return (argv, sandboxed). On macOS wrap in sandbox-exec with a
    deny-write/deny-network/deny-signal profile so execution is contained
    regardless of what the string reassembles to. Where no OS sandbox exists
    the argv is the bare `bash -c` and sandboxed=False (stamped honestly on
    the verdict; NEVER a silent claim of containment)."""
    scratch_real = str(Path(scratch).resolve())
    # The scratch path is our own mkdtemp path (alnum); refuse to build a
    # profile around a path that could break the s-expression quoting.
    if _SANDBOX_EXEC and '"' not in scratch_real and "\n" not in scratch_real:
        return ([_SANDBOX_EXEC, "-p", _sandbox_profile(scratch_real),
                 "bash", "-c", cmd], True)
    return (["bash", "-c", cmd], False)


def run_retest(row: dict, repo_root: Path, timeout_s: float, scratch: Path) -> dict:
    """Screen + execute one row's retest_cmd; returns the verdict record.
    Output text from the probe is DATA — scrubbed of secret shapes, then only
    ever json-encoded. Execution is contained by the OS sandbox on macOS."""
    global _WARNED_NO_SANDBOX
    cmd = row.get("retest_cmd", "")
    base = {
        "id": row.get("id", "?"),
        "ran_at": _now_iso(),
        "cmd_sha256": hashlib.sha256(str(cmd).encode("utf-8")).hexdigest()[:12],
    }
    ok, reason = screen_cmd(cmd)
    if not ok:
        return {**base, "verdict": VERDICT_INCONCLUSIVE, "refused": True,
                "reason": f"screen refused retest_cmd: {reason}"}
    argv, sandboxed = _confine_argv(cmd, scratch)
    if not sandboxed and not _WARNED_NO_SANDBOX:
        print("workaround-retest: WARN no OS execution sandbox on this platform "
              "(sandbox-exec absent) — probes run UNCONFINED; reviewed-registry "
              "trust is the only boundary. Verdicts are stamped sandboxed=false.",
              file=sys.stderr)
        _WARNED_NO_SANDBOX = True
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            cwd=str(repo_root),
            env=_sandbox_env(scratch),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return {**base, "verdict": VERDICT_INCONCLUSIVE, "sandboxed": sandboxed,
                "reason": f"timeout after {timeout_s:.0f}s"}
    except OSError as exc:
        return {**base, "verdict": VERDICT_INCONCLUSIVE, "sandboxed": sandboxed,
                "reason": f"spawn failure: {exc}"}
    duration_ms = int((time.monotonic() - t0) * 1000)
    verdict = (VERDICT_STILL if proc.returncode == 0
               else VERDICT_FIXED if proc.returncode == 1
               else VERDICT_INCONCLUSIVE)
    raw_out, raw_err = proc.stdout or "", proc.stderr or ""
    return {
        **base,
        "verdict": verdict,
        "sandboxed": sandboxed,
        "exit_code": proc.returncode,
        "duration_ms": duration_ms,
        # Tails are journaled — scrub secret shapes a probe may have READ from
        # disk before storing. sha256+len of the RAW output keep integrity
        # provable without exposing content (and are what the ledger carries).
        "stdout_tail": _scrub_secrets(raw_out[-800:]),
        "stderr_tail": _scrub_secrets(raw_err[-400:]),
        "stdout_sha256": hashlib.sha256(raw_out.encode("utf-8")).hexdigest()[:12],
        "stdout_len": len(raw_out),
        "stderr_sha256": hashlib.sha256(raw_err.encode("utf-8")).hexdigest()[:12],
        "stderr_len": len(raw_err),
    }


# --------------------------------------------------------------------------
# Ledgers (append-only JSONL, needs-ledger pattern)
# --------------------------------------------------------------------------

def append_jsonl(path: Path, row: dict) -> bool:
    """One O_APPEND os.write — concurrent filers interleave without a lock.
    Fail-soft: a broken ledger must never block a retest run."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
        fd = os.open(str(path), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        return True
    except OSError as exc:
        print(f"workaround-retest: WARN could not append {path}: {exc}",
              file=sys.stderr)
        return False


def read_jsonl_last_wins(path: Path) -> dict:
    """{id: row} with last-write-wins per id; tolerant of broken lines."""
    out: dict = {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict) and isinstance(row.get("id"), str):
                    out[row["id"]] = row
    except OSError:
        pass
    return out


# --------------------------------------------------------------------------
# Autonomy-graded action seam (Captain law 2026-07-17)
# --------------------------------------------------------------------------
# The retirement DISPOSITION is a function of the posture level, decided by
# framework/authority/action_mode.py — THE law for autonomous-mutation
# modes (doctrine: docs/runbooks/platform-adoption-gating.md, GATE 0/1/3).
# Under guardian/earn_up the seam answers "propose" and this runner files
# exactly the v1 propose-only proposal — byte-identical behavior. A future
# attested sovereign posture may answer "go", but an ACT on that answer
# additionally requires the Captain-PRE-ratified trivial class (GATE 1)
# below, and no applier lives in this runner anyway: consult-the-seam can
# only tighten. Ring-0 components (GATE 3: the claude binary, officer
# model routing) map to Ring-0 categories, so the seam answers propose +
# captain-card for them under EVERY posture, sovereign included.

# Trivial change classes the Captain has PRE-ratified for auto-apply in
# writing (GATE 1). EMPTY until such a recorded decision exists — adding an
# entry REQUIRES citing that decision, and the test suite pins emptiness so
# a silent widening goes red.
_PRERATIFIED_AUTO_CLASSES: frozenset = frozenset()

# Registry components whose retirement touches the Ring-0 plane (GATE 3).
_RING0_COMPONENT_CATEGORY = {
    "claude-code": "claude-binary",
}


def _retire_action(row: dict) -> dict:
    """Action descriptor for retiring this row's workaround. No undo_handle
    on purpose: this runner registers no undo mechanism, so even a future
    act_then_tell posture rung degrades to propose here."""
    component = None
    parsed = parse_version_condition(str(row.get("version_condition", "")))
    if parsed and parsed[0] == "comparator":
        component = parsed[1]
    return {
        "ring": 2,
        "reversibility": "reversible",  # a retirement reverts via the reviewed PR
        "category": _RING0_COMPONENT_CATEGORY.get(component, "workaround-retire"),
    }


def disposition_mode(row: dict, posture: "str | None" = None) -> dict:
    """``{"mode", "captain_card"}`` for this row's retirement disposition,
    via the seam; fail-closed to propose on ANY import/resolve/shape
    failure. ``posture`` is for hermetic tests — production passes None
    (the live posture kernel, which never files needs from this read)."""
    try:
        seam_root = str(_SCRIPT_DIR.parents[1])
        if seam_root not in sys.path:
            sys.path.insert(0, seam_root)
        from framework.authority.action_mode import MODES, action_decision
        decision = action_decision(_retire_action(row), posture)
        mode = decision.mode if decision.mode in MODES else "propose"
        return {"mode": mode, "captain_card": bool(decision.captain_card)}
    except Exception:
        return {"mode": "propose", "captain_card": False}


def proposal_id(workaround_id: str) -> str:
    raw = f"workaround-retire|{workaround_id}|{cabinet_id()}"
    return "WPROP-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]


def file_proposal(row: dict, verdict: dict, proposals_path: Path,
                  delta_ref: str | None,
                  disposition: "dict | None" = None) -> dict:
    """PROPOSE ONLY: append a fingerprint-deduped retirement proposal.
    Re-filing the same fingerprint bumps count/last_seen (last-write-wins
    read semantics) instead of spamming distinct rows."""
    fid = proposal_id(row["id"])
    prior = read_jsonl_last_wins(proposals_path).get(fid)
    now = _now_iso()
    proposal = {
        "id": fid,
        "kind": "workaround-retire",
        "workaround_id": row["id"],
        "title": f"Retire workaround {row['id']} — retest reports fix_confirmed",
        "status": "proposed",
        "propose_only": True,
        # Autonomy-graded action seam stamp (Captain law 2026-07-17): the
        # DISPOSITION the seam allowed at filing time. The row still
        # authorizes NOTHING (propose_only stays True in every mode):
        # acting on a non-propose answer additionally requires the
        # Captain-PRE-ratified trivial class (_PRERATIFIED_AUTO_CLASSES)
        # and rides the staged deploy path — never this runner.
        "action_mode": (disposition or {}).get("mode", "propose"),
        "captain_card": bool((disposition or {}).get("captain_card", False)),
        "count": (int(prior.get("count", 0)) if prior else 0) + 1,
        "first_seen": (prior or {}).get("first_seen") or now,
        "last_seen": now,
        "version_condition": row["version_condition"],
        "owner_surface": row["owner_surface"],
        "delta_ref": delta_ref,
        # Evidence carries NO probe text — only a length + sha256 of the raw
        # output — so a secret a probe printed can never reach this propagated
        # ledger (the scrubbed tails live only in the gitignored verdict
        # journal). `sandboxed` records whether containment was active.
        "evidence": {k: verdict.get(k) for k in
                     ("verdict", "sandboxed", "exit_code", "duration_ms",
                      "ran_at", "cmd_sha256", "stdout_sha256", "stdout_len",
                      "stderr_sha256", "stderr_len")},
    }
    append_jsonl(proposals_path, proposal)
    return proposal


# --------------------------------------------------------------------------
# Delta intake (UNTRUSTED file — json module only, compare-only)
# --------------------------------------------------------------------------

def load_delta_components(path: Path) -> list[dict]:
    """Returns the delta's component entries. Malformed entries are skipped
    (fail-soft per source). Every value is treated as opaque DATA."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"delta unreadable: {path}: {exc}") from exc
    items = doc.get("components") if isinstance(doc, dict) else doc
    if not isinstance(items, list):
        raise ValueError(f"delta has no components list: {path}")
    out = []
    for item in items:
        if (isinstance(item, dict)
                and isinstance(item.get("component"), str)
                and isinstance(item.get("new_version"), str)):
            out.append(item)
    return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="workaround-retest",
        description="Sandboxed retest runner for cabinet/config/workarounds.yml "
                    "(read-only probes; propose-only output).",
    )
    p.add_argument("ids", nargs="*", help="workaround id(s) to retest")
    p.add_argument("--all", action="store_true", help="retest every row")
    p.add_argument("--from-delta", metavar="PATH",
                   help="radar delta JSON; rows whose version_condition matches "
                        "a delta component are queued + retested now (the "
                        "verdict journal is the durable queue record)")
    p.add_argument("--list", action="store_true",
                   help="list ids + version_conditions, run nothing")
    p.add_argument("--registry", metavar="PATH", help="registry override (tests)")
    p.add_argument("--repo-root", metavar="PATH", help="repo root override (tests)")
    p.add_argument("--log", metavar="PATH", help="verdict journal override (tests)")
    p.add_argument("--proposals", metavar="PATH", help="proposals ledger override (tests)")
    p.add_argument("--no-propose", action="store_true",
                   help="emit verdicts only; file no proposals")
    p.add_argument("--timeout", type=float,
                   default=float(os.environ.get("CABINET_RETEST_TIMEOUT", "60")),
                   help="per-probe timeout seconds (default 60)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    repo_root = Path(args.repo_root).resolve() if args.repo_root else (
        Path(os.environ["CABINET_ROOT"]).resolve()
        if os.environ.get("CABINET_ROOT") else _DEFAULT_ROOT)
    registry_path = Path(args.registry) if args.registry else repo_root / REGISTRY_REL
    log_path = Path(args.log) if args.log else repo_root / LOG_REL
    proposals_path = Path(args.proposals) if args.proposals else repo_root / PROPOSALS_REL

    try:
        rows = load_registry(registry_path)
    except ValueError as exc:
        print(f"workaround-retest: registry error: {exc}", file=sys.stderr)
        return 4
    by_id = {row["id"]: row for row in rows}

    if args.list:
        for row in rows:
            print(json.dumps({"id": row["id"],
                              "version_condition": " ".join(row["version_condition"].split())}))
        return 0

    delta_ref: str | None = None
    targets: list[dict]
    if args.from_delta:
        delta_ref = args.from_delta
        try:
            components = load_delta_components(Path(args.from_delta))
        except ValueError as exc:
            print(f"workaround-retest: {exc}", file=sys.stderr)
            return 5
        targets, matched = [], set()
        for row in rows:
            for item in components:
                # DATA-ONLY comparison of untrusted delta strings; the command
                # run below is always the registry's screened retest_cmd.
                if condition_matches_delta(row["version_condition"],
                                           item["component"], item["new_version"]):
                    if row["id"] not in matched:
                        matched.add(row["id"])
                        targets.append(row)
        print(f"workaround-retest: delta matched {len(targets)} row(s) "
              f"from {len(components)} component entrie(s)", file=sys.stderr)
    elif args.all:
        targets = list(rows)
    elif args.ids:
        missing = [i for i in args.ids if i not in by_id]
        if missing:
            print(f"workaround-retest: unknown id(s): {', '.join(missing)}",
                  file=sys.stderr)
            return 4
        targets = [by_id[i] for i in args.ids]
    else:
        print("workaround-retest: nothing to do (give ids, --all, or --from-delta; "
              "see --help)", file=sys.stderr)
        return 2

    any_refused = False
    with tempfile.TemporaryDirectory(prefix="workaround-retest-") as scratch:
        for row in targets:
            verdict = run_retest(row, repo_root, args.timeout, Path(scratch))
            if delta_ref:
                verdict["delta_ref"] = delta_ref
            if verdict.get("refused"):
                any_refused = True
            if (verdict["verdict"] == VERDICT_FIXED) and not args.no_propose:
                disposition = disposition_mode(row)
                verdict["action_mode"] = disposition["mode"]
                verdict["captain_card"] = disposition["captain_card"]
                proposal = file_proposal(row, verdict, proposals_path, delta_ref,
                                         disposition=disposition)
                verdict["proposal_id"] = proposal["id"]
                verdict["proposal_count"] = proposal["count"]
            append_jsonl(log_path, verdict)
            print(json.dumps(verdict, ensure_ascii=False))
    return 3 if any_refused else 0


if __name__ == "__main__":
    sys.exit(main())
