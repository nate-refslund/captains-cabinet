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
# Shell command parsing — the core innovation replacing ~700 lines of regex
# ---------------------------------------------------------------------------

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
    r"tar\b[^;&|]*(?:-[a-zA-Z]*C\s*|--directory[=\s]+)[\"']?{path}",
    # Pattern 9: tar with -f/--file writing archive to path
    r"tar\b[^;&|]*(?:-[^\s]*f\s*|--file[=\s]+)[\"']?{path}",
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
# Policy loading
# ---------------------------------------------------------------------------

def load_policies(cabinet_root: str | None = None) -> list[dict]:
    """Load policies from framework + preset + instance layers.

    Later layers can override earlier policies by name.
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

    for policy_dir in policy_dirs:
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
                    if name:
                        policies_by_name[name] = policy
            except Exception:
                # Skip malformed policy files — fail-open with warning
                print(
                    f"WARN: policy-engine — failed to load {filepath}",
                    file=sys.stderr,
                )

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

    # Evaluate each policy
    for policy in policies:
        result = evaluate_policy(policy, tool_name, tool_input, officer)
        if result:
            print(result, file=sys.stderr)
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
