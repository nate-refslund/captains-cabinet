"""framework.objectives.counterfactual — counterfactual branches + the prediction
store (COG-3 contract rev-1 §5.3 / §4.3).

Counterfactual = pure recomputation in its OWN home: build_branch replays the same
fold at an alternative cutoff + assumption-override set into
cache_dir/counterfactuals/<branch-digest>/ with a `counterfactual: true` manifest,
NEVER touching the canonical graph.jsonl/graph-manifest.json (the serve surface
refuses counterfactual manifests, §5.4).

Predictions are ORIGINAL forecast records in their OWN store
(cache_dir/predictions/) with a disjoint `pred-` id namespace and their OWN
chained-hash manifest — EXCLUDED from N1, NEVER written to the cortex belief store,
NEVER auto-promoted to evidence (the three §4.3 walls + the self-confirming-loop
wall). Scoring appends a prediction-accuracy record to the SAME store only.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; U2 (the counterfactuals + prediction store).
"""
from __future__ import annotations

import json
from pathlib import Path

from framework.objectives import graph, model


def _predictions_dir(objectives_cache_dir) -> Path:
    return Path(objectives_cache_dir) / "predictions"


def _append_record(objectives_cache_dir, record: dict) -> None:
    """Append one record to predictions/predictions.jsonl and advance the OWN
    chained-hash manifest (tamper-evident, append-only — §4.3). Touches nothing
    outside the predictions store (never the cortex store, never the canonical
    graph)."""
    pdir = _predictions_dir(objectives_cache_dir)
    pdir.mkdir(parents=True, exist_ok=True)
    store = pdir / "predictions.jsonl"
    with open(store, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True,
                                separators=(",", ":")) + "\n")
    _write_predictions_manifest(pdir, store)


def _write_predictions_manifest(pdir: Path, store: Path) -> None:
    chain = ""
    count = 0
    for line in store.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        chain = model.digest([chain, json.loads(line)])
        count += 1
    manifest = {"schema_version": "objectives-predictions-manifest/v1",
                "chained_hash": chain, "prediction_count": count}
    (pdir / "predictions-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")


def mint_prediction(objectives_cache_dir, edge_id, assumption_set, cutoff,
                    predicted_claim):
    """Mint a forecast for `edge_id` under `assumption_set` at `cutoff` (§4.3).
    Returns a `pred-<digest>` id (disjoint from the belief-id namespace, so it is
    structurally unciteable as evidence). Lands ONLY in the predictions store —
    NEVER the cortex belief store, NEVER the canonical graph."""
    record = model.Prediction(edge_id=edge_id, assumption_set=assumption_set,
                              cutoff=cutoff, predicted_claim=predicted_claim)
    row = record.to_canonical_dict()
    row["record_kind"] = "prediction"
    _append_record(objectives_cache_dir, row)
    return record.prediction_id


def score_prediction(objectives_cache_dir, prediction_id, outcome_view):
    """Score a minted prediction against the realized `outcome_view`, appending a
    prediction-ACCURACY record to the predictions store only (§4.3). The accuracy
    id keeps the `pred-` namespace (structurally unciteable as a belief); scoring
    changes NO edge state and touches NEITHER the cortex store NOR the canonical
    graph — the self-confirming loop is walled off. Cache-dir-first signature,
    matching mint_prediction (2026-07-23 adjudication)."""
    accuracy_id = "pred-" + model.digest(["accuracy", prediction_id, outcome_view])
    record = {
        "record_kind": "accuracy",
        "accuracy_id": accuracy_id,
        "prediction_id": prediction_id,
        "outcome": outcome_view,
    }
    _append_record(objectives_cache_dir, record)
    return record


def build_branch(roots_path, objectives_cache_dir, scope, cutoff,
                 assumption_overrides):
    """Replay the fold at an alternative `cutoff` + `assumption_overrides` into
    cache_dir/counterfactuals/<branch-digest>/ (branch-digest = recorder digest of
    (cutoff, assumption_overrides)) with a `counterfactual: true` manifest. Reads
    the SAME sibling cortex store as the canonical build; NEVER writes the
    canonical root (§5.3). Replay is byte-deterministic per branch."""
    objectives_cache_dir = Path(objectives_cache_dir)
    branch_digest = model.digest([cutoff, assumption_overrides])
    branch_dir = objectives_cache_dir / "counterfactuals" / branch_digest
    cortex_dir = objectives_cache_dir.parent / "cortex"
    graph._compile(roots_path, branch_dir, cortex_dir, scope, cutoff,
                   counterfactual=True, assumption_overrides=assumption_overrides)
    return str(branch_dir)
