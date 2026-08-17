"""Live job progress: exact counts, percent, and remaining time."""
from __future__ import annotations

import json
import time
from pathlib import Path

from ..paths import ROOT

TIMING_PATH = ROOT / "timing.json"

FIRST_FLUX_HINT = (
    "First Flux image after opening the app loads FLUX.1-dev into VRAM. "
    "That is often 2–4 minutes. After it is warm, each 720p frame is usually 15–40 seconds "
    "on a 50-series GPU. Nothing leaves this PC."
)
WARM_HINT = (
    "Local Flux is sampling on your GPU. The numbers are exact sampler steps from ComfyUI."
)
IDLE_HELP = (
    "While Flux runs you will see exact numbers here:\n"
    "• image 2 / 4\n"
    "• sampler step 14 / 20\n"
    "• 37%\n"
    "• 1m 12s left\n\n"
    "The first image after opening the app is the slow one — the model loads into VRAM "
    "(often 2–4 minutes). Later images skip that load.\n\n"
    "Click ? during a job for the live count and what the current node is doing."
)

NODE_PHASE = {
    "UNETLoader": "Loading Flux UNET into VRAM",
    "DualCLIPLoader": "Loading CLIP + T5",
    "VAELoader": "Loading VAE",
    "CLIPTextEncodeFlux": "Encoding prompt",
    "CLIPTextEncode": "Encoding prompt",
    "EmptyLatentImage": "Allocating latent",
    "LoadImage": "Loading your photo",
    "ImageScale": "Scaling the photo",
    "VAEEncode": "Encoding the photo",
    "ImageToMask": "Building edit mask",
    "SetLatentNoiseMask": "Applying edit mask",
    "KSampler": "Sampling",
    "LatentUpscale": "Latent upscale",
    "VAEDecode": "Decoding pixels",
    "SaveImage": "Saving image",
    "CheckpointLoaderSimple": "Loading checkpoint",
}


def fmt_secs(seconds: float) -> str:
    s = max(0, int(round(float(seconds))))
    if s < 60:
        return f"{s}s"
    m, rem = divmod(s, 60)
    if m < 60:
        return f"{m}m {rem:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"


def load_timing() -> dict:
    if not TIMING_PATH.exists():
        return {}
    try:
        data = json.loads(TIMING_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def record_sample(kind: str, seconds: float) -> None:
    sec = float(seconds)
    if sec < 2 or sec > 3600:
        return
    data = load_timing()
    rows = list(data.get(kind) or [])
    rows.append(round(sec, 2))
    data[kind] = rows[-12:]
    try:
        TIMING_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def avg_sample(kind: str, default: float) -> float:
    rows = [float(x) for x in (load_timing().get(kind) or []) if isinstance(x, (int, float))]
    if not rows:
        return float(default)
    return sum(rows) / len(rows)


def flux_is_warm() -> bool:
    return bool(load_timing().get("flux_image"))


class JobClock:
    def __init__(self, title: str, items: int = 0, steps: int = 0, hint: str = "") -> None:
        self.title = title
        self.items = max(0, int(items))
        self.item = 0
        self.steps = max(0, int(steps))
        self.step = 0
        self.phase = title
        self.node = ""
        self.hint = hint or (WARM_HINT if flux_is_warm() else FIRST_FLUX_HINT)
        self.t0 = time.time()
        self.item_t0 = self.t0
        self.last = self.t0
        self.warm = flux_is_warm()
        self.expected_each = avg_sample("flux_image", 180.0 if not self.warm else 25.0)

    def elapsed(self) -> float:
        return max(0.0, time.time() - self.t0)

    def apply(self, ev: dict) -> None:
        if ev.get("item") is not None:
            item = max(0, int(ev["item"]))
            if item and item != self.item:
                self.item_t0 = time.time()
                self.step = 0
            self.item = item
        if ev.get("items") is not None:
            self.items = max(0, int(ev["items"]))
        if ev.get("step") is not None:
            self.step = max(0, int(ev["step"]))
        if ev.get("steps") is not None and int(ev["steps"]) > 0:
            self.steps = max(0, int(ev["steps"]))
        if ev.get("phase"):
            self.phase = str(ev["phase"])
        if ev.get("node"):
            self.node = str(ev["node"])
        if ev.get("hint"):
            self.hint = str(ev["hint"])
        self.last = time.time()

    def frac(self) -> float:
        step_f = (self.step / self.steps) if self.steps else 0.0
        if self.items > 0:
            done = max(0, self.item - 1) if self.item else 0
            return min(0.99, max(0.0, (done + step_f) / self.items))
        if self.steps:
            return min(0.99, max(0.0, step_f))
        elapsed = self.elapsed()
        guess = self.expected_each * max(self.items, 1)
        return min(0.85, elapsed / max(guess, 8.0))

    def eta(self) -> float | None:
        frac = self.frac()
        elapsed = self.elapsed()
        if frac >= 0.06 and elapsed >= 3:
            return max(0.0, elapsed / frac - elapsed)
        remaining = 1.0
        if self.items > 0:
            done = max(0, self.item - 1) if self.item else 0
            step_f = (self.step / self.steps) if self.steps else 0.0
            remaining = max(0.15, self.items - done - step_f)
        guess = self.expected_each * remaining
        if not self.warm:
            guess = max(guess, max(0.0, 150.0 - elapsed))
        return guess

    def percent(self) -> int:
        return int(round(self.frac() * 100))

    def line(self) -> str:
        bits = [self.phase or self.title]
        if self.items:
            cur = self.item or 1
            bits.append(f"{cur} / {self.items}")
        if self.steps:
            bits.append(f"step {self.step} / {self.steps}")
        bits.append(f"{self.percent()}%")
        return "  ·  ".join(bits)

    def help_text(self) -> str:
        eta = self.eta()
        lines = [
            "This job is 100% local (ComfyUI + Flux on your GPU).",
            "",
            f"Job: {self.title}",
            f"Now: {self.phase}",
        ]
        if self.items:
            lines.append(f"Image / frame: {self.item or 0} / {self.items}")
        if self.steps:
            lines.append(f"Sampler step: {self.step} / {self.steps}")
        lines.append(f"Progress: {self.percent()}%")
        lines.append(f"Elapsed: {fmt_secs(self.elapsed())}")
        lines.append(f"Estimate left: {fmt_secs(eta) if eta is not None else '…'}")
        if self.node:
            lines.append(f"Engine node: {self.node}")
        lines += ["", self.hint]
        return "\n".join(lines)
