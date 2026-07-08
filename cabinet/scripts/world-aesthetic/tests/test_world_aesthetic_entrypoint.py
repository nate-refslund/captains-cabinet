"""world-aesthetic-gate.py — the ONE entrypoint: mode dispatch + wiring.

Corpus-independent (synthetic tmp fixtures throughout, same contract as the
runner/judge suites): a clean clone with no licensed corpus proves the
dispatcher. The real-corpus behavior is pinned by the self-test in the
ledger row (WORLD-AESTHETIC-GATE) and test_calibrate_prove_real_corpus.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

WA_DIR = Path(__file__).resolve().parents[1]

W, H = 384, 320


def _load(name: str, path: Path):
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return mod


@pytest.fixture(scope="module")
def gate():
    return _load("world_aesthetic_gate_entry",
                 WA_DIR / "world-aesthetic-gate.py")


@pytest.fixture(scope="module")
def judge():
    loader = _load("world_aesthetic_loader", WA_DIR / "_loader.py")
    return loader.load_judge()


def _run(gate, capsys, argv):
    rc = gate.main([str(a) for a in argv])
    out = capsys.readouterr().out
    env = None
    if out.strip().startswith("{"):
        env = json.loads(out[out.index("{"):out.rindex("}") + 1])
    return rc, env, out


def _clean_fixtures(wa, tmp_path):
    """Clean map + textured render + SELF-FITTED calibrations (no corpus)."""
    m = wa.base_map(12, 8)
    ground = [{"sheet": "outdoor", "region": wa.SOLID_GRASS, "x": x, "y": y}
              for y in range(8) for x in range(12)]
    m["layers"].append({"name": "ground", "kind": "terrain",
                        "walkable": True, "tiles": ground})
    map_p = tmp_path / "map.json"
    map_p.write_text(json.dumps(m))

    render_p = tmp_path / "render.png"
    wa.png.encode(render_p, W, H, wa.synth.make_textured_scene(5, W, H))

    pal_p = tmp_path / "palette.json"
    pal_p.write_text(json.dumps(
        wa.gates.palette_coherence.extract_palette([render_p])))

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
    return {"map": map_p, "render": render_p,
            "palette": pal_p, "bounds": bounds_p}


def _tmp_corpus(judge, root: Path):
    """Tiny synthetic judge corpus (manifest + sha256, 2 pos / 1 neg)."""
    png = judge._corpus.png_codec()
    corpus = root / "corpus"
    images = []
    for i in range(2):
        f = corpus / "positive" / f"pos-{i}.png"
        f.parent.mkdir(parents=True, exist_ok=True)
        png.encode(f, 8, 8, bytes((10 + i * 40, 200, 60, 255)) * 64)
        images.append({"id": f"pos-{i}", "class": "positive",
                       "file": f"corpus/positive/pos-{i}.png",
                       "sha256": judge._corpus.sha256_of(f),
                       "provenance": "synthetic-test", "why": "test"})
    f = corpus / "negative" / "neg-0.png"
    f.parent.mkdir(parents=True, exist_ok=True)
    png.encode(f, 8, 8, bytes((90, 30, 190, 255)) * 64)
    images.append({"id": "neg-0", "class": "negative",
                   "file": "corpus/negative/neg-0.png",
                   "sha256": judge._corpus.sha256_of(f),
                   "provenance": "synthetic-test", "why": "test"})
    judge._corpus.atomic_write_json(corpus / "manifest.json", {
        "purpose": "test", "note": "test",
        "counts": {"positive": 2, "negative": 1}, "images": images})
    return corpus


# ------------------------------------------------------------ mode dispatch

def test_mode_is_required_and_exclusive(gate, capsys):
    with pytest.raises(SystemExit) as e:
        gate.main([])
    assert e.value.code == 2
    with pytest.raises(SystemExit) as e:
        gate.main(["--mechanical", "--calibrate"])
    assert e.value.code == 2
    capsys.readouterr()


def test_mechanical_no_inputs_exits_2(gate, capsys):
    rc, _, _ = _run(gate, capsys, ["--mechanical"])
    assert rc == 2


# ------------------------------------------------------------- --mechanical

def test_mechanical_wires_committed_calibrations_by_default(
        gate, wa, tmp_path, capsys):
    fx = _clean_fixtures(wa, tmp_path)
    rc, env, _ = _run(gate, capsys,
                      ["--mechanical", "--map", fx["map"],
                       "--render", fx["render"]])
    assert env is not None
    if (WA_DIR / "calibration" / "palette.json").is_file():
        assert env["inputs"]["palette"] == \
            str(WA_DIR / "calibration" / "palette.json")
        assert env["inputs"]["bounds"] == \
            str(WA_DIR / "calibration" / "clustering_bounds.json")
    else:  # clean clone: defaults absent -> forwarded as absent, not invented
        assert "palette" not in env["inputs"]


def test_mechanical_explicit_calibrations_override_defaults(
        gate, wa, tmp_path, capsys):
    fx = _clean_fixtures(wa, tmp_path)
    rc, env, _ = _run(gate, capsys, [
        "--mechanical", "--map", fx["map"], "--render", fx["render"],
        "--palette", fx["palette"], "--bounds", fx["bounds"]])
    assert rc == 0
    assert env["ok"] is True
    assert env["inputs"]["palette"] == str(fx["palette"])
    assert env["counts"]["error"] == 0


def test_mechanical_failure_propagates_exit_1(gate, wa, tmp_path, capsys):
    fx = _clean_fixtures(wa, tmp_path)
    bad_map = tmp_path / "bad_map.json"
    bad_map.write_text(json.dumps(wa.synth.make_scatter_map(7, n=60)))
    rc, env, _ = _run(gate, capsys, [
        "--mechanical", "--map", bad_map,
        "--palette", fx["palette"], "--bounds", fx["bounds"]])
    assert rc == 1
    codes = {f["code"] for f in env["findings"]
             if f["severity"] == "error"}
    assert "CLUSTER_SCATTER" in codes or "CONNECT_NO_WALKABLE" in codes


# ------------------------------------------------------------------- --full

def test_full_refuses_judge_when_mechanical_fails(gate, wa, tmp_path,
                                                  capsys):
    fx = _clean_fixtures(wa, tmp_path)
    bad_map = tmp_path / "bad_map.json"
    bad_map.write_text(json.dumps(wa.synth.make_scatter_map(7, n=60)))
    out_root = tmp_path / "runs"
    rc = gate.main(["--full", "--map", str(bad_map),
                    "--render", str(fx["render"]),
                    "--palette", str(fx["palette"]),
                    "--bounds", str(fx["bounds"]),
                    "--out-root", str(out_root)])
    err = capsys.readouterr().err
    assert rc == 1
    assert "vision-judge run not built" in err
    assert not out_root.exists()  # no bundle for a frame below the floor


def test_full_needs_render_candidate(gate, wa, tmp_path, capsys):
    fx = _clean_fixtures(wa, tmp_path)
    rc = gate.main(["--full", "--map", str(fx["map"]),
                    "--palette", str(fx["palette"]),
                    "--bounds", str(fx["bounds"])])
    assert rc == 2
    assert "--render" in capsys.readouterr().err


def test_full_emits_judge_bundle_on_mechanical_pass(gate, wa, judge,
                                                    tmp_path, capsys,
                                                    monkeypatch):
    fx = _clean_fixtures(wa, tmp_path)
    corpus = _tmp_corpus(judge, tmp_path)
    # Route the judge at the tmp corpus (build reads module defaults).
    monkeypatch.setattr(judge._corpus, "CORPUS_DIR", corpus)
    out_root = tmp_path / "runs"
    rc = gate.main(["--full", "--map", str(fx["map"]),
                    "--render", str(fx["render"]),
                    "--palette", str(fx["palette"]),
                    "--bounds", str(fx["bounds"]),
                    "--seed", "77", "--out-root", str(out_root)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "run bundle:" in out
    runs = list(out_root.iterdir())
    assert len(runs) == 1
    tasks = json.loads((runs[0] / "tasks.json").read_text())
    assert tasks["schema"] == "cabinet.world.judge-tasks/v1"
    # 2 cal pairs (2 pos x 1 neg) + 3 candidate pairs (2 pos + 1 neg)
    assert len(tasks["tasks"]) == 5


# -------------------------------------------------------------- --calibrate

def test_calibrate_fits_and_proves_on_tmp_corpus(gate, wa, tmp_path,
                                                 capsys):
    corpus = tmp_path / "corpus"
    (corpus / "positive").mkdir(parents=True)
    (corpus / "negative").mkdir(parents=True)
    for i, seed in enumerate((5, 6)):
        wa.png.encode(corpus / "positive" / f"pos-{i}.png", W, H,
                      wa.synth.make_textured_scene(seed, W, H))
    wa.png.encode(corpus / "negative" / "neg-0.png", W, H,
                  wa.synth.make_flat_scatter_scene(3, w=W, h=H))
    out_dir = tmp_path / "calib"
    rc = gate.main(["--calibrate", "--corpus", str(corpus),
                    "--calib-out-dir", str(out_dir)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "PROVE OK" in out
    assert (out_dir / "palette.json").is_file()
    assert (out_dir / "clustering_bounds.json").is_file()
