"""Microphone button that types into a CTkTextbox."""
from __future__ import annotations

import threading

import customtkinter as ctk

from ..engine.lexicon import fluidize
from ..engine.voice import VoiceError, listen_once
from . import theme


def attach_mic(parent, box: ctk.CTkTextbox, app, *, expand: bool = True) -> ctk.CTkButton:
    state = {"busy": False}

    def finish(text: str | None, err: Exception | None) -> None:
        state["busy"] = False
        btn.configure(text="Mic", fg_color=theme.CARD, state="normal")
        if err:
            app.set_status(f"Mic: {err}", "err")
            return
        spoken = (text or "").strip()
        if not spoken:
            app.set_status("Mic heard nothing. Wait for the beep, then speak.", "warn")
            return
        cleaned, notes = fluidize(spoken, expand=expand)
        use = cleaned or spoken
        box.delete("1.0", "end")
        box.insert("1.0", use)
        extra = f" ({'; '.join(notes)})" if notes else ""
        app.set_status(f"Heard: {use[:90]}{extra}", "ok")

    def work() -> None:
        err = None
        text = None

        def ready() -> None:
            app.after(
                0,
                lambda: (
                    btn.configure(text="Speak now!"),
                    app.set_status("Beep — speak now, in a full sentence.", "ok"),
                ),
            )

        try:
            text = listen_once(on_ready=ready)
        except Exception as exc:  # noqa: BLE001
            err = exc if isinstance(exc, VoiceError) else VoiceError(str(exc))
        app.after(0, lambda t=text, e=err: finish(t, e))

    def click() -> None:
        if state["busy"]:
            return
        state["busy"] = True
        btn.configure(text="Starting…", fg_color=theme.WARM, state="disabled")
        app.set_status("Starting microphone — wait for the beep, then speak.", "info")
        threading.Thread(target=work, daemon=True).start()

    btn = ctk.CTkButton(
        parent,
        text="Mic",
        width=88,
        height=30,
        fg_color=theme.CARD,
        command=click,
    )
    btn.pack(anchor="w", padx=18, pady=(6, 0))
    return btn
