"""Tests for cabinet/scripts/world-asset-intake.py — artist-delivery intake.

Synthetic in-test PNG fixtures ONLY (PIL Image.new — never licensed
pixels), tmp asset roots via explicit --assets-root/--manifest flags,
in-process main(argv), the aesthetic-gate subprocess seam mocked (plus one
real-wrapper smoke run over a tiny local scene). Zero network anywhere.
Module load follows the house importlib-by-path pattern
(test_world_asset_forge.py:23-34).
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

_SCRIPTS = Path(__file__).resolve().parents[1]
_REPO = Path(__file__).resolve().parents[3]


def _load(modname: str, filename: str):
    spec = importlib.util.spec_from_file_location(modname,
                                                  _SCRIPTS / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


intake = _load("world_asset_intake", "world-asset-intake.py")
gate = _load("world_asset_gate_for_intake", "world-asset-gate.py")

STRIP_COLORS = [(0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255)]


# ---------------------------------------------------------------- helpers
def _entry(eid: str, w=32, h=32, **kw) -> dict:
    return {
        "id": eid, "section": "test",
        "object": kw.pop("object", "testobj"),
        "size": ({"w": w, "h": h} if w is not None else None),
        "animated": kw.pop("animated", False),
        "frames": kw.pop("frames", None),
        "covered_by": kw.pop("covered_by", None),
        "staged": kw.pop("staged", False),
        "meaning": f"test sprite {eid}",
        **kw,
    }


def _worklist(path: Path, entries: list[dict]) -> Path:
    path.write_text(json.dumps(
        {"schema": "cabinet.world.asset-worklist/v1", "entries": entries}))
    return path


def _sprite(path: Path, w=32, h=32, fill=(200, 30, 30, 255), mode="RGBA",
            pixels=None) -> Path:
    img = Image.new(mode, (w, h), fill)
    for xy, c in (pixels or {}).items():
        img.putpixel(xy, c)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def _strip_png(path: Path, colors=STRIP_COLORS) -> Path:
    img = Image.new("RGBA", (len(colors), 1))
    img.putdata([c + (255,) for c in colors])
    img.save(path)
    return path


def _mini_manifest(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    mp = root / "manifest.json"
    mp.write_text(json.dumps({"_doc": "test manifest", "version": 3,
                              "assets": []}, indent=1, ensure_ascii=False)
                  + "\n")
    return mp


def _report(delivery: Path) -> dict:
    return json.loads((delivery / "_intake" / "report.json").read_text())


def _one_file_batch(tmp_path: Path, entries=None, **sprite_kw):
    """Delivery dir with one valid a.png + matching worklist. Returns
    (delivery_dir, worklist_path)."""
    dd = tmp_path / "batch-01"
    dd.mkdir(exist_ok=True)
    _sprite(dd / "a.png", **sprite_kw)
    wl = _worklist(tmp_path / "wl.json", entries or [_entry("a")])
    return dd, wl


# ---------------------------------------------------------------- naming
def test_unknown_id_rejected_with_suggestion(tmp_path):
    dd = tmp_path / "d"
    dd.mkdir()
    _sprite(dd / "ladder.firepit.campfyre.png")
    wl = _worklist(tmp_path / "wl.json",
                   [_entry("ladder.firepit.campfire")])
    rc = intake.main([str(dd), "--worklist", str(wl)])
    assert rc == 1
    rec = _report(dd)["files"][0]
    assert rec["status"] == "fix_needed"
    assert rec["id"] is None
    joined = " ".join(rec["reasons"])
    assert "unknown worklist id" in joined
    assert "ladder.firepit.campfire" in joined      # did-you-mean

    md = (dd / "_intake" / "report.md").read_text()
    assert "ladder.firepit.campfyre.png" in md


def test_nested_dir_ignored_nonpng_and_dotfile_handling(tmp_path):
    dd = tmp_path / "d"
    (dd / "nested").mkdir(parents=True)
    _sprite(dd / "nested" / "a.png")            # nested: ignored entirely
    _sprite(dd / "a.png")
    (dd / "notes.txt").write_text("hello")      # non-png: fix_needed
    (dd / ".DS_Store").write_bytes(b"\x00")     # dotfile: skipped silently
    wl = _worklist(tmp_path / "wl.json", [_entry("a")])
    rc = intake.main([str(dd), "--worklist", str(wl)])
    assert rc == 1
    rep = _report(dd)
    assert rep["counts"] == {"files": 2, "accepted": 1, "fix_needed": 1}
    by_file = {f["file"]: f for f in rep["files"]}
    assert by_file["a.png"]["status"] == "accepted"
    assert "not a .png delivery" in by_file["notes.txt"]["reasons"][0]
    assert ".DS_Store" not in by_file
    assert not any("nested" in f["file"] for f in rep["files"])


def test_empty_delivery_refused(tmp_path):
    dd = tmp_path / "d"
    dd.mkdir()
    wl = _worklist(tmp_path / "wl.json", [_entry("a")])
    assert intake.main([str(dd), "--worklist", str(wl)]) == 2


# ---------------------------------------------------------------- sizes
def test_static_exact_size_accepted_and_mismatch_reason(tmp_path):
    dd = tmp_path / "d"
    dd.mkdir()
    _sprite(dd / "ok.png", 48, 32)
    _sprite(dd / "bad.png", 32, 32)
    wl = _worklist(tmp_path / "wl.json",
                   [_entry("ok", 48, 32), _entry("bad", 48, 32)])
    rc = intake.main([str(dd), "--worklist", str(wl)])
    assert rc == 1
    by_file = {f["file"]: f for f in _report(dd)["files"]}
    assert by_file["ok.png"]["status"] == "accepted"
    assert by_file["ok.png"]["expected"] == {"w": 48, "h": 32,
                                             "frames": None}
    bad = by_file["bad.png"]
    assert bad["status"] == "fix_needed"
    assert bad["actual"] == {"w": 32, "h": 32}
    assert any("expected 48x32" in r and "got 32x32" in r
               for r in bad["reasons"])


def test_animated_strip_accepted_single_frame_explained(tmp_path):
    dd = tmp_path / "d"
    dd.mkdir()
    _sprite(dd / "anim.ok.png", 64, 32)         # 2 frames of 32x32
    _sprite(dd / "anim.short.png", 32, 32)      # one frame only
    entries = [_entry("anim.ok", 32, 32, animated=True, frames=2),
               _entry("anim.short", 32, 32, animated=True, frames=2)]
    wl = _worklist(tmp_path / "wl.json", entries)
    rc = intake.main([str(dd), "--worklist", str(wl)])
    assert rc == 1
    by_file = {f["file"]: f for f in _report(dd)["files"]}
    ok = by_file["anim.ok.png"]
    assert ok["status"] == "accepted"
    assert ok["expected"] == {"w": 64, "h": 32, "frames": 2}
    short = by_file["anim.short.png"]
    assert short["status"] == "fix_needed"
    reason = " ".join(short["reasons"])
    assert "expected 64x32" in reason
    assert "2 frames of 32x32" in reason
    assert "horizontal strip" in reason
    assert "got 32x32" in reason


def test_off_grid_flagged(tmp_path):
    dd = tmp_path / "d"
    dd.mkdir()
    _sprite(dd / "a.png", 24, 24)
    wl = _worklist(tmp_path / "wl.json", [_entry("a", 24, 24)])
    rc = intake.main([str(dd), "--worklist", str(wl)])
    assert rc == 1
    rec = _report(dd)["files"][0]
    assert any("off the 16px art grid" in r for r in rec["reasons"])


# ---------------------------------------------------------------- alpha
def test_rgb_without_alpha_rejected(tmp_path):
    dd, wl = _one_file_batch(tmp_path, mode="RGB", fill=(200, 30, 30))
    rc = intake.main([str(dd), "--worklist", str(wl)])
    assert rc == 1
    rec = _report(dd)["files"][0]
    assert any("no alpha channel" in r and "RGBA" in r
               for r in rec["reasons"])


def test_non_png_magic_rejected(tmp_path):
    dd = tmp_path / "d"
    dd.mkdir()
    (dd / "a.png").write_bytes(b"JFIF definitely not a png")
    wl = _worklist(tmp_path / "wl.json", [_entry("a")])
    rc = intake.main([str(dd), "--worklist", str(wl)])
    assert rc == 1
    rec = _report(dd)["files"][0]
    assert any("not a PNG (magic bytes)" in r for r in rec["reasons"])


# ---------------------------------------------------------------- halo
def _halo_sprite(path: Path, n_fringe: int) -> Path:
    """Transparent 32x32 canvas, opaque core square, n_fringe pixels of
    alpha=128 on the left edge each 4-adjacent to transparency."""
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    for y in range(8, 24):
        for x in range(8, 24):
            img.putpixel((x, y), (200, 30, 30, 255))
    for i in range(n_fringe):
        img.putpixel((7, 8 + i), (200, 30, 30, 128))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def test_halo_over_max_fix_needed_with_coords(tmp_path):
    dd = tmp_path / "d"
    dd.mkdir()
    _halo_sprite(dd / "a.png", 12)              # 12 > default 8
    wl = _worklist(tmp_path / "wl.json", [_entry("a")])
    rc = intake.main([str(dd), "--worklist", str(wl)])
    assert rc == 1
    rec = _report(dd)["files"][0]
    assert rec["halo"]["count"] == 12
    assert rec["halo"]["max"] == 8
    assert len(rec["halo"]["coords"]) == 10     # capped listing
    assert rec["halo"]["coords"][0] == [7, 8]
    reason = " ".join(rec["reasons"])
    assert "stray halo: 12" in reason
    assert "(7,8)" in reason
    assert "binary alpha" in reason


def test_halo_within_max_accepted_with_note(tmp_path):
    dd = tmp_path / "d"
    dd.mkdir()
    _halo_sprite(dd / "a.png", 3)
    wl = _worklist(tmp_path / "wl.json", [_entry("a")])
    rc = intake.main([str(dd), "--worklist", str(wl)])
    assert rc == 0
    rec = _report(dd)["files"][0]
    assert rec["status"] == "accepted"
    assert rec["halo"]["count"] == 3
    assert any("minor halo: 3" in n for n in rec["notes"])


def test_halo_max_flag_tightens(tmp_path):
    dd = tmp_path / "d"
    dd.mkdir()
    _halo_sprite(dd / "a.png", 3)
    wl = _worklist(tmp_path / "wl.json", [_entry("a")])
    rc = intake.main([str(dd), "--worklist", str(wl), "--halo-max", "0"])
    assert rc == 1
    rec = _report(dd)["files"][0]
    assert any("stray halo: 3" in r for r in rec["reasons"])


# ---------------------------------------------------------------- palette
def test_off_palette_reported_hex_count_first(tmp_path):
    dd = tmp_path / "d"
    dd.mkdir()
    _sprite(dd / "a.png", 32, 32, fill=(255, 0, 0, 255), pixels={
        (5, 5): (12, 34, 56, 255),
        (6, 5): (12, 34, 56, 255),
        (9, 9): (99, 88, 77, 255),
        (2, 2): (12, 34, 56, 0),        # transparent — never counted
    })
    wl = _worklist(tmp_path / "wl.json", [_entry("a")])
    strip = _strip_png(tmp_path / "strip.png")
    rc = intake.main([str(dd), "--worklist", str(wl),
                      "--palette", str(strip)])
    assert rc == 1
    rec = _report(dd)["files"][0]
    offs = {o["hex"]: o for o in rec["off_palette"]}
    assert offs["#0c2238"]["count"] == 2
    assert offs["#0c2238"]["first"] == [5, 5]
    assert offs["#63584d"]["count"] == 1
    assert offs["#63584d"]["first"] == [9, 9]
    reason = " ".join(rec["reasons"])
    assert "off-palette: 3 pixel(s)" in reason
    assert "#0c2238" in reason and "(5,5)" in reason


def test_palette_max_tolerance_and_exact_pass(tmp_path):
    dd = tmp_path / "d"
    dd.mkdir()
    _sprite(dd / "a.png", 32, 32, fill=(255, 0, 0, 255),
            pixels={(5, 5): (12, 34, 56, 255)})
    _sprite(dd / "b.png", 32, 32, fill=(0, 255, 0, 255))
    wl = _worklist(tmp_path / "wl.json", [_entry("a"), _entry("b")])
    strip = _strip_png(tmp_path / "strip.png")
    rc = intake.main([str(dd), "--worklist", str(wl),
                      "--palette", str(strip), "--palette-max", "2"])
    assert rc == 0
    by_file = {f["file"]: f for f in _report(dd)["files"]}
    assert by_file["a.png"]["status"] == "accepted"
    assert any("within tolerance" in n for n in by_file["a.png"]["notes"])
    assert by_file["b.png"]["status"] == "accepted"
    assert by_file["b.png"]["off_palette"] is None


def test_no_palette_flag_skips_membership(tmp_path):
    dd, wl = _one_file_batch(tmp_path, fill=(12, 34, 56, 255))
    rc = intake.main([str(dd), "--worklist", str(wl)])
    assert rc == 0
    rep = _report(dd)
    assert rep["palette"] is None
    assert rep["files"][0]["off_palette"] is None


# ---------------------------------------------------------------- entry gates
def test_covered_by_rejected(tmp_path):
    dd, wl = _one_file_batch(
        tmp_path, entries=[_entry("a", covered_by="ladder.library")])
    rc = intake.main([str(dd), "--worklist", str(wl)])
    assert rc == 1
    rec = _report(dd)["files"][0]
    reason = " ".join(rec["reasons"])
    assert "no new art expected" in reason
    assert "ladder.library" in reason


def test_size_null_crossref_rejected(tmp_path):
    dd, wl = _one_file_batch(tmp_path, entries=[_entry("a", w=None)])
    rc = intake.main([str(dd), "--worklist", str(wl)])
    assert rc == 1
    rec = _report(dd)["files"][0]
    assert any("no usable canvas size" in r for r in rec["reasons"])


def test_staged_accepted_with_note(tmp_path):
    dd, wl = _one_file_batch(tmp_path, entries=[_entry("a", staged=True)])
    rc = intake.main([str(dd), "--worklist", str(wl)])
    assert rc == 0
    rec = _report(dd)["files"][0]
    assert rec["status"] == "accepted"
    assert any("staged entry" in n for n in rec["notes"])


# ---------------------------------------------------------------- report
def test_report_schema_and_byte_determinism(tmp_path):
    dd = tmp_path / "d"
    dd.mkdir()
    _sprite(dd / "a.png")
    _sprite(dd / "bad.png", 24, 24)
    wl = _worklist(tmp_path / "wl.json", [_entry("a"), _entry("bad")])
    argv = [str(dd), "--worklist", str(wl), "--batch-tag", "t1"]
    assert intake.main(argv) == 1
    first = {n: (dd / "_intake" / n).read_bytes()
             for n in ("report.json", "report.md", "test-scene.png")}
    assert intake.main(argv) == 1               # rerun, same invocation
    for n, data in first.items():
        assert (dd / "_intake" / n).read_bytes() == data, n

    rep = json.loads(first["report.json"])
    assert rep["schema"] == "cabinet.world.intake-report/v1"
    assert set(rep) == {"schema", "batch", "worklist", "palette", "counts",
                        "files", "scene", "aesthetic_gate", "promote"}
    assert rep["batch"] == "t1"
    assert rep["counts"] == {"files": 2, "accepted": 1, "fix_needed": 1}
    assert rep["worklist"]["sha256"]
    assert rep["promote"]["mode"] == "report-only"
    assert "generated" not in json.dumps(rep)   # no timestamps anywhere
    rec = [f for f in rep["files"] if f["file"] == "a.png"][0]
    import hashlib
    assert rec["sha256"] == hashlib.sha256(
        (dd / "a.png").read_bytes()).hexdigest()


def test_scene_composed_on_grid_checker(tmp_path):
    dd = tmp_path / "d"
    dd.mkdir()
    _sprite(dd / "a.png", 32, 32)
    _sprite(dd / "b.png", 48, 32)
    wl = _worklist(tmp_path / "wl.json",
                   [_entry("a"), _entry("b", 48, 32)])
    assert intake.main([str(dd), "--worklist", str(wl)]) == 0
    scene_path = dd / "_intake" / "test-scene.png"
    with Image.open(scene_path) as im:
        assert im.width % 16 == 0 and im.height % 16 == 0
        rgba = im.convert("RGBA")
        # top-left tile is checker A (gutter, no sprite at 0,0)
        assert rgba.getpixel((0, 0)) == intake.CHECKER_A
        assert rgba.getpixel((16, 0)) == intake.CHECKER_B
        # first sprite composited at (16,16) — sorted by id, a first
        assert rgba.getpixel((16, 16)) == (200, 30, 30, 255)
    rep = _report(dd)
    assert rep["scene"]["path"] == "test-scene.png"
    assert rep["scene"]["sha256"] == __import__("hashlib").sha256(
        scene_path.read_bytes()).hexdigest()


def test_no_accepted_no_scene(tmp_path):
    dd, wl = _one_file_batch(tmp_path, mode="RGB", fill=(1, 2, 3))
    rc = intake.main([str(dd), "--worklist", str(wl), "--gate"])
    assert rc == 1
    rep = _report(dd)
    assert rep["scene"] is None
    assert not (dd / "_intake" / "test-scene.png").exists()
    assert rep["aesthetic_gate"]["exit"] is None
    assert "no accepted sprites" in rep["aesthetic_gate"]["note"]


# ---------------------------------------------------------------- gate
def test_gate_seam_mocked_verdict_folded(tmp_path, monkeypatch):
    canned = json.dumps({
        "ok": False, "counts": {"error": 1, "warn": 0, "info": 4},
        "gates_run": ["palette_coherence", "clustering"],
        "skipped": [{"gate": "edge_continuity", "reason": "needs --map"}],
        "generated": "2026-01-01T00:00:00+00:00",
        "inputs": {"render": "/abs/path/test-scene.png"},
    })
    seen = {}

    def fake(scene_path):
        seen["scene"] = Path(scene_path)
        return 1, canned

    monkeypatch.setattr(intake, "run_aesthetic_gate", fake)
    dd, wl = _one_file_batch(tmp_path)
    rc = intake.main([str(dd), "--worklist", str(wl), "--gate"])
    assert rc == 0            # gate verdict is INFORMATIONAL — never flips
    assert seen["scene"] == dd / "_intake" / "test-scene.png"
    ag = _report(dd)["aesthetic_gate"]
    assert ag["exit"] == 1
    assert ag["ok"] is False
    assert ag["counts"] == {"error": 1, "warn": 0, "info": 4}
    assert ag["gates_run"] == ["palette_coherence", "clustering"]
    assert "generated" not in ag        # timestamp dropped (determinism)
    assert "inputs" not in ag           # abs paths dropped
    assert "informational" in ag["note"]


def test_gate_real_wrapper_smoke(tmp_path):
    """One REAL subprocess run of the committed world-aesthetic-gate.py
    over the tiny scene — proves the seam argv + envelope parse against
    the tracked wrapper/calibrations. Verdict is informational: the
    committed calibration is LimeZu-fitted, so no assertion on ok."""
    dd, wl = _one_file_batch(tmp_path)
    rc = intake.main([str(dd), "--worklist", str(wl), "--gate"])
    assert rc == 0
    ag = _report(dd)["aesthetic_gate"]
    assert isinstance(ag["exit"], int)
    assert ag["exit"] in (0, 1)
    assert not ag.get("parse_error"), ag
    assert isinstance(ag["counts"], dict)
    assert "palette_coherence" in (ag["gates_run"] or [])


# ---------------------------------------------------------------- promote
def _promote_env(tmp_path, entries, files):
    """Delivery + worklist + tmp asset root/manifest. files = {name: kw}."""
    dd = tmp_path / "batchX"
    dd.mkdir(exist_ok=True)
    for name, kw in files.items():
        _sprite(dd / name, **kw)
    wl = _worklist(tmp_path / "wl.json", entries)
    root = tmp_path / "assets"
    manifest = _mini_manifest(root)
    base = [str(dd), "--worklist", str(wl), "--assets-root", str(root),
            "--manifest", str(manifest), "--batch-tag", "b1"]
    return dd, wl, root, manifest, base


def test_report_only_never_touches_manifest_or_assets(tmp_path):
    dd, wl, root, manifest, base = _promote_env(
        tmp_path, [_entry("a")], {"a.png": {}})
    before = manifest.read_bytes()
    assert intake.main(base) == 0               # no --promote
    assert manifest.read_bytes() == before
    assert not (root / "originals").exists()


def test_promote_refuses_on_any_failure(tmp_path, capsys):
    dd, wl, root, manifest, base = _promote_env(
        tmp_path, [_entry("a"), _entry("bad")],
        {"a.png": {}, "bad.png": {"w": 24, "h": 24}})
    before = manifest.read_bytes()
    rc = intake.main(base + ["--promote"])
    assert rc == 2
    assert "PROMOTE REFUSED" in capsys.readouterr().err
    assert manifest.read_bytes() == before      # nothing copied/appended
    assert not (root / "originals").exists()
    rep = _report(dd)
    assert rep["promote"]["mode"] == "refused"
    assert rep["promote"]["promoted"] == []
    assert rep["promote"]["skipped"] == ["bad.png"]


def test_promote_accepted_only_copies_subset(tmp_path):
    dd, wl, root, manifest, base = _promote_env(
        tmp_path, [_entry("a"), _entry("bad")],
        {"a.png": {}, "bad.png": {"w": 24, "h": 24}})
    rc = intake.main(base + ["--promote-accepted-only"])
    assert rc == 1                              # fix_needed still exits 1
    assert (root / "originals" / "testobj" / "a.png").is_file()
    assert not (root / "originals" / "testobj" / "bad.png").exists()
    rep = _report(dd)
    assert rep["promote"]["mode"] == "promote-accepted-only"
    assert rep["promote"]["promoted"] == ["originals/testobj/a.png"]
    assert rep["promote"]["skipped"] == ["bad.png"]
    m = json.loads(manifest.read_text())
    assert len(m["assets"]) == 1


def test_promote_row_shape_matches_install_conventions(tmp_path):
    dd, wl, root, manifest, base = _promote_env(
        tmp_path,
        [_entry("anim.x", 32, 32, animated=True, frames=2,
                object="firepit")],
        {"anim.x.png": {"w": 64, "h": 32}})
    rc = intake.main(base + ["--promote"])
    assert rc == 0
    copied = root / "originals" / "firepit" / "anim.x.png"
    assert copied.read_bytes() == (dd / "anim.x.png").read_bytes()  # verbatim
    m = json.loads(manifest.read_text())
    assert m["version"] == 3                    # untouched by intake
    assert m["_doc"] == "test manifest"         # untouched by intake
    [row] = m["assets"]
    # exact world-asset-install.py:136-147 key set
    assert set(row) == {"id", "path", "w", "h", "grid", "sha256",
                        "pack", "license"}
    assert row["id"] == "originals/firepit/anim.x"
    assert row["path"] == "originals/firepit/anim.x.png"
    assert (row["w"], row["h"]) == (64, 32)     # delivered strip dims
    assert row["grid"] == 16
    import hashlib
    assert row["sha256"] == hashlib.sha256(copied.read_bytes()).hexdigest()
    assert row["license"] == "owned — org-original"
    assert "artist delivery" in row["pack"] and "batch b1" in row["pack"]
    # install serialization format: indent=1 + trailing newline
    text = manifest.read_text()
    assert text.endswith("\n")
    assert '\n "assets"' in text


def test_promote_idempotent_replaces_not_duplicates(tmp_path):
    dd, wl, root, manifest, base = _promote_env(
        tmp_path, [_entry("a")], {"a.png": {}})
    assert intake.main(base + ["--promote"]) == 0
    assert intake.main(base + ["--promote"]) == 0
    m = json.loads(manifest.read_text())
    assert len(m["assets"]) == 1                # replaced, not duplicated
    rep = _report(dd)
    assert rep["promote"]["replaced"] == ["originals/testobj/a"]


def test_promoted_tree_passes_world_asset_gate(tmp_path):
    dd, wl, root, manifest, base = _promote_env(
        tmp_path,
        [_entry("a"), _entry("b", 48, 16, object="quay")],
        {"a.png": {}, "b.png": {"w": 48, "h": 16}})
    assert intake.main(base + ["--promote"]) == 0
    assert gate.main([str(manifest)]) == 0      # WORLD_ASSETS GREEN


def test_promote_containment_refusal_copies_nothing(tmp_path, monkeypatch,
                                                    capsys):
    monkeypatch.setattr(intake, "sanitize_id", lambda s: s)  # defeat layer 1
    dd, wl, root, manifest, base = _promote_env(
        tmp_path, [_entry("a", object="../../evil")], {"a.png": {}})
    before = manifest.read_bytes()
    rc = intake.main(base + ["--promote"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "containment" in err or "escapes" in err
    assert manifest.read_bytes() == before
    assert not (root / "originals").exists()    # two-phase: nothing copied
    assert not (tmp_path / "evil").exists()


def test_promote_missing_manifest_refused(tmp_path):
    dd = tmp_path / "d"
    dd.mkdir()
    _sprite(dd / "a.png")
    wl = _worklist(tmp_path / "wl.json", [_entry("a")])
    root = tmp_path / "assets"                  # no manifest.json inside
    rc = intake.main([str(dd), "--worklist", str(wl), "--promote",
                      "--assets-root", str(root),
                      "--manifest", str(root / "manifest.json")])
    assert rc == 2
    assert not (root / "originals").exists()


# ---------------------------------------------------------------- repo law
def test_gitignore_reincludes_originals():
    """The owned-originals tree must be committable: the negation rides
    right after the world-assets ignore pair (.gitignore world-assets
    block) — LimeZu binaries stay ignored, originals/ tracks."""
    gi = (_REPO / ".gitignore").read_text()
    assert "cabinet/dashboard/public/world-assets/*" in gi
    assert "!cabinet/dashboard/public/world-assets/originals/" in gi


def test_no_network_imports_in_tool():
    """Intake is a local tool by doctrine — no urllib/http/socket use."""
    src = (_SCRIPTS / "world-asset-intake.py").read_text()
    for banned in ("urllib", "http.client", "requests", "socket"):
        assert banned not in src, banned
