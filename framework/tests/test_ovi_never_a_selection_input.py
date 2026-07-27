"""OVI is Captain-FACING ONLY — it may never select, rank, or gate anything.

THE LAW (standing Captain rider, 2026-07-25, recorded with the purpose-gate
adjudication that reworded the metric to "attention WELL SPENT"): the OVI
composite and its attention term are a **Captain-facing instrument** and must
**never become a selection input**. Not a promotion criterion, not a ranking
key, not a gate — for anything, ever.

WHAT THIS RATCHET EXISTS TO CATCH — it is not hypothetical. Until 2026-07-26
``framework/roles/hat_graduation.py`` replayed ``ovi_snapshot_computed`` and
read its ``composite_score`` as a criterion for promoting a hat to a permanent
role capability, and that path feeds
``framework.learning.self_improvement_loop._apply_hat_graduations``, which
emits ``role_capability_added``. The composite was one snapshot away from
mechanically widening a role's permanent authority — and the composite it
would have read scored a week of ZERO Captain contact and ZERO delivery a
perfect 1.00 on its attention term. A selection input built on that rewards
going quiet. The wire is cut; this test is what stops it being reconnected
silently, by a future session that never reads the rider.

HOW IT SCANS, and why this shape:

  * ``.py`` files are parsed with ``ast`` and only CODE positions are checked —
    identifiers (Name/Attribute/alias) and string constants that are NOT
    docstrings. Prose may therefore explain the law (this file and
    ``hat_graduation.py`` both do, at length) while a live
    ``replay(event_types=["ovi_snapshot_computed"])`` is caught, because that
    token sits in a call argument, not a docstring. Comments are invisible to
    the AST and are likewise free.
  * Non-``.py`` files in the same trees get a raw token scan — a YAML/shell
    consumer is a consumer.
  * A file that fails to PARSE is a FAILURE, never a skip. A disabled sensor
    is not a pass.

DEGENERATE ENDS, each its own assertion (a scan of nothing must never read as
compliance):
  * every named tree must EXIST — a rename that empties the scan is RED, not
    silently green;
  * the scanned file count must be > 0;
  * the scanner itself is proven non-vacuous IN THIS SUITE by
    ``test_scanner_detects_a_planted_reconnection``, which plants each forbidden
    construct in a synthetic module and asserts the scanner reports it. Without
    that arm this file could pass by scanning nothing correctly forever.

HONEST LIMITATIONS, stated rather than hidden:
  * test files are excluded. A test does not select anything — it is a sensor,
    not a control — and the inverted regression pin in
    ``framework/learning/tests/test_phase7.py`` must be able to EMIT an
    ``ovi_snapshot_computed`` event to prove the wire no longer bites. The
    residual escape (hiding a live selection path inside a ``test_*.py`` and
    importing it from production) is contortion, not evasion cover.
  * a consumer that builds the token dynamically (``"ovi_" + "snapshot"``)
    evades the grammar. Per the house rule for the sibling never-a-score
    harness: treat such evasion as the violation itself.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: The trees that SELECT, RANK or GATE. Every one of these decides something —
#: who gets promoted, what reaches the Captain, what the org is allowed to do,
#: what runs next. These are exactly the places the rider forbids OVI from
#: reaching. Each MUST exist (see the degenerate-end test).
SELECTION_TREES = (
    "framework/roles",        # hat graduation -> permanent role capabilities
    "framework/fidelity",     # autonomy-cell graduation
    "framework/authority",    # the policy engine / authority matrix
    "framework/attention",    # what reaches the Captain, and the demote path
    "framework/acting",       # what the org does
    "framework/frontdoor",    # what gets sent
    "framework/evolution",    # self-improvement selection
    "framework/learning",     # the self-improvement loop that APPLIES promotions
    "framework/missions",     # routing
    "framework/scheduler",    # the planner
    "framework/organs",       # organ dispatch
    "framework/measurement",  # role evals
)

#: Tokens that mean "this code is reading the Captain-facing value index".
#: ``composite_score`` is the composite itself; ``ovi_snapshot_computed`` is
#: the only event carrying it; the attention-term names are the specific term
#: whose polarity was wrong. ``framework.ovi`` / ``framework/ovi`` catch a
#: direct import or path read of the module.
FORBIDDEN_TOKENS = (
    "ovi_snapshot_computed",
    "composite_score",
    "captain_attention_well_spent",
    "captain_attention_cost",
    "framework.ovi",
    "framework/ovi",
)


def _is_test_path(path: Path) -> bool:
    """Tests are sensors, not controls — see the docstring's limitations."""
    return "tests" in path.parts or path.name.startswith("test_")


def _docstring_nodes(tree: ast.AST) -> set:
    """The ``id()`` of every Constant node that IS a docstring.

    Docstrings are prose and are exempt: the law has to be explainable in the
    very files it binds. Everything else in a string position is code.
    """
    out = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None) or []
        if not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            out.add(id(first.value))
    return out


def _code_tokens(source: str) -> set:
    """Every identifier + non-docstring string constant in ``source``.

    Raises SyntaxError on an unparseable file — the caller turns that into a
    FAILURE, because a sensor that skips what it cannot read is not a sensor.
    """
    tree = ast.parse(source)
    skip = _docstring_nodes(tree)
    tokens: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in skip:
                tokens.add(node.value)
        elif isinstance(node, ast.Name):
            tokens.add(node.id)
        elif isinstance(node, ast.Attribute):
            tokens.add(node.attr)
        elif isinstance(node, ast.alias):
            tokens.add(node.name)
            if node.asname:
                tokens.add(node.asname)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", None)
            if mod:
                tokens.add(mod)
    return tokens


def scan_source(source: str, *, is_python: bool) -> list:
    """Forbidden tokens found in ``source``. PURE — no I/O, so the planted-
    reconnection arm can drive it directly and prove it is not vacuous."""
    if is_python:
        haystack = _code_tokens(source)
        return sorted({t for t in FORBIDDEN_TOKENS
                       if any(t in tok for tok in haystack)})
    return sorted({t for t in FORBIDDEN_TOKENS if t in source})


def _files_to_scan() -> list:
    files: list = []
    for tree in SELECTION_TREES:
        root = _REPO_ROOT / tree
        if not root.is_dir():
            continue  # the existence test owns this failure, with a better message
        for path in sorted(root.rglob("*")):
            if not path.is_file() or _is_test_path(path):
                continue
            if path.suffix in (".pyc", ".pyo") or "__pycache__" in path.parts:
                continue
            files.append(path)
    return files


class OVIIsNeverASelectionInput(unittest.TestCase):

    def test_every_named_selection_tree_exists(self):
        """A renamed/moved tree must RED, never silently empty the scan."""
        missing = [t for t in SELECTION_TREES
                   if not (_REPO_ROOT / t).is_dir()]
        self.assertEqual(
            missing, [],
            "SELECTION_TREES names a path that no longer exists: "
            f"{missing}. A tree that moved must be RE-POINTED here in the same "
            "change — an empty scan is not compliance.")

    def test_the_scan_covers_a_non_empty_file_set(self):
        """The degenerate end: scanning zero files must never read as a pass."""
        files = _files_to_scan()
        self.assertGreater(
            len(files), 0,
            "the selection-tree scan matched NO files — the ratchet would pass "
            "vacuously. Fix the tree list, do not relax this assertion.")

    def test_no_selection_path_reads_the_ovi_composite_or_attention_term(self):
        """THE LAW. OVI is Captain-facing; it selects/ranks/gates nothing."""
        violations: list = []
        unparseable: list = []
        for path in _files_to_scan():
            rel = path.relative_to(_REPO_ROOT)
            try:
                source = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue  # a binary asset carries no selection logic
            is_py = path.suffix == ".py"
            try:
                found = scan_source(source, is_python=is_py)
            except SyntaxError as exc:
                unparseable.append(f"{rel}: {exc}")
                continue
            if found:
                violations.append(f"{rel}: {found}")

        self.assertEqual(
            unparseable, [],
            "a file in a selection tree could not be PARSED, so it was not "
            f"scanned — that is a disabled sensor, not a pass: {unparseable}")
        self.assertEqual(
            violations, [],
            "OVI reached a selection/ranking/gating path — this violates the "
            "standing Captain rider that the value index is a Captain-FACING "
            "instrument and must never be a selection input. Route the need "
            "through evidence the decision actually depends on, or take it to "
            f"the Captain. Violations: {violations}")

    def test_scanner_detects_a_planted_reconnection(self):
        """NON-VACUITY: the scanner must FAIL against the code this file exists
        to forbid. Without this arm the suite could pass by scanning correctly
        and finding nothing, forever, even if the scanner were broken."""
        planted = (
            '"""A docstring may say ovi_snapshot_computed and composite_score."""\n'
            'from framework.events.emitter import replay\n'
            'def promote(candidate):\n'
            '    snaps = replay(event_types=["ovi_snapshot_computed"])\n'
            '    return snaps[-1]["payload"]["composite_score"] > 0.5\n'
        )
        found = scan_source(planted, is_python=True)
        self.assertIn("ovi_snapshot_computed", found)
        self.assertIn("composite_score", found)

        # ...and the docstring-only twin must stay CLEAN, or the exemption is
        # the thing that is broken and every prose mention becomes a false red.
        prose_only = (
            '"""Explains that ovi_snapshot_computed carries composite_score '
            'and that captain_attention_well_spent must never select."""\n'
            'def promote(candidate):\n'
            '    return candidate["uses"] >= 5\n'
        )
        self.assertEqual(scan_source(prose_only, is_python=True), [])

        # a direct import of the module is equally a reconnection
        self.assertIn(
            "framework.ovi",
            scan_source("from framework.ovi.compute import compute_ovi\n",
                        is_python=True))
        # and a non-python consumer is caught by the raw scan
        self.assertIn(
            "composite_score",
            scan_source("rank_by: composite_score\n", is_python=False))


if __name__ == "__main__":
    unittest.main()
