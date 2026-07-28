#!/usr/bin/env python3
"""Git-aware ratchet: the architecture baseline MEMBER SETS may never net-grow.

WHAT THIS CLOSES — the one path the 2026-07-27 expansion-gate landing NAMED
rather than relabelled as covered, in the baseline file's own header and in
cognitive-architecture-census.py's docstring:

    a baseline line added in the SAME commit as the file it names still empties
    the surplus, and the bijection cannot tell the difference.

Reproduced by execution against master 6ec81460 before this script existed: a
net-new production module + one line in
``cabinet/config/architecture-baseline-sets.yml`` + a visible ``maximum`` raise
returned ok=True at 248/248 with zero failures and no expansion row. The
purchase is invisible to the census BY CONSTRUCTION — the census is gitless (it
must run in a clean hatch with no history, its own docstring) so it cannot ask
what the baseline looked like before this commit. Only a git-aware check can,
which is why this is a separate script wired into CI rather than a census arm.

THE RULE, and why it is shaped the way it is. A baseline that is a SNAPSHOT of
a pinned tree has no legitimate reason to GROW: a genuinely new member is paid
for with an adjudicated ``expansions:`` row plus a visible ``maximum`` raise,
and it stays in the surplus — never in the baseline. But a ratchet that refused
every addition would break the one edit the baseline's header calls CORRECT: a
RENAME is a PAIRED edit landing in the same commit as the tree change (remove
the old member, add the new one), and blocking it with no green path is how
routine baseline edits get normalised, which is the habit this whole gate rests
on not forming. So the ratchet distinguishes them, and it does so from the TREE
and the DIFF — never from a hand-maintained list of blessed renames, because a
fourth hand-maintained list is where this program's last several drift bugs
came from.

Three rules, per class, over merge-base(base, head) → head:

  A. NET NON-GROWTH.  ``len(added) <= len(credited removals)``, where a removal
     is CREDITED only when the tree at HEAD no longer carries that member.
     The qualifier is load-bearing, not decoration: without it the ratchet
     funds itself. Moving a baseline member onto an expansion row deletes its
     baseline line while the member stays in the tree, and that vacated line
     would pay for an unadjudicated addition — a purchase channel opened by the
     ratchet, not closed by it. An uncredited removal is not an error here (the
     census reds it independently, as an unregistered surplus member, unless it
     was genuinely adjudicated); it simply buys nothing.

  B. AN ADDED MEMBER MUST EXIST at HEAD, in that class's observed member set.
     The census carries this too ("baseline names a member the tree does not
     carry") and it is restated here rather than inherited, because rule C
     below classifies an added member by asking whether it is a tracked FILE:
     a phantom path would answer "not a file", fall through to the symbol path,
     and be gated by rule A alone. Stated once, in two places, on purpose.

  C. A PATH ADDITION MUST BE A DETECTED RENAME.  If an added member is a
     tracked file at HEAD, git's own rename detection over the same diff must
     pair it with a credited removal from the same class. This is what stops
     the SWAP — delete one real module, add a different unadjudicated one, net
     count unchanged — which rules A and B alone let through. Similarity, not a
     list, decides; the threshold is stated below.

WHAT IS NOT CLOSED, named rather than relabelled as covered. Rule C reaches
only members that ARE repo paths (today: framework_production_modules). For the
symbol-shaped classes — central_event_types, central_action_types,
services_total, services_enabled, duplicate_event_writer_sinks — a rename is an
edit INSIDE a file, so git has no rename to detect and no similarity to
measure, and a same-commit swap (delete one member, add another, net zero) is
indistinguishable from a rename. It stays open, it costs deleting a live event
type / action type / service row, and it is caught by reading the diff. Closing
it would need a structural row-identity diff of each declaring file, which is a
fourth derivation of the same data and was judged not worth its drift risk at
this landing.

REMEDIES, so this friction never lacks a stated green path:
  * genuinely new member → do NOT add a baseline line. Register an
    ``expansions:`` row and raise ``maximum``. That is the sanctioned purchase
    and it is what the surplus is for.
  * pure rename or move → paired baseline edit in the same commit. Green.
  * rename PLUS a rewrite big enough that git no longer sees a rename → the new
    path is, on the evidence, a new module: drop the old baseline line and
    register the new path as an expansion. Also green, and more honest.
  * a brand-new bijection class → reds here, by design: its baseline arrives as
    a bulk addition. That landing also has to widen BIJECTION_CLASSES in the
    census (pinned verbatim by its own test), so it is already a deliberate,
    reviewed act; it is not smuggled through this ratchet.

SHALLOW CHECKOUTS ARE REFUSED, NEVER SKIPPED. ``actions/checkout`` is shallow
by default and git's merge-base is not trustworthy past a shallow boundary, so
a SHA-diff ratchet that shrugs at a shallow clone is a sensor that reports
green in exactly the environment CI runs it in. This one errors (exit 2) and
says what to change.

Read-only: it never writes to the repository under test, and it reads COMMITTED
bytes at both ends (``git show`` / ``git archive``), never the working tree —
a working-tree pass on a committed-tree gate proves nothing.

Provenance: closes the residual named in the 2026-07-27 two-model expansion-gate
adjudication, per the 2026-07-07 full-autonomy grant.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

import yaml


BASELINE_REL = "cabinet/config/architecture-baseline-sets.yml"
CENSUS_REL = "cabinet/scripts/cognitive-architecture-census.py"
REPORT_SCHEMA_VERSION = "architecture-baseline-ratchet/v1"
#: git's rename-detection threshold for rule C. Deliberately GENEROUS (git's
#: own default is 50%): a false "not a rename" is a red on honest work, and the
#: only thing a low threshold lets through is an addition that is 25%+ the same
#: file as something deleted in the same diff — which is a rename by any
#: reading. The strictness that matters lives in rules A and B.
RENAME_SIMILARITY = "25%"


class RatchetError(RuntimeError):
    """The ratchet could not measure — never a synonym for "no findings"."""


def _git(root: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if check and proc.returncode != 0:
        raise RatchetError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def _assert_measurable(root: Path) -> None:
    """Fail closed on the two environments that would silently mis-measure."""

    if not (root / ".git").exists() and not _git(
        root, "rev-parse", "--git-dir", check=False
    ).strip():
        raise RatchetError(
            f"{root} is not a git work tree; this ratchet compares two commits "
            "and has nothing to compare without one"
        )
    if _git(root, "rev-parse", "--is-shallow-repository").strip() == "true":
        raise RatchetError(
            "shallow checkout: git's merge-base is not trustworthy past a "
            "shallow boundary, so measuring here would compare against the "
            "wrong base. Give the job `fetch-depth: 0` (actions/checkout) or "
            "run `git fetch --unshallow`. Refusing rather than guessing."
        )


def _commit(root: Path, ref: str) -> str:
    resolved = _git(
        root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False
    ).strip()
    if not resolved:
        raise RatchetError(
            f"cannot resolve {ref!r} to a commit — pass --base explicitly, or "
            "fetch the branch it names"
        )
    return resolved


def _baseline_classes_at(root: Path, ref: str) -> dict[str, set[str]] | None:
    """The baseline member sets as COMMITTED at `ref`; None when the file is absent."""

    proc = subprocess.run(
        ["git", "-C", str(root), "show", f"{ref}:{BASELINE_REL}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    document = yaml.safe_load(proc.stdout)
    if not isinstance(document, dict):
        raise RatchetError(f"{BASELINE_REL} at {ref} is not a mapping")
    classes = document.get("classes")
    if not isinstance(classes, dict):
        raise RatchetError(f"{BASELINE_REL} at {ref} has no classes mapping")
    resolved: dict[str, set[str]] = {}
    for name, members in classes.items():
        if not isinstance(members, list) or not all(
            isinstance(member, str) for member in members
        ):
            raise RatchetError(
                f"{BASELINE_REL} at {ref}: class {name} must be a list of strings"
            )
        resolved[str(name)] = set(members)
    return resolved


def _tracked_files(root: Path, ref: str) -> frozenset[str]:
    return frozenset(
        line for line in _git(root, "ls-tree", "-r", "--name-only", ref).splitlines() if line
    )


def _detected_renames(root: Path, base: str, head: str) -> dict[str, str]:
    """old path -> new path, as GIT scores it over the same diff the rules read."""

    output = _git(
        root,
        "diff",
        "--name-status",
        f"-M{RENAME_SIMILARITY}",
        "-l0",
        "--diff-filter=R",
        base,
        head,
    )
    pairs: dict[str, str] = {}
    for line in output.splitlines():
        fields = line.split("\t")
        if len(fields) == 3 and fields[0].startswith("R"):
            pairs[fields[1]] = fields[2]
    return pairs


def observed_member_sets(root: Path, ref: str) -> dict[str, frozenset[str]]:
    """Ask the CENSUS what the tree at `ref` holds — never a second derivation.

    The member sets are the one input both halves of this gate share, so they
    are read from the same code that enforces the bijection, running on the
    COMMITTED tree at `ref` (extracted with `git archive`, so an unrelated dirty
    working tree can neither hide a member nor invent one). Re-deriving them
    here would be a second copy of six derivations that must agree forever.
    """

    with tempfile.TemporaryDirectory(prefix="baseline-set-ratchet-") as scratch:
        tree = Path(scratch) / "head"
        tree.mkdir()
        archive = subprocess.run(
            ["git", "-C", str(root), "archive", ref],
            capture_output=True,
            check=False,
        )
        if archive.returncode != 0:
            raise RatchetError(
                f"git archive {ref} failed: {archive.stderr.decode(errors='replace').strip()}"
            )
        extract = subprocess.run(
            ["tar", "-x", "-C", str(tree)],
            input=archive.stdout,
            capture_output=True,
            check=False,
        )
        if extract.returncode != 0:
            raise RatchetError(
                f"extracting {ref} failed: {extract.stderr.decode(errors='replace').strip()}"
            )
        census = tree / CENSUS_REL
        if not census.is_file():
            raise RatchetError(f"{CENSUS_REL} is absent at {ref}")
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        proc = subprocess.run(
            [sys.executable, str(census), "--root", str(tree), "--json"],
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            raise RatchetError(
                f"the census at {ref} could not report member sets: "
                f"{proc.stderr.strip() or 'no output'}"
            )
        report = json.loads(proc.stdout)
    members = report.get("member_sets")
    if not isinstance(members, dict) or not members:
        raise RatchetError(
            f"the census at {ref} reports no member_sets — this ratchet needs "
            "them and refuses to guess"
        )
    return {name: frozenset(values) for name, values in members.items()}


def evaluate(root: Path, base_ref: str, head_ref: str = "HEAD") -> dict[str, Any]:
    _assert_measurable(root)
    head = _commit(root, head_ref)
    base = _commit(root, base_ref)
    merge_base = _git(root, "merge-base", base, head).strip()
    if not merge_base:
        raise RatchetError(f"{base_ref} and {head_ref} share no history")

    head_classes = _baseline_classes_at(root, head)
    if head_classes is None:
        raise RatchetError(f"{BASELINE_REL} is absent at {head_ref}")
    base_classes = _baseline_classes_at(root, merge_base)
    baseline_is_new = base_classes is None
    if base_classes is None:
        base_classes = {}

    observed = observed_member_sets(root, head)
    tracked = _tracked_files(root, head)
    renames = _detected_renames(root, merge_base, head)

    failures: list[dict[str, Any]] = []
    classes: dict[str, dict[str, list[str]]] = {}
    for name in sorted(set(head_classes) | set(base_classes)):
        after = head_classes.get(name, set())
        before = base_classes.get(name, set())
        added = after - before
        removed = before - after
        present = observed.get(name, frozenset())
        credited = {member for member in removed if member not in present}
        classes[name] = {
            "added": sorted(added),
            "removed": sorted(removed),
            "credited_removals": sorted(credited),
            "uncredited_removals": sorted(removed - credited),
        }

        # A — net non-growth, credited removals only.
        if len(added) > len(credited):
            failures.append(
                {
                    "budget": name,
                    "reason": "baseline set grew",
                    "added": len(added),
                    "credited_removals": len(credited),
                }
            )
        for member in sorted(added):
            # B — an added name the tree does not carry.
            if member not in present:
                failures.append(
                    {
                        "budget": name,
                        "member": member,
                        "reason": "baseline adds a member the tree does not carry",
                    }
                )
                continue
            # C — a path addition that git does not score as a rename of a
            # credited removal in the same class.
            if member in tracked:
                sources = {
                    old for old, new in renames.items() if new == member and old in credited
                }
                if not sources:
                    failures.append(
                        {
                            "budget": name,
                            "member": member,
                            "reason": "baseline adds a path that is not a detected rename",
                        }
                    )

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "base": base,
        "head": head,
        "merge_base": merge_base,
        "baseline_absent_at_base": baseline_is_new,
        "rename_similarity": RENAME_SIMILARITY,
        "classes": classes,
        "failures": failures,
        "ok": not failures,
    }


def _human_report(report: dict[str, Any]) -> str:
    lines = [
        f"architecture baseline ratchet: {'PASS' if report['ok'] else 'FAIL'}",
        f"  merge-base {report['merge_base'][:12]} -> head {report['head'][:12]}",
    ]
    for name, delta in sorted(report["classes"].items()):
        if delta["added"] or delta["removed"]:
            lines.append(
                f"  {name}: +{len(delta['added'])} -{len(delta['removed'])} "
                f"({len(delta['credited_removals'])} credited)"
            )
    for failure in report["failures"]:
        if "member" in failure:
            lines.append(
                f"  BLOCK {failure['budget']}: {failure['reason']} [{failure['member']}]"
            )
        else:
            lines.append(
                f"  BLOCK {failure['budget']}: {failure['reason']} "
                f"(+{failure['added']} vs {failure['credited_removals']} credited removals)"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument(
        "--base",
        default="origin/master",
        help="the ref the baseline is measured against (merge-base with --head)",
    )
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--check", action="store_true", help="exit non-zero on a breach")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)
    try:
        report = evaluate(args.root, args.base, args.head)
    except (OSError, RatchetError, yaml.YAMLError, json.JSONDecodeError) as exc:
        print(f"architecture baseline ratchet error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else _human_report(report))
    return 1 if args.check and not report["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
