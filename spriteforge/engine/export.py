from __future__ import annotations

import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

from PIL import Image

from ..paths import EXPORTS, VIDEOS, ensure_dirs
from .assets import compose_sheet, slugify, now_stamp

UNITY_README = """SpriteForge → Unity
====================
1. Copy the Sprites folder into Assets/Sprites/ (or any folder under Assets).
2. Select the PNGs → Inspector → Texture Type: Sprite (2D and UI).
3. Sprite Mode: Multiple if you use a sheet, Single if you use the frame sequence.
4. Pixels Per Unit: 100 (or match your project). Filter Mode: Point (no filter) for pixel art.
5. For a clip: Window → Animation → create a clip and drop the numbered frames in order.
6. fps is in spriteforge.json.
"""

UNREAL_README = """SpriteForge → Unreal (Paper2D)
==============================
1. Copy this folder into your project's Content/ directory.
2. In Unreal, the PNGs import as textures. Open each → Sprite Actions → Apply Paper2D Texture Settings.
3. Select the frame sequence → right click → Sprite Actions → Create Sprite.
4. Select those sprites → right click → Create Flipbook. Set frames per second from spriteforge.json.
5. Drop the Flipbook on a PaperFlipbookComponent.
"""

GODOT_README = """SpriteForge → Godot
===================
1. Copy the Sprites folder into res://.
2. Select images → Import → Preset: 2D Pixel if pixel art (filter off).
3. AnimatedSprite2D → Sprite Frames → New SpriteFrames → add the numbered PNGs in order.
4. Set FPS from spriteforge.json.
"""

GENERIC_README = """SpriteForge export
==================
frames/   numbered PNG or JPEG frames
sheet.png optional sprite sheet
spriteforge.json  name, fps, frame size, loop
Use in any engine, After Effects, Aseprite, or Photoshop.
"""


def find_ffmpeg() -> Path | None:
    from ..bootstrap import locate_ffmpeg

    return locate_ffmpeg()


def find_rar() -> Path | None:
    w = shutil.which("rar") or shutil.which("Rar")
    if w:
        return Path(w)
    for p in (
        Path(r"C:\Program Files\WinRAR\Rar.exe"),
        Path(r"C:\Program Files (x86)\WinRAR\Rar.exe"),
    ):
        if p.exists():
            return p
    return None


def collect_images(src: Path | list[Path]) -> list[Path]:
    if isinstance(src, list):
        return [Path(p) for p in src if Path(p).exists()]
    src = Path(src)
    if src.is_file():
        return [src]
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    files = [p for p in src.iterdir() if p.suffix.lower() in exts and not p.name.endswith("_lock.png")]
    files.sort()
    return files


def _rgb(im: Image.Image, bg=(0, 0, 0)) -> Image.Image:
    if im.mode != "RGBA":
        return im.convert("RGB")
    base = Image.new("RGB", im.size, bg)
    base.paste(im, mask=im.split()[-1])
    return base


def write_frames(files: list[Path], dest_dir: Path, fmt: str = "png") -> list[Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    ext = ".jpg" if fmt.lower() in {"jpg", "jpeg"} else ".png"
    for i, src in enumerate(files):
        im = Image.open(src)
        dest = dest_dir / f"{i:02d}{ext}"
        if ext == ".jpg":
            _rgb(im.convert("RGBA"), (0, 255, 0)).save(dest, quality=92)
        else:
            im.convert("RGBA").save(dest)
        out.append(dest)
    return out


def write_manifest(folder: Path, name: str, files: list[Path], fps: int = 12, loop: bool = True) -> Path:
    w = h = 0
    if files:
        im = Image.open(files[0])
        w, h = im.size
    data = {
        "name": name,
        "fps": fps,
        "loop": loop,
        "frame_count": len(files),
        "frame_width": w,
        "frame_height": h,
        "frames": [p.name for p in files],
    }
    path = folder / "spriteforge.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def make_zip(folder: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in folder.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(folder))
    return dest


def make_rar(folder: Path, dest: Path) -> Path:
    rar = find_rar()
    if not rar:
        zip_dest = dest.with_suffix(".zip")
        make_zip(folder, zip_dest)
        raise FileNotFoundError(
            f"WinRAR not installed. Wrote a ZIP instead: {zip_dest}"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    subprocess.run(
        [str(rar), "a", "-r", "-ep1", str(dest), str(folder / "*")],
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return dest


def frames_to_mp4(files: list[Path], dest: Path, fps: int = 12) -> Path:
    ff = find_ffmpeg()
    if not ff:
        raise RuntimeError("ffmpeg not found. Install ffmpeg or add it to PATH.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = dest.parent / f"_ff_{dest.stem}"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    write_frames(files, staging, "png")
    pattern = str(staging / "%02d.png")
    cmd = [
        str(ff), "-y", "-framerate", str(fps), "-i", pattern,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        str(dest),
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    shutil.rmtree(staging, ignore_errors=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-400:] if proc.stderr else "ffmpeg failed")
    return dest


def build_pack(
    files: list[Path],
    *,
    name: str,
    kind: str,
    fps: int = 12,
    loop: bool = True,
    dest_root: Path | None = None,
) -> Path:
    ensure_dirs()
    slug = slugify(name) or "sprite"
    stamp = now_stamp()
    root = Path(dest_root) if dest_root else EXPORTS
    root.mkdir(parents=True, exist_ok=True)
    pack = root / f"{slug}_{stamp}"
    if pack.exists():
        shutil.rmtree(pack, ignore_errors=True)
    frames_dir = pack / "Sprites"
    frames = write_frames(files, frames_dir, "jpg" if kind == "jpeg" else "png")
    if kind != "jpeg":
        try:
            compose_sheet(frames, pack / "sheet.png", cols=min(len(frames), 8))
        except Exception:
            pass
    write_manifest(pack, name, frames, fps=fps, loop=loop)

    if kind in {"unity", "unreal", "godot", "sprites", "folder", "zip", "rar"}:
        (pack / "Import_Unity.txt").write_text(UNITY_README, encoding="utf-8")
        (pack / "Import_Unreal.txt").write_text(UNREAL_README, encoding="utf-8")
        (pack / "Import_Godot.txt").write_text(GODOT_README, encoding="utf-8")
        (pack / "README.txt").write_text(GENERIC_README, encoding="utf-8")

    if kind == "png":
        return frames_dir
    if kind == "jpeg":
        return frames_dir
    if kind == "sheet":
        sheet = pack / "sheet.png"
        if not sheet.exists():
            compose_sheet(frames, sheet, cols=min(len(frames), 8))
        return sheet
    if kind == "mp4":
        vid = VIDEOS / f"{slug}_{stamp}.mp4"
        return frames_to_mp4(frames, vid, fps=fps)
    if kind == "zip":
        return make_zip(pack, root / f"{slug}_{stamp}.zip")
    if kind == "rar":
        try:
            return make_rar(pack, root / f"{slug}_{stamp}.rar")
        except FileNotFoundError as exc:
            # still return the zip we wrote
            msg = str(exc)
            z = root / f"{slug}_{stamp}.zip"
            if "Wrote a ZIP" in msg and z.exists():
                return z
            raise
    # unity / unreal / godot / sprites / folder → leave the pack folder
    return pack


def paste_into_project(pack: Path, project_dir: Path) -> Path:
    project_dir = Path(project_dir)
    dest = project_dir / pack.name
    if dest.exists():
        dest = project_dir / f"{pack.name}_{now_stamp()}"
    if pack.is_file():
        dest = project_dir / pack.name
        shutil.copy2(pack, dest)
        return dest
    shutil.copytree(pack, dest)
    return dest
