"""palette_coherence: synthetic calibrate -> native pass / foreign fail /
UI-chrome exclusion; plus real-corpus positives under the committed palette."""

import json

import pytest

W, H = 384, 320


def _write_scene(wa, tmp_path, name, seed):
    p = tmp_path / name
    wa.png.encode(p, W, H, wa.synth.make_textured_scene(seed, W, H))
    return p


def _fit(wa, tmp_path):
    paths = [_write_scene(wa, tmp_path, f"pos{i}.png", seed)
             for i, seed in enumerate((5, 6))]
    return wa.gates.palette_coherence.extract_palette(paths)


def _with_foreign_patch(wa, seed, x0=20, y0=20, pw=150, ph=150):
    buf = bytearray(wa.synth.make_textured_scene(seed, W, H))
    for y in range(y0, y0 + ph):
        for x in range(x0, x0 + pw):
            i = (y * W + x) * 4
            buf[i], buf[i + 1], buf[i + 2] = 255, 0, 255  # magenta — foreign
    return bytes(buf)


def test_native_scene_passes(wa, tmp_path):
    pal = _fit(wa, tmp_path)
    held_out = _write_scene(wa, tmp_path, "holdout.png", 9)
    findings = wa.gates.palette_coherence.check(held_out, palette=pal)
    assert wa.errors(findings) == []
    stats = [f for f in findings if f["code"] == "PALETTE_STATS"][0]
    assert stats["data"]["foreign_share"] < 0.01


def test_foreign_patch_fails(wa, tmp_path):
    pal = _fit(wa, tmp_path)
    p = tmp_path / "foreign.png"
    wa.png.encode(p, W, H, _with_foreign_patch(wa, 9))
    findings = wa.gates.palette_coherence.check(p, palette=pal)
    errs = wa.errors(findings)
    assert [f["code"] for f in errs] == ["PALETTE_FOREIGN_MASS"]
    assert errs[0]["data"]["foreign_share"] > 0.15


def test_ui_chrome_rect_is_sanctioned(wa, tmp_path):
    pal = _fit(wa, tmp_path)
    p = tmp_path / "chrome.png"
    wa.png.encode(p, W, H, _with_foreign_patch(wa, 9))
    findings = wa.gates.palette_coherence.check(
        p, palette=pal, config={"ui_rects": [[20, 20, 150, 150]]})
    assert wa.errors(findings) == []


def test_missing_palette_warns_then_errors_strict(wa, tmp_path):
    p = _write_scene(wa, tmp_path, "s.png", 5)
    findings = wa.gates.palette_coherence.check(p, palette=None)
    assert wa.codes(findings) == ["CALIBRATION_MISSING"]
    assert findings[0]["severity"] == "warn"
    strict = wa.gates.palette_coherence.check(
        p, palette=None, config={"strict_calibration": True})
    assert strict[0]["severity"] == "error"


def test_palette_json_is_derived_numbers_only(wa, tmp_path):
    """License guard: the committable palette carries bins + hashes, never
    pixel data of the corpus images."""
    pal = _fit(wa, tmp_path)
    dumped = json.dumps(pal)
    assert len(dumped) < 200_000
    assert set(pal) <= {"schema", "quant_bits", "neighbor_radius",
                        "min_bin_share", "bins", "colors_rgb_sample",
                        "fitted_from", "source_pixels", "generated",
                        "generator"}


def test_real_corpus_positives_pass_committed_palette(wa):
    if not wa.has_corpus:
        pytest.skip("gitignored corpus not present")
    pal_path = wa.calib_dir / "palette.json"
    if not pal_path.is_file():
        pytest.skip("no committed palette calibration")
    for p in sorted((wa.corpus_dir / "positive").glob("*.png")):
        findings = wa.gates.palette_coherence.check(p, palette=pal_path)
        assert wa.errors(findings) == [], f"{p.name} flagged foreign"
