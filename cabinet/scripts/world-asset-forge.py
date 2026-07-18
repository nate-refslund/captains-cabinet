#!/usr/bin/env python3.12
"""world-asset-forge.py — PixelLab.ai sprite-candidate forge (Cabinet World).

Generates N sprite CANDIDATES per worklist entry via the PixelLab.ai
bitforge API, with full provenance sidecars, into a gitignored review
directory. Acceptance law: the forge never ingests; human accept via the
existing world-asset-install/world-asset-gate flow; candidates die in the
out-dir unless a human promotes them.

Palette contract: this tool deliberately does NOT consume
cabinet/scripts/world-aesthetic/calibration/palette.json — that file is the
aesthetic judge's MEMBERSHIP HISTOGRAM (554 five-bit quantized bins, lossy
bin centers, fitted to the outgoing LimeZu estate), not a drawing palette.
The forge takes a palette STRIP png (--palette): it rides the API as
color_image (pilot-proven palette forcing) and is the post-quantize target.
When the artist's Phase-0 master palette lands (~Aug 18-21) that strip
becomes the standard input. With --style-dir but no --palette, a strip is
derived (top-64 most-frequent opaque colors, deterministic).

Pilot-proven API contract (2026-07 live pilot):
  POST /v1/generate-image-bitforge, Bearer auth;
  style_image MUST exactly match the output canvas size (hence the per-size
  style collage built from --style-dir, or auto-fit of --style-image);
  color_image (palette strip) forces the palette;
  view "high top-down"; no_background true;
  response {"image": {"base64": ...}}.
Field names beyond that pilot-proven set (notably /v1/rotate) are best
effort — payload builders are isolated in _build_*_payload for cheap
correction against live docs.

Secrets (BINDING): the API key is read at RUNTIME from env PIXELLAB_API_KEY,
else ~/.pixellab-api-key. Never hardcoded, never logged (error paths redact),
never written to sidecars, never committed. All HTTP goes through the
_post_json seam (stdlib urllib — `requests` is not installed for the house
python3.12); tests mock the seam: zero real API calls in CI.

Spend guard: --limit (default 10) is a HARD cap on total API calls per
invocation. A run that would exceed it is REFUSED with the exact count —
never silently truncated. One-shot quality ran ~1/3 usable in the pilot, so
default --candidates is 2 and a human picks; the forge never auto-accepts.

Usage:
  python3.12 cabinet/scripts/world-asset-forge.py \
      --worklist cabinet/world/asset-worklist.json \
      --entry 'ladder.flagpole.*' [--candidates 2] [--limit 10] \
      [--style-dir DIR | --style-image PNG] [--palette STRIP.png] \
      [--rotate] [--out DIR] [--dry-run]
  python3.12 cabinet/scripts/world-asset-forge.py \
      --describe 'weathered oak harbor barrel' --size 32x32 --id barrel

Exit codes: 0 ok; 1 candidate failures/flags (files+sidecars still written
where possible); 2 usage / plan errors / spend-guard refusal; 4 HANDBACK
(no API key available).

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
"""
from __future__ import annotations

import argparse
import base64
import binascii
import fnmatch
import hashlib
import io
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

REPO = Path(os.environ.get("CABINET_ROOT")
            or Path(__file__).resolve().parents[2])
SCRIPT_DIR = Path(__file__).resolve().parent

DEFAULT_ENDPOINT = "https://api.pixellab.ai/v1/generate-image-bitforge"
DEFAULT_ROTATE_ENDPOINT = "https://api.pixellab.ai/v1/rotate"
DEFAULT_WORKLIST = REPO / "cabinet" / "world" / "asset-worklist.json"
DEFAULT_OUT = SCRIPT_DIR / "world-asset-forge-out"
DEFAULT_CANDIDATES = 2   # pilot: ~1/3 one-shot usable — N per entry + human pick
DEFAULT_LIMIT = 10       # HARD spend cap (API calls per invocation), refuse-above

GRID = 16                                  # world-asset-gate.py:43 art grid law
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"           # world-asset-gate.py:42
KEY_ENV = "PIXELLAB_API_KEY"
KEY_FILE = "~/.pixellab-api-key"
VIEW = "high top-down"                     # pilot-proven
MAX_PALETTE_COLORS = 64
LICENSE = "owned — org-original"

_TIMEOUT_S = 180.0
_RETRIES = 2             # extra attempts on 429/5xx
_RETRY_SLEEP_S = 2.0     # fixed sleep between retries (tests zero this)

EXIT_OK = 0
EXIT_CANDIDATE_ISSUES = 1
EXIT_USAGE = 2
EXIT_HANDBACK = 4

# id charset mirrors world-asset-install.py:96/:109-115 minus "/" — a forge
# entry id is a SINGLE directory segment, never a relative path.
_SAFE_ID = re.compile(r"[^A-Za-z0-9._-]+")


class ForgeError(RuntimeError):
    """Forge-level failure with a human-actionable message."""


class SpendGuardRefusal(ForgeError):
    """Run would exceed the --limit hard cap. Nothing was generated."""


class ForgeHTTPStatusError(ForgeError):
    """Non-2xx API response; body already key-redacted at raise site."""

    def __init__(self, status: int, body: str, url: str):
        self.status = status
        self.body = body
        self.url = url
        super().__init__(f"HTTP {status} from {url}: {body}")


# ---------------------------------------------------------------- helpers
def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sanitize_id(raw: str) -> str:
    """Normalize an entry id to the manifest-safe charset (single segment).

    Mirrors world-asset-install.py sanitize() (:109-115) except '/' is NOT
    allowed (ids name one directory under the out root); leading dots are
    stripped so no id can form a dot-relative or hidden segment."""
    s = raw.replace(" - ", "-").replace(" ", "_")
    s = _SAFE_ID.sub("_", s)
    while "__" in s:
        s = s.replace("__", "_")
    s = s.rstrip("_")
    while s and s[0] in "._":   # no dot-relative / hidden / bare-sep starts
        s = s[1:]
    return s


def contained(root: Path, candidate: Path) -> bool:
    """Realpath-jail check mirroring world-asset-install.py contained()
    (:118-126) / world-asset-gate.py containment."""
    real = Path(os.path.realpath(candidate))
    root_real = Path(os.path.realpath(root))
    try:
        real.relative_to(root_real)
    except ValueError:
        return False
    return True


def _entry_dir(out_root: Path, entry_id: str) -> Path:
    safe = sanitize_id(entry_id)
    if not safe:
        raise ForgeError(f"entry id {entry_id!r} sanitizes to empty — give "
                         "the entry a usable id")
    target = out_root / safe
    if not contained(out_root, target):
        raise ForgeError(f"REFUSED: entry id {entry_id!r} escapes the out "
                         f"dir ({target}) — realpath containment")
    target.mkdir(parents=True, exist_ok=True)
    return target


def _write_jailed(out_root: Path, path: Path, data: bytes) -> None:
    if not contained(out_root, path):
        raise ForgeError(f"REFUSED: write escapes the out dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


# ---------------------------------------------------------------- secrets
def key_source() -> str:
    """Which source WOULD supply the key ('env' | 'keyfile' | 'absent').
    Never touches the value beyond presence."""
    if (os.environ.get(KEY_ENV) or "").strip():
        return "env"
    kf = Path(os.path.expanduser(KEY_FILE))
    if kf.is_file() and kf.read_text(encoding="utf-8").strip():
        return "keyfile"
    return "absent"


def load_api_key() -> str:
    """Runtime-only key: env PIXELLAB_API_KEY, else ~/.pixellab-api-key.
    Raises a named HANDBACK ForgeError when absent. The value is never
    printed, logged, or written anywhere by this tool."""
    val = (os.environ.get(KEY_ENV) or "").strip()
    if val:
        return val
    kf = Path(os.path.expanduser(KEY_FILE))
    if kf.is_file():
        val = kf.read_text(encoding="utf-8").strip()
        if val:
            return val
    raise ForgeError(
        f"HANDBACK: no PixelLab API key available. Export {KEY_ENV} or put "
        f"the key (single line) in {KEY_FILE} (chmod 600). The key is read "
        "at runtime only — never hardcode, commit, or log it."
    )


def _redact(text: str, api_key: str | None) -> str:
    if api_key and text:
        return text.replace(api_key, "***REDACTED***")
    return text


# ---------------------------------------------------------------- HTTP seam
def _http_post_once(url: str, payload_bytes: bytes, api_key: str) -> dict:
    """One HTTP POST attempt (stdlib urllib). Raises ForgeHTTPStatusError on
    non-2xx (body key-redacted), ForgeError on transport/JSON failures."""
    req = urllib.request.Request(
        url,
        data=payload_bytes,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8", "replace")
        except Exception:
            raw = ""
        raise ForgeHTTPStatusError(e.code, _redact(raw, api_key), url) \
            from None
    except urllib.error.URLError as e:
        raise ForgeError(f"network error POSTing {url}: "
                         f"{_redact(str(e.reason), api_key)}") from None
    try:
        return json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise ForgeError(f"non-JSON response from {url}: {e}") from None


def _post_json(url: str, payload: dict, api_key: str) -> dict:
    """THE HTTP seam — every API call goes through here (tests mock this;
    zero real API calls in CI). Bounded retries: up to _RETRIES extra
    attempts on 429/5xx with a fixed _RETRY_SLEEP_S sleep; 4xx surface
    immediately (the caller adds actionable hints)."""
    payload_bytes = json.dumps(payload).encode("utf-8")
    attempt = 0
    while True:
        try:
            return _http_post_once(url, payload_bytes, api_key)
        except ForgeHTTPStatusError as e:
            retryable = e.status == 429 or 500 <= e.status <= 599
            if retryable and attempt < _RETRIES:
                attempt += 1
                time.sleep(_RETRY_SLEEP_S)
                continue
            raise


def _actionable_api_error(e: ForgeHTTPStatusError) -> str:
    """Surface the API error VERBATIM (already redacted) and, for the
    pilot-known style_image-size-mismatch failure, add the fix."""
    msg = f"PixelLab API error (HTTP {e.status}): {e.body}"
    low = (e.body or "").lower()
    if "style" in low and ("size" in low or "match" in low
                           or "dimension" in low):
        msg += ("\n  hint: style_image must EXACTLY match the output canvas "
                "size (pilot-proven). Use --style-dir to auto-build a "
                "per-size collage, or pass a --style-image whose dimensions "
                "equal this entry's canvas.")
    return msg


# ---------------------------------------------------------------- payloads
def _build_generate_payload(prompt: str, w: int, h: int,
                            style_b64: str | None,
                            palette_b64: str | None) -> dict:
    """generate-image-bitforge request. Pilot-proven fields; keep ALL field
    names in this one function for cheap correction."""
    payload: dict = {
        "description": prompt,
        "image_size": {"width": w, "height": h},
        "view": VIEW,
        "no_background": True,
    }
    if style_b64:
        payload["style_image"] = {"type": "base64", "base64": style_b64}
    if palette_b64:
        payload["color_image"] = {"type": "base64", "base64": palette_b64}
    return payload


def _build_rotate_payload(image_b64: str, w: int, h: int) -> dict:
    """/v1/rotate request (8-direction variants). Field names NOT
    re-verified against live docs — correct here if the API disagrees."""
    return {
        "image_size": {"width": w, "height": h},
        "from_image": {"type": "base64", "base64": image_b64},
        "n_directions": 8,
        "view": VIEW,
    }


def _extract_image_b64_list(resp: dict) -> list[str]:
    """Tolerant response walk: {'image': {'base64': ...}} (pilot-proven),
    {'image': '<b64>'}, or {'images': [...]} (rotate-style)."""
    if not isinstance(resp, dict):
        raise ForgeError("API response is not a JSON object")
    node = resp.get("image")
    if isinstance(node, dict) and isinstance(node.get("base64"), str):
        return [node["base64"]]
    if isinstance(node, str) and node:
        return [node]
    nodes = resp.get("images")
    if isinstance(nodes, list):
        out = []
        for n in nodes:
            if isinstance(n, dict) and isinstance(n.get("base64"), str):
                out.append(n["base64"])
            elif isinstance(n, str) and n:
                out.append(n)
        if out:
            return out
    raise ForgeError("API response carries no image payload "
                     f"(keys: {sorted(resp.keys())})")


def _response_meta(resp: dict) -> dict:
    """Provenance-safe response remainder: image payloads stripped, no auth
    material exists in a response body by construction."""
    return {k: v for k, v in resp.items() if k not in ("image", "images")}


# ---------------------------------------------------------------- sizes
def parse_size(text: str) -> tuple[int, int]:
    s = str(text).lower().replace("×", "x").strip()
    if "x" in s:
        a, _, b = s.partition("x")
        if a.strip().isdigit() and b.strip().isdigit():
            w, h = int(a), int(b)
            if w > 0 and h > 0:
                return w, h
    elif s.isdigit() and int(s) > 0:
        return int(s), int(s)
    raise ForgeError(f"cannot parse size {text!r} — expected WxH (e.g. 32x32)")


def size_from_entry(entry: dict) -> tuple[int, int]:
    """Tolerant size_hint reader (dict {w,h}/{width,height}, [w,h], int,
    'WxH'). Heuristic: when BOTH dims are < 16 the hint is in GRID UNITS
    (tiles) and is multiplied by 16 — the worklist speaks grid multiples."""
    hint = entry.get("size_hint", entry.get("size"))
    if hint is None:
        raise ForgeError(f"entry {entry.get('id', '?')!r} has no "
                         "size_hint — cannot pick a canvas")
    if isinstance(hint, dict):
        unit = str(hint.get("unit", "")).lower()
        w = hint.get("w", hint.get("width"))
        h = hint.get("h", hint.get("height"))
        if not (isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0):
            raise ForgeError(f"entry {entry.get('id', '?')!r} size_hint "
                             f"{hint!r} unusable")
        if unit == "grid" or (w < GRID and h < GRID):
            return w * GRID, h * GRID
        return w, h
    if isinstance(hint, (list, tuple)) and len(hint) == 2:
        w, h = int(hint[0]), int(hint[1])
    elif isinstance(hint, int):
        w = h = hint
    elif isinstance(hint, str):
        w, h = parse_size(hint)
    else:
        raise ForgeError(f"entry {entry.get('id', '?')!r} size_hint "
                         f"{hint!r} unusable")
    if w <= 0 or h <= 0:
        raise ForgeError(f"entry {entry.get('id', '?')!r} size_hint "
                         f"{hint!r} unusable")
    if w < GRID and h < GRID:      # grid-unit hint (e.g. "2x2" tiles)
        return w * GRID, h * GRID
    return w, h


# ---------------------------------------------------------------- style refs
_NEAREST = (Image.Resampling.NEAREST if hasattr(Image, "Resampling")
            else Image.NEAREST)


def _rgba_pixels(img: Image.Image) -> list[tuple[int, int, int, int]]:
    """RGBA tuples via tobytes() — avoids the Pillow-12-deprecated
    getdata() and stays stable across Pillow versions. Caller converts to
    RGBA first."""
    b = img.tobytes()
    return [tuple(b[i:i + 4]) for i in range(0, len(b), 4)]


def _list_style_pngs(style_dir: Path) -> list[Path]:
    if not style_dir.is_dir():
        raise ForgeError(f"--style-dir {style_dir} is not a directory")
    pngs = sorted((p for p in style_dir.iterdir()
                   if p.is_file() and p.suffix.lower() == ".png"),
                  key=lambda p: p.name)
    if not pngs:
        raise ForgeError(f"--style-dir {style_dir} contains no .png files")
    return pngs[:16]   # deterministic cap: first 16 by name


def build_style_collage(style_dir: Path, w: int, h: int) -> Image.Image:
    """Deterministic style collage at EXACTLY (w, h) — the pilot-proven
    requirement (style_image must match the output canvas size). Sorted
    sources tiled onto a ceil-sqrt grid, NEAREST resize, cells cycled so
    the canvas is fully covered."""
    srcs = _list_style_pngs(style_dir)
    n = len(srcs)
    cols = max(1, math.ceil(math.sqrt(n)))
    rows = max(1, math.ceil(n / cols))
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    idx = 0
    for r in range(rows):
        for c in range(cols):
            src = srcs[idx % n]
            idx += 1
            x0, x1 = (c * w) // cols, ((c + 1) * w) // cols
            y0, y1 = (r * h) // rows, ((r + 1) * h) // rows
            cw, ch = max(1, x1 - x0), max(1, y1 - y0)
            with Image.open(src) as im:
                tile = im.convert("RGBA").resize((cw, ch), _NEAREST)
            canvas.paste(tile, (x0, y0))
    return canvas


def fit_style_image(path: Path, w: int, h: int) -> tuple[Image.Image, bool]:
    """Prebuilt --style-image: used as-is when it already matches the
    canvas; otherwise deterministically NEAREST-resized to it (the API
    hard-requires an exact match). Returns (image, was_resized)."""
    if not path.is_file():
        raise ForgeError(f"--style-image {path} not found")
    try:
        with Image.open(path) as im:
            img = im.convert("RGBA")
    except (OSError, ValueError) as e:
        raise ForgeError(f"--style-image {path} is not a readable image: "
                         f"{e}") from None
    if img.size == (w, h):
        return img, False
    return img.resize((w, h), _NEAREST), True


def derive_palette_strip(style_dir: Path,
                         max_colors: int = MAX_PALETTE_COLORS) -> Image.Image:
    """Top-K (<=64) most frequent fully-opaque colors across the style dir,
    rendered 1px per color. Deterministic: ties break on the color tuple."""
    counts: dict[tuple[int, int, int], int] = {}
    for p in _list_style_pngs(style_dir):
        with Image.open(p) as im:
            for r, g, b, a in _rgba_pixels(im.convert("RGBA")):
                if a == 255:
                    counts[(r, g, b)] = counts.get((r, g, b), 0) + 1
    if not counts:
        raise ForgeError(f"--style-dir {style_dir} has no fully-opaque "
                         "pixels — cannot derive a palette strip")
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    colors = [c for c, _ in ranked[:max_colors]]
    strip = Image.new("RGBA", (len(colors), 1))
    strip.putdata([(r, g, b, 255) for (r, g, b) in colors])
    return strip


def load_palette_colors(strip: Image.Image) -> list[tuple[int, int, int]]:
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
        raise ForgeError("palette strip contains no opaque pixels")
    if len(out) > 256:
        raise ForgeError(f"palette strip has {len(out)} colors — expected "
                         "a small strip (<=256); is this really a strip?")
    return out


def quantize_to_palette(img: Image.Image,
                        colors: list[tuple[int, int, int]]) -> Image.Image:
    """Deterministic nearest-RGB quantize of every alpha>0 pixel to the
    strip colors; alpha bytes preserved verbatim; fully transparent pixels
    normalized to (0,0,0,0). Ties resolve to the earlier strip color."""
    img = img.convert("RGBA")
    cache: dict[tuple[int, int, int], tuple[int, int, int]] = {}

    def nearest(c: tuple[int, int, int]) -> tuple[int, int, int]:
        got = cache.get(c)
        if got is None:
            r, g, b = c
            got = min(colors, key=lambda p: (p[0] - r) ** 2
                      + (p[1] - g) ** 2 + (p[2] - b) ** 2)
            cache[c] = got
        return got

    out = []
    for r, g, b, a in _rgba_pixels(img):
        if a == 0:
            out.append((0, 0, 0, 0))
        else:
            nr, ng, nb = nearest((r, g, b))
            out.append((nr, ng, nb, a))
    q = Image.new("RGBA", img.size)
    q.putdata(out)
    return q


def png_bytes_of(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------- worklist
def load_worklist(path: Path) -> list[dict]:
    if not path.is_file():
        raise ForgeError(f"worklist not found: {path} — generate it with "
                         "cabinet/scripts/world-asset-spec.py")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise ForgeError(f"worklist {path} is not valid JSON: {e}") from None
    entries = doc.get("entries") if isinstance(doc, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ForgeError(f"worklist {path} has no entries[] — expected "
                         "cabinet.world.asset-worklist/v1")
    return entries


def prompt_from_entry(entry: dict) -> str:
    """Prompt text for one worklist entry. An explicit prompt/description
    wins; else synthesize deterministically from the canonical
    cabinet.world.asset-worklist/v1 fields — the spec-gen emits structured
    era_word/rung_state/object + a 'meaning' sentence, not prose prompts."""
    for k in ("prompt", "description"):
        v = entry.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    seen: set[str] = set()
    core: list[str] = []
    for k in ("era_word", "rung_state", "object"):
        v = entry.get(k)
        if isinstance(v, str) and v.strip():
            word = v.strip().replace("_", " ")
            if word not in seen:        # rung often repeats the era word
                seen.add(word)
                core.append(word)
    parts: list[str] = []
    if core:
        parts.append(", ".join(core))
    meaning = entry.get("meaning")
    if isinstance(meaning, str) and meaning.strip():
        parts.append(meaning.strip())
    if not parts:
        raise ForgeError(f"entry {entry.get('id', '?')!r} has no prompt/"
                         "description/meaning text to build a prompt from")
    return " — ".join(parts)


def select_entries(entries: list[dict], patterns: list[str]) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for pat in patterns:
        matched = [e for e in entries
                   if isinstance(e.get("id"), str)
                   and fnmatch.fnmatchcase(e["id"], pat)]
        if not matched:
            sample = ", ".join(str(e.get("id", "?")) for e in entries[:5])
            raise ForgeError(f"--entry {pat!r} matches no worklist ids "
                             f"(worklist has {len(entries)}; e.g. {sample})")
        for e in matched:
            if e["id"] not in seen:
                seen.add(e["id"])
                out.append(e)
    return out


def plan_jobs(args: argparse.Namespace) -> list[dict]:
    """Resolve the run into jobs: {id, prompt, w, h, entry}. Strict at plan
    time — a bad entry refuses the run before any spend."""
    if args.describe and args.entry:
        raise ForgeError("choose ONE mode: --describe (one-off) or "
                         "--worklist/--entry (worklist-driven)")
    jobs: list[dict] = []
    if args.describe:
        if not args.size:
            raise ForgeError("--describe needs --size WxH (e.g. 32x32)")
        w, h = parse_size(args.size)
        rid = args.id or ("oneoff-" + sanitize_id(args.describe.lower())[:40])
        jobs.append({"id": rid, "prompt": args.describe.strip(),
                     "w": w, "h": h, "entry": None})
    elif args.entry:
        if args.size:
            raise ForgeError("--size belongs to --describe one-off mode; "
                             "worklist canvas sizes come from size_hint")
        entries = load_worklist(Path(args.worklist))
        exact_ids = {p for p in args.entry
                     if not any(c in p for c in "*?[")}
        for e in select_entries(entries, args.entry):
            try:
                w, h = size_from_entry(e)
            except ForgeError as err:
                # Designed case: cross-ref rows (e.g. voyage reusing the
                # harbor_boat families) carry no canvas — un-forgeable by
                # construction. Skip under a glob; refuse when named
                # exactly (the caller explicitly wanted it).
                if e.get("id") in exact_ids:
                    raise
                cov = e.get("covered_by")
                print(f"skip {e.get('id')}: {err}"
                      + (f" (covered_by {cov!r} — no new art)" if cov
                         else ""), file=sys.stderr)
                continue
            prompt = prompt_from_entry(e)
            jobs.append({"id": e["id"], "prompt": prompt,
                         "w": w, "h": h, "entry": e})
        if not jobs:
            raise ForgeError("every matched entry was skipped (no "
                             "forgeable canvas) — nothing to do")
    else:
        raise ForgeError("nothing to do — use --worklist ... --entry "
                         "<id-or-glob> (repeatable; '*' selects all, the "
                         "spend guard still applies) or --describe ... "
                         "--size WxH")
    return jobs


# ---------------------------------------------------------------- refs
def build_refs(args: argparse.Namespace, sizes: list[tuple[int, int]],
               out_root: Path | None) -> dict:
    """Style + palette references. Style is built PER CANVAS SIZE (the API
    requires style_image == canvas size exactly). out_root=None => dry-run:
    everything in memory, nothing written."""
    refs: dict = {"style": {}, "palette": None}
    if args.style_dir and args.style_image:
        raise ForgeError("pass --style-dir OR --style-image, not both")

    if args.palette:
        p = Path(args.palette)
        if not p.is_file():
            raise ForgeError(f"--palette {p} not found")
        data = p.read_bytes()
        if data[:8] != PNG_MAGIC:
            raise ForgeError(f"--palette {p} is not a PNG")
        with Image.open(io.BytesIO(data)) as im:
            colors = load_palette_colors(im.convert("RGBA"))
        refs["palette"] = {"b64": base64.b64encode(data).decode("ascii"),
                           "sha256": sha256_of(data), "colors": colors,
                           "source": str(p)}
    elif args.style_dir:
        strip = derive_palette_strip(Path(args.style_dir))
        data = png_bytes_of(strip)
        refs["palette"] = {"b64": base64.b64encode(data).decode("ascii"),
                           "sha256": sha256_of(data),
                           "colors": load_palette_colors(strip),
                           "source": f"derived from {args.style_dir} "
                                     f"(top-{MAX_PALETTE_COLORS} opaque)"}
        if out_root is not None:
            _write_jailed(out_root, out_root / "_refs"
                          / "palette-strip-derived.png", data)

    for (w, h) in sizes:
        if args.style_dir:
            img = build_style_collage(Path(args.style_dir), w, h)
            src, resized = f"collage of {args.style_dir}", False
        elif args.style_image:
            img, resized = fit_style_image(Path(args.style_image), w, h)
            src = str(args.style_image)
        else:
            continue
        data = png_bytes_of(img)
        refs["style"][(w, h)] = {
            "b64": base64.b64encode(data).decode("ascii"),
            "sha256": sha256_of(data), "source": src, "resized": resized,
        }
        if out_root is not None:
            _write_jailed(out_root, out_root / "_refs"
                          / f"style-{w}x{h}.png", data)
    return refs


# ---------------------------------------------------------------- forge run
def _process_image_bytes(b64_payload: str, palette_colors, requested,
                         label: str) -> tuple[bytes, dict]:
    """Validate + post-process ONE api image: b64 -> PNG-magic check ->
    PIL RGBA -> palette quantize (alpha preserved) -> re-encoded PNG bytes
    + facts dict. Raises ForgeError on refusal (nothing written)."""
    try:
        raw = base64.b64decode(b64_payload)
    except (binascii.Error, ValueError) as e:
        raise ForgeError(f"{label}: undecodable base64 image payload "
                         f"({e})") from None
    if raw[:8] != PNG_MAGIC:
        raise ForgeError(f"{label}: API payload is not a PNG (magic bytes) "
                         "— refused, nothing written")
    with Image.open(io.BytesIO(raw)) as im:
        img = im.convert("RGBA")
    if palette_colors:
        img = quantize_to_palette(img, palette_colors)
    data = png_bytes_of(img)
    w, h = img.size
    facts = {
        "w": w, "h": h,
        "grid_ok": (w % GRID == 0) and (h % GRID == 0),
        "matches_request": (w, h) == tuple(requested),
        "sha256": sha256_of(data),
    }
    return data, facts


def run(args: argparse.Namespace) -> int:
    jobs = plan_jobs(args)
    if args.candidates < 1:
        raise ForgeError("--candidates must be >= 1")
    if args.limit < 1:
        raise ForgeError("--limit must be >= 1")

    calls_per_candidate = 2 if args.rotate else 1
    planned_calls = len(jobs) * args.candidates * calls_per_candidate
    over_limit = planned_calls > args.limit

    sizes = sorted({(j["w"], j["h"]) for j in jobs})
    for j in jobs:
        if j["w"] % GRID or j["h"] % GRID:
            print(f"warn: {j['id']} canvas {j['w']}x{j['h']} is off the "
                  f"{GRID}px grid — the gate will flag it", file=sys.stderr)
        cov = (j["entry"] or {}).get("covered_by")
        if cov:
            print(f"warn: {j['id']} is covered_by {cov!r} — its art is "
                  "owned by that ladder family; generating anyway spends "
                  "candidates on a duplicate", file=sys.stderr)

    if args.dry_run:
        refs = build_refs(args, sizes, out_root=None)
        print("DRY RUN — request plan (zero API calls, zero writes)")
        print(f"  endpoint: {args.endpoint}")
        if args.rotate:
            print(f"  rotate-endpoint: {args.rotate_endpoint} (fields "
                  "unverified vs live docs)")
        print(f"  auth: {key_source()} "
              f"({KEY_ENV} | {KEY_FILE}; value never printed)")
        pal = refs["palette"]
        print(f"  palette: {pal['source']} — {len(pal['colors'])} colors, "
              f"sha256 {pal['sha256'][:12]}…" if pal else
              "  palette: none (no quantize, no color_image)")
        for (w, h) in sizes:
            st = refs["style"].get((w, h))
            print(f"  style {w}x{h}: " + (f"{st['source']}"
                  f"{' [RESIZED to canvas]' if st['resized'] else ''}, "
                  f"sha256 {st['sha256'][:12]}…" if st else "none"))
        for j in jobs:
            print(f"  entry {j['id']}: {j['w']}x{j['h']} x"
                  f"{args.candidates} candidate(s) — prompt: "
                  f"{j['prompt'][:80]}")
        verdict = (f"EXCEEDS --limit {args.limit}: a real run would REFUSE "
                   f"(re-run with --limit {planned_calls})"
                   if over_limit else f"within --limit {args.limit}")
        print(f"  planned API calls: {planned_calls} — {verdict}")
        return EXIT_OK

    if over_limit:
        raise SpendGuardRefusal(
            f"REFUSED (spend guard): this run would make {planned_calls} "
            f"API calls ({len(jobs)} entr{'y' if len(jobs) == 1 else 'ies'}"
            f" x {args.candidates} candidate(s)"
            + (" x 2 for --rotate" if args.rotate else "")
            + f") but --limit is {args.limit}. Nothing was generated — "
            f"narrow --entry, lower --candidates, or re-run with an "
            f"explicit --limit {planned_calls} if you mean it."
        )

    api_key = load_api_key()
    out_root = Path(args.out).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    refs = build_refs(args, sizes, out_root=out_root)
    pal = refs["palette"]
    palette_colors = pal["colors"] if pal else None

    ok = flagged = failed = 0
    for job in jobs:
        jid = sanitize_id(job["id"])
        entry_dir = _entry_dir(out_root, job["id"])
        w, h = job["w"], job["h"]
        style = refs["style"].get((w, h))
        payload = _build_generate_payload(
            job["prompt"], w, h,
            style["b64"] if style else None,
            pal["b64"] if pal else None)
        for n in range(1, args.candidates + 1):
            label = f"{jid} cand-{n}"
            try:
                resp = _post_json(args.endpoint, payload, api_key)
                b64img = _extract_image_b64_list(resp)[0]
                data, facts = _process_image_bytes(
                    b64img, palette_colors, (w, h), label)
            except ForgeHTTPStatusError as e:
                print(f"FAIL {label}: {_actionable_api_error(e)}",
                      file=sys.stderr)
                failed += 1
                continue
            except ForgeError as e:
                print(f"FAIL {label}: {e}", file=sys.stderr)
                failed += 1
                continue

            png_path = entry_dir / f"cand-{n}.png"
            _write_jailed(out_root, png_path, data)

            warns = []
            if not facts["grid_ok"]:
                warns.append(f"off the {GRID}px grid "
                             f"({facts['w']}x{facts['h']})")
            if not facts["matches_request"]:
                warns.append(f"API returned {facts['w']}x{facts['h']} for "
                             f"a {w}x{h} request")

            rotations = []
            rotate_error = None
            if args.rotate:
                try:
                    rresp = _post_json(
                        args.rotate_endpoint,
                        _build_rotate_payload(
                            base64.b64encode(data).decode("ascii"), w, h),
                        api_key)
                    for k, rb64 in enumerate(_extract_image_b64_list(rresp),
                                             start=1):
                        rdata, rfacts = _process_image_bytes(
                            rb64, palette_colors, (w, h),
                            f"{label} rot{k}")
                        rpath = entry_dir / f"cand-{n}-rot{k}.png"
                        _write_jailed(out_root, rpath, rdata)
                        rotations.append({"path": rpath.name,
                                          "sha256": rfacts["sha256"],
                                          "grid_ok": rfacts["grid_ok"]})
                except ForgeHTTPStatusError as e:
                    rotate_error = _actionable_api_error(e)
                except ForgeError as e:
                    rotate_error = str(e)
                if rotate_error:
                    warns.append(f"rotate failed: {rotate_error}")

            sidecar = {
                "schema": "cabinet.world.forge-candidate/v1",
                "entry_id": jid,
                "candidate": n,
                "prompt": job["prompt"],
                "endpoint": args.endpoint,
                "params": {
                    "view": VIEW,
                    "no_background": True,
                    "image_size": {"width": w, "height": h},
                    "candidates_requested": args.candidates,
                    "rotate": bool(args.rotate),
                    "quantized_to_palette": bool(palette_colors),
                    "alpha": "preserved (RGB quantized for alpha>0; "
                             "alpha==0 normalized transparent)",
                },
                "size": {"w": w, "h": h},
                "actual_size": {"w": facts["w"], "h": facts["h"]},
                "grid": GRID,
                "grid_ok": facts["grid_ok"],
                "style_collage_sha256": style["sha256"] if style else None,
                "style_source": style["source"] if style else None,
                "style_resized_to_canvas": (style["resized"]
                                            if style else False),
                "palette_strip_sha256": pal["sha256"] if pal else None,
                "palette_source": pal["source"] if pal else None,
                "png_sha256": facts["sha256"],
                "response_meta": _response_meta(resp),
                "rotations": rotations,
                "rotate_error": rotate_error,
                "worklist_entry": job["entry"],
                "manifest_row": {          # world-asset-install.py:141-147
                    "id": jid,             # stable: one winner per entry
                    "path": f"{jid}/cand-{n}.png",
                    "w": facts["w"], "h": facts["h"], "grid": GRID,
                    "sha256": facts["sha256"],
                    "pack": f"PixelLab forge candidate — {jid}",
                    "license": LICENSE,
                },
            }
            _write_jailed(out_root, entry_dir / f"cand-{n}.json",
                          (json.dumps(sidecar, indent=2, sort_keys=True,
                                      ensure_ascii=False) + "\n")
                          .encode("utf-8"))

            if warns:
                flagged += 1
                print(f"FLAG {label}: " + "; ".join(warns), file=sys.stderr)
            else:
                ok += 1
                print(f"ok   {label} {facts['w']}x{facts['h']} "
                      f"sha256 {facts['sha256'][:12]}…")

    total = len(jobs) * args.candidates
    print(f"forge: {ok} ok, {flagged} flagged, {failed} failed of {total} "
          f"candidate(s) -> {out_root}")
    print("acceptance: human pick only — promote via world-asset-install/"
          "world-asset-gate; the forge never ingests.")
    return EXIT_CANDIDATE_ISSUES if (failed or flagged) else EXIT_OK


# ---------------------------------------------------------------- CLI
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="world-asset-forge.py",
        description="PixelLab.ai sprite-candidate forge (Cabinet World). "
                    "Generates N candidates per entry with provenance "
                    "sidecars; a human promotes winners via the "
                    "world-asset-install/world-asset-gate flow.",
        epilog=f"Spend guard: --limit (default {DEFAULT_LIMIT}) hard-caps "
               "total API calls per invocation; over-limit runs are refused "
               "with the exact count, never truncated. Key: env "
               f"{KEY_ENV} else {KEY_FILE} (runtime only, never logged). "
               "Exit codes: 0 ok, 1 candidate failures/flags, 2 usage/"
               "spend-guard, 4 key handback.")
    p.add_argument("--worklist", default=str(DEFAULT_WORKLIST),
                   help="asset worklist JSON from world-asset-spec.py "
                        f"(default {DEFAULT_WORKLIST})")
    p.add_argument("--entry", action="append", default=[],
                   metavar="ID_OR_GLOB",
                   help="worklist entry id or fnmatch glob (repeatable)")
    p.add_argument("--describe", help="one-off mode: freehand prompt text")
    p.add_argument("--size", help="one-off canvas WxH in px (e.g. 32x32)")
    p.add_argument("--id", help="one-off entry id (default derived from "
                                "--describe)")
    p.add_argument("--candidates", type=int, default=DEFAULT_CANDIDATES,
                   help=f"candidates per entry (default {DEFAULT_CANDIDATES}"
                        "; pilot ~1/3 one-shot usable — human picks)")
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                   help=f"HARD cap on total API calls (default "
                        f"{DEFAULT_LIMIT}); over-limit refuses")
    p.add_argument("--style-dir", help="dir of reference PNGs — builds a "
                   "deterministic style collage per canvas size (and "
                   "derives a palette strip when --palette absent)")
    p.add_argument("--style-image", help="prebuilt style PNG (auto-fit to "
                   "canvas when sizes differ — the API needs an exact "
                   "match)")
    p.add_argument("--palette", "--palette-image", dest="palette",
                   help="palette strip PNG: sent as API color_image AND "
                        "the post-quantize target")
    p.add_argument("--rotate", action="store_true",
                   help="also call /rotate per candidate (8-direction; "
                        "spends a 2nd API call per candidate; field names "
                        "unverified vs live docs)")
    p.add_argument("--endpoint", default=DEFAULT_ENDPOINT,
                   help=f"generate endpoint (default {DEFAULT_ENDPOINT})")
    p.add_argument("--rotate-endpoint", default=DEFAULT_ROTATE_ENDPOINT,
                   help=f"rotate endpoint (default {DEFAULT_ROTATE_ENDPOINT})")
    p.add_argument("--out", default=str(DEFAULT_OUT),
                   help=f"candidate out dir (default {DEFAULT_OUT}; "
                        "gitignored review area)")
    p.add_argument("--dry-run", action="store_true",
                   help="print the request plan — zero API calls, zero "
                        "writes")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except SpendGuardRefusal as e:
        print(str(e), file=sys.stderr)
        return EXIT_USAGE
    except ForgeError as e:
        msg = str(e)
        if msg.startswith("HANDBACK"):
            print(msg, file=sys.stderr)
            return EXIT_HANDBACK
        print(f"world-asset-forge: {msg}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
