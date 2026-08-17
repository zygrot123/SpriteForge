from __future__ import annotations

from pathlib import Path

import customtkinter as ctk

from ..paths import BUNDLE, PROJECT, exe_dir, is_frozen

BG = "#0c0f14"
PANEL = "#141922"
CARD = "#1b2130"
LINE = "#2a3346"
TEXT = "#e8eef7"
MUTED = "#8b96ab"
ACCENT = "#3ee0c2"
ACCENT_DIM = "#1c4f47"
WARM = "#ff6b57"
WARN = "#f0c14b"
OK = "#5bd68a"


def apply() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")


def icon_path() -> Path | None:
    import sys

    candidates = [
        BUNDLE / "tools" / "spriteforge.ico",
        PROJECT / "tools" / "spriteforge.ico",
        exe_dir() / "spriteforge.ico",
        exe_dir() / "_internal" / "tools" / "spriteforge.ico",
    ]
    for p in candidates:
        if p.is_file():
            return p
    if is_frozen():
        exe = Path(sys.executable)
        if exe.is_file():
            return exe
    return None


def apply_icon(win) -> None:
    ico = icon_path()
    if ico is None:
        return
    path = str(ico)
    try:
        win.iconbitmap(path)
    except Exception:
        pass
    try:
        win.iconbitmap(default=path)
    except Exception:
        pass


def section(parent, title: str) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        parent,
        text=title.upper(),
        text_color=ACCENT,
        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        anchor="w",
    )


def muted(parent, text: str, wrap: int = 420) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        parent,
        text=text,
        text_color=MUTED,
        font=ctk.CTkFont(family="Segoe UI", size=13),
        wraplength=wrap,
        justify="left",
        anchor="w",
    )
