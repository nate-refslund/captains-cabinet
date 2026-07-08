"""Pure-stdlib PNG codec for the aesthetic gates (python3.12, no Pillow).

WHY: the gates must run on the bare system python3.12 (no venv guaranteed on
the Mac Mini target), and every image the gates touch is a small pixel-art
render or corpus scene. Supports exactly what the corpus + renderer emit:
8-bit, non-interlaced, color types 0 (gray), 2 (RGB), 3 (palette+tRNS),
6 (RGBA). Everything else is rejected loudly — a gate must never silently
mis-read pixels.

Decode returns (width, height, rgba: bytes) with 4 bytes per pixel.
Encode writes color type 6 (RGBA), filter 0 rows.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

_SIG = b"\x89PNG\r\n\x1a\n"
# Hard cap so a hostile/corrupt file cannot balloon memory via zlib
# (decompression bomb): 64 MP * 4 bytes ≈ 256 MB worst case, far above any
# legitimate render but bounded.
MAX_PIXELS = 64_000_000

_CHANNELS = {0: 1, 2: 3, 3: 1, 6: 4}


class PngError(ValueError):
    pass


def _chunks(data: bytes):
    if data[:8] != _SIG:
        raise PngError("not a PNG (bad signature)")
    pos = 8
    n = len(data)
    while pos + 8 <= n:
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctype = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        if len(body) != length:
            raise PngError(f"truncated chunk {ctype!r}")
        yield ctype, body
        pos += 12 + length  # length + type + body + crc
        if ctype == b"IEND":
            return
    raise PngError("missing IEND")


def read_size(path: str | Path) -> tuple[int, int]:
    """Width/height from IHDR only — no pixel decode (cheap for label gate)."""
    with open(path, "rb") as f:
        head = f.read(33)
    if head[:8] != _SIG or head[12:16] != b"IHDR":
        raise PngError(f"not a PNG: {path}")
    w, h = struct.unpack(">II", head[16:24])
    return w, h


def decode(path: str | Path, max_pixels: int = MAX_PIXELS) -> tuple[int, int, bytes]:
    data = Path(path).read_bytes()
    width = height = None
    bitdepth = colortype = interlace = None
    idat = bytearray()
    plte: bytes | None = None
    trns: bytes | None = None

    for ctype, body in _chunks(data):
        if ctype == b"IHDR":
            width, height, bitdepth, colortype, _comp, _filt, interlace = \
                struct.unpack(">IIBBBBB", body)
        elif ctype == b"IDAT":
            idat.extend(body)
        elif ctype == b"PLTE":
            plte = body
        elif ctype == b"tRNS":
            trns = body

    if width is None:
        raise PngError("missing IHDR")
    if bitdepth != 8:
        raise PngError(f"unsupported bit depth {bitdepth} (only 8)")
    if colortype not in _CHANNELS:
        raise PngError(f"unsupported color type {colortype} (0/2/3/6 only)")
    if interlace != 0:
        raise PngError("interlaced PNG unsupported")
    if width <= 0 or height <= 0 or width * height > max_pixels:
        raise PngError(f"image size {width}x{height} outside sane bounds")

    ch = _CHANNELS[colortype]
    rowbytes = width * ch
    expected = (rowbytes + 1) * height

    # Bounded decompression: never let zlib hand back more than expected.
    dec = zlib.decompressobj()
    raw = dec.decompress(bytes(idat), expected)
    if len(raw) < expected:
        raw += dec.flush(expected - len(raw))
    if len(raw) < expected:
        raise PngError("truncated pixel data")
    raw = raw[:expected]

    # Unfilter (spec filters 0..4). 8-bit depth → bpp == channel count.
    recon = bytearray(rowbytes * height)
    prev_start = -1
    for y in range(height):
        fpos = y * (rowbytes + 1)
        ftype = raw[fpos]
        line = bytearray(raw[fpos + 1:fpos + 1 + rowbytes])
        start = y * rowbytes
        if ftype == 0:
            pass
        elif ftype == 1:  # Sub
            for i in range(ch, rowbytes):
                line[i] = (line[i] + line[i - ch]) & 0xFF
        elif ftype == 2:  # Up
            if prev_start >= 0:
                for i in range(rowbytes):
                    line[i] = (line[i] + recon[prev_start + i]) & 0xFF
        elif ftype == 3:  # Average
            if prev_start >= 0:
                for i in range(rowbytes):
                    a = line[i - ch] if i >= ch else 0
                    line[i] = (line[i] + ((a + recon[prev_start + i]) >> 1)) & 0xFF
            else:
                for i in range(ch, rowbytes):
                    line[i] = (line[i] + (line[i - ch] >> 1)) & 0xFF
        elif ftype == 4:  # Paeth
            for i in range(rowbytes):
                a = line[i - ch] if i >= ch else 0
                b = recon[prev_start + i] if prev_start >= 0 else 0
                c = recon[prev_start + i - ch] if (prev_start >= 0 and i >= ch) else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                if pa <= pb and pa <= pc:
                    pr = a
                elif pb <= pc:
                    pr = b
                else:
                    pr = c
                line[i] = (line[i] + pr) & 0xFF
        else:
            raise PngError(f"bad filter type {ftype} at row {y}")
        recon[start:start + rowbytes] = line
        prev_start = start

    # Expand to RGBA.
    out = bytearray(width * height * 4)
    if colortype == 6:
        out[:] = recon
    elif colortype == 2:
        o = 0
        for i in range(0, len(recon), 3):
            out[o] = recon[i]
            out[o + 1] = recon[i + 1]
            out[o + 2] = recon[i + 2]
            out[o + 3] = 255
            o += 4
    elif colortype == 0:
        o = 0
        for v in recon:
            out[o] = out[o + 1] = out[o + 2] = v
            out[o + 3] = 255
            o += 4
    else:  # palette
        if plte is None:
            raise PngError("palette PNG missing PLTE")
        o = 0
        for idx in recon:
            base = idx * 3
            if base + 3 > len(plte):
                raise PngError(f"palette index {idx} out of range")
            out[o] = plte[base]
            out[o + 1] = plte[base + 1]
            out[o + 2] = plte[base + 2]
            out[o + 3] = trns[idx] if (trns is not None and idx < len(trns)) else 255
            o += 4
    return width, height, bytes(out)


def _chunk(ctype: bytes, body: bytes) -> bytes:
    return (struct.pack(">I", len(body)) + ctype + body
            + struct.pack(">I", zlib.crc32(ctype + body) & 0xFFFFFFFF))


def encode(path: str | Path, width: int, height: int, rgba: bytes) -> None:
    """Write an RGBA8 PNG (filter 0). Used by tests + synthetic fixtures."""
    if len(rgba) != width * height * 4:
        raise PngError("rgba buffer size mismatch")
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    rowbytes = width * 4
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw.extend(rgba[y * rowbytes:(y + 1) * rowbytes])
    body = zlib.compress(bytes(raw), 6)
    Path(path).write_bytes(
        _SIG + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", body) + _chunk(b"IEND", b""))
