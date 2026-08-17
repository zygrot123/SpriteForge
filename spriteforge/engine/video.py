from __future__ import annotations

import random
from pathlib import Path

from ..paths import FRAMES, VIDEOS, ensure_dirs
from .assets import slugify, now_stamp
from .export import frames_to_mp4
from .motion import HEIGHT_LOCK, PRESENTATIONS, invent_frames, stabilize_frames
from .prompts import compile_prompt
from .quality import SAME_CHAR, finish_sprite


def animate_to_video(
    client,
    *,
    prompt_text: str,
    ref_path: Path | None,
    identity: str = "",
    style: str = "abyssal_iso",
    view: str = "side",
    bg: str = "green",
    width: int = 768,
    height: int = 1024,
    steps: int = 24,
    guidance: float = 3.5,
    nframes: int = 8,
    fps: int = 12,
    seed: int | None = None,
    dest: Path | None = None,
    presentation: str = "",
) -> tuple[Path, list[Path]]:
    """Local image/text → motion frames → MP4. Uses the sprite identity lock."""
    ensure_dirs()
    seed = seed if seed is not None else random.randint(1, 2**31 - 1)
    pres = PRESENTATIONS.get(presentation) or {}
    plen = pres.get("lock", "")
    vlock = pres.get("video", "")
    if pres.get("view"):
        view = pres["view"]
    poses = invent_frames(prompt_text or "the subject moves in place", nframes)
    folder = FRAMES / f"vid_{now_stamp()}"
    folder.mkdir(parents=True, exist_ok=True)
    last = ref_path
    if last is None:
        still_prompt = compile_prompt(
            prompt_text, style=style, view=view, bg=bg,
            extra="neutral starting pose, still, ready to move",
            presentation=plen,
        )
        if hasattr(client, "mark_item"):
            client.mark_item(1, nframes + 1, f"Base still  1 / {nframes + 1}")
        raws = client.generate(
            still_prompt, seed=seed, steps=steps, width=width, height=height,
            guidance=guidance, prefix="vid_base", dest_dir=folder,
        )
        base = folder / "base.png"
        finish_sprite(raws[0], base, bg=bg, key=True, kind="sprite")
        last = raws[0]
        frames = [base]
    else:
        frames = []
    for i, pose in enumerate(poses):
        if hasattr(client, "mark_item"):
            off = 1 if ref_path is None else 0
            client.mark_item(i + 1 + off, nframes + off, f"Video frame {i + 1} / {nframes}")
        prompt = compile_prompt(
            prompt_text, style=style, view=view, bg=bg, identity=identity,
            pose=f"{SAME_CHAR}, {HEIGHT_LOCK}, {vlock}, animation frame {i+1} of {nframes}: {pose}",
            presentation=plen,
        )
        raws = client.generate(
            prompt, seed=seed + i + 1, steps=steps, width=width, height=height,
            guidance=guidance, ref_path=last, denoise=0.38,
            prefix=f"vid_{i:02d}", dest_dir=folder,
        )
        dest_f = folder / f"{i:02d}.png"
        finish_sprite(raws[0], dest_f, bg=bg, key=True, kind="sprite")
        last = raws[0]
        frames.append(dest_f)
    frames = stabilize_frames(frames, grounded=True)
    dest = dest or (VIDEOS / f"{slugify(prompt_text)[:32]}_{now_stamp()}.mp4")
    return frames_to_mp4(frames, dest, fps=fps), frames
