"""label_overlap: per-zoom overlaps, spam ratio, bounds, dims cross-check."""


def _labels(entries, w=200, h=160):
    return {"schema": "cabinet.world.labels/v1",
            "render": {"width": w, "height": h}, "labels": entries}


def test_disjoint_labels_pass(wa):
    findings = wa.gates.label_overlap.check(_labels([
        {"id": "a", "zoom": 0, "rect": [0, 0, 40, 12]},
        {"id": "b", "zoom": 0, "rect": [50, 0, 40, 12]},
        {"id": "c", "zoom": 0, "rect": [0, 20, 40, 12]}]))
    assert wa.errors(findings) == []


def test_same_zoom_overlap_fails_cross_zoom_passes(wa):
    findings = wa.gates.label_overlap.check(_labels([
        {"id": "a", "zoom": 1, "rect": [10, 10, 40, 12]},
        {"id": "b", "zoom": 1, "rect": [30, 15, 40, 12]},     # overlaps a
        {"id": "c", "zoom": 2, "rect": [10, 10, 40, 12]}]))   # other zoom
    errs = wa.errors(findings)
    assert [f["code"] for f in errs] == ["LABEL_OVERLAP"]
    assert errs[0]["data"]["zoom"] == 1


def test_spam_ratio_fails(wa):
    findings = wa.gates.label_overlap.check(_labels([
        {"id": "big", "zoom": 0, "rect": [0, 0, 150, 100]}]))  # 47% of render
    assert "LABEL_SPAM" in [f["code"] for f in wa.errors(findings)]


def test_chrome_is_sanctioned(wa):
    findings = wa.gates.label_overlap.check(_labels([
        {"id": "hud", "zoom": 0, "rect": [0, 0, 200, 120], "chrome": True},
        {"id": "a", "zoom": 0, "rect": [10, 130, 40, 12]}]))
    assert wa.errors(findings) == []


def test_out_of_bounds_warns(wa):
    findings = wa.gates.label_overlap.check(_labels([
        {"id": "a", "zoom": 0, "rect": [180, 150, 40, 20]}]))
    assert wa.errors(findings) == []
    assert "LABEL_OUT_OF_BOUNDS" in wa.codes(findings)


def test_png_dims_cross_check(wa, tmp_path):
    p = tmp_path / "r.png"
    wa.png.encode(p, 100, 80, bytes([0, 0, 0, 255]) * (100 * 80))
    findings = wa.gates.label_overlap.check(
        _labels([{"id": "a", "zoom": 0, "rect": [0, 0, 99, 79]}],
                w=200, h=160),
        image_path=p)
    assert "LABEL_RENDER_MISMATCH" in wa.codes(findings)
    # PNG dims win: 99x79 box is in-bounds for 100x80
    assert "LABEL_OUT_OF_BOUNDS" not in wa.codes(findings)


def test_bare_list_and_bad_rect(wa):
    findings = wa.gates.label_overlap.check([
        {"id": "a", "zoom": 0, "rect": [0, 0, 10, 10]},
        {"id": "broken", "zoom": 0}])
    assert "LABEL_BAD_RECT" in wa.codes(findings)
    assert "LABEL_NO_DIMS" in wa.codes(findings)
    assert wa.errors(findings) == []
