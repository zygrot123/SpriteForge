from __future__ import annotations

import os
import random
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image

from ..engine.imagine import (
    ASPECTS,
    EDIT_LOCK,
    FREE_STYLES,
    RESOLUTIONS,
    STRENGTHS,
    generate_variations,
    imagine_video,
    import_local,
    scale_video,
    think_prompt,
    upscale_image,
)
from ..engine.assets import unique_out
from ..paths import OUTPUTS, VIDEOS
from . import theme
from .controls import _ValueSlider
from .mic import attach_mic
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
            "Talk or type. Load a photo from this PC, then say what to add, change, or animate. "
            "The edit and the video both follow your words on that picture.",
            wrap=330,
        ).pack(anchor="w", padx=18, pady=(0, 12))

        theme.section(form, "Your image (from this PC)").pack(anchor="w", padx=18, pady=(8, 4))
        load_row = ctk.CTkFrame(form, fg_color="transparent")
        load_row.pack(fill="x", padx=18)
        ctk.CTkButton(load_row, text="Load from PC", width=120, fg_color=theme.ACCENT_DIM, command=self.browse).pack(side="left")
        ctk.CTkButton(load_row, text="Paste", width=70, fg_color=theme.CARD, command=self.paste_image).pack(side="left", padx=6)
        ctk.CTkButton(load_row, text="Clear", width=70, fg_color=theme.CARD, command=self.clear_image).pack(side="left")
        self.src_lbl = ctk.CTkLabel(form, text="No image loaded — text-only Imagine.", text_color=theme.MUTED, wraplength=330, justify="left", anchor="w")
        self.src_lbl.pack(fill="x", padx=18, pady=(6, 0))
        theme.section(form, "How hard to change the photo").pack(anchor="w", padx=18, pady=(10, 4))
        self.strength = ctk.CTkOptionMenu(form, values=list(STRENGTHS), fg_color=theme.CARD)
        self.strength.set("Add / tweak — follow my words")
        self.strength.pack(fill="x", padx=18)
        self.four_edits = ctk.CTkCheckBox(form, text="Make 4 edit variations")
        self.four_edits.pack(anchor="w", padx=18, pady=(8, 0))
        self.four_edits.select()
        ctk.CTkButton(
            form, text="Edit this image", height=36, fg_color=theme.WARM, hover_color="#d45544",
            command=self.edit_image,
        ).pack(fill="x", padx=18, pady=(10, 4))
        ctk.CTkButton(
            form, text="Video from this image", height=36, fg_color=theme.ACCENT_DIM,
            hover_color="#24665c", command=self.image_video,
        ).pack(fill="x", padx=18, pady=4)

        theme.section(form, "Idea").pack(anchor="w", padx=18, pady=(8, 4))
        self.prompt = ctk.CTkTextbox(form, height=130, font=ctk.CTkFont("Segoe UI", 14), fg_color=theme.CARD)
        self.prompt.pack(fill="x", padx=18)
        self.prompt.insert("1.0", "a lonely lantern adrift on a black sea under two pale moons")
        attach_mic(form, self.prompt, self.app)

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
        theme.section(form, "Output size (image + video)").pack(anchor="w", padx=18, pady=(10, 4))
        self.outres = ctk.CTkOptionMenu(form, values=list(RESOLUTIONS), fg_color=theme.CARD)
        self.outres.set("720p")
        self.outres.pack(fill="x", padx=18)

        theme.section(form, "Motion (video)").pack(anchor="w", padx=18, pady=(10, 4))
        self.motion = ctk.CTkTextbox(form, height=64, fg_color=theme.CARD)
        self.motion.pack(fill="x", padx=18)
        self.motion.insert("1.0", "slow camera push-in, light breathing, clouds and water living")
        attach_mic(form, self.motion, self.app)
        self.duration = _ValueSlider(form, "Video length (seconds)", 2, 10, 4, integer=True)
        self.duration.pack(fill="x", padx=18, pady=(8, 0))
        self.use_mem = ctk.CTkCheckBox(form, text="Use evolving memory (profile taste)")
        self.use_mem.pack(anchor="w", padx=18, pady=(10, 0))
        if self.app.cfg.get("use_memory", True):
            self.use_mem.select()

        ctk.CTkButton(
            form, text="Imagine  ×4", height=42, fg_color=theme.WARM, hover_color="#d45544",
            font=ctk.CTkFont("Segoe UI", 15, "bold"), command=self.imagine,
        ).pack(fill="x", padx=18, pady=(16, 6))
        ctk.CTkButton(
            form, text="Upscale image to size", height=36, fg_color=theme.ACCENT_DIM,
            hover_color="#24665c", command=self.upscale,
        ).pack(fill="x", padx=18, pady=4)
        ctk.CTkButton(
            form, text="Upscale last video to size", height=36, fg_color=theme.CARD,
            command=self.upscale_video,
        ).pack(fill="x", padx=18, pady=4)
        ctk.CTkButton(
            form, text="Text → video", height=40, fg_color=theme.WARM, hover_color="#d45544",
            command=self.text_video,
        ).pack(fill="x", padx=18, pady=4)
        ctk.CTkButton(form, text="Open outputs", fg_color=theme.CARD, command=lambda: os.startfile(OUTPUTS)).pack(
            fill="x", padx=18, pady=(10, 4)
        )

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

        self.hero = ctk.CTkLabel(right, text="Load a photo or run Imagine ×4", text_color=theme.MUTED, fg_color=theme.CARD, corner_radius=12)
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
        return self.app.mind.steer(self._idea())

    def _denoise(self) -> float:
        return float(STRENGTHS.get(self.strength.get(), 0.38))

    def _show_src(self, path: Path, note: str = "") -> None:
        self.still = path
        self.picked = path
        self.app.last_image = path
        img = _thumb(path, (960, 540))
        if img:
            self._hero = img
            self.hero.configure(image=img, text="")
        label = f"Loaded  ·  {path.name}"
        if note:
            label = f"{note}  ·  {path.name}"
        self.src_lbl.configure(text=f"Using {path.name} — edits and video follow your prompt on this picture.", text_color=theme.ACCENT)
        self.pick_lbl.configure(text=label, text_color=theme.ACCENT)

    def _refresh_compiled(self) -> str:
        idea = self._idea()
        exact = not self._think()
        extra = EDIT_LOCK if (self.still and Path(self.still).exists()) else ""
        p = think_prompt(
            idea,
            style=self.style.get(),
            think=self._think() and not exact,
            memory="" if exact else self._memory(),
            extra=extra,
            exact=exact,
        )
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

        src = self.still if self.still and Path(self.still).exists() else None

        def work():
            return generate_variations(
                self.app.client(), text, style=style, think=think,
                width=w, height=h, seed=seed, memory=mem,
                ref_path=src, denoise=self._denoise() if src else 1.0,
                aspect=self.aspect.get(), preset=self.outres.get(),
                exact=not think,
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
            kind = "photo edits" if src else "variations"
            self.app.set_status(f"4 {kind} ready — click one, then 4K or video.", "ok")

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

        preset = self.outres.get()

        def work():
            return upscale_image(self.app.client(), src, preset=preset, text=text, style=style, think=think)

        def done(path, err):
            if err:
                self.app.set_status(f"{preset} upscale failed: {err}", "err")
                return
            self.app.last_image = path
            self.app.lib.record_output(path, {"kind": f"imagine_{preset}", "prompt": text, "src": str(src)})
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
            self.pick_lbl.configure(text=f"{preset} ready  ·  {w}×{h}  ·  {path.name}", text_color=theme.OK)
            self.app.set_status(f"{preset} → {path.name} ({w}×{h})", "ok")

        self.app.run_job(work, done, f"Upscaling image to {preset}…")

    def edit_image(self) -> None:
        src = self.still if self.still and Path(self.still).exists() else self._selected()
        if not src:
            self.app.set_status("Load a photo from this PC first.", "warn")
            return
        text = self._idea()
        if not text:
            self.app.set_status("Write what to add or change on the photo.", "warn")
            return
        self._refresh_compiled()
        style = self.style.get()
        think = self._think()
        mem = self._memory()
        denoise = self._denoise()
        count = 4 if self.four_edits.get() else 1
        seed = random.randint(1, 2**31 - 1)

        def work():
            return generate_variations(
                self.app.client(), text, style=style, think=think,
                seed=seed, memory=mem, count=count,
                ref_path=src, denoise=denoise,
                aspect=self.aspect.get(), preset=self.outres.get(),
                exact=not think,
            )

        def done(paths, err):
            if err:
                self.app.set_status(f"Edit failed: {err}", "err")
                return
            self.vars = list(paths or [])
            self._render_grid()
            if self.vars:
                self.pick(0, remember=False)
                self.still = self.vars[0]
            for p in self.vars:
                self.app.lib.record_output(p, {"kind": "imagine_edit", "prompt": text, "src": str(src)})
            self.app.mind.note("edit", text, style=style, weight=2.5, path=str(self.vars[0] if self.vars else src))
            self.app.refresh_memory_label()
            self.app.set_status(f"Edited with your words · {len(self.vars)} result(s). Pick one or make video.", "ok")

        self.app.run_job(work, done, "Editing your photo to follow the prompt…")

    def image_video(self) -> None:
        src = self.still if self.still and Path(self.still).exists() else self._selected()
        if not src:
            self.app.set_status("Load a photo from this PC (or pick a variation) first.", "warn")
            return
        if not self._idea() and not self._motion():
            self.app.set_status("Write what the video should do — add, change, or how it should move.", "warn")
            return
        self._run_video(src)

    def text_video(self) -> None:
        text = self._idea()
        if not text:
            self.app.set_status("Write an idea first.", "warn")
            return
        src = None
        if self.still and Path(self.still).exists():
            src = Path(self.still)
        elif self.picked and self.vars and Path(self.picked).exists() and Path(self.picked) in [Path(p) for p in self.vars]:
            src = Path(self.picked)
        w, h = ASPECTS[self.aspect.get()]
        style = self.style.get()
        think = self._think()
        motion = self._motion()

        seconds = float(self.duration.get())

        def work():
            still = src
            if still is None:
                ones = generate_variations(
                    self.app.client(), text, style=style, think=think,
                    width=w, height=h, count=1,
                    aspect=self.aspect.get(), preset=self.outres.get(),
                    exact=not think, memory="" if not think else self._memory(),
                )
                still = ones[0]
            return still, imagine_video(
                self.app.client(), still, text=text, motion=motion, style=style, think=False,
                out_height=RESOLUTIONS.get(self.outres.get(), 720),
                duration=seconds,
            )

        def done(payload, err):
            if err:
                self.app.set_status(f"Video failed: {err}", "err")
                return
            still, path = payload
            self.app.last_image = still
            self.app.last_video = path
            self.app.mind.note("video", text, style=style, aspect=self.aspect.get(), weight=2.0, path=str(path))
            self.app.refresh_memory_label()
            self.app.set_status(f"Text → video ({int(seconds)}s, same hero) → {path.name}", "ok")
            os.startfile(path)

        self.app.run_job(work, done, f"Text → video, {int(seconds)} seconds, locking the same face…")

    def _run_video(self, src: Path) -> None:
        text = self._idea()
        style = self.style.get()
        think = self._think()
        motion = self._motion()

        height = RESOLUTIONS.get(self.outres.get(), 720)
        seconds = float(self.duration.get())

        def work():
            return imagine_video(
                self.app.client(), src, text=text, motion=motion, style=style, think=False,
                out_height=height, duration=seconds,
            )

        def done(path, err):
            if err:
                self.app.set_status(f"Video failed: {err}", "err")
                return
            self.app.last_video = path
            self.app.mind.note("video", text, style=style, aspect=self.aspect.get(), weight=2.0, path=str(path))
            self.app.refresh_memory_label()
            self.app.set_status(f"Video ready ({self.outres.get()}, {int(seconds)}s, same hero) → {path.name}", "ok")
            os.startfile(path)
            try:
                os.startfile(VIDEOS)
            except OSError:
                pass

        self.app.run_job(work, done, f"Animating {int(seconds)}s at {self.outres.get()}, same face…")

    def upscale_video(self) -> None:
        src = getattr(self.app, "last_video", None)
        if not src or not Path(src).exists():
            pick = filedialog.askopenfilename(title="Choose a video to scale", filetypes=[("Video", "*.mp4;*.mov;*.mkv;*.webm")])
            if not pick:
                self.app.set_status("No video to upscale.", "warn")
                return
            src = Path(pick)
        src = Path(src)
        preset = self.outres.get()
        height = RESOLUTIONS.get(preset, 720)
        dest = unique_out(VIDEOS, f"video_{preset}", ext=".mp4")

        def work():
            return scale_video(src, dest, height)

        def done(path, err):
            if err:
                self.app.set_status(f"Video scale failed: {err}", "err")
                return
            self.app.last_video = path
            self.app.set_status(f"Video {preset} → {path.name}", "ok")
            os.startfile(path)

        self.app.run_job(work, done, f"Scaling video to {preset}…")

    def browse(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose an image on this PC",
            filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.tif;*.tiff")],
        )
        if not path:
            return
        dest = import_local(Path(path))
        self._show_src(dest)
        self.app.set_status(f"Loaded from PC: {Path(path).name}", "ok")

    def paste_image(self) -> None:
        try:
            from PIL import ImageGrab

            grabbed = ImageGrab.grabclipboard()
        except Exception as exc:  # noqa: BLE001
            self.app.set_status(f"Clipboard failed: {exc}", "err")
            return
        if grabbed is None:
            self.app.set_status("Clipboard has no image. Copy a picture, then Paste.", "warn")
            return
        if isinstance(grabbed, list) and grabbed:
            dest = import_local(Path(grabbed[0]))
            self._show_src(dest, "Pasted file")
            self.app.set_status(f"Pasted file: {dest.name}", "ok")
            return
        if not isinstance(grabbed, Image.Image):
            self.app.set_status("Clipboard is not an image.", "warn")
            return
        dest = unique_out(OUTPUTS, "pasted")
        grabbed.convert("RGB").save(dest, "PNG")
        self._show_src(dest, "Pasted")
        self.app.set_status(f"Pasted image → {dest.name}", "ok")

    def clear_image(self) -> None:
        self.still = None
        self.src_lbl.configure(text="No image loaded — text-only Imagine.", text_color=theme.MUTED)
        self.app.set_status("Cleared loaded photo.", "info")
