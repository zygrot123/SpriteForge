from __future__ import annotations

import os
import random
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from ..config import save_config
from ..engine.assets import compose_sheet, draw_grid_preview, process_sprite, slice_sheet, unique_out
from ..engine.quality import MODES, generate_quality, mode_key, mode_labels
from ..engine.motion import PRESENTATIONS, presentation_by_label, presentation_labels
from ..engine.lexicon import fluidize
from ..engine.prompts import SCENES, STRUCTURES, STYLES, compile_negative, compile_prompt
from ..engine.sampling import expand_script
from ..paths import EXPORTS, OUTPUTS, ROOT, SHEETS, VIDEOS
from . import theme
from .controls import GenPanel
from .mic import attach_mic
from .studio import BGS, SIZES, _style_key, _style_labels, _thumb, _view_labels


class StructuresPage(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color=theme.BG)
        self.app = app
        self.last: Path | None = None
        self._img = None
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        form = ctk.CTkScrollableFrame(self, fg_color=theme.PANEL, width=380, corner_radius=0)
        form.grid(row=0, column=0, sticky="nsew")
        ctk.CTkLabel(form, text="Structures & tiles", text_color=theme.TEXT, font=ctk.CTkFont("Segoe UI", 22, "bold")).pack(anchor="w", padx=18, pady=(18, 4))
        theme.muted(form, "Buildings, dungeon chunks, props, vegetation, doors, and seamless tiles — isolated so you can drop them in-engine.").pack(anchor="w", padx=18, pady=(0, 12))

        kinds = [v["label"] for v in STRUCTURES.values()]
        theme.section(form, "Kind").pack(anchor="w", padx=18, pady=(8, 4))
        self.kind = ctk.CTkOptionMenu(form, values=kinds, fg_color=theme.CARD)
        self.kind.pack(fill="x", padx=18)
        theme.section(form, "Describe").pack(anchor="w", padx=18, pady=(10, 4))
        self.prompt = ctk.CTkTextbox(form, height=110, fg_color=theme.CARD)
        self.prompt.pack(fill="x", padx=18)
        self.prompt.insert("1.0", "ruined abyss shrine gate, cracked black stone, cyan rune cracks, hanging chains")
        attach_mic(form, self.prompt, self.app)

        theme.section(form, "Style").pack(anchor="w", padx=18, pady=(10, 4))
        self.style = ctk.CTkOptionMenu(form, values=_style_labels(), fg_color=theme.CARD)
        self.style.set(STYLES["abyssal_iso"]["label"])
        self.style.pack(fill="x", padx=18)
        theme.section(form, "View").pack(anchor="w", padx=18, pady=(10, 4))
        self.view = ctk.CTkOptionMenu(form, values=_view_labels(), fg_color=theme.CARD)
        self.view.set("isometric")
        self.view.pack(fill="x", padx=18)
        theme.section(form, "Size preset").pack(anchor="w", padx=18, pady=(10, 4))
        self.size = ctk.CTkOptionMenu(form, values=list(SIZES.keys()), fg_color=theme.CARD, command=self._on_size)
        self.size.set("1024 × 1024  hero")
        self.size.pack(fill="x", padx=18)
        theme.section(form, "Background").pack(anchor="w", padx=18, pady=(10, 4))
        self.bg = ctk.CTkOptionMenu(form, values=BGS, fg_color=theme.CARD)
        self.bg.set("green")
        self.bg.pack(fill="x", padx=18)
        theme.section(form, "Quality engine").pack(anchor="w", padx=18, pady=(10, 4))
        self.quality = ctk.CTkOptionMenu(form, values=mode_labels(), fg_color=theme.CARD)
        self.quality.set(MODES.get(self.app.cfg.get("quality_mode", "quality"), MODES["quality"])["label"])
        self.quality.pack(fill="x", padx=18)
        self.key = ctk.CTkCheckBox(form, text="Punch out background")
        self.key.pack(anchor="w", padx=18, pady=10)
        self.key.select()
        self.gen = GenPanel(form, self.app, default_w=1024, default_h=1024)
        self.gen.pack(fill="x", padx=18)
        ctk.CTkButton(form, text="Generate structure", height=42, fg_color=theme.WARM, hover_color="#d45544", command=self.generate).pack(fill="x", padx=18, pady=16)

        right = ctk.CTkFrame(self, fg_color=theme.BG)
        right.grid(row=0, column=1, sticky="nsew", padx=16, pady=16)
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)
        self.preview = ctk.CTkLabel(right, text="Structure preview", text_color=theme.MUTED, fg_color=theme.CARD, corner_radius=12)
        self.preview.grid(row=0, column=0, sticky="nsew")
        ctk.CTkButton(right, text="Open outputs", fg_color=theme.CARD, command=lambda: os.startfile(OUTPUTS)).grid(row=1, column=0, sticky="w", pady=(10, 0))

    def _kind_key(self) -> str:
        label = self.kind.get()
        for k, v in STRUCTURES.items():
            if v["label"] == label:
                return k
        return "prop"

    def _on_size(self, label: str) -> None:
        if hasattr(self, "gen") and label in SIZES:
            w, h = SIZES[label]
            self.gen.set_size(w, h)

    def generate(self) -> None:
        text = self.prompt.get("1.0", "end").strip()
        if not text:
            self.app.set_status("Describe the structure.", "warn")
            return
        kind = self._kind_key()
        text, _notes = fluidize(text, expand=True)
        gs = self.gen.collect()
        qmode = mode_key(self.quality.get())
        self.app.cfg["quality_mode"] = qmode
        sampler_name, scheduler = gs.comfy_sampler()
        extra = "seamless tileable, repeating edges" if gs.tiling or kind == "tile" else ""

        def work():
            dest = None
            meta = {}
            idx = 0
            for chunk in expand_script(text, gs.script):
                prompt = compile_prompt(
                    chunk, style=_style_key(self.style.get()), view=self.view.get(),
                    bg=self.bg.get(), kind="structure", structure_kind=kind,
                    literal=True, chroma=bool(self.key.get()) and kind != "tile", extra=extra,
                )
                for b in range(max(1, gs.batch_count)):
                    seed = gs.seed + idx
                    dest, meta = generate_quality(
                        self.app.client(),
                        prompt,
                        mode=qmode,
                        engine=self.app.cfg.get("engine", "flux"),
                        seed=seed,
                        steps=gs.steps,
                        width=gs.width,
                        height=gs.height,
                        guidance=gs.cfg,
                        bg=self.bg.get(),
                        kind="tile" if kind == "tile" else "structure",
                        key=bool(self.key.get()) and kind != "tile",
                        negative=compile_negative("tile" if kind == "tile" else "sprite", extra=gs.negative),
                        prefix=f"struct_{kind}_{seed}",
                        dest_dir=OUTPUTS,
                        name=kind,
                        sampler_name=sampler_name,
                        scheduler=scheduler,
                        batch_size=gs.batch_size,
                        hires_fix=gs.hires_fix,
                        hires_scale=gs.hires_scale,
                        hires_denoise=gs.hires_denoise,
                        refiner=gs.refiner,
                    )
                    self.app.lib.record_output(dest, {"kind": kind, "prompt": chunk, "seed": seed, "score": meta})
                    idx += 1
            return dest, meta

        def done(payload, err):
            if err:
                self.app.set_status(f"Structure failed: {err}", "err")
                return
            path, meta = payload
            self.last = path
            img = _thumb(path, (720, 720))
            if img:
                self._img = img
                self.preview.configure(image=img, text="")
            self.app.mind.note(f"struct_{kind}", text, style=self.style.get(), weight=1.0, path=str(path))
            self.app.refresh_memory_label()
            self.app.set_status(f"Score {meta.get('total', 0):.0f}/100 · {path.name}", "ok")

        self.app.run_job(work, done, f"{MODES[qmode]['label']} — structure pipeline…")


class ScenesPage(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color=theme.BG)
        self.app = app
        self.last: Path | None = None
        self._img = None
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        form = ctk.CTkScrollableFrame(self, fg_color=theme.PANEL, width=380, corner_radius=0)
        form.grid(row=0, column=0, sticky="nsew")
        ctk.CTkLabel(form, text="Scenes, skies, walls", text_color=theme.TEXT, font=ctk.CTkFont("Segoe UI", 22, "bold")).pack(anchor="w", padx=18, pady=(18, 4))
        theme.muted(form, "Your description is sent as written. Style only tints the paint — it will not add a character. Isolated props punch out. Fill-frame skies and rooms stay full-bleed.").pack(anchor="w", padx=18, pady=(0, 12))

        kinds = [v["label"] for v in SCENES.values()]
        theme.section(form, "What to make").pack(anchor="w", padx=18, pady=(8, 4))
        self.kind = ctk.CTkOptionMenu(form, values=kinds, fg_color=theme.CARD, command=self._on_kind)
        self.kind.pack(fill="x", padx=18)
        self.hint = ctk.CTkLabel(form, text="", text_color=theme.MUTED, wraplength=320, justify="left", anchor="w")
        self.hint.pack(fill="x", padx=18, pady=(6, 0))

        theme.section(form, "Describe").pack(anchor="w", padx=18, pady=(10, 4))
        self.prompt = ctk.CTkTextbox(form, height=110, fg_color=theme.CARD)
        self.prompt.pack(fill="x", padx=18)
        attach_mic(form, self.prompt, self.app)

        theme.section(form, "Style").pack(anchor="w", padx=18, pady=(10, 4))
        self.style = ctk.CTkOptionMenu(form, values=_style_labels(), fg_color=theme.CARD)
        self.style.set(STYLES["abyssal_iso"]["label"])
        self.style.pack(fill="x", padx=18)
        theme.section(form, "View").pack(anchor="w", padx=18, pady=(10, 4))
        self.view = ctk.CTkOptionMenu(form, values=_view_labels(), fg_color=theme.CARD)
        self.view.pack(fill="x", padx=18)
        theme.section(form, "Size preset").pack(anchor="w", padx=18, pady=(10, 4))
        self.size = ctk.CTkOptionMenu(form, values=list(SIZES.keys()), fg_color=theme.CARD, command=self._on_size)
        self.size.pack(fill="x", padx=18)
        theme.section(form, "Key color (props only)").pack(anchor="w", padx=18, pady=(10, 4))
        self.bg = ctk.CTkOptionMenu(form, values=BGS, fg_color=theme.CARD)
        self.bg.set("green")
        self.bg.pack(fill="x", padx=18)
        theme.section(form, "Quality engine").pack(anchor="w", padx=18, pady=(10, 4))
        self.quality = ctk.CTkOptionMenu(form, values=mode_labels(), fg_color=theme.CARD)
        self.quality.set(MODES["fast"]["label"])
        self.quality.pack(fill="x", padx=18)
        self.key = ctk.CTkCheckBox(form, text="Punch out background")
        self.key.pack(anchor="w", padx=18, pady=10)
        self.gen = GenPanel(form, self.app, default_w=1280, default_h=720)
        self.gen.pack(fill="x", padx=18)
        theme.section(form, "Prompt sent to the model").pack(anchor="w", padx=18, pady=(10, 4))
        self.compiled = ctk.CTkTextbox(form, height=80, fg_color=theme.CARD, text_color=theme.MUTED, font=ctk.CTkFont("Consolas", 11))
        self.compiled.pack(fill="x", padx=18)
        ctk.CTkButton(form, text="Generate scene", height=42, fg_color=theme.WARM, hover_color="#d45544", command=self.generate).pack(fill="x", padx=18, pady=16)

        right = ctk.CTkFrame(self, fg_color=theme.BG)
        right.grid(row=0, column=1, sticky="nsew", padx=16, pady=16)
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)
        self.preview = ctk.CTkLabel(right, text="Scene preview", text_color=theme.MUTED, fg_color=theme.CARD, corner_radius=12)
        self.preview.grid(row=0, column=0, sticky="nsew")
        ctk.CTkButton(right, text="Open outputs", fg_color=theme.CARD, command=lambda: os.startfile(OUTPUTS)).grid(row=1, column=0, sticky="w", pady=(10, 0))
        self._on_kind(self.kind.get())

    def _kind_key(self) -> str:
        label = self.kind.get()
        for k, v in SCENES.items():
            if v["label"] == label:
                return k
        return "prop"

    def _on_kind(self, _label: str | None = None) -> None:
        spec = SCENES[self._kind_key()]
        pipe = spec.get("pipeline", "prop")
        self.hint.configure(text=spec.get("example", ""))
        view = spec.get("view", "front")
        if view in _view_labels():
            self.view.set(view)
        size = spec.get("size")
        if size and size in SIZES:
            self.size.set(size)
            if hasattr(self, "gen"):
                w, h = SIZES[size]
                self.gen.set_size(w, h)
        if pipe in {"plate", "tile"}:
            self.key.deselect()
        else:
            self.key.select()
        current = self.prompt.get("1.0", "end").strip()
        examples = {v.get("example", "") for v in SCENES.values()}
        if not current or current in examples:
            self.prompt.delete("1.0", "end")
            self.prompt.insert("1.0", spec.get("example", ""))

    def _on_size(self, label: str) -> None:
        if hasattr(self, "gen") and label in SIZES:
            w, h = SIZES[label]
            self.gen.set_size(w, h)

    def generate(self) -> None:
        text = self.prompt.get("1.0", "end").strip()
        if not text:
            self.app.set_status("Describe the sky, wall, or prop.", "warn")
            return
        kind = self._kind_key()
        spec = SCENES[kind]
        pipe = spec.get("pipeline", "prop")
        text, _notes = fluidize(text, expand=True)
        gs = self.gen.collect()
        bg = self.bg.get()
        key = bool(self.key.get()) and pipe == "prop"
        qmode = mode_key(self.quality.get())
        self.app.cfg["quality_mode"] = qmode
        qkind = "plate" if pipe == "plate" else ("tile" if pipe == "tile" else "structure")
        sampler_name, scheduler = gs.comfy_sampler()
        extra = "seamless tileable, repeating edges" if gs.tiling or pipe == "tile" else ""
        preview = compile_prompt(
            text,
            style=_style_key(self.style.get()),
            view=self.view.get(),
            bg=bg,
            kind="scene",
            structure_kind=kind,
            literal=True,
            chroma=key,
            extra=extra,
        )
        self.compiled.delete("1.0", "end")
        self.compiled.insert("1.0", preview)
        neg_kind = "plate" if pipe == "plate" else ("tile" if pipe == "tile" else "sprite")

        def work():
            dest = None
            meta = {}
            idx = 0
            for chunk in expand_script(text, gs.script):
                prompt = compile_prompt(
                    chunk,
                    style=_style_key(self.style.get()),
                    view=self.view.get(),
                    bg=bg,
                    kind="scene",
                    structure_kind=kind,
                    literal=True,
                    chroma=key,
                    extra=extra,
                )
                for _b in range(max(1, gs.batch_count)):
                    seed = gs.seed + idx
                    dest, meta = generate_quality(
                        self.app.client(),
                        prompt,
                        mode=qmode,
                        engine=self.app.cfg.get("engine", "flux"),
                        seed=seed,
                        steps=gs.steps,
                        width=gs.width,
                        height=gs.height,
                        guidance=gs.cfg,
                        bg=bg,
                        kind=qkind,
                        key=key,
                        negative=compile_negative(neg_kind, extra=gs.negative),
                        prefix=f"scene_{kind}_{seed}",
                        dest_dir=OUTPUTS,
                        name=kind,
                        sampler_name=sampler_name,
                        scheduler=scheduler,
                        batch_size=gs.batch_size,
                        hires_fix=gs.hires_fix,
                        hires_scale=gs.hires_scale,
                        hires_denoise=gs.hires_denoise,
                        refiner=gs.refiner,
                    )
                    self.app.lib.record_output(dest, {"kind": f"scene_{kind}", "prompt": chunk, "seed": seed, "score": meta})
                    idx += 1
            return dest, meta

        def done(payload, err):
            if err:
                self.app.set_status(f"Scene failed: {err}", "err")
                return
            path, meta = payload
            self.last = path
            img = _thumb(path, (900, 720))
            if img:
                self._img = img
                self.preview.configure(image=img, text="")
            self.app.mind.note(f"scene_{kind}", text, style=self.style.get(), weight=1.0, path=str(path))
            self.app.refresh_memory_label()
            self.app.set_status(f"{spec['label']} · score {meta.get('total', 0):.0f}/100 · {path.name}", "ok")

        self.app.run_job(work, done, f"Generating {spec['label'].lower()}…")


class SheetsPage(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color=theme.BG)
        self.app = app
        self.src: Path | None = None
        self.cells: list[Path] = []
        self._img = None
        self._play_img = None
        self._playing = False
        self._i = 0
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        form = ctk.CTkFrame(self, fg_color=theme.PANEL, width=340, corner_radius=0)
        form.grid(row=0, column=0, sticky="nsew")
        ctk.CTkLabel(form, text="Sprite sheets", text_color=theme.TEXT, font=ctk.CTkFont("Segoe UI", 22, "bold")).pack(anchor="w", padx=18, pady=(18, 8))
        ctk.CTkButton(form, text="Load sheet or image", fg_color=theme.CARD, command=self.load).pack(fill="x", padx=18, pady=6)
        theme.section(form, "Columns").pack(anchor="w", padx=18, pady=(12, 4))
        self.cols = ctk.CTkEntry(form)
        self.cols.insert(0, "8")
        self.cols.pack(fill="x", padx=18)
        theme.section(form, "Rows").pack(anchor="w", padx=18, pady=(10, 4))
        self.rows = ctk.CTkEntry(form)
        self.rows.insert(0, "1")
        self.rows.pack(fill="x", padx=18)
        ctk.CTkButton(form, text="Show grid overlay", fg_color=theme.CARD, command=self.overlay).pack(fill="x", padx=18, pady=(16, 6))
        ctk.CTkButton(form, text="Slice into frames", fg_color=theme.ACCENT_DIM, command=self.slice).pack(fill="x", padx=18, pady=6)
        ctk.CTkButton(form, text="Compose folder → sheet", fg_color=theme.CARD, command=self.compose_folder).pack(fill="x", padx=18, pady=6)
        row = ctk.CTkFrame(form, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=16)
        ctk.CTkButton(row, text="Play", width=80, fg_color=theme.ACCENT_DIM, command=self.play).pack(side="left")
        ctk.CTkButton(row, text="Stop", width=80, fg_color=theme.CARD, command=self.stop).pack(side="left", padx=8)

        right = ctk.CTkFrame(self, fg_color=theme.BG)
        right.grid(row=0, column=1, sticky="nsew", padx=16, pady=16)
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)
        self.preview = ctk.CTkLabel(right, text="Load a sheet", text_color=theme.MUTED, fg_color=theme.CARD, corner_radius=12)
        self.preview.grid(row=0, column=0, sticky="nsew")

    def load(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.webp")])
        if not path:
            return
        self.src = Path(path)
        self._show(self.src)

    def _show(self, path: Path) -> None:
        img = _thumb(path, (900, 700))
        if img:
            self._img = img
            self.preview.configure(image=img, text="")

    def overlay(self) -> None:
        if not self.src:
            return
        try:
            cols, rows = int(self.cols.get()), int(self.rows.get())
        except ValueError:
            self.app.set_status("Cols/rows must be numbers.", "warn")
            return
        im = draw_grid_preview(self.src, cols, rows)
        tmp = SHEETS / "_overlay_preview.png"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        im.save(tmp)
        self._show(tmp)

    def slice(self) -> None:
        if not self.src:
            self.app.set_status("Load a sheet first.", "warn")
            return
        cols, rows = int(self.cols.get()), int(self.rows.get())
        dest = SHEETS / f"{self.src.stem}_cells"
        self.cells = slice_sheet(self.src, dest, cols, rows)
        self.app.set_status(f"Sliced {len(self.cells)} cells → {dest}", "ok")
        os.startfile(dest)

    def compose_folder(self) -> None:
        folder = filedialog.askdirectory()
        if not folder:
            return
        frames = sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in {".png", ".jpg", ".webp"})
        if not frames:
            self.app.set_status("No images in that folder.", "warn")
            return
        dest = unique_out(SHEETS, "composed")
        compose_sheet(frames, dest)
        self.src = dest
        self.cells = frames
        self._show(dest)
        self.app.set_status(f"Composed {len(frames)} frames → {dest.name}", "ok")

    def play(self) -> None:
        if not self.cells:
            self.app.set_status("Slice a sheet or compose a folder first.", "warn")
            return
        self._playing = True
        self._i = 0
        self._tick()

    def _tick(self) -> None:
        if not self._playing or not self.cells:
            return
        path = self.cells[self._i % len(self.cells)]
        img = _thumb(path, (512, 512))
        if img:
            self._play_img = img
            self.preview.configure(image=img, text="")
        self._i += 1
        self.after(140, self._tick)

    def stop(self) -> None:
        self._playing = False


class ExportPage(ctk.CTkFrame):
    KINDS = {
        "PNG frames": "png",
        "JPEG frames": "jpeg",
        "Sprite sheet PNG": "sheet",
        "Sprites file (folder + json)": "sprites",
        "ZIP pack": "zip",
        "RAR pack": "rar",
        "Unity pack": "unity",
        "Unreal pack": "unreal",
        "Godot pack": "godot",
        "MP4 video": "mp4",
    }

    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color=theme.BG)
        self.app = app
        self.picked: list[Path] = []
        form = ctk.CTkScrollableFrame(self, fg_color=theme.BG)
        form.pack(fill="both", expand=True, padx=20, pady=18)
        ctk.CTkLabel(form, text="Export", text_color=theme.TEXT, font=ctk.CTkFont("Segoe UI", 22, "bold")).pack(anchor="w")
        theme.muted(form, "Send frames to Unity, Unreal, Godot, or any folder. Pack as ZIP/RAR, PNG, JPEG, a sprites file, or MP4. Text-to-video and image-to-video are at the bottom.", wrap=780).pack(anchor="w", pady=(4, 14))

        theme.section(form, "Source").pack(anchor="w", pady=(8, 4))
        row = ctk.CTkFrame(form, fg_color="transparent")
        row.pack(anchor="w", pady=4)
        ctk.CTkButton(row, text="Last animation", fg_color=theme.CARD, command=self.use_anim).pack(side="left")
        ctk.CTkButton(row, text="Last image", fg_color=theme.CARD, command=self.use_image).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Browse files", fg_color=theme.CARD, command=self.browse_files).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Browse folder", fg_color=theme.CARD, command=self.browse_folder).pack(side="left", padx=6)
        self.src_lbl = ctk.CTkLabel(form, text="Nothing selected", text_color=theme.MUTED, anchor="w")
        self.src_lbl.pack(fill="x", pady=(4, 8))

        theme.section(form, "Pack name").pack(anchor="w", pady=(8, 4))
        self.name = ctk.CTkEntry(form, width=360)
        self.name.insert(0, "sprite_pack")
        self.name.pack(anchor="w")
        theme.section(form, "Format").pack(anchor="w", pady=(10, 4))
        self.kind = ctk.CTkOptionMenu(form, values=list(self.KINDS), fg_color=theme.CARD, width=320)
        self.kind.set("ZIP pack")
        self.kind.pack(anchor="w")
        theme.section(form, "FPS (video / clips)").pack(anchor="w", pady=(10, 4))
        self.fps = ctk.CTkOptionMenu(form, values=["8", "10", "12", "15", "24"], fg_color=theme.CARD, width=120)
        self.fps.set("12")
        self.fps.pack(anchor="w")

        brow = ctk.CTkFrame(form, fg_color="transparent")
        brow.pack(anchor="w", pady=16)
        ctk.CTkButton(brow, text="Export", height=40, fg_color=theme.WARM, command=self.export).pack(side="left")
        ctk.CTkButton(brow, text="Export into my project folder…", height=40, fg_color=theme.ACCENT_DIM, command=self.export_into).pack(side="left", padx=8)
        ctk.CTkButton(brow, text="Open exports", fg_color=theme.CARD, command=lambda: os.startfile(EXPORTS)).pack(side="left", padx=8)

        theme.section(form, "Text → video").pack(anchor="w", pady=(22, 4))
        theme.muted(form, "Writes a still, animates it, then encodes MP4. Uses your local Flux + ffmpeg. Optional SpaceXAI video if a key is in Settings.", wrap=720).pack(anchor="w")
        self.t2v_cam = ctk.CTkOptionMenu(form, values=presentation_labels(), fg_color=theme.CARD, width=320)
        self.t2v_cam.set(PRESENTATIONS["hades"]["label"])
        self.t2v_cam.pack(anchor="w", pady=(4, 6))
        self.t2v = ctk.CTkTextbox(form, height=70, fg_color=theme.CARD)
        self.t2v.pack(fill="x", pady=6)
        self.t2v.insert("1.0", "the locked knight walks in place, camera locked")
        ctk.CTkButton(form, text="Generate text-to-video", fg_color=theme.WARM, command=self.text_video).pack(anchor="w", pady=6)

        theme.section(form, "Image → video").pack(anchor="w", pady=(16, 4))
        theme.muted(form, "Pick a still (or last image) and describe the motion. Same local pipeline, or SpaceXAI if enabled.", wrap=720).pack(anchor="w")
        self.i2v = ctk.CTkEntry(form, width=520, placeholder_text="the character jumps in place, then lands")
        self.i2v.pack(anchor="w", pady=6)
        irow = ctk.CTkFrame(form, fg_color="transparent")
        irow.pack(anchor="w")
        ctk.CTkButton(irow, text="Choose still…", fg_color=theme.CARD, command=self.pick_still).pack(side="left")
        ctk.CTkButton(irow, text="Generate image-to-video", fg_color=theme.WARM, command=self.image_video).pack(side="left", padx=8)
        self.still: Path | None = None

    def _files(self) -> list[Path]:
        if self.picked:
            return self.picked
        frames = getattr(self.app, "last_frames", None) or []
        if frames:
            return [Path(p) for p in frames]
        img = getattr(self.app, "last_image", None)
        if img and Path(img).exists():
            return [Path(img)]
        return []

    def _refresh_src(self) -> None:
        files = self._files()
        self.src_lbl.configure(text=f"{len(files)} file(s) ready" if files else "Nothing selected — generate or browse.")

    def on_show(self) -> None:
        self._refresh_src()

    def use_anim(self) -> None:
        self.picked = [Path(p) for p in (getattr(self.app, "last_frames", None) or [])]
        self._refresh_src()

    def use_image(self) -> None:
        img = getattr(self.app, "last_image", None)
        self.picked = [Path(img)] if img and Path(img).exists() else []
        self._refresh_src()

    def browse_files(self) -> None:
        paths = filedialog.askopenfilenames(filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.webp")])
        self.picked = [Path(p) for p in paths]
        self._refresh_src()

    def browse_folder(self) -> None:
        folder = filedialog.askdirectory()
        if folder:
            from ..engine.export import collect_images
            self.picked = collect_images(Path(folder))
        self._refresh_src()

    def pick_still(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.webp")])
        if path:
            self.still = Path(path)
            self.app.set_status(f"Still: {self.still.name}", "ok")

    def export(self) -> None:
        self._do_export(None)

    def export_into(self) -> None:
        folder = filedialog.askdirectory(title="Pick Unity / Unreal / Godot / any project folder")
        if not folder:
            return
        self._do_export(Path(folder))

    def _do_export(self, project: Path | None) -> None:
        from ..engine.export import build_pack, paste_into_project

        files = self._files()
        if not files:
            self.app.set_status("Pick frames or an image first.", "warn")
            return
        kind = self.KINDS[self.kind.get()]
        name = self.name.get().strip() or "sprite_pack"
        fps = int(self.fps.get())

        def work():
            pack = build_pack(files, name=name, kind=kind, fps=fps)
            if project:
                pack = paste_into_project(pack, project)
            return pack

        def done(pack, err):
            if err:
                self.app.set_status(f"Export failed: {err}", "err")
                return
            self.app.set_status(f"Exported → {pack}", "ok")
            os.startfile(pack if Path(pack).is_dir() else Path(pack).parent)

        self.app.run_job(work, done, f"Exporting {kind} pack…")

    def text_video(self) -> None:
        prompt = self.t2v.get("1.0", "end").strip()
        if not prompt:
            self.app.set_status("Write what should happen in the video.", "warn")
            return
        self._make_video(prompt, None)

    def image_video(self) -> None:
        still = self.still or getattr(self.app, "last_image", None)
        if not still or not Path(still).exists():
            self.app.set_status("Choose a still image first.", "warn")
            return
        motion = self.i2v.get().strip() or "the subject moves in place, camera locked"
        self._make_video(motion, Path(still))

    def _make_video(self, prompt: str, still: Path | None) -> None:
        from ..engine.video import animate_to_video
        from ..engine.xai import XAIClient, XAIError
        from ..paths import VIDEOS

        key = (self.app.cfg.get("xai_api_key") or "").strip()
        use_cloud = bool(self.app.cfg.get("xai_enabled")) and bool(key)

        def work():
            if use_cloud:
                dest = VIDEOS / f"cloud_{Path(still).stem if still else 't2v'}.mp4"
                return XAIClient(key).video(prompt, dest, image_path=still, duration=6)
            _pk, pres = presentation_by_label(self.t2v_cam.get())
            return animate_to_video(
                self.app.client(),
                prompt_text=prompt,
                ref_path=still,
                nframes=8,
                fps=int(self.fps.get()),
                view=pres.get("view", "side"),
                presentation=_pk,
            )[0]

        def done(path, err):
            if err:
                self.app.set_status(f"Video failed: {err}", "err")
                return
            self.app.set_status(f"Video ready → {path}", "ok")
            os.startfile(path)

        self.app.run_job(work, done, "Rendering video…")


class LibraryPage(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color=theme.BG)
        self.app = app
        self._thumbs: list[ctk.CTkImage] = []
        ctk.CTkLabel(self, text="Library", text_color=theme.TEXT, font=ctk.CTkFont("Segoe UI", 22, "bold")).pack(anchor="w", padx=18, pady=(18, 4))
        theme.muted(self, "Recent outputs from Generate, Animations, and Structures.", wrap=800).pack(anchor="w", padx=18)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=10)
        ctk.CTkButton(row, text="Refresh", fg_color=theme.CARD, command=self.refresh).pack(side="left")
        ctk.CTkButton(row, text="Open library folder", fg_color=theme.CARD, command=lambda: os.startfile(OUTPUTS)).pack(side="left", padx=8)
        self.gridf = ctk.CTkScrollableFrame(self, fg_color=theme.BG)
        self.gridf.pack(fill="both", expand=True, padx=12, pady=8)

    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        for w in self.gridf.winfo_children():
            w.destroy()
        self._thumbs.clear()
        files = self.app.lib.recent_outputs(48)
        if not files:
            ctk.CTkLabel(self.gridf, text="Nothing generated yet.", text_color=theme.MUTED).pack(pady=20)
            return
        for i, path in enumerate(files):
            cell = ctk.CTkFrame(self.gridf, fg_color=theme.CARD, width=188)
            cell.grid(row=i // 5, column=i % 5, padx=8, pady=8, sticky="n")
            img = _thumb(path, (160, 160))
            if img:
                self._thumbs.append(img)
                thumb = ctk.CTkLabel(cell, image=img, text="")
                thumb.pack(padx=8, pady=(8, 2))
                thumb.bind("<Double-Button-1>", lambda _e, p=path: os.startfile(p))
            ctk.CTkLabel(cell, text=path.name[:22], text_color=theme.MUTED, font=ctk.CTkFont("Segoe UI", 11)).pack()
            btns = ctk.CTkFrame(cell, fg_color="transparent")
            btns.pack(fill="x", padx=8, pady=(4, 10))
            ctk.CTkButton(
                btns, text="Open", width=70, height=26, fg_color=theme.CARD,
                command=lambda p=path: os.startfile(p),
            ).pack(side="left")
            ctk.CTkButton(
                btns, text="Delete", width=70, height=26, fg_color="#4a2430",
                hover_color="#6a3040", command=lambda p=path: self.delete_one(p),
            ).pack(side="right")

    def delete_one(self, path: Path) -> None:
        from tkinter import messagebox

        if not messagebox.askyesno("Delete sprite", f"Delete this file permanently?\n\n{path.name}"):
            return
        try:
            self.app.lib.delete_output(path)
        except OSError as exc:
            self.app.set_status(f"Could not delete: {exc}", "err")
            return
        self.refresh()
        self.app.set_status(f"Deleted {path.name}", "ok")


class SettingsPage(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color=theme.BG)
        self.app = app
        box = ctk.CTkScrollableFrame(self, fg_color=theme.BG)
        box.pack(fill="both", expand=True, padx=20, pady=18)
        ctk.CTkLabel(box, text="Settings", text_color=theme.TEXT, font=ctk.CTkFont("Segoe UI", 22, "bold")).pack(anchor="w")
        theme.muted(box, "On launch the app checks ComfyUI, FLUX, and ffmpeg. Missing files download locally. Text-to-video uses Flux frames + ffmpeg — no cloud required.", wrap=720).pack(anchor="w", pady=(4, 16))
        from ..bootstrap import inspect_install
        st = inspect_install()
        lines = "  |  ".join(("OK " if ok else "NO ") + name for name, ok, _w in st.checklist())
        ctk.CTkLabel(box, text=lines, text_color=theme.ACCENT if st.video_ready else theme.WARN, wraplength=720, justify="left").pack(anchor="w", pady=(0, 10))

        theme.section(box, "ComfyUI URL").pack(anchor="w", pady=(8, 4))
        self.url = ctk.CTkEntry(box, width=480)
        self.url.insert(0, self.app.cfg["comfy_url"])
        self.url.pack(anchor="w")
        theme.section(box, "ComfyUI folder").pack(anchor="w", pady=(10, 4))
        self.root = ctk.CTkEntry(box, width=640)
        self.root.insert(0, self.app.cfg.get("comfy_root") or "")
        self.root.pack(anchor="w")
        theme.section(box, "ComfyUI python").pack(anchor="w", pady=(10, 4))
        self.py = ctk.CTkEntry(box, width=640)
        self.py.insert(0, self.app.cfg.get("comfy_python") or "")
        self.py.pack(anchor="w")

        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(anchor="w", pady=12)
        ctk.CTkButton(row, text="Ping engine", fg_color=theme.CARD, command=self.app.refresh_comfy).pack(side="left")
        ctk.CTkButton(row, text="Start engine", fg_color=theme.ACCENT_DIM, command=self.app.boot_comfy).pack(side="left", padx=8)
        ctk.CTkButton(row, text="Setup / updates / fix", fg_color=theme.WARM, command=self.repair).pack(side="left", padx=8)
        ctk.CTkButton(row, text="Open data folder", fg_color=theme.CARD, command=lambda: os.startfile(ROOT)).pack(side="left", padx=8)

        theme.section(box, "Local engine").pack(anchor="w", pady=(16, 4))
        self.engine = ctk.CTkOptionMenu(box, values=["flux", "sdxl"], fg_color=theme.CARD, width=200)
        self.engine.set(self.app.cfg.get("engine", "flux"))
        self.engine.pack(anchor="w")
        theme.section(box, "Steps").pack(anchor="w", pady=(10, 4))
        self.steps = ctk.CTkEntry(box, width=120)
        self.steps.insert(0, str(self.app.cfg.get("steps", 24)))
        self.steps.pack(anchor="w")
        theme.section(box, "FLUX guidance").pack(anchor="w", pady=(10, 4))
        self.guidance = ctk.CTkEntry(box, width=120)
        self.guidance.insert(0, str(self.app.cfg.get("guidance", 3.5)))
        self.guidance.pack(anchor="w")

        theme.section(box, "Optional SpaceXAI (not required)").pack(anchor="w", pady=(18, 4))
        theme.muted(box, "Local Flux is the free path. If you later add an XAI_API_KEY you can switch image edits to grok-imagine-image-2.0 — leave this blank to stay 100% free.", wrap=720).pack(anchor="w")
        self.xai = ctk.CTkEntry(box, width=480, placeholder_text="xai-…", show="•")
        if self.app.cfg.get("xai_api_key"):
            self.xai.insert(0, self.app.cfg["xai_api_key"])
        self.xai.pack(anchor="w", pady=(6, 4))

        ctk.CTkButton(box, text="Save settings", fg_color=theme.WARM, command=self.save).pack(anchor="w", pady=18)

    def save(self) -> None:
        self.app.cfg["comfy_url"] = self.url.get().strip()
        self.app.cfg["comfy_root"] = self.root.get().strip()
        self.app.cfg["comfy_python"] = self.py.get().strip()
        self.app.cfg["engine"] = self.engine.get()
        try:
            self.app.cfg["steps"] = int(self.steps.get())
            self.app.cfg["guidance"] = float(self.guidance.get())
        except ValueError:
            self.app.set_status("Steps/guidance must be numbers.", "warn")
            return
        self.app.cfg["xai_api_key"] = self.xai.get().strip()
        self.app.cfg["xai_enabled"] = bool(self.app.cfg["xai_api_key"])
        save_config(self.app.cfg)
        self.app.set_status("Settings saved.", "ok")
        self.app.refresh_comfy()

    def repair(self) -> None:
        from ..config import load_config
        from ..ui.setup import SetupWizard

        wiz = SetupWizard(self.app)
        wiz.wait(self.app)
        if wiz.result:
            self.app.cfg = load_config()
            self.root.delete(0, "end")
            self.root.insert(0, self.app.cfg.get("comfy_root") or "")
            self.py.delete(0, "end")
            self.py.insert(0, self.app.cfg.get("comfy_python") or "")
            self.app.maybe_autostart()
