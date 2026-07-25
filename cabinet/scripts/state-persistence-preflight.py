#!/usr/bin/env python3.12
"""State-persistence preflight — does this deploy lose the cabinet's learned state?

WHY THIS EXISTS
---------------
cabinet-deploy.sh provisions every release as a FRESH `git worktree`. A fresh
worktree contains tracked files and nothing else, so every gitignored path —
which is precisely the cabinet's accumulated runtime state — starts EMPTY in
the new release. The only thing that carries state across a deploy is
runtime-provision.sh's link_instance_data(), which symlinks a hand-maintained
set of paths into the runtime root's shared/ tree.

Three hand-maintained lists already drifted from .gitignore: ratified Captain
rules (memory/skills/evolved/), the tier-3 decision log, the tool-call log, the
append-only foundry archive and two instance config files were silently dropped
on every deploy. Nothing errored; the health gate passed. State was stranded in
the old release directory and then `rm -rf`'d by `prune --keep 5`.

So this check does NOT add a fourth hand-maintained list. It DERIVES the durable
set from .gitignore (the authoritative answer to "what can a fresh worktree not
contain?") and asserts every derived path is either carried or explicitly,
reasonedly declared disposable.

FAIL-CLOSED, deliberately. Anything the checker cannot positively account for is
a FAILURE, never a silent pass:
  - a derived path matching no persistence list and no policy entry -> FAIL
  - a policy entry with a missing/empty `reason` -> FAIL
  - a persistence list that cannot be parsed out of runtime-provision.sh -> FAIL
    (an unparseable list must never read as an empty list)
  - a wildcard rule the policy claims, but which no longer exists in
    runtime-provision.sh -> FAIL

MODES
  (default)      static: derive from .gitignore, check the lists + policy.
                 This is the CI job — it catches list drift at review time.
  --slot <path>  additionally assert against a REAL provisioned release: every
                 durable path must resolve into the runtime root's shared/ tree
                 (or be genuinely present). This is the deploy-time gate — it
                 catches "the list says so but the linking did not happen".

Exit 0 = no durable path would be lost. Exit 1 = this deploy loses state.
Exit 2 = the checker could not establish the facts (also a blocking failure).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import sys

import yaml

# The wildcard-linking blocks inside link_instance_data() that this checker
# models. Each policy `wildcard_covered` entry must name one of these probes;
# the probe string must still be greppable in runtime-provision.sh, so deleting
# a wildcard block fails the check instead of silently widening coverage.
WILDCARD_PROBES = {
    "agents-ceo-md": '-ceo.md',
    "oauth-backup": '.oauth-backup-',
    "interfaces-md": 'name \'*.md\'',
    "cabinet-env": 'shared/cabinet.env',
}


def die(msg: str) -> None:
    print(f"state-persistence-preflight: CANNOT VERIFY — {msg}", file=sys.stderr)
    sys.exit(2)


def unit_of(pattern: str) -> str:
    """Reduce a gitignore pattern to the path that holds the state.

    A wildcard pattern's durability unit is the deepest wildcard-free prefix:
    `memory/logs/*.jsonl` -> `memory/logs`. A literal pattern is its own unit.
    Trailing/leading slashes are stripped so units compare cleanly.
    """
    p = pattern.strip().rstrip("/").lstrip("/")
    parts = []
    for seg in p.split("/"):
        if any(ch in seg for ch in "*?["):
            break
        parts.append(seg)
    return "/".join(parts) if parts else p


def parse_gitignore(path: str) -> list[tuple[str, int]]:
    """Positive (non-negated) patterns with line numbers. Negations only
    re-include tracked files, which by definition survive a fresh worktree."""
    out = []
    with open(path, encoding="utf-8") as fh:
        for n, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("!"):
                continue
            out.append((line, n))
    if not out:
        die(f"{path} yielded no patterns — refusing to certify an empty durable set")
    return out


def parse_persistence_lists(path: str) -> dict[str, list[str]]:
    """Extract the three lists from runtime-provision.sh by regex.

    Sourcing the script would execute its command dispatch, so it is read as
    text. Every list is REQUIRED: a rename or reformat that makes one
    unparseable fails the check rather than silently emptying it.
    """
    try:
        src = open(path, encoding="utf-8").read()
    except OSError as exc:
        die(f"cannot read {path}: {exc}")
    lists: dict[str, list[str]] = {}
    for var in ("INSTANCE_PERSISTENT_DIRS",
                "INSTANCE_PERSISTENT_SEEDED_DIRS",
                "INSTANCE_PERSISTENT_FILES"):
        m = re.search(rf'^{var}="([^"]*)"', src, re.M)
        if not m:
            die(f"could not parse {var} out of {path} — an unparseable list must "
                f"never be treated as an empty list")
        entries = m.group(1).split()
        if not entries:
            die(f"{var} parsed as EMPTY in {path} — refusing to pass")
        lists[var] = entries
    for name, probe in WILDCARD_PROBES.items():
        if probe not in src:
            die(f"wildcard rule '{name}' (probe {probe!r}) no longer present in "
                f"{path} — coverage claims for it are stale")
    return lists


def parse_policy(path: str) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Load the policy file. EVERY entry must carry a non-empty reason.

    `known_gap` is for a path that IS durable but whose fix needs a design
    decision (e.g. the persisted copy would shadow a tracked file). It is
    deliberately narrow: it must also carry an `expires` date, and the check
    FAILS once that date passes, so a deferral cannot quietly become permanent.
    """
    try:
        doc = yaml.safe_load(open(path, encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        die(f"cannot read policy {path}: {exc}")
    problems: list[str] = []
    parsed: dict[str, dict[str, str]] = {}
    today = _dt.date.today()
    for section in ("wildcard_covered", "disposable", "known_gap"):
        acc: dict[str, str] = {}
        for i, entry in enumerate(doc.get(section) or []):
            if not isinstance(entry, dict) or "path" not in entry:
                problems.append(f"{section}[{i}]: entry is not a mapping with a 'path'")
                continue
            reason = str(entry.get("reason") or "").strip()
            if not reason:
                problems.append(
                    f"{section}: '{entry['path']}' has no reason — a "
                    f"persistence exemption without a written reason is a failure")
                continue
            if section == "wildcard_covered":
                rule = str(entry.get("rule") or "").strip()
                if rule not in WILDCARD_PROBES:
                    problems.append(
                        f"wildcard_covered: '{entry['path']}' names rule {rule!r}, "
                        f"which is not a known link_instance_data wildcard block")
                    continue
            if section == "known_gap":
                raw = str(entry.get("expires") or "").strip()
                try:
                    expires = _dt.date.fromisoformat(raw)
                except ValueError:
                    problems.append(
                        f"known_gap: '{entry['path']}' needs an `expires: YYYY-MM-DD` "
                        f"date — an open data-loss gap may not be deferred forever")
                    continue
                if expires < today:
                    problems.append(
                        f"known_gap: '{entry['path']}' EXPIRED on {expires} — this "
                        f"durable path is still not carried across deploys. Fix it "
                        f"or have the Captain re-date the deferral.")
                    continue
                reason = f"{reason} (deferred until {expires})"
            acc[unit_of(str(entry["path"]))] = reason
        parsed[section] = acc
    if problems:
        for p in problems:
            print(f"state-persistence-preflight: POLICY ERROR — {p}", file=sys.stderr)
        sys.exit(1)
    return parsed["wildcard_covered"], parsed["disposable"], parsed["known_gap"]


def covered_by_lists(unit: str, lists: dict[str, list[str]]) -> str | None:
    """A whole-directory symlink carries everything beneath it; a file entry
    carries exactly itself."""
    for var in ("INSTANCE_PERSISTENT_DIRS", "INSTANCE_PERSISTENT_SEEDED_DIRS"):
        for entry in lists[var]:
            e = entry.rstrip("/")
            if unit == e or unit.startswith(e + "/"):
                return f"{var}:{entry}"
    for entry in lists["INSTANCE_PERSISTENT_FILES"]:
        if unit == entry.rstrip("/"):
            return f"INSTANCE_PERSISTENT_FILES:{entry}"
    return None


def check_slot(unit: str, slot: str, shared_root: str) -> str | None:
    """Deploy-time arm: in a REAL provisioned release, is there durable content
    sitting where the next deploy would discard it?

    The question is "would a deploy LOSE this", so absence is not a failure: a
    path nothing has written yet holds no state to lose, and several list
    entries are legitimately absent until the cabinet first creates them. Only
    real content inside the release worktree is a finding. Returns an error
    string, or None if the path is safe.
    """
    full = os.path.join(slot, unit)
    if not os.path.lexists(full):
        return None                      # nothing there yet — nothing to lose
    real = os.path.realpath(full)
    if real.startswith(os.path.realpath(shared_root) + os.sep):
        return None                      # resolves into shared/ — persisted
    if os.path.islink(full):
        return f"symlinked OUTSIDE the shared tree -> {real}"
    return "lives inside the release worktree — the next deploy discards it"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=".", help="repo root to derive from")
    ap.add_argument("--slot", help="a provisioned release to assert against")
    ap.add_argument("--shared", help="the runtime root's shared/ tree (with --slot)")
    ap.add_argument("--policy", help="override the policy file path")
    args = ap.parse_args()

    repo = os.path.realpath(args.repo)
    policy_path = args.policy or os.path.join(
        repo, "cabinet/config/state-persistence-policy.yml")
    lists = parse_persistence_lists(
        os.path.join(repo, "cabinet/scripts/runtime-provision.sh"))
    wildcard, disposable, known_gap = parse_policy(policy_path)

    if args.slot and not args.shared:
        die("--slot requires --shared (the runtime root's shared/ tree)")

    seen: dict[str, int] = {}
    for pattern, lineno in parse_gitignore(os.path.join(repo, ".gitignore")):
        seen.setdefault(unit_of(pattern), lineno)

    failures: list[tuple[str, int, str]] = []
    counts = {"carried": 0, "wildcard": 0, "disposable": 0}
    gaps: list[tuple[str, str]] = []
    for unit, lineno in sorted(seen.items()):
        if unit in disposable:
            counts["disposable"] += 1
            continue
        if unit in known_gap:
            gaps.append((unit, known_gap[unit]))
            continue
        if unit in wildcard:
            counts["wildcard"] += 1
            continue
        via = covered_by_lists(unit, lists)
        if via is None:
            failures.append((unit, lineno, "on NO persistence list and NO policy entry"))
            continue
        counts["carried"] += 1
        if args.slot:
            err = check_slot(unit, args.slot, args.shared)
            if err:
                failures.append((unit, lineno, f"listed via {via} but {err}"))

    total = len(seen)
    print(f"state-persistence-preflight: {total} durable candidates derived from "
          f".gitignore — {counts['carried']} carried, {counts['wildcard']} "
          f"wildcard-linked, {counts['disposable']} declared disposable, "
          f"{len(failures)} UNACCOUNTED")
    for unit, why in gaps:
        print(f"state-persistence-preflight: KNOWN GAP — {unit}: {why}")
    if not failures:
        print("state-persistence-preflight: OK — no durable path would be lost.")
        return 0
    print("\nstate-persistence-preflight: DEPLOY WOULD LOSE STATE\n", file=sys.stderr)
    for unit, lineno, why in failures:
        print(f"  {unit}   (.gitignore:{lineno})\n      {why}", file=sys.stderr)
    print(f"\n  {len(failures)} path(s) unaccounted for. Either add each to a "
          f"persistence list in\n  cabinet/scripts/runtime-provision.sh, or add a "
          f"reasoned entry to\n  {os.path.relpath(policy_path, repo)}.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
