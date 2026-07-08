"""Calibration gate for the vision judge — the D5 move.

Before any candidate verdict counts, the judge (an agent following the
protocol) must first correctly rank a HIDDEN calibration set: every corpus
negative below every positive. The calibration pairs are built from the full
positive x negative cross product, blinded and shuffled among the candidate
pairs by judge_protocol.build (hidden > sequenced-visible: a judge cannot ace
a visible warm-up and then phone in the real pairs, because it cannot tell
which is which).

Gate: pairwise accuracy >= CALIBRATION_THRESHOLD (0.90). Below the floor the
whole run is VOID — verdicts are stamped `void`, never computed. Calibration
results are stamped into every run output either way.

Pure library (no CLI): judge_protocol.build embeds the pairs,
judge_protocol.ingest calls score() and enforces the gate.
"""

from __future__ import annotations

import random

CALIBRATION_THRESHOLD = 0.90
_EPS = 1e-9


def build_pairs(positives: list[dict], negatives: list[dict],
                rng: random.Random, max_pairs: int = 0) -> list[dict]:
    """Full positive x negative cross product (optionally seeded-capped).

    Returns [{"positive": pos_entry, "negative": neg_entry}, ...] in
    rng-shuffled order. `max_pairs > 0` caps via rng.sample — still every
    judge run draws its calibration from the same hidden distribution.
    """
    if not positives or not negatives:
        raise ValueError("calibration needs at least one positive and one "
                         "negative corpus entry")
    pairs = [{"positive": p, "negative": n}
             for p in positives for n in negatives]
    if max_pairs and 0 < max_pairs < len(pairs):
        pairs = rng.sample(pairs, max_pairs)
    rng.shuffle(pairs)
    return pairs


def score(cal_key: list[dict], answers_by_id: dict[str, dict],
          threshold: float = CALIBRATION_THRESHOLD) -> dict:
    """Score calibration answers; a missing answer counts as incorrect.

    cal_key rows: {"task_id": str, "positive_side": "LEFT"|"RIGHT",
                   "positive_id": str, "negative_id": str}
    answers_by_id: task_id -> {"choice": "LEFT"|"RIGHT", "why": str}
    """
    n = len(cal_key)
    correct = 0
    failures = []
    for row in cal_key:
        ans = answers_by_id.get(row["task_id"])
        chose = ans["choice"] if ans else None
        if chose == row["positive_side"]:
            correct += 1
        else:
            failures.append({
                "task_id": row["task_id"],
                "positive_id": row["positive_id"],
                "negative_id": row["negative_id"],
                "chose": chose,
                "why": (ans or {}).get("why", ""),
            })
    accuracy = (correct / n) if n else 0.0
    return {
        "n_pairs": n,
        "correct": correct,
        "accuracy": accuracy,
        "threshold": threshold,
        # n == 0 can never calibrate: no evidence of judge competence.
        "passed": n > 0 and accuracy + _EPS >= threshold,
        "failures": failures,
    }
