#!/usr/bin/env python3.12
"""Render (and, only when explicitly told to, install) the fleet dead-man agent.

WHY THIS IS PYTHON AND NOT SHELL. CI runs on ubuntu and its only shell coverage
is `bash -n` — a syntax check that executes nothing. A shell installer would be
untested by construction on macOS, the one platform that exists. Everything
here that can be decided without launchd is a pure function with tests that run
on the CI runner; the only macOS-specific step left is `launchctl bootstrap`,
which this script deliberately does not perform.

WHY IT NEVER CALLS launchctl. Installing a LaunchAgent is an operational act on
someone's machine. `generate-plists.py` holds the same line for the fleet
("this script NEVER calls launchctl — rendering only") and the reasoning is
identical here, with one addition: this agent's entire value is that it is NOT
part of the fleet's install path, so quietly joining one would undo the point.
The final two commands are PRINTED for a human to run.

Default is render-and-print. `--install` is the only flag that writes into
~/Library/LaunchAgents, and even then nothing is loaded until the human runs
the bootstrap line it prints.
"""
from __future__ import annotations

import argparse
import os
import plistlib
import re
import subprocess
import sys

LABEL = "com.cabinet-liveness.fleet-deadman"
TEMPLATE_REL = f"cabinet/launchd/{LABEL}.template.plist"
LAUNCH_AGENTS = "~/Library/LaunchAgents"

# The substitutions the template declares. Kept as an explicit, closed set so an
# unrendered placeholder is a hard error rather than a literal "${HOME}" quietly
# baked into a plist that then fails at 3am with a confusing path.
_PLACEHOLDER = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


def render(template: str, values: dict) -> str:
    """Substitute ``${NAME}`` from ``values``. Raises on any placeholder the
    caller did not supply — a half-rendered plist is worse than no plist,
    because launchd will happily load it and then never work."""
    missing = sorted({m.group(1) for m in _PLACEHOLDER.finditer(template)}
                     - set(values))
    if missing:
        raise KeyError(f"template placeholders with no value: {missing}")
    return _PLACEHOLDER.sub(lambda m: values[m.group(1)], template)


def default_values(repo_root: str, home: str, user: str) -> dict:
    return {"REPO_ROOT": repo_root.rstrip("/"), "HOME": home.rstrip("/"),
            "USER": user}


def destination(agents_dir: str) -> str:
    return os.path.join(os.path.expanduser(agents_dir), f"{LABEL}.plist")


def under(path: str, root: str) -> bool:
    """Is ``path`` inside ``root``? Used to assert a write lands where it was
    asked to land BEFORE the write happens — the sandbox rule this program paid
    for when a sweep nearly appended to a live env file."""
    p = os.path.realpath(os.path.expanduser(path))
    r = os.path.realpath(os.path.expanduser(root))
    return p == r or p.startswith(r.rstrip("/") + os.sep)


def validate(rendered: str) -> dict:
    """Parse the rendered plist and assert the properties that matter. Returns
    the parsed dict. plistlib is the same parser launchd's format targets, so a
    file that fails here would have failed there — just later and quieter."""
    obj = plistlib.loads(rendered.encode("utf-8"))
    if obj.get("Label") != LABEL:
        raise ValueError(f"Label is {obj.get('Label')!r}, expected {LABEL!r}")
    if obj["Label"].startswith("com.cabinet."):
        # The one invariant that makes this agent worth having: it must not be
        # inside the label space that gets torn down as a unit.
        raise ValueError("this agent must NOT live under the com.cabinet.* "
                         "prefix — the fleet teardown unloads that prefix "
                         "wholesale, which is the event it exists to survive")
    if not obj.get("StartInterval"):
        raise ValueError("no StartInterval: a dead-man that never runs is not "
                         "a dead-man")
    return obj


def main(argv: list | None = None) -> int:
    here = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    ap = argparse.ArgumentParser(prog="fleet-deadman-install")
    ap.add_argument("--repo-root", default=here)
    ap.add_argument("--output-dir", default="",
                    help="render here instead of printing (never loads)")
    ap.add_argument("--install", action="store_true",
                    help=f"write the plist into {LAUNCH_AGENTS} (still does NOT "
                         "load it; the bootstrap line is printed for a human)")
    args = ap.parse_args(argv)

    root = os.path.realpath(os.path.expanduser(args.repo_root))
    tpl_path = os.path.join(root, TEMPLATE_REL)
    try:
        with open(tpl_path, "r", encoding="utf-8") as fh:
            template = fh.read()
    except OSError as exc:
        print(f"cannot read {tpl_path}: {exc}", file=sys.stderr)
        return 1

    values = default_values(root, os.path.expanduser("~"),
                            os.environ.get("USER", ""))
    try:
        rendered = render(template, values)
        validate(rendered)
    except Exception as exc:
        print(f"render failed: {exc}", file=sys.stderr)
        return 1

    if args.install and args.output_dir:
        print("--install and --output-dir are mutually exclusive", file=sys.stderr)
        return 2

    out_dir = os.path.expanduser(args.output_dir or "") or (
        os.path.expanduser(LAUNCH_AGENTS) if args.install else "")
    if not out_dir:
        sys.stdout.write(rendered)
        print(f"\n# not written. --output-dir <dir> to stage, --install for "
              f"{LAUNCH_AGENTS}", file=sys.stderr)
        return 0

    if not under(os.path.join(out_dir, "x"), out_dir):  # pragma: no cover
        print("refusing: destination escapes its own directory", file=sys.stderr)
        return 2
    os.makedirs(out_dir, exist_ok=True)
    dest = destination(out_dir)
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(rendered)
    try:
        subprocess.run(["plutil", "-lint", dest], check=True,
                       capture_output=True, timeout=30)
    except FileNotFoundError:
        pass  # not macOS; plistlib already validated the structure
    except subprocess.CalledProcessError as exc:
        print(f"plutil -lint rejected {dest}: {exc.stdout}", file=sys.stderr)
        return 1

    print(f"wrote {dest}")
    print("")
    print("NOTHING IS LOADED YET. To start it, run these two lines yourself:")
    print(f"  launchctl bootout gui/$(id -u)/{LABEL} 2>/dev/null || true")
    print(f"  launchctl bootstrap gui/$(id -u) {dest}")
    print("")
    print("Then confirm both legs are armed:")
    print("  python3.12 cabinet/scripts/fleet-deadman.py --status")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
