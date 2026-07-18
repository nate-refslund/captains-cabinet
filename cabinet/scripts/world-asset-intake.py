#!/usr/bin/env python3.12
"""world-asset-intake.py — artist-delivery intake for Cabinet World sprites.

The RECEIVING half of the asset production loop (the forge/spec pair in
docs/runbooks/world-asset-forge.md is the generating half): the onboarded
artist delivers a batch of transparent PNGs — one file per canonical
worklist entry, named `<entry-id>.png` — into a local folder, and this
tool validates every file against `cabinet/world/asset-worklist.json`,
writes a machine + human report with EXACT artist-actionable reasons
(coordinates, color hexes, expected-vs-actual sizes), composes a
deterministic conformance test scene from the accepted sprites, and —
only on the explicit `--promote` flag — installs accepted PNGs into
`cabinet/dashboard/public/world-assets/originals/<object>/` with
content-addressed manifest rows (world-asset-install.py row conventions,
license "owned — org-original").

Validation per file:
  * filename stem must EXACTLY equal a worklist entry id (safe charset;
    unknown ids get did-you-mean suggestions);
  * `covered_by` rows refuse (no new art — the named family supplies it);
    `size: null` cross-refs refuse; `staged` entries accept with a note;
  * PNG magic + IHDR dims BEFORE any pixel decode; dims must equal the
    entry's `size` {w,h}; ANIMATED entries are delivered as ONE horizontal
    strip of `frames` frames => expected file is (w*frames) x h
    (world-asset-install.py gif_to_sheet `_sheetN` convention);
  * 16px art-grid law; alpha channel required (RGBA export);
  * stray-halo scan: semi-transparent pixels (alpha 1..254) 4-adjacent to
    fully transparent ones = anti-aliased fringe; > --halo-max fails with
    coordinates;
  * optional --palette STRIP.png: exact-RGB membership over alpha>0
    pixels; off-palette colors reported hex + count + first coordinate;
    > --palette-max fails.

The `--gate` flag additionally runs the committed
cabinet/scripts/world-aesthetic/world-aesthetic-gate.py --mechanical over
the test scene and folds the verdict into the report as INFORMATIONAL
only — the committed calibration is fitted to the outgoing LimeZu estate
(runbook §5), so conforming new-style artist art may honestly fail it
until the Phase-0 style-bible recalibration.

Determinism law: no timestamps, no RNG anywhere in outputs — reports and
the test scene are byte-identical across reruns of the same batch. No
network anywhere in this tool.

Usage:
  python3.12 cabinet/scripts/world-asset-intake.py DELIVERY_DIR \
      [--worklist cabinet/world/asset-worklist.json] \
      [--palette STRIP.png] [--palette-max 0] [--halo-max 8] [--gate] \
      [--report-dir DIR] [--scene-out PNG] \
      [--promote [--promote-accepted-only]] \
      [--assets-root DIR] [--manifest JSON] [--batch-tag TAG]

Exit codes: 0 all accepted; 1 any fix_needed (reports still written);
2 usage error / promote refusal.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import io
import json
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

from PIL import Image

REPO = Path(os.environ.get("CABINET_ROOT")
            or Path(__file__).resolve().parents[2])
SCRIPT_DIR = Path(__file__).resolve().parent

DEFAULT_WORKLIST = REPO / "cabinet" / "world" / "asset-worklist.json"
DEFAULT_ASSETS_ROOT = (REPO / "cabinet" / "dashboard" / "public"
                       / "world-assets")
AESTHETIC_GATE = SCRIPT_DIR / "world-aesthetic" / "world-aesthetic-gate.py"

GRID = 16                                  # world-asset-gate.py:43 art grid law
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"           # world-asset-gate.py:42
LICENSE = "owned — org-original"           # world-asset-forge.py:94 / runbook §6
REPORT_SCHEMA = "cabinet.world.intake-report/v1"

DEFAULT_HALO_MAX = 8       # tolerated semi-transparent fringe pixels per file
DEFAULT_PALETTE_MAX = 0    # tolerated off-palette pixels per file
MAX_ANALYZE_DIM = 2048     # decompression-bomb guard: refuse pixel decode
                           # above this (largest worklist canvas is ~384px)
HALO_COORDS_MAX = 10       # coordinates listed per halo report
OFF_PALETTE_COLORS_MAX = 32  # distinct off-palette colors listed per file

# conformance-scene constants — own neutral grays, NEVER pack pixels
# (this is a conformance sheet, not world art)
CHECKER_A = (92, 92, 92, 255)
CHECKER_B = (76, 76, 76, 255)
SCENE_MAX_ROW_W = 512
SCENE_GUTTER = 16

GATE_CAVEAT = ("informational only — the committed calibration is fitted "
               "to the outgoing LimeZu estate (world-asset-forge runbook "
               "§5); conforming new-style artist art may honestly fail it "
               "until the Phase-0 style-bible recalibration")

EXIT_OK = 0
EXIT_FIX_NEEDED = 1
EXIT_USAGE = 2

# id charset mirrors world-asset-forge.py:107 (itself install:96 minus "/");
# every one of the 371 canonical worklist ids matches _ID_RE exactly, so a
# delivered filename can never smuggle a path separator or traversal.
_SAFE_ID = re.compile(r"[^A-Za-z0-9._-]+")
_ID_RE = re.compile(r"[A-Za-z0-9._-]+")


class IntakeError(RuntimeError):
    """Intake-level refusal with a human-actionable message."""


# ---------------------------------------------------------------- helpers
def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def png_dimensions(data: bytes) -> tuple[int, int] | None:
    """Width/height from the IHDR chunk — copied world-asset-gate.py:46-53
    so intake never decodes pixels before the magic+IHDR pre-check."""
    if len(data) < 33 or data[:8] != PNG_MAGIC:
        return None
    if data[12:16] != b"IHDR":
        return None
    w, h = struct.unpack(">II", data[16:24])
    return int(w), int(h)


def sanitize_id(raw: str) -> str:
    """Single-segment safe token — copied world-asset-forge.py:133-146
    (leading dots stripped: no dot-relative / hidden / bare-sep starts)."""
    s = raw.replace(" - ", "-").replace(" ", "_")
    s = _SAFE_ID.sub("_", s)
    while "__" in s:
        s = s.replace("__", "_")
    s = s.rstrip("_")
    while s and s[0] in "._":
        s = s[1:]
    return s


def contained(root: Path, candidate: Path) -> bool:
    """Realpath-jail check — copied world-asset-forge.py:149-158 (itself
    mirroring world-asset-install.py contained() / gate containment)."""
    real = Path(os.path.realpath(candidate))
    root_real = Path(os.path.realpath(root))
    try:
        real.relative_to(root_real)
    except ValueError:
        return False
    return True


def _write_jailed(out_root: Path, path: Path, data: bytes) -> None:
    """Jailed write — copied world-asset-forge.py:174-179."""
    if not contained(out_root, path):
        raise IntakeError(f"REFUSED: write escapes the report dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _rgba_pixels(img: Image.Image) -> list[tuple[int, int, int, int]]:
    """RGBA tuples via tobytes() — copied world-asset-forge.py:397-402
    (avoids the Pillow-12-deprecated getdata())."""
    b = img.tobytes()
    return [tuple(b[i:i + 4]) for i in range(0, len(b), 4)]


def load_palette_colors(strip: Image.Image) -> list[tuple[int, int, int]]:
    """Ordered unique opaque colors of a palette strip — copied
    world-asset-forge.py:477-492 (same >256 sanity refusal)."""
    seen: set[tuple[int, int, int]] = set()
    out: list[tuple[int, int, int]] = []
    for r, g, b, a in _rgba_pixels(strip.convert("RGBA")):
        if a == 0:
            continue
        c = (r, g, b)
        if c not in seen:
            seen.add(c)
            out.append(c)
    if not out:
        raise IntakeError("palette strip contains no opaque pixels")
    if len(out) > 256:
        raise IntakeError(f"palette strip has {len(out)} colors — expected "
                          "a small strip (<=256); is this really a strip?")
    return out


# ---------------------------------------------------------------- worklist
def load_worklist(path: Path) -> tuple[dict[str, dict], bytes]:
    """Worklist entries keyed by id + raw bytes (report provenance sha256).
    Adapted from world-asset-forge.py load_worklist (:531-543)."""
    if not path.is_file():
        raise IntakeError(f"worklist not found: {path} — generate it with "
                          "cabinet/scripts/world-asset-spec.py")
    raw = path.read_bytes()
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise IntakeError(f"worklist {path} is not valid JSON: {e}") from None
    entries = doc.get("entries") if isinstance(doc, dict) else None
    if not isinstance(entries, list) or not entries:
        raise IntakeError(f"worklist {path} has no entries[] — expected "
                          "cabinet.world.asset-worklist/v1")
    by_id: dict[str, dict] = {}
    for e in entries:
        if isinstance(e, dict) and isinstance(e.get("id"), str):
            by_id[e["id"]] = e
    if not by_id:
        raise IntakeError(f"worklist {path} entries carry no usable ids")
    return by_id, raw


def expected_size(entry: dict) -> tuple[int, int, int | None]:
    """(expected_w, expected_h, frames|None) for a DELIVERED file.

    The canonical worklist (cabinet.world.asset-worklist/v1) carries
    `size` as a {w,h} px dict plus `animated`+`frames` — there is no
    size_hint field. An animated entry is delivered as ONE horizontal
    strip of `frames` frames, so the expected file width is w*frames
    (world-asset-install.py gif_to_sheet `_sheetN` convention, :165-181).
    Raises IntakeError for size:null cross-ref rows and broken animated
    declarations."""
    size = entry.get("size")
    if not (isinstance(size, dict) and isinstance(size.get("w"), int)
            and isinstance(size.get("h"), int)
            and size["w"] > 0 and size["h"] > 0):
        raise IntakeError("entry has no usable canvas size (size: "
                          f"{size!r}) — no deliverable is expected for it")
    w, h = size["w"], size["h"]
    if entry.get("animated"):
        frames = entry.get("frames")
        if not (isinstance(frames, int) and frames >= 2):
            raise IntakeError("animated entry with unusable frame count "
                              f"({entry.get('frames')!r}) — fix the "
                              "worklist before intake")
        return w * frames, h, frames
    return w, h, None


# ---------------------------------------------------------------- pixels
def image_has_alpha(img: Image.Image) -> bool:
    """Delivered with a usable alpha channel? RGBA/LA/PA carry one;
    palette images only when a transparency table is present."""
    if img.mode in ("RGBA", "LA", "PA"):
        return True
    return img.mode == "P" and "transparency" in img.info


def halo_check(img: Image.Image) -> tuple[int, list[tuple[int, int]]]:
    """Stray-halo scan: semi-transparent pixels (alpha 1..254) 4-adjacent
    to a fully transparent (alpha==0) pixel — the classic anti-aliased
    fringe a soft eraser/feather leaves around a sprite. Canvas edges do
    NOT count as transparent neighbours. Returns (count, first
    HALO_COORDS_MAX coordinates in row-major order)."""
    w, h = img.size
    a = img.getchannel("A").tobytes()
    coords: list[tuple[int, int]] = []
    count = 0
    for y in range(h):
        row = y * w
        for x in range(w):
            v = a[row + x]
            if v == 0 or v == 255:
                continue
            if ((x > 0 and a[row + x - 1] == 0)
                    or (x + 1 < w and a[row + x + 1] == 0)
                    or (y > 0 and a[row - w + x] == 0)
                    or (y + 1 < h and a[row + w + x] == 0)):
                count += 1
                if len(coords) < HALO_COORDS_MAX:
                    coords.append((x, y))
    return count, coords


def palette_check(img: Image.Image, colors: list[tuple[int, int, int]]
                  ) -> tuple[int, list[dict]]:
    """Exact-RGB palette membership over alpha>0 pixels. Returns (total
    off-palette pixel count, per-color records sorted by count desc then
    hex asc, capped at OFF_PALETTE_COLORS_MAX, each with the first
    row-major coordinate)."""
    allowed = set(colors)
    w = img.size[0]
    stats: dict[tuple[int, int, int], dict] = {}
    total = 0
    b = img.tobytes()
    for i in range(0, len(b), 4):
        if b[i + 3] == 0:
            continue
        c = (b[i], b[i + 1], b[i + 2])
        if c in allowed:
            continue
        total += 1
        rec = stats.get(c)
        if rec is None:
            idx = i // 4
            stats[c] = {"c": c, "count": 1,
                        "first": (idx % w, idx // w)}
        else:
            rec["count"] += 1
    ranked = sorted(stats.values(), key=lambda r: (-r["count"], r["c"]))
    out = [{"hex": "#%02x%02x%02x" % r["c"], "count": r["count"],
            "first": list(r["first"])}
           for r in ranked[:OFF_PALETTE_COLORS_MAX]]
    return total, out


# ---------------------------------------------------------------- validate
def validate_file(path: Path, by_id: dict[str, dict],
                  palette_colors: list[tuple[int, int, int]] | None,
                  halo_max: int, palette_max: int) -> dict:
    """One delivery file -> report record. Collects EVERY applicable
    reason (the artist fixes a file once, not once per re-run)."""
    rec: dict = {
        "file": path.name, "id": None, "status": "fix_needed",
        "reasons": [], "notes": [], "expected": None, "actual": None,
        "sha256": None, "halo": None, "off_palette": None,
    }
    reasons: list[str] = rec["reasons"]
    notes: list[str] = rec["notes"]

    if path.suffix.lower() != ".png":
        reasons.append("not a .png delivery — sprites are delivered as one "
                       "transparent PNG per worklist entry id")
        return rec
    stem = path.name[: -len(path.suffix)]
    if not _ID_RE.fullmatch(stem):
        reasons.append(
            f"filename {stem!r} contains characters outside the worklist "
            "id charset [A-Za-z0-9._-] — name the file exactly "
            "<worklist-entry-id>.png")
        return rec
    entry = by_id.get(stem)
    if entry is None:
        sugg = difflib.get_close_matches(stem, sorted(by_id), n=3,
                                         cutoff=0.6)
        hint = (" — did you mean: " + ", ".join(sugg)
                if sugg else "")
        reasons.append(f"unknown worklist id {stem!r}{hint}")
        return rec
    rec["id"] = stem

    cov = entry.get("covered_by")
    if cov:
        reasons.append(f"no new art expected — sprite family supplied by "
                       f"{cov!r} (worklist covered_by); deliver that "
                       "family's entries instead")
        return rec
    try:
        ew, eh, frames = expected_size(entry)
    except IntakeError as e:
        reasons.append(str(e))
        return rec
    rec["expected"] = {"w": ew, "h": eh, "frames": frames}
    if entry.get("staged"):
        notes.append("staged entry — art is accepted and installable now; "
                     "nothing renders until its feed/wiring lands")

    data = path.read_bytes()
    rec["sha256"] = sha256_of(data)
    if data[:8] != PNG_MAGIC:
        reasons.append("not a PNG (magic bytes) — export a real PNG, never "
                       "rename another format")
        return rec
    dims = png_dimensions(data)
    if dims is None:
        reasons.append("unreadable PNG IHDR — the file is corrupt or "
                       "truncated")
        return rec
    aw, ah = dims
    rec["actual"] = {"w": aw, "h": ah}
    if aw > MAX_ANALYZE_DIM or ah > MAX_ANALYZE_DIM:
        reasons.append(f"wrong size: expected {ew}x{eh}, got {aw}x{ah} — "
                       f"beyond the {MAX_ANALYZE_DIM}px analysis bound, "
                       "pixel checks skipped")
        return rec
    if (aw, ah) != (ew, eh):
        if frames:
            reasons.append(
                f"wrong size: expected {ew}x{eh} ({frames} frames of "
                f"{ew // frames}x{eh}, one horizontal strip — the install "
                f"_sheetN convention), got {aw}x{ah}")
        else:
            reasons.append(f"wrong size: expected {ew}x{eh}, got {aw}x{ah}")
    if aw % GRID or ah % GRID:
        reasons.append(f"{aw}x{ah} sits off the {GRID}px art grid")

    try:
        with Image.open(io.BytesIO(data)) as im:
            has_alpha = image_has_alpha(im)
            rgba = im.convert("RGBA")
    except (OSError, ValueError, SyntaxError) as e:
        reasons.append(f"PNG pixel data is unreadable ({e})")
        return rec

    if not has_alpha:
        reasons.append("no alpha channel — export an RGBA PNG with a "
                       "transparent background")
    else:
        count, coords = halo_check(rgba)
        if count:
            rec["halo"] = {"count": count, "max": halo_max,
                           "coords": [list(c) for c in coords]}
            where = ", ".join(f"({x},{y})" for x, y in coords)
            if count > halo_max:
                reasons.append(
                    f"stray halo: {count} semi-transparent fringe "
                    f"pixel(s) (> {halo_max} allowed) at e.g. {where} — "
                    "flatten anti-aliased edges to binary alpha")
            else:
                notes.append(f"minor halo: {count} semi-transparent fringe "
                             f"pixel(s) (<= {halo_max} allowed) at {where}")

    if palette_colors is not None:
        total, offs = palette_check(rgba, palette_colors)
        if total:
            rec["off_palette"] = offs
            det = "; ".join(
                f"{o['hex']} x{o['count']} first "
                f"({o['first'][0]},{o['first'][1]})" for o in offs[:5])
            more = " …" if len(offs) > 5 else ""
            if total > palette_max:
                reasons.append(
                    f"off-palette: {total} pixel(s) outside the master "
                    f"strip (> {palette_max} allowed) — {det}{more} — "
                    "repaint with exact strip colors")
            else:
                notes.append(f"off-palette within tolerance: {total} "
                             f"pixel(s) (<= {palette_max}) — {det}{more}")

    if not reasons:
        rec["status"] = "accepted"
    return rec


# ---------------------------------------------------------------- scene
def compose_scene(accepted: list[dict], delivery: Path) -> Image.Image:
    """Deterministic conformance sheet: accepted sprites sorted by id,
    left-to-right rows on a neutral 2-tone 16px checker, 16px gutters,
    rows capped at SCENE_MAX_ROW_W, canvas padded to the 16 grid. Own
    gray constants only — never pack pixels; byte-identical reruns."""
    sprites: list[Image.Image] = []
    for r in sorted(accepted, key=lambda q: q["id"]):
        with Image.open(delivery / r["file"]) as im:
            sprites.append(im.convert("RGBA"))
    gut = SCENE_GUTTER
    max_w = max(SCENE_MAX_ROW_W,
                max(s.width for s in sprites) + 2 * gut)
    placements: list[tuple[Image.Image, int, int]] = []
    x, y, row_h = gut, gut, 0
    for s in sprites:
        if x > gut and x + s.width + gut > max_w:
            y += row_h + gut
            x, row_h = gut, 0
        placements.append((s, x, y))
        x += s.width + gut
        row_h = max(row_h, s.height)
    total_h = y + row_h + gut
    W = -(-max_w // GRID) * GRID
    H = -(-total_h // GRID) * GRID
    canvas = Image.new("RGBA", (W, H))
    for ty in range(0, H, GRID):
        for tx in range(0, W, GRID):
            col = (CHECKER_A if ((tx // GRID + ty // GRID) % 2 == 0)
                   else CHECKER_B)
            canvas.paste(col, (tx, ty, min(tx + GRID, W),
                               min(ty + GRID, H)))
    for s, px, py in placements:
        canvas.alpha_composite(s, (px, py))
    return canvas


def png_bytes_of(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------- gate seam
def run_aesthetic_gate(scene_path: Path) -> tuple[int, str]:
    """THE subprocess seam (tests mock this): run the committed aesthetic
    gate mechanically over the conformance scene. argv LIST, never a
    shell; sys.executable is the house python3.12 by launch law."""
    proc = subprocess.run(
        [sys.executable, str(AESTHETIC_GATE), "--mechanical",
         "--render", str(scene_path)],
        capture_output=True, text=True)
    return proc.returncode, proc.stdout


def fold_gate(exit_code: int, stdout: str) -> dict:
    """Fold the gate envelope into the report. The envelope's `generated`
    timestamp and absolute-path `inputs` are deliberately dropped —
    intake reports carry no timestamps (determinism law)."""
    out: dict = {"exit": exit_code, "note": GATE_CAVEAT}
    try:
        env = json.loads(stdout)
        out["ok"] = bool(env.get("ok"))
        out["counts"] = env.get("counts")
        out["gates_run"] = env.get("gates_run")
        out["skipped"] = env.get("skipped")
    except ValueError:
        out["parse_error"] = True
        out["output_tail"] = stdout.strip()[-400:]
    return out


# ---------------------------------------------------------------- promote
def promote(accepted: list[dict], by_id: dict[str, dict], delivery: Path,
            assets_root: Path, manifest_path: Path,
            batch_tag: str) -> dict:
    """Copy accepted PNGs VERBATIM into originals/<object>/ and upsert
    manifest rows (world-asset-install.py conventions: row shape :136-147,
    upsert-by-id + serialization :676-701; version/_doc never touched).
    Two-phase: every destination is jail-checked and every source
    re-hashed BEFORE anything is copied — a violation copies nothing."""
    if not manifest_path.is_file():
        raise IntakeError(f"manifest not found: {manifest_path} — promote "
                          "appends rows to the TRACKED manifest and "
                          "refuses to invent one")
    try:
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise IntakeError(f"manifest {manifest_path} is not valid JSON: "
                          f"{e}") from None
    assets = m.get("assets")
    if not isinstance(assets, list):
        raise IntakeError("manifest.assets must be a list "
                          "(world-asset-gate.py contract)")

    plan: list[tuple[str, str, Path, bytes, dict]] = []
    for rec in sorted(accepted, key=lambda r: r["id"]):
        entry_id = rec["id"]
        obj = by_id[entry_id].get("object")
        safe_obj = sanitize_id(str(obj or ""))
        if not safe_obj:
            raise IntakeError(f"{entry_id}: worklist object {obj!r} "
                              "sanitizes to empty — cannot place the "
                              "sprite; nothing copied")
        rel = f"originals/{safe_obj}/{entry_id}.png"
        dest = assets_root / rel
        if not contained(assets_root, dest):
            raise IntakeError(f"REFUSED: {entry_id} promote path escapes "
                              f"the asset root ({dest}) — realpath "
                              "containment; nothing copied")
        data = (delivery / rec["file"]).read_bytes()
        if sha256_of(data) != rec["sha256"]:
            raise IntakeError(f"{entry_id}: file changed between "
                              "validation and promote (sha256 mismatch) — "
                              "re-run intake; nothing copied")
        row = {  # world-asset-install.py:136-147 row shape
            "id": rel[: -len(".png")],
            "path": rel,
            "w": rec["actual"]["w"], "h": rec["actual"]["h"], "grid": GRID,
            "sha256": rec["sha256"],
            "pack": ("org-commissioned original — artist delivery, "
                     f"batch {batch_tag}"),
            "license": LICENSE,
        }
        plan.append((entry_id, rel, dest, data, row))

    by_row_id = {a.get("id"): a for a in assets if isinstance(a, dict)}
    promoted: list[str] = []
    replaced: list[str] = []
    for _entry_id, rel, dest, data, row in plan:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)          # delivered bytes verbatim
        if row["id"] in by_row_id:      # install:681-683 upsert semantics
            by_row_id[row["id"]].update(row)
            replaced.append(row["id"])
        else:
            assets.append(row)
            by_row_id[row["id"]] = row
        promoted.append(rel)
    # install:698-699 exact serialization; version/_doc left untouched
    manifest_path.write_text(
        json.dumps(m, indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return {"promoted": promoted, "replaced": replaced}


# ---------------------------------------------------------------- report
def report_markdown(rep: dict) -> str:
    """Human mirror of report.json — artist-readable, no timestamps."""
    c = rep["counts"]
    lines = [f"# World-asset intake — batch `{rep['batch']}`", ""]
    lines.append(f"- files: {c['files']} — **accepted: {c['accepted']}**, "
                 f"**fix_needed: {c['fix_needed']}**")
    wl = rep["worklist"]
    lines.append(f"- worklist: `{wl['path']}` "
                 f"(sha256 `{wl['sha256'][:12]}…`)")
    pal = rep["palette"]
    if pal:
        lines.append(f"- palette: `{pal['path']}` — {pal['n_colors']} "
                     f"colors (sha256 `{pal['sha256'][:12]}…`)")
    else:
        lines.append("- palette: _none — exact-membership check skipped_")
    lines.append("")

    fix = [f for f in rep["files"] if f["status"] != "accepted"]
    if fix:
        lines.append(f"## Fix needed ({len(fix)})")
        lines.append("")
        for f in fix:
            lines.append(f"### `{f['file']}`")
            for r in f["reasons"]:
                lines.append(f"- {r}")
            for n in f["notes"]:
                lines.append(f"- note: {n}")
            lines.append("")

    acc = [f for f in rep["files"] if f["status"] == "accepted"]
    if acc:
        lines.append(f"## Accepted ({len(acc)})")
        lines.append("")
        for f in acc:
            exp = f["expected"] or {}
            size = f"{exp.get('w')}x{exp.get('h')}"
            if exp.get("frames"):
                size += f" ({exp['frames']} frames)"
            extra = ("" if not f["notes"]
                     else " — " + "; ".join(f["notes"]))
            lines.append(f"- `{f['id']}` — {size}{extra}")
        lines.append("")

    lines.append("## Conformance scene")
    lines.append("")
    scene = rep["scene"]
    if scene:
        lines.append(f"- `{scene['path']}` {scene['w']}x{scene['h']} "
                     f"(sha256 `{scene['sha256'][:12]}…`)")
    else:
        lines.append("- _not composed — no accepted sprites_")
    ag = rep["aesthetic_gate"]
    if ag:
        if ag.get("exit") is None:
            lines.append(f"- aesthetic gate: {ag['note']}")
        elif ag.get("parse_error"):
            lines.append(f"- aesthetic gate: exit {ag['exit']}, output "
                         f"unparseable — tail: `{ag['output_tail']}`")
        else:
            lines.append(f"- aesthetic gate: exit {ag['exit']}, "
                         f"ok={ag.get('ok')}, counts={ag.get('counts')} "
                         f"— {ag['note']}")
    lines.append("")

    lines.append("## Promotion")
    lines.append("")
    pr = rep["promote"]
    if pr["mode"] == "report-only":
        lines.append("- report-only: nothing copied; re-run with "
                     "`--promote` to install accepted sprites")
    elif pr["mode"] == "refused":
        lines.append(f"- REFUSED: {pr['reason']}")
    else:
        lines.append(f"- mode: {pr['mode']} — {len(pr['promoted'])} "
                     f"sprite(s) into `originals/` "
                     f"({len(pr['replaced'])} manifest row(s) replaced)")
        for rel in pr["promoted"]:
            lines.append(f"  - `{rel}`")
        if pr["skipped"]:
            lines.append(f"- skipped (fix_needed): "
                         + ", ".join(f"`{s}`" for s in pr["skipped"]))
        lines.append("- follow-up: `python3.12 "
                     "cabinet/scripts/world-asset-gate.py`")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- run
def run(args: argparse.Namespace) -> int:
    delivery = Path(args.delivery_dir)
    if not delivery.is_dir():
        raise IntakeError(f"delivery dir not found: {delivery}")
    if args.halo_max < 0 or args.palette_max < 0:
        raise IntakeError("--halo-max/--palette-max must be >= 0")
    if args.promote_accepted_only:
        args.promote = True          # accepted-only IS a promote mode

    report_dir = (Path(args.report_dir) if args.report_dir
                  else delivery / "_intake")
    scene_out = (Path(args.scene_out) if args.scene_out
                 else report_dir / "test-scene.png")
    assets_root = (Path(args.assets_root) if args.assets_root
                   else DEFAULT_ASSETS_ROOT)
    manifest_path = (Path(args.manifest) if args.manifest
                     else assets_root / "manifest.json")
    batch = args.batch_tag or delivery.resolve().name

    by_id, wl_raw = load_worklist(Path(args.worklist))

    palette_colors = None
    palette_info = None
    if args.palette:
        p = Path(args.palette)
        if not p.is_file():
            raise IntakeError(f"--palette {p} not found")
        pdata = p.read_bytes()
        if pdata[:8] != PNG_MAGIC:
            raise IntakeError(f"--palette {p} is not a PNG")
        with Image.open(io.BytesIO(pdata)) as im:
            palette_colors = load_palette_colors(im)
        palette_info = {"path": str(p), "sha256": sha256_of(pdata),
                        "n_colors": len(palette_colors)}

    report_dir_r = Path(os.path.realpath(report_dir))
    scene_out_r = Path(os.path.realpath(scene_out))
    candidates: list[Path] = []
    for pth in sorted(delivery.iterdir(), key=lambda q: q.name):
        if pth.name.startswith("."):
            continue                     # dotfiles (.DS_Store etc.)
        if pth.is_dir():
            continue                     # nested dirs ignored (_intake/ etc.)
        rp = Path(os.path.realpath(pth))
        if rp == scene_out_r or report_dir_r in rp.parents:
            continue                     # never validate our own outputs
        candidates.append(pth)
    if not candidates:
        raise IntakeError(f"no deliveries found in {delivery} — expected "
                          "top-level <worklist-entry-id>.png files")

    records = [validate_file(p, by_id, palette_colors,
                             args.halo_max, args.palette_max)
               for p in candidates]
    accepted = [r for r in records if r["status"] == "accepted"]
    fix = [r for r in records if r["status"] != "accepted"]

    scene_info = None
    gate_info = None
    if accepted:
        scene = compose_scene(accepted, delivery)
        sdata = png_bytes_of(scene)
        if args.scene_out:
            scene_out.parent.mkdir(parents=True, exist_ok=True)
            scene_out.write_bytes(sdata)   # explicit path = caller authority
        else:
            _write_jailed(report_dir, scene_out, sdata)
        try:
            scene_path_str = str(scene_out_r.relative_to(report_dir_r))
        except ValueError:
            scene_path_str = str(scene_out)
        scene_info = {"path": scene_path_str, "sha256": sha256_of(sdata),
                      "w": scene.width, "h": scene.height}
        if args.gate:
            code, out = run_aesthetic_gate(scene_out)
            gate_info = fold_gate(code, out)
    elif args.gate:
        gate_info = {"exit": None,
                     "note": "gate skipped — no accepted sprites, "
                             "no scene composed"}

    promote_info: dict = {"mode": "report-only", "promoted": [],
                          "replaced": [], "skipped": []}
    refused = None
    if args.promote:
        if fix and not args.promote_accepted_only:
            refused = (f"{len(fix)} file(s) fix_needed — nothing copied; "
                       "fix and re-deliver, or pass "
                       "--promote-accepted-only to install only the "
                       "accepted subset")
            promote_info = {"mode": "refused", "reason": refused,
                            "promoted": [], "replaced": [],
                            "skipped": sorted(r["file"] for r in fix)}
        else:
            got = promote(accepted, by_id, delivery, assets_root,
                          manifest_path, batch)
            promote_info = {
                "mode": ("promote-accepted-only"
                         if args.promote_accepted_only else "promote"),
                "promoted": got["promoted"],
                "replaced": got["replaced"],
                "skipped": sorted(r["file"] for r in fix),
            }

    report = {
        "schema": REPORT_SCHEMA,
        "batch": batch,
        "worklist": {"path": str(args.worklist),
                     "sha256": sha256_of(wl_raw)},
        "palette": palette_info,
        "counts": {"files": len(records), "accepted": len(accepted),
                   "fix_needed": len(fix)},
        "files": records,
        "scene": scene_info,
        "aesthetic_gate": gate_info,
        "promote": promote_info,
    }
    jtext = json.dumps(report, indent=2, sort_keys=True,
                       ensure_ascii=False) + "\n"
    _write_jailed(report_dir, report_dir / "report.json",
                  jtext.encode("utf-8"))
    _write_jailed(report_dir, report_dir / "report.md",
                  report_markdown(report).encode("utf-8"))

    print(f"intake: {len(accepted)} accepted, {len(fix)} fix_needed of "
          f"{len(records)} file(s) — report: {report_dir / 'report.md'}")
    if promote_info["mode"].startswith("promote"):
        print(f"promoted {len(promote_info['promoted'])} sprite(s) into "
              f"{assets_root / 'originals'} "
              f"({len(promote_info['replaced'])} manifest row(s) replaced)")
        print(f"follow-up conformance gate: python3.12 "
              f"cabinet/scripts/world-asset-gate.py {manifest_path}")
    if refused:
        print(f"PROMOTE REFUSED: {refused}", file=sys.stderr)
        return EXIT_USAGE
    return EXIT_FIX_NEEDED if fix else EXIT_OK


# ---------------------------------------------------------------- CLI
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="world-asset-intake.py",
        description="Artist-delivery intake for Cabinet World sprites: "
                    "validate a batch of <worklist-id>.png files, write "
                    "machine+human reports with exact actionable reasons, "
                    "compose a deterministic conformance scene, and "
                    "(--promote only) install accepted sprites into "
                    "originals/ with content-addressed manifest rows.",
        epilog="Default is REPORT-ONLY: nothing outside --report-dir is "
               "written. Exit codes: 0 all accepted, 1 any fix_needed "
               "(reports still written), 2 usage/promote refusal. "
               f"License stamped on promoted rows: '{LICENSE}'.")
    p.add_argument("delivery_dir",
                   help="folder of delivered <worklist-entry-id>.png files "
                        "(top level only; dirs and dotfiles ignored)")
    p.add_argument("--worklist", default=str(DEFAULT_WORKLIST),
                   help="asset worklist JSON from world-asset-spec.py "
                        f"(default {DEFAULT_WORKLIST})")
    p.add_argument("--palette",
                   help="master palette strip PNG — exact-RGB membership "
                        "audit over every alpha>0 pixel")
    p.add_argument("--palette-max", type=int, default=DEFAULT_PALETTE_MAX,
                   help="tolerated off-palette pixels per file "
                        f"(default {DEFAULT_PALETTE_MAX})")
    p.add_argument("--halo-max", type=int, default=DEFAULT_HALO_MAX,
                   help="tolerated semi-transparent fringe pixels per "
                        f"file (default {DEFAULT_HALO_MAX})")
    p.add_argument("--gate", action="store_true",
                   help="also run world-aesthetic-gate.py --mechanical "
                        "over the conformance scene (verdict folded into "
                        "the report as INFORMATIONAL — see runbook §8)")
    p.add_argument("--report-dir",
                   help="report output dir (default DELIVERY_DIR/_intake)")
    p.add_argument("--scene-out",
                   help="conformance scene PNG path "
                        "(default REPORT_DIR/test-scene.png)")
    p.add_argument("--promote", action="store_true",
                   help="install accepted sprites into originals/ + "
                        "manifest rows; REFUSES if any file failed unless "
                        "--promote-accepted-only")
    p.add_argument("--promote-accepted-only", action="store_true",
                   help="promote the accepted subset even when other "
                        "files failed (implies --promote)")
    p.add_argument("--assets-root",
                   help="world-assets root "
                        f"(default {DEFAULT_ASSETS_ROOT})")
    p.add_argument("--manifest",
                   help="manifest JSON (default ASSETS_ROOT/manifest.json)")
    p.add_argument("--batch-tag",
                   help="batch label stamped into promoted rows' pack "
                        "field (default: delivery dir basename)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except IntakeError as e:
        print(f"world-asset-intake: {e}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
