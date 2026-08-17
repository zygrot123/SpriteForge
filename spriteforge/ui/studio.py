from __future__ import annotations

import random
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image

from ..engine.assets import compose_sheet, process_sprite, slugify, unique_out
from ..engine.quality import MODES, finish_sprite, generate_quality, mode_key, mode_labels
from ..engine.brain import understand
from ..engine.motion import (
    CATEGORIES,
    DIR_SETS,
    GROUND_LOCK,
    HEIGHT_LOCK,
    PRESENTATIONS,
    SOLO_LOCK,
    all_animations,
    anim_by_label,
    anim_labels,
    compose_direction_sheet,
    invent_frames,
    presentation_by_label,
    presentation_labels,
    save_animation,
    stabilize_frames,
)
from ..engine.prompts import (
    ANIMATIONS,
    LOCK_STRENGTH,
    STYLES,
    VIEWS,
    compile_negative,
    compile_prompt,
    pixel_hint,
)
from ..paths import FRAMES, OUTPUTS, SHEETS
from . import theme

SIZES = {
    "512 × 512  icon / prop": (512, 512),
    "512 × 768  compact sprite": (512, 768),
    "768 × 1024  character": (768, 1024),
    "1024 × 1024  hero": (1024, 1024),
    "1024 × 768  wide / iso": (1024, 768),
    "1280 × 720  scene plate": (1280, 720),
    "1536 × 768  sky strip": (1536, 768),
}
PIXELS = ["Off", "32", "48", "64", "96", "128"]
BGS = ["green", "magenta", "cyan", "black", "gray"]


def _style_labels() -> list[str]:
    return [v["label"] for v in STYLES.values()]


def _style_key(label: str) -> str:
    for k, v in STYLES.items():
        if v["label"] == label:
            return k
    return "abyssal_iso"


def _view_labels() -> list[str]:
    return list(VIEWS.keys())


def _anim_labels() -> list[str]:
    return anim_labels("all")


def _anim_key(label: str) -> str:
    key, _spec = anim_by_label(label)
    return key


def _thumb(path: Path, box: tuple[int, int]) -> ctk.CTkImage | None:
    try:
        im = Image.open(path).convert("RGBA")
    except OSError:
        return None
    im.thumbnail(box, Image.Resampling.LANCZOS)
    return ctk.CTkImage(light_image=im, dark_image=im, size=im.size)


class GeneratePage(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color=theme.BG)
        self.app = app
        self.last_path: Path | None = None
        self.session_lock: Path | None = None
        self._preview_img = None
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        form = ctk.CTkScrollableFrame(self, fg_color=theme.PANEL, width=380, corner_radius=0)
        form.grid(row=0, column=0, sticky="nsew")
        ctk.CTkLabel(
            form, text="Text → sprite", text_color=theme.TEXT,
            font=ctk.CTkFont("Segoe UI", 22, "bold"),
        ).pack(anchor="w", padx=18, pady=(18, 4))
        theme.muted(form, "First generate invents the character. After that, keep “Same character” on so extra images stay that person — not a new warrior every click.").pack(anchor="w", padx=18, pady=(0, 12))

        theme.section(form, "Describe").pack(anchor="w", padx=18, pady=(8, 4))
        self.prompt = ctk.CTkTextbox(form, height=110, font=ctk.CTkFont("Segoe UI", 14), fg_color=theme.CARD)
        self.prompt.pack(fill="x", padx=18, pady=(0, 10))
        self.prompt.insert("1.0", "lone abyss knight, blackened plate, torn red cape, single cyan visor slit")

        self.present = self._combo(form, "Game camera", presentation_labels(), PRESENTATIONS["hades"]["label"])
        self.present.configure(command=self._on_present)
        self.style = self._combo(form, "Style", _style_labels(), STYLES[self.app.cfg["default_style"]]["label"])
        self.view = self._combo(form, "View / camera", _view_labels(), self.app.cfg.get("default_view", "isometric"))
        self._on_present(self.present.get())
        self.size = self._combo(form, "Size", list(SIZES.keys()), "768 × 1024  character")
        self.bg = self._combo(form, "Key background", BGS, self.app.cfg.get("default_bg", "green"))
        self.pixel = self._combo(form, "Pixelize after", PIXELS, "Off")
        self.count = self._combo(form, "How many", ["1", "2", "3", "4"], "1")
        qdefault = MODES.get(self.app.cfg.get("quality_mode", "quality"), MODES["quality"])["label"]
        self.quality = self._combo(form, "Quality engine", mode_labels(), qdefault)

        theme.section(form, "Seed").pack(anchor="w", padx=18, pady=(10, 4))
        seed_row = ctk.CTkFrame(form, fg_color="transparent")
        seed_row.pack(fill="x", padx=18, pady=(0, 8))
        self.seed = ctk.CTkEntry(seed_row, placeholder_text="random")
        self.seed.pack(side="left", fill="x", expand=True)
        self.rand_seed = ctk.CTkCheckBox(seed_row, text="Random", width=90)
        self.rand_seed.pack(side="left", padx=(8, 0))
        self.rand_seed.select()

        self.key_bg = ctk.CTkCheckBox(form, text="Punch out background (PNG alpha)")
        self.key_bg.pack(anchor="w", padx=18, pady=4)
        self.key_bg.select()
        self.same_char = ctk.CTkCheckBox(form, text="Same character (don't invent a new one)")
        self.same_char.pack(anchor="w", padx=18, pady=4)
        self.same_char.select()
        self.hold_lbl = ctk.CTkLabel(form, text="No character held yet — first generate will invent one.", text_color=theme.MUTED, wraplength=320, justify="left", anchor="w")
        self.hold_lbl.pack(fill="x", padx=18, pady=(0, 6))
        ctk.CTkButton(form, text="Forget character", fg_color=theme.CARD, height=28, command=self.forget_character).pack(fill="x", padx=18, pady=(0, 6))

        ctk.CTkButton(
            form, text="Generate sprite", height=42, fg_color=theme.WARM, hover_color="#d45544",
            font=ctk.CTkFont("Segoe UI", 15, "bold"), command=self.generate,
        ).pack(fill="x", padx=18, pady=(14, 8))

        theme.section(form, "Brain").pack(anchor="w", padx=18, pady=(8, 4))
        self.brain_lbl = ctk.CTkLabel(
            form, text="Write something like “Pikachu but as a fish” — the brain rewrites weak phrases.",
            text_color=theme.ACCENT, wraplength=320, justify="left", anchor="w",
        )
        self.brain_lbl.pack(fill="x", padx=18, pady=(0, 6))
        theme.section(form, "Compiled prompt").pack(anchor="w", padx=18, pady=(8, 4))
        self.compiled = ctk.CTkTextbox(form, height=90, fg_color=theme.CARD, text_color=theme.MUTED, font=ctk.CTkFont("Consolas", 11))
        self.compiled.pack(fill="x", padx=18, pady=(0, 18))

        right = ctk.CTkFrame(self, fg_color=theme.BG)
        right.grid(row=0, column=1, sticky="nsew", padx=16, pady=16)
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)
        self.preview = ctk.CTkLabel(right, text="Preview appears here", text_color=theme.MUTED, fg_color=theme.CARD, corner_radius=12)
        self.preview.grid(row=0, column=0, sticky="nsew")

        actions = ctk.CTkFrame(right, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.lock_name = ctk.CTkEntry(actions, placeholder_text="Model name, e.g. Vane")
        self.lock_name.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(actions, text="Lock as exact model", fg_color=theme.ACCENT_DIM, hover_color="#24665c", command=self.lock_model).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="Open folder", fg_color=theme.CARD, command=self.open_folder).pack(side="left", padx=4)

    def _on_present(self, label: str) -> None:
        if not hasattr(self, "view") or not hasattr(self, "style"):
            return
        _k, spec = presentation_by_label(label)
        if spec.get("view") in VIEWS:
            self.view.set(spec["view"])
        if spec.get("style") and spec["style"] in STYLES:
            self.style.set(STYLES[spec["style"]]["label"])

    def _combo(self, parent, title, values, current):
        theme.section(parent, title).pack(anchor="w", padx=18, pady=(8, 4))
        box = ctk.CTkOptionMenu(parent, values=values, fg_color=theme.CARD, button_color=theme.LINE)
        box.set(current if current in values else values[0])
        box.pack(fill="x", padx=18)
        return box

    def _opts(self) -> dict:
        w, h = SIZES[self.size.get()]
        pix = None if self.pixel.get() == "Off" else int(self.pixel.get())
        if self.rand_seed.get() or not self.seed.get().strip():
            seed = random.randint(1, 2**31 - 1)
        else:
            seed = int(self.seed.get().strip())
        return {
            "text": self.prompt.get("1.0", "end").strip(),
            "style": _style_key(self.style.get()),
            "view": self.view.get(),
            "bg": self.bg.get(),
            "width": w,
            "height": h,
            "pixel": pix,
            "seed": seed,
            "count": int(self.count.get()),
            "key": bool(self.key_bg.get()),
            "quality": mode_key(self.quality.get()),
            "present": self.present.get(),
        }

    def generate(self) -> None:
        o = self._opts()
        if not o["text"]:
            self.app.set_status("Write a description first.", "warn")
            return
        extra = pixel_hint(o["pixel"])
        intent = understand(o["text"])
        _pk, pres = presentation_by_label(o["present"])
        prompt = compile_prompt(
            o["text"], style=o["style"], view=o["view"], bg=o["bg"], extra=extra, intent=intent,
            presentation=pres.get("lock", ""),
        )
        self.brain_lbl.configure(text=intent.summary)
        self.compiled.delete("1.0", "end")
        shown = prompt
        if intent.transformed:
            shown = f"[BRAIN] {intent.summary}\n\n{prompt}"
        self.compiled.insert("1.0", shown)
        self.app.cfg["quality_mode"] = o["quality"]
        hold = bool(self.same_char.get()) and self.session_lock and self.session_lock.exists()
        lock_src = self.session_lock if hold else None

        def work():
            client = self.app.client()
            paths = []
            metas = []
            per = o["count"]
            qmode = o["quality"]
            if per > 1 and qmode == "studio":
                qmode = "quality"
            base_lock = lock_src
            for i in range(per):
                seed = o["seed"] + i * 101
                dest, meta = generate_quality(
                    client,
                    prompt,
                    mode=qmode if base_lock is None else "fast",
                    engine=self.app.cfg.get("engine", "flux"),
                    seed=seed,
                    steps=int(self.app.cfg.get("steps", 24)),
                    width=o["width"],
                    height=o["height"],
                    guidance=float(self.app.cfg.get("guidance", 3.5)),
                    bg=o["bg"],
                    kind="sprite",
                    pixel_size=o["pixel"],
                    key=o["key"],
                    negative=compile_negative("sprite", extra=intent.negatives),
                    prefix=f"gen_{seed}",
                    dest_dir=OUTPUTS,
                    name="sprite",
                    ref_path=base_lock,
                    lock_denoise=0.30,
                )
                paths.append(dest)
                metas.append(meta)
                if base_lock is None:
                    lp = Path(meta["lock_path"]) if meta.get("lock_path") else dest
                    if lp.exists():
                        base_lock = lp
                self.app.lib.record_output(dest, {"kind": "sprite", "seed": seed, "prompt": o["text"], "score": meta})
            return {"paths": paths, "metas": metas, "lock": str(base_lock) if base_lock else ""}

        def done(payload, err):
            if err:
                self.app.set_status(f"Generate failed: {err}", "err")
                return
            paths, metas = payload["paths"], payload["metas"]
            self.last_path = paths[0]
            self.app.last_image = paths[0]
            if payload.get("lock"):
                self.session_lock = Path(payload["lock"])
            self._show(paths[0])
            self._update_hold()
            score = metas[0].get("total", 0)
            same = "same character" if metas[0].get("same_character") or hold else "new character"
            refined = " · refined" if metas[0].get("refined") else ""
            self.app.set_status(
                f"{same} · score {score:.0f}/100{refined} · {len(paths)} → {paths[0].name}",
                "ok",
            )

        label = "Keeping this character" if hold else MODES[o["quality"]]["label"]
        self.app.run_job(work, done, f"{label} — {('same model' if hold else 'inventing then locking')}…")

    def forget_character(self) -> None:
        self.session_lock = None
        self._update_hold()
        self.app.set_status("Character forgotten. Next generate invents someone new.", "info")

    def _update_hold(self) -> None:
        if self.session_lock and self.session_lock.exists():
            self.hold_lbl.configure(
                text=f"Holding {self.session_lock.stem}. Next generate stays this person.",
                text_color=theme.ACCENT,
            )
            self.same_char.select()
        else:
            self.hold_lbl.configure(
                text="No character held yet — first generate will invent one.",
                text_color=theme.MUTED,
            )

    def _show(self, path: Path) -> None:
        img = _thumb(path, (720, 720))
        if img:
            self._preview_img = img
            self.preview.configure(image=img, text="")

    def lock_model(self) -> None:
        if not self.last_path or not self.last_path.exists():
            self.app.set_status("Generate something first, then lock it.", "warn")
            return
        o = self._opts()
        name = self.lock_name.get().strip() or o["text"][:40]
        card = self.app.lib.create(
            name, o["text"], style=o["style"], view=o["view"], bg=o["bg"],
            seed=o["seed"], width=o["width"], height=o["height"],
            ref_image=self.last_path, ref_role="front",
        )
        self.app.set_status(f"Locked model “{card.name}”. Use Animations to pose it.", "ok")
        self.app.show("models")

    def open_folder(self) -> None:
        OUTPUTS.mkdir(parents=True, exist_ok=True)
        import os
        os.startfile(OUTPUTS)  # noqa: S606 — user asked for Windows app


class ModelsPage(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color=theme.BG)
        self.app = app
        self.current_id: str | None = None
        self._thumbs: list[ctk.CTkImage] = []
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(self, fg_color=theme.PANEL, width=280, corner_radius=0)
        left.grid(row=0, column=0, sticky="nsew")
        left.grid_propagate(False)
        ctk.CTkLabel(left, text="Locked models", text_color=theme.TEXT, font=ctk.CTkFont("Segoe UI", 18, "bold")).pack(anchor="w", padx=16, pady=(18, 8))
        self.listbox = ctk.CTkScrollableFrame(left, fg_color=theme.PANEL)
        self.listbox.pack(fill="both", expand=True, padx=8, pady=8)
        ctk.CTkButton(left, text="Import image as model", fg_color=theme.CARD, command=self.import_image).pack(fill="x", padx=16, pady=(4, 16))

        right = ctk.CTkFrame(self, fg_color=theme.BG)
        right.grid(row=0, column=1, sticky="nsew", padx=18, pady=18)
        ctk.CTkLabel(right, text="Exact character card", text_color=theme.TEXT, font=ctk.CTkFont("Segoe UI", 22, "bold")).pack(anchor="w")
        theme.muted(right, "A locked model remembers the face, colors, gear, seed and a reference image. Animations and extra views are img2img from that reference so the character does not drift.").pack(anchor="w", pady=(4, 12))

        theme.section(right, "Name").pack(anchor="w", pady=(8, 4))
        self.name = ctk.CTkEntry(right)
        self.name.pack(fill="x")
        theme.section(right, "Identity lock (write every visual fact)").pack(anchor="w", pady=(10, 4))
        self.identity = ctk.CTkTextbox(right, height=140, fg_color=theme.CARD)
        self.identity.pack(fill="x")

        row = ctk.CTkFrame(right, fg_color="transparent")
        row.pack(fill="x", pady=12)
        self.style = ctk.CTkOptionMenu(row, values=_style_labels(), width=220, fg_color=theme.CARD)
        self.style.pack(side="left", padx=(0, 8))
        self.view = ctk.CTkOptionMenu(row, values=_view_labels(), width=160, fg_color=theme.CARD)
        self.view.pack(side="left")

        self.refs = ctk.CTkFrame(right, fg_color=theme.CARD, height=160)
        self.refs.pack(fill="x", pady=10)

        btns = ctk.CTkFrame(right, fg_color="transparent")
        btns.pack(fill="x", pady=8)
        ctk.CTkButton(btns, text="Save card", fg_color=theme.ACCENT_DIM, command=self.save_card).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btns, text="Add reference image", fg_color=theme.CARD, command=self.add_ref).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="Build turnaround", fg_color=theme.CARD, command=self.build_turn).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="Delete", fg_color="#4a2430", hover_color="#6a3040", command=self.delete_card).pack(side="right")

    def on_show(self) -> None:
        self.refresh_list()

    def refresh_list(self) -> None:
        for w in self.listbox.winfo_children():
            w.destroy()
        cards = self.app.lib.list_models()
        if not cards:
            ctk.CTkLabel(self.listbox, text="No models yet.\nGenerate a sprite and lock it.", text_color=theme.MUTED, justify="left").pack(anchor="w", padx=8, pady=8)
            return
        for card in cards:
            btn = ctk.CTkButton(
                self.listbox, text=card.name, anchor="w", fg_color=theme.CARD,
                command=lambda cid=card.id: self.select(cid),
            )
            btn.pack(fill="x", pady=3)

    def select(self, model_id: str) -> None:
        card = self.app.lib.get(model_id)
        if not card:
            return
        self.current_id = card.id
        self.name.delete(0, "end")
        self.name.insert(0, card.name)
        self.identity.delete("1.0", "end")
        self.identity.insert("1.0", card.identity)
        self.style.set(STYLES.get(card.style, STYLES["abyssal_iso"])["label"])
        self.view.set(card.view if card.view in VIEWS else "isometric")
        self._draw_refs(card)

    def _draw_refs(self, card) -> None:
        for w in self.refs.winfo_children():
            w.destroy()
        self._thumbs.clear()
        if not card.refs:
            ctk.CTkLabel(self.refs, text="No reference images yet", text_color=theme.MUTED).pack(padx=12, pady=20)
            return
        for role, name in card.refs.items():
            path = card.folder() / name
            frame = ctk.CTkFrame(self.refs, fg_color=theme.PANEL)
            frame.pack(side="left", padx=8, pady=8)
            img = _thumb(path, (120, 140))
            if img:
                self._thumbs.append(img)
                ctk.CTkLabel(frame, image=img, text="").pack()
            ctk.CTkLabel(frame, text=role, text_color=theme.MUTED).pack()

    def save_card(self) -> None:
        if not self.current_id:
            name = self.name.get().strip()
            ident = self.identity.get("1.0", "end").strip()
            if not name or not ident:
                self.app.set_status("Name + identity required.", "warn")
                return
            card = self.app.lib.create(
                name, ident, style=_style_key(self.style.get()), view=self.view.get(),
                bg="green", seed=random.randint(1, 2**31 - 1), width=768, height=1024,
            )
            self.current_id = card.id
            self.refresh_list()
            self.app.set_status(f"Created model {card.name}", "ok")
            return
        card = self.app.lib.get(self.current_id)
        if not card:
            return
        card.name = self.name.get().strip() or card.name
        card.identity = self.identity.get("1.0", "end").strip()
        card.style = _style_key(self.style.get())
        card.view = self.view.get()
        card.save()
        self.refresh_list()
        self.app.set_status("Model card saved.", "ok")

    def import_image(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.webp")])
        if not path:
            return
        name = Path(path).stem
        card = self.app.lib.create(
            name, name, style=_style_key(self.style.get()), view=self.view.get(),
            bg="green", seed=0, width=768, height=1024, ref_image=Path(path), ref_role="front",
        )
        self.refresh_list()
        self.select(card.id)
        self.app.set_status(f"Imported {name}. Fill in the identity lock so poses stay exact.", "ok")

    def add_ref(self) -> None:
        if not self.current_id:
            self.app.set_status("Select or create a model first.", "warn")
            return
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.webp")])
        if not path:
            return
        card = self.app.lib.get(self.current_id)
        self.app.lib.add_ref(card, Path(path), "front")
        self.select(card.id)

    def delete_card(self) -> None:
        if not self.current_id:
            return
        self.app.lib.delete_model(self.current_id)
        self.current_id = None
        self.refresh_list()
        self.app.set_status("Model deleted.", "ok")

    def build_turn(self) -> None:
        if not self.current_id:
            self.app.set_status("Select a locked model first.", "warn")
            return
        card = self.app.lib.get(self.current_id)
        ref = self.app.lib.ref_path(card)
        if not ref:
            self.app.set_status("This model needs a reference image.", "warn")
            return
        frames = ANIMATIONS["turnaround"]["frames"]
        views = ["front", "three_quarter", "side", "three_quarter", "back"]
        roles = ["front", "qfront", "side", "qback", "back"]

        def work():
            client = self.app.client()
            last = ref
            out = []
            for pose, view, role in zip(frames, views, roles):
                prompt = compile_prompt(
                    "", style=card.style, view=view, bg=card.bg,
                    identity=card.identity, pose=pose,
                )
                raws = client.generate(
                    prompt, seed=card.seed or random.randint(1, 2**31 - 1),
                    steps=int(self.app.cfg.get("steps", 24)),
                    width=card.width, height=card.height,
                    guidance=float(self.app.cfg.get("guidance", 3.5)),
                    ref_path=last, denoise=0.42, prefix=f"{card.id}_{role}",
                    dest_dir=card.folder(),
                )
                dest = card.folder() / f"{role}.png"
                process_sprite(raws[0], dest, bg=card.bg, key=True)
                self.app.lib.add_ref(card, dest, role)
                last = dest
                out.append(dest)
            return out

        def done(paths, err):
            if err:
                self.app.set_status(f"Turnaround failed: {err}", "err")
                return
            self.select(card.id)
            self.app.set_status(f"Turnaround saved ({len(paths)} views).", "ok")

        self.app.run_job(work, done, "Building front / 3-4 / side / back from the locked model…")


class AnimatePage(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color=theme.BG)
        self.app = app
        self.frames: list[Path] = []
        self._thumbs: list[ctk.CTkImage] = []
        self._play_i = 0
        self._playing = False
        self._play_img = None
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.last_poses: list[str] = []
        self.last_grounded = True
        self.last_hint = ""

        head = ctk.CTkFrame(self, fg_color=theme.BG)
        head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=18, pady=(18, 8))
        ctk.CTkLabel(head, text="Same model, new motion", text_color=theme.TEXT, font=ctk.CTkFont("Segoe UI", 22, "bold")).pack(anchor="w")
        theme.muted(head, "4-dir / 8-dir keeps the same face and height. Each cell is padded so sprites never overlap on the sheet.", wrap=900).pack(anchor="w")

        form = ctk.CTkScrollableFrame(self, fg_color=theme.PANEL, width=360, corner_radius=12)
        form.grid(row=1, column=0, sticky="nsw", padx=(18, 8), pady=8)
        self.model = ctk.CTkOptionMenu(form, values=["(no models)"], width=300, fg_color=theme.CARD)
        self.model.pack(padx=16, pady=(16, 8))
        self.category = ctk.CTkOptionMenu(form, values=CATEGORIES, width=300, fg_color=theme.CARD, command=self._on_cat)
        self.category.set("all")
        self.category.pack(padx=16, pady=6)
        self.anim = ctk.CTkOptionMenu(form, values=_anim_labels(), width=300, fg_color=theme.CARD, command=self._on_anim)
        self.anim.pack(padx=16, pady=6)
        self.hint = ctk.CTkLabel(form, text="", text_color=theme.MUTED, wraplength=300, justify="left")
        self.hint.pack(padx=16, pady=(0, 8), anchor="w")
        self.dirs = ctk.CTkOptionMenu(
            form,
            values=["This view only"] + [k for k in DIR_SETS if k != "this"],
            width=300,
            fg_color=theme.CARD,
        )
        self.dirs.set("Hades 8-dir")
        self.dirs.pack(padx=16, pady=6)
        self.view = ctk.CTkOptionMenu(form, values=_view_labels(), width=300, fg_color=theme.CARD)
        self.view.pack(padx=16, pady=6)
        self.present = ctk.CTkOptionMenu(
            form, values=presentation_labels(), width=300, fg_color=theme.CARD, command=self._on_present_anim,
        )
        self.present.set(PRESENTATIONS["hades"]["label"])
        self.present.pack(padx=16, pady=6)
        self._on_present_anim(self.present.get())
        self.strength = ctk.CTkOptionMenu(
            form, values=[v["label"] for v in LOCK_STRENGTH.values()], width=300, fg_color=theme.CARD,
        )
        self.strength.set(LOCK_STRENGTH["tight"]["label"])
        self.strength.pack(padx=16, pady=6)
        self.nframes = ctk.CTkOptionMenu(form, values=["4", "5", "6", "8", "10", "12"], width=300, fg_color=theme.CARD)
        self.nframes.set("6")
        self.nframes.pack(padx=16, pady=6)
        self.notes = ctk.CTkEntry(form, placeholder_text="optional extra, e.g. holds a longsword")
        self.notes.pack(fill="x", padx=16, pady=8)
        self.same_h = ctk.CTkCheckBox(form, text="Same height / foot line")
        self.same_h.pack(anchor="w", padx=16, pady=4)
        self.same_h.select()
        ctk.CTkButton(form, text="Generate animation", height=40, fg_color=theme.WARM, hover_color="#d45544", command=self.generate).pack(fill="x", padx=16, pady=(10, 8))

        theme.section(form, "On the fly").pack(anchor="w", padx=16, pady=(12, 4))
        self.fly = ctk.CTkTextbox(form, height=70, fg_color=theme.CARD)
        self.fly.pack(fill="x", padx=16)
        self.fly.insert("1.0", "spins once then slams the weapon into the ground")
        ctk.CTkButton(form, text="Generate this animation", height=36, fg_color=theme.ACCENT_DIM, command=self.generate_fly).pack(fill="x", padx=16, pady=(8, 12))

        theme.section(form, "Keep this move").pack(anchor="w", padx=16, pady=(4, 4))
        self.save_name = ctk.CTkEntry(form, placeholder_text="Name, e.g. Ground Slam")
        self.save_name.pack(fill="x", padx=16, pady=(0, 6))
        ctk.CTkButton(form, text="Save for other sprites", fg_color=theme.CARD, command=self.keep_anim).pack(fill="x", padx=16, pady=(0, 16))
        self._on_anim(self.anim.get())

        right = ctk.CTkFrame(self, fg_color=theme.BG)
        right.grid(row=1, column=1, sticky="nsew", padx=(8, 18), pady=8)
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)
        self.stage = ctk.CTkLabel(right, text="Frames will play here", text_color=theme.MUTED, fg_color=theme.CARD, corner_radius=12)
        self.stage.grid(row=0, column=0, sticky="nsew")
        self.strip = ctk.CTkScrollableFrame(right, height=120, fg_color=theme.PANEL, orientation="horizontal")
        self.strip.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        row = ctk.CTkFrame(right, fg_color="transparent")
        row.grid(row=2, column=0, sticky="ew", pady=10)
        ctk.CTkButton(row, text="Play", fg_color=theme.ACCENT_DIM, command=self.play).pack(side="left", padx=(0, 6))
        ctk.CTkButton(row, text="Stop", fg_color=theme.CARD, command=self.stop).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Export sprite sheet", fg_color=theme.CARD, command=self.export_sheet).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Export pack…", fg_color=theme.CARD, command=lambda: self.app.show("export")).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Open frames folder", fg_color=theme.CARD, command=lambda: __import__("os").startfile(FRAMES)).pack(side="left", padx=6)

    def on_show(self) -> None:
        cards = self.app.lib.list_models()
        names = [c.name for c in cards] or ["(no models)"]
        self.model.configure(values=names)
        if self.model.get() not in names:
            self.model.set(names[0])
        self._refresh_anims()

    def _on_cat(self, _cat: str) -> None:
        self._refresh_anims()

    def _refresh_anims(self) -> None:
        labels = anim_labels(self.category.get())
        if not labels:
            labels = anim_labels("all")
        current = self.anim.get()
        self.anim.configure(values=labels)
        self.anim.set(current if current in labels else labels[0])
        self._on_anim(self.anim.get())

    def _on_anim(self, label: str) -> None:
        _key, spec = anim_by_label(label)
        self.hint.configure(text=spec.get("hint", ""))
        self.nframes.set(str(spec.get("default_frames", 6)))

    def _card(self):
        name = self.model.get()
        for c in self.app.lib.list_models():
            if c.name == name:
                return c
        return None

    def _denoise(self) -> float:
        label = self.strength.get()
        for spec in LOCK_STRENGTH.values():
            if spec["label"] == label:
                return spec["denoise"]
        return 0.42

    def generate(self) -> None:
        key, spec = anim_by_label(self.anim.get())
        n = int(self.nframes.get())
        poses = (spec["frames"] * ((n // max(1, len(spec["frames"]))) + 1))[:n]
        self._run_anim(key, poses, spec.get("grounded", True), spec.get("hint", spec.get("label", key)))

    def generate_fly(self) -> None:
        text = self.fly.get("1.0", "end").strip()
        if not text:
            self.app.set_status("Describe the move first.", "warn")
            return
        n = int(self.nframes.get())
        poses = invent_frames(text, n)
        self.save_name.delete(0, "end")
        self.save_name.insert(0, text[:40])
        self._run_anim("fly_" + slugify(text)[:24], poses, True, text)

    def keep_anim(self) -> None:
        if not self.last_poses:
            self.app.set_status("Generate a move first, then save it.", "warn")
            return
        name = self.save_name.get().strip() or self.last_hint or "Custom move"
        card = save_animation(
            name, self.last_poses,
            hint=self.last_hint or name,
            grounded=self.last_grounded,
            default_frames=len(self.last_poses),
        )
        self.category.set("custom")
        self._refresh_anims()
        self.anim.set(card["label"])
        self.app.set_status(f"Saved “{card['name']}”. Any locked sprite can play it now.", "ok")

    def _on_present_anim(self, label: str) -> None:
        if not hasattr(self, "dirs") or not hasattr(self, "view"):
            return
        _k, spec = presentation_by_label(label)
        if spec.get("dirs") and spec["dirs"] in DIR_SETS:
            self.dirs.set(spec["dirs"])
        if spec.get("view") in VIEWS:
            self.view.set(spec["view"])

    def _dir_jobs(self) -> list[tuple[str, str, str, str]]:
        label = self.dirs.get()
        spec = DIR_SETS.get(label)
        if not spec:
            view = self.view.get()
            return [("this", view, "front", "")]
        return [(name, view, ref, extra) for name, view, ref, extra in spec]

    def _run_anim(self, key: str, poses: list[str], grounded: bool, hint: str) -> None:
        card = self._card()
        if not card:
            self.app.set_status("Lock a model first on the Generate or Lock model page.", "warn")
            return
        base_ref = self.app.lib.ref_path(card)
        if not base_ref:
            self.app.set_status("That model has no reference image.", "warn")
            return
        n = len(poses)
        notes = self.notes.get().strip()
        denoise = self._denoise()
        dest_root = FRAMES / card.id / key
        dest_root.mkdir(parents=True, exist_ok=True)
        self.last_poses = list(poses)
        self.last_grounded = grounded
        self.last_hint = hint
        lock_h = bool(self.same_h.get())
        jobs = self._dir_jobs()

        def work():
            client = self.app.client()
            seed = card.seed or random.randint(1, 2**31 - 1)
            dir_map: dict[str, list] = {}
            all_out: list = []
            qmode = self.app.cfg.get("quality_mode", "quality")
            extra_steps = 4 if qmode == "quality" else 8 if qmode == "studio" else 0
            steps = int(self.app.cfg.get("steps", 24)) + extra_steps
            for d_i, (dname, view, ref_role, facing) in enumerate(jobs):
                dest_dir = dest_root / dname
                dest_dir.mkdir(parents=True, exist_ok=True)
                last = self.app.lib.ref_path(card, ref_role) or base_ref
                row = []
                for i, pose in enumerate(poses):
                    extra = f"{pose}, {HEIGHT_LOCK}, {SOLO_LOCK}"
                    if facing:
                        extra = f"{extra}, {facing}"
                    if grounded:
                        extra = f"{extra}, {GROUND_LOCK}"
                    _pk, pres = presentation_by_label(self.present.get())
                    prompt = compile_prompt(
                        notes, style=card.style, view=view, bg=card.bg,
                        identity=card.identity,
                        pose=f"animation frame {i+1} of {n}: {extra}",
                        presentation=pres.get("lock", ""),
                    )
                    raws = client.generate(
                        prompt, seed=seed + d_i * 100 + i,
                        steps=steps,
                        width=card.width, height=card.height,
                        guidance=float(self.app.cfg.get("guidance", 3.5)),
                        ref_path=last, denoise=denoise,
                        prefix=f"{card.id}_{key}_{dname}_{i:02d}", dest_dir=dest_dir,
                    )
                    dest = dest_dir / f"{i:02d}.png"
                    finish_sprite(raws[0], dest, bg=card.bg, key=True, kind="sprite")
                    last = raws[0]
                    row.append(dest)
                if lock_h:
                    row = stabilize_frames(row, grounded=grounded, pad=24)
                dir_map[dname] = row
                all_out.extend(row)
            if lock_h and all_out:
                all_out = stabilize_frames(all_out, grounded=grounded, pad=24)
                # remap after global stabilize (same paths overwritten)
                offset = 0
                for dname, row in list(dir_map.items()):
                    dir_map[dname] = all_out[offset:offset + len(row)]
                    offset += len(row)
            if len(dir_map) > 1:
                sheet = compose_direction_sheet(dir_map, SHEETS / f"{card.id}_{key}_dirs.png", pad=24)
            else:
                sheet = compose_sheet(all_out, SHEETS / f"{card.id}_{key}.png", cols=len(all_out), pad=16)
            return {"frames": all_out, "sheet": sheet, "dirs": list(dir_map)}

        def done(payload, err):
            if err:
                self.app.set_status(f"Animation failed: {err}", "err")
                return
            self.frames = payload["frames"]
            self.app.last_frames = list(self.frames)
            self.app.last_sheet = payload.get("sheet")
            self._fill_strip()
            if self.frames:
                self._show(self.frames[0])
            dirs = payload.get("dirs") or []
            self.app.set_status(
                f"{len(self.frames)} frames · {len(dirs)} dir(s) · same height, no overlap · {payload['sheet'].name}",
                "ok",
            )

        nd = len(jobs)
        self.app.run_job(
            work, done,
            f"Animating {card.name} — {n} frames × {nd} direction(s), same face/height…",
        )

    def _fill_strip(self) -> None:
        for w in self.strip.winfo_children():
            w.destroy()
        self._thumbs.clear()
        for i, path in enumerate(self.frames):
            img = _thumb(path, (88, 110))
            if not img:
                continue
            self._thumbs.append(img)
            btn = ctk.CTkButton(self.strip, image=img, text=str(i), width=96, fg_color=theme.CARD, command=lambda p=path: self._show(p))
            btn.pack(side="left", padx=4, pady=6)

    def _show(self, path: Path) -> None:
        img = _thumb(path, (640, 640))
        if img:
            self._play_img = img
            self.stage.configure(image=img, text="")

    def play(self) -> None:
        if not self.frames:
            return
        self._playing = True
        self._play_i = 0
        self._tick()

    def _tick(self) -> None:
        if not self._playing or not self.frames:
            return
        self._show(self.frames[self._play_i % len(self.frames)])
        self._play_i += 1
        self.after(140, self._tick)

    def stop(self) -> None:
        self._playing = False

    def export_sheet(self) -> None:
        if not self.frames:
            self.app.set_status("Generate frames first.", "warn")
            return
        dest = unique_out(SHEETS, "sheet")
        compose_sheet(self.frames, dest, cols=len(self.frames))
        self.app.set_status(f"Sheet saved → {dest}", "ok")
        import os
        os.startfile(SHEETS)
