from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageFilter, ImageStat

from .assets import _is_key_color, chroma_key, pixelize, unique_out
from .prompts import compile_prompt

QUALITY_EXTRA = (
    "masterpiece game-production still, crisp readable silhouette, coherent anatomy, "
    "hands with five fingers if visible, held items firmly gripped, "
    "head and both feet fully inside the frame, generous empty margin on every side, "
    "single clean light direction, no second character, no crowd, no set dressing, "
    "no floating debris, no ground disk, no drop shadow blob"
)

REFINE_LOCK = (
    "KEEP THIS EXACT SUBJECT AND POSE. Production cleanup only: "
    "flatten the background to a perfectly even chroma-key lime green #00FF00, "
    "remove ground plane and cast shadow, sharpen armor and cloth edges, "
    "fix extra limbs or melted hands, keep the full body inside the frame "
    "with air around the silhouette, do not redesign, do not change costume or colors"
)

SAME_CHAR = (
    "KEEP THIS EXACT CHARACTER. Same face, same helmet, same horns or crown, "
    "same armor shape and colors, same cape, same weapons, same body proportions. "
    "This is the same person, not a new design, not a palette swap, not a cousin. "
    "Do not invent new gear. Tiny pose or lighting change only if the prompt asks."
)

MODES = {
    "fast": {
        "label": "Fast — 1 pass",
        "candidates": 1,
        "refine": False,
        "retry": False,
        "steps_boost": 0,
        "min_score": 0,
        "denoise": 0.30,
    },
    "quality": {
        "label": "Quality — best of 2 + refine",
        "candidates": 2,
        "refine": True,
        "retry": False,
        "steps_boost": 4,
        "min_score": 55,
        "denoise": 0.28,
    },
    "studio": {
        "label": "Studio — best of 3 + refine + retry",
        "candidates": 3,
        "refine": True,
        "retry": True,
        "steps_boost": 8,
        "min_score": 64,
        "denoise": 0.26,
    },
}


def mode_labels() -> list[str]:
    return [v["label"] for v in MODES.values()]


def mode_key(label: str) -> str:
    for k, v in MODES.items():
        if v["label"] == label:
            return k
    return "quality"


@dataclass
class Score:
    total: float
    isolation: float
    keyability: float
    padding: float
    occupancy: float
    sharpness: float
    notes: list[str]

    def as_dict(self) -> dict:
        return {
            "total": round(self.total, 1),
            "isolation": round(self.isolation, 1),
            "keyability": round(self.keyability, 1),
            "padding": round(self.padding, 1),
            "occupancy": round(self.occupancy, 1),
            "sharpness": round(self.sharpness, 1),
            "notes": self.notes,
        }


def _bg_match(r: int, g: int, b: int, bg: str) -> bool:
    targets = {
        "green": (0, 255, 0),
        "magenta": (255, 0, 255),
        "cyan": (0, 255, 255),
        "black": (0, 0, 0),
        "gray": (128, 128, 128),
    }
    tr, tg, tb = targets.get(bg, targets["green"])
    return _is_key_color(r, g, b, bg, tr, tg, tb, 48)


def score_image(path: Path, bg: str = "green", kind: str = "sprite") -> Score:
    im = Image.open(path).convert("RGB")
    small = im.resize((160, 160), Image.Resampling.BILINEAR)
    w, h = small.size
    px = small.load()
    notes: list[str] = []

    corners = [px[1, 1], px[w - 2, 1], px[1, h - 2], px[w - 2, h - 2]]
    cr = sum(c[0] for c in corners) / 4
    cg = sum(c[1] for c in corners) / 4
    cb = sum(c[2] for c in corners) / 4
    spread = sum(abs(c[0] - cr) + abs(c[1] - cg) + abs(c[2] - cb) for c in corners) / 4
    isolation = max(0.0, 25.0 - spread / 8.0)
    if spread > 80:
        notes.append("uneven backdrop")

    key_hits = sum(1 for c in corners if _bg_match(*c[:3], bg))
    keyability = (key_hits / 4.0) * 20.0
    if key_hits < 3:
        notes.append("backdrop not keyable")

    mask = []
    ink = 0
    minx, miny, maxx, maxy = w, h, 0, 0
    for y in range(h):
        row = []
        for x in range(w):
            r, g, b = px[x, y]
            subject = not _bg_match(r, g, b, bg)
            row.append(subject)
            if subject:
                ink += 1
                if x < minx:
                    minx = x
                if y < miny:
                    miny = y
                if x > maxx:
                    maxx = x
                if y > maxy:
                    maxy = y
        mask.append(row)
    occ = ink / float(w * h) if w * h else 0.0
    if kind == "tile":
        occupancy = 15.0
    else:
        lo, hi = (0.22, 0.62) if kind == "sprite" else (0.28, 0.78)
        if occ < 0.06:
            occupancy = 2.0
            notes.append("almost empty")
        elif occ > 0.92:
            occupancy = 3.0
            notes.append("fills the whole frame")
        elif lo <= occ <= hi:
            occupancy = 15.0
        else:
            occupancy = 9.0
            notes.append("subject scale off")

    if ink < 20:
        padding = 0.0
        notes.append("no readable subject")
    else:
        pad_l, pad_t, pad_r, pad_b = minx, miny, (w - 1 - maxx), (h - 1 - maxy)
        min_pad = min(pad_l, pad_t, pad_r, pad_b)
        padding = min(20.0, min_pad * 2.2)
        if min_pad < 4:
            notes.append("cropped against the edge")
            padding *= 0.4

    edges = small.filter(ImageFilter.FIND_EDGES)
    sharp_mean = float(ImageStat.Stat(edges.convert("L")).mean[0])
    sharpness = max(0.0, min(10.0, (sharp_mean - 8.0) / 4.0))
    if sharp_mean < 10:
        notes.append("soft / muddy")

    total = isolation + keyability + padding + occupancy + sharpness
    return Score(total, isolation, keyability, padding, occupancy, sharpness, notes)


def finish_sprite(
    src: Path,
    dest: Path,
    *,
    bg: str = "green",
    pixel_size: int | None = None,
    key: bool = True,
    kind: str = "sprite",
) -> Path:
    im = Image.open(src).convert("RGBA")
    if key and kind != "tile" and bg in {"green", "magenta", "cyan", "black", "gray"}:
        im = chroma_key(im, bg)
    if kind != "tile":
        im = _recenter(im)
        im = im.filter(ImageFilter.UnsharpMask(radius=1.4, percent=130, threshold=3))
    if pixel_size:
        im = pixelize(im, int(pixel_size))
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest)
    return dest


def _recenter(im: Image.Image, pad_ratio: float = 0.10) -> Image.Image:
    alpha = im.split()[-1]
    bbox = alpha.getbbox()
    if not bbox:
        return im
    x0, y0, x1, y1 = bbox
    crop = im.crop((x0, y0, x1, y1))
    cw, ch = crop.size
    canvas_w, canvas_h = im.size
    pad = int(max(canvas_w, canvas_h) * pad_ratio)
    max_w = max(8, canvas_w - 2 * pad)
    max_h = max(8, canvas_h - 2 * pad)
    if cw > max_w or ch > max_h:
        scale = min(max_w / cw, max_h / ch)
        crop = crop.resize((max(1, int(cw * scale)), max(1, int(ch * scale))), Image.Resampling.LANCZOS)
        cw, ch = crop.size
    out = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    ox = (canvas_w - cw) // 2
    oy = (canvas_h - ch) // 2
    out.alpha_composite(crop, (ox, oy))
    return out


ENV_KINDS = {"tile", "plate", "scene"}
ENV_REFINE = (
    "KEEP THIS EXACT SCENE. Cleanup only: sharper forms, cleaner color, "
    "do not add a character, person, silhouette, hero, or extra objects. "
    "Do not invent ground if the prompt said no ground."
)


def enhance_prompt(prompt: str, mode: str, kind: str = "sprite") -> str:
    if mode == "fast" or kind in ENV_KINDS:
        return prompt
    return f"{prompt}, {QUALITY_EXTRA}"


def generate_quality(
    client,
    prompt: str,
    *,
    mode: str = "quality",
    engine: str = "flux",
    seed: int,
    steps: int,
    width: int,
    height: int,
    guidance: float,
    bg: str = "green",
    kind: str = "sprite",
    pixel_size: int | None = None,
    key: bool = True,
    negative: str = "",
    prefix: str = "sprite",
    dest_dir: Path,
    name: str = "sprite",
    ref_path: Path | str | None = None,
    lock_denoise: float = 0.30,
    sampler_name: str = "euler",
    scheduler: str = "simple",
    batch_size: int = 1,
    hires_fix: bool = False,
    hires_scale: float = 2.0,
    hires_denoise: float = 0.45,
    refiner: bool = False,
) -> tuple[Path, dict]:
    spec = MODES.get(mode, MODES["quality"])
    env = kind in ENV_KINDS
    steps = int(steps) if env else int(steps) + int(spec["steps_boost"])
    work_prompt = enhance_prompt(prompt, mode, kind)
    cands = spec["candidates"]
    ref = Path(ref_path) if ref_path else None
    if ref and not ref.exists():
        ref = None
    if ref or env:
        cands = 1
        spec = {**spec, "retry": False, "refine": bool(refiner) if env else spec["refine"]}
        if ref and not env:
            work_prompt = f"{SAME_CHAR}, {work_prompt}"
    elif refiner:
        spec = {**spec, "refine": True}

    scored: list[tuple[float, Score, Path]] = []
    trash: list[Path] = []
    for i in range(cands):
        raws = client.generate(
            work_prompt,
            engine=engine,
            seed=int(seed) + i * 9973,
            steps=steps,
            width=width,
            height=height,
            guidance=guidance,
            negative=negative,
            ref_path=ref,
            denoise=float(lock_denoise) if ref else 1.0,
            prefix=f"{prefix}_c{i}",
            dest_dir=dest_dir,
            sampler_name=sampler_name,
            scheduler=scheduler,
            batch_size=batch_size,
            hires_fix=hires_fix,
            hires_scale=hires_scale,
            hires_denoise=hires_denoise,
            cfg=guidance,
        )
        path = raws[0]
        s = score_image(path, bg=bg, kind=kind)
        scored.append((s.total, s, path))

    scored.sort(key=lambda t: t[0], reverse=True)
    best_total, best_score, best_path = scored[0]
    for _t, _s, p in scored[1:]:
        trash.append(p)

    if spec["retry"] and best_total < spec["min_score"]:
        retry_prompt = f"{work_prompt}, pull the camera back, full subject visible, flatter solid #00FF00 studio backdrop"
        raws = client.generate(
            retry_prompt,
            engine=engine,
            seed=int(seed) + 424242,
            steps=steps,
            width=width,
            height=height,
            guidance=guidance,
            negative=negative,
            prefix=f"{prefix}_retry",
            dest_dir=dest_dir,
            sampler_name=sampler_name,
            scheduler=scheduler,
            cfg=guidance,
        )
        s = score_image(raws[0], bg=bg, kind=kind)
        if s.total > best_total:
            trash.append(best_path)
            best_total, best_score, best_path = s.total, s, raws[0]
        else:
            trash.append(raws[0])

    refined = False
    if spec["refine"]:
        refine_prompt = f"{ENV_REFINE}, {prompt}" if env else f"{REFINE_LOCK}, {prompt}"
        raws = client.generate(
            refine_prompt,
            engine="flux",
            seed=int(seed) + 17,
            steps=max(16, steps - 6),
            width=width,
            height=height,
            guidance=guidance,
            ref_path=best_path,
            denoise=float(spec["denoise"]),
            prefix=f"{prefix}_ref",
            dest_dir=dest_dir,
            sampler_name=sampler_name,
            scheduler=scheduler,
        )
        s = score_image(raws[0], bg=bg, kind=kind)
        if s.total >= best_total - 4:
            trash.append(best_path)
            best_total, best_score, best_path = s.total, s, raws[0]
            refined = True
        else:
            trash.append(raws[0])

    dest = unique_out(dest_dir, name)
    lock_path = dest.with_name(dest.stem + "_lock.png")
    try:
        shutil.copyfile(best_path, lock_path)
    except OSError:
        lock_path = best_path
    finish_kind = "tile" if env else kind
    finish_sprite(best_path, dest, bg=bg, pixel_size=pixel_size, key=key and not env, kind=finish_kind)
    if best_path.resolve() != dest.resolve() and best_path.resolve() != Path(lock_path).resolve():
        trash.append(best_path)
    for p in trash:
        try:
            if p.exists() and p.resolve() != dest.resolve():
                p.unlink()
        except OSError:
            pass
    meta = best_score.as_dict()
    meta["mode"] = mode
    meta["refined"] = refined
    meta["candidates"] = cands
    meta["lock_path"] = str(lock_path)
    meta["same_character"] = bool(ref)
    return dest, meta


# keep compile_prompt imported for callers that want one-stop quality prompts
_ = compile_prompt
