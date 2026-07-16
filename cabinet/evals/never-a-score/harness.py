#!/usr/bin/env python3
"""Never-a-score eval harness — EVAL-025 (evidence aggregates are never scores).

Mechanical PASS/FAIL law for the NEVER-A-SCORE golden eval (eval body:
memory/golden-evals/eval-025-never-a-score.md — that directory is germline,
schg-locked on the live checkout, so the runnable half lives here,
non-germline, wired into cabinet/scripts/run-golden-evals.sh as section
EVAL-025-NEVER-A-SCORE).

The law it enforces, from the whole-cabinet evidence design (§2.5,
2026-07-16), binding per the Phase-1 laws wave:

  Evidence-derived aggregates are monitoring metrics and kill criteria
  ONLY — never officer-visible scores, never inputs to generation or
  selection. A future consumer that surfaces an evidence metric to
  officers fails the suite.

Deterministic by design — no LLM, no network, no Redis, no framework
imports, and it never reads instance/evidence/ or any signing material.
The only subprocess is a fixed-argv, read-only `git ls-files -z` used to
enumerate tracked files (pruned os.walk fallback when git is unavailable).
Scanned file contents are inert data: substring and AST matching only,
never executed. All checks are static:

  C1  scalar-consumer scan     every tracked file mentioning the report-only
                               golden-eval-scalar series (or its emit lib) is
                               in the pinned fixture allowlist. A new reader
                               = a new consumer of an evidence-derived
                               aggregate = FAIL until governance-reviewed.
  C2  projection key law       AST over framework/evidence/recorder.py:
                               cabinet_projection's allowed_detail set may
                               not contain score/aggregate/cost/fuel-shaped
                               keys (token deny-list; pinned exemptions).
  C3  projection shape pin     the projection's top-level keys and
                               per-record keys equal the pinned sets — no
                               "scores"/"stats" section can appear without
                               deliberately updating this eval's fixture in
                               the same governance-reviewed change; the
                               per-record trust value stays the literal
                               "untrusted_observation".
  C4  doctrine strings         the untrusted-observations banner, the trust
                               const in schema+verifier, the raw-read deny in
                               base-safety.yml, the writer-side REPORT-ONLY
                               doctrine, and the series' gitignore line all
                               stay present.
  C5  doorway character        cabinet/scripts/evidence-read.sh still invokes
                               only the `project` subcommand of
                               framework.evidence and names no raw verb.
  C6  deny-tokenizer vectors   the classifier itself is pinned by labeled
                               vectors (denied + allowed), candor-style.

Fail-closed: a missing/malformed fixture, an unreadable pinned file, or an
unrecognizable AST shape is a FAIL, never a skip. Honest limitation: C1 is
a token scan over tracked file contents — a consumer that constructs the
series path dynamically evades the grammar; label such a consumer into the
allowlist review the moment it is found (and treat the evasion itself as
the violation). C2/C3 pin the ONE officer evidence read surface; aggregates
computed elsewhere are covered only insofar as they reach that surface or
the scalar series.

SECURITY: paths are resolved relative to this file; --repo-root/--fixtures
are operator-supplied, read-only, and never interpolated into a shell.

Usage:
  python3.12 harness.py --self-test [--fixtures DIR] [--repo-root DIR]
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_FIXTURES_DIR = _HERE / "fixtures"
_REPO_ROOT = _HERE.parents[2]

PASS = "PASS"
FAIL = "FAIL"

# Key tokens that make a projection detail key score/aggregate/cost-shaped.
# Split on _ - . before matching; exemptions are exact-key and pinned in the
# fixture with a written justification (governance-reviewed data, not code).
DENY_TOKENS = frozenset({
    "score", "scores", "scored", "scoring",
    "grade", "grades", "graded", "grading",
    "rank", "ranks", "ranked", "ranking", "rankings",
    "rating", "ratings", "rated",
    "percentile", "percentiles", "leaderboard", "leaderboards",
    "kpi", "kpis", "elo",
    "metric", "metrics", "aggregate", "aggregates", "aggregated",
    "rate", "rates", "avg", "average", "averages", "mean", "median",
    "quantile",
    "cost", "costs", "usd", "spend", "spent", "spending",
    "budget", "budgets", "token", "tokens",
    "fuel", "graduation", "graduations", "autonomy",
})

# Directories pruned in the (git-less) walk fallback only. `git ls-files`
# is the primary enumerator and already excludes untracked runtime data.
WALK_PRUNE = frozenset({
    ".git", "node_modules", "__pycache__", ".next", ".venv", "venv",
    "instance",
})


class HarnessError(RuntimeError):
    """A fail-closed harness failure (broken fixture, unrecognizable AST)."""


def is_score_shaped(key: str) -> bool:
    """True when a detail key tokenizes into any denied score/aggregate
    token. Pure and deterministic — pinned by the fixture deny_vectors."""
    tokens = [t for t in re.split(r"[_\-.]+", str(key).lower()) if t]
    return any(t in DENY_TOKENS for t in tokens)


def load_fixture(fixtures_dir: Path) -> dict:
    """Load and shape-check the law-pins fixture. Fail-closed: missing or
    malformed fixture data is an error, never an empty default."""
    path = Path(fixtures_dir) / "law-pins.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HarnessError(f"fixture unreadable/malformed: {path}: {exc}")
    if not isinstance(doc, dict):
        raise HarnessError(f"fixture is not an object: {path}")
    required = (
        "scalar_tokens", "scalar_reference_allowlist", "projection",
        "required_strings", "doorway", "deny_vectors",
    )
    missing = [k for k in required if k not in doc]
    if missing:
        raise HarnessError(f"fixture missing keys {missing}: {path}")
    if not doc["scalar_tokens"] or not isinstance(doc["scalar_tokens"], list):
        raise HarnessError("fixture scalar_tokens must be a non-empty list")
    allow = doc["scalar_reference_allowlist"]
    if not isinstance(allow, list) or not all(
            isinstance(e, dict) and e.get("path") and e.get("why")
            for e in allow):
        raise HarnessError(
            "fixture scalar_reference_allowlist entries need path + why")
    return doc


def tracked_files(repo_root: Path) -> list[str]:
    """Repo-relative paths of files to scan. Primary: `git ls-files -z`
    (fixed argv, read-only). Fallback: pruned os.walk. Empty result is a
    failure upstream (a repo with zero files is not this repo)."""
    try:
        proc = subprocess.run(  # noqa: S603 — fixed argv, no shell
            ["git", "ls-files", "-z"],
            cwd=str(repo_root), capture_output=True, timeout=60,
        )
        if proc.returncode == 0 and proc.stdout:
            return [p for p in proc.stdout.decode("utf-8", "replace").split("\0") if p]
    except (OSError, subprocess.TimeoutExpired):
        pass
    found: list[str] = []
    for base, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in WALK_PRUNE]
        for name in files:
            rel = os.path.relpath(os.path.join(base, name), repo_root)
            # Runtime jsonl exhaust is untracked data, not code.
            if rel.startswith("shared/interfaces/") and rel.endswith(".jsonl"):
                continue
            found.append(rel)
    return sorted(found)


def scan_scalar_references(
    repo_root: Path, tokens: list[str], allowlist: set[str],
) -> tuple[list[str], list[str]]:
    """Return (hits, violations): tracked files whose CONTENT mentions any
    scalar token, and the subset not in the allowlist. Case-insensitive;
    binary files are skipped (the tokens are ASCII path/function names)."""
    needles = [t.lower().encode("utf-8") for t in tokens]
    hits: list[str] = []
    for rel in tracked_files(repo_root):
        path = repo_root / rel
        if not path.is_file() or path.is_symlink():
            continue
        try:
            blob = path.read_bytes()
        except OSError:
            raise HarnessError(f"tracked file unreadable during scan: {rel}")
        if b"\0" in blob[:8192]:
            continue
        low = blob.lower()
        if any(n in low for n in needles):
            hits.append(rel)
    violations = sorted(set(hits) - set(allowlist))
    return sorted(hits), violations


def _projection_fn(recorder_path: Path) -> ast.FunctionDef:
    try:
        tree = ast.parse(recorder_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        raise HarnessError(f"cannot parse {recorder_path}: {exc}")
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "cabinet_projection":
            # Stash the module tree so extract_allowed_detail can resolve a
            # module-level allow-list constant without re-reading the file.
            node.cabinet_module_tree = tree  # type: ignore[attr-defined]
            return node
    raise HarnessError(
        "cabinet_projection not found in recorder.py — the officer "
        "projection moved; update this eval deliberately")


def _set_literal_keys(value: ast.expr, where: str) -> list[str]:
    """String members of a set literal, or a frozenset(...) call wrapping
    one. Fail-closed on any other shape or non-string member."""
    if (isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "frozenset"
            and len(value.args) == 1
            and not value.keywords):
        value = value.args[0]
    if not isinstance(value, ast.Set):
        raise HarnessError(f"{where} is no longer a set literal")
    keys: list[str] = []
    for elt in value.elts:
        if not (isinstance(elt, ast.Constant) and isinstance(elt.value, str)):
            raise HarnessError(
                f"{where} contains a non-string-literal "
                "member — the allow-list must stay reviewable")
        keys.append(elt.value)
    if not keys:
        raise HarnessError(f"{where} is empty")
    return keys


def _resolve_module_constant(fn: ast.FunctionDef, name: str) -> list[str]:
    """Resolve `name` to a module-level set/frozenset literal (exactly one
    level of indirection; the module constant must itself be literal)."""
    tree = getattr(fn, "cabinet_module_tree", None)
    if not isinstance(tree, ast.Module):
        raise HarnessError(
            "allowed_detail references a name but the module tree is "
            "unavailable — extract via _projection_fn")
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return _set_literal_keys(node.value, name)
    raise HarnessError(
        f"allowed_detail references {name} but no module-level literal "
        "assignment of that name exists")


def extract_allowed_detail(fn: ast.FunctionDef) -> list[str]:
    """The allowed_detail set literal, as strings. Accepts either an inline
    set literal or a reference to ONE module-level set/frozenset literal
    constant (the shared single-source-of-truth shape). Fail-closed on any
    non-literal member or a missing/reshaped assignment."""
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "allowed_detail":
                    if isinstance(node.value, ast.Name):
                        return _resolve_module_constant(fn, node.value.id)
                    return _set_literal_keys(node.value, "allowed_detail")
    raise HarnessError("allowed_detail assignment not found in cabinet_projection")


def _literal_dict_keys(node: ast.Dict, where: str) -> list[str]:
    keys: list[str] = []
    for key in node.keys:
        if key is None or not (isinstance(key, ast.Constant)
                               and isinstance(key.value, str)):
            raise HarnessError(
                f"{where} has a non-literal or unpacked key — the projection "
                "shape must stay statically reviewable")
        keys.append(key.value)
    return keys


def extract_projection_shape(fn: ast.FunctionDef) -> tuple[list[str], list[str], str]:
    """(top_level_keys, record_keys, record_trust_value) from the
    projection's single dict return and its records.append({...}) call."""
    returns = [n for n in ast.walk(fn)
               if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict)]
    if len(returns) != 1:
        raise HarnessError(
            f"expected exactly one dict-literal return in cabinet_projection, "
            f"found {len(returns)}")
    top_level = _literal_dict_keys(returns[0].value, "projection return dict")
    record_dicts = [
        n.args[0] for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "append" and n.args
        and isinstance(n.args[0], ast.Dict)
    ]
    if len(record_dicts) != 1:
        raise HarnessError(
            f"expected exactly one records.append(dict-literal) in "
            f"cabinet_projection, found {len(record_dicts)}")
    record_keys = _literal_dict_keys(record_dicts[0], "projection record dict")
    trust_value = ""
    for key, value in zip(record_dicts[0].keys, record_dicts[0].values):
        if isinstance(key, ast.Constant) and key.value == "trust":
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                trust_value = value.value
            else:
                raise HarnessError(
                    "projection record trust is no longer a string literal")
    return top_level, record_keys, trust_value


def run_self_test(fixtures_dir: Path, repo_root: Path) -> int:
    failures: list[str] = []
    checks = 0

    def ok(name: str, note: str) -> None:
        print(f"  ok   {name}: {note}")

    def bad(name: str, note: str) -> None:
        failures.append(f"{name}: {note}")
        print(f"  VIOLATION {name}: {note}", file=sys.stderr)

    try:
        fixture = load_fixture(fixtures_dir)
    except HarnessError as exc:
        print(f"NEVER-A-SCORE-EVAL: fixture load failed — {exc}", file=sys.stderr)
        return 1

    repo_root = Path(repo_root).resolve()
    if not repo_root.is_dir():
        print(f"NEVER-A-SCORE-EVAL: repo root missing: {repo_root}", file=sys.stderr)
        return 1

    # C6 first: if the classifier itself is broken, nothing downstream holds.
    checks += 1
    vectors = fixture["deny_vectors"]
    misses = [v for v in vectors.get("denied", []) if not is_score_shaped(v)]
    misses += [f"!{v}" for v in vectors.get("allowed", []) if is_score_shaped(v)]
    if not vectors.get("denied") or not vectors.get("allowed"):
        bad("deny-vectors", "fixture must carry both denied and allowed vectors")
    elif misses:
        bad("deny-vectors", f"classifier disagrees with labels: {misses}")
    else:
        ok("deny-vectors",
           f"{len(vectors['denied'])} denied + {len(vectors['allowed'])} "
           "allowed vectors classify as labeled")

    # C2 + C3: the officer projection (the ONE evidence read surface).
    recorder_path = repo_root / str(fixture["projection"].get(
        "file", "framework/evidence/recorder.py"))
    try:
        fn = _projection_fn(recorder_path)
        allowed_detail = extract_allowed_detail(fn)
        top_level, record_keys, trust_value = extract_projection_shape(fn)
    except HarnessError as exc:
        checks += 1
        bad("projection-ast", str(exc))
        allowed_detail, top_level, record_keys, trust_value = [], [], [], ""

    if allowed_detail:
        checks += 1
        exemptions = fixture["projection"].get("detail_key_exemptions") or {}
        offenders = [k for k in allowed_detail
                     if is_score_shaped(k) and k not in exemptions]
        if offenders:
            bad("projection-detail-keys",
                f"score/aggregate-shaped keys in the officer projection "
                f"allow-list: {sorted(offenders)} — evidence metrics are "
                "never officer-visible scores (never-a-score law)")
        else:
            exempt_used = sorted(k for k in allowed_detail if k in exemptions)
            ok("projection-detail-keys",
               f"{len(allowed_detail)} allow-listed keys carry no "
               f"score/aggregate shape (exemptions in use: {exempt_used})")

        checks += 1
        want_top = set(fixture["projection"].get("top_level_keys") or [])
        want_rec = set(fixture["projection"].get("record_keys") or [])
        if not want_top or not want_rec:
            bad("projection-shape", "fixture shape pins are empty")
        elif set(top_level) != want_top or set(record_keys) != want_rec:
            bad("projection-shape",
                f"projection shape drifted: top-level {sorted(set(top_level) ^ want_top)} "
                f"record {sorted(set(record_keys) ^ want_rec)} — adding any "
                "aggregate/score section is governance-changing; update the "
                "fixture only inside a reviewed governance change")
        elif trust_value != "untrusted_observation":
            bad("projection-shape",
                f"record trust literal is {trust_value!r}, expected "
                "'untrusted_observation'")
        else:
            ok("projection-shape",
               f"top-level {sorted(want_top)} + {len(want_rec)} record keys "
               "pinned; trust stays 'untrusted_observation'")

    # C4: doctrine strings on the pinned governance surfaces.
    for pin in fixture["required_strings"]:
        checks += 1
        rel = str(pin.get("file") or "")
        target = repo_root / rel
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            bad("doctrine-string", f"pinned file unreadable: {rel}")
            continue
        gone = [s for s in (pin.get("must_contain") or []) if s not in text]
        if gone:
            bad("doctrine-string", f"{rel} lost pinned text {gone} ({pin.get('why')})")
        else:
            ok("doctrine-string", f"{rel}: {len(pin.get('must_contain') or [])} pins hold")

    # C5: officer doorway character.
    checks += 1
    doorway = fixture["doorway"]
    doorway_rel = str(doorway.get("file") or "")
    try:
        doorway_text = (repo_root / doorway_rel).read_text(encoding="utf-8")
    except OSError:
        bad("doorway", f"officer doorway unreadable: {doorway_rel}")
    else:
        missing = [s for s in (doorway.get("must_contain") or [])
                   if s not in doorway_text]
        present = [s for s in (doorway.get("forbidden_substrings") or [])
                   if s in doorway_text]
        if missing or present:
            bad("doorway",
                f"{doorway_rel} drifted (missing={missing} forbidden-present={present}) "
                "— the only officer evidence read stays the redacted projection")
        else:
            ok("doorway", f"{doorway_rel} still projects and names no raw verb")

    # C1: unsanctioned consumers of the report-only scalar series.
    checks += 1
    allowlist = {str(e["path"]) for e in fixture["scalar_reference_allowlist"]}
    stale = sorted(p for p in allowlist if not (repo_root / p).is_file())
    try:
        hits, violations = scan_scalar_references(
            repo_root, [str(t) for t in fixture["scalar_tokens"]], allowlist)
    except HarnessError as exc:
        bad("scalar-consumers", str(exc))
    else:
        if violations:
            bad("scalar-consumers",
                f"unsanctioned reference(s) to the report-only golden-eval "
                f"scalar series: {violations} — evidence-derived aggregates "
                "are monitoring/kill-criteria only; a new consumer needs a "
                "governance-reviewed allowlist entry stating why it is not "
                "a score or a generation/selection input")
        elif stale:
            bad("scalar-consumers",
                f"stale allowlist entries (file gone/renamed): {stale} — "
                "keep the fixture honest in the same change")
        elif not hits:
            bad("scalar-consumers",
                "zero scalar references found — the writer itself vanished; "
                "the series (and this eval's teeth) have been unplugged")
        else:
            ok("scalar-consumers",
               f"{len(hits)} sanctioned reference(s), 0 unsanctioned")

    if failures:
        print(f"NEVER-A-SCORE-EVAL: {len(failures)} violation(s) across "
              f"{checks} checks", file=sys.stderr)
        return 1
    print(f"NEVER-A-SCORE-EVAL: {checks}/{checks} checks green — no evidence "
          "metric is officer-visible or score-consumed")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--self-test", action="store_true",
                    help="run all law pins; exit 0 iff every check holds")
    ap.add_argument("--fixtures", default=str(_FIXTURES_DIR),
                    help="fixtures directory (default: beside this file)")
    ap.add_argument("--repo-root", default=str(_REPO_ROOT),
                    help="repository root to scan (default: this checkout)")
    args = ap.parse_args(argv)
    if args.self_test:
        return run_self_test(Path(args.fixtures), Path(args.repo_root))
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
