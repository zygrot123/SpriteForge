from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def exe_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundle_dir() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", exe_dir()))
    return exe_dir()


def user_home() -> Path:
    """Writable data root. Frozen builds use %LOCALAPPDATA%\\SpriteForge."""
    if is_frozen():
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        home = base / "SpriteForge"
        home.mkdir(parents=True, exist_ok=True)
        return home
    return exe_dir()


ROOT = user_home()
PROJECT = exe_dir()
BUNDLE = bundle_dir()
DATA = ROOT / "data"
LIBRARY = ROOT / "library"
MODELS = LIBRARY / "models"
OUTPUTS = LIBRARY / "outputs"
SHEETS = LIBRARY / "sheets"
FRAMES = LIBRARY / "frames"
ANIMS = LIBRARY / "anims"
EXPORTS = LIBRARY / "exports"
VIDEOS = LIBRARY / "videos"
JOBS = LIBRARY / "jobs"
RUNTIME = ROOT / "runtime"
DOWNLOADS = RUNTIME / "downloads"
CONFIG_PATH = ROOT / "config.json"
LOG_PATH = ROOT / "spriteforge.log"
MEMORY = ROOT / "memory"


def default_comfy_candidates() -> list[Path]:
    home = Path.home()
    portable = RUNTIME / "ComfyUI_windows_portable" / "ComfyUI"
    return [
        portable,
        home / "Documents" / "comfy" / "ComfyUI",
        home / "Documents" / "ComfyUI",
        home / "ComfyUI",
        Path(r"C:\ComfyUI"),
        Path(r"C:\ComfyUI_windows_portable\ComfyUI"),
    ]


def find_comfy_python(comfy_root: Path) -> Path | None:
    guesses = [
        comfy_root.parent / "python_embeded" / "python.exe",
        comfy_root / ".venv" / "Scripts" / "python.exe",
        comfy_root / "venv" / "Scripts" / "python.exe",
        comfy_root / "python_embeded" / "python.exe",
    ]
    for p in guesses:
        if p.exists():
            return p
    return None


def discover_comfy() -> tuple[Path | None, Path | None]:
    for root in default_comfy_candidates():
        if (root / "main.py").exists():
            py = find_comfy_python(root)
            if py:
                return root, py
    return None, None


# Back-compat names used by older modules
_disc_root, _disc_py = discover_comfy()
COMFY_DEFAULT = _disc_root or (RUNTIME / "ComfyUI_windows_portable" / "ComfyUI")
COMFY_PYTHON = _disc_py or (RUNTIME / "ComfyUI_windows_portable" / "python_embeded" / "python.exe")
COMFY_INPUT = COMFY_DEFAULT / "input"
COMFY_OUTPUT = COMFY_DEFAULT / "output"


def ensure_dirs() -> None:
    for p in (DATA, LIBRARY, MODELS, OUTPUTS, SHEETS, FRAMES, ANIMS, EXPORTS, VIDEOS, JOBS, RUNTIME, DOWNLOADS, MEMORY):
        p.mkdir(parents=True, exist_ok=True)
