"""connectivity: BFS anchor->doors over walkable cells + occupancy rules."""


def _town(wa, ring=False):
    """10x8 walkable dirt, 2x2 building at (4,2), door punched at (4,3)."""
    m = wa.base_map(10, 8)
    m["anchor"] = [1, 1]
    ground = [{"sheet": "outdoor", "region": wa.SOLID_DIRT, "x": x, "y": y}
              for y in range(8) for x in range(10)]
    m["layers"].append({"name": "ground", "kind": "terrain", "walkable": True,
                        "tiles": ground})
    m["layers"].append({"name": "buildings", "kind": "building", "tiles": [
        {"sheet": "props", "region": [0, 0, 32, 32], "x": 4, "y": 2}]})
    m["layers"].append({"name": "doors", "kind": "door", "tiles": [
        {"sheet": "props", "region": [0, 32, 16, 16], "x": 4, "y": 3}]})
    if ring:
        cells = set()
        for x in range(3, 7):
            cells.add((x, 1)); cells.add((x, 4))
        for y in range(1, 5):
            cells.add((3, y)); cells.add((6, y))
        m["layers"].append({"name": "walls", "kind": "collision", "tiles": [
            {"sheet": "props", "region": [16, 0, 16, 16], "x": x, "y": y}
            for (x, y) in sorted(cells)]})
    return m


def test_door_reachable_passes(wa):
    findings = wa.gates.connectivity.check(_town(wa))
    assert wa.errors(findings) == []
    stats = [f for f in findings if f["code"] == "CONNECT_STATS"][0]
    assert stats["data"]["doors"] == 1
    assert stats["data"]["unreachable_doors"] == 0


def test_walled_off_door_fails(wa):
    findings = wa.gates.connectivity.check(_town(wa, ring=True))
    errs = wa.errors(findings)
    assert [f["code"] for f in errs] == ["CONNECT_DOOR_UNREACHABLE"]
    assert errs[0]["where"]["cell"] == [4, 3]


def test_anchor_on_collision_fails(wa):
    m = _town(wa)
    m["layers"].append({"name": "rock", "kind": "collision", "tiles": [
        {"sheet": "props", "region": [16, 0, 16, 16], "x": 1, "y": 1}]})
    findings = wa.gates.connectivity.check(m)
    assert "CONNECT_ANCHOR_UNWALKABLE" in [f["code"] for f in wa.errors(findings)]


def test_no_doors_is_info(wa):
    m = _town(wa)
    m["layers"] = [l for l in m["layers"] if l["kind"] != "door"]
    findings = wa.gates.connectivity.check(m)
    assert wa.errors(findings) == []
    assert "CONNECT_NO_DOORS" in wa.codes(findings)


def test_missing_anchor_fails(wa):
    m = _town(wa)
    del m["anchor"]
    findings = wa.gates.connectivity.check(m)
    assert [f["code"] for f in wa.errors(findings)] == ["CONNECT_NO_ANCHOR"]


def test_building_footprint_blocks(wa):
    """The 32x32 building must block all 4 covered cells except the door."""
    occ = wa.common.build_occupancy(_town(wa))
    assert (4, 2) not in occ["walkable"]
    assert (5, 2) not in occ["walkable"]
    assert (5, 3) not in occ["walkable"]
    assert (4, 3) in occ["walkable"]          # door punches through
    assert (4, 3) in occ["doors"]


def test_explicit_walkable_override(wa):
    m = wa.base_map(3, 3)
    m["layers"].append({"name": "ground", "kind": "terrain", "walkable": True,
                        "tiles": [{"sheet": "outdoor", "region": wa.SOLID_DIRT,
                                   "x": 0, "y": 0},
                                  {"sheet": "outdoor", "region": wa.SOLID_DIRT,
                                   "x": 1, "y": 0, "walkable": False}]})
    m["layers"].append({"name": "crate", "kind": "prop", "tiles": [
        {"sheet": "props", "region": [0, 0, 16, 16], "x": 2, "y": 0,
         "walkable": True}]})
    occ = wa.common.build_occupancy(m)
    assert (0, 0) in occ["walkable"]
    assert (1, 0) not in occ["walkable"]      # explicit tile False blocks
    assert (2, 0) in occ["walkable"]          # explicit True punches prop block
