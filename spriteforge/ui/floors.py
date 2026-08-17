"""Floors — local Seeing Eyes-style dungeon painter + solver."""
from __future__ import annotations

import os
import random
from pathlib import Path

import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageTk

from ..engine.dungeon import (
    KIND,
    KINDS,
    PAINT_TOOLS,
    Contradiction,
    Grid,
    bake_kit,
    export_map,
    export_pack,
    generate_map,
    hit_cell,
    load_grid,
    new_grid,
    paint,
    render_map,
    save_grid,
    solve_steps,
    stamp_features,
)
from ..engine.prompts import STYLES
from ..paths import MAPS
from . import theme
from .studio import _style_key, _style_labels


class FloorsPage(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color=theme.BG)
        self.app = app
        self.grid_map = load_grid() or new_grid(12, 12, seed=random.randint(1, 99999))
        self.undo: list[Grid] = []
        self.hand = "floor"
        self.rot = 0
        self.iso = True
        self.auto = True
        self.animating = False
        self._photo = None
        self._shown = (1, 1)
        self._full = (1, 1)
        self._origin = (0, 0)
        self._hover: tuple[int, int] | None = None
        self._drag_stroke = False

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        form = ctk.CTkScrollableFrame(self, fg_color=theme.PANEL, width=380, corner_radius=0)
        form.grid(row=0, column=0, sticky="nsew")
        ctk.CTkLabel(
            form, text="Floors", text_color=theme.TEXT,
            font=ctk.CTkFont("Segoe UI", 22, "bold"),
        ).pack(anchor="w", padx=18, pady=(18, 4))
        theme.muted(
            form,
            "Seeing Eyes-style builder, all local. Pick a tile, click or drag to place, "
            "press R to rotate. Generate fills the rest so openings meet. "
            "Bake kit paints matching Flux tiles for this dungeon.",
            wrap=330,
        ).pack(anchor="w", padx=18, pady=(0, 12))

        theme.section(form, "Dungeon material").pack(anchor="w", padx=18, pady=(8, 4))
        self.theme_box = ctk.CTkTextbox(form, height=72, fg_color=theme.CARD)
        self.theme_box.pack(fill="x", padx=18)
        self.theme_box.insert("1.0", self.grid_map.theme or "abyssal black flagstones, cyan lichen, wet grout, torch soot")

        theme.section(form, "Style").pack(anchor="w", padx=18, pady=(10, 4))
        self.style = ctk.CTkOptionMenu(form, values=_style_labels(), fg_color=theme.CARD)
        self.style.set(STYLES.get("abyssal_iso", {}).get("label") or _style_labels()[0])
        self.style.pack(fill="x", padx=18)

        self.gw = self._slider(form, "Grid width", 6, 24, self.grid_map.w)
        self.gh = self._slider(form, "Grid height", 6, 24, self.grid_map.h)
        self.seed_e = ctk.CTkEntry(form, fg_color=theme.CARD)
        theme.section(form, "Seed").pack(anchor="w", padx=18, pady=(10, 4))
        self.seed_e.pack(fill="x", padx=18)
        self.seed_e.insert(0, str(self.grid_map.seed or ""))

        flags = ctk.CTkFrame(form, fg_color="transparent")
        flags.pack(fill="x", padx=18, pady=(10, 0))
        self.cave_on = ctk.CTkCheckBox(flags, text="Cave bites")
        self.grave_on = ctk.CTkCheckBox(flags, text="Graveyards")
        self.canal_on = ctk.CTkCheckBox(flags, text="Force a canal")
        self.terr_on = ctk.CTkCheckBox(flags, text="Terraces")
        self.cave_on.pack(anchor="w")
        self.grave_on.pack(anchor="w")
        self.canal_on.pack(anchor="w")
        self.terr_on.pack(anchor="w")

        self.auto_on = ctk.CTkCheckBox(form, text="Auto-solve around edits", command=self._toggle_auto)
        self.auto_on.pack(anchor="w", padx=18, pady=(10, 0))
        self.auto_on.select()
        self.iso_on = ctk.CTkCheckBox(form, text="Isometric view", command=self._toggle_iso)
        self.iso_on.pack(anchor="w", padx=18, pady=(4, 0))
        self.iso_on.select()
        self.anim_on = ctk.CTkCheckBox(form, text="Animate build")
        self.anim_on.pack(anchor="w", padx=18, pady=(4, 0))

        row = ctk.CTkFrame(form, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(14, 4))
        ctk.CTkButton(row, text="Generate map", height=36, fg_color=theme.WARM, hover_color="#d45544", command=self.generate).pack(side="left", expand=True, fill="x")
        ctk.CTkButton(row, text="Undo", width=72, height=36, fg_color=theme.CARD, command=self.undo_map).pack(side="left", padx=(6, 0))

        ctk.CTkButton(
            form, text="Bake kit with local Flux", height=36, fg_color=theme.ACCENT_DIM,
            hover_color="#24665c", command=self.bake,
        ).pack(fill="x", padx=18, pady=(6, 4))

        theme.section(form, "Paint (R rotates)").pack(anchor="w", padx=18, pady=(14, 4))
        self.tool = ctk.CTkOptionMenu(
            form, values=PAINT_TOOLS, fg_color=theme.CARD, command=self._set_hand,
        )
        self.tool.set("floor")
        self.tool.pack(fill="x", padx=18)
        ctk.CTkButton(form, text="Rotate 90°  (R)", height=30, fg_color=theme.CARD, command=self._rotate).pack(fill="x", padx=18, pady=(6, 0))
        self.hand_lbl = ctk.CTkLabel(form, text="In hand: Floor  rot 0°", text_color=theme.ACCENT, anchor="w")
        self.hand_lbl.pack(fill="x", padx=18, pady=(6, 0))

        pal = ctk.CTkFrame(form, fg_color="transparent")
        pal.pack(fill="x", padx=14, pady=(8, 4))
        for i, kind in enumerate(k for k in KINDS if k.id != "void"):
            btn = ctk.CTkButton(
                pal, text=kind.label, width=168, height=26, fg_color=theme.CARD,
                text_color=theme.TEXT, command=lambda k=kind.id: self._set_hand(k),
            )
            btn.grid(row=i // 2, column=i % 2, padx=4, pady=2, sticky="ew")

        erow = ctk.CTkFrame(form, fg_color="transparent")
        erow.pack(fill="x", padx=18, pady=(16, 18))
        ctk.CTkButton(erow, text="Export PNG", fg_color=theme.WARM, command=self.export_png).pack(side="left", expand=True, fill="x")
        ctk.CTkButton(erow, text="Export ZIP", fg_color=theme.CARD, command=self.export_zip).pack(side="left", padx=(6, 0), expand=True, fill="x")
        ctk.CTkButton(form, text="Open maps folder", fg_color=theme.CARD, command=lambda: os.startfile(MAPS)).pack(fill="x", padx=18, pady=(0, 18))

        right = ctk.CTkFrame(self, fg_color=theme.BG)
        right.grid(row=0, column=1, sticky="nsew", padx=16, pady=16)
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)
        self.board = tk.Canvas(right, bg=theme.CARD, highlightthickness=0, bd=0)
        self.board.grid(row=0, column=0, sticky="nsew")
        self.hover_lbl = ctk.CTkLabel(right, text="Click a cell to place. Drag to paint. Use Rotate 90°.", text_color=theme.MUTED, anchor="w")
        self.hover_lbl.grid(row=1, column=0, sticky="ew", pady=(10, 0))

        self.board.bind("<Button-1>", self._click)
        self.board.bind("<B1-Motion>", self._drag)
        self.board.bind("<ButtonRelease-1>", self._release)
        self.board.bind("<Motion>", self._move)
        self.board.bind("<KeyPress-r>", self._rotate)
        self.board.bind("<KeyPress-R>", self._rotate)
        self._resize_job = None
        self.board.bind("<Configure>", self._on_resize)
        self.after(200, self.redraw)

    def _on_resize(self, _e=None) -> None:
        if self._resize_job:
            try:
                self.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.after(80, self.redraw)

    def _slider(self, parent, title, lo, hi, value):
        from .controls import _ValueSlider

        s = _ValueSlider(parent, title, lo, hi, value, integer=True)
        s.pack(fill="x", padx=18, pady=(8, 0))
        return s

    def _theme(self) -> str:
        return self.theme_box.get("1.0", "end").strip()

    def _seed(self) -> int:
        raw = self.seed_e.get().strip()
        if raw.lstrip("-").isdigit():
            return int(raw)
        return random.randint(1, 2**31 - 1)

    def _push(self) -> None:
        self.undo.append(self.grid_map.snapshot())
        self.undo = self.undo[-24:]

    def _set_hand(self, name: str) -> None:
        self.hand = name
        self.tool.set(name)
        self.rot = 0
        self._hand_label()

    def _hand_label(self) -> None:
        spec = KIND.get(self.hand)
        label = spec.label if spec else self.hand
        self.hand_lbl.configure(text=f"In hand: {label}  rot {self.rot * 90}°")

    def _toggle_auto(self) -> None:
        self.auto = bool(self.auto_on.get())

    def _toggle_iso(self) -> None:
        self.iso = bool(self.iso_on.get())
        self.redraw()

    def _rotate(self, _e=None):
        page = getattr(self.app, "_pages", {}).get("floors")
        if page is not None and page is not self:
            return
        if _e is not None:
            focus = self.focus_get()
            cls = (focus.winfo_class() if focus else "") or ""
            if cls in {"Text", "Entry", "TEntry"}:
                return
        spec = KIND.get(self.hand)
        turns = spec.turns if spec else 4
        self.rot = (self.rot + 1) % max(1, turns)
        self._hand_label()

    def on_show(self) -> None:
        self.redraw()

    def generate(self) -> None:
        if self.animating:
            return
        self._push()
        w, h = int(self.gw.get()), int(self.gh.get())
        seed = self._seed()
        self.seed_e.delete(0, "end")
        self.seed_e.insert(0, str(seed))
        theme_s = self._theme()
        caves, graves = bool(self.cave_on.get()), bool(self.grave_on.get())
        canal, terr = bool(self.canal_on.get()), bool(self.terr_on.get())
        pins = self.grid_map.snapshot()
        pins.w, pins.h = w, h

        if self.anim_on.get():
            try:
                draft = new_grid(w, h, seed, theme_s)
                draft.kit = dict(self.grid_map.kit or {})
                for y in range(min(h, len(pins.cells))):
                    for x in range(min(w, len(pins.cells[y]))):
                        if pins.cells[y][x].pin:
                            draft.cells[y][x] = pins.cells[y][x].clone()
                stamp_features(draft, random.Random(seed), caves=caves, graves=graves, canal=canal, terraces=terr)
                frames = solve_steps(draft, seed=seed)
                self._play(frames or [draft])
            except Contradiction as exc:
                self.app.set_status(str(exc), "warn")
            return

        try:
            self.grid_map = generate_map(
                w, h, seed=seed, theme=theme_s, caves=caves, graves=graves,
                canal=canal, terraces=terr, pins=pins,
            )
            self.grid_map.kit = pins.kit
            save_grid(self.grid_map)
            self.redraw()
            self.app.set_status(f"Map {w}×{h}  seed {seed} — openings match.", "ok")
        except Contradiction as exc:
            self.app.set_status(str(exc), "warn")

    def _play(self, frames: list[Grid]) -> None:
        self.animating = True
        self.app.set_status(f"Building {len(frames)} cells…", "info")

        def tick(i: int) -> None:
            if i >= len(frames):
                self.animating = False
                self.grid_map = frames[-1]
                save_grid(self.grid_map)
                self.redraw()
                self.app.set_status(f"Map ready  {self.grid_map.w}×{self.grid_map.h}.", "ok")
                return
            self.grid_map = frames[i]
            self.redraw()
            self.after(28, lambda: tick(i + 1))

        tick(0)

    def undo_map(self) -> None:
        if not self.undo:
            self.app.set_status("Nothing to undo.", "warn")
            return
        self.grid_map = self.undo.pop()
        save_grid(self.grid_map)
        self.redraw()
        self.app.set_status("Undid last map change.", "ok")

    def bake(self) -> None:
        theme_s = self._theme()
        if not theme_s:
            self.app.set_status("Describe the dungeon stone first.", "warn")
            return
        seed = self._seed()
        style = _style_key(self.style.get())

        def work():
            return bake_kit(
                self.app.client(), theme_s, style=style,
                steps=int(self.app.cfg.get("steps") or 20),
                guidance=float(self.app.cfg.get("guidance") or 3.5),
                seed=seed,
            )

        def done(kit, err):
            if err:
                self.app.set_status(f"Kit bake failed: {err}", "err")
                return
            self.grid_map.kit = kit or {}
            self.grid_map.theme = theme_s
            save_grid(self.grid_map)
            self.redraw()
            self.app.set_status(f"Kit ready — {len(kit or {})} matching tiles. Generate or paint.", "ok")

        n = len([k for k in KINDS if k.id != "void"])
        self.app.run_job(
            work, done, "Baking dungeon kit on local Flux…",
            items=n, steps=int(self.app.cfg.get("steps") or 20),
        )

    def export_png(self) -> None:
        path = export_map(self.grid_map, iso=self.iso, cell=96)
        self.app.last_image = path
        self.app.lib.record_output(path, {"kind": "dungeon", "seed": self.grid_map.seed})
        self.app.set_status(f"Map PNG → {path.name}", "ok")
        os.startfile(path)

    def export_zip(self) -> None:
        path = export_pack(self.grid_map)
        self.app.set_status(f"Pack → {path.name} (iso + top-down + tiles + map.json)", "ok")
        os.startfile(path.parent)

    def _cell_at(self, event) -> tuple[int, int] | None:
        ox, oy = self._origin
        sw, sh = self._shown
        fw, fh = self._full
        lx = int(event.x) - ox
        ly = int(event.y) - oy
        if lx < 0 or ly < 0 or lx > sw or ly > sh:
            return None
        scale_x = fw / max(sw, 1)
        scale_y = fh / max(sh, 1)
        return hit_cell(
            self.grid_map, int(lx * scale_x), int(ly * scale_y),
            iso=self.iso, cell=48, view_w=fw, view_h=fh,
        )

    def _apply(self, xy: tuple[int, int] | None, *, stroke: bool = False) -> None:
        if xy is None or self.animating:
            return
        x, y = xy
        if not stroke:
            self._push()
        auto = self.auto and self.hand != "off" and not stroke
        try:
            paint(self.grid_map, x, y, self.hand, self.rot, auto=auto)
        except Contradiction as exc:
            if not stroke and self.undo:
                self.grid_map = self.undo.pop()
            self.app.set_status(f"That piece does not fit: {exc}", "warn")
            return
        save_grid(self.grid_map)
        self.redraw()
        cell = self.grid_map.get(x, y)
        name = KIND.get(cell.kind).label if cell and cell.kind in KIND else "?"
        self.app.set_status(f"{name} @ {x},{y}  rot {self.rot * 90}°", "ok")

    def _click(self, event) -> None:
        self.board.focus_set()
        self._drag_stroke = True
        self._apply(self._cell_at(event), stroke=False)

    def _drag(self, event) -> None:
        if self.hand in {"off", "perturb", "torch"}:
            return
        self._apply(self._cell_at(event), stroke=True)

    def _release(self, _event) -> None:
        if self._drag_stroke and self.auto and self.hand not in {"off", "torch"}:
            try:
                from ..engine.dungeon import solve

                solve(self.grid_map, seed=self.grid_map.seed)
                save_grid(self.grid_map)
                self.redraw()
            except Contradiction as exc:
                self.app.set_status(str(exc), "warn")
        self._drag_stroke = False

    def _move(self, event) -> None:
        xy = self._cell_at(event)
        self._hover = xy
        if not xy:
            self.hover_lbl.configure(text="Click a cell to place. Drag to paint. R rotates.")
            return
        x, y = xy
        cell = self.grid_map.get(x, y)
        have = KIND.get(cell.kind).label if cell and cell.kind in KIND else "empty"
        pin = "  pinned" if cell and cell.pin else ""
        torch = "  torch" if cell and cell.torch else ""
        self.hover_lbl.configure(text=f"Cell {x},{y}  ·  {have}{pin}{torch}  ·  placing {self.hand} {self.rot * 90}°")

    def redraw(self) -> None:
        w = max(self.board.winfo_width(), 200)
        h = max(self.board.winfo_height(), 200)
        if w < 40 or h < 40:
            self.after(120, self.redraw)
            return
        raw = render_map(self.grid_map, iso=self.iso, cell=48, kit=self.grid_map.kit)
        img = raw.copy()
        img.thumbnail((max(40, w - 8), max(40, h - 8)), Image.Resampling.LANCZOS)
        self._full = raw.size
        self._shown = img.size
        self._origin = ((w - img.size[0]) // 2, (h - img.size[1]) // 2)
        self._photo = ImageTk.PhotoImage(img.convert("RGB"))
        self.board.delete("all")
        self.board.create_image(w // 2, h // 2, image=self._photo, anchor="center")
