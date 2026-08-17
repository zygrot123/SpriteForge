"""A1111-style sampling / size / seed panel shared by Generate, Scenes, Structures."""
from __future__ import annotations

import random

import customtkinter as ctk

from ..engine.sampling import HIRES_SCALES, SAMPLER_LABELS, SCRIPTS, SampleSettings, parse_seed, snap16
from . import theme


class _ValueSlider(ctk.CTkFrame):
    def __init__(
        self,
        master,
        title: str,
        from_: float,
        to: float,
        value: float,
        *,
        integer: bool = False,
        steps: int | None = None,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self.integer = integer
        theme.section(self, title).pack(anchor="w")
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", pady=(2, 0))
        self.var = ctk.DoubleVar(value=value)
        self.lbl = ctk.CTkLabel(row, text=self._fmt(value), width=52, text_color=theme.TEXT, anchor="e")
        nsteps = steps if steps is not None else (int(to - from_) if integer else 100)
        self.slider = ctk.CTkSlider(
            row,
            from_=from_,
            to=to,
            number_of_steps=max(1, nsteps),
            variable=self.var,
            command=self._on,
            progress_color=theme.ACCENT,
            button_color=theme.ACCENT,
            fg_color=theme.LINE,
        )
        self.slider.pack(side="left", fill="x", expand=True)
        self.lbl.pack(side="left", padx=(8, 0))

    def _fmt(self, value: float) -> str:
        if self.integer:
            return str(int(round(value)))
        return f"{value:.1f}".rstrip("0").rstrip(".")

    def _on(self, value: float) -> None:
        if self.integer:
            value = int(round(float(value)))
            self.var.set(value)
        self.lbl.configure(text=self._fmt(float(value)))

    def get(self) -> float:
        v = float(self.var.get())
        return int(round(v)) if self.integer else v

    def set(self, value: float) -> None:
        self.var.set(value)
        self._on(value)


class GenPanel(ctk.CTkFrame):
    def __init__(self, master, app, *, default_w: int = 1024, default_h: int = 1024) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        cfg = app.cfg
        theme.section(self, "Generation").pack(anchor="w", pady=(12, 4))

        theme.section(self, "Sampling method").pack(anchor="w", pady=(8, 4))
        self.sampler = ctk.CTkOptionMenu(self, values=SAMPLER_LABELS, fg_color=theme.CARD)
        self.sampler.set(cfg.get("sampler", "Euler") if cfg.get("sampler") in SAMPLER_LABELS else "Euler")
        self.sampler.pack(fill="x")

        self.steps = _ValueSlider(self, "Sampling steps", 1, 50, int(cfg.get("steps", 20)), integer=True)
        self.steps.pack(fill="x", pady=(8, 0))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", pady=(10, 0))
        self.hires = ctk.CTkCheckBox(row, text="Hires. fix")
        self.hires.pack(side="left")
        if cfg.get("hires_fix"):
            self.hires.select()
        self.refiner = ctk.CTkCheckBox(row, text="Refiner")
        self.refiner.pack(side="left", padx=(16, 0))
        if cfg.get("refiner"):
            self.refiner.select()

        self.width = _ValueSlider(self, "Width", 256, 2048, snap16(default_w), integer=True, steps=112)
        self.width.pack(fill="x", pady=(8, 0))
        self.height = _ValueSlider(self, "Height", 256, 2048, snap16(default_h), integer=True, steps=112)
        self.height.pack(fill="x", pady=(8, 0))

        self.batch_count = _ValueSlider(self, "Batch count", 1, 8, int(cfg.get("batch_count", 1)), integer=True)
        self.batch_count.pack(fill="x", pady=(8, 0))
        self.batch_size = _ValueSlider(self, "Batch size", 1, 4, int(cfg.get("batch_size", 1)), integer=True)
        self.batch_size.pack(fill="x", pady=(8, 0))

        self.cfg = _ValueSlider(self, "CFG Scale", 1.0, 15.0, float(cfg.get("guidance", 3.5)), integer=False)
        self.cfg.pack(fill="x", pady=(8, 0))

        theme.section(self, "Seed").pack(anchor="w", pady=(10, 4))
        seed_row = ctk.CTkFrame(self, fg_color="transparent")
        seed_row.pack(fill="x")
        self.seed = ctk.CTkEntry(seed_row, placeholder_text="-1 = random")
        last = cfg.get("last_seed", -1)
        self.seed.insert(0, "-1")
        self.seed.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(seed_row, text="🎲", width=40, fg_color=theme.CARD, command=self.roll_seed).pack(side="left", padx=(6, 0))
        ctk.CTkButton(seed_row, text="↺", width=40, fg_color=theme.CARD, command=self.reuse_seed).pack(side="left", padx=(6, 0))
        self.extra = ctk.CTkCheckBox(seed_row, text="Extra", width=70, command=self._toggle_extra)
        self.extra.pack(side="left", padx=(8, 0))

        self.extra_box = ctk.CTkFrame(self, fg_color=theme.CARD, corner_radius=8)
        theme.section(self.extra_box, "Negative prompt").pack(anchor="w", padx=10, pady=(8, 4))
        self.negative = ctk.CTkTextbox(self.extra_box, height=64, fg_color=theme.PANEL)
        self.negative.pack(fill="x", padx=10)
        theme.section(self.extra_box, "Hires scale").pack(anchor="w", padx=10, pady=(8, 4))
        self.hires_scale = ctk.CTkOptionMenu(self.extra_box, values=HIRES_SCALES, fg_color=theme.PANEL)
        self.hires_scale.set(str(cfg.get("hires_scale", 2.0)))
        self.hires_scale.pack(fill="x", padx=10)
        self.hires_denoise = _ValueSlider(
            self.extra_box, "Hires denoise", 0.1, 1.0, float(cfg.get("hires_denoise", 0.45)), integer=False
        )
        self.hires_denoise.pack(fill="x", padx=10, pady=(6, 0))
        self.tiling = ctk.CTkCheckBox(self.extra_box, text="Tiling")
        self.tiling.pack(anchor="w", padx=10, pady=(8, 10))

        theme.section(self, "Script").pack(anchor="w", pady=(10, 4))
        self.script = ctk.CTkOptionMenu(self, values=SCRIPTS, fg_color=theme.CARD)
        self.script.set("None")
        self.script.pack(fill="x")

        self._last_used = int(last) if isinstance(last, int) else -1

    def _toggle_extra(self) -> None:
        if self.extra.get():
            self.extra_box.pack(fill="x", pady=(8, 0))
        else:
            self.extra_box.pack_forget()

    def reuse_seed(self) -> None:
        if self._last_used >= 0:
            self.set_seed(self._last_used)

    def roll_seed(self) -> None:
        self.set_seed(random.randint(1, 2**31 - 1))

    def set_seed(self, value: int) -> None:
        self.seed.delete(0, "end")
        self.seed.insert(0, str(int(value)))

    def set_size(self, width: int, height: int) -> None:
        self.width.set(snap16(width))
        self.height.set(snap16(height))

    def collect(self) -> SampleSettings:
        raw_seed = parse_seed(self.seed.get())
        seed = random.randint(1, 2**31 - 1) if raw_seed < 0 else raw_seed
        self._last_used = seed
        self.app.cfg["last_seed"] = seed
        self.app.cfg["sampler"] = self.sampler.get()
        self.app.cfg["steps"] = int(self.steps.get())
        self.app.cfg["guidance"] = float(self.cfg.get())
        self.app.cfg["batch_count"] = int(self.batch_count.get())
        self.app.cfg["batch_size"] = int(self.batch_size.get())
        self.app.cfg["hires_fix"] = bool(self.hires.get())
        self.app.cfg["refiner"] = bool(self.refiner.get())
        try:
            scale = float(self.hires_scale.get())
        except ValueError:
            scale = 2.0
        self.app.cfg["hires_scale"] = scale
        self.app.cfg["hires_denoise"] = float(self.hires_denoise.get())
        return SampleSettings(
            sampler=self.sampler.get(),
            steps=int(self.steps.get()),
            cfg=float(self.cfg.get()),
            width=snap16(int(self.width.get())),
            height=snap16(int(self.height.get())),
            batch_count=int(self.batch_count.get()),
            batch_size=int(self.batch_size.get()),
            seed=seed,
            last_seed=seed,
            hires_fix=bool(self.hires.get()),
            hires_scale=scale,
            hires_denoise=float(self.hires_denoise.get()),
            refiner=bool(self.refiner.get()),
            extra=bool(self.extra.get()),
            script=self.script.get(),
            negative=self.negative.get("1.0", "end").strip() if self.extra.get() else "",
            tiling=bool(self.tiling.get()) if self.extra.get() else False,
        )
