"""Flywheel step 2 — the non-regression gate over the frozen correction corpus.

WHY (fresh review 2026-07-04 §6.2): a correction that never replays is spent
once. The corpus (framework/fidelity/regression_corpus_lib.py harvests it into
the instance-layer store instance/fidelity/regression_corpus/ — egg R009; the
lib's framework-local DEFAULT_CORPUS_DIR ships empty, and an empty corpus is
an honest no_verdict here) freezes every human correction as a case; THIS
module is the checkable predicate the F1/eval cadence calls before accepting a
behavior change:

    PASS  iff  no frozen case regresses  AND  >= 1 frozen case improves.

TERMS (per case, over a replay of the frozen situations):
  * a case RESULT is a bool: True = the replayed system decision AGREES with
    the frozen human verdict for that case; False = it would repeat the
    corrected mistake. Producing results is the replay runner's job (the F1
    cadence drives the harness over the corpus situations); this module only
    judges baseline-vs-candidate result sets.
  * REGRESSED: baseline True -> candidate False (a case we had learned, lost).
  * IMPROVED:  baseline False -> candidate True (a correction newly absorbed).

FAIL-SAFE (Corridor invariant — a gate on ANY error yields NO verdict, never a
spurious pass): the outcome is three-valued —
  * "pass"       — predicate evaluable and met.
  * "fail"       — predicate evaluable and NOT met (a regression exists, or
                   nothing improved). An honest negative.
  * "no_verdict" — the predicate could not be evaluated: empty corpus, a
                   frozen case missing from either result set, a non-bool
                   result, malformed corpus/result files, or any exception in
                   the file-driven path. NEVER converted into pass; callers
                   gate on `result.passed` which is True ONLY for "pass".

Coverage is strict by design: certifying "no frozen case regresses" is
impossible if a frozen case was not replayed on BOTH sides, so missing
coverage is no_verdict (not a silent skip). Extra (non-frozen) ids in a result
set are tolerated and ignored — the gate certifies the frozen set only.

Deliberately NOT wired into framework/fidelity/graduation.py (schg-locked
germline — cabinet/scripts/germline-lock.sh FILES): the eval cadence calls
this module directly; graduation's per-cell trust math is a separate concern.

System Python is 3.9.6 — stdlib only, `from __future__ import annotations`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

from framework.fidelity.regression_corpus_lib import CASE_FORMAT, DEFAULT_CORPUS_DIR

OUTCOME_PASS = "pass"
OUTCOME_FAIL = "fail"
OUTCOME_NO_VERDICT = "no_verdict"


class CorpusError(Exception):
    """The frozen corpus is unreadable or malformed. Raised by load_corpus();
    the file-driven gate path converts it to a no_verdict result (fail-safe)."""


@dataclass
class GateResult:
    """The gate's verdict + the evidence behind it.

    `outcome` is the three-valued verdict (module docstring). `regressed` /
    `improved` carry the concrete case ids so a failing gate is immediately
    diagnosable (which correction was lost / newly absorbed). `reasons` is
    human-readable and ALWAYS populated for fail/no_verdict."""
    outcome: str
    regressed: list[str] = field(default_factory=list)
    improved: list[str] = field(default_factory=list)
    checked: int = 0
    reasons: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """The ONE boolean callers may gate on: True ONLY for outcome 'pass'
        (both 'fail' and 'no_verdict' are False — no spurious pass)."""
        return self.outcome == OUTCOME_PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "passed": self.passed,
            "regressed": list(self.regressed),
            "improved": list(self.improved),
            "checked": self.checked,
            "reasons": list(self.reasons),
        }


# ---------------------------------------------------------------------------
# corpus loading
# ---------------------------------------------------------------------------

def load_corpus(corpus_dir: Optional[Path] = None) -> list[dict[str, Any]]:
    """Load + validate every frozen case in the corpus, sorted by case_id.

    Validation is minimal but load-bearing: a corrupt or drifted case file
    raises CorpusError rather than being silently skipped — a gate that
    silently dropped a frozen case could certify non-regression it never
    checked (the exact failure the fail-safe posture forbids)."""
    corpus_dir = Path(corpus_dir) if corpus_dir is not None else DEFAULT_CORPUS_DIR
    cases_dir = corpus_dir / "cases"
    if not cases_dir.is_dir():
        return []  # honest empty corpus (evaluate_gate makes it no_verdict)

    cases: list[dict[str, Any]] = []
    for path in sorted(cases_dir.glob("case-*.json")):
        try:
            body = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise CorpusError(f"unreadable case file {path.name}: {exc}") from exc
        if not isinstance(body, dict):
            raise CorpusError(f"case file {path.name} is not an object")
        if body.get("case_format") != CASE_FORMAT:
            raise CorpusError(
                f"case file {path.name}: unsupported case_format "
                f"{body.get('case_format')!r} (expected {CASE_FORMAT})"
            )
        if body.get("case_id") != path.stem:
            # id/filename drift means the corpus was hand-edited — refuse.
            raise CorpusError(
                f"case file {path.name}: embedded case_id {body.get('case_id')!r} "
                "does not match filename"
            )
        for key in ("cell", "situation", "human_verdict"):
            if not isinstance(body.get(key), dict):
                raise CorpusError(f"case file {path.name}: missing/invalid {key!r}")
        cases.append(body)
    return cases


def corpus_case_ids(corpus_dir: Optional[Path] = None) -> list[str]:
    """The frozen case-id set (sorted). Raises CorpusError on a malformed
    corpus — same strictness as load_corpus, for the same reason."""
    return [c["case_id"] for c in load_corpus(corpus_dir)]


# ---------------------------------------------------------------------------
# the predicate
# ---------------------------------------------------------------------------

def evaluate_gate(
    corpus_ids: list[str],
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> GateResult:
    """The checkable predicate: 'no frozen case regresses AND >=1 improves'.

    `baseline` / `candidate` map case_id -> bool (True = replay agreed with
    the frozen human verdict). Pure function — no IO, no exceptions for data
    problems (they become no_verdict), so the eval cadence can call it with
    whatever transport it likes.

    Decision table (dated 2026-07-05):
      * empty corpus_ids               -> no_verdict ("nothing frozen to
        certify" — an empty suite must never wave a change through).
      * frozen id missing on either side, or a non-bool value -> no_verdict
        (coverage is part of the claim; see module docstring).
      * any regression                 -> fail.
      * zero regressions, zero improvements -> fail ("no case improved" — the
        predicate demands demonstrated improvement, per review §6.2's braintrust
        rule; an all-green-but-flat candidate is not certified by THIS gate).
      * zero regressions, >=1 improvement  -> pass.
    """
    ids = sorted(set(corpus_ids))
    if not ids:
        return GateResult(
            outcome=OUTCOME_NO_VERDICT,
            reasons=["empty corpus: nothing frozen to certify"],
        )

    missing_base = [i for i in ids if i not in baseline]
    missing_cand = [i for i in ids if i not in candidate]
    if missing_base or missing_cand:
        reasons = []
        if missing_base:
            reasons.append(f"baseline missing {len(missing_base)} frozen case(s): "
                           + ", ".join(missing_base[:5]))
        if missing_cand:
            reasons.append(f"candidate missing {len(missing_cand)} frozen case(s): "
                           + ", ".join(missing_cand[:5]))
        return GateResult(outcome=OUTCOME_NO_VERDICT, reasons=reasons)

    # bool is an int subclass; require REAL bools so a stray score (0.7) or a
    # string "true" can never be coerced into a verdict.
    bad_type = [
        i for i in ids
        if not isinstance(baseline[i], bool) or not isinstance(candidate[i], bool)
    ]
    if bad_type:
        return GateResult(
            outcome=OUTCOME_NO_VERDICT,
            reasons=["non-boolean result for case(s): " + ", ".join(bad_type[:5])],
        )

    regressed = [i for i in ids if baseline[i] and not candidate[i]]
    improved = [i for i in ids if not baseline[i] and candidate[i]]

    if regressed:
        return GateResult(
            outcome=OUTCOME_FAIL,
            regressed=regressed,
            improved=improved,
            checked=len(ids),
            reasons=[f"{len(regressed)} frozen case(s) regressed"],
        )
    if not improved:
        return GateResult(
            outcome=OUTCOME_FAIL,
            improved=[],
            checked=len(ids),
            reasons=["no frozen case improved (predicate requires >=1)"],
        )
    return GateResult(
        outcome=OUTCOME_PASS,
        improved=improved,
        checked=len(ids),
        reasons=[],
    )


def gate_from_files(
    baseline_path: Path,
    candidate_path: Path,
    corpus_dir: Optional[Path] = None,
) -> GateResult:
    """File-driven wrapper for the F1/eval cadence: two result files (flat
    JSON objects {case_id: bool}) judged against the frozen corpus.

    NEVER raises — ANY exception (unreadable file, bad JSON, malformed corpus)
    returns a no_verdict GateResult carrying the error text, so a crashed eval
    step can never be mistaken for a green gate (Corridor fail-safe)."""
    try:
        ids = corpus_case_ids(corpus_dir)
        baseline = json.loads(Path(baseline_path).read_text())
        candidate = json.loads(Path(candidate_path).read_text())
        if not isinstance(baseline, dict) or not isinstance(candidate, dict):
            return GateResult(
                outcome=OUTCOME_NO_VERDICT,
                reasons=["result files must be flat JSON objects {case_id: bool}"],
            )
        return evaluate_gate(ids, baseline, candidate)
    except Exception as exc:  # noqa: BLE001 — the catch-all IS the fail-safe
        return GateResult(
            outcome=OUTCOME_NO_VERDICT,
            reasons=[f"gate error (no verdict): {exc!r}"],
        )
