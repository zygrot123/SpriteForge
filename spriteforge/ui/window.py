from __future__ import annotations

import threading
import traceback
from pathlib import Path

import customtkinter as ctk

from ..config import load_config, save_config
from ..engine.assets import Library
from ..engine.comfy import ComfyClient, ComfyError, start_comfy
from ..engine.memory import MemoryStore
from ..paths import LOG_PATH, OUTPUTS, ensure_dirs
from . import theme
from .chat import ChatPage
from .imagine import ImaginePage
from .memory import MemoryPage
from .studio import AnimatePage, GeneratePage, ModelsPage
from .workshop import ExportPage, LibraryPage, ScenesPage, SettingsPage, SheetsPage, StructuresPage


class SpriteForgeApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        theme.apply()
        ensure_dirs()
        self.cfg = load_config()
        self.lib = Library()
        self.mind = MemoryStore()
        self.busy = False
        self.last_image = None
        self.last_frames: list = []
        self.last_sheet = None
        self.last_video = None
        self._pages: dict[str, ctk.CTkFrame] = {}
        self._nav_btns: dict[str, ctk.CTkButton] = {}

        self.title("SpriteForge  —  local sprite studio")
        self.geometry("1280x820")
        self.minsize(1100, 720)
        self.configure(fg_color=theme.BG)
        theme.apply_icon(self)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_body()
        self._build_status()
        self.refresh_memory_label()
        self.show("generate")
        self.after(500, self.maybe_autostart)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def client(self) -> ComfyClient:
        return ComfyClient(self.cfg["comfy_url"], self.cfg.get("comfy_root") or "")

    def _build_sidebar(self) -> None:
        side = ctk.CTkFrame(self, width=210, fg_color=theme.PANEL, corner_radius=0)
        side.grid(row=0, column=0, rowspan=2, sticky="nsew")
        side.grid_propagate(False)

        brand = ctk.CTkLabel(
            side,
            text="SPRITEFORGE",
            text_color=theme.ACCENT,
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
        )
        brand.pack(padx=18, pady=(22, 2), anchor="w")
        ctk.CTkLabel(
            side,
            text="Free local sprite studio",
            text_color=theme.MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=12),
        ).pack(padx=18, pady=(0, 4), anchor="w")
        self.memory_lbl = ctk.CTkLabel(
            side,
            text="",
            text_color=theme.ACCENT,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            wraplength=180,
            justify="left",
            anchor="w",
        )
        self.memory_lbl.pack(padx=18, pady=(0, 16), anchor="w")

        items = [
            ("generate", "Generate"),
            ("imagine", "Imagine"),
            ("chat", "Forge chat"),
            ("models", "Lock model"),
            ("animate", "Animations"),
            ("structures", "Structures"),
            ("scenes", "Scenes"),
            ("sheets", "Sprite sheets"),
            ("export", "Export"),
            ("library", "Library"),
            ("memory", "Memory"),
            ("settings", "Settings"),
        ]
        for key, label in items:
            btn = ctk.CTkButton(
                side,
                text=label,
                anchor="w",
                height=38,
                fg_color="transparent",
                hover_color=theme.CARD,
                text_color=theme.TEXT,
                font=ctk.CTkFont(family="Segoe UI", size=14),
                command=lambda k=key: self.show(k),
            )
            btn.pack(fill="x", padx=10, pady=2)
            self._nav_btns[key] = btn

        self.comfy_dot = ctk.CTkLabel(
            side,
            text="●  ComfyUI  checking…",
            text_color=theme.MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=12),
        )
        self.comfy_dot.pack(side="bottom", padx=18, pady=18, anchor="w")

    def _build_body(self) -> None:
        self.body = ctk.CTkFrame(self, fg_color=theme.BG, corner_radius=0)
        self.body.grid(row=0, column=1, sticky="nsew")
        self.body.grid_columnconfigure(0, weight=1)
        self.body.grid_rowconfigure(0, weight=1)

        self._pages["generate"] = GeneratePage(self.body, self)
        self._pages["imagine"] = ImaginePage(self.body, self)
        self._pages["chat"] = ChatPage(self.body, self)
        self._pages["models"] = ModelsPage(self.body, self)
        self._pages["animate"] = AnimatePage(self.body, self)
        self._pages["structures"] = StructuresPage(self.body, self)
        self._pages["scenes"] = ScenesPage(self.body, self)
        self._pages["sheets"] = SheetsPage(self.body, self)
        self._pages["export"] = ExportPage(self.body, self)
        self._pages["library"] = LibraryPage(self.body, self)
        self._pages["memory"] = MemoryPage(self.body, self)
        self._pages["settings"] = SettingsPage(self.body, self)
        for page in self._pages.values():
            page.grid(row=0, column=0, sticky="nsew")

    def _build_status(self) -> None:
        bar = ctk.CTkFrame(self, height=36, fg_color=theme.PANEL, corner_radius=0)
        bar.grid(row=1, column=1, sticky="ew")
        self.status = ctk.CTkLabel(
            bar,
            text="Ready. Describe a sprite and hit Generate.",
            text_color=theme.MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            anchor="w",
        )
        self.status.pack(side="left", padx=16, pady=6, fill="x", expand=True)
        self.spin = ctk.CTkProgressBar(bar, width=140, height=8, progress_color=theme.ACCENT)
        self.spin.pack(side="right", padx=16)
        self.spin.set(0)

    def show(self, key: str) -> None:
        page = self._pages[key]
        page.tkraise()
        for k, btn in self._nav_btns.items():
            if k == key:
                btn.configure(fg_color=theme.CARD, text_color=theme.ACCENT)
            else:
                btn.configure(fg_color="transparent", text_color=theme.TEXT)
        if hasattr(page, "on_show"):
            page.on_show()

    def refresh_memory_label(self) -> None:
        if hasattr(self, "memory_lbl"):
            self.memory_lbl.configure(text=self.mind.summary())

    def set_status(self, text: str, kind: str = "info") -> None:
        colors = {"info": theme.MUTED, "ok": theme.OK, "warn": theme.WARN, "err": theme.WARM}
        self.status.configure(text=text, text_color=colors.get(kind, theme.MUTED))

    def run_job(self, work, on_done, start_msg: str = "Working…") -> None:
        if self.busy:
            self.set_status("Already generating — wait for the current job.", "warn")
            return
        self.busy = True
        self.set_status(start_msg, "info")
        self.spin.configure(mode="indeterminate")
        self.spin.start()

        def wrap() -> None:
            err = None
            result = None
            try:
                result = work()
            except Exception as exc:  # noqa: BLE001 — surface to UI
                err = exc
                traceback.print_exc()
            self.after(0, lambda: self._finish_job(on_done, result, err))

        threading.Thread(target=wrap, daemon=True).start()

    def _finish_job(self, on_done, result, err) -> None:
        self.busy = False
        self.spin.stop()
        self.spin.configure(mode="determinate")
        self.spin.set(0)
        on_done(result, err)

    def refresh_comfy(self) -> None:
        def check() -> dict:
            c = self.client()
            stats = c.ping()
            return {
                "flux": c.flux_ready(),
                "sdxl": c.sdxl_ready(),
                "gpu": (stats.get("devices") or [{}])[0].get("name", "GPU"),
            }

        def done(info, err) -> None:
            from ..bootstrap import inspect_install

            st = inspect_install()
            if err:
                self.comfy_dot.configure(text="●  ComfyUI  offline", text_color=theme.WARM)
                self.set_status("ComfyUI is offline. Open Settings → Download / repair.", "warn")
                return
            bits = ["ComfyUI"]
            if info.get("flux") or st.flux:
                bits.append("FLUX")
            if st.ffmpeg:
                bits.append("Video")
            self.comfy_dot.configure(text="●  " + " · ".join(bits), text_color=theme.OK)
            gpu = (info.get("gpu") or "").replace("cuda:0 ", "")
            miss = f" Missing: {', '.join(st.missing)}." if st.missing else ""
            self.set_status(f"Local ready on {gpu}. Sprites + animation + text-to-video.{miss}", "ok" if not miss else "warn")

        threading.Thread(target=lambda: self._check_comfy_bg(check, done), daemon=True).start()

    def _check_comfy_bg(self, check, done) -> None:
        try:
            info = check()
            self.after(0, lambda: done(info, None))
        except Exception as exc:  # noqa: BLE001
            self.after(0, lambda: done(None, exc))

    def maybe_autostart(self) -> None:
        def check() -> bool:
            return self.client().online()

        def after_check(online: bool, err) -> None:
            if online:
                self.refresh_comfy()
                return
            py = Path(self.cfg.get("comfy_python") or "")
            root = Path(self.cfg.get("comfy_root") or "")
            if py.exists() and (root / "main.py").exists():
                self.boot_comfy()
            else:
                self.comfy_dot.configure(text="●  Engine not installed", text_color=theme.WARM)
                self.set_status("Open Settings → Download engine to install ComfyUI + models on this PC.", "warn")

        def wrap() -> None:
            try:
                online = check()
                self.after(0, lambda: after_check(online, None))
            except Exception as exc:  # noqa: BLE001
                self.after(0, lambda: after_check(False, exc))

        threading.Thread(target=wrap, daemon=True).start()

    def boot_comfy(self) -> None:
        py = Path(self.cfg.get("comfy_python") or "")
        root = Path(self.cfg.get("comfy_root") or "")
        try:
            start_comfy(py, root, LOG_PATH)
        except ComfyError as exc:
            self.set_status(str(exc), "err")
            return
        self.set_status("Starting local engine… first load after install can take a minute.", "warn")
        self.after(8000, self.refresh_comfy)

    def persist(self) -> None:
        save_config(self.cfg)

    def _on_close(self) -> None:
        self.persist()
        self.destroy()


def run() -> None:
    app = SpriteForgeApp()
    app.mainloop()
