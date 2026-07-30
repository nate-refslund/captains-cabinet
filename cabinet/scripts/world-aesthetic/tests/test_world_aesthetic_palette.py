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
    wa.require("positive")
    pal_path = wa.calib_dir / "palette.json"
    assert pal_path.is_file(), (
        "calibration/palette.json is TRACKED — its absence is a broken checkout, "
        "not a reason to skip the only arm that pins the committed palette")
    for p in wa.corpus("positive"):
        findings = wa.gates.palette_coherence.check(p, palette=pal_path)
        assert wa.errors(findings) == [], f"{p.name} flagged foreign"


# ----------------------------------------- the palette separation proof
# calibrate.py prove_palette is the ONLY thing asserting that
# palette_coherence still discriminates. Against the pre-2026-07-28 LimeZu
# corpus the gate passed 3 of its own 5 negatives, and nothing noticed,
# because there was no palette arm in prove at all. These tests are that
# arm's arm: each one fails if prove_palette stops being able to fail.

def _mini_corpus(wa, tmp_path, foreign_negative=False):
    """A 2-positive / 1-owned-negative corpus in the real directory shape."""
    corpus = tmp_path / "corpus"
    (corpus / "positive").mkdir(parents=True)
    (corpus / "negative").mkdir(parents=True)
    for i, seed in enumerate((5, 6)):
        wa.png.encode(corpus / "positive" / f"pos-{i}.png", W, H,
                      wa.synth.make_textured_scene(seed, W, H))
    # An owned-family negative: same colours, broken composition. P2 requires
    # the palette gate to PASS it — its defect belongs to clustering.
    buf = (_with_foreign_patch(wa, 8) if foreign_negative
           else wa.synth.make_flat_scatter_scene(3, 30, W, H, bg=(96, 160, 96)))
    wa.png.encode(corpus / "negative" / "neg-owned-scatter.png", W, H, buf)
    return corpus


def test_prove_palette_passes_a_real_fit(wa, tmp_path):
    corpus = _mini_corpus(wa, tmp_path)
    pal = wa.gates.palette_coherence.extract_palette(
        sorted((corpus / "positive").glob("*.png")))
    violations, not_run = wa.calibrate.prove_palette(wa.gates, corpus, pal)
    assert violations == []
    # No archived corpus in a tmp dir -> P5 must be declared NOT RUN, never
    # silently counted as a pass.
    assert any("P5" in n for n in not_run)


def test_prove_palette_FAILS_a_dead_palette(wa, tmp_path):
    """The mutation arm: a palette that admits the entire colour cube cannot
    discriminate anything, and the proof must say so. If this ever passes,
    prove_palette has become decorative."""
    corpus = _mini_corpus(wa, tmp_path)
    pal = wa.gates.palette_coherence.extract_palette(
        sorted((corpus / "positive").glob("*.png")))
    dead = dict(pal, bins=list(range(1 << (3 * pal["quant_bits"]))))
    violations, _ = wa.calibrate.prove_palette(wa.gates, corpus, dead)
    assert any(v.startswith("P3") for v in violations), violations
    assert any(v.startswith("P4") for v in violations), violations


def test_prove_palette_FAILS_when_an_owned_negative_is_failed_by_colour(
        wa, tmp_path):
    """P2 is not vacuous: an owned-art negative carrying genuinely foreign
    colour must be reported, because the palette gate blaming a composition
    defect on colour is a mis-attribution, not a catch."""
    corpus = _mini_corpus(wa, tmp_path, foreign_negative=True)
    pal = wa.gates.palette_coherence.extract_palette(
        sorted((corpus / "positive").glob("*.png")))
    violations, _ = wa.calibrate.prove_palette(wa.gates, corpus, pal)
    assert any(v.startswith("P2") for v in violations), violations


def test_channel_rotation_bite_arm_is_clustering_blind(wa, tmp_path):
    """The P3 arm's whole value is that no other gate can see it. Pin the
    property: identical flat_mass and dominant_share before and after."""
    src = tmp_path / "src.png"
    wa.png.encode(src, W, H, wa.synth.make_textured_scene(5, W, H))
    dst = tmp_path / "rot.png"
    wa.calibrate._channel_rotated(wa.gates, src, dst)
    a = wa.gates.clustering.image_stats(src)
    b = wa.gates.clustering.image_stats(dst)
    assert a["flat_mass"] == b["flat_mass"]
    assert a["dominant_share"] == b["dominant_share"]
    # …and it really is a different image.
    assert src.read_bytes() != dst.read_bytes()
