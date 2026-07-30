"""aesthetic_gates.py runner end-to-end + calibrate.py fit/prove contract.

Everything here is corpus-independent (license-free synthetic fixtures in
tmp_path) except the final real-corpus prove test, which skips on a clean
clone where the gitignored corpus is absent.
"""

import json

import pytest

W, H = 384, 320


def _run(wa, capsys, argv):
    rc = wa.runner.main([str(a) for a in argv])
    out = capsys.readouterr().out
    return rc, (json.loads(out) if out.strip() else None)


def _clean_map(wa):
    m = wa.base_map(12, 8)
    m["anchor"] = [1, 1]
    ground = [{"sheet": "outdoor", "region": wa.SOLID_GRASS, "x": x, "y": y}
              for y in range(8) for x in range(12)]
    m["layers"] += [
        {"name": "ground", "kind": "terrain", "walkable": True,
         "tiles": ground},
        {"name": "buildings", "kind": "building", "tiles": [
            {"sheet": "props", "region": [0, 0, 32, 32], "x": 5, "y": 2}]},
        {"name": "doors", "kind": "door", "tiles": [
            {"sheet": "props", "region": [0, 32, 16, 16], "x": 5, "y": 3}]},
        {"name": "props", "kind": "prop", "tiles": [
            {"sheet": "props", "region": [0, 0, 16, 16], "x": x, "y": y}
            for (x, y) in ((2, 5), (3, 5), (2, 6))]},
    ]
    return m


def _fixtures(wa, tmp_path):
    """Map + render + labels + SELF-FITTED calibrations (no corpus needed)."""
    fx = {}
    map_p = tmp_path / "map.json"
    map_p.write_text(json.dumps(_clean_map(wa)))
    fx["map"] = map_p

    render_p = tmp_path / "render.png"
    wa.png.encode(render_p, W, H, wa.synth.make_textured_scene(5, W, H))
    fx["render"] = render_p

    pal = wa.gates.palette_coherence.extract_palette([render_p])
    pal_p = tmp_path / "palette.json"
    pal_p.write_text(json.dumps(pal))
    fx["palette"] = pal_p

    istats = wa.gates.clustering.image_stats(render_p)
    image_block = wa.calibrate.fit_image_bounds([istats])
    image_block["params"] = istats["params"]
    mstats = [wa.gates.clustering.map_stats(wa.synth.make_clustered_map(s))
              for s in (11, 12, 13)]
    map_block = wa.calibrate.fit_map_bounds(mstats)
    map_block["params"] = mstats[0]["params"]
    bounds_p = tmp_path / "bounds.json"
    bounds_p.write_text(json.dumps(
        {"schema": "cabinet.world.clustering-bounds/v1",
         "map": map_block, "image": image_block}))
    fx["bounds"] = bounds_p

    labels_p = tmp_path / "labels.json"
    labels_p.write_text(json.dumps(
        {"schema": "cabinet.world.labels/v1",
         "render": {"width": W, "height": H},
         "labels": [
             {"id": "hq", "text": "HQ", "zoom": 1, "rect": [10, 10, 60, 14]},
             {"id": "dock", "text": "Dock", "zoom": 1,
              "rect": [200, 230, 70, 14]},
             {"id": "hud", "text": "menu", "zoom": 1,
              "rect": [0, 300, W, 20], "chrome": True}]}))
    fx["labels"] = labels_p
    return fx


# ------------------------------------------------------------- end-to-end

def test_clean_scene_exits_0_all_gates_run(wa, tmp_path, capsys):
    fx = _fixtures(wa, tmp_path)
    rc, env = _run(wa, capsys, [
        "--map", fx["map"], "--render", fx["render"],
        "--labels", fx["labels"], "--palette", fx["palette"],
        "--bounds", fx["bounds"]])
    assert rc == 0
    assert env["schema"] == "cabinet.world.aesthetic-findings/v1"
    assert env["ok"] is True
    assert env["counts"]["error"] == 0
    assert env["gates_run"] == list(wa.gates.GATE_ORDER)
    assert env["skipped"] == []


def test_bad_scene_exits_1_with_findings_across_gates(wa, tmp_path, capsys):
    fx = _fixtures(wa, tmp_path)
    # The full anti-showcase: scatter map (no ground, 48px barn), flat-void
    # render, overlapping+spam labels — against the SAME clean calibrations.
    m = wa.synth.make_scatter_map(7, n=60)
    m["sheets"]["b48"] = {"grid": 48}
    m["layers"].append({"name": "barn", "kind": "building", "tiles": [
        {"sheet": "b48", "region": [0, 0, 48, 48], "x": 1, "y": 1}]})
    bad_map = tmp_path / "bad_map.json"
    bad_map.write_text(json.dumps(m))
    bad_render = tmp_path / "bad_render.png"
    wa.png.encode(bad_render, W, H,
                  wa.synth.make_flat_scatter_scene(3, w=W, h=H))
    bad_labels = tmp_path / "bad_labels.json"
    bad_labels.write_text(json.dumps([
        {"id": f"l{i}", "zoom": 0, "rect": [40 + 12 * i, 60, 150, 40]}
        for i in range(4)]))

    rc, env = _run(wa, capsys, [
        "--map", bad_map, "--render", bad_render, "--labels", bad_labels,
        "--palette", fx["palette"], "--bounds", fx["bounds"]])
    assert rc == 1
    assert env["ok"] is False
    codes = {f["code"] for f in env["findings"] if f["severity"] == "error"}
    assert {"CONNECT_NO_WALKABLE", "SCALE_48PX_SOURCE", "LABEL_OVERLAP",
            "LABEL_SPAM", "PALETTE_FOREIGN_MASS", "CLUSTER_SCATTER",
            "CLUSTER_FLAT_VOID"} <= codes


# ----------------------------------------------------- CLI contract bits

def test_unusable_invocations_exit_2(wa, tmp_path, capsys):
    assert _run(wa, capsys, [])[0] == 2
    fx = _fixtures(wa, tmp_path)
    assert _run(wa, capsys,
                ["--map", fx["map"], "--only", "nope"])[0] == 2
    bad = tmp_path / "broken.json"
    bad.write_text("{not json")
    assert _run(wa, capsys, ["--map", bad])[0] == 2
    assert _run(wa, capsys,
                ["--map", fx["map"], "--render",
                 tmp_path / "missing.png"])[0] == 2
    assert _run(wa, capsys,
                ["--map", fx["map"], "--ui-rects",
                 tmp_path / "missing.json"])[0] == 2
    not_a_map = tmp_path / "not_a_map.json"
    not_a_map.write_text(json.dumps({"schema": "other/v1"}))
    assert _run(wa, capsys, ["--map", not_a_map])[0] == 2


def test_only_subset_and_skip(wa, tmp_path, capsys):
    fx = _fixtures(wa, tmp_path)
    rc, env = _run(wa, capsys, ["--map", fx["map"],
                                "--only", "connectivity,scale_lint"])
    assert rc == 0
    assert env["gates_run"] == ["connectivity", "scale_lint"]
    assert env["skipped"] == []
    rc, env = _run(wa, capsys, ["--map", fx["map"], "--skip", "clustering"])
    assert "clustering" not in env["gates_run"]


def test_missing_inputs_are_skipped_not_silent(wa, tmp_path, capsys):
    fx = _fixtures(wa, tmp_path)
    rc, env = _run(wa, capsys, ["--map", fx["map"]])
    assert rc == 0  # clustering CALIBRATION_MISSING is a warn, not an error
    assert {s["gate"] for s in env["skipped"]} == \
        {"label_overlap", "palette_coherence"}
    assert "GATE_SKIPPED" in {f["code"] for f in env["findings"]}
    assert env["counts"]["warn"] >= 1


def test_strict_escalates_warnings(wa, tmp_path, capsys):
    fx = _fixtures(wa, tmp_path)
    rc, _ = _run(wa, capsys, ["--map", fx["map"], "--strict"])
    assert rc == 1  # the CALIBRATION_MISSING warn now fails


def test_out_writes_envelope(wa, tmp_path, capsys):
    fx = _fixtures(wa, tmp_path)
    out_p = tmp_path / "findings.json"
    rc, env = _run(wa, capsys, ["--map", fx["map"], "--out", out_p])
    assert rc == 0
    assert json.loads(out_p.read_text()) == env


def test_gate_crash_is_contained(wa, tmp_path, capsys):
    fx = _fixtures(wa, tmp_path)
    bad_bounds = tmp_path / "bad_bounds.json"
    bad_bounds.write_text("{corrupt")
    rc, env = _run(wa, capsys,
                   ["--map", fx["map"], "--bounds", bad_bounds])
    assert rc == 1
    crashes = [f for f in env["findings"] if f["code"] == "GATE_CRASH"]
    assert [f["gate"] for f in crashes] == ["clustering"]
    # the crash must not take the other gates down with it
    assert {"edge_continuity", "connectivity", "scale_lint"} <= \
        set(env["gates_run"])


# ------------------------------------------------------------- calibrate

def test_fit_bounds_guards(wa):
    with pytest.raises(ValueError):
        wa.calibrate.fit_map_bounds([])
    with pytest.raises(ValueError):
        wa.calibrate.fit_image_bounds(
            [{"flat_mass": None, "dominant_share": None, "busy_cv": None}])


def test_fit_map_bounds_margins(wa):
    stats = [wa.gates.clustering.map_stats(wa.synth.make_clustered_map(s))
             for s in (11, 12, 13)]
    b = wa.calibrate.fit_map_bounds(stats)
    assert b["r_max"] > max(s["r"] for s in stats)
    assert b["open_min"] < min(s["open_ratio"] for s in stats)


def test_calibrate_prove_real_corpus(wa, capsys):
    """The offline separation proof over the REAL corpus: every negative
    trips, every positive passes, against the COMMITTED calibrations."""
    # `prove` reads the corpus DIRECTORY, so it needs both classes present —
    # and the positive class is held in full on a fresh checkout.
    wa.require("negative")
    wa.require("positive")
    rc = wa.calibrate.main(["prove"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "PROVE OK" in out
