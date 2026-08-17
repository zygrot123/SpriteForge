"""Reuse-last-image buttons shared by Generate, Imagine, Structures, Scenes, Library."""
from __future__ import annotations

from pathlib import Path

import customtkinter as ctk

from ..engine.carry import SLOTS, suggest_slot
from . import theme


def add_bridge(parent, app, get_path, *, default_kind: str = "image", pad: int = 0) -> ctk.CTkFrame:
    box = ctk.CTkFrame(parent, fg_color=theme.CARD, corner_radius=10)
    if pad:
        box.pack(fill="x", padx=pad, pady=(8, 0))
    theme.section(box, "Use this in another tab").pack(anchor="w", padx=10, pady=(8, 4))
    theme.muted(box, "Hold it, drop it on Floors, or open it on Imagine.", wrap=300).pack(anchor="w", padx=10)
    slot = ctk.CTkOptionMenu(box, values=list(SLOTS), fg_color=theme.PANEL, width=160)
    slot.set(suggest_slot(default_kind))
    slot.pack(anchor="w", padx=10, pady=(6, 4))

    row = ctk.CTkFrame(box, fg_color="transparent")
    row.pack(fill="x", padx=10, pady=(0, 10))

    def path() -> Path | None:
        raw = get_path()
        if not raw:
            return None
        p = Path(raw)
        return p if p.exists() else None

    def hold() -> None:
        p = path()
        if not p:
            app.set_status("Generate or load an image first.", "warn")
            return
        app.hold(p, kind=default_kind)

    def to_floors() -> None:
        p = path()
        if not p:
            app.set_status("Generate or load an image first.", "warn")
            return
        app.send_to_floors(p, slot.get())

    def to_imagine() -> None:
        p = path()
        if not p:
            app.set_status("Generate or load an image first.", "warn")
            return
        app.send_to_imagine(p)

    ctk.CTkButton(row, text="Hold", width=70, height=28, fg_color=theme.CARD, command=hold).pack(side="left")
    ctk.CTkButton(row, text="To Floors", width=86, height=28, fg_color=theme.WARM, command=to_floors).pack(side="left", padx=6)
    ctk.CTkButton(row, text="To Imagine", width=90, height=28, fg_color=theme.ACCENT_DIM, command=to_imagine).pack(side="left")
    return box
