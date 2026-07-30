"""clustering: the scattered-props detector — THE prove-it contract.

Task order: the gate must FAIL on corpus negatives (the 5.png-class synthetic
scatter, as MAP data and as renders, plus the real Captain-rejected build
screenshots) and PASS on positives-derived stats (the COMMITTED
calibration/clustering_bounds.json — image bounds fitted from the 9 LimeZu
corpus positives, map bounds from canonical clustered layouts). The same
separation is provable offline via `calibrate.py prove`.
"""

import json

import pytest

# (seed, n) mirroring calibrate.SCATTER_SEEDS — 42/1337 are the corpus
# neg-scatter render seeds, reproduced here as MAP data.
SCATTER_CASES = ((42, 18), (1337, 90), (7, 60))
DENSE_CASES = {1337, 7}          # blanket scatter: also loses all clearings
HOLDOUT_SEEDS = (99, 23, 47)     # never used for fitting (fit uses 11..16)


def _bounds(wa):
    p = wa.calib_dir / "clustering_bounds.json"
    # ASSERT, never skip: this file is TRACKED (`git ls-files` lists it), so the
    # skip it used to take could not fire on any real checkout and could only
    # ever hide a deleted calibration. A guard that cannot legitimately fire is
    # a disabled sensor wearing a condition.
    assert p.is_file(), (
        f"{p} is tracked and missing — every clustering arm below is calibrated "
        "against it, so its absence is a broken checkout, not a reason to pass")
    return json.loads(p.read_text())


# ------------------------------------------------------------- calibration

def test_committed_bounds_are_positives_derived(wa):
    b = _bounds(wa)
    assert b["schema"] == "cabinet.world.clustering-bounds/v1"
    mb = b["map"]
    assert set(mb) >= {"r_max", "open_min", "params", "fitted_from"}
    assert len(mb["fitted_from"]) >= 3
    # Separation mechanics: uniform random scatter sits at Clark-Evans R≈1,
    # so a fitted r_max at or above 1 could never catch it.
    assert 0 < mb["r_max"] < 0.9
    ib = b.get("image")
    assert ib, "image bounds must be fitted from the positive corpus"
    assert set(ib) >= {"flat_max", "dominant_max", "params", "fitted_from"}
    for entry in ib["fitted_from"]:
        assert entry["sha256"] and entry["file"].startswith("pos-")


# ---------------------------------------------------- prove-it: MAP side

def test_scatter_maps_fail_committed_bounds(wa):
    """5.png-class synthetic scatter maps MUST trip the fitted map bounds."""
    b = _bounds(wa)
    for seed, n in SCATTER_CASES:
        m = wa.synth.make_scatter_map(seed, n=n)
        findings = wa.gates.clustering.check(map_data=m, bounds=b)
        codes = [f["code"] for f in wa.errors(findings)]
        assert "CLUSTER_SCATTER" in codes, (seed, n, codes)
        if seed in DENSE_CASES:
            assert "CLUSTER_NO_CLEARING" in codes, (seed, n, codes)


def test_clustered_holdout_maps_pass_committed_bounds(wa):
    """Designed clumps+plaza layouts (held-out seeds) MUST pass."""
    b = _bounds(wa)
    for seed in HOLDOUT_SEEDS:
        m = wa.synth.make_clustered_map(seed)
        findings = wa.gates.clustering.check(map_data=m, bounds=b)
        assert wa.errors(findings) == [], (seed, wa.codes(findings))
        assert "CLUSTER_MAP_STATS" in wa.codes(findings)


# --------------------------------------------------- prove-it: IMAGE side

def test_corpus_negative_renders_fail(wa):
    """Every negative the manifest declares AND this checkout can verify.

    Three of the six negatives are HELD (Captain-rejected screenshots carrying
    licensed art), so on a fresh checkout this runs over the three synthetic
    owned-art negatives, which build_corpus rebuilds byte-identically from the
    repo's own tracked pack. That is the difference between an arm that runs in
    CI and an arm that skips there — and `wa.held` names what it did not see.
    """
    wa.require("negative")
    b = _bounds(wa)
    for p in wa.corpus("negative"):
        findings = wa.gates.clustering.check(image_path=p, bounds=b)
        codes = [f["code"] for f in wa.errors(findings)]
        assert "CLUSTER_FLAT_VOID" in codes, f"{p.name} not caught: {codes}"


def test_corpus_positive_renders_pass(wa):
    wa.require("positive")
    b = _bounds(wa)
    for p in wa.corpus("positive"):
        findings = wa.gates.clustering.check(image_path=p, bounds=b)
        assert wa.errors(findings) == [], (p.name, wa.codes(findings))


def test_synthetic_flat_scatter_render_fails(wa, tmp_path):
    """Corpus-independent image-side negative: the exact rejected look,
    regenerated from seed — must trip the committed image bounds."""
    b = _bounds(wa)
    p = tmp_path / "scatter.png"
    wa.png.encode(p, 384, 320, wa.synth.make_flat_scatter_scene(42))
    findings = wa.gates.clustering.check(image_path=p, bounds=b)
    assert "CLUSTER_FLAT_VOID" in [f["code"] for f in wa.errors(findings)]


def test_map_and_image_sides_combine(wa, tmp_path):
    b = _bounds(wa)
    p = tmp_path / "scatter.png"
    wa.png.encode(p, 384, 320, wa.synth.make_flat_scatter_scene(1337, n=90))
    m = wa.synth.make_scatter_map(1337, n=90)
    codes = [f["code"] for f in
             wa.errors(wa.gates.clustering.check(map_data=m, image_path=p,
                                                 bounds=b))]
    assert "CLUSTER_SCATTER" in codes and "CLUSTER_FLAT_VOID" in codes


# ------------------------------------------------------------- mechanics

def test_few_props_skips_map_stats(wa):
    b = _bounds(wa)
    m = wa.base_map(12, 8)
    m["layers"].append({"name": "props", "kind": "prop", "tiles": [
        {"sheet": "props", "region": [0, 0, 16, 16], "x": x, "y": 1}
        for x in (1, 5, 9)]})  # 3 props, spread out — but below min_props
    findings = wa.gates.clustering.check(map_data=m, bounds=b)
    assert wa.errors(findings) == []
    assert "CLUSTER_FEW_PROPS" in wa.codes(findings)


def test_missing_bounds_warn_then_error_strict(wa):
    m = wa.synth.make_scatter_map(42, n=18)
    findings = wa.gates.clustering.check(map_data=m, bounds=None)
    miss = [f for f in findings if f["code"] == "CALIBRATION_MISSING"]
    assert miss and miss[0]["severity"] == "warn"
    assert wa.errors(findings) == []  # no bounds -> nothing trips
    strict = wa.gates.clustering.check(
        map_data=m, bounds=None, config={"strict_calibration": True})
    assert [f["code"] for f in wa.errors(strict)] == ["CALIBRATION_MISSING"]


def test_prop_footprint_centers(wa):
    m = wa.base_map(10, 10)
    m["layers"].append({"name": "props", "kind": "prop", "tiles": [
        {"sheet": "props", "region": [0, 0, 32, 32], "x": 2, "y": 2}]})
    assert wa.gates.clustering.prop_centers(m) == [(3.0, 3.0)]


def test_synth_fixtures_deterministic(wa):
    assert wa.synth.make_scatter_map(42, n=18) == \
        wa.synth.make_scatter_map(42, n=18)
    assert wa.synth.make_clustered_map(11) == wa.synth.make_clustered_map(11)
    assert wa.synth.make_flat_scatter_scene(7) == \
        wa.synth.make_flat_scatter_scene(7)
    assert wa.synth.make_textured_scene(7) == wa.synth.make_textured_scene(7)
