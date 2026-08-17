"""Local dungeon / floor builder — Seeing Eyes style, no cloud.

Tiles have edge sockets. Generate fills the grid with wave-function collapse.
Paint a piece, rotate it, auto-solve the neighbors so openings still meet.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..paths import MAPS, OUTPUTS, ensure_dirs
from .assets import unique_out

# Edge sockets. Same letter connects to the same letter.
F, W, A, C, V = "F", "W", "A", "C", "V"

N, E, S, WEST = 0, 1, 2, 3
DELTA = ((0, -1, N, S), (1, 0, E, WEST), (0, 1, S, N), (-1, 0, WEST, E))


@dataclass(frozen=True)
class TileKind:
    id: str
    label: str
    sockets: tuple[str, str, str, str]
    weight: float = 1.0
    turns: int = 4
    paint: str = ""
    fill: tuple[int, int, int] = (86, 92, 104)
    ink: tuple[int, int, int] = (38, 42, 52)
    prompt: str = ""


KINDS: list[TileKind] = [
    TileKind("floor", "Floor", (F, F, F, F), 6.0, 1, "floor", (98, 104, 116), (48, 52, 62),
             "open isometric dungeon floor tile, walkable flagstones, no walls, modular kit piece"),
    TileKind("hall", "Hall", (F, W, F, W), 3.5, 2, "hall", (90, 96, 108), (34, 36, 46),
             "isometric dungeon corridor tile, OPEN north and south, SOLID walls east and west"),
    TileKind("corner", "Corner", (F, F, W, W), 2.4, 4, "corner", (88, 94, 106), (34, 36, 46),
             "isometric dungeon L-corner, OPEN north and east, SOLID walls south and west"),
    TileKind("tee", "T-junction", (F, F, F, W), 1.6, 4, "tee", (92, 98, 110), (34, 36, 46),
             "isometric dungeon T-junction, OPEN north east south, SOLID wall west"),
    TileKind("cross", "Cross", (F, F, F, F), 1.2, 1, "cross", (94, 100, 112), (40, 44, 54),
             "isometric dungeon four-way crossing, openings all four sides, pillar corners"),
    TileKind("dead", "Dead end", (F, W, W, W), 1.0, 4, "dead", (84, 88, 98), (30, 32, 40),
             "isometric dungeon dead-end, OPEN only to the north, three solid walls"),
    TileKind("solid", "Solid wall", (W, W, W, W), 0.8, 1, "solid", (58, 60, 70), (22, 24, 30),
             "isometric solid dungeon wall block, no doorway, closed on all sides"),
    TileKind("door", "Door hall", (F, W, F, W), 1.1, 2, "door", (96, 90, 78), (40, 32, 24),
             "isometric dungeon corridor with a wooden door on the run, open north and south"),
    TileKind("water", "Water", (A, A, A, A), 1.4, 1, "water", (36, 78, 104), (16, 36, 52),
             "isometric dungeon canal / water tile, water on all four edges, stone rim"),
    TileKind("shore", "Shore", (F, W, A, W), 1.0, 4, "shore", (50, 86, 102), (24, 40, 50),
             "isometric shore tile, FLOOR north, WATER south, stone walls east and west"),
    TileKind("cave", "Cave", (C, C, C, C), 1.3, 1, "cave", (78, 62, 52), (36, 26, 20),
             "isometric organic cave floor, rough rock, openings all sides, same kit lighting"),
    TileKind("mouth", "Cave mouth", (C, W, F, W), 0.9, 4, "mouth", (82, 68, 56), (36, 26, 20),
             "isometric cave mouth, CAVE north, FLOOR south, rock walls east and west"),
    TileKind("stair", "Stairs", (F, W, F, W), 0.8, 2, "stair", (110, 100, 84), (48, 40, 28),
             "isometric dungeon stair tile, steps running north-south, walls east and west"),
    TileKind("grave", "Graveyard", (F, F, F, F), 0.6, 1, "grave", (72, 78, 70), (32, 36, 30),
             "isometric graveyard floor tile, a few stone markers, walkable, open all sides"),
    TileKind("terrace", "Terrace", (F, F, W, W), 0.7, 4, "terrace", (86, 92, 74), (40, 44, 32),
             "isometric outdoor terrace tile, open north and east, retaining wall south and west"),
    TileKind("void", "Empty", (V, V, V, V), 0.2, 1, "erase", (18, 20, 26), (10, 12, 16),
             "empty void, no architecture"),
]

KIND = {k.id: k for k in KINDS}
PAINT_TOOLS = [
    "off", "erase", "floor", "hall", "corner", "tee", "cross", "dead",
    "solid", "door", "water", "shore", "cave", "mouth", "stair", "grave", "terrace",
    "torch", "perturb",
]


@dataclass
class Oriented:
    kind: str
    rot: int
    sockets: tuple[str, str, str, str]
    weight: float
    label: str


def rotate_socks(socks: tuple[str, str, str, str], rot: int) -> tuple[str, str, str, str]:
    r = int(rot) % 4
    s = list(socks)
    for _ in range(r):
        s = [s[WEST], s[N], s[E], s[S]]
    return (s[0], s[1], s[2], s[3])


def catalog() -> list[Oriented]:
    out: list[Oriented] = []
    for kind in KINDS:
        if kind.id == "void":
            continue
        seen: set[tuple[str, str, str, str]] = set()
        for rot in range(kind.turns):
            socks = rotate_socks(kind.sockets, rot)
            if socks in seen:
                continue
            seen.add(socks)
            out.append(Oriented(kind.id, rot, socks, kind.weight, kind.label))
    return out


CATALOG = catalog()
INDEX = {(o.kind, o.rot): i for i, o in enumerate(CATALOG)}


def _match(a: str, b: str) -> bool:
    return a == b


@dataclass
class Cell:
    kind: str = "void"
    rot: int = 0
    pin: bool = False
    torch: bool = False

    def key(self) -> tuple[str, int]:
        return self.kind, self.rot

    def clone(self) -> "Cell":
        return Cell(self.kind, self.rot, self.pin, self.torch)


@dataclass
class Grid:
    w: int
    h: int
    cells: list[list[Cell]] = field(default_factory=list)
    seed: int = 0
    theme: str = ""
    kit: dict[str, str] = field(default_factory=dict)
    backdrop: str = ""

    def __post_init__(self) -> None:
        if not self.cells:
            self.cells = [[Cell() for _ in range(self.w)] for _ in range(self.h)]

    def get(self, x: int, y: int) -> Cell | None:
        if 0 <= x < self.w and 0 <= y < self.h:
            return self.cells[y][x]
        return None

    def snapshot(self) -> "Grid":
        return Grid(
            self.w, self.h,
            [[c.clone() for c in row] for row in self.cells],
            seed=self.seed, theme=self.theme, kit=dict(self.kit),
            backdrop=self.backdrop,
        )

    def to_dict(self) -> dict:
        return {
            "w": self.w, "h": self.h, "seed": self.seed, "theme": self.theme,
            "kit": self.kit, "backdrop": self.backdrop,
            "cells": [
                [{"k": c.kind, "r": c.rot, "p": c.pin, "t": c.torch} for c in row]
                for row in self.cells
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Grid":
        w, h = int(data["w"]), int(data["h"])
        g = cls(
            w, h, seed=int(data.get("seed") or 0), theme=data.get("theme") or "",
            kit=data.get("kit") or {}, backdrop=str(data.get("backdrop") or ""),
        )
        rows = data.get("cells") or []
        for y, row in enumerate(rows[:h]):
            for x, raw in enumerate(row[:w]):
                g.cells[y][x] = Cell(
                    str(raw.get("k") or "void"),
                    int(raw.get("r") or 0),
                    bool(raw.get("p")),
                    bool(raw.get("t")),
                )
        return g


class Contradiction(RuntimeError):
    pass


def _options_for(grid: Grid) -> list[list[set[int]]]:
    all_idx = set(range(len(CATALOG)))
    opts: list[list[set[int]]] = [[set(all_idx) for _ in range(grid.w)] for _ in range(grid.h)]
    for y in range(grid.h):
        for x in range(grid.w):
            cell = grid.cells[y][x]
            if cell.pin or (cell.kind != "void" and cell.pin):
                idx = INDEX.get((cell.kind, cell.rot % 4))
                if idx is None:
                    idx = INDEX.get((cell.kind, 0))
                if idx is not None:
                    opts[y][x] = {idx}
    return opts


def _pin_opts(grid: Grid) -> list[list[set[int]]]:
    all_idx = set(range(len(CATALOG)))
    opts: list[list[set[int]]] = [[set(all_idx) for _ in range(grid.w)] for _ in range(grid.h)]
    for y in range(grid.h):
        for x in range(grid.w):
            cell = grid.cells[y][x]
            if not cell.pin:
                continue
            idx = INDEX.get((cell.kind, cell.rot % 4))
            if idx is None:
                idx = INDEX.get((cell.kind, 0))
            opts[y][x] = {idx} if idx is not None else set()
    return opts


def _propagate(opts: list[list[set[int]]], w: int, h: int) -> None:
    stack = [(x, y) for y in range(h) for x in range(w) if len(opts[y][x]) <= 1]
    while stack:
        x, y = stack.pop()
        here = opts[y][x]
        if not here:
            raise Contradiction(f"empty at {x},{y}")
        for dx, dy, mine, theirs in DELTA:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            before = opts[ny][nx]
            keep = {
                j for j in before
                if any(_match(CATALOG[i].sockets[mine], CATALOG[j].sockets[theirs]) for i in here)
            }
            if len(keep) == len(before):
                continue
            if not keep:
                raise Contradiction(f"neighbor {nx},{ny}")
            opts[ny][nx] = keep
            stack.append((nx, ny))


def _lowest(opts: list[list[set[int]]], rng: random.Random) -> tuple[int, int] | None:
    best: list[tuple[int, int]] = []
    best_n = 10**9
    for y, row in enumerate(opts):
        for x, s in enumerate(row):
            n = len(s)
            if n <= 1:
                continue
            if n < best_n:
                best_n = n
                best = [(x, y)]
            elif n == best_n:
                best.append((x, y))
    if not best:
        return None
    return rng.choice(best)


def _pick(idxs: set[int], rng: random.Random) -> int:
    bag = list(idxs)
    weights = [max(0.05, CATALOG[i].weight) for i in bag]
    return rng.choices(bag, weights=weights, k=1)[0]


def _commit(grid: Grid, opts: list[list[set[int]]]) -> None:
    for y in range(grid.h):
        for x in range(grid.w):
            cell = grid.cells[y][x]
            if cell.pin:
                continue
            s = opts[y][x]
            if not s:
                cell.kind, cell.rot = "void", 0
                continue
            i = next(iter(s)) if len(s) == 1 else _pick(s, random.Random(x * 97 + y))
            o = CATALOG[i]
            cell.kind, cell.rot = o.kind, o.rot


def solve(grid: Grid, *, seed: int | None = None, attempts: int = 36) -> Grid:
    """Collapse unpinned cells so every edge matches. Pins stay."""
    rng = random.Random(seed if seed is not None else grid.seed or random.randint(1, 2**31 - 1))
    last_err = "unsolved"
    for _ in range(max(1, attempts)):
        try:
            opts = _pin_opts(grid)
            _propagate(opts, grid.w, grid.h)
            while True:
                spot = _lowest(opts, rng)
                if spot is None:
                    break
                x, y = spot
                choice = _pick(opts[y][x], rng)
                opts[y][x] = {choice}
                _propagate(opts, grid.w, grid.h)
            _commit(grid, opts)
            return grid
        except Contradiction as exc:
            last_err = str(exc)
            continue
    raise Contradiction(f"Could not solve the floor ({last_err}). Erase a pin or Generate again.")


def solve_steps(grid: Grid, *, seed: int | None = None, attempts: int = 24) -> list[Grid]:
    """Same as solve, but a snapshot after every collapse (animate build)."""
    rng = random.Random(seed if seed is not None else grid.seed or random.randint(1, 2**31 - 1))
    last_err = "unsolved"
    for _ in range(max(1, attempts)):
        frames: list[Grid] = []
        try:
            opts = _pin_opts(grid)
            _propagate(opts, grid.w, grid.h)
            work = grid.snapshot()
            _commit(work, opts)
            frames.append(work.snapshot())
            while True:
                spot = _lowest(opts, rng)
                if spot is None:
                    break
                x, y = spot
                opts[y][x] = {_pick(opts[y][x], rng)}
                _propagate(opts, grid.w, grid.h)
                _commit(work, opts)
                frames.append(work.snapshot())
            _commit(grid, opts)
            return frames
        except Contradiction as exc:
            last_err = str(exc)
            continue
    raise Contradiction(f"Could not solve the floor ({last_err}).")


def new_grid(w: int, h: int, seed: int = 0, theme: str = "") -> Grid:
    return Grid(max(4, min(32, int(w))), max(4, min(32, int(h))), seed=int(seed), theme=theme)


def paint(grid: Grid, x: int, y: int, tool: str, rot: int = 0, *, auto: bool = True) -> None:
    cell = grid.get(x, y)
    if cell is None:
        return
    if tool in {"off", ""}:
        return
    if tool == "torch":
        cell.torch = not cell.torch
        return
    if tool == "erase":
        cell.kind, cell.rot, cell.pin, cell.torch = "void", 0, False, False
        if auto:
            solve(grid, seed=grid.seed)
        return
    if tool == "perturb":
        cell.pin = False
        if auto:
            solve(grid, seed=random.randint(1, 2**31 - 1))
        return
    if tool not in KIND:
        return
    kind = KIND[tool]
    cell.kind = kind.id
    cell.rot = int(rot) % max(1, kind.turns)
    cell.pin = True
    if auto:
        solve(grid, seed=grid.seed)


def stamp_features(grid: Grid, rng: random.Random, *, caves: bool, graves: bool, canal: bool, terraces: bool) -> None:
    w, h = grid.w, grid.h
    if caves:
        n = max(1, (w * h) // 18)
        for _ in range(n):
            x, y = rng.randrange(w), rng.randrange(h)
            cell = grid.cells[y][x]
            if cell.pin:
                continue
            cell.kind, cell.rot, cell.pin = "cave", 0, True
    if graves:
        n = max(1, (w * h) // 28)
        for _ in range(n):
            x, y = rng.randrange(1, max(2, w - 1)), rng.randrange(1, max(2, h - 1))
            cell = grid.cells[y][x]
            if cell.pin:
                continue
            cell.kind, cell.rot, cell.pin = "grave", 0, True
    if terraces:
        for x in range(w):
            cell = grid.cells[0][x]
            if not cell.pin:
                cell.kind, cell.rot, cell.pin = "terrace", 2, True
    if canal:
        y = rng.randrange(h // 3, max(h // 3 + 1, (2 * h) // 3))
        for x in range(w):
            cell = grid.cells[y][x]
            if cell.pin:
                continue
            cell.kind, cell.rot, cell.pin = "water", 0, True


def generate_map(
    w: int,
    h: int,
    *,
    seed: int | None = None,
    theme: str = "",
    caves: bool = False,
    graves: bool = False,
    canal: bool = False,
    terraces: bool = False,
    pins: Grid | None = None,
) -> Grid:
    seed = int(seed if seed is not None else random.randint(1, 2**31 - 1))
    kit = dict(pins.kit) if pins else {}
    backdrop = pins.backdrop if pins else ""
    grid = pins.snapshot() if pins else new_grid(w, h, seed, theme)
    grid.w, grid.h = w, h
    grid.kit = kit
    grid.backdrop = backdrop
    if len(grid.cells) != h or any(len(r) != w for r in grid.cells):
        fresh = new_grid(w, h, seed, theme)
        for y in range(min(h, len(grid.cells))):
            for x in range(min(w, len(grid.cells[y]))):
                fresh.cells[y][x] = grid.cells[y][x].clone()
        grid = fresh
    grid.seed = seed
    grid.theme = theme
    rng = random.Random(seed)
    stamp_features(grid, rng, caves=caves, graves=graves, canal=canal, terraces=terraces)
    solve(grid, seed=seed)
    # un-pin generated feature stamps so later edits can move them, keep user pins
    return grid


def _font(size: int):
    try:
        return ImageFont.truetype("segoeui.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _load_art(path: str | Path | None, size: tuple[int, int]) -> Image.Image | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        im = Image.open(p).convert("RGBA")
    except OSError:
        return None
    return im.resize(size, Image.Resampling.LANCZOS)


def draw_tile(kind: str, rot: int, size: int, art: Image.Image | None = None) -> Image.Image:
    spec = KIND.get(kind, KIND["void"])
    socks = rotate_socks(spec.sockets, rot)
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pad = max(2, size // 16)
    d.rounded_rectangle((pad, pad, size - pad - 1, size - pad - 1), radius=max(2, size // 10), fill=spec.fill + (255,))
    wall = spec.ink + (255,)
    t = max(3, size // 8)
    if socks[N] in {W, V}:
        d.rectangle((pad, pad, size - pad, pad + t), fill=wall)
    if socks[E] in {W, V}:
        d.rectangle((size - pad - t, pad, size - pad, size - pad), fill=wall)
    if socks[S] in {W, V}:
        d.rectangle((pad, size - pad - t, size - pad, size - pad), fill=wall)
    if socks[WEST] in {W, V}:
        d.rectangle((pad, pad, pad + t, size - pad), fill=wall)
    if kind == "water":
        d.ellipse((size * 0.28, size * 0.28, size * 0.72, size * 0.72), fill=(70, 150, 190, 180))
    elif kind == "stair":
        for i in range(4):
            yy = pad + t + i * (size // 7)
            d.rectangle((pad + t, yy, size - pad - t, yy + 3), fill=(200, 180, 130, 220))
    elif kind == "grave":
        d.rectangle((size * 0.4, size * 0.32, size * 0.6, size * 0.7), fill=(160, 160, 150, 230))
    elif kind == "door":
        d.rectangle((size * 0.42, size * 0.28, size * 0.58, size * 0.72), fill=(90, 55, 30, 240))
    elif kind == "cave":
        d.ellipse((size * 0.3, size * 0.3, size * 0.7, size * 0.7), fill=(50, 36, 28, 160))
    if art is not None:
        return art
    return im


def render_map(
    grid: Grid,
    *,
    iso: bool = True,
    cell: int = 48,
    kit: dict[str, str] | None = None,
) -> Image.Image:
    kit = kit or grid.kit or {}
    art_cache: dict[tuple[str, int], Image.Image | None] = {}

    def art_for(kind: str, rot: int, sz: tuple[int, int]) -> Image.Image | None:
        key = (kind, rot)
        if key not in art_cache:
            path = kit.get(f"{kind}_{rot}") or kit.get(kind)
            art_cache[key] = _load_art(path, sz)
        return art_cache[key]

    if not iso:
        img = Image.new("RGBA", (grid.w * cell + 2, grid.h * cell + 2), (12, 14, 20, 255))
        back = _load_art(getattr(grid, "backdrop", "") or kit.get("backdrop"), img.size)
        if back:
            img.alpha_composite(back)
        for y in range(grid.h):
            for x in range(grid.w):
                c = grid.cells[y][x]
                tile = draw_tile(c.kind, c.rot, cell, art_for(c.kind, c.rot, (cell, cell)))
                img.alpha_composite(tile, (x * cell + 1, y * cell + 1))
                if c.torch:
                    d = ImageDraw.Draw(img)
                    cx, cy = x * cell + cell // 2, y * cell + cell // 2
                    d.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill=(255, 190, 80, 230))
        return img

    tw, th = cell, int(cell * 0.58)
    width = (grid.w + grid.h) * (tw // 2) + tw
    height = (grid.w + grid.h) * (th // 2) + th * 2
    img = Image.new("RGBA", (max(64, width), max(64, height)), (12, 14, 20, 255))
    back = _load_art(getattr(grid, "backdrop", "") or kit.get("backdrop"), img.size)
    if back:
        img.alpha_composite(back)
    ox = (grid.h) * (tw // 2)
    oy = th
    order = sorted(((x, y) for y in range(grid.h) for x in range(grid.w)), key=lambda p: p[0] + p[1])
    for x, y in order:
        c = grid.cells[y][x]
        px = ox + (x - y) * (tw // 2)
        py = oy + (x + y) * (th // 2)
        stamp = art_for(c.kind, c.rot, (tw, int(cell * 0.9)))
        if stamp is None:
            stamp = _iso_tile(c.kind, c.rot, tw, th)
        img.alpha_composite(stamp, (int(px - stamp.width // 2 + tw // 2), int(py - stamp.height + th)))
        if c.torch:
            d = ImageDraw.Draw(img)
            d.ellipse((px + tw // 2 - 5, py + th // 3 - 5, px + tw // 2 + 5, py + th // 3 + 5), fill=(255, 200, 90, 240))
    return img


def _iso_tile(kind: str, rot: int, tw: int, th: int) -> Image.Image:
    spec = KIND.get(kind, KIND["void"])
    socks = rotate_socks(spec.sockets, rot)
    h = th * 2
    im = Image.new("RGBA", (tw, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    mid_x, top, mid_y, bot = tw // 2, h - th * 2, h - th, h
    # sit diamond on the bottom
    top = th
    mid_y = th + th // 2
    bot = th * 2 - 2
    diamond = [(mid_x, top), (tw - 2, mid_y), (mid_x, bot), (2, mid_y)]
    d.polygon(diamond, fill=spec.fill + (255,), outline=spec.ink + (255,))
    wall = tuple(max(0, c - 28) for c in spec.fill) + (255,)
    if socks[N] in {W, V}:
        d.polygon([(mid_x, top), (tw - 2, mid_y), (mid_x, mid_y)], fill=wall)
    if socks[WEST] in {W, V}:
        d.polygon([(mid_x, top), (2, mid_y), (mid_x, mid_y)], fill=wall)
    if kind == "water":
        d.ellipse((mid_x - tw // 6, mid_y - th // 6, mid_x + tw // 6, mid_y + th // 6), fill=(70, 150, 190, 200))
    return im


def hit_cell(grid: Grid, px: int, py: int, *, iso: bool, cell: int, view_w: int, view_h: int) -> tuple[int, int] | None:
    if not iso:
        x, y = (px - 1) // cell, (py - 1) // cell
        if 0 <= x < grid.w and 0 <= y < grid.h:
            return int(x), int(y)
        return None
    tw, th = cell, int(cell * 0.58)
    width = (grid.w + grid.h) * (tw // 2) + tw
    height = (grid.w + grid.h) * (th // 2) + th * 2
    scale = min(view_w / max(width, 1), view_h / max(height, 1), 1.0)
    if scale <= 0:
        return None
    ox = (grid.h) * (tw // 2)
    oy = th
    lx = px / scale
    ly = py / scale
    sx = (lx - ox) / max(tw / 2, 1)
    sy = (ly - oy) / max(th / 2, 1)
    x = round((sx + sy) / 2)
    y = round((sy - sx) / 2)
    if 0 <= x < grid.w and 0 <= y < grid.h:
        return int(x), int(y)
    return None


def save_grid(grid: Grid, path: Path | None = None) -> Path:
    ensure_dirs()
    path = path or (MAPS / "current.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(grid.to_dict(), indent=2), encoding="utf-8")
    return path


def load_grid(path: Path | None = None) -> Grid | None:
    path = path or (MAPS / "current.json")
    if not path.exists():
        return None
    try:
        return Grid.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None


def export_map(grid: Grid, *, iso: bool = True, cell: int = 96) -> Path:
    img = render_map(grid, iso=iso, cell=cell, kit=grid.kit)
    dest = unique_out(OUTPUTS, "dungeon_iso" if iso else "dungeon_top")
    img.convert("RGB").save(dest, "PNG")
    return dest


def export_pack(grid: Grid) -> Path:
    import zipfile

    ensure_dirs()
    dest = unique_out(MAPS, "dungeon_pack", ext=".zip")
    iso = render_map(grid, iso=True, cell=96)
    top = render_map(grid, iso=False, cell=64)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("map.json", json.dumps(grid.to_dict(), indent=2))
        from io import BytesIO

        buf = BytesIO()
        iso.convert("RGB").save(buf, "PNG")
        zf.writestr("map_isometric.png", buf.getvalue())
        buf = BytesIO()
        top.convert("RGB").save(buf, "PNG")
        zf.writestr("map_topdown.png", buf.getvalue())
        for kind, path in (grid.kit or {}).items():
            p = Path(path)
            if p.exists():
                zf.write(p, f"tiles/{kind}{p.suffix}")
    return dest


KIT_LOCK = (
    "SAME DUNGEON TILE KIT. Same stone, same mortar, same lighting, same camera height, "
    "same scale. Isolated modular isometric game tile on a flat chroma-key lime green #00FF00 backdrop. "
    "No character, no UI, one tile only, readable silhouette, production prop."
)


def kit_prompt(kind: TileKind, theme: str, style_lock: str = "") -> str:
    idea = (theme or "dark abyss dungeon stone, cyan lichen").strip()
    parts = [
        f"Follow these words exactly for the material: {idea}",
        kind.prompt,
        KIT_LOCK,
    ]
    if style_lock:
        parts.append(style_lock)
    return ", ".join(parts)


def bake_kit(
    client,
    theme: str,
    *,
    style: str = "abyssal_iso",
    steps: int = 20,
    guidance: float = 3.5,
    seed: int | None = None,
    width: int = 768,
    height: int = 768,
) -> dict[str, str]:
    """Paint every unique kit piece with local Flux. First tile locks the rest."""
    from .prompts import STYLES, compile_negative
    from .quality import finish_sprite

    ensure_dirs()
    seed = int(seed if seed is not None else random.randint(1, 2**31 - 1))
    style_lock = (STYLES.get(style) or {}).get("lock") or ""
    folder = MAPS / f"kit_{seed}"
    folder.mkdir(parents=True, exist_ok=True)
    pieces = [k for k in KINDS if k.id != "void"]
    kit: dict[str, str] = {}
    lock: Path | None = None
    total = len(pieces)
    for i, kind in enumerate(pieces):
        if hasattr(client, "mark_item"):
            client.mark_item(i + 1, total, f"Kit tile {kind.label}  {i + 1} / {total}")
        raws = client.generate(
            kit_prompt(kind, theme, style_lock),
            seed=seed + i * 17,
            steps=max(16, int(steps)),
            width=width,
            height=height,
            guidance=guidance,
            negative=compile_negative("sprite", extra="character, person, hero, text, UI"),
            prefix=f"kit_{kind.id}",
            dest_dir=folder,
            ref_path=lock,
            denoise=0.46 if lock else 1.0,
        )
        dest = folder / f"{kind.id}.png"
        finish_sprite(raws[0], dest, bg="green", key=True, kind="structure")
        kit[kind.id] = str(dest)
        if lock is None:
            lock = dest
    return kit
