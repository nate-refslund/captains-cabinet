#!/usr/bin/env python3
"""frame-judge's own arms — every one shown RED against the defect it names.

WHY EACH ARM IS MUTATED HERE. Two arms proposed for the night ambience defect
both PASSED the broken code, and a whole suite once went green while the guard it
tested could have been deleted, because every arm checked the OUTPUT and none
supplied an INPUT that reached the guard. So the question asked of each arm below
is the one that catches that: what input reaches this, and does a test contain
that input? Each mutation is a real defect — the 2026-07-29 dusk dither, an
ambience filter that never applied, the wrong bucket for the hour, a wash that
stopped drawing — not a synthetic perturbation chosen because it is easy to fail.

WHY SYNTHETIC FRAMES. The arms are what is under test here; the browser is under
test in CI, where `shoot.mjs` captures the real /world and this same judge runs
over it. A hermetic test that builds its own frames can mutate ONE property at a
time, which a real capture cannot, and it needs no committed PNGs.

THE COMPLEMENTARITY ARM IS THE IMPORTANT ONE. `ambience` reads the histogram and
`grain` reads the structure. A mutation that PERMUTES pixels leaves the histogram
identical and moves only the second — if that passed both, one of them would be
decoration.
"""
from __future__ import annotations

import importlib.util
import json
import random
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

HERE = Path(__file__).resolve().parent
JUDGE = HERE.parent / "frame-judge.py"
sys.path.insert(0, str(HERE.parent))
import ambience_py  # noqa: E402


def _load():
    spec = importlib.util.spec_from_file_location("frame_judge", JUDGE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


judge = _load()

W, H = 320, 240
SEA = ambience_py.sea("day")


def _land_tones() -> list[tuple[int, int, int]]:
    """Real corpus tones for the island block, from the renderer's own artifact.

    Not invented colours: the ambience remap snaps to the palette's native set,
    so a made-up tone would exercise a code path the product never takes.
    """
    out: list[tuple[int, int, int]] = []
    for name in ("grass", "grassDark", "roof", "wood", "stone", "sand"):
        try:
            out += ambience_py.ramp("night", name)  # any lit bucket lists the ramp names
        except Exception:
            continue
    # `ramp` returns the SHADED tones; what the day frame needs is the unshaded
    # art, so the ramps are only used to discover which families exist. The tones
    # themselves come from the day sea ramp plus a spread the grade arm can read.
    return out


def day_frame(path: Path, *, flat: bool = False, all_sea: bool = False) -> Path:
    """A day frame: open sea with the shipped ramp, and an island block on it.

    SHAPED LIKE THE REAL ART, not like noise, and that matters for one arm in
    particular. The world's own frames measure ~7.9 mean |ΔL| between adjacent
    pixels: broad flat surfaces carrying a sparse dither. A fixture of
    maximum-frequency stripes would already sit at the top of that scale, and the
    permutation arm below — which proves `grain` sees something `ambience` cannot
    — would pass a shuffled frame because there was no structure left to destroy.
    Measured on the first version of this file, which did exactly that.

    So: mostly one sea tone with two neighbours sprinkled through it (which is
    also what gives the veil probe a multi-tone open-water window), and an island
    of solid 8px blocks spanning dark to bright so check_light's grade arm has a
    real distribution to read.
    """
    im = Image.new("RGB", (W, H))
    px = im.load()
    for y in range(H):
        for x in range(W):
            if flat:
                px[x, y] = SEA[0]
            else:
                k = (x * 7 + y * 13) % 12
                px[x, y] = SEA[2] if k > 1 else SEA[1 + k * 2]
    if not (all_sea or flat):
        band = [(0x2E, 0x3A, 0x2A), (0x4A, 0x6A, 0x3C), (0x6C, 0x8E, 0x4E),
                (0x8E, 0xA8, 0x60), (0xB4, 0x7A, 0x46), (0xD8, 0xC4, 0x8E),
                (0xF0, 0xE4, 0xC0), (0x8A, 0x3A, 0x2E)]
        for y in range(20, H - 20):
            for x in range(120, W - 20):
                px[x, y] = band[((x - 120) // 8 + (y - 20) // 8 * 3) % len(band)]
    im.save(path)
    return path


def lit_frame(day: Path, out: Path, bucket: str) -> Path:
    """The day frame under a bucket's light — what a correct renderer produces.

    Built with `ambience_py.remap`, which is the port of the renderer's own LUT
    pinned to `ambience-derived.json` by test_ambience_mirror. So an honest pair
    here is honest for the same reason a real capture is.
    """
    im = Image.open(day).convert("RGB")
    px = im.load()
    cache: dict = {}
    for y in range(im.size[1]):
        for x in range(im.size[0]):
            c = px[x, y]
            if c not in cache:
                cache[c] = ambience_py.remap(c, bucket)
            px[x, y] = cache[c]
    im.save(out)
    return out


def sweep(tmp: Path, *, bucket="night", hour=2, zoom=1.0, killswitch=False,
          mutate=None, twin_mutate=None, day_kw=None, lit_from=None) -> Path:
    """A whole capture directory + manifest, exactly as shoot.mjs writes one."""
    d = tmp / "sweep"
    d.mkdir(exist_ok=True)
    day = day_frame(d / "day.png", **(day_kw or {}))
    lit = lit_frame(day, d / "lit.png", lit_from or bucket)
    if mutate:
        mutate(lit)
    frames = [
        {"file": str(day), "state": "t", "hour": 13, "bucket": "day", "zoom": zoom,
         "weather": "sun", "killswitch": False, "w": W, "h": H, "issues": []},
        {"file": str(lit), "state": "t", "hour": hour, "bucket": bucket, "zoom": zoom,
         "weather": "sun", "killswitch": False, "w": W, "h": H, "issues": []},
    ]
    if killswitch:
        ks = d / "day-ks.png"
        Image.open(day).convert("RGB").save(ks)
        if twin_mutate:
            twin_mutate(ks)
        frames.append({"file": str(ks), "state": "t", "hour": 13, "bucket": "day",
                       "zoom": zoom, "weather": "sun", "killswitch": True,
                       "w": W, "h": H, "issues": []})
    twin = d / "twin.png"
    Image.open(day).convert("RGB").save(twin)
    (d / "frames.json").write_text(json.dumps(
        {"frames": frames, "determinism": {"a": str(day), "b": str(twin)}}))
    return d


def run(d: Path) -> tuple[int, dict]:
    rep = d / "report.json"
    p = subprocess.run([sys.executable, str(JUDGE), str(d), "--json", str(rep)],
                       capture_output=True, text=True)
    return p.returncode, json.loads(rep.read_text()) if rep.exists() else {"results": []}


def arm(report: dict, prefix: str) -> list:
    return [r for r in report["results"] if r["arm"].startswith(prefix)]


# ── the honest baseline ─────────────────────────────────────────────────────
def test_an_honest_sweep_is_green(tmp_path):
    """Every arm passes on a frame pair the ambience module itself produced.

    Without this the mutations below prove nothing: an arm that reds on
    everything is not a sensor either.
    """
    rc, rep = run(sweep(tmp_path, killswitch=True,
                        twin_mutate=lambda p: _desaturate(p, 0.35)))
    assert rc == 0, [r for r in rep["results"] if not r["ok"]]
    assert arm(rep, "ambience") and arm(rep, "grain") and arm(rep, "grade")
    assert arm(rep, "water") and arm(rep, "killswitch") and arm(rep, "surface")
    # The surface law is EXACT on an honest pair, and this is the line that says
    # so: the lit frame here is ambience_py.remap applied per colour, and it adds
    # a tone to precisely zero tiles. Every non-zero figure the real sweep prints
    # (0.4-5.5%) is therefore the GPU and the Python port disagreeing, not the
    # law bending — which is what makes SURFACE_EXCESS a floor rather than a dial.
    assert all("0/300 tiles gained" in r["detail"] for r in arm(rep, "surface")), \
        arm(rep, "surface")


# ── ambience: the histogram arm ─────────────────────────────────────────────
def test_ambience_red_when_the_filter_never_applied(tmp_path):
    """THE SHIPPED FAILURE MODE. `ambienceFilter` returns null on a renderer that
    cannot compile the shader, and the world paints a perfectly daytime frame at
    midnight. Here the night frame IS the day frame."""
    def mutate(p):
        Image.open(p.parent / "day.png").convert("RGB").save(p)
    rc, rep = run(sweep(tmp_path, mutate=mutate))
    assert rc != 0
    assert [r for r in arm(rep, "ambience") if not r["ok"]], rep["results"]


def test_ambience_red_on_the_wrong_bucket_for_the_hour(tmp_path):
    """h02 is night. A frame carrying DUSK's light at that hour is a clock bug,
    and it is invisible to every check that has no clock."""
    rc, rep = run(sweep(tmp_path, bucket="night", hour=2, lit_from="dusk"))
    assert rc != 0
    assert [r for r in arm(rep, "ambience") if not r["ok"]], rep["results"]


def test_ambience_red_on_the_2026_07_29_dusk_dither(tmp_path):
    """THE DEFECT ITSELF: an opaque seeded dither replacing 16% of every pixel
    with one in-palette hue. It passed PALETTE_FOREIGN_MASS by construction —
    every covered pixel was a legitimate corpus sand tone — and it passed all
    twelve invariants, because none of them ever saw a composited frame."""
    rc, rep = run(sweep(tmp_path, mutate=lambda p: _dither(p, 0.16, (0xE8, 0xC0, 0x90))))
    assert rc != 0
    assert [r for r in arm(rep, "ambience") if not r["ok"]], rep["results"]


def test_ambience_green_arm_needs_the_pair_and_says_so_without_it(tmp_path):
    """A lit frame with no day twin is UNJUDGED and NON-ZERO, never a quiet pass."""
    d = sweep(tmp_path)
    man = json.loads((d / "frames.json").read_text())
    man["frames"] = [f for f in man["frames"] if f["bucket"] != "day"]
    (d / "frames.json").write_text(json.dumps(man))
    rc, rep = run(d)
    assert rc != 0
    amb = arm(rep, "ambience")
    assert amb and not amb[0]["ok"] and "UNJUDGED" in amb[0]["detail"]


# ── grain: the structure arm, and that it is not the same arm ───────────────
def test_grain_red_on_the_dither(tmp_path):
    """THE AMBIENCE STRUCTURE LAW. A dither is a decision per POSITION; measured
    on real frames the pass it replaced ran 4.0x the art's own grain."""
    rc, rep = run(sweep(tmp_path, mutate=lambda p: _dither(p, 0.16, (0xE8, 0xC0, 0x90))))
    assert rc != 0
    assert [r for r in arm(rep, "grain") if not r["ok"]], rep["results"]


def test_grain_catches_what_the_histogram_arm_cannot(tmp_path):
    """PERMUTE the lit frame's pixels: the histogram is bit-identical, so the
    ambience arm sees nothing, and every edge in the frame has moved.

    If this passed both arms, one of them would be decoration — and it is the
    exact shape of a position-dependent pass that keeps the palette legal, which
    is what the veil was.
    """
    rc, rep = run(sweep(tmp_path, mutate=_permute))
    assert rc != 0
    assert all(r["ok"] for r in arm(rep, "ambience")), "the histogram is unchanged"
    assert [r for r in arm(rep, "grain") if not r["ok"]], rep["results"]


def test_grain_refuses_a_flat_day_twin(tmp_path):
    """A ratio against zero proves nothing, so a flat day frame is UNJUDGED."""
    rc, rep = run(sweep(tmp_path, day_kw={"flat": True}))
    assert rc != 0
    g = arm(rep, "grain")
    assert g and not g[0]["ok"]


# ── grade ───────────────────────────────────────────────────────────────────
def test_grade_red_on_a_washed_out_day_frame(tmp_path):
    """check_light's own failure: a frame washed toward white."""
    def wash(_p):
        pass
    d = sweep(tmp_path)
    day = d / "day.png"
    im = Image.open(day).convert("RGB")
    px = im.load()
    for y in range(im.size[1]):
        for x in range(im.size[0]):
            r, g, b = px[x, y]
            px[x, y] = (min(255, r + 90), min(255, g + 90), min(255, b + 90))
    im.save(day)
    rc, rep = run(d)
    assert rc != 0
    assert [r for r in arm(rep, "grade") if not r["ok"]], rep["results"]


def test_grade_refuses_a_frame_with_no_island_in_it(tmp_path):
    """All open sea: there is nothing whose grade to judge, and saying so beats
    reporting the ocean's own flatness as a washed-out world."""
    rc, rep = run(sweep(tmp_path, day_kw={"all_sea": True}))
    assert rc != 0
    g = arm(rep, "grade")
    assert g and not g[0]["ok"] and "UNJUDGED" in g[0]["detail"]


# ── water ───────────────────────────────────────────────────────────────────
def test_water_red_when_the_sea_is_brighter_than_any_water_this_world_draws(tmp_path):
    """The veil law, on the frame the harness captured rather than on one PNG
    somebody remembered to take."""
    def brighten(p):
        im = Image.open(p).convert("RGB")
        px = im.load()
        sea = set(ambience_py.sea("night"))
        for y in range(im.size[1]):
            for x in range(0, im.size[0], 6):
                if px[x, y] in sea:
                    px[x, y] = (0xF2, 0xD8, 0xB4)
        im.save(p)
    rc, rep = run(sweep(tmp_path, mutate=brighten))
    assert rc != 0
    assert [r for r in arm(rep, "water") if not r["ok"]], rep["results"]


# ── surface: the neighbour law ──────────────────────────────────────────────
def test_surface_red_on_the_2026_07_29_dusk_dither(tmp_path):
    """THE DEFECT, judged by the arm built for its shape rather than its size.

    Every apricot pixel in that pass was a legitimate corpus sand tone, which is
    why `PALETTE_FOREIGN_MASS` returned green: a membership test asks whether a
    colour EXISTS in the art and never whether it belongs on the surface it
    landed on. This arm asks the second question by counting tones per tile.
    """
    rc, rep = run(sweep(tmp_path, mutate=lambda p: _dither(p, 0.16, (0xE8, 0xC0, 0x90))))
    assert rc != 0
    assert [r for r in arm(rep, "surface") if not r["ok"]], rep["results"]


def test_surface_catches_the_veil_ambience_and_grain_are_both_blind_to(tmp_path):
    """THE ARM'S REASON TO EXIST, and the test that would make it decoration if
    it failed.

    A LUMINANCE-MATCHED chroma veil, at 0.4% coverage, on the island only.
      * `grain` reads edge energy in |ΔL| — the veil preserves each pixel's
        luminance exactly, so it adds none and grain passes.
      * `ambience` reads the histogram — 0.4% of pixels moves mean by 0.38 and
        saturation by 0.0025 on a real frame, both an order under the bounds.
      * `water` covers open water only, so the island is not its surface; the
        veil is placed there ON PURPOSE, or this test would be re-proving the
        water probe.
    Measured on the shipped renderer at this coverage: ambience Δmean 0.38 /
    Δsat 0.0025 (bounds 1.5 / 0.015) and grain 4.14 against the day frame's
    7.81 — both pass — while this arm reads 51% of tiles. Assert all three,
    because "the new arm is red" alone would not show it sees anything new.
    """
    rc, rep = run(sweep(tmp_path, mutate=_chroma_veil_on_the_island(0.004)))
    assert rc != 0
    assert all(r["ok"] for r in arm(rep, "ambience")), arm(rep, "ambience")
    assert all(r["ok"] for r in arm(rep, "grain")), arm(rep, "grain")
    assert all(r["ok"] for r in arm(rep, "water")), arm(rep, "water")
    assert [r for r in arm(rep, "surface") if not r["ok"]], rep["results"]


def test_surface_green_when_the_pass_only_merges_tones(tmp_path):
    """ONE-DIRECTIONAL BY INTENT, not by accident.

    Ambience legitimately collapses distinct day tones onto one lit tone — the
    real sweep merges 230-2784 tiles' worth. An arm that reddened on any change
    to the tone count would fire on every honest frame, and the way to prove it
    does not is to hand it a pass that ONLY merges: a hard posterise, which
    destroys tones everywhere and creates none.
    """
    rc, rep = run(sweep(tmp_path, mutate=_posterise))
    su = arm(rep, "surface")
    assert su and all(r["ok"] for r in su), su
    assert all("0/300 tiles gained" in r["detail"] for r in su), su


def test_surface_unjudged_without_a_twin_carrying_the_same_overlays(tmp_path):
    """No twin means nothing was measured, and a green would claim otherwise."""
    d = sweep(tmp_path)
    man = json.loads((d / "frames.json").read_text())
    man["frames"] = [f for f in man["frames"] if f["bucket"] != "day"]
    (d / "frames.json").write_text(json.dumps(man))
    rc, rep = run(d)
    assert rc != 0
    su = arm(rep, "surface")
    assert su and not su[0]["ok"] and "UNJUDGED" in su[0]["detail"], su


def test_a_daylight_only_sweep_is_unjudged_by_both_pair_arms(tmp_path):
    """A SWEEP THAT NEVER LEFT NOON, which is the one input that reaches the
    `no pairs at all` branch of either pair arm.

    Written because the two tests above it did NOT reach it. Dropping the day
    frame from the manifest leaves the lit frame ORPHANED, and the orphan branch
    answers first — so with `if not pairs:` and `if not spairs:` deleted outright,
    both of those tests still passed. Proven by defeating each branch in turn:
    the older `ambience` one had shipped in exactly that state.

    `--hours 13` produces this directory, so it is a reachable invocation and not
    a contrived one: no lit frame exists, nothing is orphaned, and both clock arms
    have to say they looked at nothing rather than printing no line at all.
    """
    d = sweep(tmp_path)
    man = json.loads((d / "frames.json").read_text())
    man["frames"] = [f for f in man["frames"] if f["bucket"] == "day"]
    assert man["frames"], "the fixture must still carry its day frame"
    (d / "frames.json").write_text(json.dumps(man))
    rc, rep = run(d)
    assert rc != 0
    for name in ("ambience", "surface"):
        a = arm(rep, name)
        assert a, f"{name} printed no line at all on a daylight-only sweep: {rep['results']}"
        assert not a[0]["ok"] and "UNJUDGED" in a[0]["detail"], a


def test_surface_unjudged_when_the_twin_is_a_different_size(tmp_path):
    """Two grids that do not line up have no tile in common, and comparing tile
    (0,0) of a 320px frame with tile (0,0) of a 160px one is comparing two
    different parts of the world."""
    d = sweep(tmp_path)
    day = d / "day.png"
    Image.open(day).convert("RGB").resize((W // 2, H // 2)).save(day)
    rc, rep = run(d)
    assert rc != 0
    su = [r for r in arm(rep, "surface") if not r["ok"]]
    assert su and "UNJUDGED" in su[0]["detail"], arm(rep, "surface")


def test_surface_unjudged_when_the_frame_is_smaller_than_one_tile(tmp_path):
    """THE DEGENERATE END. Zero tiles is zero denominators — a share over an
    empty set is either a crash or a silent 0.00% green, and the second is the
    disabled sensor this file exists to make impossible."""
    d = sweep(tmp_path)
    for n in ("day.png", "lit.png", "twin.png"):
        p = d / n
        Image.open(p).convert("RGB").resize((8, 8)).save(p)
    rc, rep = run(d)
    assert rc != 0
    su = [r for r in arm(rep, "surface") if not r["ok"]]
    assert su and "UNJUDGED" in su[0]["detail"], arm(rep, "surface")


# ── determinism ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("delta", [(1, 0, 0), (0, 1, 0), (0, 0, 1)])
def test_determinism_red_when_two_captures_differ(tmp_path, delta):
    """One pixel is enough: every day-vs-bucket arm rests on the pair being the
    same island, and a renderer that is not reproducible makes them noise.

    ONE CHANNEL AT A TIME, on purpose. The first version compared the difference
    IMAGE converted to 'L', whose ITU-601 weights round a pure one-unit red
    difference to zero — so two different frames read as identical and every arm
    beneath this one was standing on a fail-open. Only the red case caught it.
    """
    d = sweep(tmp_path)
    twin = d / "twin.png"
    im = Image.open(twin).convert("RGB")
    px = im.load()
    r, g, b = px[0, 0]
    px[0, 0] = (r + delta[0], g + delta[1], b + delta[2])
    im.save(twin)
    rc, rep = run(d)
    assert rc != 0
    det = arm(rep, "determinism")
    assert det and not det[0]["ok"]


# ── killswitch ──────────────────────────────────────────────────────────────
def test_killswitch_red_when_the_wash_stops_drawing(tmp_path):
    """The killswitch frame identical to its twin means the red wash did not
    paint — the org is stopped and the world does not say so."""
    rc, rep = run(sweep(tmp_path, killswitch=True))     # ks frame == its twin
    assert rc != 0
    ks = arm(rep, "killswitch")
    assert ks and not ks[0]["ok"], rep["results"]


def test_killswitch_unjudged_rather_than_green_when_absent(tmp_path):
    """A sweep that captured no killswitch frame has not looked at the wash."""
    rc, rep = run(sweep(tmp_path, killswitch=False))
    assert rc != 0
    ks = arm(rep, "killswitch")
    assert ks and not ks[0]["ok"] and "UNJUDGED" in ks[0]["detail"]


# ── the invocation itself ───────────────────────────────────────────────────
def test_a_directory_with_no_manifest_is_exit_2(tmp_path):
    """PNGs with no manifest cannot say which hour or zoom any of them is."""
    (tmp_path / "lone.png").write_bytes(b"")
    p = subprocess.run([sys.executable, str(JUDGE), str(tmp_path)],
                       capture_output=True, text=True)
    assert p.returncode == 2


def test_a_manifest_listing_no_frames_is_exit_2(tmp_path):
    """The degenerate end. A capture step that produced nothing must not reach
    the arms at all — 38 arms over 0 frames is the fastest possible green."""
    d = sweep(tmp_path)
    man = json.loads((d / "frames.json").read_text())
    man["frames"] = []
    (d / "frames.json").write_text(json.dumps(man))
    p = subprocess.run([sys.executable, str(JUDGE), str(d)], capture_output=True, text=True)
    assert p.returncode == 2


def test_a_manifest_naming_a_missing_frame_is_exit_2(tmp_path):
    d = sweep(tmp_path)
    (d / "lit.png").unlink()
    p = subprocess.run([sys.executable, str(JUDGE), str(d)], capture_output=True, text=True)
    assert p.returncode == 2


# ── mutations ───────────────────────────────────────────────────────────────
def _dither(p: Path, coverage: float, hue: tuple[int, int, int]) -> None:
    """The 2026-07-29 pass: an opaque seeded dither in one in-palette hue."""
    im = Image.open(p).convert("RGB")
    px = im.load()
    rnd = random.Random(7)
    for y in range(im.size[1]):
        for x in range(im.size[0]):
            if rnd.random() < coverage:
                px[x, y] = hue
    im.save(p)


def _chroma_veil_on_the_island(coverage: float):
    """A veil that keeps every pixel's LUMINANCE and replaces its hue.

    Built to be invisible to the two arms that already exist. `grain` measures
    |ΔL| between adjacent pixels, so a luminance-preserving pass moves it by
    nothing; `ambience` measures the histogram, and at this coverage the shift is
    an order under its bounds. Confined to the island band (x >= 120), which is
    the region the water probe does not judge — so a red here cannot be the water
    arm wearing another name.
    """
    def mutate(p: Path) -> None:
        im = Image.open(p).convert("RGB")
        px = im.load()
        rnd = random.Random(7)
        for y in range(20, im.size[1] - 20):
            for x in range(120, im.size[0] - 20):
                if rnd.random() < coverage:
                    r, g, b = px[x, y]
                    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
                    v = max(0, min(255, int(lum / (0.2126 + 0.0722))))
                    px[x, y] = (v, 0, v)
        im.save(p)
    return mutate


def _posterise(p: Path) -> None:
    """A pass that only ever MERGES tones — the direction the surface law allows."""
    im = Image.open(p).convert("RGB")
    px = im.load()
    for y in range(im.size[1]):
        for x in range(im.size[0]):
            px[x, y] = tuple((c >> 5) << 5 for c in px[x, y])
    im.save(p)


def _permute(p: Path) -> None:
    """Same pixels, different places — the histogram cannot see this at all."""
    im = Image.open(p).convert("RGB")
    data = list(im.getdata())
    random.Random(11).shuffle(data)
    im.putdata(data)
    im.save(p)


def _desaturate(p: Path, keep: float) -> None:
    """What the killswitch wash does, at the measured magnitude (0.42 -> 0.24)."""
    im = Image.open(p).convert("RGB")
    px = im.load()
    for y in range(im.size[1]):
        for x in range(im.size[0]):
            r, g, b = px[x, y]
            m = (r + g + b) / 3
            px[x, y] = (int(m + (r - m) * keep), int(m + (g - m) * keep),
                        int(m + (b - m) * keep))
    im.save(p)
