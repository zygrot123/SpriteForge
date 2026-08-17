from __future__ import annotations

import threading
import traceback
from pathlib import Path

import customtkinter as ctk

from ..config import load_config, save_config
from ..engine.assets import Library
from ..engine.comfy import ComfyClient, ComfyError, start_comfy
from ..engine.memory import MemoryStore
from ..engine.progress import IDLE_HELP, JobClock, fmt_secs, record_sample
from ..paths import LOG_PATH, OUTPUTS, ensure_dirs
from . import theme
from .chat import ChatPage
from .floors import FloorsPage
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
        self.last_structure = None
        self.last_scene = None
        self.hold_path = None
        self.hold_kind = ""
        self.hold_label = ""
        self._pages: dict[str, ctk.CTkFrame] = {}
        self._nav_btns: dict[str, ctk.CTkButton] = {}
        self._clock: JobClock | None = None
        self._pulse_id: str | None = None
        self._help_win = None
        self._status_title = "Ready. Describe a sprite and hit Generate."
        self._status_kind = "info"

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
        c = ComfyClient(self.cfg["comfy_url"], self.cfg.get("comfy_root") or "")
        c.on_progress = self.report_progress
        if self._clock:
            c.job_item = self._clock.item
            c.job_items = self._clock.items
        return c

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
            ("floors", "Floors"),
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
        self.comfy_dot.pack(side="bottom", padx=18, pady=(4, 14), anchor="w")

        hold = ctk.CTkFrame(side, fg_color=theme.CARD, corner_radius=8)
        hold.pack(side="bottom", fill="x", padx=12, pady=(0, 8))
        ctk.CTkLabel(hold, text="IN HAND", text_color=theme.ACCENT, font=ctk.CTkFont("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(8, 0))
        self.hold_lbl = ctk.CTkLabel(hold, text="Nothing held. Generate, then send it here.", text_color=theme.MUTED, wraplength=170, justify="left", anchor="w")
        self.hold_lbl.pack(fill="x", padx=10, pady=(2, 6))
        hrow = ctk.CTkFrame(hold, fg_color="transparent")
        hrow.pack(fill="x", padx=8, pady=(0, 8))
        ctk.CTkButton(hrow, text="Floors", width=54, height=24, fg_color=theme.WARM, command=self._hold_to_floors).pack(side="left")
        ctk.CTkButton(hrow, text="Imagine", width=62, height=24, fg_color=theme.ACCENT_DIM, command=self._hold_to_imagine).pack(side="left", padx=4)
        ctk.CTkButton(hrow, text="×", width=28, height=24, fg_color=theme.CARD, command=self.clear_hold).pack(side="left")

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
        self._pages["floors"] = FloorsPage(self.body, self)
        self._pages["scenes"] = ScenesPage(self.body, self)
        self._pages["sheets"] = SheetsPage(self.body, self)
        self._pages["export"] = ExportPage(self.body, self)
        self._pages["library"] = LibraryPage(self.body, self)
        self._pages["memory"] = MemoryPage(self.body, self)
        self._pages["settings"] = SettingsPage(self.body, self)
        for page in self._pages.values():
            page.grid(row=0, column=0, sticky="nsew")

    def _build_status(self) -> None:
        bar = ctk.CTkFrame(self, height=42, fg_color=theme.PANEL, corner_radius=0)
        bar.grid(row=1, column=1, sticky="ew")
        self.status = ctk.CTkLabel(
            bar,
            text="Ready. Describe a sprite and hit Generate.",
            text_color=theme.MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            anchor="w",
        )
        self.status.pack(side="left", padx=(16, 8), pady=6, fill="x", expand=True)
        self.eta_lbl = ctk.CTkLabel(
            bar, text="", text_color=theme.WARN,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            width=110, anchor="e",
        )
        self.eta_lbl.pack(side="left", padx=(0, 6))
        self.help_btn = ctk.CTkButton(
            bar, text="?", width=28, height=26, fg_color=theme.CARD,
            hover_color=theme.LINE, text_color=theme.TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            command=self._show_job_help,
        )
        self.help_btn.pack(side="left", padx=(0, 8))
        self.pct_lbl = ctk.CTkLabel(
            bar, text="", text_color=theme.ACCENT,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            width=44, anchor="e",
        )
        self.pct_lbl.pack(side="left", padx=(0, 8))
        self.spin = ctk.CTkProgressBar(bar, width=180, height=10, progress_color=theme.ACCENT)
        self.spin.pack(side="right", padx=(0, 16), pady=12)
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

    def hold(self, path, kind: str = "image", label: str = "") -> None:
        p = Path(path) if path else None
        if not p or not p.exists():
            self.set_status("That file is missing.", "warn")
            return
        self.hold_path = p
        self.hold_kind = kind or "image"
        self.hold_label = label or p.name
        self.last_image = p
        if kind.startswith("struct") or kind in {"tile", "dungeon", "building", "gate", "prop"}:
            self.last_structure = p
        if kind.startswith("scene") or kind in {"floor", "wall", "water", "sky", "backdrop", "interior"}:
            self.last_scene = p
        if hasattr(self, "hold_lbl"):
            self.hold_lbl.configure(text=f"{self.hold_label}", text_color=theme.TEXT)
        self.set_status(f"In hand: {p.name} — send it to Floors or Imagine.", "ok")

    def clear_hold(self) -> None:
        self.hold_path = None
        self.hold_kind = ""
        self.hold_label = ""
        if hasattr(self, "hold_lbl"):
            self.hold_lbl.configure(text="Nothing held. Generate, then send it here.", text_color=theme.MUTED)
        self.set_status("Cleared the tray.", "info")

    def send_to_floors(self, path, slot: str = "floor") -> None:
        p = Path(path)
        if not p.exists():
            self.set_status("That file is missing.", "warn")
            return
        self.hold(p, kind=slot, label=p.name)
        self.show("floors")
        page = self._pages.get("floors")
        if page and hasattr(page, "receive"):
            page.receive(p, slot)

    def send_to_imagine(self, path) -> None:
        p = Path(path)
        if not p.exists():
            self.set_status("That file is missing.", "warn")
            return
        self.hold(p, kind="image", label=p.name)
        self.show("imagine")
        page = self._pages.get("imagine")
        if page and hasattr(page, "_show_src"):
            page._show_src(p, "From another tab")

    def _hold_to_floors(self) -> None:
        if not self.hold_path:
            self.set_status("Hold an image first — generate or pick one.", "warn")
            return
        from ..engine.carry import suggest_slot

        self.send_to_floors(self.hold_path, suggest_slot(self.hold_kind))

    def _hold_to_imagine(self) -> None:
        if not self.hold_path:
            self.set_status("Hold an image first — generate or pick one.", "warn")
            return
        self.send_to_imagine(self.hold_path)

    def set_status(self, text: str, kind: str = "info") -> None:
        colors = {"info": theme.MUTED, "ok": theme.OK, "warn": theme.WARN, "err": theme.WARM}
        self._status_title = text
        self._status_kind = kind
        if self.busy and self._clock:
            self._refresh_job_label()
            return
        self.status.configure(text=text, text_color=colors.get(kind, theme.MUTED))

    def report_progress(self, ev: dict | None = None, **kw) -> None:
        payload = dict(ev or {})
        payload.update(kw)
        if threading.current_thread() is not threading.main_thread():
            self.after(0, lambda p=payload: self._apply_progress(p))
            return
        self._apply_progress(payload)

    def _apply_progress(self, ev: dict) -> None:
        if not self.busy:
            return
        if self._clock is None:
            self._clock = JobClock(self._status_title or "Working…")
        self._clock.apply(ev)
        self._refresh_job_label()

    def _refresh_job_label(self) -> None:
        clock = self._clock
        if not clock:
            return
        self.status.configure(text=clock.line(), text_color=theme.TEXT)
        eta = clock.eta()
        if eta is None or (clock.elapsed() < 2 and clock.percent() < 4):
            self.eta_lbl.configure(text="estimating…")
        else:
            self.eta_lbl.configure(text=f"{fmt_secs(eta)} left")
        self.pct_lbl.configure(text=f"{clock.percent()}%")
        self.spin.set(clock.frac())
        if self._help_win is not None:
            try:
                if self._help_win.winfo_exists() and hasattr(self, "_help_box"):
                    self._help_box.configure(state="normal")
                    self._help_box.delete("1.0", "end")
                    self._help_box.insert("1.0", clock.help_text())
                    self._help_box.configure(state="disabled")
            except Exception:
                pass

    def _pulse_job(self) -> None:
        self._pulse_id = None
        if not self.busy:
            return
        self._refresh_job_label()
        self._pulse_id = self.after(400, self._pulse_job)

    def _show_job_help(self) -> None:
        if self._help_win is not None:
            try:
                if self._help_win.winfo_exists():
                    self._help_win.destroy()
                    self._help_win = None
                    return
            except Exception:
                self._help_win = None
        win = ctk.CTkToplevel(self)
        win.title("What is Flux doing?")
        win.geometry("480x360")
        win.configure(fg_color=theme.PANEL)
        win.attributes("-topmost", True)
        body = self._clock.help_text() if self._clock else IDLE_HELP
        box = ctk.CTkTextbox(win, fg_color=theme.CARD, text_color=theme.TEXT, wrap="word", font=ctk.CTkFont("Segoe UI", 13))
        box.pack(fill="both", expand=True, padx=14, pady=14)
        box.insert("1.0", body)
        box.configure(state="disabled")
        self._help_box = box
        self._help_win = win

        def _gone(_e=None) -> None:
            self._help_win = None

        win.protocol("WM_DELETE_WINDOW", lambda: (win.destroy(), _gone()))

    def run_job(self, work, on_done, start_msg: str = "Working…", items: int = 0, steps: int = 0, hint: str = "") -> None:
        if self.busy:
            self.set_status("Already generating — wait for the current job.", "warn")
            return
        self.busy = True
        self._status_title = start_msg
        self._status_kind = "info"
        self._clock = JobClock(start_msg, items=items, steps=steps, hint=hint)
        self.spin.configure(mode="determinate")
        self.spin.set(0)
        self.eta_lbl.configure(text="estimating…")
        self.pct_lbl.configure(text="0%")
        self.status.configure(text=self._clock.line(), text_color=theme.TEXT)
        if self._pulse_id:
            try:
                self.after_cancel(self._pulse_id)
            except Exception:
                pass
        self._pulse_id = self.after(400, self._pulse_job)

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
        clock = self._clock
        if clock and clock.elapsed() > 2:
            each = clock.elapsed() / max(clock.items, 1)
            record_sample("flux_image", each)
            if not clock.warm:
                record_sample("flux_first", clock.elapsed())
        self.busy = False
        self._clock = None
        if self._pulse_id:
            try:
                self.after_cancel(self._pulse_id)
            except Exception:
                pass
            self._pulse_id = None
        self.spin.set(0 if err else 1)
        self.eta_lbl.configure(text="")
        self.pct_lbl.configure(text="" if err else "100%")
        on_done(result, err)
        if not self.busy:
            self.after(1600, lambda: self.pct_lbl.configure(text="") if not self.busy else None)

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
