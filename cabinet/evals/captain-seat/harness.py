#!/usr/bin/env python3
"""Captain-seat eval harness — EVAL-027 (the retro's Part 1c).

Mechanical PASS/FAIL law for the CAPTAIN-SEAT REVIEW golden eval (eval body:
memory/golden-evals/eval-027-captain-seat-review.md — staged via
docs/proposals/germline-amendment-captain-seat-eval-2026-07-26.md; that
directory is schg-locked on the live checkout, so the runnable half lives
here, non-germline, wired into cabinet/scripts/run-golden-evals.sh as section
EVAL-027-CAPTAIN-SEAT).

The law it enforces (Captain ruling 2026-07-26, recorded as an officer-note in
the decisions ledger): the retro gains a pass run FROM THE CAPTAIN'S SEAT — the
reviewer takes his place and reports what the window COST him. Two halves must
hold or the pass is worthless:

  * the deterministic evidence half (cabinet/scripts/meta-cognition/
    captain-seat-pack.sh) must COUNT repetition it is shown, and must print an
    absent store as a measured ABSENCE rather than inventing content;
  * the judgment half's contract (Part 1c of memory/skills/cross-officer-retro.md)
    must keep its load-bearing clauses — above all that a finding cites a cost
    PAID IN-WINDOW, and that a quiet window yields exactly NO FINDINGS.

Three arms, all deterministic:

  A1  repetition   the pack, run against fixtures/repetition/ (an
                   action-lessons store carrying the SAME subject twice),
                   reports that subject with count 2 and the pinned
                   per-taxonomy counts.
  A2  healthy      the pack, run against fixtures/healthy/ (every subject
                   distinct, the other stores absent), reports repetition
                   "(none)" AND prints every absent store as an ABSENT line.
                   This is the degenerate end: a quiet window must stay quiet
                   and honest, never fabricate.
  A3  contract-pin every pinned Part 1c clause is still present verbatim in
                   memory/skills/cross-officer-retro.md — the skill text is
                   the only thing standing between this pass and a
                   friction-invention machine, so silent dilution is a FAIL.

Plus A4: both fixture trees are byte-IDENTICAL after the runs (the pack claims
read-only; a claim nobody tried to defeat is an assumption, not a control).

SAFETY — this eval can never touch Redis, the network, or any live store:

  * every pack run gets CAPTAIN_SEAT_ROOT pointed at a committed fixture tree,
    so no live path is ever read;
  * the pack's channel-health section shells out to `redis-cli`. The runs here
    execute with a scratch directory PREPENDED to PATH holding a `redis-cli`
    that exits non-zero without connecting to anything, so the probe resolves
    to the pack's own "redis: unavailable" branch. No assertion in this
    harness depends on that line — redis being genuinely absent (CI, a bare
    box) is equally fine;
  * the subprocess environment is rebuilt from scratch (PATH, HOME=scratch,
    LC_ALL) — no inherited REDIS_*/CABINET_* variable can reach the pack;
  * no network call exists anywhere in the pack or here.

Honest limitations, stated rather than hidden:
  * the same scratch PATH dir carries a `python3.12` shim execing THIS
    interpreter, because the pack pins the house interpreter by name and the
    runner section resolves `python3.12 || python3`. The eval therefore tests
    the pack's LOGIC, not the interpreter-name layout of the box it runs on.
  * A3 is a substring pin, not a semantic one: it proves the clauses are still
    there, not that a reviewer obeys them. Obedience is what the per-item
    Captain gate on every emitted finding is for.

Fail-closed: a missing pack script, a missing/malformed fixture, a missing
fixture tree, a non-zero pack exit, or an unreadable skill file is a FAIL —
never a skip.

SECURITY: --repo-root/--fixtures are operator-supplied, read-only, and never
interpolated into a shell (argv lists only, shell=False). Fixture content is
inert data — compared, never executed.

Usage:
  python3.12 harness.py --self-test [--fixtures DIR] [--repo-root DIR]
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_FIXTURES_DIR = _HERE / "fixtures"
_REPO_ROOT = _HERE.parents[2]

_PACK_REL = "cabinet/scripts/meta-cognition/captain-seat-pack.sh"
_TAXONOMY_PREFIX = "action-lessons rows per taxonomy: "
_REPEATED_PREFIX = "repeated subjects (count>1): "
_PACK_TIMEOUT_S = 120


def _fail(msg: str) -> int:
    print(f"MISMATCH: {msg}")
    return 1


def _tree_digest(root: Path) -> str:
    """Order-stable digest of every file under root (path + bytes)."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode("utf-8"))
            h.update(b"\0")
            h.update(p.read_bytes())
            h.update(b"\0")
    return h.hexdigest()


def _write_shim(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


def _run_pack(pack: Path, seat_root: Path, scratch: Path) -> "tuple[int, str]":
    """Run the pack against a fixture root in a rebuilt environment."""
    shim_dir = scratch / "bin"
    shim_dir.mkdir(exist_ok=True)
    # A redis-cli that connects to nothing: the pack's probe must resolve to
    # its own "unavailable" branch, so no live control plane can be touched.
    _write_shim(shim_dir / "redis-cli",
                "#!/bin/sh\necho 'eval sandbox: redis-cli disabled' >&2\nexit 1\n")
    # The pack pins the house interpreter by name; run it under THIS one.
    _write_shim(shim_dir / "python3.12",
                f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    home = scratch / "home"
    home.mkdir(exist_ok=True)
    env = {
        "PATH": f"{shim_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        "HOME": str(home),
        "LC_ALL": "C.UTF-8",
        "CAPTAIN_SEAT_ROOT": str(seat_root),
        "CAPTAIN_SEAT_WINDOW_DAYS": "14",
    }
    proc = subprocess.run(
        ["bash", str(pack)], env=env, cwd=str(scratch),
        capture_output=True, text=True, timeout=_PACK_TIMEOUT_S, check=False)
    return proc.returncode, proc.stdout


def _mapping_after(out: str, prefix: str) -> "dict | None | str":
    """Return the mapping printed after `prefix`, '(none)' as a string, or None."""
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            payload = stripped[len(prefix):].strip()
            if payload == "(none)":
                return "(none)"
            try:
                value = ast.literal_eval(payload)
            except (ValueError, SyntaxError):
                return None
            return value if isinstance(value, dict) else None
    return None


def _check_repetition(pack: Path, fixtures: Path, pins: dict,
                      scratch: Path) -> int:
    spec = pins["repetition"]
    root = fixtures / spec["root"]
    if not root.is_dir():
        return _fail(f"repetition fixture tree missing: {root}")
    rc, out = _run_pack(pack, root, scratch)
    if rc != 0:
        return _fail(f"repetition arm: pack exited {rc}")
    failures = 0
    got_tax = _mapping_after(out, _TAXONOMY_PREFIX)
    want_tax = spec["taxonomy_counts"]
    if got_tax != want_tax:
        failures += _fail(
            f"repetition arm taxonomy counts: want {want_tax} got {got_tax!r}")
    got_rep = _mapping_after(out, _REPEATED_PREFIX)
    want_rep = spec["repeated_subjects"]
    if got_rep != want_rep:
        failures += _fail(
            "repetition arm: the pack must report the twice-corrected subject "
            f"with its count — want {want_rep} got {got_rep!r}")
    return failures


def _check_healthy(pack: Path, fixtures: Path, pins: dict,
                   scratch: Path) -> int:
    spec = pins["healthy"]
    root = fixtures / spec["root"]
    if not root.is_dir():
        return _fail(f"healthy fixture tree missing: {root}")
    rc, out = _run_pack(pack, root, scratch)
    if rc != 0:
        return _fail(f"healthy arm: pack exited {rc}")
    failures = 0
    got_tax = _mapping_after(out, _TAXONOMY_PREFIX)
    want_tax = spec["taxonomy_counts"]
    if got_tax != want_tax:
        failures += _fail(
            f"healthy arm taxonomy counts: want {want_tax} got {got_tax!r}")
    got_rep = _mapping_after(out, _REPEATED_PREFIX)
    if got_rep != "(none)":
        failures += _fail(
            "healthy arm: a window with no repeated subject must report "
            f"'(none)' — got {got_rep!r} (fabricated repetition)")
    if spec["repeated_subjects_line"] not in out:
        failures += _fail(
            "healthy arm: the repetition line itself is missing — the "
            "section did not run, so 'reports none' would be vacuous")
    for rel, reason in spec["absent_markers"]:
        marker = f"ABSENT: {root / rel} — {reason}"
        if marker not in out:
            failures += _fail(
                f"healthy arm: absent store not reported as a measured "
                f"absence: expected line '{marker}'")
    if spec["briefing_scoring_absent_substring"] not in out:
        failures += _fail(
            "healthy arm: an absent briefing-scoring loop must print as "
            f"ABSENT (looked for '{spec['briefing_scoring_absent_substring']}')")
    return failures


def _check_contract(repo_root: Path, pins: dict) -> int:
    spec = pins["contract_pin"]
    path = repo_root / spec["path"]
    try:
        text = path.read_text()
    except OSError as exc:
        return _fail(f"contract-pin arm: {path} unreadable: {exc}")
    failures = 0
    for item in spec["required"]:
        if item["text"] not in text:
            failures += _fail(
                f"contract-pin arm: {spec['path']} lost a load-bearing Part 1c "
                f"clause ({item['why']}): {item['text']!r}")
    return failures


def run_self_test(fixtures_dir: Path, repo_root: Path) -> int:
    pins_path = fixtures_dir / "pins.json"
    try:
        pins = json.loads(pins_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return _fail(f"fixture unreadable: {pins_path}: {exc}")
    if not isinstance(pins, dict):
        return _fail("fixture root must be an object")
    for key in ("repetition", "healthy", "contract_pin"):
        if not isinstance(pins.get(key), dict):
            return _fail(f"fixture section missing/malformed: {key}")
    if not pins["contract_pin"].get("required"):
        return _fail("fixture contract_pin.required missing/empty — a pin "
                     "list that pins nothing would pass on any skill text")

    pack = repo_root / _PACK_REL
    if not pack.is_file():
        return _fail(f"Captain-seat pack missing at {pack}")

    before = {name: _tree_digest(fixtures_dir / pins[name]["root"])
              for name in ("repetition", "healthy")
              if (fixtures_dir / pins[name]["root"]).is_dir()}

    failures = 0
    with tempfile.TemporaryDirectory(prefix="captain-seat-eval-") as tmp:
        scratch = Path(tmp)
        failures += _check_repetition(pack, fixtures_dir, pins, scratch)
        failures += _check_healthy(pack, fixtures_dir, pins, scratch)
    failures += _check_contract(repo_root, pins)

    # A4 — the pack claims read-only; prove it against the fixture trees.
    for name, digest in before.items():
        after = _tree_digest(fixtures_dir / pins[name]["root"])
        if after != digest:
            failures += _fail(
                f"{name} fixture tree MUTATED by the pack run — the pack "
                "must be read-only")

    # The summary line must never claim green on a red run — a reassuring
    # summary over failing arms is the same class as a sensor that reports OK
    # while the thing it watches is broken.
    pinned = len(pins["contract_pin"]["required"])
    if failures:
        print(f"CAPTAIN-SEAT-EVAL: RED — {failures} mismatch(es) across "
              f"repetition / healthy / contract-pin ({pinned} clauses pinned)")
        return 1
    print(f"CAPTAIN-SEAT-EVAL: GREEN — repetition + healthy(degenerate) arms "
          f"hold; {pinned} Part 1c clauses pinned; fixture trees unmutated")
    return 0


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(prog="captain-seat-eval-harness")
    parser.add_argument("--self-test", action="store_true", required=True)
    parser.add_argument("--fixtures", default=str(_FIXTURES_DIR))
    parser.add_argument("--repo-root", default=str(_REPO_ROOT))
    args = parser.parse_args(argv)
    return run_self_test(Path(args.fixtures), Path(args.repo_root))


if __name__ == "__main__":
    sys.exit(main())
