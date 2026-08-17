from __future__ import annotations

import threading
import traceback

import customtkinter as ctk

from ..bootstrap import (
    PACK_LABELS,
    check_updates,
    detect_gpu,
    diagnose_components,
    inspect_install,
    repair_components,
    setup_needed,
)
from ..config import load_config, save_config
from . import theme

STATUS_COLOR = {
    "ok": theme.OK,
    "missing": theme.WARM,
    "broken": theme.WARM,
    "update": theme.WARN,
    "unknown": theme.MUTED,
    "working": theme.ACCENT,
    "skip": theme.MUTED,
}


class SetupWizard:
    def __init__(self, parent=None) -> None:
        theme.apply()
        self.result = False
        self._busy = False
        self._rows: dict[str, dict] = {}
        if parent is None:
            self.win = ctk.CTk()
        else:
            self.win = ctk.CTkToplevel(parent)
            self.win.transient(parent)
            self.win.grab_set()
        self.win.title("SpriteForge  —  setup, updates, fix")
        self.win.geometry("860x780")
        self.win.minsize(780, 680)
        self.win.configure(fg_color=theme.BG)

        ctk.CTkLabel(
            self.win,
            text="Local files — download, update, fix",
            text_color=theme.TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
        ).pack(anchor="w", padx=24, pady=(18, 4))
        theme.muted(
            self.win,
            "Every piece is listed below. Watch each one install. Check for updates on models. "
            "Fix re-downloads anything missing or broken. All of it stays on this PC.",
            wrap=800,
        ).pack(anchor="w", padx=24)

        gpu = detect_gpu()
        gpu_txt = gpu.split(":", 1)[-1] if gpu.startswith("nvidia:") else "No NVIDIA GPU detected"
        ctk.CTkLabel(
            self.win,
            text=f"GPU:  {gpu_txt}",
            text_color=theme.OK if gpu.startswith("nvidia:") else theme.WARN,
            font=ctk.CTkFont("Segoe UI", 13),
        ).pack(anchor="w", padx=24, pady=(8, 4))

        theme.section(self.win, "Pack").pack(anchor="w", padx=24, pady=(8, 4))
        self.pack_choice = ctk.CTkOptionMenu(self.win, values=list(PACK_LABELS.values()), width=440, fg_color=theme.CARD)
        self.pack_choice.set(PACK_LABELS["flux"])
        self.pack_choice.pack(anchor="w", padx=24)

        theme.section(self.win, "What’s installing").pack(anchor="w", padx=24, pady=(12, 4))
        self.listf = ctk.CTkScrollableFrame(self.win, fg_color=theme.PANEL, height=280)
        self.listf.pack(fill="x", padx=24)
        self._build_rows()

        self.bar = ctk.CTkProgressBar(self.win, width=800, height=10, progress_color=theme.ACCENT)
        self.bar.pack(padx=24, pady=(12, 4))
        self.bar.set(0)
        self.status = ctk.CTkLabel(self.win, text="Idle.", text_color=theme.MUTED, anchor="w")
        self.status.pack(fill="x", padx=24)
        self.log = ctk.CTkTextbox(self.win, height=120, fg_color=theme.CARD, text_color=theme.MUTED, font=ctk.CTkFont("Consolas", 12))
        self.log.pack(fill="both", expand=True, padx=24, pady=8)

        row = ctk.CTkFrame(self.win, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=(4, 16))
        self.btn_dl = ctk.CTkButton(row, text="Download missing", height=36, fg_color=theme.WARM, command=lambda: self._run("missing"))
        self.btn_dl.pack(side="left")
        self.btn_chk = ctk.CTkButton(row, text="Check for updates", height=36, fg_color=theme.CARD, command=self._check)
        self.btn_chk.pack(side="left", padx=6)
        self.btn_up = ctk.CTkButton(row, text="Update", height=36, fg_color=theme.ACCENT_DIM, command=lambda: self._run("update"))
        self.btn_up.pack(side="left", padx=6)
        self.btn_fix = ctk.CTkButton(row, text="Fix broken", height=36, fg_color="#4a2430", hover_color="#6a3040", command=lambda: self._run("broken"))
        self.btn_fix.pack(side="left", padx=6)
        ctk.CTkButton(row, text="Continue", height=36, fg_color=theme.CARD, command=self._continue).pack(side="right")
        self.win.protocol("WM_DELETE_WINDOW", self._skip)
        self._append("Ready. Download missing, or Check for updates.")

    def _pack_key(self) -> str:
        label = self.pack_choice.get()
        for k, v in PACK_LABELS.items():
            if v == label:
                return k
        return "flux"

    def _build_rows(self) -> None:
        for w in self.listf.winfo_children():
            w.destroy()
        self._rows.clear()
        for c in diagnose_components(self._pack_key()):
            row = ctk.CTkFrame(self.listf, fg_color=theme.CARD)
            row.pack(fill="x", padx=6, pady=3)
            title = ctk.CTkLabel(row, text=c.label, width=280, anchor="w", font=ctk.CTkFont("Segoe UI", 13, "bold"))
            title.pack(side="left", padx=8, pady=6)
            st = ctk.CTkLabel(row, text=c.status.upper(), width=90, anchor="w", text_color=STATUS_COLOR.get(c.status, theme.MUTED))
            st.pack(side="left")
            bar = ctk.CTkProgressBar(row, width=180, height=8, progress_color=theme.ACCENT)
            bar.pack(side="left", padx=8)
            bar.set(1.0 if c.status == "ok" else 0.0)
            det = ctk.CTkLabel(row, text=c.detail or ("installed" if c.status == "ok" else "not installed"), text_color=theme.MUTED, anchor="w")
            det.pack(side="left", fill="x", expand=True, padx=6)
            self._rows[c.id] = {"status": st, "bar": bar, "detail": det}

    def _set_row(self, cid: str, frac: float, msg: str, state: str | None = None) -> None:
        row = self._rows.get(cid)
        if not row:
            # try match by label fragment
            for key, r in self._rows.items():
                if cid.lower() in key or key in cid.lower():
                    row = r
                    break
        if not row:
            return
        row["bar"].set(max(0.0, min(1.0, frac)))
        row["detail"].configure(text=msg[:80])
        if state:
            row["status"].configure(text=state.upper(), text_color=STATUS_COLOR.get(state, theme.ACCENT))
        elif frac < 1:
            row["status"].configure(text="WORKING", text_color=theme.ACCENT)
        else:
            row["status"].configure(text="OK", text_color=theme.OK)

    def mainloop(self) -> None:
        self.win.mainloop()

    def wait(self, host) -> None:
        host.wait_window(self.win)

    def _append(self, line: str) -> None:
        self.log.insert("end", line.rstrip() + "\n")
        self.log.see("end")

    def _lock(self, on: bool) -> None:
        self._busy = on
        state = "disabled" if on else "normal"
        for b in (self.btn_dl, self.btn_chk, self.btn_up, self.btn_fix):
            b.configure(state=state)

    def _run(self, mode: str) -> None:
        if self._busy:
            return
        self._lock(True)
        pack = self._pack_key()
        gpu = "nvidia" if "No NVIDIA" not in str(self.gpu_lbl.cget("text") if hasattr(self, "gpu_lbl") else "") else "cpu"
        gpu = "nvidia"
        self._append(f"Starting {mode}…")

        def progress(name: str, frac: float, msg: str) -> None:
            self.win.after(0, lambda n=name, f=frac, m=msg: self._on_progress(n, f, m))

        def work() -> None:
            try:
                st = repair_components(pack=pack, gpu=gpu, mode=mode, progress=progress)
                self.win.after(0, lambda: self._finish(st, mode))
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                self.win.after(0, lambda: self._fail(exc))

        threading.Thread(target=work, daemon=True).start()

    def _check(self) -> None:
        if self._busy:
            return
        self._lock(True)
        self._append("Checking servers for newer files…")

        def work() -> None:
            try:
                comps = check_updates(diagnose_components(self._pack_key()))
                self.win.after(0, lambda: self._after_check(comps))
            except Exception as exc:  # noqa: BLE001
                self.win.after(0, lambda: self._fail(exc))

        threading.Thread(target=work, daemon=True).start()

    def _after_check(self, comps) -> None:
        self._lock(False)
        updates = [c for c in comps if c.status == "update"]
        broken = [c for c in comps if c.status == "broken"]
        for c in comps:
            state = c.status
            msg = c.detail or c.status
            frac = 1.0 if c.status == "ok" else 0.0
            self._set_row(c.id, frac, msg, state)
        if updates:
            self.status.configure(text=f"{len(updates)} update(s) available. Press Update.", text_color=theme.WARN)
            self._append("Updates: " + ", ".join(c.label for c in updates))
        elif broken:
            self.status.configure(text=f"{len(broken)} broken file(s). Press Fix broken.", text_color=theme.WARM)
        else:
            self.status.configure(text="Everything is current.", text_color=theme.OK)
            self._append("No updates.")

    def _on_progress(self, name: str, frac: float, msg: str) -> None:
        self.bar.set(max(0.0, min(1.0, frac)))
        self.status.configure(text=msg, text_color=theme.TEXT)
        self._append(msg)
        cid = name
        for key in self._rows:
            if key == name or name.lower().startswith(key) or key in name.lower() or name in (self._rows[key]["status"].cget("text") or ""):
                cid = key
                break
        # map common progress names
        low = name.lower()
        if "comfy" in low:
            cid = "comfy"
        elif "ffmpeg" in low:
            cid = "ffmpeg"
        elif "7-zip" in low or "7zip" in low:
            cid = "seven"
        elif "flux.1" in low or "unet" in low:
            cid = "flux_unet"
        elif "clip" in low:
            cid = "clip_l"
        elif "t5" in low:
            cid = "t5xxl"
        elif "vae" in low and "sdxl" not in low:
            cid = "ae"
        elif "sdxl base" in low:
            cid = "sdxl"
        self._set_row(cid, frac, msg)

    def _fail(self, exc: Exception) -> None:
        self._lock(False)
        self.status.configure(text=f"Failed: {exc}", text_color=theme.WARM)
        self._append(f"ERROR: {exc}")
        self._build_rows()

    def _finish(self, st, mode: str) -> None:
        cfg = load_config()
        if st.comfy_root:
            cfg["comfy_root"] = str(st.comfy_root)
        if st.comfy_python:
            cfg["comfy_python"] = str(st.comfy_python)
        cfg["setup_complete"] = bool(st.ready and st.ffmpeg)
        cfg["engine"] = "flux" if st.flux else "sdxl"
        save_config(cfg)
        self._lock(False)
        self._build_rows()
        if st.ready and st.ffmpeg:
            self.result = True
            self.status.configure(text=f"{mode} finished. Sprites, animation, and video are local.", text_color=theme.OK)
        else:
            self.status.configure(text="Still missing: " + ", ".join(st.missing or ["?"]), text_color=theme.WARN)

    def _continue(self) -> None:
        if self._busy:
            return
        st = inspect_install()
        self.result = bool(st.ready)
        self.win.destroy()

    def _skip(self) -> None:
        if self._busy:
            return
        self.result = False
        self.win.destroy()


def run_setup() -> bool:
    if not setup_needed(load_config()):
        return True
    wiz = SetupWizard()
    wiz.mainloop()
    return bool(wiz.result)
