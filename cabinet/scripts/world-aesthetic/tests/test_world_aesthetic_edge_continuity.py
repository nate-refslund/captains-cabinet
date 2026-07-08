"""edge_continuity: convention data self-consistency + seam detection."""


def _island_map(wa, center_region=None):
    """6x6 dirt field with a 3x3 grass blob island at cells (1,1)..(3,3).
    Constructed straight from the blob3x3 convention -> zero seam breaks."""
    m = wa.base_map(6, 6)
    tiles = []
    island = {}
    for cy in range(3):
        for cx in range(3):
            island[(1 + cx, 1 + cy)] = wa.blob(cx, cy)
    if center_region is not None:
        island[(2, 2)] = center_region
    for y in range(6):
        for x in range(6):
            region = island.get((x, y), wa.SOLID_DIRT)
            tiles.append({"sheet": "outdoor", "region": region, "x": x, "y": y})
    m["layers"].append({"name": "ground", "kind": "terrain", "walkable": True,
                        "tiles": tiles})
    return m


def test_convention_data_internally_consistent(wa):
    """Every adjacent cell pair inside the blob3x3 block must be compatible —
    guards gates/data/autotile_conventions.json against typos."""
    conv = wa.gates.edge_continuity.load_conventions()
    cells = conv["conventions"]["blob3x3"]["cells"]
    sides = {}
    for key, rows in cells.items():
        cx, cy = map(int, key.split(","))
        sides[(cx, cy)] = wa.gates.edge_continuity._sides_from_subgrid(
            rows, "A", "B")
    for (cx, cy), s in sides.items():
        right = sides.get((cx + 1, cy))
        below = sides.get((cx, cy + 1))
        if right:
            assert s["E"] == right["W"], f"blob3x3 {cx},{cy} E vs {cx+1},{cy} W"
        if below:
            assert s["S"] == below["N"], f"blob3x3 {cx},{cy} S vs {cx},{cy+1} N"


def test_correct_island_passes(wa):
    findings = wa.gates.edge_continuity.check(_island_map(wa))
    assert wa.errors(findings) == []


def test_swapped_edge_tile_fails(wa):
    # Put a W-edge tile where the island center belongs -> seams break.
    m = _island_map(wa, center_region=wa.blob(0, 1))
    findings = wa.gates.edge_continuity.check(m)
    errs = wa.errors(findings)
    assert errs and all(f["code"] == "EDGE_MISMATCH" for f in errs)


def test_solid_wrong_terrain_fails(wa):
    # Solid DIRT dropped into the island center: dirt sides vs grass ring.
    m = _island_map(wa, center_region=wa.SOLID_DIRT)
    findings = wa.gates.edge_continuity.check(m)
    assert any(f["code"] == "EDGE_MISMATCH" for f in wa.errors(findings))


def test_unknown_region_is_wildcard_info(wa):
    m = _island_map(wa, center_region=[160, 160, 16, 16])  # no block match
    findings = wa.gates.edge_continuity.check(m)
    assert wa.errors(findings) == []
    assert "EDGE_UNKNOWN_TILE" in wa.codes(findings)


def test_non_terrain_layers_ignored(wa):
    m = wa.base_map(4, 4)
    m["layers"].append({"name": "props", "kind": "prop", "tiles": [
        {"sheet": "outdoor", "region": wa.blob(0, 0), "x": 0, "y": 0},
        {"sheet": "outdoor", "region": wa.blob(2, 2), "x": 1, "y": 0}]})
    assert wa.gates.edge_continuity.check(m) == []
