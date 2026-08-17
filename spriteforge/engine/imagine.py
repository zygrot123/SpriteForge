"""Free-style text-to-image / image-to-video: 4 variations, pick one, 4K upscale."""
from __future__ import annotations

import random
import shutil
from pathlib import Path

from PIL import Image, ImageFilter

from ..paths import FRAMES, OUTPUTS, VIDEOS, ensure_dirs
from .assets import unique_out
from .export import frames_to_mp4
from .sampling import snap16

ASPECTS: dict[str, tuple[int, int]] = {
    "1:1": (1024, 1024),
    "16:9": (1280, 720),
    "9:16": (720, 1280),
    "3:2": (1152, 768),
    "2:3": (768, 1152),
    "4:3": (1152, 864),
    "21:9": (1536, 640),
}

FREE_STYLES: dict[str, str] = {
    "Open (free)": "",
    "Cinematic": "cinematic film still, anamorphic, motivated lighting, atmospheric haze",
    "Painterly": "oil-paint concept art, visible brush, rich midtones, gallery finish",
    "Photograph": "photographed, natural light, real materials, shallow depth of field",
    "Anime": "high-end anime film frame, clean color, atmospheric, not a chibi sprite",
    "Dark fantasy": "dark fantasy concept art, ember and cyan light, painterly, no HUD",
}

THINK = (
    "free artistic interpretation of the idea, invent complementary detail that serves it, "
    "cinematic composition, coherent lighting, tactile materials, finished illustration, "
    "not a game sprite sheet, not chroma-key, not isolated on a blank studio backdrop unless asked"
)

VARIANTS = (
    "primary composition, strongest read of the idea",
    "alternate camera and crop, same subject and world",
    "different lighting and time of day, same subject and world",
    "bolder color and atmosphere, same subject and world",
)

UHD_LONG = 3840
FLUX_PIXEL_CAP = 3840 * 2160


def think_prompt(text: str, *, style: str = "Open (free)", think: bool = True, extra: str = "") -> str:
    idea = (text or "").strip()
    parts = [f"The idea to paint: {idea}"]
    if think:
        parts.append(THINK)
    tint = FREE_STYLES.get(style, "")
    if tint:
        parts.append(tint)
    if extra:
        parts.append(extra)
    return ", ".join(parts)


def target_4k(width: int, height: int) -> tuple[int, int]:
    long = max(int(width), int(height), 1)
    scale = UHD_LONG / long
    return snap16(max(64, int(width * scale))), snap16(max(64, int(height * scale)))


def _save_rgb(src: Path, dest: Path, size: tuple[int, int] | None = None) -> Path:
    im = Image.open(src).convert("RGB")
    if size and im.size != size:
        im = im.resize(size, Image.Resampling.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "PNG")
    return dest


def generate_variations(
    client,
    text: str,
    *,
    style: str = "Open (free)",
    think: bool = True,
    width: int = 1024,
    height: int = 1024,
    steps: int = 20,
    guidance: float = 3.5,
    seed: int | None = None,
    count: int = 4,
) -> list[Path]:
    ensure_dirs()
    seed = seed if seed is not None else random.randint(1, 2**31 - 1)
    base = think_prompt(text, style=style, think=think)
    width, height = snap16(width), snap16(height)
    out: list[Path] = []
    for i, hint in enumerate(VARIANTS[: max(1, count)]):
        prompt = f"{base}, variation {i + 1} of {count}: {hint}"
        raws = client.generate(
            prompt,
            seed=int(seed) + i * 9973,
            steps=steps,
            width=width,
            height=height,
            guidance=guidance,
            prefix=f"imagine_v{i + 1}",
            dest_dir=OUTPUTS,
        )
        dest = unique_out(OUTPUTS, f"imagine_v{i + 1}")
        _save_rgb(raws[0], dest)
        try:
            if raws[0].resolve() != dest.resolve():
                raws[0].unlink(missing_ok=True)
        except OSError:
            pass
        out.append(dest)
    return out


def upscale_4k(
    client,
    src: Path,
    *,
    text: str,
    style: str = "Open (free)",
    think: bool = True,
    steps: int = 18,
    guidance: float = 3.5,
    seed: int | None = None,
) -> Path:
    """Creative 4K upscale: Flux detail pass when VRAM allows, always writes 4K."""
    ensure_dirs()
    src = Path(src)
    im = Image.open(src)
    tw, th = target_4k(*im.size)
    seed = seed if seed is not None else random.randint(1, 2**31 - 1)
    prompt = think_prompt(
        text or "the same image, more fine detail",
        style=style,
        think=think,
        extra="ultra-sharp 4K master, recover texture and edges, do not change the subject or composition",
    )
    dest = unique_out(OUTPUTS, "imagine_4k")

    def refine(w: int, h: int, denoise: float) -> Path | None:
        try:
            raws = client.generate(
                prompt,
                seed=seed,
                steps=steps,
                width=w,
                height=h,
                guidance=guidance,
                ref_path=src,
                denoise=denoise,
                prefix="imagine_up",
                dest_dir=OUTPUTS,
                scale_width=w,
                scale_height=h,
            )
            return raws[0]
        except Exception:
            return None

    refined: Path | None = None
    if tw * th <= FLUX_PIXEL_CAP:
        refined = refine(tw, th, 0.28)
    if refined is None:
        mid_scale = min(1.0, 2560 / max(tw, th))
        mw, mh = snap16(int(tw * mid_scale)), snap16(int(th * mid_scale))
        refined = refine(mw, mh, 0.32)

    if refined and refined.exists():
        master = Image.open(refined).convert("RGB")
    else:
        master = im.convert("RGB")
    if master.size != (tw, th):
        master = master.resize((tw, th), Image.Resampling.LANCZOS)
    master = master.filter(ImageFilter.UnsharpMask(radius=1.6, percent=140, threshold=3))
    master.save(dest, "PNG")
    if refined:
        try:
            if refined.resolve() != dest.resolve():
                refined.unlink(missing_ok=True)
        except OSError:
            pass
    return dest


def imagine_video(
    client,
    src: Path,
    *,
    text: str,
    motion: str,
    style: str = "Open (free)",
    think: bool = True,
    nframes: int = 10,
    fps: int = 12,
    steps: int = 16,
    guidance: float = 3.5,
    seed: int | None = None,
    max_long: int = 1280,
) -> Path:
    """Image-to-video that keeps the full picture — no chroma punch-out."""
    ensure_dirs()
    src = Path(src)
    seed = seed if seed is not None else random.randint(1, 2**31 - 1)
    im = Image.open(src).convert("RGB")
    w, h = im.size
    scale = min(1.0, max_long / max(w, h))
    vw, vh = snap16(int(w * scale)), snap16(int(h * scale))
    if vw % 2:
        vw += 1
    if vh % 2:
        vh += 1
    folder = FRAMES / unique_out(FRAMES, "imagine_vid").stem
    folder.mkdir(parents=True, exist_ok=True)
    prompt = think_prompt(
        text,
        style=style,
        think=think,
        extra=(
            f"continuous cinematic shot, same scene and subject, "
            f"motion: {(motion or 'subtle living atmosphere, slow camera push-in').strip()}, "
            "no cut, no new hero, keep composition"
        ),
    )
    frames: list[Path] = []
    first = folder / "00.png"
    im.resize((vw, vh), Image.Resampling.LANCZOS).save(first)
    frames.append(first)
    last = first
    for i in range(1, max(2, nframes)):
        raws = client.generate(
            f"{prompt}, animation frame {i + 1} of {nframes}",
            seed=seed + i,
            steps=steps,
            width=vw,
            height=vh,
            guidance=guidance,
            ref_path=last,
            denoise=0.34,
            prefix=f"imagine_f{i:02d}",
            dest_dir=folder,
        )
        dest = folder / f"{i:02d}.png"
        _save_rgb(raws[0], dest, (vw, vh))
        last = dest
        frames.append(dest)
    dest = unique_out(VIDEOS, "imagine", ext=".mp4")
    return frames_to_mp4(frames, dest, fps=fps)


def copy_pick(src: Path) -> Path:
    dest = unique_out(OUTPUTS, "imagine_pick")
    shutil.copyfile(src, dest)
    return dest
