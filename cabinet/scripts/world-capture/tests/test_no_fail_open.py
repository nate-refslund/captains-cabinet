#!/usr/bin/env python3
"""No arm may report a PASS when the thing it guards is not there.

WHY THIS FILE EXISTS. check_shadows was found green on a frame with every shadow
deleted (2026-07-27). The audit that followed found the same shape in eight more of
the twelve arms: three globbed an assets directory, so pointing them at a path that
does not exist made the loop never run and each printed "0 problems" and PASSED; five
more passed over an empty sprite list, a missing state key, or zero contested pixels.
A loop with nothing in it prints a zero, and a zero reads like evidence.

Every one of those was fixed by hand and proven by hand. This is the arm that keeps
them fixed, and it needs NO capture and NO fixture: point each check at nothing at all
— a render path that does not exist, a blueprint with no sprites, no ground layer, no
id buffer, no state — and none of the twelve may come back green. That property is
cheap to state, cheap to run, and it is exactly the property that was silently false.

It runs against `mirror/`, which is what CI actually executes.

THE SECOND HALF MATTERS AS MUCH: an honest zero must stay GREEN. A camp with no lanes,
a frame with no sprite big enough to carry a shadow, layers that do not overlap — those
are legal absences, and there the arm must pass, say UNJUDGED, and CLAIM NO SURFACE so
verify.py goes on reporting the surface as unchecked. A test that only demanded red
would be satisfied by an arm that fails on everything.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAPTURE = HERE.parent
MIRROR = CAPTURE / "mirror"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


C = _load(MIRROR / "checks" / "world_checks.py", "mirrored_world_checks")
PAL = _load(MIRROR / "designs" / "world-mockup-v2" / "palette.py", "mirrored_palette").flat_colors()

NOWHERE = "/tmp/no-such-render-2026-07-27/frame.png"
NO_ASSETS = "/tmp/no-such-assets-dir-2026-07-27"

# One entry per registered check, each called with EVERY input absent: a render that is
# not on disk (so no ground layer, no id buffers), a blueprint with no sprites, no
# lanes, no layers, no state. `verify.py`'s REGISTRY is the list this must cover, and
# the count is asserted below so a thirteenth check cannot be added without a row here.
EMPTY_BP: dict = {}
EMPTY_STATE: dict = {}

NOTHING_AT_ALL = {
    "on_road": lambda: C.check_on_road(NOWHERE, EMPTY_BP),
    "stacking": lambda: C.check_stacking(NOWHERE, EMPTY_BP),
    "sprite_opacity": lambda: C.check_sprite_opacity(NO_ASSETS, EMPTY_BP),
    "sprite_cutoff": lambda: C.check_sprite_cutoff(NO_ASSETS, EMPTY_BP),
    "palette": lambda: C.check_palette(NO_ASSETS, EMPTY_BP, PAL),
    "state_traceable": lambda: C.check_state_traceable(EMPTY_BP, EMPTY_STATE, set()),
    "paint_fidelity": lambda: C.check_paint_fidelity(NOWHERE, EMPTY_BP, NO_ASSETS),
    "era": lambda: C.check_era(EMPTY_BP, EMPTY_STATE),
    "light": lambda: C.check_light(NOWHERE, EMPTY_BP, EMPTY_STATE),
    "terrain": lambda: C.check_terrain(NOWHERE, EMPTY_BP, EMPTY_STATE),
    "depth_order": lambda: C.check_depth_order(NOWHERE, EMPTY_BP),
    "shadows": lambda: C.check_shadows(NOWHERE, EMPTY_BP),
}


def test_the_registry_and_this_file_cover_the_same_checks():
    """A thirteenth check must not be able to arrive without a no-fail-open row."""
    verify_src = (MIRROR / "checks" / "verify.py").read_text()
    registered = set(re.findall(r'^\s*\("(\w+)",\s*"\d{4}-\d{2}-\d{2}"', verify_src, re.M))
    assert registered == set(NOTHING_AT_ALL), (
        f"verify.py registers {sorted(registered)}; this file covers "
        f"{sorted(NOTHING_AT_ALL)} — every registered check needs a degenerate row")
    assert len(registered) == 12


@pytest.mark.parametrize("name", sorted(NOTHING_AT_ALL))
def test_no_check_passes_with_every_input_absent(name):
    check, ok, detail, surfaces = NOTHING_AT_ALL[name]()
    assert check == name
    assert ok is False, (
        f"{name} reported a PASS with no render, no ground layer, no assets, no id "
        f"buffer, no sprites and no state: {detail!r}. That is the fail-open this "
        "whole suite exists to prevent — a check that could not run has not passed.")
    assert surfaces == set(), (
        f"{name} could not run and still claimed {sorted(surfaces)}. A claimed surface "
        "is subtracted from verify.py's unchecked list, so claiming one here hides the "
        "hole rather than reporting it.")


# ---------------------------------------------------------------- the other direction
def _sprite(n, x=100, y=100, w=60, h=60):
    return {"n": n, "x": x, "y": y, "w": w, "h": h}


def _frame(tmp_path, size=(160, 120)):
    """A render plus the buffers a check looks for beside it. Inputs PRESENT, subject
    absent — which is the case the arms must stay GREEN on."""
    from PIL import Image
    d = tmp_path / "cap"; d.mkdir()
    Image.new("RGB", size, (90, 130, 80)).save(d / "frame.png")
    Image.new("RGB", size, (90, 130, 80)).save(d / "frame.ground.png")
    Image.new("RGB", size, (0, 0, 0)).save(d / "frame.ids.png")
    Image.new("RGB", size, (0, 0, 0)).save(d / "frame.idsrev.png")
    return str(d / "frame.png")


def test_a_camp_with_no_lanes_stays_green_and_claims_no_road_surface(tmp_path):
    """THE INVERSE ARM, and it carries as much weight as the twelve above. Without it,
    a check that failed on EVERYTHING would satisfy this file — and an arm that cries
    wolf on every honest zero gets switched off, which is the same hole by a slower
    route. A camp has not worn any paths yet: green, UNJUDGED, `roads` unclaimed."""
    render = _frame(tmp_path)
    bp = {"sprites": [_sprite("camp_tent")], "lanes": {}, "state": {"era": "camp"}}
    name, ok, detail, surfaces = C.check_on_road(render, bp)
    assert ok is True, detail
    assert "UNJUDGED" in detail
    assert surfaces == set(), "an arm that judged nothing may not claim `roads`"


def test_layers_that_never_overlap_stay_green_and_claim_no_depth_surface(tmp_path):
    """Zero contested pixels is honest when nothing could contest anything."""
    render = _frame(tmp_path)
    bp = {"sprites": [_sprite("a")],
          "layers": [{"id": 1, "rgb": [1, 0, 0], "sort_y": 10, "x": 0, "y": 0, "w": 8, "h": 8},
                     {"id": 2, "rgb": [2, 0, 0], "sort_y": 20, "x": 120, "y": 90, "w": 8, "h": 8}]}
    name, ok, detail, surfaces = C.check_depth_order(render, bp)
    assert ok is True, detail
    assert "UNJUDGED" in detail and surfaces == set()


def test_overlapping_layers_with_dead_buffers_go_red(tmp_path):
    """The same zero, with the layers piled on top of each other: now it is a dead
    sensor, not a clean frame."""
    render = _frame(tmp_path)
    bp = {"sprites": [_sprite("a")],
          "layers": [{"id": 1, "rgb": [1, 0, 0], "sort_y": 10, "x": 0, "y": 0, "w": 80, "h": 80},
                     {"id": 2, "rgb": [2, 0, 0], "sort_y": 20, "x": 4, "y": 4, "w": 80, "h": 80}]}
    name, ok, detail, surfaces = C.check_depth_order(render, bp)
    assert ok is False, detail
    assert surfaces == set()


def test_an_empty_sprite_list_is_red_in_every_arm_that_iterates_one(tmp_path):
    """The inputs are all PRESENT and the blueprint draws nothing. Eight arms iterate
    that array, and every one of them used to print a zero over it — `state_traceable`
    cleared the frame, `paint_fidelity` and `shadows` called it UNJUDGED and green. A
    frame that draws nothing is a broken emit, not an empty world."""
    render = _frame(tmp_path)
    bp = {"sprites": [], "lanes": {"a": [[0, 0], [10, 10]]}, "layers": [],
          "state": {"era": "hamlet", "justified": [], "ladders": {"well": {}}}}
    for name, call in (
        ("on_road", lambda: C.check_on_road(render, bp)),
        ("stacking", lambda: C.check_stacking(render, bp)),
        ("state_traceable", lambda: C.check_state_traceable(bp, bp["state"], set())),
        ("paint_fidelity", lambda: C.check_paint_fidelity(render, bp, str(tmp_path))),
        ("era", lambda: C.check_era(bp, bp["state"])),
        ("shadows", lambda: C.check_shadows(render, bp)),
    ):
        n, ok, detail, surfaces = call()
        assert n == name and ok is False and surfaces == set(), f"{name}: {detail!r}"


def test_a_drawn_lighthouse_with_no_lamp_rung_is_red(tmp_path):
    """Deleting the TOWER was caught; deleting its STATE was not. The subject is in the
    frame and the thing that decides whether its glow is legal has gone."""
    render = _frame(tmp_path)
    bp = {"sprites": [_sprite("lighthouse", w=60, h=90)]}
    n, ok, detail, surfaces = C.check_light(render, bp, {"era": "hamlet", "ladders": {}})
    assert ok is False
    assert "no measured lighthouse_lamp rung" in detail, detail
    assert "lamp" not in surfaces


def test_era_with_no_ladders_is_unverifiable(tmp_path):
    """The rung arm's whole subject is `state.ladders`. An empty dict made it report
    '0 of 0 ladders judged' and pass."""
    bp = {"sprites": [_sprite("great_house")]}
    n, ok, detail, surfaces = C.check_era(bp, {"era": "hamlet"})
    assert ok is False and "UNVERIFIABLE" in detail and surfaces == set()


def test_unjudged_is_green_and_claims_no_surface():
    """The real inverse case, with the inputs present: `_unjudged` must stay green."""
    n, ok, detail, surfaces = C._unjudged("demo", "the subject is not in this frame")
    assert ok is True and surfaces == set() and "UNJUDGED" in detail
    n, ok, detail, surfaces = C._unverifiable("demo", "the input is gone")
    assert ok is False and surfaces == set() and "UNVERIFIABLE" in detail
    n, ok, detail, surfaces = C._illegal("demo", "the absence is itself the defect")
    assert ok is False and surfaces == set()


def test_a_counting_arm_goes_red_under_its_floor():
    """`_counted` is the shared shape for every counting arm: nothing judged is not a
    clean sweep, and it must drop the surface claim as well as the green."""
    n, ok, detail, surfaces = C._counted("demo", [], 0, 78, ["a", "b"], 0.80, "problems",
                                         {"art"})
    assert ok is False and surfaces == set() and "0/78" in detail
    n, ok, detail, surfaces = C._counted("demo", [], 78, 78, [], 0.80, "problems", {"art"})
    assert ok is True and surfaces == {"art"}
