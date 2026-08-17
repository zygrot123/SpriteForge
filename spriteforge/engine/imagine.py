"""Free-style text-to-image / image-to-video: 4 variations, pick one, 4K upscale."""
from __future__ import annotations

import random
import re
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

EDIT_LOCK = (
    "KEEP THIS PHOTO as the base. The change in the user's words MUST be visible. "
    "If they asked for another sword in the left hand, the left hand holds a second sword. "
    "Do not ignore any part of the request. Do not invent a new character or a new scene."
)

HERO_LOCK = (
    "SAME HERO IN EVERY FRAME. Same face, same eyes, same nose, same jaw, "
    "same hair, same helmet or crown, same armor, same colors, same body. "
    "One person, one continuous shot. Do not redesign. Do not cast a new actor."
)

CHANGE_RE = re.compile(
    r"\b(add|another|extra|second|put|give|hold|holding|wearing|remove|delete|"
    r"change|make it|in his|in her|left hand|right hand|both hands)\b",
    re.I,
)

STRENGTHS: dict[str, float] = {
    "Tiny — keep almost everything": 0.28,
    "Add / tweak — follow my words": 0.52,
    "Restyle — new light and mood": 0.58,
    "Transform — bigger change": 0.70,
}

EDIT_TRIES = (
    "apply the user's words, the change must be clearly visible",
    "same request again, do not skip it, make the change obvious",
    "same request, keep identity, the new object or change is in frame",
    "same request, follow every word, nothing extra",
)

UHD_LONG = 3840
FLUX_PIXEL_CAP = 3840 * 2160

RESOLUTIONS: dict[str, int] = {
    "360p": 360,
    "480p": 480,
    "720p": 720,
    "1080p": 1080,
    "4K": 2160,
}


def think_prompt(
    text: str,
    *,
    style: str = "Open (free)",
    think: bool = True,
    extra: str = "",
    memory: str = "",
    exact: bool = False,
) -> str:
    idea = (text or "").strip()
    if exact:
        parts = [
            f"Follow these words exactly, do not add a different story: {idea}",
            f"Required: {idea}",
        ]
        if extra:
            parts.append(extra)
        return ", ".join(parts)
    if think:
        from .brain import understand

        idea = understand(idea, fluid=True).visual()
    parts = [f"The idea to paint: {idea}"]
    if think:
        parts.append(THINK)
    tint = FREE_STYLES.get(style, "")
    if tint:
        parts.append(tint)
    if memory:
        parts.append(f"Stay consistent with this user's evolving memory: {memory}")
    if extra:
        parts.append(extra)
    return ", ".join(parts)


def aspect_size(aspect: str, preset: str) -> tuple[int, int]:
    aw, ah = ASPECTS.get(aspect, (1280, 720))
    th = int(RESOLUTIONS.get(preset, 720))
    tw = max(2, int(round(aw * (th / ah))))
    if tw % 2:
        tw += 1
    if th % 2:
        th += 1
    long = max(tw, th)
    if long > 3840:
        s = 3840 / long
        tw, th = int(tw * s) // 2 * 2, int(th * s) // 2 * 2
    return tw, th


def work_size(aspect: str, preset: str) -> tuple[int, int, int, int]:
    """Flux work canvas + final output canvas (aspect + 360/480/720/1080/4K)."""
    fw, fh = aspect_size(aspect, preset)
    long = max(fw, fh)
    if long > 1280:
        s = 1280 / long
        ww, wh = max(64, int(fw * s) // 2 * 2), max(64, int(fh * s) // 2 * 2)
    else:
        ww, wh = fw, fh
    return snap16(ww), snap16(wh), fw, fh


def fit_to_canvas(src: Path, width: int, height: int) -> Path:
    """Center-crop the photo onto the chosen aspect, then scale."""
    im = Image.open(src).convert("RGB")
    sw, sh = im.size
    src_r = sw / max(sh, 1)
    dst_r = width / max(height, 1)
    if src_r > dst_r:
        nw = max(1, int(sh * dst_r))
        x = (sw - nw) // 2
        im = im.crop((x, 0, x + nw, sh))
    else:
        nh = max(1, int(sw / dst_r))
        y = (sh - nh) // 2
        im = im.crop((0, y, sw, y + nh))
    im = im.resize((width, height), Image.Resampling.LANCZOS)
    dest = unique_out(OUTPUTS, "canvas")
    im.save(dest, "PNG")
    return dest


def effective_denoise(text: str, denoise: float) -> float:
    if CHANGE_RE.search(text or "") and denoise < 0.5:
        return 0.55
    return float(denoise)


def target_4k(width: int, height: int) -> tuple[int, int]:
    return target_res(width, height, "4K")


def target_res(width: int, height: int, preset: str = "1080p") -> tuple[int, int]:
    """Fit the image so its height matches 360/480/720/1080/4K, keep aspect."""
    h0 = max(int(height), 1)
    w0 = max(int(width), 1)
    want = int(RESOLUTIONS.get(preset, 1080))
    th = want if want % 2 == 0 else want + 1
    tw = max(2, int(round(w0 * (th / h0))))
    if tw % 2:
        tw += 1
    return tw, th


def _save_rgb(src: Path, dest: Path, size: tuple[int, int] | None = None) -> Path:
    im = Image.open(src).convert("RGB")
    if size and im.size != size:
        im = im.resize(size, Image.Resampling.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "PNG")
    return dest


def fit_size(src: Path, max_long: int = 1280) -> tuple[int, int]:
    im = Image.open(src)
    w, h = im.size
    scale = min(1.0, max_long / max(w, h, 1))
    return snap16(max(64, int(w * scale))), snap16(max(64, int(h * scale)))


def import_local(src: Path) -> Path:
    """Copy a PC image into the library so the app can edit or animate it."""
    ensure_dirs()
    src = Path(src)
    dest = unique_out(OUTPUTS, f"import_{src.stem}")
    im = Image.open(src).convert("RGB")
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
    memory: str = "",
    ref_path: Path | str | None = None,
    denoise: float = 0.38,
    aspect: str = "",
    preset: str = "",
    exact: bool = False,
) -> list[Path]:
    ensure_dirs()
    seed = seed if seed is not None else random.randint(1, 2**31 - 1)
    exact = bool(exact or not think)
    extra = EDIT_LOCK if ref_path else ""
    base = think_prompt(
        text, style=style, think=think and not exact, memory="" if exact else memory,
        extra=extra, exact=exact,
    )
    ref = Path(ref_path) if ref_path else None
    final_w = final_h = 0
    if aspect and preset:
        width, height, final_w, final_h = work_size(aspect, preset)
    elif ref and ref.exists():
        width, height = fit_size(ref)
    width, height = snap16(width), snap16(height)
    if ref and ref.exists() and aspect:
        ref = fit_to_canvas(ref, width, height)
    denoise = effective_denoise(text, denoise) if ref else 1.0
    if exact:
        guidance = max(float(guidance), 4.5)
        steps = max(int(steps), 24)
    hints = EDIT_TRIES if ref else VARIANTS
    out: list[Path] = []
    for i, hint in enumerate(hints[: max(1, count)]):
        if exact:
            prompt = f"{base}. Attempt {i + 1} of {count}: {hint}. Words again: {text}"
        else:
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
            ref_path=ref if ref and ref.exists() else None,
            denoise=float(denoise),
            scale_width=width if ref else None,
            scale_height=height if ref else None,
        )
        dest = unique_out(OUTPUTS, f"imagine_v{i + 1}")
        _save_rgb(raws[0], dest, (final_w, final_h) if final_w and final_h else None)
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
    return upscale_image(client, src, preset="4K", text=text, style=style, think=think, steps=steps, guidance=guidance, seed=seed)


def upscale_image(
    client,
    src: Path,
    *,
    preset: str = "1080p",
    text: str = "",
    style: str = "Open (free)",
    think: bool = True,
    steps: int = 18,
    guidance: float = 3.5,
    seed: int | None = None,
) -> Path:
    """Scale a still to 360p / 480p / 720p / 1080p / 4K. Flux refine when enlarging."""
    ensure_dirs()
    src = Path(src)
    im = Image.open(src)
    tw, th = target_res(*im.size, preset)
    enlarging = tw * th > im.size[0] * im.size[1] * 1.05
    seed = seed if seed is not None else random.randint(1, 2**31 - 1)
    prompt = think_prompt(
        text or "the same image, more fine detail",
        style=style,
        think=think,
        extra=f"clean {preset} master, recover texture and edges, do not change the subject or composition",
        memory="",
    )
    dest = unique_out(OUTPUTS, f"imagine_{preset.replace(' ', '')}")

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
    if enlarging and tw * th <= FLUX_PIXEL_CAP:
        refined = refine(tw, th, 0.28 if preset in {"1080p", "4K"} else 0.22)
    if enlarging and refined is None and preset == "4K":
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


def video_frame_plan(duration: float) -> tuple[int, float]:
    """Unique Flux frames + fps so the clip lasts `duration` seconds."""
    seconds = min(10.0, max(2.0, float(duration)))
    nframes = min(24, max(8, int(round(seconds * 6))))
    fps = max(2.0, nframes / seconds)
    return nframes, fps


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
    out_height: int | None = None,
    duration: float | None = None,
) -> Path:
    """Animate one still. Every frame img2img's the original hero so the face does not swap."""
    ensure_dirs()
    src = Path(src)
    if duration:
        nframes, fps = video_frame_plan(duration)
    nframes = max(2, int(nframes))
    seed = seed if seed is not None else random.randint(1, 2**31 - 1)
    im = Image.open(src).convert("RGB")
    w, h = im.size
    if out_height:
        work_h = min(int(out_height), 720)
        scale = work_h / max(h, 1)
    else:
        scale = min(1.0, max_long / max(w, h))
    vw, vh = snap16(int(w * scale)), snap16(int(h * scale))
    if vw % 2:
        vw += 1
    if vh % 2:
        vh += 1
    folder = FRAMES / unique_out(FRAMES, "imagine_vid").stem
    folder.mkdir(parents=True, exist_ok=True)
    desire = (motion or "").strip() or (text or "").strip() or "subtle living atmosphere, slow camera push-in"
    hero = folder / "hero.png"
    im.resize((vw, vh), Image.Resampling.LANCZOS).save(hero)
    frames: list[Path] = [hero]
    for i in range(1, nframes):
        t = i / max(nframes - 1, 1)
        prompt = think_prompt(
            text or "this same image, now moving",
            style=style,
            think=False,
            exact=True,
            extra=(
                f"{HERO_LOCK} Motion only: {desire}. "
                f"Progress {int(t * 100)} percent through that motion. "
                "Do not change the face or costume. Camera and cloth may move slightly."
            ),
        )
        raws = client.generate(
            prompt,
            seed=seed,
            steps=max(14, int(steps)),
            width=vw,
            height=vh,
            guidance=max(float(guidance), 4.0),
            ref_path=hero,
            denoise=0.18 + 0.06 * t,
            prefix=f"imagine_f{i:02d}",
            dest_dir=folder,
            scale_width=vw,
            scale_height=vh,
        )
        dest = folder / f"{i:02d}.png"
        _save_rgb(raws[0], dest, (vw, vh))
        frames.append(dest)
    dest = unique_out(VIDEOS, "imagine", ext=".mp4")
    frames_to_mp4(frames, dest, fps=max(1, int(round(fps))))
    if out_height and abs(int(out_height) - vh) > 4:
        scaled = dest.with_name(dest.stem + f"_{int(out_height)}p.mp4")
        dest = scale_video(dest, scaled, int(out_height))
    return dest


def scale_video(src: Path, dest: Path, height: int) -> Path:
    """ffmpeg scale existing video to 360/480/720/1080/2160 tall."""
    from .export import find_ffmpeg

    ff = find_ffmpeg()
    if not ff:
        raise RuntimeError("ffmpeg not found. Open Setup and install video tools.")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    h = max(2, int(height) // 2 * 2)
    cmd = [
        str(ff), "-y", "-i", str(src),
        "-vf", f"scale=-2:{h}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(dest),
    ]
    import subprocess

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not dest.exists():
        raise RuntimeError((proc.stderr or "ffmpeg scale failed")[-400:])
    return dest


def copy_pick(src: Path) -> Path:
    dest = unique_out(OUTPUTS, "imagine_pick")
    shutil.copyfile(src, dest)
    return dest
