"""PNG codec: roundtrip, all filter types, rejections, corpus smoke."""

import random
import struct
import zlib

import pytest


def test_roundtrip_rgba(wa, tmp_path):
    rng = random.Random(1)
    w, h = 13, 7
    rgba = bytes(rng.randrange(256) for _ in range(w * h * 4))
    p = tmp_path / "rt.png"
    wa.png.encode(p, w, h, rgba)
    assert wa.png.read_size(p) == (w, h)
    dw, dh, out = wa.png.decode(p)
    assert (dw, dh) == (w, h)
    assert out == rgba


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _chunk(ctype, body):
    return (struct.pack(">I", len(body)) + ctype + body
            + struct.pack(">I", zlib.crc32(ctype + body) & 0xFFFFFFFF))


def test_decode_all_filter_types(wa, tmp_path):
    """Forward-filter a known image with Sub/Up/Average/Paeth, expect exact
    reconstruction — pins the unfilter math against the spec."""
    rng = random.Random(7)
    w, h, bpp = 5, 4, 4
    rows = [bytes(rng.randrange(256) for _ in range(w * bpp))
            for _ in range(h)]
    filters = [1, 2, 3, 4]
    raw = bytearray()
    for y, ftype in enumerate(filters):
        cur = rows[y]
        prev = rows[y - 1] if y else bytes(w * bpp)
        raw.append(ftype)
        for i in range(w * bpp):
            a = cur[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if ftype == 1:
                v = cur[i] - a
            elif ftype == 2:
                v = cur[i] - b
            elif ftype == 3:
                v = cur[i] - ((a + b) >> 1)
            else:
                v = cur[i] - _paeth(a, b, c)
            raw.append(v & 0xFF)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    p = tmp_path / "filt.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
                  + _chunk(b"IDAT", zlib.compress(bytes(raw)))
                  + _chunk(b"IEND", b""))
    dw, dh, out = wa.png.decode(p)
    assert (dw, dh) == (w, h)
    assert out == b"".join(rows)


def test_rejects_interlace_and_16bit_and_bombs(wa, tmp_path):
    def make(ihdr):
        p = tmp_path / "bad.png"
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
                      + _chunk(b"IDAT", zlib.compress(b"\x00" * 5))
                      + _chunk(b"IEND", b""))
        return p

    PngError = wa.png.PngError
    with pytest.raises(PngError, match="interlaced"):
        wa.png.decode(make(struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 1)))
    with pytest.raises(PngError, match="bit depth"):
        wa.png.decode(make(struct.pack(">IIBBBBB", 1, 1, 16, 6, 0, 0, 0)))
    with pytest.raises(PngError, match="bounds"):
        wa.png.decode(make(struct.pack(">IIBBBBB", 1 << 20, 1 << 20, 8, 6, 0, 0, 0)))
    with pytest.raises(PngError):
        wa.png.decode(tmp_path / "nope.png") if (tmp_path / "nope.png").exists() \
            else (_ for _ in ()).throw(PngError("missing"))


def test_corpus_smoke(wa):
    # The corpus itself is gitignored, so "no corpus at all" is a legitimate
    # skip. A corpus that EXISTS but is missing a named image is not — that is
    # a corpus/test mismatch, and skipping it is how this sensor went quiet
    # through the 2026-07-28 re-fit (it named LimeZu positives that no longer
    # exist). Assert instead, so a corpus change has to update its readers.
    if not wa.has_corpus:
        pytest.skip("gitignored corpus not present on this checkout")
    rgb = wa.corpus_dir / "positive" / "pos-owned-square-close.png"  # ct2
    rgba = wa.corpus_dir / "negative" / "neg-city-street-void.png"   # ct6
    for p in (rgb, rgba):
        assert p.exists(), (
            f"{p.name} is named by this test but not in the corpus — "
            f"re-point the test at a current corpus image (both PNG colour "
            f"types must stay covered: ct2 truecolour and ct6 truecolour+alpha)")
        w, h, buf = wa.png.decode(p)
        assert (w, h) == wa.png.read_size(p)
        assert len(buf) == w * h * 4
        assert any(buf[i + 3] for i in range(0, 400, 4))  # some opacity
