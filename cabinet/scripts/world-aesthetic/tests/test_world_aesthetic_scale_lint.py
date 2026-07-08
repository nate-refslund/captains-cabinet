"""scale_lint: 16px grid, 48px giant-barn class, entity charset band."""


def _codes(wa, findings, sev=None):
    return [f["code"] for f in findings
            if sev is None or f["severity"] == sev]


def test_aligned_16px_clean(wa):
    m = wa.base_map()
    m["layers"].append({"name": "ground", "kind": "terrain", "tiles": [
        {"sheet": "outdoor", "region": [16, 0, 16, 16], "x": 0, "y": 0},
        {"sheet": "props", "region": [32, 64, 16, 32], "x": 1, "y": 0}]})
    assert wa.gates.scale_lint.check(m) == []


def test_misaligned_region_fails(wa):
    m = wa.base_map()
    m["layers"].append({"name": "ground", "kind": "terrain", "tiles": [
        {"sheet": "outdoor", "region": [8, 0, 16, 16], "x": 0, "y": 0},
        {"sheet": "outdoor", "region": [0, 0, 24, 24], "x": 1, "y": 0}]})
    findings = wa.gates.scale_lint.check(m)
    assert _codes(wa, findings, "error").count("SCALE_MISALIGNED") == 2


def test_48px_sheet_grid_is_giant_barn(wa):
    m = wa.base_map()
    m["layers"].append({"name": "buildings", "kind": "building", "tiles": [
        {"sheet": "b48", "region": [0, 0, 48, 48], "x": 0, "y": 0}]})
    findings = wa.gates.scale_lint.check(m)
    codes = _codes(wa, findings, "error")
    assert "SCALE_48PX_SOURCE" in codes
    # 48 is a 16-multiple: the dedicated rule must catch what alignment can't.
    assert "SCALE_MISALIGNED" not in codes


def test_non16_grid_fails(wa):
    m = wa.base_map()
    m["sheets"]["b32"] = {"grid": 32}
    m["layers"].append({"name": "ground", "kind": "terrain", "tiles": [
        {"sheet": "b32", "region": [0, 0, 32, 32], "x": 0, "y": 0}]})
    assert "SCALE_NON16_SOURCE" in _codes(wa, wa.gates.scale_lint.check(m),
                                          "error")


def test_unknown_sheet_name_heuristic(wa):
    m = wa.base_map()
    m["layers"].append({"name": "buildings", "kind": "building", "tiles": [
        {"sheet": "ME_Barn_48x48", "region": [0, 0, 48, 48], "x": 0, "y": 0},
        {"sheet": "mystery", "region": [0, 0, 96, 48], "x": 3, "y": 0},
        {"sheet": "mystery", "region": [96, 0, 96, 48], "x": 9, "y": 0}]})
    findings = wa.gates.scale_lint.check(m)
    assert "SCALE_48PX_SOURCE" in _codes(wa, findings, "error")
    warns = _codes(wa, findings, "warn")
    assert warns.count("SCALE_SHEET_UNKNOWN") == 1   # once per sheet
    assert warns.count("SCALE_SUSPECT_48") == 2


def test_entity_band(wa):
    m = wa.base_map()
    m["layers"].append({"name": "officers", "kind": "entity", "tiles": [
        {"sheet": "charset", "region": [0, 0, 16, 32], "x": 0, "y": 0},   # ok
        {"sheet": "charset", "region": [0, 32, 16, 16], "x": 1, "y": 0},  # ok
        {"sheet": "charset", "region": [0, 48, 16, 48], "x": 2, "y": 0},  # tall
        {"sheet": "b48", "region": [0, 0, 48, 48], "x": 3, "y": 0}]})     # 3x
    findings = wa.gates.scale_lint.check(m)
    errs = _codes(wa, findings, "error")
    assert errs.count("SCALE_ENTITY_BAND") == 2
    assert "SCALE_48PX_SOURCE" in errs
