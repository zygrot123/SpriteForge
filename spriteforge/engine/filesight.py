"""Look at local images, zip, and rar so Forge can get inspired."""
from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

from PIL import Image, ImageFilter, ImageStat

from ..paths import OUTPUTS, ensure_dirs
from .assets import unique_out

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
ARCHIVE_EXT = {".zip", ".rar", ".7z"}


def _avg_color(im: Image.Image) -> tuple[int, int, int]:
    small = im.convert("RGB").resize((32, 32), Image.Resampling.BOX)
    st = ImageStat.Stat(small)
    return int(st.mean[0]), int(st.mean[1]), int(st.mean[2])


def _palette(im: Image.Image, n: int = 5) -> list[str]:
    q = im.convert("RGB").resize((80, 80), Image.Resampling.BOX).quantize(colors=n, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette() or []
    counts = sorted(q.getcolors() or [], reverse=True)
    out = []
    for _c, idx in counts[:n]:
        r, g, b = pal[idx * 3 : idx * 3 + 3]
        out.append(f"#{r:02x}{g:02x}{b:02x}")
    return out


def inspect_image(path: Path) -> dict:
    path = Path(path)
    im = Image.open(path)
    rgb = im.convert("RGB")
    w, h = rgb.size
    r, g, b = _avg_color(rgb)
    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    sat = (max(r, g, b) - min(r, g, b)) / 255.0
    edges = float(ImageStat.Stat(rgb.filter(ImageFilter.FIND_EDGES).convert("L")).mean[0])
    warm = r > b + 12
    cool = b > r + 12
    mood = "bright" if luma > 160 else "mid" if luma > 80 else "dark"
    if sat < 0.12:
        tone = "muted / nearly gray"
    elif warm:
        tone = "warm (ember, gold, skin)"
    elif cool:
        tone = "cool (cyan, steel, night)"
    else:
        tone = "balanced color"
    busy = "busy, lots of edges" if edges > 28 else "simple, readable shapes"
    ratio = w / max(h, 1)
    if ratio > 1.5:
        shape = "wide cinematic"
    elif ratio < 0.75:
        shape = "tall portrait"
    else:
        shape = "near-square"
    return {
        "kind": "image",
        "name": path.name,
        "path": str(path),
        "width": w,
        "height": h,
        "mode": im.mode,
        "mood": mood,
        "tone": tone,
        "busy": busy,
        "shape": shape,
        "palette": _palette(rgb),
        "summary": (
            f"{path.name} — {w}×{h} {shape}, {mood} {tone}, {busy}. "
            f"Palette {', '.join(_palette(rgb)[:4])}."
        ),
    }


def _extract_zip(src: Path, dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    found: list[Path] = []
    with zipfile.ZipFile(src, "r") as zf:
        for info in zf.infolist()[:80]:
            if info.is_dir():
                continue
            suffix = Path(info.filename).suffix.lower()
            if suffix not in IMAGE_EXT:
                continue
            name = Path(info.filename).name
            out = dest / name
            out.write_bytes(zf.read(info))
            found.append(out)
    return found


def _extract_rar(src: Path, dest: Path) -> list[Path]:
    from ..bootstrap import seven_zip

    seven = seven_zip()
    dest.mkdir(parents=True, exist_ok=True)
    if not seven.exists():
        raise RuntimeError("7zr.exe is missing — cannot open RAR. Run Setup / Fix.")
    proc = subprocess.run(
        [str(seven), "x", "-y", f"-o{dest}", str(src)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "7zr failed")[-300:])
    found = []
    for p in dest.rglob("*"):
        if p.is_file() and p.suffix.lower() in IMAGE_EXT:
            found.append(p)
    return found[:40]


def inspect_archive(path: Path) -> dict:
    path = Path(path)
    dest = unique_out(OUTPUTS, f"seen_{path.stem}").with_suffix("")
    dest.mkdir(parents=True, exist_ok=True)
    ext = path.suffix.lower()
    if ext == ".zip":
        images = _extract_zip(path, dest)
    elif ext in {".rar", ".7z"}:
        images = _extract_rar(path, dest)
    else:
        raise RuntimeError(f"Unsupported archive: {ext}")
    notes = []
    for im in images[:8]:
        try:
            notes.append(inspect_image(im))
        except OSError:
            continue
    names = [p.name for p in images]
    moods = [n["mood"] for n in notes]
    tones = [n["tone"] for n in notes]
    return {
        "kind": "archive",
        "name": path.name,
        "path": str(path),
        "count": len(images),
        "files": names[:30],
        "images": notes,
        "summary": (
            f"{path.name} — {len(images)} pictures inside. "
            f"Moods: {', '.join(sorted(set(moods))) or 'unknown'}. "
            f"Color: {', '.join(sorted(set(tones))) or 'mixed'}."
        ),
    }


def inspect_any(path: Path) -> dict:
    ensure_dirs()
    path = Path(path)
    suf = path.suffix.lower()
    if suf in IMAGE_EXT:
        return inspect_image(path)
    if suf in ARCHIVE_EXT:
        return inspect_archive(path)
    return {
        "kind": "file",
        "name": path.name,
        "path": str(path),
        "summary": f"{path.name} ({path.suffix or 'no extension'}, {path.stat().st_size} bytes). I can read pictures and zip/rar packs.",
    }
