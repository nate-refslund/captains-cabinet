#!/usr/bin/env python3.12
"""world-compose-portraits.py — deterministic officer portraits + interim
UI frames (Cabinet World T3, spec §9.1 / Captain addendum 3 2026-07-09).

PORTRAITS. Composes one portrait per officer slug from the LimeZu Portrait
Generator raw piece PNGs (ON-DISK per addendum 3 — the Linux app itself is
never executed; the pieces compose directly with PIL, same pattern as the
character sprites). Composition is seeded by the SAME 32-bit FNV-1a the
renderer uses (dashboard lib/world/hash.ts): fnv1a("<slug>:<channel>")
selects skin / eyes / hairstyle / accessory — same officer, same face,
forever (determinism law). Rendered ONCE here at build time and manifest'd
as derived assets with full provenance (chosen piece filenames + seed).

Outputs (into cabinet/dashboard/public/world-assets/, gitignored except the
manifest — LimeZu-derived pixels are commercial-licensed, never committed):
  portraits/portrait_<slug>.png        64x64 still (talk frame 0)
  portraits/portrait_<slug>_sheet.png  640x64 talk row (10 frames — the rail
                                       animates it ONLY while the officer's
                                       verb is <5 min fresh)

PACK FRAMES (--frames, requires the T4-installed Modern UI pack sheets in
world-assets): cuts the three canonical 9-slice dialog frames from the
32x32-family Style sheets (addendum 3(c): 32x32 is canonical for in-world
dialogs), ×2 integer-NN upscaled so every export sits on the 16px art grid
(the ui-pack track's flagged 9-slice/16-grid seam, resolved by pre-scaling
instead of a gate amendment):
  ui/frame_parchment  Style_1 rounded wood/orange  (Harvestholm surfaces)
  ui/frame_slate      Style_2 blue-grey square     (Lantern Quay surfaces)
  ui/frame_heavy      Style_2 dark navy plaque     (killswitch confirm ONLY)
Rows carry `slice` (border-image-slice px, 1:1 with rendered border width)
consumed by components/world/pixel-frame.tsx.

INTERIM FRAMES (also --frames, own pixels — placeholder doctrine): three
hand-authored 48x48 16-grid 9-slice dialog frames
  ui/frame_interim_parchment | ui/frame_interim_slate | ui/frame_interim_heavy
kept as the documented fallback chain (pack row → interim row → loud DOM
fallback). Fully deterministic (fixed palettes, zero randomness) and NOT
LimeZu-derived, but they live in the same gitignored asset dir for one
loading path.

Manifest rows are UPSERTED by id (content-addressed: sha256/w/h/grid) and
must pass cabinet/scripts/world-asset-gate.py afterwards (run it — this
script does not bypass the gate).

Usage:
  python3.12 cabinet/scripts/world-compose-portraits.py [slugs...] [--frames]
  python3.12 cabinet/scripts/world-compose-portraits.py --check   # re-derive,
      compare sha256 against the manifest (drift = exit 1)

Pieces root: ~/Downloads/Portrait Generator 1.5.0 Linux Build/Portrait Pieces
(override: CABINET_PORTRAIT_PIECES). Scale: the 32x32 family (64px portrait
cells) — canonical for dialogs per addendum 3(c).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    print("FAIL: Pillow (PIL) required — python3.12 -m pip install pillow")
    sys.exit(1)

REPO_ROOT = Path(os.environ.get("CABINET_ROOT")
                 or Path(__file__).resolve().parents[2])
ASSET_ROOT = REPO_ROOT / "cabinet" / "dashboard" / "public" / "world-assets"
MANIFEST = ASSET_ROOT / "manifest.json"
PIECES_ROOT = Path(os.environ.get(
    "CABINET_PORTRAIT_PIECES",
    str(Path.home() / "Downloads" / "Portrait Generator 1.5.0 Linux Build"
        / "Portrait Pieces"))) / "Portrait_Generator - 32x32"

DEFAULT_ROSTER = ["cos", "polads-ceo", "stephie-ceo", "comms-officer"]
CELL = 64                      # portrait cell in the 32x32-family sheets
SHEET_W, SHEET_H = 640, 192    # 10 frames x 3 rows (talk / nod / shake)
PROVENANCE_PACK = ("derived: LimeZu Portrait Generator pieces "
                   "(fnv1a(slug:channel) composition, "
                   "world-compose-portraits.py)")
LICENSE = "LimeZu commercial — derived pixels, do not redistribute"


def fnv1a(s: str) -> int:
    """32-bit FNV-1a — byte-for-byte the dashboard's lib/world/hash.ts."""
    h = 0x811C9DC5
    for ch in s:
        h ^= ord(ch)
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def _contained(p: Path, root: Path) -> Path:
    real = p.resolve()
    real.relative_to(root.resolve())  # raises ValueError on escape
    return real


def _pieces(subdir: str) -> list[Path]:
    d = _contained(PIECES_ROOT / subdir, PIECES_ROOT)
    return sorted(f for f in d.iterdir() if f.suffix.lower() == ".png")


def pick(slug: str, channel: str, pool: list):
    return pool[fnv1a(f"{slug}:{channel}") % len(pool)]


def compose_portrait(slug: str) -> tuple[Image.Image, dict]:
    """Skin → eyes → hairstyle → (curated) accessory, full-sheet composite."""
    skins = _pieces("Skins")
    eyes = _pieces("Eyes")
    hair = _pieces("Hairstyles")
    # Curated accessory pool (professional subset — a seeded pick is FOREVER,
    # so novelty pieces like party cones / zombie brains are excluded).
    acc_all = _pieces("Accessories")
    allowed = ("Glasses", "Monocle", "Beard")
    acc_pool: list[Path | None] = [None, None, None]  # none is likeliest
    acc_pool += [p for p in acc_all
                 if any(a in p.name for a in allowed) and "Small" not in p.name]

    chosen = {
        "skin": pick(slug, "skin", skins),
        "eyes": pick(slug, "eyes", eyes),
        "hair": pick(slug, "hair", hair),
        "accessory": pick(slug, "accessory", acc_pool),
    }
    out = Image.new("RGBA", (SHEET_W, SHEET_H), (0, 0, 0, 0))
    for layer in ("skin", "eyes", "hair", "accessory"):
        piece = chosen[layer]
        if piece is None:
            continue
        img = Image.open(piece).convert("RGBA")
        if img.size != (SHEET_W, SHEET_H):
            raise SystemExit(f"FAIL: {piece} is {img.size}, expected "
                             f"{(SHEET_W, SHEET_H)} — wrong pieces scale?")
        out = Image.alpha_composite(out, img)
    prov = {k: (v.name if v is not None else "none") for k, v in chosen.items()}
    prov["seed"] = f"fnv1a({slug}:<channel>)"
    return out, prov


# ── interim 9-slice frames (own pixels; 48x48, 16px cells) ─────────────────

FRAME_PALETTES = {
    # (outline, edge-light, edge-dark, fill)
    "parchment": ((58, 41, 24), (196, 164, 108), (122, 92, 54), (46, 36, 24)),
    "slate": ((16, 22, 30), (118, 142, 168), (56, 72, 92), (24, 30, 38)),
    "heavy": ((8, 6, 6), (110, 104, 100), (48, 42, 40), (20, 16, 16)),
}


def draw_interim_frame(theme: str) -> Image.Image:
    outline, light, dark, fill = FRAME_PALETTES[theme]
    im = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # center cell = card fill (border-image-slice: 16 fill)
    d.rectangle([16, 16, 31, 31], fill=(*fill, 244))
    # frame band: 2px outline, bevel light top/left, dark bottom/right
    d.rectangle([0, 0, 47, 47], outline=(*outline, 255), width=2)
    d.rectangle([2, 2, 45, 45], outline=(*light, 255), width=2)
    d.rectangle([4, 4, 43, 43], outline=(*dark, 255), width=2)
    d.rectangle([6, 6, 41, 41], fill=(*fill, 244))
    # corner rivets (heavy gets doubled rivets — the unadorned weight cue)
    for cx, cy in [(3, 3), (44, 3), (3, 44), (44, 44)]:
        d.rectangle([cx - 1, cy - 1, cx + 1, cy + 1], fill=(*light, 255))
        if theme == "heavy":
            d.rectangle([cx, cy, cx, cy], fill=(*outline, 255))
    return im


# ── pack frames (cut from the T4-installed Modern UI Style sheets) ─────────
#
# Crop boxes were located + visually verified 2026-07-09 (alpha-bbox scan of
# the sheets at 4x). Shadow rows below the parchment/heavy frames are
# deliberately excluded (a drop shadow breaks 9-slice edge symmetry).
# (sheet_id, crop_box(l,t,r,b), slice_native_px)
PACK_FRAMES = {
    "parchment": ("ui/32x32/Modern_UI_Style_1_32x32", (116, 338, 172, 394), 12),
    "slate": ("ui/32x32/Modern_UI_Style_2_32x32", (16, 0, 80, 64), 14),
    "heavy": ("ui/32x32/Modern_UI_Style_2_32x32", (24, 470, 72, 518), 10),
}
PACK_SCALE = 2  # integer NN — puts 56px crops on the 16 grid (112) and
                # makes slice px == rendered border px at dashboard zoom


def cut_pack_frame(theme: str) -> tuple[Image.Image, dict, int]:
    sheet_id, box, slice_px = PACK_FRAMES[theme]
    manifest = json.loads(MANIFEST.read_text())
    row = next((r for r in manifest["assets"] if r["id"] == sheet_id), None)
    if row is None:
        raise FileNotFoundError(f"pack sheet {sheet_id} not in manifest "
                                f"(T4 install pending?)")
    src = _contained(ASSET_ROOT / row["path"], ASSET_ROOT)
    im = Image.open(src).convert("RGBA").crop(box)
    im = im.resize((im.width * PACK_SCALE, im.height * PACK_SCALE),
                   Image.NEAREST)
    prov = {"source": sheet_id, "crop": list(box), "scale": PACK_SCALE}
    return im, prov, slice_px * PACK_SCALE


# ── manifest upsert ─────────────────────────────────────────────────────────

def upsert_rows(rows: list[dict]) -> None:
    manifest = json.loads(MANIFEST.read_text())
    assets = manifest["assets"]
    by_id = {r["id"]: i for i, r in enumerate(assets)}
    for row in rows:
        if row["id"] in by_id:
            assets[by_id[row["id"]]] = row
        else:
            assets.append(row)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")


def row_for(rel: str, aid: str, img_path: Path, pack: str, license_: str,
            derived: dict | None = None, slice_px: int | None = None) -> dict:
    data = img_path.read_bytes()
    import struct
    w, h = struct.unpack(">II", data[16:24])
    row = {
        "id": aid,
        "path": rel,
        "w": int(w),
        "h": int(h),
        "grid": 16,
        "sha256": hashlib.sha256(data).hexdigest(),
        "pack": pack,
        "license": license_,
    }
    if derived:
        row["derived"] = derived
    if slice_px is not None:
        row["slice"] = slice_px  # border-image-slice px (pixel-frame.tsx)
    return row


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    roster = args or DEFAULT_ROSTER
    check = "--check" in flags
    do_frames = "--frames" in flags or check or not args

    if not PIECES_ROOT.is_dir():
        print(f"FAIL: pieces root missing: {PIECES_ROOT} "
              f"(set CABINET_PORTRAIT_PIECES)")
        return 1

    out_dir = ASSET_ROOT / "portraits"
    ui_dir = ASSET_ROOT / "ui"
    rows: list[dict] = []
    drift: list[str] = []

    manifest_ids = {}
    if check and MANIFEST.exists():
        manifest_ids = {r["id"]: r for r in
                        json.loads(MANIFEST.read_text())["assets"]}

    for slug in roster:
        sheet, prov = compose_portrait(slug)
        talk_row = sheet.crop((0, 0, SHEET_W, CELL))       # 640x64, 10 frames
        still = sheet.crop((0, 0, CELL, CELL))             # frame 0
        for suffix, img in (("", still), ("_sheet", talk_row)):
            aid = f"portraits/portrait_{slug}{suffix}"
            rel = f"portraits/portrait_{slug}{suffix}.png"
            target = ASSET_ROOT / rel
            if check:
                import io
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                sha = hashlib.sha256(buf.getvalue()).hexdigest()
                have = manifest_ids.get(aid, {}).get("sha256")
                if have != sha:
                    drift.append(f"{aid}: manifest {str(have)[:12]} != "
                                 f"recomposed {sha[:12]}")
                continue
            out_dir.mkdir(parents=True, exist_ok=True)
            img.save(target, format="PNG")
            rows.append(row_for(rel, aid, target, PROVENANCE_PACK, LICENSE,
                                derived=prov))
        print(f"{'checked' if check else 'composed'} {slug}: "
              + ", ".join(f"{k}={v}" for k, v in prov.items()
                          if k != "seed"))

    if do_frames:
        frame_jobs: list[tuple[str, Image.Image, str, str, dict | None, int]] = []
        for theme in FRAME_PALETTES:
            frame_jobs.append((
                f"ui/frame_interim_{theme}", draw_interim_frame(theme),
                "own pixels — interim 9-slice dialog frame (T3 §9.2 "
                "fallback behind ui/frame_<theme>)",
                "CC0 (authored in-repo)", None, 16))
            try:
                img, prov, slice_px = cut_pack_frame(theme)
                frame_jobs.append((
                    f"ui/frame_{theme}", img,
                    "derived: LimeZu Modern UI 32x32 Style sheet frame cut "
                    "(world-compose-portraits.py, x2 NN)", LICENSE,
                    prov, slice_px))
            except FileNotFoundError as e:
                print(f"skip ui/frame_{theme}: {e} — interim frame carries")
        for aid, img, pack, license_, prov, slice_px in frame_jobs:
            rel = f"{aid}.png"
            if check:
                import io
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                sha = hashlib.sha256(buf.getvalue()).hexdigest()
                have = manifest_ids.get(aid, {}).get("sha256")
                if have != sha:
                    drift.append(f"{aid}: manifest {str(have)[:12]} != "
                                 f"redrawn {sha[:12]}")
                continue
            ui_dir.mkdir(parents=True, exist_ok=True)
            img.save(ASSET_ROOT / rel, format="PNG")
            rows.append(row_for(rel, aid, ASSET_ROOT / rel, pack, license_,
                                derived=prov, slice_px=slice_px))

    if check:
        if drift:
            print("DRIFT:")
            for d in drift:
                print(f"  {d}")
            return 1
        print("OK: all derived assets recompose byte-identically")
        return 0

    upsert_rows(rows)
    print(f"upserted {len(rows)} manifest rows → run "
          f"python3.12 cabinet/scripts/world-asset-gate.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
