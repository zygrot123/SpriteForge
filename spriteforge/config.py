from __future__ import annotations

import json
from copy import deepcopy

from .bootstrap import resolve_paths
from .paths import CONFIG_PATH, ensure_dirs

DEFAULTS = {
    "comfy_url": "http://127.0.0.1:8188",
    "comfy_root": "",
    "comfy_python": "",
    "engine": "flux",
    "default_style": "abyssal_iso",
    "default_view": "isometric",
    "default_bg": "green",
    "default_size": "768x1024",
    "steps": 20,
    "guidance": 3.5,
    "sampler": "Euler",
    "batch_count": 1,
    "batch_size": 1,
    "hires_fix": False,
    "hires_scale": 2.0,
    "hires_denoise": 0.45,
    "refiner": False,
    "last_seed": -1,
    "lock_strength": "tight",
    "setup_complete": False,
    "install_pack": "flux",
    "quality_mode": "quality",
    "use_memory": True,
    "active_profile": "default",
}


def load_config() -> dict:
    ensure_dirs()
    merged = deepcopy(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            merged.update({k: v for k, v in data.items() if k in DEFAULTS})
        except (json.JSONDecodeError, OSError):
            pass
    root, py = resolve_paths(merged)
    if root and not merged.get("comfy_root"):
        merged["comfy_root"] = str(root)
    if py and not merged.get("comfy_python"):
        merged["comfy_python"] = str(py)
    return merged


def save_config(cfg: dict) -> None:
    ensure_dirs()
    out = deepcopy(DEFAULTS)
    out.update({k: v for k, v in cfg.items() if k in DEFAULTS})
    CONFIG_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
