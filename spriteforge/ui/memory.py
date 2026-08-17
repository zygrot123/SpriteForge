from __future__ import annotations

from tkinter import messagebox, simpledialog

import customtkinter as ctk

from . import theme


class MemoryPage(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color=theme.BG)
        self.app = app
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        left = ctk.CTkScrollableFrame(self, fg_color=theme.PANEL, width=380, corner_radius=0)
        left.grid(row=0, column=0, sticky="nsew")
        ctk.CTkLabel(left, text="Memory", text_color=theme.TEXT, font=ctk.CTkFont("Segoe UI", 22, "bold")).pack(
            anchor="w", padx=18, pady=(18, 4)
        )
        theme.muted(
            left,
            "Like Hermes: a profile that learns as you work. Sessions can be kept or deleted. "
            "Picks and 4K upscales teach taste. Imagine uses this unless you turn it off.",
            wrap=330,
        ).pack(anchor="w", padx=18, pady=(0, 12))

        theme.section(left, "Profile").pack(anchor="w", padx=18, pady=(8, 4))
        self.profile_menu = ctk.CTkOptionMenu(left, values=["Default"], fg_color=theme.CARD, command=self._switch_profile)
        self.profile_menu.pack(fill="x", padx=18)
        self.name = ctk.CTkEntry(left, placeholder_text="Profile name")
        self.name.pack(fill="x", padx=18, pady=(8, 0))
        self.note = ctk.CTkTextbox(left, height=70, fg_color=theme.CARD)
        self.note.pack(fill="x", padx=18, pady=(8, 0))
        prow = ctk.CTkFrame(left, fg_color="transparent")
        prow.pack(fill="x", padx=18, pady=8)
        ctk.CTkButton(prow, text="Save profile", width=110, fg_color=theme.ACCENT_DIM, command=self.save_profile).pack(side="left")
        ctk.CTkButton(prow, text="New", width=70, fg_color=theme.CARD, command=self.new_profile).pack(side="left", padx=6)
        ctk.CTkButton(prow, text="Delete", width=70, fg_color="#4a2430", hover_color="#6a3040", command=self.delete_profile).pack(side="left")

        theme.section(left, "Session").pack(anchor="w", padx=18, pady=(14, 4))
        self.sess_lbl = ctk.CTkLabel(left, text="", text_color=theme.TEXT, wraplength=330, justify="left", anchor="w")
        self.sess_lbl.pack(fill="x", padx=18)
        srow = ctk.CTkFrame(left, fg_color="transparent")
        srow.pack(fill="x", padx=18, pady=8)
        ctk.CTkButton(srow, text="New session", width=110, fg_color=theme.CARD, command=self.new_session).pack(side="left")
        ctk.CTkButton(srow, text="Keep", width=70, fg_color=theme.ACCENT_DIM, command=self.keep_session).pack(side="left", padx=6)
        ctk.CTkButton(srow, text="Delete", width=70, fg_color="#4a2430", hover_color="#6a3040", command=self.delete_session).pack(side="left")

        theme.section(left, "Pin a memory").pack(anchor="w", padx=18, pady=(12, 4))
        self.pin_in = ctk.CTkEntry(left, placeholder_text="e.g. never put a character in skies")
        self.pin_in.pack(fill="x", padx=18)
        ctk.CTkButton(left, text="Pin", width=80, fg_color=theme.CARD, command=self.add_pin).pack(anchor="w", padx=18, pady=8)

        theme.section(left, "Use memory when imagining").pack(anchor="w", padx=18, pady=(8, 4))
        self.use = ctk.CTkCheckBox(left, text="Steer Imagine with evolved taste")
        self.use.pack(anchor="w", padx=18, pady=(0, 16))
        if self.app.cfg.get("use_memory", True):
            self.use.select()

        right = ctk.CTkFrame(self, fg_color=theme.BG)
        right.grid(row=0, column=1, sticky="nsew", padx=16, pady=16)
        right.grid_rowconfigure(2, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self.evolved = ctk.CTkLabel(
            right, text="", text_color=theme.TEXT, justify="left", anchor="nw", wraplength=720,
        )
        self.evolved.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        ctk.CTkLabel(right, text="SESSIONS", text_color=theme.ACCENT, font=ctk.CTkFont("Segoe UI", 12, "bold"), anchor="w").grid(
            row=1, column=0, sticky="w", pady=(4, 4)
        )
        self.sess_list = ctk.CTkScrollableFrame(right, fg_color=theme.CARD, height=180)
        self.sess_list.grid(row=2, column=0, sticky="nsew")

        ctk.CTkLabel(right, text="THIS SESSION", text_color=theme.ACCENT, font=ctk.CTkFont("Segoe UI", 12, "bold"), anchor="w").grid(
            row=3, column=0, sticky="w", pady=(12, 4)
        )
        self.log = ctk.CTkTextbox(right, height=180, fg_color=theme.CARD, text_color=theme.MUTED, font=ctk.CTkFont("Consolas", 11))
        self.log.grid(row=4, column=0, sticky="ew")

        self._pins_box = ctk.CTkFrame(right, fg_color="transparent")
        self._pins_box.grid(row=5, column=0, sticky="ew", pady=(10, 0))

    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        mind = self.app.mind
        names = [p.get("name") or p["id"] for p in mind.profiles()]
        current = mind.profile().get("name") or mind.active_profile_id()
        self.profile_menu.configure(values=names or ["Default"])
        if current in names:
            self.profile_menu.set(current)
        self.name.delete(0, "end")
        self.name.insert(0, current)
        self.note.delete("1.0", "end")
        self.note.insert("1.0", mind.profile().get("note") or "")
        sess = mind.active_session() or {}
        kept = "kept" if sess.get("kept") else "open — delete or keep"
        self.sess_lbl.configure(
            text=f"{sess.get('title') or 'No session'}\n{sess.get('updated') or ''} · {kept} · {len(sess.get('events') or [])} events"
        )
        lt = mind.longterm()
        facts = lt.get("facts") or ["Nothing evolved yet. Generate, pick, and upscale — taste grows from that."]
        pins = lt.get("pins") or []
        uses = int(lt.get("uses") or 0)
        lines = [f"Evolved across {uses} uses.", ""] + [f"• {f}" for f in facts]
        if pins:
            lines += ["", "Pinned:"] + [f"• {p}" for p in pins]
        self.evolved.configure(text="\n".join(lines))

        for w in self.sess_list.winfo_children():
            w.destroy()
        for row in mind.list_sessions():
            self._session_row(row)

        self.log.delete("1.0", "end")
        events = list(sess.get("events") or [])[-30:]
        if not events:
            self.log.insert("1.0", "This session is empty.")
        else:
            blob = []
            for ev in reversed(events):
                blob.append(f"{ev.get('when','')}  {ev.get('kind','')}  {(ev.get('prompt') or '')[:80]}")
            self.log.insert("1.0", "\n".join(blob))

        for w in self._pins_box.winfo_children():
            w.destroy()
        for pin in pins:
            pr = ctk.CTkFrame(self._pins_box, fg_color=theme.CARD)
            pr.pack(fill="x", pady=3)
            ctk.CTkLabel(pr, text=pin, text_color=theme.TEXT, anchor="w").pack(side="left", padx=10, pady=6)
            ctk.CTkButton(pr, text="Unpin", width=70, height=26, fg_color=theme.CARD, command=lambda t=pin: self._unpin(t)).pack(
                side="right", padx=8
            )

        if hasattr(self.app, "refresh_memory_label"):
            self.app.refresh_memory_label()

    def _session_row(self, row: dict) -> None:
        active = (self.app.mind.active_session() or {}).get("id")
        bg = theme.LINE if row.get("id") == active else theme.PANEL
        box = ctk.CTkFrame(self.sess_list, fg_color=bg)
        box.pack(fill="x", padx=8, pady=4)
        mark = "★ " if row.get("kept") else ""
        title = f"{mark}{row.get('title') or row.get('id')}"
        ctk.CTkLabel(box, text=title, text_color=theme.TEXT, anchor="w").pack(side="left", padx=10, pady=8)
        ctk.CTkButton(box, text="Open", width=60, height=26, fg_color=theme.CARD, command=lambda s=row["id"]: self._open(s)).pack(
            side="right", padx=4
        )
        ctk.CTkButton(box, text="Keep", width=60, height=26, fg_color=theme.ACCENT_DIM, command=lambda s=row["id"]: self._keep(s)).pack(
            side="right", padx=4
        )
        ctk.CTkButton(
            box, text="Delete", width=60, height=26, fg_color="#4a2430", hover_color="#6a3040",
            command=lambda s=row["id"]: self._delete(s),
        ).pack(side="right", padx=4)

    def _switch_profile(self, name: str) -> None:
        for p in self.app.mind.profiles():
            if (p.get("name") or p["id"]) == name:
                self.app.mind.switch_profile(p["id"])
                break
        self.refresh()
        self.app.set_status(f"Profile: {name}", "ok")

    def save_profile(self) -> None:
        self.app.mind.rename_profile(self.name.get().strip(), self.note.get("1.0", "end").strip())
        self.app.cfg["use_memory"] = bool(self.use.get())
        from ..config import save_config

        save_config(self.app.cfg)
        self.refresh()
        self.app.set_status("Profile saved.", "ok")

    def new_profile(self) -> None:
        name = simpledialog.askstring("New profile", "Profile name:", parent=self.app)
        if not name or not name.strip():
            return
        self.app.mind.create_profile(name.strip())
        self.refresh()
        self.app.set_status(f"Created profile {name.strip()}", "ok")

    def delete_profile(self) -> None:
        pid = self.app.mind.active_profile_id()
        name = self.app.mind.profile().get("name") or pid
        if not messagebox.askyesno("Delete profile", f"Delete profile “{name}” and all of its sessions and memories?"):
            return
        if not self.app.mind.delete_profile(pid):
            self.app.set_status("Keep at least one profile.", "warn")
            return
        self.refresh()
        self.app.set_status("Profile deleted.", "ok")

    def new_session(self) -> None:
        self.app.mind.new_session()
        self.refresh()
        self.app.set_status("New session started. Old long-term memory stays.", "ok")

    def keep_session(self) -> None:
        sess = self.app.mind.active_session()
        if not sess:
            return
        self.app.mind.keep_session(sess["id"], True)
        self.refresh()
        self.app.set_status("Session kept.", "ok")

    def delete_session(self) -> None:
        sess = self.app.mind.active_session()
        if not sess:
            return
        self._delete(sess["id"])

    def _open(self, sid: str) -> None:
        self.app.mind.switch_session(sid)
        self.refresh()

    def _keep(self, sid: str) -> None:
        self.app.mind.keep_session(sid, True)
        self.refresh()

    def _delete(self, sid: str) -> None:
        ans = messagebox.askyesnocancel(
            "Delete session",
            "Yes = delete this session and forget its traces.\n"
            "No = delete the session log, keep evolved taste.\n"
            "Cancel = keep the session.",
        )
        if ans is None:
            return
        self.app.mind.delete_session(sid, forget=bool(ans))
        self.refresh()
        self.app.set_status("Session deleted.", "ok")

    def add_pin(self) -> None:
        text = self.pin_in.get().strip()
        if not text:
            return
        self.app.mind.pin(text)
        self.pin_in.delete(0, "end")
        self.refresh()

    def _unpin(self, text: str) -> None:
        self.app.mind.unpin(text)
        self.refresh()
