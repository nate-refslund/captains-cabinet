#!/usr/bin/env python3
"""Cabinet Policy Engine — typed YAML policies evaluated in Python.

Replaces the command-matching portion of pre-tool-use.sh section 3-5.
Stateful checks (kill switch, spending limits, Layer 1 gate, CI green gate,
context slug validation, MCP scope) remain in bash.

Reads JSON on stdin: {"tool_name": "...", "tool_input": {...}}
Exits 0 (allow) or 2 (block, reason on stderr).

Uses only stdlib + PyYAML (available in CI).
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Shared authority classifier (the F+A join key) [FIX-1]
# ---------------------------------------------------------------------------
# The policy engine may still be invoked STANDALONE (policy-shadow.py /
# setup-mac.sh) — not only as part of the `framework` package — so the repo
# root is not guaranteed on sys.path. Put it there (honoring CABINET_ROOT where
# the framework lives in deployment, else walking up from this file:
# authority -> framework -> repo root) so the gate and the consequence emitter
# share the ONE canonical classify_action / resolve_lane. No duplicate copy:
# single source of truth. (CG-14 pull-down 2026-07-07: this file moved from
# cabinet/scripts/lib/ into framework/authority/ so the germ layer is
# import-closed — framework callers no longer path-insert upward into cabinet/.)
def _authority_root() -> Path:
    env_root = os.environ.get("CABINET_ROOT")
    if env_root and (Path(env_root) / "framework" / "authority").is_dir():
        return Path(env_root)
    return Path(__file__).resolve().parent.parent.parent


_AUTH_ROOT = _authority_root()
if str(_AUTH_ROOT) not in sys.path:
    sys.path.insert(0, str(_AUTH_ROOT))

try:  # pragma: no cover - exercised via test_authority_join.py
    from framework.authority.classifier import classify_action  # noqa: E402
    from framework.authority.lane import resolve_lane  # noqa: E402
except Exception:  # pragma: no cover - keep the engine importable if absent
    classify_action = None  # type: ignore[assignment]
    resolve_lane = None  # type: ignore[assignment]

# Sovereign-posture kernel [SOV-3] — same fail-safe import contract as the
# classifier above: any absence resolves guardian / no-grants / no-needs
# (never raises, never widens). Tests inject by patching these module globals.
try:  # pragma: no cover - exercised via the posture gate tests
    from framework.authority.posture import resolve_posture as _resolve_posture  # noqa: E402
except Exception:  # pragma: no cover - keep the engine importable if absent
    _resolve_posture = None  # type: ignore[assignment]

try:  # pragma: no cover - exercised via the posture gate tests
    from framework.authority import grants as _grants  # noqa: E402
except Exception:  # pragma: no cover - keep the engine importable if absent
    _grants = None  # type: ignore[assignment]

try:  # pragma: no cover - exercised via the posture gate tests
    from framework.authority import needs as _needs  # noqa: E402
except Exception:  # pragma: no cover - keep the engine importable if absent
    _needs = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Shell command parsing — the core innovation replacing ~700 lines of regex
# ---------------------------------------------------------------------------

# Shell control-flow keywords — not binaries, skip and continue to the next token.
SHELL_CONTROL_KEYWORDS = frozenset({
    "if", "then", "else", "elif", "fi",
    "while", "until", "do", "done",
    "for", "in", "select",
    "case", "esac",
    "function", "!",
})

# Wrapper binaries that execute their arguments (not introspection).
# When encountered as the command word, we recurse into their arguments.
EXEC_WRAPPERS = frozenset({
    "eval", "exec", "nohup", "time", "nice", "ionice", "chrt",
    "taskset", "unbuffer", "cgexec", "doas", "pkexec", "gosu",
    "su-exec", "strace", "ltrace", "gdb", "valgrind", "watch",
    "chroot", "timeout", "numactl", "setsid", "stdbuf", "coproc",
    "trap",
})

# env is special: it takes VAR=VAL assignments and flags before the command.
ENV_BINARIES = frozenset({"env"})

# Shell binaries that take -c <code> to execute a string.
SHELL_BINARIES = frozenset({
    "bash", "sh", "dash", "zsh", "ksh", "mksh", "ash",
    "fish", "csh", "tcsh", "busybox", "su", "runuser", "script",
})

# command -p executes; command -v/-V is introspection (not blocked).
COMMAND_BINARY = "command"

# Characters that separate shell statements.
_STATEMENT_SEPS = re.compile(r"(?:&&|\|\||[;|&])")


def _strip_path(binary: str) -> str:
    """Strip leading path: /usr/bin/sudo -> sudo."""
    return binary.rsplit("/", 1)[-1] if "/" in binary else binary


def _strip_quotes_and_escapes(token: str) -> str:
    """Remove surrounding/embedded quotes and leading backslashes.

    Handles: "sudo", 'sudo', s"udo", \\sudo, "su""do".
    Bash fuses adjacent quoted/unquoted segments into one word at exec time.
    """
    result = []
    i = 0
    while i < len(token):
        ch = token[i]
        if ch == "\\" and i + 1 < len(token):
            # Backslash-escaped char: emit the next char literally.
            result.append(token[i + 1])
            i += 2
        elif ch in ("'", '"'):
            # Walk to matching close quote; emit interior.
            close = ch
            i += 1
            while i < len(token) and token[i] != close:
                result.append(token[i])
                i += 1
            if i < len(token):
                i += 1  # skip closing quote
        elif ch == "$" and i + 1 < len(token) and token[i + 1] == "'":
            # ANSI-C quoting $'...'
            i += 2
            while i < len(token) and token[i] != "'":
                if token[i] == "\\" and i + 1 < len(token):
                    result.append(token[i + 1])
                    i += 2
                else:
                    result.append(token[i])
                    i += 1
            if i < len(token):
                i += 1
        else:
            result.append(ch)
            i += 1
    return "".join(result)


def _split_on_statement_seps(command: str) -> list[str]:
    """Split a command string on ;, &&, ||, | respecting quoting.

    Returns a list of statement strings. Handles single quotes, double
    quotes, $'...' ANSI-C quotes, and backslash escapes.
    """
    statements: list[str] = []
    current: list[str] = []
    i = 0
    n = len(command)

    while i < n:
        ch = command[i]
        # Quoting: skip through quoted spans
        if ch == "'":
            j = command.find("'", i + 1)
            if j == -1:
                current.append(command[i:])
                i = n
            else:
                current.append(command[i : j + 1])
                i = j + 1
        elif ch == '"':
            j = i + 1
            while j < n:
                if command[j] == "\\" and j + 1 < n:
                    j += 2
                elif command[j] == '"':
                    break
                else:
                    j += 1
            current.append(command[i : j + 1])
            i = j + 1
        elif ch == "$" and i + 1 < n and command[i + 1] == "'":
            j = command.find("'", i + 2)
            if j == -1:
                current.append(command[i:])
                i = n
            else:
                current.append(command[i : j + 1])
                i = j + 1
        elif ch == "\\" and i + 1 < n:
            current.append(command[i : i + 2])
            i += 2
        # Statement separators
        elif ch == ";" or ch == "|" or ch == "&":
            # Check for && or ||
            if ch == "&" and i + 1 < n and command[i + 1] == "&":
                statements.append("".join(current))
                current = []
                i += 2
            elif ch == "|" and i + 1 < n and command[i + 1] == "|":
                statements.append("".join(current))
                current = []
                i += 2
            elif ch == "|":
                statements.append("".join(current))
                current = []
                i += 1
            elif ch == ";":
                statements.append("".join(current))
                current = []
                i += 1
            elif ch == "&":
                # Background operator
                statements.append("".join(current))
                current = []
                i += 1
            else:
                current.append(ch)
                i += 1
        # Subshell/brace group boundaries
        elif ch in ("(", ")", "{", "}"):
            statements.append("".join(current))
            current = []
            i += 1
        # Backtick command substitution
        elif ch == "`":
            j = command.find("`", i + 1)
            if j == -1:
                current.append(command[i:])
                i = n
            else:
                # Treat content of backticks as a separate statement
                statements.append("".join(current))
                current = []
                statements.append(command[i + 1 : j])
                i = j + 1
        # $() command substitution
        elif ch == "$" and i + 1 < n and command[i + 1] == "(":
            # Find matching close paren (simple nesting)
            depth = 1
            j = i + 2
            while j < n and depth > 0:
                if command[j] == "(":
                    depth += 1
                elif command[j] == ")":
                    depth -= 1
                elif command[j] == "\\" and j + 1 < n:
                    j += 1
                elif command[j] == "'":
                    k = command.find("'", j + 1)
                    if k != -1:
                        j = k
                elif command[j] == '"':
                    k = j + 1
                    while k < n:
                        if command[k] == "\\" and k + 1 < n:
                            k += 2
                        elif command[k] == '"':
                            break
                        else:
                            k += 1
                    j = k
                j += 1
            # Treat the substitution body as a separate statement to scan
            statements.append("".join(current))
            current = []
            statements.append(command[i + 2 : j - 1] if j > i + 2 else "")
            i = j
        # Heredoc detection: << WORD ... WORD
        elif ch == "<" and i + 1 < n and command[i + 1] == "<":
            # Detect heredoc: <<[-]WORD or <<[-]'WORD' or <<[-]"WORD"
            hd_start = i + 2
            # Skip optional dash for <<-
            if hd_start < n and command[hd_start] == "-":
                hd_start += 1
            # Skip optional space
            while hd_start < n and command[hd_start] == " ":
                hd_start += 1
            # Here-string <<<
            if i + 2 < n and command[i + 2] == "<":
                # Here-string: <<< 'content' or <<< content
                # The content after <<< should be scanned as a statement.
                hs_start = i + 3
                while hs_start < n and command[hs_start] in (" ", "\t"):
                    hs_start += 1
                # Extract the here-string value
                if hs_start < n and command[hs_start] in ("'", '"'):
                    quote = command[hs_start]
                    end = command.find(quote, hs_start + 1)
                    if end == -1:
                        hs_body = command[hs_start + 1 :]
                        i = n
                    else:
                        hs_body = command[hs_start + 1 : end]
                        i = end + 1
                else:
                    # Unquoted — goes to next whitespace or end
                    end = hs_start
                    while end < n and command[end] not in (" ", "\t", "\n", ";", "&", "|"):
                        end += 1
                    hs_body = command[hs_start:end]
                    i = end
                current.append(command[i - len(hs_body) - (3 if hs_start == i - len(hs_body) else 0): i])
                # Add the here-string body as a separate statement to scan
                statements.append(hs_body)
                continue
            # Proper heredoc
            if hd_start < n:
                # Get delimiter word (strip quotes if present)
                delim_start = hd_start
                if command[hd_start] in ("'", '"'):
                    delim_end = command.find(command[hd_start], hd_start + 1)
                    if delim_end == -1:
                        delim_end = n
                    delim = command[hd_start + 1 : delim_end]
                    hd_start = delim_end + 1
                else:
                    delim_end = hd_start
                    while delim_end < n and command[delim_end] not in (" ", "\t", "\n"):
                        delim_end += 1
                    delim = command[hd_start:delim_end]
                    hd_start = delim_end
                # Find the heredoc body between newlines
                body_start = command.find("\n", hd_start)
                if body_start != -1 and delim:
                    body_end = command.find("\n" + delim, body_start + 1)
                    if body_end == -1:
                        # Try end-of-string
                        if command.rstrip().endswith(delim):
                            body_end = command.rstrip().rfind(delim)
                            heredoc_body = command[body_start + 1 : body_end]
                        else:
                            heredoc_body = command[body_start + 1 :]
                    else:
                        heredoc_body = command[body_start + 1 : body_end]
                    statements.append("".join(current))
                    current = []
                    statements.append(heredoc_body)
                    # Skip past the end delimiter
                    if body_end != -1:
                        i = body_end + 1 + len(delim)
                    else:
                        i = n
                    continue
            current.append(command[i : i + 2])
            i += 2
        else:
            current.append(ch)
            i += 1

    if current:
        statements.append("".join(current))

    return [s.strip() for s in statements if s.strip()]


def _tokenize_simple(statement: str) -> list[str]:
    """Tokenize a single shell statement into words.

    Uses shlex where possible, with fallback for edge cases.
    Brace expansion is handled earlier in _expand_braces_in_command.
    """
    try:
        tokens = shlex.split(statement, posix=True)
    except ValueError:
        # Malformed quoting — fall back to whitespace split with manual
        # quote stripping.
        tokens = statement.split()
        tokens = [_strip_quotes_and_escapes(t) for t in tokens]

    return tokens


def _extract_from_statement(tokens: list[str]) -> list[str]:
    """Given tokenized words of a single statement, extract invoked binaries.

    Recursively handles wrappers, env prefixes, shell -c, etc.
    Returns a list of leaf-level binary names (path-stripped).
    """
    if not tokens:
        return []

    binaries: list[str] = []
    i = 0

    # Skip leading VAR=VAL assignments (POSIX inline env)
    while i < len(tokens) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[i]):
        i += 1

    if i >= len(tokens):
        return []

    # Skip shell negation operator
    if tokens[i] == "!":
        i += 1
        if i >= len(tokens):
            return []

    cmd_word_raw = tokens[i]
    cmd_word = _strip_path(_strip_quotes_and_escapes(cmd_word_raw))

    # Shell control-flow keywords: skip and continue to next token
    if cmd_word in SHELL_CONTROL_KEYWORDS:
        return _extract_from_statement(tokens[i + 1:])

    # Handle 'command' specially: -v/-V is introspection, -p executes
    if cmd_word == COMMAND_BINARY:
        i += 1
        # Skip flags
        while i < len(tokens) and tokens[i].startswith("-"):
            flag = tokens[i]
            if "-v" in flag or "-V" in flag:
                # Introspection — not execution
                return []
            i += 1
            # Skip -- end-of-options marker
            if flag == "--":
                break
        # Recurse on remaining tokens
        return _extract_from_statement(tokens[i:])

    # env binary: skip flags and VAR=VAL, recurse into the command
    if cmd_word in ENV_BINARIES:
        i += 1
        while i < len(tokens):
            tok = tokens[i]
            if tok.startswith("-"):
                # env flag: -u VAR, -C DIR, -S STR, etc.
                # -S is special: its argument is a command string
                if tok == "-S" or tok.startswith("-S"):
                    if tok == "-S" and i + 1 < len(tokens):
                        # Next token is the command string
                        return extract_invoked_binaries(tokens[i + 1])
                    elif tok.startswith("-S") and len(tok) > 2:
                        # Fused: -S'cmd' or -Scmd
                        return extract_invoked_binaries(tok[2:])
                    i += 1
                    continue
                # Other flags may take an argument
                i += 1
                # If next token doesn't start with - and isn't VAR=VAL,
                # it could be a flag argument
                if i < len(tokens) and not tokens[i].startswith("-") and "=" not in tokens[i]:
                    i += 1
                continue
            elif re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tok):
                # VAR=VAL
                i += 1
                continue
            else:
                # This is the command to execute
                break
        return _extract_from_statement(tokens[i:])

    # Shell binary with -c: the next argument is a command string
    # Long flags that take a value argument (--rcfile FILE, --init-file FILE, etc.)
    _SHELL_LONG_FLAGS_WITH_VALUE = frozenset({
        "--rcfile", "--init-file",
    })
    if cmd_word in SHELL_BINARIES:
        i += 1
        has_c = False
        while i < len(tokens):
            tok = tokens[i]
            if tok == "--":
                i += 1
                break
            elif tok.startswith("--"):
                # Long flag
                if "=" in tok:
                    # --flag=value — self-contained
                    i += 1
                elif tok in _SHELL_LONG_FLAGS_WITH_VALUE:
                    # --rcfile FILE — consume the value too
                    i += 2
                else:
                    # --norc, --noprofile, etc. — no value
                    i += 1
                continue
            elif tok.startswith("-") and "c" in tok:
                # Found -c (or -xc, -lc, etc.)
                has_c = True
                i += 1
                break
            elif tok.startswith("-"):
                # Short flags without c: -x, -l, etc.
                i += 1
                continue
            else:
                break
        if has_c and i < len(tokens):
            # The argument after -c is a command string — recurse
            return extract_invoked_binaries(tokens[i])
        # Shell without -c but with <<< (here-string) — already handled
        # by _split_on_statement_seps which extracts heredoc/here-string bodies.
        # Shell without -c running a script file — the file is the "binary"
        return []

    # Exec wrappers: skip flags, recurse into remaining args
    if cmd_word in EXEC_WRAPPERS:
        i += 1
        # For eval, everything after is the command to execute
        if cmd_word == "eval":
            if i < len(tokens):
                # Join remaining tokens and recurse — eval concatenates args
                return extract_invoked_binaries(" ".join(tokens[i:]))
            return []
        # For trap, the first non-flag arg is the command string
        if cmd_word == "trap":
            while i < len(tokens) and tokens[i].startswith("-"):
                i += 1
            if i < len(tokens):
                return extract_invoked_binaries(tokens[i])
            return []
        # For coproc, next token might be a name (identifier)
        if cmd_word == "coproc":
            if i < len(tokens) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", tokens[i]):
                i += 1  # skip coproc name
        # Generic wrapper: skip flags and their arguments, then positional
        # args that belong to the wrapper (not the target command).
        #
        # Wrappers that take mandatory positional args before the target cmd:
        #   timeout [flags] DURATION CMD...
        #   chroot [flags] NEWROOT CMD...
        #   nice [flags] CMD...  (but -n takes a value)
        #   chrt [flags] PRIORITY CMD...
        #   taskset [flags] MASK CMD...
        #   numactl [flags] CMD...
        #   stdbuf [flags] CMD...  (flags like -oL are self-contained)
        #   ionice [flags] CMD...  (flags like -c CLASS are self-contained)
        #
        # Strategy: consume all -flags (and their values), then consume
        # wrapper-specific positional args, then the remaining tokens are
        # the target command.

        # Phase 1: consume all flags
        while i < len(tokens) and tokens[i].startswith("-"):
            flag = tokens[i]
            i += 1
            if flag == "--":
                break
            # Long flags with = are self-contained
            if flag.startswith("--") and "=" in flag:
                continue
            # Flags that take a separate value argument
            # For most wrappers, a flag followed by a non-flag token means
            # the next token is the flag's value (e.g. -n 10, -c 3)
            if i < len(tokens) and not tokens[i].startswith("-"):
                # These flag prefixes are known to take values
                if cmd_word in ("nice",) and flag in ("-n", "--adjustment"):
                    i += 1
                elif cmd_word in ("ionice",) and flag in ("-c", "-n", "--class", "--classdata"):
                    i += 1
                elif cmd_word in ("chrt",) and flag in ("-p", "--pid"):
                    i += 1
                elif cmd_word in ("timeout",) and flag in ("-k", "--kill-after", "-s", "--signal"):
                    i += 1
                elif cmd_word in ("stdbuf",) and flag in ("-i", "-o", "-e"):
                    i += 1
                elif cmd_word in ("cgexec",) and flag in ("-g", "--sticky"):
                    i += 1
                elif cmd_word in ("numactl",) and flag in ("--physcpubind", "--cpunodebind",
                                                            "--membind", "--interleave",
                                                            "--preferred"):
                    i += 1
                elif flag.startswith("--") and not flag.startswith("--no"):
                    # Generic long flag likely takes a value
                    i += 1

        # Phase 2: consume wrapper-specific positional args
        if cmd_word == "timeout":
            # timeout DURATION CMD... — skip the duration token
            if i < len(tokens) and re.match(r"^[0-9]", tokens[i]):
                i += 1
        elif cmd_word == "chroot":
            # chroot NEWROOT CMD... — skip the root path
            if i < len(tokens):
                i += 1
        elif cmd_word in ("chrt", "taskset"):
            # chrt PRIORITY CMD... / taskset MASK CMD...
            if i < len(tokens) and re.match(r"^[0-9]", tokens[i]):
                i += 1

        return _extract_from_statement(tokens[i:])

    # Leaf-level binary
    binaries.append(cmd_word)
    return binaries


def _expand_braces_in_command(command: str) -> str:
    """Expand shell brace expressions in command text before parsing.

    Handles: {,sudo} -> sudo, {sudo,} -> sudo, {,{,sudo}} -> sudo,
    {,sudo,} -> sudo. Only expands braces that contain commas (shell
    brace expansion syntax). Non-comma braces like { cmd; } are left alone.
    """
    result = command
    # Iteratively expand from innermost braces outward
    for _ in range(10):  # max nesting depth
        # Find innermost brace pair containing a comma
        match = re.search(r"\{([^{}]*,[^{}]*)\}", result)
        if not match:
            break
        inner = match.group(1)
        parts = [p for p in inner.split(",") if p]
        if parts:
            # Replace with space-separated alternatives (each becomes
            # a potential command word). The suffix after } stays attached.
            replacement = " ".join(parts)
        else:
            replacement = ""
        result = result[:match.start()] + replacement + result[match.end():]
    return result


def extract_invoked_binaries(command: str) -> list[str]:
    """Parse a shell command and return all binaries that would be invoked.

    Handles: eval wrapping, bash -c, env prefix, nohup/exec/time wrappers,
    full path invocation (/usr/bin/sudo), brace expansion ({,sudo}),
    quote splicing ("su""do"), heredoc bodies, semicolons/pipes/&&,
    here-strings (<<<), backslash escapes, and nested combinations.
    """
    if not command or not command.strip():
        return []

    # Pre-process: expand brace expressions BEFORE splitting on statement
    # separators, because { and } are also statement boundary characters.
    # Brace expansion like {,sudo} or {sudo,} must be expanded first.
    preprocessed = _expand_braces_in_command(command)

    statements = _split_on_statement_seps(preprocessed)
    all_binaries: list[str] = []

    for stmt in statements:
        tokens = _tokenize_simple(stmt)
        binaries = _extract_from_statement(tokens)
        all_binaries.extend(binaries)

    return all_binaries


# ---------------------------------------------------------------------------
# Destructive rm detection
# ---------------------------------------------------------------------------

def is_destructive_rm(command: str) -> bool:
    """Check if command invokes rm with recursive flag targeting root.

    Catches: rm -rf /, rm -fr /, rm -f -r /, rm --recursive --force /,
    rm -rf /*, and all flag-order variants. Does NOT flag rm file.txt
    or rm -rf /tmp/build (non-root paths).
    """
    statements = _split_on_statement_seps(command)

    for stmt in statements:
        tokens = _tokenize_simple(stmt)
        # Walk through to find rm invocations (including via wrappers)
        _binaries = _extract_from_statement(tokens)
        if not any(b == "rm" for b in _binaries):
            continue

        # Now find the rm token and parse its args
        if _check_rm_in_tokens(tokens):
            return True

    return False


def _check_rm_in_tokens(tokens: list[str]) -> bool:
    """Check if a token list contains a destructive rm invocation."""
    rm_idx = -1
    for i, tok in enumerate(tokens):
        cleaned = _strip_path(_strip_quotes_and_escapes(tok))
        if cleaned == "rm":
            rm_idx = i
            break
        # Skip wrapper tokens — they lead to rm eventually
        if cleaned in EXEC_WRAPPERS | ENV_BINARIES | SHELL_BINARIES | {COMMAND_BINARY}:
            continue

    if rm_idx < 0:
        return False

    # Parse flags and args after rm
    has_recursive = False
    targets: list[str] = []

    for tok in tokens[rm_idx + 1 :]:
        cleaned = _strip_quotes_and_escapes(tok)
        if cleaned.startswith("--"):
            if cleaned == "--recursive":
                has_recursive = True
            elif cleaned == "--":
                continue
        elif cleaned.startswith("-") and not cleaned.startswith("--"):
            # Short flags: check for r or R
            flag_chars = cleaned[1:]
            if "r" in flag_chars or "R" in flag_chars:
                has_recursive = True
        else:
            targets.append(cleaned)

    if not has_recursive:
        return False

    # Check if any target is root
    for target in targets:
        stripped = target.rstrip("*").rstrip("/")
        if stripped == "" or target == "/":
            # Targeting / or /*
            return True

    return False


# ---------------------------------------------------------------------------
# Bash write-to-path detection
# ---------------------------------------------------------------------------

# Patterns that indicate a bash command writes to a path
_WRITE_PATTERNS = [
    # Pattern 1: redirect stdout/stderr to path (>, >>, >|)
    r">{1,2}\|?\s*[\"']?{path}",
    # Pattern 2: sed -i (inplace edit) with path as file arg
    # Single-dash -i (with optional suffix like .bak): -i, -i.bak, -Ei, -ni
    # Long form --in-place only. Excludes --posix, --regexp-extended etc.
    r"sed\b(?:[^;&|]|'[^']*'|\"[^\"]*\")*(?:(?<![-])-[a-zA-Z]*i(?:\.[^\s]*)?(?:\s|$)|--in-place(?:=[^\s]*)?)(?:[^;&|]|'[^']*'|\"[^\"]*\")*\s[\"']?{path}",
    # Pattern 3: tee writing to path (exclude input redirects: < before path)
    r"tee\b[^;&|]*(?<!<)\s[\"']?{path}",
    # Pattern 4: cp/mv/rsync with path as last arg (destination)
    r"(?:cp|mv|rsync)\b[^;&|]*\s[\"']?{path}[^\s;&|\"']*[\"']?\s*(?:$|[;&|<>])",
    # Pattern 5a: cp/mv with -t flag (target directory)
    r"(?:cp|mv)\b[^;&|]*-[a-zA-Z]*t\s*[\"']?{path}",
    # Pattern 5b: cp/mv/rsync with --target-directory
    r"(?:cp|mv|rsync)\b[^;&|]*--target-directory[=\s]+[\"']?{path}",
    # Pattern 6: patch with path as file arg (exclude input redirects)
    r"patch\b[^;&|]*(?<!<)\s[\"']?{path}",
    # Pattern 7: perl -i (inplace edit) with path
    r"perl\b[^;&|]*(?:-[^\sIi]*i[^\s]*|--in-place(?:=[^\s]*)?)[^;&|]*\s*[\"']?{path}",
    # Pattern 8: tar extract/create to path via -C or --directory
    # Handles: -C /path, -C/path (no space), -xC /path (bundled), --directory=/path,
    # --directory /path, --dir=/path (abbreviated)
    r"tar\b[^;&|]*(?:-[a-zA-Z]*C[=\s]*|--dir(?:ectory)?[=\s]+)[\"']?{path}",
    # Pattern 8b: tar -fC bundled — -f takes archive arg, -C takes dir arg
    # Handles: -fC archive dir, -xfC archive dir, -fxC archive dir
    r"tar\b[^;&|]*-[a-zA-Z]*f[a-zA-Z]*C\s+\S+\s+[\"']?{path}",
    # Pattern 9: tar with -f/--file writing archive to path
    # Handles: -f /path, -cf /path (bundled), --file=/path, --file /path
    r"tar\b[^;&|]*(?:-[a-zA-Z]*f[=\s]*|--file[=\s]+)[\"']?{path}",
]


def check_bash_write_to_path(command: str, path_pattern: str) -> bool:
    """Check if a Bash command writes to a path matching the pattern.

    Detects: redirect (> >>), sed -i, tee, cp/mv/rsync dest, patch,
    perl -i, tar extract/create.
    """
    for pattern_template in _WRITE_PATTERNS:
        pattern = pattern_template.replace("{path}", path_pattern)
        if re.search(pattern, command):
            return True
    # Relaxed match: try without trailing slash for tar -C/-f patterns
    # where the path may not have a trailing slash (e.g., tar -C /workspace/slug)
    # Only apply to tar patterns to avoid false positives on quoted paths
    # with spaces (e.g., echo x > "/workspace/foo bar/README.md")
    relaxed = path_pattern.rstrip("/")
    if relaxed != path_pattern:
        relaxed_pat = relaxed + r"(?:/|\s|[\"';&|<>)]|$)"
        for pattern_template in _WRITE_PATTERNS:
            if "tar" not in pattern_template:
                continue
            pattern = pattern_template.replace("{path}", relaxed_pat)
            if re.search(pattern, command):
                return True
    return False


# ---------------------------------------------------------------------------
# Path matching helpers
# ---------------------------------------------------------------------------

def _path_matches_pattern(file_path: str, pattern: str) -> bool:
    """Check if a file path matches a glob-style pattern.

    Supports: *.env, *.env.*, */constitution/*, /workspace/*/
    """
    # Normalize: ensure no double slashes
    file_path = file_path.replace("//", "/")
    pattern = pattern.replace("//", "/")

    # For patterns like /workspace/*/ — match paths that start with
    # /workspace/<something>/
    if pattern.endswith("/"):
        # Directory prefix pattern — check if the path is under this directory
        dir_pattern = pattern.rstrip("/")
        if fnmatch.fnmatch(file_path, dir_pattern + "/*"):
            return True
        if fnmatch.fnmatch(file_path, dir_pattern):
            return True

    # Standard fnmatch
    if fnmatch.fnmatch(file_path, pattern):
        return True

    # Also check just the basename for extension patterns
    basename = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path
    if fnmatch.fnmatch(basename, pattern):
        return True

    # Root-relative path vs a leading-`*/` directory pattern (parity fix).
    # `*/constitution/*` requires a dir segment before `constitution/`, so it
    # matches the ABSOLUTE form but not the root-relative `constitution/X`.
    # pre-tool-use.sh + the regex shadow both match the relative form, so the
    # typed engine was strictly narrower on a covered rule. Retry with a
    # synthetic leading `/` so the relative path matches as its absolute form
    # would. Purely ADDITIVE (only adds matches); `docs/constitution-guide.md`
    # still fails.
    if "/" in pattern and not file_path.startswith("/"):
        if _path_matches_pattern("/" + file_path, pattern):
            return True

    return False


# ---------------------------------------------------------------------------
# Policy evaluation
# ---------------------------------------------------------------------------

def evaluate_policy(
    policy: dict[str, Any],
    tool_name: str,
    tool_input: dict[str, Any],
    officer: str,
) -> str | None:
    """Evaluate a single policy against a tool invocation.

    Returns the block message if the policy triggers, or None to allow.
    """
    ptype = policy["type"]

    # Check officer exemptions
    exempt = policy.get("exempt_officers", [])
    if officer in exempt:
        return None

    if ptype == "binary_block":
        return _eval_binary_block(policy, tool_name, tool_input)
    elif ptype == "destructive_rm":
        return _eval_destructive_rm(policy, tool_name, tool_input)
    elif ptype == "command_contains":
        return _eval_command_contains(policy, tool_name, tool_input, officer)
    elif ptype == "path_block":
        return _eval_path_block(policy, tool_name, tool_input)
    elif ptype == "bash_write_to_path":
        return _eval_bash_write_to_path(policy, tool_name, tool_input)
    elif ptype == "tier2_isolation":
        return _eval_tier2_isolation(policy, tool_name, tool_input, officer)
    elif ptype == "authority_matrix":
        return _eval_authority_matrix(policy, tool_name, tool_input, officer)
    else:
        return None


def _eval_binary_block(
    policy: dict, tool_name: str, tool_input: dict
) -> str | None:
    blocked_binaries = set(policy.get("binaries", []))
    if tool_name != "Bash":
        return None
    command = tool_input.get("command", "")
    if not command:
        return None
    invoked = extract_invoked_binaries(command)
    for binary in invoked:
        if binary in blocked_binaries:
            return f"BLOCKED: {policy['message']}"
    return None


def _eval_destructive_rm(
    policy: dict, tool_name: str, tool_input: dict
) -> str | None:
    if tool_name != "Bash":
        return None
    command = tool_input.get("command", "")
    if not command:
        return None
    if is_destructive_rm(command):
        return f"BLOCKED: {policy['message']}"
    expanded = _expand_braces_in_command(command)
    if expanded != command and is_destructive_rm(expanded):
        return f"BLOCKED: {policy['message']}"
    return None


def _eval_command_contains(
    policy: dict, tool_name: str, tool_input: dict, officer: str
) -> str | None:
    # Check tool restriction
    if policy.get("tool") and tool_name != policy["tool"]:
        return None
    if tool_name != "Bash":
        return None

    command = tool_input.get("command", "")
    if not command:
        return None

    case_sensitive = policy.get("case_sensitive", True)
    check_cmd = command if case_sensitive else command.upper()

    # patterns: any match triggers
    patterns = policy.get("patterns", [])
    for pattern in patterns:
        check_pattern = pattern if case_sensitive else pattern.upper()
        if check_pattern in check_cmd:
            return f"BLOCKED: {policy['message']}"

    # patterns_all: ALL must match (each item can contain | for OR within)
    patterns_all = policy.get("patterns_all", [])
    if patterns_all:
        all_match = True
        for pattern_group in patterns_all:
            alternatives = pattern_group.split("|")
            group_match = False
            for alt in alternatives:
                check_alt = alt if case_sensitive else alt.upper()
                if check_alt in check_cmd:
                    group_match = True
                    break
            if not group_match:
                all_match = False
                break
        if all_match:
            return f"BLOCKED: {policy['message']}"

    return None


def _extract_file_path(tool_input: dict) -> str:
    """Extract file path from tool input, checking common field names."""
    return tool_input.get("file_path") or tool_input.get("path") or ""


def _eval_path_block(
    policy: dict, tool_name: str, tool_input: dict
) -> str | None:
    tools = policy.get("tools", [])
    if tool_name not in tools:
        return None

    file_path = _extract_file_path(tool_input)
    if not file_path:
        return None

    path_patterns = policy.get("path_patterns", [])
    for pattern in path_patterns:
        if _path_matches_pattern(file_path, pattern):
            return f"BLOCKED: {policy['message']}"
    return None


def _eval_bash_write_to_path(
    policy: dict, tool_name: str, tool_input: dict
) -> str | None:
    if tool_name != "Bash":
        return None
    command = tool_input.get("command", "")
    if not command:
        return None
    path_pattern = policy.get("path_pattern", "")
    if not path_pattern:
        return None
    if check_bash_write_to_path(command, path_pattern):
        return f"BLOCKED: {policy['message']}"
    return None


def _eval_tier2_isolation(
    policy: dict, tool_name: str, tool_input: dict, officer: str
) -> str | None:
    tools = policy.get("tools", [])
    if tool_name not in tools:
        return None

    file_path = _extract_file_path(tool_input)
    if not file_path:
        return None

    base_path = policy.get("base_path", "")
    if not base_path:
        return None

    # Check if the file is under the tier2 base path
    if base_path not in file_path:
        return None

    # It is under tier2 — check if it's the officer's own directory
    expected_subpath = f"{base_path}{officer}/"
    if expected_subpath not in file_path:
        return f"BLOCKED: {policy['message']} ({base_path}{officer}/)"
    return None


# ---------------------------------------------------------------------------
# Authority matrix policy type [T6] — fail-safe, shadow-capable
# ---------------------------------------------------------------------------
# Turns the matrix DATA (framework/policies/authority-matrix.yml, validated by
# framework/authority/matrix.py) into a per-action verdict and returns a block
# message (force propose-only / gated) or None (allow). Design:
# docs/authority-matrix-design-2026-06-19.md §1 Component 2 + §3.
#
# THE FAIL-SAFE SPINE (Corridor-confirmed; the design's error-handling
# inventory):
#   * HARD CEILING short-circuit — the hard_ceiling risk_classes
#     (external_comms, deploy_prod, spend, secrets, network_write,
#     credentials_grant) are ALWAYS gated, ignoring confidence entirely.
#     A SOVEREIGN posture ceiling row may narrow that to the CONDITIONAL
#     standing_grant (grant-or-need, D2) — never to unconditional auto.
#   * Unknown / unmeasured / ambiguous -> propose_only. An unknown action_type
#     (classify_action -> AMBIGUOUS, or anything not mapped) has no risk_class
#     and proposes. A missing/absent cell verdict resolves to propose_only.
#   * read_cell_state reads F2 graduation.evaluate LIVE (un-stubbed
#     2026-07-03), fail-safe-wrapped: absence/exception/unknown-state ->
#     "unmeasured" -> propose_only. Autonomy lights up cell-by-cell as cells
#     earn graduated state — and the verdict is still SHADOW-consumed until
#     the Captain-gated enforcement flip.
#   * Defensive .get() throughout — a malformed/empty policy dict proposes,
#     never auto. No exception escapes to the caller.
#
# SHADOW-ONLY: this eval is a pure decision function. T6 wires it into
# evaluate_policy()'s dispatch but adds NO new live exit-2 to pre-tool-use.sh —
# the verdict is consumed in shadow (policy-shadow.py, a later task) until the
# Captain-gated CABINET_AUTHORITY_ENFORCING flip. main()'s live loop enforces
# only the LEGACY typed rules; authority_matrix policies are not part of the
# framework floor that main() blocks on.

def risk_of(action_type: str, risk_classes: Any) -> str | None:
    """Map an `action_type` enum string to its `risk_class`, or None.

    None means "no risk_class" — an unknown / ambiguous / unmapped action
    type. The caller treats None as fail-safe propose_only. Defensive: a
    malformed `risk_classes` structure yields None, never raises.
    """
    if not isinstance(risk_classes, dict):
        return None
    for rc_name, rc in risk_classes.items():
        if not isinstance(rc, dict):
            continue
        ats = rc.get("action_types")
        if isinstance(ats, list) and action_type in ats:
            return rc_name
    return None


# Posture vocabulary [SOV-3; earn_up joined in the axes build, spec
# 2026-07-05 §1]. Local mirror of matrix.POSTURES so the engine stays
# standalone-importable: only these non-default postures may select a
# `postures.*` table; guardian IS the root table and anything unknown or
# malformed falls back to it (fail toward guardian, never widen). earn_up's
# table only NARROWS vs the root (machine-checked by matrix.py), so selecting
# it needs no attestation.
_GUARDIAN = "guardian"
_EARN_UP = "earn_up"
_POSTURE_TABLES = frozenset({"sovereign", _EARN_UP})


def resolve_verdict(
    verdicts: Any,
    risk_class: str,
    state: str,
    *,
    posture: str | None = None,
    postures: Any = None,
) -> str:
    """Resolve a (risk_class, confidence_state) cell to a verdict string.

    Supports the "*" wildcard row (hard-ceiling rows ship as {"*": ...}).
    FAIL-SAFE: any absent risk_class, absent state (with no wildcard), or
    malformed table resolves to "propose_only" — never auto.

    Posture axis [SOV-3, keyword-only — positional callers untouched]: when
    `posture` names a known non-default posture AND `postures` carries a
    well-formed FULL table for it (the floor's `postures.<name>.verdicts`),
    that table answers instead of the root one. `posture=None`/"guardian"/
    unknown, or a malformed `postures` structure, resolves from the root
    table — guardian byte-identical.
    """
    if posture in _POSTURE_TABLES and isinstance(postures, dict):
        entry = postures.get(posture)
        if isinstance(entry, dict) and isinstance(entry.get("verdicts"), dict):
            verdicts = entry["verdicts"]
    if not isinstance(verdicts, dict):
        return "propose_only"
    row = verdicts.get(risk_class)
    if not isinstance(row, dict):
        return "propose_only"
    if state in row:
        return row[state]
    if "*" in row:
        return row["*"]
    return "propose_only"


_CELL_STATES = {"unmeasured", "propose_only", "eligible", "graduated", "demote"}


def read_cell_state(officer: str, lane: str | None, action_type: str) -> str:
    """Read the per-cell graduation state from F2 (`framework.fidelity.graduation`).

    UN-STUBBED 2026-07-03 (CRIT-3): the A0 stub hardcoded "unmeasured", so the
    measure→gate wire was severed and `auto` was unreachable by construction.
    Now the live graduation engine answers — still SHADOW-consumed only (the
    verdict reaches enforcement solely behind the CABINET_AUTHORITY_ENFORCING
    flip + parity gate, unchanged by this change).

    FAIL-CLOSED wrapper. Two distinct failure directions, resolved differently
    since the 2026-07-05 act-first widening (MF-1, checkpoint review
    lane-germline-0705-cp1):
      * NO EVIDENCE YET — evaluate() returns None for a cell with no rows.
        This is the LEGITIMATE unmeasured case → "unmeasured", which the
        trust-first matrix maps to act_with_undo for reversible/pm classes.
        Correct: a brand-new reversible cell is trusted from day one. NOTE: only
        a literal None is the no-evidence signal; a dict result MUST carry a
        recognized state — an empty/stateless dict falls to the OOV rule below
        (fail-closed), never silently trusted.
      * CANNOT READ — an import failure or an evaluate() EXCEPTION (broken
        evidence plane) → "demote". Pre-widening this path returned
        "unmeasured" because unmeasured meant propose_only; post-widening
        unmeasured means ALLOW, so resolving a read ERROR to "unmeasured" would
        silently ERASE a demotion at exactly the enforcing gate. "demote" maps
        to propose_only across every class (and always_gated still wins for
        ceilings), matching the lane gate's fail-closed `_graduation_demoted`
        (run_action_lane.py) — a broken evidence plane must BLOCK, never allow.
      * OUT-OF-VOCABULARY — evaluate() returned a state we don't recognize:
        also "demote" (fail-closed) — an unknown state must never be trusted.
    Reads the consequence ledger at call time (acceptable in shadow; revisit
    with a TTL cache before any enforcement flip if per-call latency matters).

    CANONICAL ACTOR-ID JOIN (2026-07-04 germline batch): this query composes
    "officer:" + the BARE role (e.g. "officer:cos"). Emitters therefore write
    actor = {"kind": "officer", "id": "<bare role>"} — NEVER a pre-prefixed
    "officer:cos" id, which double-prefixes to "officer:officer:cos" here and
    silently severs demotion evidence from the gate (the demote state would
    never be read). If you change the composition here, change every emitter
    in the same batch.
    """
    try:
        from framework.fidelity import graduation  # noqa: E402 (path set at module load)
        result = graduation.evaluate((f"officer:{officer}", lane, action_type))
    except Exception:
        # CANNOT READ the evidence plane → fail CLOSED (see docstring MF-1).
        return "demote"
    if result is None:
        # No cell rows yet — the LEGITIMATE unmeasured case (trust-first: a
        # fresh reversible cell is act_with_undo from day one).
        return "unmeasured"
    state = (result or {}).get("state")
    # A recognized state passes through; an out-of-vocabulary state is treated
    # as a read failure → fail closed (never trust an unknown state).
    return state if state in _CELL_STATES else "demote"


def _act_with_undo_gap(action_type: str) -> str | None:
    """Why an `act_with_undo` verdict can NOT be honored for `action_type` — a
    short gap reason for the block message — or None when the undo plane is
    mechanically viable and the gate may allow.

    THE TWO REQUIRED PRECONDITIONS (EARN-DEMOTION ruling, captain-decisions
    2026-07-03/04; Corridor-confirmed invariant): the allow branch grants
    act_with_undo ONLY when
      1. a REGISTERED deterministic inverse exists for this action_type, and
      2. the undo journal dir is reachable/writable;
    otherwise the caller falls through to propose-only. "No inverse ⇒ no
    unattended act" is the undo plane's mechanical perimeter
    (framework/frontdoor/action_undo.py:381 act_first_eligible); a journal
    dir that cannot be written means the lane's WRITE-AHEAD row — the 48h
    undo handle — could never land, so acting unattended would break the
    reversibility promise (framework/frontdoor/action_exec.py module
    docstring, "adversarial KILLED #2").

    ⚠ FLIP PRECONDITION — JOURNALING AT THE OFFICER TOOL SURFACE (MF-3,
    checkpoint review lane-germline-0705-cp1). This gate proves the undo plane
    is *mechanically viable* (an inverse is registered and the journal dir can
    be written), NOT that any given call is *actually* journaled. Reversibility
    is only real for acts that flow through the write-ahead lane
    (action_exec/action_undo). A RAW officer tool call — Edit/Write, or a direct
    Monday MCP mutation — that this matrix verdict would apply to is journaled
    by NOTHING and captures no prestate, so at CABINET_AUTHORITY_ENFORCING=1 an
    act_with_undo ALLOW here would permit an un-undoable write. This is DARK
    today (the authority matrix is excluded from the enforcing set — see
    main()), so no live call is affected. Do NOT flip enforcement for the
    act_with_undo classes until raw officer pm_write/calendar_write tool calls
    are routed through (or wrapped by) the journaled lane, or blocked at the
    hook so only lane-executed acts can act. Tracked as a flip precondition
    alongside the schg lock + launchd steps.

    SINGLE-SOURCE derivation — no duplicate mapping in the gate (same
    no-duplicate rule as the classifier import at the top of this file):
      * kind -> action_type: framework/acting/action_lane.py:524
        ACTION_TYPE_MAP (the graduation-wire stamp map). Inverted here; an
        action_type with ZERO lane kinds has nothing registered to execute
        (or reverse) it -> gap.
      * kind -> backend: framework/frontdoor/action_exec.py:210 _backend_for
        — the ACTUAL backend used at write time [RT-B11], env-aware
        (ACTION_LANE_REMINDER_BACKEND), so e.g. reminder_create on
        apple_reminders (no reliable inverse — act-first excluded) correctly
        yields a gap here instead of an allow.
      * registry probe: action_undo.act_first_eligible(kind, backend) — True
        iff inverse_for() yields a registered, non-"none" op AND the backend
        is not act-first excluded. Private-member imports are deliberate:
        duplicating either map in the gate is exactly the drift this
        codebase forbids.

    FAIL-SAFE (Corridor invariant): every probe is exception-wrapped to a
    gap reason — an import failure, a malformed registry, or an unprobeable
    journal path yields a gap (-> propose_only at the caller), NEVER an
    allow.

    READ-ONLY (Corridor invariant): the journal probe must not mkdir or
    touch anything — this eval is a pure decision function (section header
    above) and is also shadow-consumed per recorded verdict. Dir creation
    stays owned by the lane's journal_step/_ensure_dir at write time; the
    gate only verifies that creation WILL succeed (nearest existing ancestor
    is a writable, traversable dir). The probed path derives ONLY from
    action_undo._undo_dir() (CABINET_UNDO_DIR env / fixed default) — no
    tool-input ever reaches it (no traversal surface).
    """
    # Precondition 1 — a registered deterministic inverse for this action_type.
    try:
        from framework.acting.action_lane import ACTION_TYPE_MAP  # noqa: E402
        from framework.frontdoor import action_exec  # noqa: E402
        from framework.frontdoor import action_undo  # noqa: E402
    except Exception:
        return "undo registry unavailable"
    try:
        real_kinds = [k for k, at in ACTION_TYPE_MAP.items() if at == action_type]
        # N2 (checkpoint review lane-germline-0705-cp1): require EVERY real
        # execution kind of this action_type to be reversible, not just one.
        # `_act_with_undo_gap` only receives the action_type, but a card step
        # executes via a SPECIFIC kind; if several kinds map to one action_type
        # and only some are invertible, an `any()` allow would let the gate
        # trust the action_type while a card carrying the NON-invertible kind
        # acts un-undoably. `all()` is conservative-correct: whichever kind the
        # card carries, an inverse is guaranteed. (Today every widened/beachhead
        # action_type is single-kind so any()==all(); this hardens the class
        # against a future multi-kind entry.)
        if real_kinds:
            ok = all(
                action_undo.act_first_eligible(k, action_exec._backend_for(k))
                for k in real_kinds
            )
        else:
            # IDENTITY FALLBACK: the four WIDENED reversible action_types
            # {task_status_move, label, tier2_note, local_edit} are classifier-
            # native — they never appear as ACTION_TYPE_MAP values (the map
            # covers card-step kinds only: board_status, task_create,
            # calendar_event_create, officer_dispatch, investigation_run), so
            # real_kinds is []. action_undo registers their inverses under the
            # action_type NAME itself (inverse_for "GERMLINE WIDENING" branch),
            # so probe the action_type as its own kind. SAFE by the registry's
            # fail-closed shape: an unregistered name resolves op "none" -> not
            # eligible -> gap; _backend_for returns "unknown" (not act-first
            # excluded), which the four widened inverse branches ignore
            # (backend-agnostic — see the "deliberately NO backend branch" note
            # in inverse_for). An action_type with no real kinds AND no identity
            # registration correctly yields a gap.
            ok = action_undo.act_first_eligible(
                action_type, action_exec._backend_for(action_type)
            )
        if not ok:
            return "no registered deterministic inverse"
    except Exception:
        return "inverse-registry probe failed"

    # Precondition 2 — the undo journal dir is reachable/writable. Walk up to
    # the nearest EXISTING ancestor (the dir itself may legitimately not exist
    # yet — journal_step mkdirs at write time) and require it to be a writable,
    # traversable directory. A non-dir in the way, an unwritable ancestor, or
    # any OSError -> gap.
    try:
        probe = action_undo._undo_dir()
        # N4 (checkpoint review): a RELATIVE undo dir would resolve the walk-up
        # against the current working directory — a writable cwd could then
        # falsely satisfy "journal viable" while the real durable target is
        # elsewhere. A durable journal is always an absolute location, so a
        # relative path is a misconfiguration → fail closed (gap), never a
        # cwd-relative false positive.
        if not probe.is_absolute():
            return "undo journal dir not absolute"
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        if not (probe.is_dir() and os.access(probe, os.W_OK | os.X_OK)):
            return "undo journal dir unreachable"
    except Exception:
        return "undo-journal probe failed"

    return None


# ---------------------------------------------------------------------------
# Sovereign-posture gate wire [SOV-3] — posture selection + D2 ceiling branch
# ---------------------------------------------------------------------------
# Posture is a SELECTION dimension of the ONE matrix (sovereign build spec
# 2026-07-04 §0): the kernel (framework.authority.posture) answers "which
# posture table applies?", the floor's `postures.sovereign` table answers
# "what verdict?", and grants/needs (FI-2/FI-3) answer the hard-ceiling
# standing_grant rows. Everything here is fail-safe toward guardian: module
# absent, exception, unknown posture, malformed tables — all resolve today's
# exact behavior, byte-identical block strings included.

def resolve_gate_posture(lane: str | None = None) -> str:
    """The posture this gate evaluation runs under — fail-safe.

    "sovereign" IFF the SOV-1 kernel attests the Captain-locked ruling
    (present + schema-valid + deployment match + schg-locked; env may only
    narrow); "earn_up" whenever the kernel says so (a NARROWING choice the
    kernel honors even unattested — axes spec 2026-07-05 §1). Module absent,
    any exception, or an out-of-vocab answer resolves "guardian" — the
    default world stays bit-identical.
    """
    if _resolve_posture is None:
        return _GUARDIAN
    try:
        posture = _resolve_posture(lane)
    except Exception:
        return _GUARDIAN
    return posture if posture in _POSTURE_TABLES else _GUARDIAN


# The ONLY verdicts the earn_up ladder overlay may lift to — the frozen rung
# map's image (would-like-to maps to the propose_only floor itself = no lift).
# Anything else the ladder returns is refused fail-closed.
_RUNG_LIFT_VERDICTS = frozenset({"auto_with_veto_window", "notify_after", "auto"})


def _earn_up_rung_lift(lane: str | None) -> str | None:
    """The trust-ladder overlay verdict for an earn_up cell, or None (AX-2).

    Supplies the "Captain granted the rung for that lane" leg of the earn_up
    lift (axes spec 2026-07-05 §1 L1): trust_ladder.rung_verdict_lift derives
    the granted rung from the `granted:` rows of the ATTESTED
    (Captain-locked) ladder file — never from `trust_rung_granted` events,
    which are same-uid-appendable audit records (AX-8 no-self-grant fix) —
    capped by the rungs that same file still defines for the lane, and maps
    the effective rung through the frozen rung→verdict table. Lazy +
    fail-safe: module absent, broken grant read, missing/corrupt/unattested
    ladder file, or an out-of-vocab answer ⇒ None — the static earn_up floor
    (propose_only) stands. Never raises.
    """
    try:
        from framework.learning import trust_ladder  # noqa: E402
        lifted = trust_ladder.rung_verdict_lift(lane, posture=_EARN_UP)
    except Exception:
        return None
    return lifted if lifted in _RUNG_LIFT_VERDICTS else None


def _grant_context(tool_input: Any) -> dict[str, Any]:
    """Hard-scope context ({recipient|amount_eur|vendor}) from the tool call.

    Only positively-typed fields are forwarded — a missing field FAILS the
    class hard-scope predicate inside grants.check (fail-closed), so the gate
    never grants a ceiling act it cannot scope-verify.
    """
    if not isinstance(tool_input, dict):
        return {}
    ctx: dict[str, Any] = {}
    recipient = tool_input.get("recipient") or tool_input.get("to")
    if isinstance(recipient, str) and recipient.strip():
        ctx["recipient"] = recipient
    amount = tool_input.get("amount_eur")
    if isinstance(amount, (int, float)) and not isinstance(amount, bool):
        ctx["amount_eur"] = amount
    vendor = tool_input.get("vendor")
    if isinstance(vendor, str) and vendor.strip():
        ctx["vendor"] = vendor
    return ctx


def _emit_gate_tell(officer: str, payload: dict[str, Any]) -> None:
    """Best-effort org_event for a sovereign allow — the tell IS the audit
    (D4: a notify_after allow returns None, so no acted_row exists; this
    event is what the digest renders). NEVER blocks the allow."""
    try:
        from framework.events.emitter import emit  # noqa: E402
        emit("policy_evaluated", actor=f"officer:{officer}", payload=payload)
    except Exception:
        pass


def standing_grant_resolution(
    risk_class: str,
    action_type: str,
    *,
    lane: str | None,
    context: dict[str, Any] | None = None,
    officer: str = "unknown",
    act: bool = False,
) -> dict[str, Any]:
    """D2 standing-grant resolution for a sovereign hard-ceiling row.

    Returns {available, granted, grant_id, need_id, reason}. `act=True` is the
    GATE path (files the deduped NEED on a miss, counts the use on a hit);
    `act=False` is the SHADOW path — a pure probe: no need filed, no rate
    consumed, the would-be need id computed via the deterministic content
    fingerprint. `available=False` (grants module absent / check raised) means
    the standing-grant machinery cannot answer at all — the caller degrades
    the row to plain always_gated (guardian strings). Never raises.
    """
    out: dict[str, Any] = {
        "available": False, "granted": False, "grant_id": None,
        "need_id": None, "reason": "standing-grant kernel unavailable",
    }
    if _grants is None:
        return out
    try:
        res = _grants.check(
            risk_class, action_type, lane=lane, context=context,
            file_needs=act,
        )
    except Exception:
        return out
    out["available"] = True
    if isinstance(res, dict) and res.get("granted"):
        out["granted"] = True
        out["grant_id"] = res.get("grant_id")
        out["reason"] = str(res.get("reason") or "")
        if act:
            try:
                _grants.record_use(out["grant_id"])
            except Exception:
                pass
        return out
    out["reason"] = str(
        (res.get("reason") if isinstance(res, dict) else None)
        or "no matching standing grant"
    )
    if _needs is not None:
        try:
            if act:
                out["need_id"] = _needs.file_need(
                    "standing_grant",
                    risk_class=risk_class,
                    action_type=action_type,
                    lane=lane,
                    why=(
                        f"officer gate blocked {risk_class}/{action_type} "
                        f"(lane {lane}): {out['reason']}"
                    ),
                    unblocks=(
                        f"sovereign auto for {action_type} under a Captain "
                        f"standing grant"
                    ),
                    filed_by=f"policy_engine:{officer}",
                    scope_hint=context,
                )
            else:
                out["need_id"] = _needs.need_id(
                    "standing_grant", risk_class, action_type, lane
                )
        except Exception:
            out["need_id"] = None
    return out


def _eval_authority_matrix(
    policy: dict, tool_name: str, tool_input: dict, officer: str
) -> str | None:
    """Authority-matrix verdict for a tool call. Returns a block message
    (propose-only / gated) or None (allow).

    Ceiling classes always gate in guardian; a SOVEREIGN posture ceiling row
    may resolve `standing_grant` (D2): an attested Captain standing grant with
    a satisfied hard-scope predicate ⇒ attributed allow + rate-counted; else a
    deduped NEED is filed and this step gates while the chain proceeds. Under
    EARN_UP the ceiling rows stay always_gated (guardian strings, grants never
    consulted) and non-ceiling cells floor at propose_only, liftable only by
    the trust-ladder overlay (step 3b — graduated cell + Captain-granted
    rung). Other cells resolve via the LIVE graduation state (read_cell_state,
    un-stubbed 2026-07-03) against the POSTURE-SELECTED verdicts table into
    one of the outcomes below — consumed in SHADOW only until the
    Captain-gated enforcement flip:

      * `auto`                    -> allow (None) — a graduated cell.
      * `act_with_undo`           -> allow (None) ONLY when the undo plane is
                                     mechanically viable for the action_type
                                     (_act_with_undo_gap: registered inverse
                                     + writable journal); else propose-only.
                                     EARN-DEMOTION doctrine (2026-07-04 fix).
      * `auto_with_veto_window` /
        `notify_after`            -> allow (None) at THIS gate; the window /
                                     after-notification is enforced by the
                                     downstream deferred-send + consequence
                                     machinery, not by a pre-tool-use block.
                                     notify_after (sovereign tables, D4) also
                                     emits the gate tell the digest renders —
                                     the gate returns None so no acted_row
                                     exists; the org_event IS the record.
      * anything else (propose_only, always_gated, classifier, a MISPLACED
        standing_grant on a non-ceiling row, unknown)
                                  -> propose-only (fail-safe collapse).

    With no posture config the resolution and every block string are
    byte-identical to the guardian/legacy gate. See the section headers for
    the fail-safe contract.
    """
    # RECONCILE 2026-07-05: kept both — HEAD's four-outcome verdict contract
    # (act_with_undo gap-check + veto-window/notify_after allow legs) + the
    # sovereign posture axis (standing_grant D2 ceiling path, posture-selected
    # tables, guardian byte-identical default).
    message = policy.get("message", "below the autonomy bar — proposing instead")

    # 0. A merged floor that failed validation was quarantined by
    #    load_policies (D8) — fail CLOSED to propose-only, never evaluate it.
    if policy.get("_validation_failed"):
        return f"PROPOSE-ONLY (authority matrix failed validation) — {message}"

    # The shared classifier/lane resolver are imported at module load from
    # framework.authority. If absent (deployment without the framework on the
    # path), fail-safe to propose_only rather than crashing the gate.
    if classify_action is None or resolve_lane is None:
        return f"PROPOSE-ONLY (classifier unavailable) — {message}"

    action_type = classify_action(tool_name, tool_input)
    risk_classes = policy.get("risk_classes")
    risk_class = risk_of(action_type, risk_classes)

    # 1. Unknown / ambiguous / unmapped action_type -> fail-safe propose_only.
    if risk_class is None:
        return (
            f"PROPOSE-ONLY (unclassified action '{action_type}') — {message}"
        )

    # Lane + posture resolve ONCE, above the ceiling short-circuit [SOV-3]
    # (both are pure reads; posture is guardian on any ambiguity/failure).
    lane = resolve_lane()
    posture = resolve_gate_posture(lane)
    postures = policy.get("postures")

    # 2. HARD CEILING short-circuit — ignores confidence, fail-closed [FIX-7].
    #    Sovereign narrows always_gated to the CONDITIONAL standing_grant only
    #    when the posture table says so (D2); every other outcome — guardian,
    #    always_gated posture row, kernel unavailable — keeps the guardian
    #    strings BYTE-IDENTICAL.
    hard_ceiling = policy.get("hard_ceiling")
    if isinstance(hard_ceiling, list) and risk_class in hard_ceiling:
        if posture in _POSTURE_TABLES:
            ceiling_verdict = resolve_verdict(
                policy.get("verdicts"), risk_class, "*",
                posture=posture, postures=postures,
            )
            if ceiling_verdict == "standing_grant":
                res = standing_grant_resolution(
                    risk_class, action_type, lane=lane,
                    context=_grant_context(tool_input), officer=officer,
                    act=True,
                )
                if res["granted"]:
                    # Attributed allow — grant_id is the authority.
                    _emit_gate_tell(officer, {
                        "kind": "standing_grant_allow",
                        "verdict": "standing_grant",
                        "posture": posture,
                        "risk_class": risk_class,
                        "action_type": action_type,
                        "lane": lane,
                        "grant_id": res["grant_id"],
                        "tool_name": tool_name,
                    })
                    return None
                if res["available"]:
                    # U+00B7 strip — same binder-injection defense as the
                    # needs kernel (the reason may echo executor scope data).
                    reason = str(
                        res.get("reason") or "no matching standing grant"
                    ).replace("·", "")
                    if res.get("need_id"):
                        return (
                            f"GATED (standing_grant: {risk_class}) — {reason}; "
                            f"filed {res['need_id']} — the chain proceeds "
                            f"without this step."
                        )
                    return (
                        f"GATED (standing_grant: {risk_class}) — {reason}; "
                        f"the chain proceeds without this step."
                    )
                # Kernel unavailable ⇒ the row degrades to plain always_gated
                # (guardian strings below) — narrower, never wider.
        if risk_class == "external_comms":
            return (
                "GATED (hard ceiling: external_comms) — draft via queue_draft, "
                "never auto."
            )
        return (
            f"GATED (hard ceiling: {risk_class}) — propose to Captain; "
            f"no auto path."
        )

    # 3. Read the LIVE per-cell graduation state (read_cell_state, un-stubbed
    #    2026-07-03; fail-CLOSED — exception/OOV -> demote, only a literal
    #    None -> unmeasured) and resolve the (risk_class, state) cell against
    #    the posture-selected verdicts table. Lane + posture were resolved
    #    ONCE above the ceiling short-circuit [SOV-3] — never re-resolved
    #    here (cell-key normalization stays consistent between emit + gate).
    # RECONCILE 2026-07-05: kept both — HEAD's live-graduation read + the
    # sovereign posture-table resolution; dropped HEAD's duplicate
    # `lane = resolve_lane()` (lane already resolved at step 1.5).
    state = read_cell_state(officer, lane, action_type)
    verdict = resolve_verdict(
        policy.get("verdicts"), risk_class, state,
        posture=posture, postures=postures,
    )

    # 3b. EARN_UP TRUST-LADDER OVERLAY [AX-2, axes spec 2026-07-05 §1 L1] —
    #    the static earn_up table floors every non-ceiling cell at
    #    propose_only; ALL autonomy above that floor is rung-granted at run
    #    time. The lift applies ONLY when posture==earn_up AND the cell's
    #    LIVE graduation state is `graduated` AND the Captain granted the
    #    rung for this lane (trust_rung_granted, replayed by the ladder —
    #    capped by the ladder file, so a missing/corrupt file fail-closes to
    #    the floor). NEVER lifts ceilings: step 2 short-circuits every
    #    hard-ceiling class before this point, and the isinstance guard
    #    additionally refuses to lift ANYTHING under a malformed hard_ceiling
    #    (fail-closed — a ceiling class could otherwise reach step 3).
    #    Guardian and sovereign never enter this branch (posture equality),
    #    so their behavior stays byte-identical.
    if (
        posture == _EARN_UP
        and state == "graduated"
        and isinstance(hard_ceiling, list)
        and risk_class not in hard_ceiling
    ):
        lifted = _earn_up_rung_lift(lane)
        if lifted is not None:
            verdict = lifted

    # RECONCILE 2026-07-05: kept both — HEAD's verdict ladder (act_with_undo
    # gap-check, auto_with_veto_window/notify_after allow legs, fail-safe
    # collapse, auto) + sovereign's notify_after gate-tell emission and the
    # misplaced-standing_grant fail-closed branch (D4).

    # 4. act_with_undo — the EARN-DEMOTION allow branch (added 2026-07-04).
    #    FIXES A DORMANT LANDMINE: the bare `verdict != "auto"` collapse below
    #    used to catch act_with_undo too, blocking it at EVERY state. The
    #    germline matrix (framework/policies/authority-matrix.yml:84-95) maps
    #    pm_write / calendar_write to act_with_undo at every non-demote
    #    confidence state — the EARN-DEMOTION ruling (captain-decisions
    #    2026-07-03/04): trust on reversible-with-undo is granted from day one
    #    and LOST on evidence (demote -> propose_only via resolve_verdict),
    #    never pre-earned. Collapsing it to propose-only was dormant while
    #    CABINET_AUTHORITY_ENFORCING defaulted "0", but would have silently
    #    reversed the doctrine forever the moment the flag flipped.
    #
    #    ALLOW IS CONDITIONAL (fail-safe — Corridor-confirmed invariant): the
    #    gate returns allow(None) ONLY when a registered deterministic inverse
    #    exists for the action_type AND the undo journal path is writable
    #    (_act_with_undo_gap above); otherwise it falls through to
    #    propose-only with the gap named in the message. And the gate's None
    #    only stops the pre-tool-use BLOCK — it executes nothing: act-first
    #    execution is honored solely through the journaled action lane, which
    #    write-ahead-journals before every mutation (PATH parity,
    #    framework/frontdoor/tests/test_undo_capability_parity.py).
    if verdict == "act_with_undo":
        gap = _act_with_undo_gap(action_type)
        if gap is None:
            return None
        return (
            f"PROPOSE-ONLY ({risk_class}, confidence={state}; act_with_undo "
            f"verdict but {gap} for '{action_type}') — {message}"
        )

    # 5. auto_with_veto_window / notify_after — explicit allow-with-window
    #    (added 2026-07-04; previously collapsed to propose by the bare
    #    `!= "auto"` check). Both are ACT verdicts in the matrix vocabulary
    #    (framework/authority/matrix.py:68): auto_with_veto_window acts with a
    #    deferred-send veto window (veto_window_minutes, matrix Component 5 —
    #    internal_comms@graduated, where "the notification IS the veto
    #    handle"); notify_after acts immediately and tells the Captain after
    #    (the read_only_dispatch posture, e.g. investigation_run — read-only,
    #    so no inverse is needed or checked). The window / notification is
    #    enforced by the downstream deferred-send + consequence machinery, NOT
    #    by a pre-tool-use exit-2 — so at THIS gate both resolve to allow.
    #    Only cells the Captain-ratified germline matrix maps to these
    #    verdicts can reach here; hard ceilings were short-circuited at step 2
    #    and can never resolve to an act verdict. notify_after (present in
    #    sovereign tables per D4 — guardian carries none) additionally EMITS
    #    the gate tell: the gate returns None so no acted_row exists; the
    #    org_event is what the digest renders.
    if verdict == "auto_with_veto_window":
        return None
    if verdict == "notify_after":
        _emit_gate_tell(officer, {
            "kind": "notify_after",
            "verdict": "notify_after",
            "posture": posture,
            "risk_class": risk_class,
            "action_type": action_type,
            "confidence_state": state,
            "lane": lane,
            "tool_name": tool_name,
        })
        return None

    # 5b. A standing_grant verdict reaching this step is MISPLACED (D4 — it is
    #    only legal on a posture ceiling row, resolved at step 2 above) —
    #    fail CLOSED to propose-only with the misplacement named, never allow.
    if verdict == "standing_grant":
        return (
            f"PROPOSE-ONLY (misplaced standing_grant verdict on "
            f"'{risk_class}') — {message}"
        )

    # 6. FAIL-SAFE collapse — any verdict not explicitly allowed above blocks
    #    as propose-only: propose_only itself, always_gated, unknown or
    #    malformed verdict strings — undefined never acts (Corridor
    #    invariant). With no posture config every cell resolves from the root
    #    (guardian) table and every block string here is byte-identical to
    #    the legacy gate. CAPTAIN-RULING (2026-07-04 germline batch):
    #    `classifier` (deploy_nonprod@graduated/eligible -> mechanical
    #    low-risk-deploy routing) deliberately STAYS collapsed here —
    #    deploy_nonprod keeps the earn-up posture and was NOT widened; wiring
    #    the deploy classifier is a separate Captain-gated step.
    if verdict != "auto":
        return f"PROPOSE-ONLY ({risk_class}, confidence={state}) — {message}"

    # 7. auto verdict -> allow. Reachable only for a cell the live graduation
    #    engine has actually graduated under the posture-selected table
    #    (read_cell_state fail-safes read errors to "demote" and no-evidence
    #    to "unmeasured") — and still SHADOW-consumed until the Captain-gated
    #    enforcement flip.
    return None


# ---------------------------------------------------------------------------
# Policy loading
# ---------------------------------------------------------------------------

def _is_authority_matrix_policy(policy: Any, name: Any) -> bool:
    """True for the authority-matrix policy by TYPE or by NAME — the name
    check stops a preset/instance policy named `authority-matrix` (any type)
    from displacing the floor entry in the by-name merge."""
    return (
        isinstance(policy, dict)
        and (policy.get("type") == "authority_matrix" or name == "authority-matrix")
    )


def _validate_authority_floor(policies_by_name: dict[str, dict]) -> None:
    """Runtime-validate the merged authority floor with the SAME validators as
    CI (D8: `_validate_postures` + `no_ceiling_or_prod_auto`) — fail CLOSED.

    Any violation — or the validators being unimportable — replaces the policy
    with a quarantine stub carrying `_validation_failed`, which the gate
    resolves to propose-only for EVERY action (never fail-open, never evaluate
    a widening/corrupt matrix). D8's OTHER arm, the MISSING floor: a merge
    that produced no `authority_matrix` policy at all (floor file deleted, or
    unparseable so the malformed-file skip dropped it) synthesizes the same
    stub under the reserved floor name — otherwise the gate would apply no
    authority verdict whatsoever, which is fail-open. Mutates
    `policies_by_name` in place.
    """
    for name, policy in list(policies_by_name.items()):
        if not isinstance(policy, dict) or policy.get("type") != "authority_matrix":
            continue
        try:
            from framework.authority.matrix import (  # noqa: E402
                _validate_postures, no_ceiling_or_prod_auto,
            )
            _validate_postures(policy)
            if not no_ceiling_or_prod_auto(policy):
                raise ValueError("a hard-ceiling row resolves to 'auto'")
        except Exception as exc:
            policies_by_name[name] = {
                "name": name,
                "type": "authority_matrix",
                "message": str(
                    policy.get("message")
                    or "below the autonomy bar — proposing instead"
                ),
                "_validation_failed": str(exc) or "authority matrix failed validation",
            }
            print(
                f"WARN: policy-engine — authority matrix '{name}' failed "
                f"validation ({exc}); fail-closed to propose-only",
                file=sys.stderr,
            )
    if not any(
        isinstance(p, dict) and p.get("type") == "authority_matrix"
        for p in policies_by_name.values()
    ):
        policies_by_name["authority-matrix"] = {
            "name": "authority-matrix",
            "type": "authority_matrix",
            "message": "below the autonomy bar — proposing instead",
            "_validation_failed": "floor missing/unparseable",
        }
        print(
            "WARN: policy-engine — authority matrix floor missing/unparseable; "
            "fail-closed to propose-only",
            file=sys.stderr,
        )


def load_policies(cabinet_root: str | None = None) -> list[dict]:
    """Load policies from framework + preset + instance layers.

    Later layers can override earlier policies by name — EXCEPT the authority
    matrix, which is FLOOR-ONLY (D8): a preset/instance layer carrying an
    `authority_matrix`-typed policy (or one named `authority-matrix`) is
    refused with a WARN, so a writable layer can never widen the germline
    verdict tables. The surviving merged floor is then runtime-validated
    fail-closed — and a merge with NO surviving floor (file absent or
    unparseable) is quarantined the same way (see `_validate_authority_floor`).
    """
    import yaml  # noqa: E402 — deferred import, available in CI

    if cabinet_root is None:
        cabinet_root = os.environ.get("CABINET_ROOT", "/opt/founders-cabinet")

    # Determine active preset
    active_preset = os.environ.get("ACTIVE_PRESET", "")
    if not active_preset:
        preset_file = os.path.join(cabinet_root, "instance", "config", "active-preset")
        try:
            active_preset = Path(preset_file).read_text().strip()
        except (FileNotFoundError, PermissionError):
            active_preset = "work"

    # Scan paths in order (later overrides earlier by policy name)
    policy_dirs = [
        os.path.join(cabinet_root, "framework", "policies"),
        os.path.join(cabinet_root, "presets", active_preset, "policies"),
        os.path.join(cabinet_root, "instance", "config", "policies"),
    ]

    policies_by_name: dict[str, dict] = {}

    for layer, policy_dir in enumerate(policy_dirs):
        if not os.path.isdir(policy_dir):
            continue
        for filename in sorted(os.listdir(policy_dir)):
            if not filename.endswith((".yml", ".yaml")):
                continue
            filepath = os.path.join(policy_dir, filename)
            try:
                with open(filepath) as f:
                    data = yaml.safe_load(f)
                if not data or "policies" not in data:
                    continue
                for policy in data["policies"]:
                    name = policy.get("name")
                    if not name:
                        continue
                    if layer > 0 and _is_authority_matrix_policy(policy, name):
                        # D8: framework floor wins — refuse the layered matrix.
                        print(
                            f"WARN: policy-engine — {filepath} layers an "
                            f"authority matrix ('{name}'); the framework "
                            f"floor wins (skipped)",
                            file=sys.stderr,
                        )
                        continue
                    policies_by_name[name] = policy
            except Exception:
                # Skip malformed policy files — fail-open with warning
                print(
                    f"WARN: policy-engine — failed to load {filepath}",
                    file=sys.stderr,
                )

    _validate_authority_floor(policies_by_name)
    return list(policies_by_name.values())


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        hook_input = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        # Malformed input — fail-open (don't brick the session)
        sys.exit(0)

    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})
    officer = os.environ.get("OFFICER", os.environ.get("OFFICER_NAME", "unknown"))

    # Load policies from framework + preset + instance
    cabinet_root = os.environ.get("CABINET_ROOT", "/opt/founders-cabinet")
    policies = load_policies(cabinet_root)

    # NO-LIVE-BEHAVIOR-CHANGE gate [T6, A0 shadow-only]. The authority_matrix
    # verdict is reachable via evaluate_policy() (the shadow harness calls it
    # directly to RECORD verdicts), but main() — the live hook entry — must NOT
    # exit-2 on an authority verdict until the Captain-gated enforcing flip.
    # CABINET_AUTHORITY_ENFORCING defaults "0": authority_matrix policies are
    # skipped by the live loop, so authority adds no new live block. The legacy
    # typed rules (binary_block / destructive_rm / command_contains / path_block
    # / bash_write_to_path / tier2_isolation) are unaffected and still enforce.
    # This flag is independent of the legacy-engine enforcing flag; flipping it
    # is a later, Captain-approved cycle (design §7 Cycle 2).
    authority_enforcing = os.environ.get("CABINET_AUTHORITY_ENFORCING", "0") == "1"

    # Evaluate each policy
    for policy in policies:
        if policy.get("type") == "authority_matrix" and not authority_enforcing:
            continue  # shadow-only in A0 — do not live-block on the verdict
        result = evaluate_policy(policy, tool_name, tool_input, officer)
        if result:
            print(result, file=sys.stderr)
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
