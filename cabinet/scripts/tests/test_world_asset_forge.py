"""Tests for cabinet/scripts/world-asset-forge.py — HTTP fully mocked.

Zero network in CI: an autouse fixture replaces the urllib transport
primitive with a raiser, and generation tests mock the `_post_json` seam.
The ONLY key material anywhere is the synthetic 'test-key-123'; HOME is a
tmp dir so the real ~/.pixellab-api-key can never be read. Gate-shape is
proven by running world-asset-gate.py helpers over the written candidates.
"""
from __future__ import annotations

import base64
import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

_SCRIPTS = Path(__file__).resolve().parents[1]


def _load(modname: str, filename: str):
    spec = importlib.util.spec_from_file_location(modname,
                                                  _SCRIPTS / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


forge = _load("world_asset_forge", "world-asset-forge.py")
gate = _load("world_asset_gate_for_forge", "world-asset-gate.py")

SYNTH_KEY = "test-key-123"   # synthetic — never a real credential
STRIP_COLORS = [(0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255)]


# ---------------------------------------------------------------- helpers
def _png_bytes(w=32, h=32, fill=(7, 7, 7, 255), pixels=None) -> bytes:
    img = Image.new("RGBA", (w, h), fill)
    for xy, c in (pixels or {}).items():
        img.putpixel(xy, c)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _png_b64(w=32, h=32, fill=(7, 7, 7, 255), pixels=None) -> str:
    return base64.b64encode(_png_bytes(w, h, fill, pixels)).decode("ascii")


def _strip_png(path: Path, colors=STRIP_COLORS) -> Path:
    img = Image.new("RGBA", (len(colors), 1))
    img.putdata([c + (255,) for c in colors])
    img.save(path)
    return path


def _style_dir(tmp_path: Path) -> Path:
    d = tmp_path / "style"
    d.mkdir(exist_ok=True)
    for name, fill in (("a.png", (255, 0, 0, 255)),
                       ("b.png", (0, 255, 0, 255))):
        Image.new("RGBA", (16, 16), fill).save(d / name)
    return d


def _worklist(path: Path, ids, size="32x32") -> Path:
    entries = [{"id": i, "section": "test",
                "description": f"test sprite {i}", "size_hint": size}
               for i in ids]
    path.write_text(json.dumps(
        {"schema": "cabinet.world.asset-worklist/v1", "entries": entries}))
    return path


def _scan_tree_for(root: Path, needle: bytes) -> list[Path]:
    return [p for p in root.rglob("*")
            if p.is_file() and needle in p.read_bytes()]


# ---------------------------------------------------------------- fixtures
@pytest.fixture(autouse=True)
def _hermetic(monkeypatch, tmp_path):
    """tmp HOME (the real ~/.pixellab-api-key is untouchable), no ambient
    key, zero retry sleep, and a loud failure on any REAL http attempt."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("PIXELLAB_API_KEY", raising=False)
    monkeypatch.setattr(forge, "_RETRY_SLEEP_S", 0.0)

    def _no_net(*a, **k):
        raise AssertionError("real HTTP attempted in tests")

    monkeypatch.setattr(forge, "_http_post_once", _no_net)
    yield


@pytest.fixture
def seam(monkeypatch):
    """Mock THE seam: canned pilot-shaped success response, call capture."""
    calls = []

    def fake(url, payload, api_key):
        calls.append({"url": url, "payload": payload, "api_key": api_key})
        return {"image": {"base64": _png_b64()}, "usage": {"credits": 1}}

    monkeypatch.setattr(forge, "_post_json", fake)
    return calls


# ---------------------------------------------------------------- secrets
def test_key_precedence_env_over_keyfile(monkeypatch, tmp_path):
    keyfile = Path((tmp_path / "home") / ".pixellab-api-key")
    keyfile.write_text("file-key-456\n")
    monkeypatch.setenv("PIXELLAB_API_KEY", SYNTH_KEY)
    assert forge.load_api_key() == SYNTH_KEY
    monkeypatch.delenv("PIXELLAB_API_KEY")
    assert forge.load_api_key() == "file-key-456"   # whitespace stripped


def test_missing_key_is_named_handback(tmp_path, capsys, seam):
    out = tmp_path / "out"
    rc = forge.main(["--describe", "oak barrel", "--size", "32x32",
                     "--out", str(out)])
    assert rc == forge.EXIT_HANDBACK == 4
    err = capsys.readouterr().err
    assert "HANDBACK" in err
    assert "PIXELLAB_API_KEY" in err
    assert ".pixellab-api-key" in err
    assert seam == []                    # refused before any call


def test_key_never_in_stdout_or_output_files(monkeypatch, tmp_path,
                                             capsys, seam):
    monkeypatch.setenv("PIXELLAB_API_KEY", SYNTH_KEY)
    out = tmp_path / "out"
    wl = _worklist(tmp_path / "wl.json", ["ladder.test.a"])
    rc = forge.main(["--worklist", str(wl), "--entry", "ladder.test.a",
                     "--candidates", "1", "--out", str(out),
                     "--style-dir", str(_style_dir(tmp_path))])
    assert rc == 0
    assert seam and seam[0]["api_key"] == SYNTH_KEY   # seam got the key…
    captured = capsys.readouterr()
    assert SYNTH_KEY not in captured.out + captured.err   # …output didn't
    assert _scan_tree_for(out, SYNTH_KEY.encode()) == []  # …no file did


# ---------------------------------------------------------------- spend
def test_defaults_candidates_2_limit_10():
    assert forge.DEFAULT_LIMIT == 10
    args = forge.build_parser().parse_args(
        ["--describe", "x", "--size", "16x16"])
    assert args.limit == 10
    assert args.candidates == 2


def test_spend_guard_refuses_over_limit(tmp_path, capsys, seam):
    wl = _worklist(tmp_path / "wl.json", [f"e{i}" for i in range(6)])
    out = tmp_path / "out"
    rc = forge.main(["--worklist", str(wl), "--entry", "*",
                     "--out", str(out)])   # 6 x 2 = 12 > default 10
    assert rc == forge.EXIT_USAGE == 2
    err = capsys.readouterr().err
    assert "12" in err and "--limit is 10" in err and "REFUSED" in err
    assert seam == []                     # zero API calls
    assert not out.exists()               # zero writes


def test_spend_guard_explicit_limit_allows(monkeypatch, tmp_path, seam):
    monkeypatch.setenv("PIXELLAB_API_KEY", SYNTH_KEY)
    wl = _worklist(tmp_path / "wl.json", [f"e{i}" for i in range(6)])
    out = tmp_path / "out"
    rc = forge.main(["--worklist", str(wl), "--entry", "*",
                     "--limit", "12", "--out", str(out)])
    assert rc == 0
    assert len(seam) == 12
    assert len(list(out.rglob("cand-*.png"))) == 12


# ---------------------------------------------------------------- generate
def test_candidate_sidecar_and_gate_shape(monkeypatch, tmp_path, seam):
    monkeypatch.setenv("PIXELLAB_API_KEY", SYNTH_KEY)
    out = tmp_path / "out"
    strip = _strip_png(tmp_path / "strip.png")
    wl = _worklist(tmp_path / "wl.json", ["ladder.flagpole.pennant.rag"])
    rc = forge.main(["--worklist", str(wl),
                     "--entry", "ladder.flagpole.pennant.rag",
                     "--candidates", "1", "--out", str(out),
                     "--palette", str(strip)])
    assert rc == 0
    cand = out / "ladder.flagpole.pennant.rag" / "cand-1.png"
    side = out / "ladder.flagpole.pennant.rag" / "cand-1.json"
    assert cand.is_file() and side.is_file()

    data = cand.read_bytes()
    assert gate.png_dimensions(data) == (32, 32)   # gate helper, real file

    sc = json.loads(side.read_text())
    assert sc["entry_id"] == "ladder.flagpole.pennant.rag"
    assert sc["prompt"].startswith("test sprite")
    assert sc["endpoint"] == forge.DEFAULT_ENDPOINT
    assert sc["size"] == {"w": 32, "h": 32}
    assert sc["grid"] == gate.GRID == 16
    assert sc["grid_ok"] is True
    assert sc["palette_strip_sha256"] is not None
    assert sc["response_meta"] == {"usage": {"credits": 1}}   # image stripped

    row = sc["manifest_row"]
    assert set(row) == {"id", "path", "w", "h", "grid", "sha256",
                        "pack", "license"}   # world-asset-install.py:141-147
    assert row["id"] == "ladder.flagpole.pennant.rag"
    assert row["path"] == "ladder.flagpole.pennant.rag/cand-1.png"
    assert (row["w"], row["h"]) == gate.png_dimensions(data)
    assert row["grid"] == 16
    import hashlib
    assert row["sha256"] == hashlib.sha256(data).hexdigest()
    assert row["license"] == "owned — org-original"
    assert row["pack"].startswith("PixelLab forge candidate — ")

    # payload carried the pilot-proven fields
    payload = seam[0]["payload"]
    assert payload["image_size"] == {"width": 32, "height": 32}
    assert payload["view"] == "high top-down"
    assert payload["no_background"] is True
    assert payload["color_image"]["base64"]


def test_style_collage_exactly_canvas_size(tmp_path):
    col = forge.build_style_collage(_style_dir(tmp_path), 48, 32)
    assert col.size == (48, 32)


def test_style_refs_ride_payload_at_canvas_size(monkeypatch, tmp_path,
                                                seam):
    monkeypatch.setenv("PIXELLAB_API_KEY", SYNTH_KEY)
    out = tmp_path / "out"
    wl = _worklist(tmp_path / "wl.json", ["e1"])
    rc = forge.main(["--worklist", str(wl), "--entry", "e1",
                     "--candidates", "1", "--out", str(out),
                     "--style-dir", str(_style_dir(tmp_path))])
    assert rc == 0
    style_b64 = seam[0]["payload"]["style_image"]["base64"]
    assert gate.png_dimensions(base64.b64decode(style_b64)) == (32, 32)


def test_prebuilt_style_image_autofit(monkeypatch, tmp_path, seam):
    monkeypatch.setenv("PIXELLAB_API_KEY", SYNTH_KEY)
    big = tmp_path / "style-big.png"
    Image.new("RGBA", (64, 64), (9, 9, 9, 255)).save(big)
    out = tmp_path / "out"
    wl = _worklist(tmp_path / "wl.json", ["e1"])
    rc = forge.main(["--worklist", str(wl), "--entry", "e1",
                     "--candidates", "1", "--out", str(out),
                     "--style-image", str(big)])
    assert rc == 0
    style_b64 = seam[0]["payload"]["style_image"]["base64"]
    assert gate.png_dimensions(base64.b64decode(style_b64)) == (32, 32)
    sc = json.loads((out / "e1" / "cand-1.json").read_text())
    assert sc["style_resized_to_canvas"] is True


def test_missing_style_image_actionable(monkeypatch, tmp_path, capsys,
                                        seam):
    monkeypatch.setenv("PIXELLAB_API_KEY", SYNTH_KEY)
    rc = forge.main(["--describe", "probe", "--size", "32x32", "--id", "p",
                     "--style-image", str(tmp_path / "absent.png"),
                     "--out", str(tmp_path / "out")])
    assert rc == forge.EXIT_USAGE == 2
    err = capsys.readouterr().err
    assert "--style-image" in err and "not found" in err
    assert seam == []                     # discovered before any spend


def test_quantize_only_strip_colors_alpha_preserved(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELLAB_API_KEY", SYNTH_KEY)
    api_png = _png_b64(32, 32, fill=(10, 10, 10, 255), pixels={
        (0, 0): (250, 5, 5, 255),      # near red
        (1, 0): (5, 240, 5, 255),      # near green
        (2, 0): (100, 100, 100, 128),  # semi-transparent grey
        (3, 0): (0, 0, 0, 0),          # fully transparent
    })
    monkeypatch.setattr(
        forge, "_post_json",
        lambda url, payload, api_key: {"image": {"base64": api_png}})
    out = tmp_path / "out"
    strip = _strip_png(tmp_path / "strip.png")
    rc = forge.main(["--describe", "quantize probe", "--size", "32x32",
                     "--id", "probe", "--candidates", "1",
                     "--out", str(out), "--palette", str(strip)])
    assert rc == 0
    img = Image.open(out / "probe" / "cand-1.png").convert("RGBA")
    allowed = set(STRIP_COLORS)
    raw = img.tobytes()
    for i in range(0, len(raw), 4):
        r, g, b, a = raw[i], raw[i + 1], raw[i + 2], raw[i + 3]
        if a == 0:
            continue
        assert (r, g, b) in allowed
    assert img.getpixel((0, 0)) == (255, 0, 0, 255)
    assert img.getpixel((1, 0)) == (0, 255, 0, 255)
    assert img.getpixel((2, 0))[3] == 128      # alpha byte preserved
    assert img.getpixel((3, 0)) == (0, 0, 0, 0)


def test_non_png_payload_refused(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("PIXELLAB_API_KEY", SYNTH_KEY)
    bogus = base64.b64encode(b"JFIF definitely not a png").decode("ascii")
    monkeypatch.setattr(
        forge, "_post_json",
        lambda url, payload, api_key: {"image": {"base64": bogus}})
    out = tmp_path / "out"
    rc = forge.main(["--describe", "bad payload", "--size", "16x16",
                     "--id", "bad", "--candidates", "1", "--out", str(out)])
    assert rc == forge.EXIT_CANDIDATE_ISSUES == 1
    assert not (out / "bad" / "cand-1.png").exists()   # refused = no file
    assert "not a PNG" in capsys.readouterr().err


def test_off_grid_png_flagged_but_written(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("PIXELLAB_API_KEY", SYNTH_KEY)
    api_png = _png_b64(24, 24)                     # 24 % 16 != 0
    monkeypatch.setattr(
        forge, "_post_json",
        lambda url, payload, api_key: {"image": {"base64": api_png}})
    out = tmp_path / "out"
    rc = forge.main(["--describe", "off grid", "--size", "32x32",
                     "--id", "offgrid", "--candidates", "1",
                     "--out", str(out)])
    assert rc == 1
    cand = out / "offgrid" / "cand-1.png"
    assert cand.is_file()                          # still written for review
    sc = json.loads((out / "offgrid" / "cand-1.json").read_text())
    assert sc["grid_ok"] is False
    assert sc["actual_size"] == {"w": 24, "h": 24}
    assert "grid" in capsys.readouterr().err


# ---------------------------------------------------------------- jail
def test_sanitize_id_kills_traversal_and_dots():
    assert forge.sanitize_id("../evil") == "evil"
    assert forge.sanitize_id("../../escape-me") == "escape-me"
    assert forge.sanitize_id("a/b/c") == "a_b_c"
    assert forge.sanitize_id("ladder.flag.cloth") == "ladder.flag.cloth"
    assert forge.sanitize_id("..") == ""


def test_jail_refuses_when_sanitize_bypassed(monkeypatch, tmp_path):
    monkeypatch.setattr(forge, "sanitize_id", lambda s: s)  # defeat layer 1
    with pytest.raises(forge.ForgeError, match="containment|escapes"):
        forge._entry_dir(tmp_path / "out", "../evil")


def test_traversal_worklist_id_stays_inside_out_dir(monkeypatch, tmp_path,
                                                    seam):
    monkeypatch.setenv("PIXELLAB_API_KEY", SYNTH_KEY)
    out = tmp_path / "jailed" / "out"
    wl = _worklist(tmp_path / "wl.json", ["../../escape-me"])
    rc = forge.main(["--worklist", str(wl), "--entry", "*",
                     "--candidates", "1", "--out", str(out)])
    assert rc == 0
    assert (out / "escape-me" / "cand-1.png").is_file()   # sanitized inside
    assert not (tmp_path / "escape-me").exists()
    assert not (tmp_path / "jailed" / "escape-me").exists()


# ---------------------------------------------------------------- dry-run
def test_dry_run_zero_calls_zero_writes(tmp_path, capsys, seam):
    out = tmp_path / "out"
    wl = _worklist(tmp_path / "wl.json", ["e1", "e2"])
    rc = forge.main(["--worklist", str(wl), "--entry", "*",
                     "--out", str(out), "--dry-run",
                     "--style-dir", str(_style_dir(tmp_path))])
    assert rc == 0
    assert seam == []                      # zero API calls
    assert not out.exists()                # zero writes
    got = capsys.readouterr().out
    assert "DRY RUN" in got
    assert "planned API calls: 4" in got   # 2 entries x default 2
    assert forge.DEFAULT_ENDPOINT in got
    assert "e1" in got and "e2" in got


# ---------------------------------------------------------------- retries
def _seq_transport(monkeypatch, outcomes):
    calls = {"n": 0}

    def fake(url, payload_bytes, api_key):
        item = outcomes[min(calls["n"], len(outcomes) - 1)]
        calls["n"] += 1
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(forge, "_http_post_once", fake)
    return calls


def test_post_json_retries_5xx_then_succeeds(monkeypatch):
    okresp = {"image": {"base64": _png_b64()}}
    calls = _seq_transport(monkeypatch, [
        forge.ForgeHTTPStatusError(500, "server melted", "u"), okresp])
    assert forge._post_json("u", {}, "k") == okresp
    assert calls["n"] == 2


def test_post_json_429_retries_bounded(monkeypatch):
    calls = _seq_transport(monkeypatch, [
        forge.ForgeHTTPStatusError(429, "slow down", "u")])
    with pytest.raises(forge.ForgeHTTPStatusError):
        forge._post_json("u", {}, "k")
    assert calls["n"] == 1 + forge._RETRIES     # bounded: 3 total


def test_4xx_no_retry_size_mismatch_verbatim_and_hint(monkeypatch,
                                                      tmp_path, capsys):
    monkeypatch.setenv("PIXELLAB_API_KEY", SYNTH_KEY)
    body = ("style_image dimensions must match image_size "
            "(got 64x64, expected 32x32)")
    calls = _seq_transport(monkeypatch, [
        forge.ForgeHTTPStatusError(400, body, "u")])
    out = tmp_path / "out"
    rc = forge.main(["--describe", "mismatch probe", "--size", "32x32",
                     "--id", "mm", "--candidates", "1", "--out", str(out)])
    assert rc == 1
    assert calls["n"] == 1                      # 4xx never retried
    err = capsys.readouterr().err
    assert body in err                          # surfaced VERBATIM
    assert "--style-dir" in err                 # actionable hint


# ---------------------------------------------------------------- modes
def test_one_off_mode_writes_under_given_id(monkeypatch, tmp_path, seam):
    monkeypatch.setenv("PIXELLAB_API_KEY", SYNTH_KEY)
    out = tmp_path / "out"
    rc = forge.main(["--describe", "weathered oak harbor barrel",
                     "--size", "32x32", "--id", "barrel",
                     "--candidates", "2", "--out", str(out)])
    assert rc == 0
    assert (out / "barrel" / "cand-1.png").is_file()
    assert (out / "barrel" / "cand-2.png").is_file()
    sc = json.loads((out / "barrel" / "cand-1.json").read_text())
    assert sc["entry_id"] == "barrel"
    assert sc["worklist_entry"] is None
    assert len(seam) == 2


def test_entry_glob_selects_subset(monkeypatch, tmp_path, seam):
    monkeypatch.setenv("PIXELLAB_API_KEY", SYNTH_KEY)
    out = tmp_path / "out"
    wl = _worklist(tmp_path / "wl.json", ["a.x", "a.y", "b.z"])
    rc = forge.main(["--worklist", str(wl), "--entry", "a.*",
                     "--candidates", "1", "--out", str(out)])
    assert rc == 0
    assert (out / "a.x").is_dir() and (out / "a.y").is_dir()
    assert not (out / "b.z").exists()


def test_unknown_entry_glob_refused(tmp_path, capsys, seam):
    wl = _worklist(tmp_path / "wl.json", ["a.x"])
    rc = forge.main(["--worklist", str(wl), "--entry", "nope*",
                     "--out", str(tmp_path / "out")])
    assert rc == 2
    assert "matches no worklist ids" in capsys.readouterr().err
    assert seam == []


def test_missing_worklist_names_spec_tool(tmp_path, capsys, seam):
    rc = forge.main(["--worklist", str(tmp_path / "absent.json"),
                     "--entry", "*", "--out", str(tmp_path / "out")])
    assert rc == 2
    assert "world-asset-spec.py" in capsys.readouterr().err


def test_prompt_from_entry_precedence_and_synthesis():
    assert forge.prompt_from_entry({"description": "hand prompt"}) \
        == "hand prompt"
    assert forge.prompt_from_entry(
        {"prompt": "wins", "meaning": "loses"}) == "wins"
    synth = forge.prompt_from_entry({
        "era_word": "log_cabin", "rung_state": "cottage",
        "object": "great_house",
        "meaning": "The Great House — the org's seat."})
    assert synth == ("log cabin, cottage, great house — "
                     "The Great House — the org's seat.")
    with pytest.raises(forge.ForgeError, match="no prompt"):
        forge.prompt_from_entry({"id": "x", "notes": []})


def test_canonical_worklist_shape_end_to_end(monkeypatch, tmp_path, seam,
                                             capsys):
    """Real spec-gen v1 entry shape: meaning + era_word/rung_state/object,
    size as a {w,h} px dict, no prose description — must forge cleanly."""
    monkeypatch.setenv("PIXELLAB_API_KEY", SYNTH_KEY)
    entry = {"id": "ladder.great_house.log_cabin.cottage",
             "section": "ladder", "district": "village_core",
             "object": "great_house", "era_word": "log_cabin",
             "rung_state": "cottage", "mode": "tier", "class": "great",
             "day0": True, "day0_state": None, "staged": False,
             "covered_by": "great_house", "size": {"w": 32, "h": 32},
             "animated": False, "frames": None,
             "meaning": "The Great House — the org's seat.", "notes": []}
    wl = tmp_path / "wl.json"
    wl.write_text(json.dumps({"schema": "cabinet.world.asset-worklist/v1",
                              "entries": [entry]}))
    out = tmp_path / "out"
    rc = forge.main(["--worklist", str(wl), "--entry", "*",
                     "--candidates", "1", "--out", str(out)])
    assert rc == 0
    payload = seam[0]["payload"]
    assert payload["image_size"] == {"width": 32, "height": 32}
    assert payload["description"].startswith(
        "log cabin, cottage, great house — ")
    assert "covered_by" in capsys.readouterr().err   # duplicate-spend warn
    sc = json.loads((out / "ladder.great_house.log_cabin.cottage"
                     / "cand-1.json").read_text())
    assert sc["worklist_entry"]["meaning"].startswith("The Great House")


def test_null_size_crossref_skipped_under_glob(monkeypatch, tmp_path,
                                               seam, capsys):
    """size:null cross-ref rows (voyage reuses harbor_boat art) skip with
    a warn under a glob, refuse when named exactly, and an all-skipped
    selection refuses."""
    monkeypatch.setenv("PIXELLAB_API_KEY", SYNTH_KEY)
    crossref = {"id": "anim.voyage.harbor_boat", "section": "animation",
                "size": None, "covered_by": "ladder.harbor_boat",
                "meaning": "voyage reuses harbor_boat families",
                "notes": ["no new art"]}
    good = {"id": "anim.fauna.dog", "section": "animation",
            "size": {"w": 32, "h": 32}, "covered_by": None,
            "meaning": "village dog idle loop", "notes": []}
    wl = tmp_path / "wl.json"
    wl.write_text(json.dumps({"schema": "cabinet.world.asset-worklist/v1",
                              "entries": [crossref, good]}))
    out = tmp_path / "out"

    rc = forge.main(["--worklist", str(wl), "--entry", "anim.*",
                     "--candidates", "1", "--out", str(out)])
    assert rc == 0
    err = capsys.readouterr().err
    assert "skip anim.voyage.harbor_boat" in err
    assert "covered_by" in err
    assert (out / "anim.fauna.dog" / "cand-1.png").is_file()
    assert not (out / "anim.voyage.harbor_boat").exists()
    assert len(seam) == 1                     # only the forgeable entry

    rc = forge.main(["--worklist", str(wl),
                     "--entry", "anim.voyage.harbor_boat",
                     "--out", str(out)])      # exact id => loud refusal
    assert rc == 2
    assert "no size_hint" in capsys.readouterr().err

    rc = forge.main(["--worklist", str(wl), "--entry", "anim.voyage.*",
                     "--out", str(out)])      # all-skipped => refuse
    assert rc == 2
    assert "every matched entry was skipped" in capsys.readouterr().err


def test_grid_unit_size_hint_scales_to_pixels(monkeypatch, tmp_path, seam):
    monkeypatch.setenv("PIXELLAB_API_KEY", SYNTH_KEY)
    out = tmp_path / "out"
    wl = _worklist(tmp_path / "wl.json", ["tiles"], size="2x2")  # grid units
    rc = forge.main(["--worklist", str(wl), "--entry", "tiles",
                     "--candidates", "1", "--out", str(out)])
    assert rc == 0
    assert seam[0]["payload"]["image_size"] == {"width": 32, "height": 32}


def test_style_strength_sent_only_when_given_and_with_style_image():
    """style_strength: absent by default (no regression), sent when passed —
    and only alongside a style_image (meaningless without one)."""
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "waf_ss", Path(__file__).resolve().parents[1] / "world-asset-forge.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    # default None -> not sent, even with a style image
    p0 = m._build_generate_payload("x", 32, 32, "STYLEB64", None, style_strength=None)
    assert "style_strength" not in p0
    assert p0["style_image"]["base64"] == "STYLEB64"
    # given -> sent, when a style image exists
    p1 = m._build_generate_payload("x", 32, 32, "STYLEB64", None, style_strength=70)
    assert p1["style_strength"] == 70
    # given but NO style image -> not sent (nothing to strengthen)
    p2 = m._build_generate_payload("x", 32, 32, None, None, style_strength=70)
    assert "style_strength" not in p2
