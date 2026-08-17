"""Build a Windows-compatible ICO from spriteforge_icon.png.

Pillow's default ICO writer stores PNG-compressed frames. Explorer and
PyInstaller often fail to show those on the EXE, so this writes classic
32-bit BMP DIB frames (plus a PNG 256px entry, which Vista+ expects).
"""
from __future__ import annotations

import struct
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "spriteforge_icon.png"
DEST = ROOT / "spriteforge.ico"
# BMP frames Explorer always understands; 256 stays PNG (Vista+ convention).
BMP_SIZES = (16, 20, 24, 32, 40, 48, 64, 128)
PNG_SIZES = (256,)


def _dib(im: Image.Image) -> bytes:
    im = im.convert("RGBA")
    w, h = im.size
    pixels = list(im.getdata())
    xor = bytearray()
    and_row = ((w + 31) // 32) * 4
    mask = bytearray()
    for y in range(h - 1, -1, -1):
        bits = bytearray(and_row)
        for x in range(w):
            r, g, b, a = pixels[y * w + x]
            xor.extend((b, g, r, a))
            if a < 128:
                bits[x // 8] |= 1 << (7 - (x % 8))
        mask.extend(bits)
    header = struct.pack(
        "<IiiHHIIiiII",
        40,
        w,
        h * 2,
        1,
        32,
        0,
        len(xor) + len(mask),
        0,
        0,
        0,
        0,
    )
    return header + bytes(xor) + bytes(mask)


def _png256(im: Image.Image) -> bytes:
    from io import BytesIO

    buf = BytesIO()
    im.convert("RGBA").save(buf, format="PNG")
    return buf.getvalue()


def write_ico(src: Path, dest: Path) -> None:
    master = Image.open(src).convert("RGBA")
    frames: list[tuple[int, int, bytes]] = []
    for s in BMP_SIZES:
        frames.append((s, 32, _dib(master.resize((s, s), Image.Resampling.LANCZOS))))
    for s in PNG_SIZES:
        frames.append((s, 32, _png256(master.resize((s, s), Image.Resampling.LANCZOS))))

    count = len(frames)
    offset = 6 + 16 * count
    out = bytearray()
    out += struct.pack("<HHH", 0, 1, count)
    for size, bpp, data in frames:
        out += struct.pack(
            "<BBBBHHII",
            0 if size >= 256 else size,
            0 if size >= 256 else size,
            0,
            0,
            1,
            bpp,
            len(data),
            offset,
        )
        offset += len(data)
    for _size, _bpp, data in frames:
        out += data
    dest.write_bytes(out)


if __name__ == "__main__":
    if not SRC.is_file():
        raise SystemExit(f"missing source art: {SRC}")
    write_ico(SRC, DEST)
    print(f"wrote {DEST} ({DEST.stat().st_size} bytes)")
