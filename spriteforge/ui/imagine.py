from __future__ import annotations

import os
import random
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image

from ..engine.imagine import (
    ASPECTS,
    FREE_STYLES,
    generate_variations,
    imagine_video,
    think_prompt,
    upscale_4k,
)
from ..paths import OUTPUTS, VIDEOS
from . import theme
from .studio import _thumb


class ImaginePage(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color=theme.BG)
        self.app = app
        self.vars: list[Path] = []
        self.picked: Path | None = None
        self.picked_i = -1
        self._thumbs: list[ctk.CTkImage] = []
        self._hero = None
        self.still: Path | None = None

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        form = ctk.CTkScrollableFrame(self, fg_color=theme.PANEL, width=380, corner_radius=0)
        form.grid(row=0, column=0, sticky="nsew")
        ctk.CTkLabel(
            form, text="Imagine", text_color=theme.TEXT,
            font=ctk.CTkFont("Segoe UI", 22, "bold"),
        ).pack(anchor="w", padx=18, pady=(18, 4))
        theme.muted(
            form,
            "Free text-to-image and image-to-video. Writes four variations like Midjourney. "
            "Pick one, then upscale it to 4K or turn it into a video.",
            wrap=330,
        ).pack(anchor="w", padx=18, pady=(0, 12))

        theme.section(form, "Idea").pack(anchor="w", padx=18, pady=(8, 4))
        self.prompt = ctk.CTkTextbox(form, height=130, font=ctk.CTkFont("Segoe UI", 14), fg_color=theme.CARD)
        self.prompt.pack(fill="x", padx=18)
        self.prompt.insert("1.0", "a lonely lantern adrift on a black sea under two pale moons")

        theme.section(form, "Thinking").pack(anchor="w", padx=18, pady=(10, 4))
        self.think = ctk.CTkOptionMenu(
            form, values=["Free think — invent complementary detail", "Exact words only"],
            fg_color=theme.CARD,
        )
        self.think.set("Free think — invent complementary detail")
        self.think.pack(fill="x", padx=18)

        theme.section(form, "Style").pack(anchor="w", padx=18, pady=(10, 4))
        self.style = ctk.CTkOptionMenu(form, values=list(FREE_STYLES), fg_color=theme.CARD)
        self.style.set("Open (free)")
        self.style.pack(fill="x", padx=18)

        theme.section(form, "Aspect").pack(anchor="w", padx=18, pady=(10, 4))
        self.aspect = ctk.CTkOptionMenu(form, values=list(ASPECTS), fg_color=theme.CARD)
        self.aspect.set("16:9")
        self.aspect.pack(fill="x", padx=18)

        theme.section(form, "Motion (video)").pack(anchor="w", padx=18, pady=(10, 4))
        self.motion = ctk.CTkTextbox(form, height=64, fg_color=theme.CARD)
        self.motion.pack(fill="x", padx=18)
        self.motion.insert("1.0", "slow camera push-in, light breathing, clouds and water living")
        self.use_mem = ctk.CTkCheckBox(form, text="Use evolving memory (profile taste)")
        self.use_mem.pack(anchor="w", padx=18, pady=(10, 0))
        if self.app.cfg.get("use_memory", True):
            self.use_mem.select()

        ctk.CTkButton(
            form, text="Imagine  ×4", height=42, fg_color=theme.WARM, hover_color="#d45544",
            font=ctk.CTkFont("Segoe UI", 15, "bold"), command=self.imagine,
        ).pack(fill="x", padx=18, pady=(16, 6))
        ctk.CTkButton(
            form, text="Upscale selected to 4K", height=36, fg_color=theme.ACCENT_DIM,
            hover_color="#24665c", command=self.upscale,
        ).pack(fill="x", padx=18, pady=4)
        ctk.CTkButton(
            form, text="Image → video", height=36, fg_color=theme.CARD, command=self.image_video,
        ).pack(fill="x", padx=18, pady=4)
        ctk.CTkButton(
            form, text="Text → video", height=36, fg_color=theme.CARD, command=self.text_video,
        ).pack(fill="x", padx=18, pady=4)

        brow = ctk.CTkFrame(form, fg_color="transparent")
        brow.pack(fill="x", padx=18, pady=(10, 4))
        ctk.CTkButton(brow, text="Browse still…", width=150, fg_color=theme.CARD, command=self.browse).pack(side="left")
        ctk.CTkButton(brow, text="Open outputs", width=150, fg_color=theme.CARD, command=lambda: os.startfile(OUTPUTS)).pack(side="left", padx=8)

        theme.section(form, "Prompt the model will get").pack(anchor="w", padx=18, pady=(12, 4))
        self.compiled = ctk.CTkTextbox(form, height=80, fg_color=theme.CARD, text_color=theme.MUTED, font=ctk.CTkFont("Consolas", 11))
        self.compiled.pack(fill="x", padx=18, pady=(0, 18))

        right = ctk.CTkFrame(self, fg_color=theme.BG)
        right.grid(row=0, column=1, sticky="nsew", padx=16, pady=16)
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self.gridf = ctk.CTkFrame(right, fg_color="transparent")
        self.gridf.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self.gridf.grid_columnconfigure((0, 1), weight=1)
        self.cells: list[ctk.CTkFrame] = []
        self.cell_lbls: list[ctk.CTkLabel] = []
        for i in range(4):
            cell = ctk.CTkFrame(self.gridf, fg_color=theme.CARD, corner_radius=10, border_width=2, border_color=theme.LINE)
            cell.grid(row=i // 2, column=i % 2, padx=6, pady=6, sticky="nsew")
            lbl = ctk.CTkLabel(cell, text=f"V{i + 1}", text_color=theme.MUTED)
            lbl.pack(fill="both", expand=True, padx=8, pady=8)
            for w in (cell, lbl):
                w.bind("<Button-1>", lambda _e, n=i: self.pick(n))
            self.cells.append(cell)
            self.cell_lbls.append(lbl)

        self.hero = ctk.CTkLabel(right, text="Pick a variation after Imagine ×4", text_color=theme.MUTED, fg_color=theme.CARD, corner_radius=12)
        self.hero.grid(row=1, column=0, sticky="nsew")
        self.pick_lbl = ctk.CTkLabel(right, text="Nothing selected", text_color=theme.MUTED, anchor="w")
        self.pick_lbl.grid(row=2, column=0, sticky="ew", pady=(10, 0))

    def _idea(self) -> str:
        return self.prompt.get("1.0", "end").strip()

    def _think(self) -> bool:
        return self.think.get().startswith("Free")

    def _motion(self) -> str:
        return self.motion.get("1.0", "end").strip()

    def _memory(self) -> str:
        if not self.use_mem.get() or not self.app.cfg.get("use_memory", True):
            return ""
        return self.app.mind.steer()

    def _refresh_compiled(self) -> str:
        p = think_prompt(self._idea(), style=self.style.get(), think=self._think(), memory=self._memory())
        self.compiled.delete("1.0", "end")
        self.compiled.insert("1.0", p)
        return p

    def _selected(self) -> Path | None:
        if self.picked and Path(self.picked).exists():
            return Path(self.picked)
        if self.still and Path(self.still).exists():
            return Path(self.still)
        last = getattr(self.app, "last_image", None)
        if last and Path(last).exists():
            return Path(last)
        return None

    def imagine(self) -> None:
        text = self._idea()
        if not text:
            self.app.set_status("Write an idea first.", "warn")
            return
        self._refresh_compiled()
        w, h = ASPECTS[self.aspect.get()]
        seed = random.randint(1, 2**31 - 1)
        style = self.style.get()
        think = self._think()

        mem = self._memory()

        def work():
            return generate_variations(
                self.app.client(), text, style=style, think=think,
                width=w, height=h, seed=seed, memory=mem,
            )

        def done(paths, err):
            if err:
                self.app.set_status(f"Imagine failed: {err}", "err")
                return
            self.vars = list(paths or [])
            self._render_grid()
            if self.vars:
                self.pick(0, remember=False)
            for p in self.vars:
                self.app.lib.record_output(p, {"kind": "imagine", "prompt": text, "seed": seed})
            self.app.mind.note("imagine", text, style=style, aspect=self.aspect.get(), weight=1.0)
            self.app.refresh_memory_label()
            self.app.set_status(f"4 variations ready — click one, then 4K or video.", "ok")

        self.app.run_job(work, done, "Imagining 4 variations…")

    def _render_grid(self) -> None:
        self._thumbs.clear()
        for i, lbl in enumerate(self.cell_lbls):
            if i < len(self.vars) and self.vars[i].exists():
                img = _thumb(self.vars[i], (360, 220))
                if img:
                    self._thumbs.append(img)
                    lbl.configure(image=img, text="")
                    continue
            lbl.configure(image=None, text=f"V{i + 1}")

    def pick(self, index: int, remember: bool = True) -> None:
        if index < 0 or index >= len(self.vars):
            return
        self.picked_i = index
        self.picked = self.vars[index]
        self.app.last_image = self.picked
        for i, cell in enumerate(self.cells):
            cell.configure(border_color=theme.ACCENT if i == index else theme.LINE)
        hero = _thumb(self.picked, (960, 540))
        if hero:
            self._hero = hero
            self.hero.configure(image=hero, text="")
        self.pick_lbl.configure(
            text=f"Selected  V{index + 1}  ·  {self.picked.name}",
            text_color=theme.ACCENT,
        )
        if remember:
            self.app.mind.note(
                "pick",
                self._idea(),
                style=self.style.get(),
                aspect=self.aspect.get(),
                variant=index,
                weight=2.0,
                path=str(self.picked),
            )
            self.app.refresh_memory_label()

    def upscale(self) -> None:
        src = self._selected()
        if not src:
            self.app.set_status("Pick a variation first (or browse a still).", "warn")
            return
        text = self._idea()
        style = self.style.get()
        think = self._think()

        def work():
            return upscale_4k(self.app.client(), src, text=text, style=style, think=think)

        def done(path, err):
            if err:
                self.app.set_status(f"4K upscale failed: {err}", "err")
                return
            self.app.last_image = path
            self.app.lib.record_output(path, {"kind": "imagine_4k", "prompt": text, "src": str(src)})
            self.app.mind.note(
                "upscale", text, style=style, aspect=self.aspect.get(),
                variant=self.picked_i if self.picked_i >= 0 else None,
                weight=3.0, path=str(path),
            )
            self.app.refresh_memory_label()
            img = _thumb(path, (960, 540))
            if img:
                self._hero = img
                self.hero.configure(image=img, text="")
            try:
                w, h = Image.open(path).size
            except OSError:
                w = h = 0
            self.pick_lbl.configure(text=f"4K ready  ·  {w}×{h}  ·  {path.name}", text_color=theme.OK)
            self.app.set_status(f"4K upscale → {path.name} ({w}×{h})", "ok")

        self.app.run_job(work, done, "Upscaling selected to 4K…")

    def image_video(self) -> None:
        src = self._selected()
        if not src:
            self.app.set_status("Pick a variation or browse a still first.", "warn")
            return
        self._run_video(src)

    def text_video(self) -> None:
        text = self._idea()
        if not text:
            self.app.set_status("Write an idea first.", "warn")
            return
        src = self._selected()
        w, h = ASPECTS[self.aspect.get()]
        style = self.style.get()
        think = self._think()
        motion = self._motion()

        def work():
            still = src
            if still is None:
                ones = generate_variations(
                    self.app.client(), text, style=style, think=think,
                    width=w, height=h, count=1,
                )
                still = ones[0]
            return still, imagine_video(
                self.app.client(), still, text=text, motion=motion, style=style, think=think,
            )

        def done(payload, err):
            if err:
                self.app.set_status(f"Video failed: {err}", "err")
                return
            still, path = payload
            self.app.last_image = still
            self.app.mind.note("video", text, style=style, aspect=self.aspect.get(), weight=2.0, path=str(path))
            self.app.refresh_memory_label()
            self.app.set_status(f"Video ready → {path.name}", "ok")
            os.startfile(path)

        self.app.run_job(work, done, "Text → video…")

    def _run_video(self, src: Path) -> None:
        text = self._idea()
        style = self.style.get()
        think = self._think()
        motion = self._motion()

        def work():
            return imagine_video(
                self.app.client(), src, text=text, motion=motion, style=style, think=think,
            )

        def done(path, err):
            if err:
                self.app.set_status(f"Video failed: {err}", "err")
                return
            self.app.mind.note("video", text, style=style, aspect=self.aspect.get(), weight=2.0, path=str(path))
            self.app.refresh_memory_label()
            self.app.set_status(f"Video ready → {path.name}", "ok")
            os.startfile(path)
            try:
                os.startfile(VIDEOS)
            except OSError:
                pass

        self.app.run_job(work, done, "Animating selected image…")

    def browse(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.webp")])
        if not path:
            return
        self.still = Path(path)
        self.picked = self.still
        self.app.last_image = self.still
        img = _thumb(self.still, (960, 540))
        if img:
            self._hero = img
            self.hero.configure(image=img, text="")
        self.pick_lbl.configure(text=f"Still  ·  {self.still.name}", text_color=theme.ACCENT)
        self.app.set_status(f"Still: {self.still.name}", "ok")
