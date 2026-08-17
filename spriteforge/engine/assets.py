from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw

from ..paths import FRAMES, LIBRARY, MODELS, OUTPUTS, SHEETS, ensure_dirs

SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    s = SLUG_RE.sub("-", (text or "asset").strip().lower()).strip("-")
    return s[:48] or "asset"


def now_stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


@dataclass
class ModelCard:
    id: str
    name: str
    identity: str
    style: str = "abyssal_iso"
    view: str = "isometric"
    bg: str = "green"
    seed: int = 0
    width: int = 768
    height: int = 1024
    refs: dict = field(default_factory=dict)
    created: str = ""
    notes: str = ""

    def folder(self) -> Path:
        return MODELS / self.id

    def save(self) -> Path:
        folder = self.folder()
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "model.json"
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, folder: Path) -> "ModelCard":
        data = json.loads((folder / "model.json").read_text(encoding="utf-8"))
        return _model_from_dict(data)


def _model_from_dict(data: dict) -> ModelCard:
    return ModelCard(
        id=data["id"],
        name=data.get("name", data["id"]),
        identity=data.get("identity", ""),
        style=data.get("style", "abyssal_iso"),
        view=data.get("view", "isometric"),
        bg=data.get("bg", "green"),
        seed=int(data.get("seed") or 0),
        width=int(data.get("width") or 768),
        height=int(data.get("height") or 1024),
        refs=data.get("refs") or {},
        created=data.get("created") or "",
        notes=data.get("notes") or "",
    )


class Library:
    def __init__(self) -> None:
        ensure_dirs()

    def list_models(self) -> list[ModelCard]:
        cards: list[ModelCard] = []
        if not MODELS.exists():
            return cards
        for folder in sorted(MODELS.iterdir()):
            meta = folder / "model.json"
            if folder.is_dir() and meta.exists():
                try:
                    cards.append(_model_from_dict(json.loads(meta.read_text(encoding="utf-8"))))
                except (json.JSONDecodeError, KeyError, OSError):
                    continue
        return cards

    def get(self, model_id: str) -> ModelCard | None:
        meta = MODELS / model_id / "model.json"
        if not meta.exists():
            return None
        return _model_from_dict(json.loads(meta.read_text(encoding="utf-8")))

    def create(
        self,
        name: str,
        identity: str,
        *,
        style: str,
        view: str,
        bg: str,
        seed: int,
        width: int,
        height: int,
        ref_image: Path | None = None,
        ref_role: str = "front",
        notes: str = "",
    ) -> ModelCard:
        mid = f"{slugify(name)}-{uuid.uuid4().hex[:6]}"
        card = ModelCard(
            id=mid,
            name=name.strip() or mid,
            identity=identity.strip(),
            style=style,
            view=view,
            bg=bg,
            seed=int(seed),
            width=int(width),
            height=int(height),
            refs={},
            created=now_stamp(),
            notes=notes,
        )
        card.save()
        if ref_image:
            self.add_ref(card, ref_image, ref_role)
        return card

    def add_ref(self, card: ModelCard, src: Path, role: str) -> Path:
        folder = card.folder()
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / f"{role}{Path(src).suffix.lower() or '.png'}"
        shutil.copyfile(src, dest)
        card.refs[role] = dest.name
        card.save()
        return dest

    def ref_path(self, card: ModelCard, role: str | None = None) -> Path | None:
        if role and card.refs.get(role):
            p = card.folder() / card.refs[role]
            return p if p.exists() else None
        for key in ("front", "isometric", "side", "three_quarter", "back", "base"):
            if card.refs.get(key):
                p = card.folder() / card.refs[key]
                if p.exists():
                    return p
        if card.refs:
            p = card.folder() / next(iter(card.refs.values()))
            if p.exists():
                return p
        return None

    def delete_model(self, model_id: str) -> None:
        folder = MODELS / model_id
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)

    def record_output(self, path: Path, meta: dict) -> Path:
        rec = OUTPUTS / "index.jsonl"
        row = {"file": str(path), "when": now_stamp(), **meta}
        with rec.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        return rec

    def recent_outputs(self, limit: int = 40) -> list[Path]:
        files = [
            p for p in OUTPUTS.rglob("*")
            if p.is_file()
            and p.suffix.lower() in {".png", ".jpg", ".webp"}
            and not p.name.endswith("_lock.png")
        ]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return files[:limit]

    def delete_output(self, path: Path) -> bool:
        path = Path(path)
        if not path.exists():
            return False
        path.unlink()
        return True


def _is_key_color(r: int, g: int, b: int, bg: str, tr: int, tg: int, tb: int, fuzz: int) -> bool:
    dist = abs(r - tr) + abs(g - tg) + abs(b - tb)
    if dist <= fuzz * 3:
        return True
    if bg == "green" and g >= 70 and g - max(r, b) >= 18:
        return True
    if bg == "magenta" and r >= 80 and b >= 80 and min(r, b) - g >= 20:
        return True
    if bg == "cyan" and g >= 80 and b >= 80 and min(g, b) - r >= 20:
        return True
    if bg == "black" and r + g + b < 36:
        return True
    return False


def chroma_key(im: Image.Image, bg: str = "green", fuzz: int = 48) -> Image.Image:
    """Punch out studio backdrop. Edge flood-fill so mint/teal stand-ins for #00FF00 still key."""
    from collections import deque

    rgba = im.convert("RGBA")
    px = rgba.load()
    w, h = rgba.size
    targets = {
        "green": (0, 255, 0),
        "magenta": (255, 0, 255),
        "cyan": (0, 255, 255),
        "black": (0, 0, 0),
        "gray": (128, 128, 128),
    }
    tr, tg, tb = targets.get(bg, targets["green"])
    corners = [px[0, 0][:3], px[w - 1, 0][:3], px[0, h - 1][:3], px[w - 1, h - 1][:3]]
    cr = sum(c[0] for c in corners) // 4
    cg = sum(c[1] for c in corners) // 4
    cb = sum(c[2] for c in corners) // 4

    def match(r: int, g: int, b: int) -> bool:
        if _is_key_color(r, g, b, bg, tr, tg, tb, fuzz):
            return True
        return abs(r - cr) + abs(g - cg) + abs(b - cb) <= fuzz * 3

    seen = bytearray(w * h)
    q: deque[tuple[int, int]] = deque()
    for x in range(w):
        q.append((x, 0))
        q.append((x, h - 1))
    for y in range(h):
        q.append((0, y))
        q.append((w - 1, y))
    while q:
        x, y = q.popleft()
        i = y * w + x
        if seen[i]:
            continue
        seen[i] = 1
        r, g, b, _a = px[x, y]
        if not match(r, g, b):
            continue
        px[x, y] = (r, g, b, 0)
        if x > 0:
            q.append((x - 1, y))
        if x + 1 < w:
            q.append((x + 1, y))
        if y > 0:
            q.append((x, y - 1))
        if y + 1 < h:
            q.append((x, y + 1))
    return rgba


def pixelize(im: Image.Image, logical: int) -> Image.Image:
    w, h = im.size
    if w >= h:
        nw, nh = logical, max(1, int(logical * h / w))
    else:
        nh, nw = logical, max(1, int(logical * w / h))
    small = im.resize((nw, nh), Image.Resampling.NEAREST)
    return small.resize((nw * (w // nw or 1), nh * (h // nh or 1)), Image.Resampling.NEAREST) if False else small.resize(
        (w, h), Image.Resampling.NEAREST
    )


def process_sprite(src: Path, dest: Path, *, bg: str = "green", pixel_size: int | None = None, key: bool = True) -> Path:
    im = Image.open(src)
    if key and bg in {"green", "magenta", "cyan", "black", "gray"}:
        im = chroma_key(im, bg)
    else:
        im = im.convert("RGBA")
    if pixel_size:
        im = pixelize(im, int(pixel_size))
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest)
    return dest


def compose_sheet(frames: list[Path], dest: Path, *, cols: int | None = None, pad: int = 0, cell: tuple[int, int] | None = None) -> Path:
    images = [Image.open(p).convert("RGBA") for p in frames if Path(p).exists()]
    if not images:
        raise ValueError("No frames to compose")
    n = len(images)
    if cols is None:
        cols = n if n <= 8 else min(8, n)
    rows = (n + cols - 1) // cols
    if cell:
        cw, ch = cell
    else:
        cw = max(im.width for im in images)
        ch = max(im.height for im in images)
    sheet = Image.new("RGBA", (cols * cw + pad * (cols + 1), rows * ch + pad * (rows + 1)), (0, 0, 0, 0))
    for i, im in enumerate(images):
        r, c = divmod(i, cols)
        fitted = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        copy = im.copy()
        if copy.width > cw or copy.height > ch:
            copy.thumbnail((cw, ch), Image.Resampling.LANCZOS)
        ox = (cw - copy.width) // 2
        oy = (ch - copy.height) // 2
        fitted.alpha_composite(copy, (ox, oy))
        sheet.alpha_composite(fitted, (pad + c * (cw + pad), pad + r * (ch + pad)))
    dest.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dest)
    return dest


def slice_sheet(src: Path, dest_dir: Path, cols: int, rows: int) -> list[Path]:
    im = Image.open(src).convert("RGBA")
    cw, ch = im.width // cols, im.height // rows
    dest_dir.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for r in range(rows):
        for c in range(cols):
            cell = im.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch))
            path = dest_dir / f"r{r:02d}_c{c:02d}.png"
            cell.save(path)
            out.append(path)
    return out


def draw_grid_preview(src: Path, cols: int, rows: int) -> Image.Image:
    im = Image.open(src).convert("RGBA")
    overlay = im.copy()
    draw = ImageDraw.Draw(overlay)
    cw, ch = im.width / cols, im.height / rows
    for c in range(cols + 1):
        x = int(c * cw)
        draw.line([(x, 0), (x, im.height)], fill=(0, 255, 180, 180), width=2)
    for r in range(rows + 1):
        y = int(r * ch)
        draw.line([(0, y), (im.width, y)], fill=(0, 255, 180, 180), width=2)
    return overlay


def unique_out(folder: Path, name: str, ext: str = ".png") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    base = slugify(name)
    path = folder / f"{base}_{now_stamp()}{ext}"
    n = 2
    while path.exists():
        path = folder / f"{base}_{now_stamp()}_{n}{ext}"
        n += 1
    return path


# keep unused imports honest for callers
_ = (LIBRARY, FRAMES, SHEETS)
