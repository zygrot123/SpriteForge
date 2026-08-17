from __future__ import annotations

import os
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from ..engine.companion import Forge
from ..paths import OUTPUTS
from . import theme
from .mic import attach_mic


class ChatPage(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color=theme.BG)
        self.app = app
        self.files: list[Path] = []
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(self, fg_color=theme.PANEL, corner_radius=0)
        head.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            head, text="Forge", text_color=theme.TEXT,
            font=ctk.CTkFont("Segoe UI", 22, "bold"),
        ).pack(anchor="w", padx=18, pady=(16, 2))
        theme.muted(
            head,
            "Talk like you talk to me. Upload a picture and say “add a second sword in his left hand” — "
            "Forge edits the file. It also remembers you in the memory bank.",
            wrap=820,
        ).pack(anchor="w", padx=18, pady=(0, 12))

        self.log = ctk.CTkTextbox(self, fg_color=theme.CARD, font=ctk.CTkFont("Segoe UI", 14), wrap="word")
        self.log.grid(row=1, column=0, sticky="nsew", padx=16, pady=(12, 8))

        files_row = ctk.CTkFrame(self, fg_color="transparent")
        files_row.grid(row=2, column=0, sticky="ew", padx=16)
        ctk.CTkButton(files_row, text="Upload file…", width=120, fg_color=theme.ACCENT_DIM, command=self.upload).pack(side="left")
        ctk.CTkButton(files_row, text="Clear files", width=100, fg_color=theme.CARD, command=self.clear_files).pack(side="left", padx=6)
        self.file_lbl = ctk.CTkLabel(files_row, text="No file attached", text_color=theme.MUTED, anchor="w")
        self.file_lbl.pack(side="left", padx=10, fill="x", expand=True)

        box = ctk.CTkFrame(self, fg_color=theme.PANEL)
        box.grid(row=3, column=0, sticky="ew", padx=16, pady=(8, 16))
        box.grid_columnconfigure(0, weight=1)
        self.input = ctk.CTkTextbox(box, height=70, fg_color=theme.CARD)
        self.input.grid(row=0, column=0, sticky="ew", padx=(10, 6), pady=10)
        side = ctk.CTkFrame(box, fg_color="transparent")
        side.grid(row=0, column=1, padx=(0, 10), pady=10)
        ctk.CTkButton(side, text="Send", width=90, height=36, fg_color=theme.WARM, command=self.send).pack()
        attach_mic(side, self.input, self.app)
        self.input.bind("<Control-Return>", lambda _e: self.send())

    def on_show(self) -> None:
        self._reload()

    def _forge(self) -> Forge:
        return Forge(self.app.mind)

    def _reload(self) -> None:
        self.log.delete("1.0", "end")
        forge = self._forge()
        hist = forge.history(40)
        if not hist:
            self.log.insert("end", "Forge: I'm here. Talk, or upload a picture / zip / rar.\n\n")
            return
        for row in hist:
            who = "You" if row.get("role") == "user" else "Forge"
            self.log.insert("end", f"{who}: {row.get('text','')}\n\n")
        self.log.see("end")

    def upload(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Show Forge a file",
            filetypes=[
                ("Pictures and packs", "*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.zip;*.rar;*.7z"),
                ("Images", "*.png;*.jpg;*.jpeg;*.webp;*.bmp"),
                ("Archives", "*.zip;*.rar;*.7z"),
                ("All", "*.*"),
            ],
        )
        for p in paths:
            path = Path(p)
            if path not in self.files:
                self.files.append(path)
        self._files_label()

    def clear_files(self) -> None:
        self.files.clear()
        self._files_label()

    def _files_label(self) -> None:
        if not self.files:
            self.file_lbl.configure(text="No file attached", text_color=theme.MUTED)
            return
        names = ", ".join(p.name for p in self.files[:5])
        extra = f" +{len(self.files)-5}" if len(self.files) > 5 else ""
        self.file_lbl.configure(text=f"Attached: {names}{extra}", text_color=theme.ACCENT)

    def send(self) -> None:
        text = self.input.get("1.0", "end").strip()
        if not text and not self.files:
            self.app.set_status("Say something or attach a file.", "warn")
            return
        self.input.delete("1.0", "end")
        shown = text or "(looks at files)"
        self.log.insert("end", f"You: {shown}\n\n")
        self.log.see("end")
        files = list(self.files)
        forge = self._forge()

        last = getattr(self.app, "last_image", None)

        def work():
            return forge.think(text, files, last_image=last)

        def done(payload, err):
            if err:
                self.app.set_status(f"Forge failed: {err}", "err")
                self.log.insert("end", f"Forge: I hit a snag — {err}\n\n")
                return
            payload = payload or {}
            reply = payload.get("text") or ""
            self.log.insert("end", f"Forge: {reply}\n\n")
            self.log.see("end")
            self.app.refresh_memory_label()
            action = payload.get("action")
            if action:
                self._run_action(action)
            else:
                self.app.set_status("Forge answered.", "ok")

        self.app.run_job(work, done, "Forge is thinking…")

    def _run_action(self, action: dict) -> None:
        from ..engine.imagine import generate_variations, imagine_video, upscale_image

        kind = action.get("type")
        src = Path(action.get("path") or "")
        prompt = action.get("prompt") or ""
        if not src.exists():
            self.app.set_status("No picture to edit. Upload one or generate first.", "warn")
            return

        def work():
            if kind == "edit":
                return generate_variations(
                    self.app.client(),
                    action.get("raw") or prompt,
                    think=False,
                    exact=True,
                    count=1,
                    ref_path=src,
                    denoise=0.74,
                    aspect="16:9",
                    preset="720p",
                )[0]
            if kind == "video":
                return imagine_video(
                    self.app.client(), src, text=prompt, motion=prompt,
                    think=False, duration=float(action.get("duration") or 4),
                )
            if kind == "upscale":
                return upscale_image(self.app.client(), src, preset=action.get("preset") or "1080p", text=prompt)
            raise RuntimeError(f"unknown action {kind}")

        def done(path, err):
            if err:
                self.log.insert("end", f"Forge: Edit failed — {err}\n\n")
                self.app.set_status(f"Forge edit failed: {err}", "err")
                return
            self.app.last_image = path
            self.app.lib.record_output(path, {"kind": f"forge_{kind}", "prompt": prompt})
            self.log.insert("end", f"Forge: Done. Saved {Path(path).name}\n\n")
            self.log.see("end")
            try:
                os.startfile(path)
            except OSError:
                pass
            self.app.set_status(f"Forge {kind} → {Path(path).name}", "ok")

        self.app.run_job(work, done, f"Forge is {kind}ing the file…")
