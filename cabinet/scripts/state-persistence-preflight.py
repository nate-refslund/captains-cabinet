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
  --current <p>  the OUTGOING release. See THE OUTGOING-RELEASE ARM below.

THE OUTGOING-RELEASE ARM (added 2026-07-25 after this checker certified a deploy
that lost 11 of 13 durable paths). The original --slot arm asked "does the NEW
slot's path resolve into shared/?" and treated ABSENCE as safe: "nothing there
yet, nothing to lose". But absence in the new slot is exactly the signature of
the bug — the state is not missing, it is sitting in the OUTGOING release, about
to be stranded there and then rm -rf'd by `prune`. A checker that only ever
looks at the new slot cannot answer its own question. So --current walks the
live release for untracked (i.e. runtime-created) content and fails if any of it
is unreachable from the new slot. That single arm catches all three failures
this checker previously waved through: unlinked directory classes, unseeded
wildcard destinations, and lists that name a path without carrying it.

Exit 0 = no durable path would be lost. Exit 1 = this deploy loses state.
Exit 2 = the checker could not establish the facts (also a blocking failure).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import subprocess
import sys

try:
    import yaml
except ImportError as _exc:  # pragma: no cover - environment-dependent
    # Deploy runs this under /opt/homebrew/bin/python3.12, which is NOT
    # necessarily the interpreter CI installed PyYAML into. Without this guard
    # the ImportError propagated as a bare traceback and cabinet-deploy.sh
    # reported "this release would DISCARD durable state" — a scary, wrong
    # diagnosis for a missing dependency. Say what is actually broken.
    print(
        "state-persistence-preflight: CANNOT VERIFY — PyYAML is not importable "
        f"under {sys.executable} ({_exc}). This is a MISSING DEPENDENCY, not a "
        "state-loss finding: the policy file could not be read, so nothing was "
        "checked either way. Install it (e.g. "
        f"'{sys.executable} -m pip install pyyaml') or point CABINET_PYTHON at "
        "an interpreter that has it, then re-run.",
        file=sys.stderr)
    sys.exit(2)

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


def parse_policy(path: str, deploy_time: bool = False
                 ) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Load the policy file. EVERY entry must carry a non-empty reason.

    `known_gap` is for a path that IS durable but whose fix needs a design
    decision (e.g. the persisted copy would shadow a tracked file). It is
    deliberately narrow: it must also carry an `expires` date, and the check
    FAILS once that date passes, so a deferral cannot quietly become permanent.

    EXPIRY IS BLOCKING IN CI, LOUD AT DEPLOY TIME (`deploy_time=True`). Because
    cabinet-deploy.sh aborts on any non-zero exit, a blocking expiry would make
    every `expires:` date a scheduled hard-stop of the entire deploy path — the
    fleet would stop being able to ship on a calendar date, over a deferral that
    says nothing about whether THIS deploy loses state. Review time is where a
    deferral gets renewed and where blocking actually works, so CI keeps the
    hard failure. At deploy time it prints as EXPIRED and is impossible to miss,
    but it does not brick shipping. An expired gap describes a path that was
    ALREADY not carried yesterday; refusing to deploy does not carry it.
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
                    msg = (f"known_gap: '{entry['path']}' EXPIRED on {expires} — this "
                           f"durable path is still not carried across deploys. Fix it "
                           f"or have the Captain re-date the deferral.")
                    if not deploy_time:
                        problems.append(msg)
                        continue
                    print(f"state-persistence-preflight: EXPIRED DEFERRAL — {msg}",
                          file=sys.stderr)
                    reason = f"{reason} (deferral EXPIRED {expires} — overdue)"
                else:
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


def _tracked_under(root: str, rel: str) -> set[str]:
    """Repo-relative paths git tracks under `rel`, or an empty set."""
    try:
        out = subprocess.run(["git", "-C", root, "ls-files", "-z", "--", rel],
                             capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return set()
    return {p for p in out.stdout.split("\0") if p}


def _reachable_from_slot(relp: str, slot: str, shared_root: str) -> bool:
    """Is this outgoing-release file readable from the NEW release, out of the
    one physical store that survives the deploy?"""
    dest = os.path.join(slot, relp)
    if not os.path.exists(dest):
        return False
    return os.path.realpath(dest).startswith(os.path.realpath(shared_root) + os.sep)


def check_outgoing(unit: str, current: str, slot: str, shared_root: str) -> list[str]:
    """Is there state in the OUTGOING release this deploy would strand?

    THE question. Walks `current/<unit>` for UNTRACKED regular files — untracked
    is what "created at runtime" looks like in a release worktree, since a
    release is a fresh `git worktree` that is never developed in — and returns
    every one that is not reachable from the new slot via shared/.

    A symlink at the unit root is the steady state (a previous provision already
    pointed it into shared/) and is skipped immediately, which is also what keeps
    this cheap: after one correct deploy there is nothing left to walk.
    """
    src = os.path.join(current, unit)
    if os.path.islink(src) or not os.path.exists(src):
        return []
    tracked = _tracked_under(current, unit)
    if os.path.isfile(src):
        return ([] if unit in tracked
                or _reachable_from_slot(unit, slot, shared_root) else [unit])
    stranded: list[str] = []
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames
                       if not os.path.islink(os.path.join(dirpath, d))]
        for name in filenames:
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                continue
            relp = os.path.relpath(full, current)
            if relp in tracked:
                continue            # tracked: the new worktree checks it out
            if not _reachable_from_slot(relp, slot, shared_root):
                stranded.append(relp)
    return sorted(stranded)


def untracked_residue(current: str, slot: str, shared_root: str) -> list[str]:
    """Untracked-AND-UNIGNORED files in the outgoing release.

    These are invisible to the .gitignore derivation by construction, so
    "no durable path would be lost" would overclaim without them — a
    vault/decisions/*.md record was measured lost at exit 0. Reported, not
    failed: nothing gitignores them, so there is no list to add them to and a
    hard failure would leave the operator no remedy. The honest headline plus a
    visible list is the useful outcome.
    """
    try:
        out = subprocess.run(
            ["git", "-C", current, "status", "--porcelain", "--untracked-files=all"],
            capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError):
        return []
    residue = []
    for line in out.stdout.splitlines():
        if not line.startswith("?? "):
            continue
        relp = line[3:].strip().strip('"')
        if not _reachable_from_slot(relp, slot, shared_root):
            residue.append(relp)
    return sorted(residue)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=".", help="repo root to derive from")
    ap.add_argument("--slot", help="a provisioned release to assert against")
    ap.add_argument("--shared", help="the runtime root's shared/ tree (with --slot)")
    ap.add_argument("--current", help="the OUTGOING release (defaults to "
                                      "<shared>/../current when that exists)")
    ap.add_argument("--policy", help="override the policy file path")
    args = ap.parse_args()

    repo = os.path.realpath(args.repo)
    policy_path = args.policy or os.path.join(
        repo, "cabinet/config/state-persistence-policy.yml")
    lists = parse_persistence_lists(
        os.path.join(repo, "cabinet/scripts/runtime-provision.sh"))
    wildcard, disposable, known_gap = parse_policy(policy_path,
                                                  deploy_time=bool(args.slot))

    if args.slot and not args.shared:
        die("--slot requires --shared (the runtime root's shared/ tree)")

    current = args.current
    if args.slot and not current:
        cand = os.path.join(os.path.dirname(os.path.realpath(args.shared)), "current")
        if os.path.exists(cand):
            current = cand
    if current and not os.path.isdir(current):
        die(f"--current {current} is not a directory")

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
        by_wildcard = unit in wildcard
        if by_wildcard:
            counts["wildcard"] += 1
            via = f"wildcard:{unit}"
        else:
            via = covered_by_lists(unit, lists)
            if via is None:
                failures.append((unit, lineno,
                                 "on NO persistence list and NO policy entry"))
                continue
            counts["carried"] += 1
        if args.slot:
            # check_slot is a WHOLE-PATH test: it asks whether <unit> itself
            # resolves into shared/. That is the right question for a list entry
            # (which is symlinked whole) and the WRONG question for a wildcard
            # unit — instance/agents and shared/interfaces are ordinary tracked
            # directories that are carried FILE BY FILE, so the directory itself
            # correctly stays a real directory in the release. Only the per-file
            # arm below has the right granularity for them.
            if not by_wildcard:
                err = check_slot(unit, args.slot, args.shared)
                if err:
                    failures.append((unit, lineno, f"listed via {via} but {err}"))
            # THE arm this checker was missing — see THE OUTGOING-RELEASE ARM in
            # the module docstring. Skipped for disposable/known_gap units above:
            # a known_gap is BY DEFINITION real content in the outgoing release,
            # so running this on it would block every deploy forever over a
            # deferral the Captain already ruled on.
            if current:
                stranded = check_outgoing(unit, current, args.slot, args.shared)
                if stranded:
                    shown = ", ".join(stranded[:5])
                    more = f" (+{len(stranded) - 5} more)" if len(stranded) > 5 else ""
                    failures.append((unit, lineno, (
                        f"listed via {via}, but {len(stranded)} runtime-created "
                        f"file(s) in the OUTGOING release are unreachable from "
                        f"this slot and would be stranded there for `prune` to "
                        f"delete: {shown}{more}")))

    total = len(seen)
    print(f"state-persistence-preflight: {total} durable candidates derived from "
          f".gitignore — {counts['carried']} carried, {counts['wildcard']} "
          f"wildcard-linked, {counts['disposable']} declared disposable, "
          f"{len(failures)} UNACCOUNTED")
    for unit, why in gaps:
        print(f"state-persistence-preflight: KNOWN GAP — {unit}: {why}")

    residue: list[str] = []
    if args.slot and current:
        residue = untracked_residue(current, args.slot, args.shared)
        if residue:
            print(f"state-persistence-preflight: {len(residue)} untracked-and-"
                  f"UNIGNORED file(s) in the outgoing release are outside this "
                  f"check's derived set and would not survive this deploy "
                  f"(reported, not blocking — nothing gitignores them, so there "
                  f"is no persistence list to add them to):")
            for relp in residue[:20]:
                print(f"    {relp}")
            if len(residue) > 20:
                print(f"    ... and {len(residue) - 20} more")

    if not failures:
        # SCOPE, stated honestly. The derivation is .gitignore, so this can only
        # certify .gitignore-derived paths. The bare old headline — "no durable
        # path would be lost." — overclaimed exactly there: a vault/decisions
        # record that is untracked AND unignored was measured lost under it.
        if residue:
            print(f"state-persistence-preflight: OK — no durable path would be "
                  f"lost AMONG THE PATHS THIS CHECK DERIVES; the {len(residue)} "
                  f"untracked-and-unignored file(s) listed above are outside "
                  f"that derivation and WOULD be lost.")
        else:
            scanned = (" and the outgoing release's untracked content, scanned "
                       "and clean" if current and args.slot else "")
            print(f"state-persistence-preflight: OK — no durable path would be "
                  f"lost. (Scope: paths derived from .gitignore{scanned}.)")
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
