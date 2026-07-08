#!/usr/bin/env python3.12
"""Golden-frame regression + Captain taste accumulation (stdlib-only).

Approved frames are pinned under ../goldens/ — gitignored except
goldens/manifest.json (approved renders are LimeZu-derived, licensed pixels
never enter git; the tracked manifest carries sha256 + per-region thresholds
so any checkout can verify the golden it is diffing against).

Subcommands:
    pin      --image F --id ID [--note N] [--source S] [--force]
             [--region name:x,y,w,h[:min_ssim[:max_pixel_frac]]]...
             [--min-ssim F] [--max-pixel-frac F]
             -> copy frame into goldens/, record sha256 + regions in manifest
    compare  --image F --golden ID [--out FILE]
             -> grayscale windowed SSIM + exact pixel-diff fraction per
                manifest region; golden-diff JSON to stdout (+ --out);
                exit 0 all regions pass, 1 regression, 2 unusable
    record   --image F --verdict approve|reject --note N [--id ID]
             [--source S] [--pin]
             -> Captain verdict appends the frame to the calibration corpus
                (approve -> corpus/positive/, reject -> corpus/negative/) so
                every ruling permanently sharpens the judge (taste
                accumulation); --pin additionally pins an approved frame as
                a golden under the same id
    verify   -> check every pinned golden against the manifest sha256s

Comparison math is pure python over the bounded stdlib PNG decoder
(gates/_png — decompression-bomb capped): fine for pixel-art frames, a few
seconds at 1080p. SSIM uses 8x8 non-overlapping windows on ITU-R 601 luma
with the standard C1/C2 stabilizers; pixel-diff counts pixels where any RGBA
channel differs by more than --channel-tol (default 0 — pixel-art renders
are expected byte-stable).
"""

from __future__ import annotations

import argparse
import shutil
import sys
import re
from pathlib import Path

if __package__ in (None, ""):  # direct script execution (PEP 366 re-anchor)
    import importlib.util

    _pkg_dir = Path(__file__).resolve().parent
    if "world_aesthetic_judge" not in sys.modules:
        _spec = importlib.util.spec_from_file_location(
            "world_aesthetic_judge", _pkg_dir / "__init__.py",
            submodule_search_locations=[str(_pkg_dir)])
        _mod = importlib.util.module_from_spec(_spec)
        sys.modules["world_aesthetic_judge"] = _mod
        try:
            _spec.loader.exec_module(_mod)
        except BaseException:
            sys.modules.pop("world_aesthetic_judge", None)
            raise
    __package__ = "world_aesthetic_judge"

from . import _corpus  # noqa: E402

GOLDENS_SCHEMA = "cabinet.world.goldens/v1"
GOLDEN_DIFF_SCHEMA = "cabinet.world.golden-diff/v1"
DEFAULT_MIN_SSIM = 0.97
DEFAULT_MAX_PIXEL_FRAC = 0.02
SSIM_WINDOW = 8
_C1 = (0.01 * 255.0) ** 2
_C2 = (0.03 * 255.0) ** 2
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class GoldenError(ValueError):
    pass


# ---------------------------------------------------------------- image math

def luma(rgba: bytes, width: int, height: int) -> list[int]:
    """ITU-R 601 luma per pixel (0..255 ints)."""
    out = [0] * (width * height)
    o = 0
    for i in range(0, len(rgba), 4):
        out[o] = (299 * rgba[i] + 587 * rgba[i + 1]
                  + 114 * rgba[i + 2]) // 1000
        o += 1
    return out


def ssim_region(la: list[int], lb: list[int], width: int,
                rect: tuple[int, int, int, int],
                window: int = SSIM_WINDOW) -> float:
    """Mean SSIM over non-overlapping window x window tiles of the region."""
    x0, y0, w, h = rect
    vals: list[float] = []
    for wy in range(y0, y0 + h, window):
        bh = min(window, y0 + h - wy)
        for wx in range(x0, x0 + w, window):
            bw = min(window, x0 + w - wx)
            n = bw * bh
            sa = sb = saa = sbb = sab = 0
            for yy in range(wy, wy + bh):
                base = yy * width
                for xx in range(wx, wx + bw):
                    a = la[base + xx]
                    b = lb[base + xx]
                    sa += a
                    sb += b
                    saa += a * a
                    sbb += b * b
                    sab += a * b
            ma = sa / n
            mb = sb / n
            va = saa / n - ma * ma
            vb = sbb / n - mb * mb
            cov = sab / n - ma * mb
            vals.append(((2 * ma * mb + _C1) * (2 * cov + _C2))
                        / ((ma * ma + mb * mb + _C1) * (va + vb + _C2)))
    if not vals:
        raise GoldenError(f"empty region rect: {list(rect)}")
    return sum(vals) / len(vals)


def pixel_diff_frac(a: bytes, b: bytes, width: int,
                    rect: tuple[int, int, int, int], tol: int = 0) -> float:
    """Fraction of region pixels where any RGBA channel differs > tol."""
    x0, y0, w, h = rect
    if w <= 0 or h <= 0:
        raise GoldenError(f"empty region rect: {list(rect)}")
    diff = 0
    for yy in range(y0, y0 + h):
        base = yy * width * 4
        for xx in range(x0, x0 + w):
            i = base + xx * 4
            if (abs(a[i] - b[i]) > tol or abs(a[i + 1] - b[i + 1]) > tol
                    or abs(a[i + 2] - b[i + 2]) > tol
                    or abs(a[i + 3] - b[i + 3]) > tol):
                diff += 1
    return diff / (w * h)


# ------------------------------------------------------------- manifest I/O

def _empty_manifest() -> dict:
    return {
        "schema": GOLDENS_SCHEMA,
        "purpose": "Golden-frame regression pins for Cabinet World renders "
                   "(Captain-approved frames; SSIM + pixel-diff per region).",
        "note": "Golden PNGs are gitignored (LimeZu-derived, licensed); this "
                "manifest is the tracked record. Verify with "
                "`goldens.py verify`.",
        "goldens": [],
    }


def load_goldens_manifest(goldens_dir: Path = _corpus.GOLDENS_DIR) -> dict:
    mp = Path(goldens_dir) / "manifest.json"
    if not mp.exists():
        return _empty_manifest()
    import json
    data = json.loads(mp.read_text())
    if data.get("schema") != GOLDENS_SCHEMA or \
            not isinstance(data.get("goldens"), list):
        raise GoldenError(f"bad goldens manifest: {mp}")
    return data


def _find(data: dict, golden_id: str) -> dict | None:
    for g in data["goldens"]:
        if g["id"] == golden_id:
            return g
    return None


def _decode_png(path: Path) -> tuple[int, int, bytes]:
    png = _corpus.png_codec()
    try:
        return png.decode(path)
    except Exception as e:
        raise GoldenError(f"cannot decode PNG {path}: {e}") from e


def _check_rect(rect: list[int], size: tuple[int, int], name: str) -> None:
    if (len(rect) != 4 or any(not isinstance(v, int) for v in rect)
            or rect[2] <= 0 or rect[3] <= 0 or rect[0] < 0 or rect[1] < 0
            or rect[0] + rect[2] > size[0] or rect[1] + rect[3] > size[1]):
        raise GoldenError(
            f"region '{name}' rect {rect} outside {size[0]}x{size[1]} frame")


# ------------------------------------------------------------------ actions

def pin_golden(image: Path, golden_id: str, note: str = "", source: str = "",
               regions: list[dict] | None = None,
               min_ssim: float = DEFAULT_MIN_SSIM,
               max_pixel_frac: float = DEFAULT_MAX_PIXEL_FRAC,
               force: bool = False,
               goldens_dir: Path = _corpus.GOLDENS_DIR) -> dict:
    if not _ID_RE.match(golden_id):
        raise GoldenError(f"bad golden id (want [a-z0-9][a-z0-9_-]*): "
                          f"{golden_id!r}")
    image = Path(image)
    if not image.exists():
        raise GoldenError(f"image not found: {image}")
    w, h, _ = _decode_png(image)

    goldens_dir = Path(goldens_dir)
    goldens_dir.mkdir(parents=True, exist_ok=True)
    dest = _corpus.contained(goldens_dir / f"{golden_id}.png", goldens_dir)

    data = load_goldens_manifest(goldens_dir)
    if _find(data, golden_id) is not None and not force:
        raise GoldenError(f"golden id already pinned: {golden_id} "
                          f"(re-pinning an approved look needs --force)")

    regions = regions or [{"name": "full", "rect": [0, 0, w, h]}]
    for r in regions:
        _check_rect(r["rect"], (w, h), r["name"])

    shutil.copyfile(image, dest)
    entry = {
        "id": golden_id,
        "file": f"goldens/{golden_id}.png",
        "sha256": _corpus.sha256_of(dest),
        "size": [w, h],
        "approved_at": _corpus.utcnow_iso(),
        "source": source or str(image),
        "note": note,
        "thresholds": {"min_ssim": min_ssim,
                       "max_pixel_frac": max_pixel_frac},
        "regions": regions,
    }
    data["goldens"] = ([g for g in data["goldens"] if g["id"] != golden_id]
                       + [entry])
    data["goldens"].sort(key=lambda g: g["id"])
    _corpus.atomic_write_json(goldens_dir / "manifest.json", data)
    return entry


def compare_to_golden(image: Path, golden_id: str, channel_tol: int = 0,
                      goldens_dir: Path = _corpus.GOLDENS_DIR) -> dict:
    """Per-region SSIM + pixel-diff of `image` against a pinned golden."""
    goldens_dir = Path(goldens_dir)
    data = load_goldens_manifest(goldens_dir)
    entry = _find(data, golden_id)
    if entry is None:
        raise GoldenError(f"no such golden: {golden_id}")

    gpath = _corpus.contained(goldens_dir.parent / entry["file"], goldens_dir)
    if not gpath.exists():
        raise GoldenError(f"golden file missing on disk: {entry['file']} "
                          f"(gitignored — restore the approved frame)")
    if _corpus.sha256_of(gpath) != entry["sha256"]:
        raise GoldenError(f"golden bytes drifted from manifest: "
                          f"{entry['file']} (refusing a tampered golden)")

    image = Path(image)
    if not image.exists():
        raise GoldenError(f"image not found: {image}")
    gw, gh, grgba = _decode_png(gpath)
    iw, ih, irgba = _decode_png(image)

    result = {
        "schema": GOLDEN_DIFF_SCHEMA,
        "golden": golden_id,
        "golden_sha256": entry["sha256"],
        "image": str(image),
        "image_sha256": _corpus.sha256_of(image),
        "size": [gw, gh],
        "channel_tol": channel_tol,
        "regions": [],
        "pass": False,
    }
    if (iw, ih) != (gw, gh):
        result["error"] = (f"size mismatch: image {iw}x{ih} vs golden "
                           f"{gw}x{gh} — regression compare needs "
                           f"same-size frames")
        return result

    gl = luma(grgba, gw, gh)
    il = luma(irgba, iw, ih)
    defaults = entry.get("thresholds", {})
    all_pass = True
    for region in entry["regions"]:
        rect = tuple(region["rect"])
        _check_rect(list(rect), (gw, gh), region["name"])
        min_s = region.get("min_ssim",
                           defaults.get("min_ssim", DEFAULT_MIN_SSIM))
        max_f = region.get("max_pixel_frac",
                           defaults.get("max_pixel_frac",
                                        DEFAULT_MAX_PIXEL_FRAC))
        s = ssim_region(il, gl, gw, rect)
        f = pixel_diff_frac(irgba, grgba, gw, rect, tol=channel_tol)
        ok = s >= min_s and f <= max_f
        all_pass = all_pass and ok
        result["regions"].append({
            "name": region["name"], "rect": list(rect),
            "ssim": round(s, 6), "min_ssim": min_s,
            "pixel_diff_frac": round(f, 6), "max_pixel_frac": max_f,
            "pass": ok,
        })
    result["pass"] = all_pass
    return result


def record_verdict(image: Path, verdict: str, note: str,
                   entry_id: str = "", source: str = "",
                   corpus_dir: Path = _corpus.CORPUS_DIR) -> dict:
    """Append a Captain approve/reject to the calibration corpus.

    This is the taste-accumulation loop: every Captain ruling becomes a
    corpus example that future calibration sets and pairwise samples draw
    from — the judge's bar rises with every decision.
    """
    if verdict not in ("approve", "reject"):
        raise GoldenError(f"verdict must be approve|reject, got {verdict!r}")
    if not note.strip():
        raise GoldenError("a Captain verdict needs a --note (the WHY is the "
                          "taste signal)")
    image = Path(image)
    if not image.exists():
        raise GoldenError(f"image not found: {image}")
    _decode_png(image)  # corpus must stay readable by the stdlib codec

    cls = "positive" if verdict == "approve" else "negative"
    entry_id = entry_id or (
        f"cap-{verdict}-"
        f"{_corpus.utcnow_iso().replace(':', '').replace('-', '')[:15]}")
    if not _ID_RE.match(entry_id):
        raise GoldenError(f"bad entry id (want [a-z0-9][a-z0-9_-]*): "
                          f"{entry_id!r}")

    corpus_dir = Path(corpus_dir)
    dest = _corpus.contained(corpus_dir / cls / f"{entry_id}.png", corpus_dir)
    if dest.exists():
        raise GoldenError(f"corpus file already exists: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(image, dest)

    entry = {
        "id": entry_id,
        "class": cls,
        "file": f"corpus/{cls}/{entry_id}.png",
        "sha256": _corpus.sha256_of(dest),
        "provenance": source or (f"Captain {verdict} via judge/goldens.py "
                                 f"record ({_corpus.utcnow_iso()})"),
        "why": note,
        "recorded_at": _corpus.utcnow_iso(),
    }
    try:
        _corpus.append_corpus_entries([entry], corpus_dir=corpus_dir)
    except BaseException:
        dest.unlink(missing_ok=True)  # keep image + manifest atomic together
        raise
    return entry


def verify_goldens(goldens_dir: Path = _corpus.GOLDENS_DIR) -> list[str]:
    """Return problems ([] = all pinned goldens match the manifest)."""
    goldens_dir = Path(goldens_dir)
    problems = []
    for g in load_goldens_manifest(goldens_dir)["goldens"]:
        try:
            p = _corpus.contained(goldens_dir.parent / g["file"], goldens_dir)
        except _corpus.CorpusError as e:
            problems.append(str(e))
            continue
        if not p.exists():
            problems.append(f"MISSING: {g['file']}")
        elif _corpus.sha256_of(p) != g["sha256"]:
            problems.append(f"HASH MISMATCH: {g['file']}")
    return problems


# ---------------------------------------------------------------------- CLI

def _parse_region(spec: str) -> dict:
    parts = spec.split(":")
    if len(parts) < 2 or len(parts) > 4:
        raise GoldenError(f"bad --region (want name:x,y,w,h[:min_ssim"
                          f"[:max_pixel_frac]]): {spec!r}")
    name = parts[0]
    try:
        rect = [int(v) for v in parts[1].split(",")]
        region: dict = {"name": name, "rect": rect}
        if len(parts) >= 3:
            region["min_ssim"] = float(parts[2])
        if len(parts) == 4:
            region["max_pixel_frac"] = float(parts[3])
    except ValueError as e:
        raise GoldenError(f"bad --region numbers in {spec!r}: {e}") from e
    if len(rect) != 4:
        raise GoldenError(f"bad --region rect (want x,y,w,h): {spec!r}")
    return region


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="goldens.py",
        description="Golden-frame regression + Captain taste accumulation.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pin = sub.add_parser("pin", help="pin an approved frame as a golden")
    pin.add_argument("--image", required=True)
    pin.add_argument("--id", required=True, dest="golden_id")
    pin.add_argument("--note", default="")
    pin.add_argument("--source", default="")
    pin.add_argument("--region", action="append", default=[],
                     help="name:x,y,w,h[:min_ssim[:max_pixel_frac]] "
                          "(repeatable; default one full-frame region)")
    pin.add_argument("--min-ssim", type=float, default=DEFAULT_MIN_SSIM)
    pin.add_argument("--max-pixel-frac", type=float,
                     default=DEFAULT_MAX_PIXEL_FRAC)
    pin.add_argument("--force", action="store_true")
    pin.add_argument("--goldens-dir", default=str(_corpus.GOLDENS_DIR))

    cmp_ = sub.add_parser("compare", help="diff a frame against a golden")
    cmp_.add_argument("--image", required=True)
    cmp_.add_argument("--golden", required=True, dest="golden_id")
    cmp_.add_argument("--channel-tol", type=int, default=0)
    cmp_.add_argument("--out", default="")
    cmp_.add_argument("--goldens-dir", default=str(_corpus.GOLDENS_DIR))

    rec = sub.add_parser("record",
                         help="append a Captain approve/reject to the corpus")
    rec.add_argument("--image", required=True)
    rec.add_argument("--verdict", required=True,
                     choices=("approve", "reject"))
    rec.add_argument("--note", required=True)
    rec.add_argument("--id", default="", dest="entry_id")
    rec.add_argument("--source", default="")
    rec.add_argument("--pin", action="store_true",
                     help="also pin an approved frame as a golden (same id)")
    rec.add_argument("--corpus-dir", default=str(_corpus.CORPUS_DIR))
    rec.add_argument("--goldens-dir", default=str(_corpus.GOLDENS_DIR))

    ver = sub.add_parser("verify",
                         help="verify pinned goldens against the manifest")
    ver.add_argument("--goldens-dir", default=str(_corpus.GOLDENS_DIR))
    return p


def main(argv: list[str] | None = None) -> int:
    import json
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "pin":
            regions = [_parse_region(s) for s in args.region]
            entry = pin_golden(
                Path(args.image), args.golden_id, note=args.note,
                source=args.source, regions=regions or None,
                min_ssim=args.min_ssim, max_pixel_frac=args.max_pixel_frac,
                force=args.force, goldens_dir=Path(args.goldens_dir))
            print(f"pinned golden {entry['id']} "
                  f"({entry['size'][0]}x{entry['size'][1]}, "
                  f"{len(entry['regions'])} region(s))")
            return 0
        if args.cmd == "compare":
            result = compare_to_golden(
                Path(args.image), args.golden_id,
                channel_tol=args.channel_tol,
                goldens_dir=Path(args.goldens_dir))
            text = json.dumps(result, indent=2)
            print(text)
            if args.out:
                Path(args.out).write_text(text + "\n")
            return 0 if result["pass"] else 1
        if args.cmd == "record":
            entry = record_verdict(
                Path(args.image), args.verdict, args.note,
                entry_id=args.entry_id, source=args.source,
                corpus_dir=Path(args.corpus_dir))
            print(f"recorded Captain {args.verdict} as corpus "
                  f"{entry['class']}: {entry['id']}")
            if args.pin:
                if args.verdict != "approve":
                    raise GoldenError("--pin only applies to approve "
                                      "verdicts")
                pin_golden(Path(args.image), entry["id"], note=args.note,
                           source=entry["provenance"],
                           goldens_dir=Path(args.goldens_dir))
                print(f"pinned golden {entry['id']}")
            return 0
        if args.cmd == "verify":
            problems = verify_goldens(Path(args.goldens_dir))
            data = load_goldens_manifest(Path(args.goldens_dir))
            total = len(data["goldens"])
            for line in problems:
                print(line)
            print(f"{total - len(problems)}/{total} goldens verified OK")
            return 1 if problems else 0
        raise GoldenError(f"unknown command {args.cmd!r}")
    except (GoldenError, _corpus.CorpusError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
