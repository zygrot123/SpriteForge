"""A1111-style sampler names mapped onto ComfyUI KSampler."""
from __future__ import annotations

from dataclasses import dataclass

SAMPLERS: list[tuple[str, str, str]] = [
    ("Euler", "euler", "simple"),
    ("Euler a", "euler_ancestral", "normal"),
    ("DPM++ 2M", "dpmpp_2m", "normal"),
    ("DPM++ 2M Karras", "dpmpp_2m", "karras"),
    ("DPM++ 2M SDE", "dpmpp_2m_sde", "normal"),
    ("DPM++ 2M SDE Karras", "dpmpp_2m_sde", "karras"),
    ("DPM++ SDE", "dpmpp_sde", "normal"),
    ("DPM++ SDE Karras", "dpmpp_sde", "karras"),
    ("DPM++ 2S a", "dpmpp_2s_ancestral", "normal"),
    ("DPM++ 2S a Karras", "dpmpp_2s_ancestral", "karras"),
    ("DPM2", "dpm_2", "normal"),
    ("DPM2 a", "dpm_2_ancestral", "normal"),
    ("DPM2 Karras", "dpm_2", "karras"),
    ("Heun", "heun", "normal"),
    ("LMS", "lms", "normal"),
    ("LMS Karras", "lms", "karras"),
    ("DDIM", "ddim", "ddim_uniform"),
    ("UniPC", "uni_pc", "normal"),
]

SAMPLER_LABELS = [row[0] for row in SAMPLERS]
_BY_LABEL = {row[0]: (row[1], row[2]) for row in SAMPLERS}

SCRIPTS = ["None", "Prompt matrix (|)", "Seed walk"]

HIRES_SCALES = ["1.5", "2.0"]


@dataclass
class SampleSettings:
    sampler: str = "Euler"
    steps: int = 20
    cfg: float = 3.5
    width: int = 1024
    height: int = 1024
    batch_count: int = 1
    batch_size: int = 1
    seed: int = -1
    last_seed: int = -1
    hires_fix: bool = False
    hires_scale: float = 2.0
    hires_denoise: float = 0.45
    refiner: bool = False
    extra: bool = False
    script: str = "None"
    negative: str = ""
    tiling: bool = False

    def comfy_sampler(self) -> tuple[str, str]:
        return resolve_sampler(self.sampler)


def resolve_sampler(label: str) -> tuple[str, str]:
    return _BY_LABEL.get(label, ("euler", "simple"))


def snap16(n: int) -> int:
    return max(16, int(n) // 16 * 16)


def parse_seed(text: str, randomize: bool = False) -> int:
    raw = (text or "").strip()
    if randomize or raw in {"", "-1", "random"}:
        return -1
    try:
        return int(raw)
    except ValueError:
        return -1


def expand_script(prompt: str, script: str) -> list[str]:
    text = (prompt or "").strip()
    if script == "Prompt matrix (|)" and "|" in text:
        parts = [p.strip() for p in text.split("|") if p.strip()]
        return parts or [text]
    return [text]
