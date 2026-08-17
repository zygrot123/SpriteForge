from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zipfile

from .paths import BUNDLE, DOWNLOADS, RUNTIME, discover_comfy, find_comfy_python

ProgressFn = Callable[[str, float, str], None]


SEVEN_ZIP_URL = "https://www.7-zip.org/a/7zr.exe"
FFMPEG_ZIP_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

COMFY_PACKS = {
    "nvidia": {
        "label": "NVIDIA GPU (recommended)",
        "url": "https://github.com/Comfy-Org/ComfyUI/releases/latest/download/ComfyUI_windows_portable_nvidia.7z",
        "archive": "ComfyUI_windows_portable_nvidia.7z",
        "folder": "ComfyUI_windows_portable",
    },
    "amd": {
        "label": "AMD GPU",
        "url": "https://github.com/Comfy-Org/ComfyUI/releases/latest/download/ComfyUI_windows_portable_amd.7z",
        "archive": "ComfyUI_windows_portable_amd.7z",
        "folder": "ComfyUI_windows_portable_amd",
    },
    "cpu": {
        "label": "CPU only (very slow)",
        "url": "https://github.com/Comfy-Org/ComfyUI/releases/latest/download/ComfyUI_windows_portable_nvidia.7z",
        "archive": "ComfyUI_windows_portable_nvidia.7z",
        "folder": "ComfyUI_windows_portable",
    },
}

MODELS = {
    "flux_unet": {
        "url": "https://huggingface.co/Comfy-Org/flux1-dev/resolve/main/flux1-dev-fp8.safetensors?download=true",
        "rel": "models/diffusion_models/flux1-dev-fp8.safetensors",
        "packs": {"flux", "full"},
        "label": "FLUX.1-dev fp8 (~16 GB)",
    },
    "clip_l": {
        "url": "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors?download=true",
        "rel": "models/clip/clip_l.safetensors",
        "packs": {"flux", "full"},
        "label": "CLIP-L (~235 MB)",
    },
    "t5xxl": {
        "url": "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors?download=true",
        "rel": "models/text_encoders/t5xxl_fp8_e4m3fn.safetensors",
        "packs": {"flux", "full"},
        "label": "T5-XXL fp8 (~4.6 GB)",
    },
    "ae": {
        "url": "https://huggingface.co/Comfy-Org/Lumina_Image_2.0_Repackaged/resolve/main/split_files/vae/ae.safetensors?download=true",
        "rel": "models/vae/ae.safetensors",
        "packs": {"flux", "full"},
        "label": "FLUX VAE (~320 MB)",
    },
    "sdxl": {
        "url": "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors?download=true",
        "rel": "models/checkpoints/sd_xl_base_1.0.safetensors",
        "packs": {"sdxl", "full"},
        "label": "SDXL base (~6.5 GB)",
    },
    "sdxl_vae": {
        "url": "https://huggingface.co/madebyollin/sdxl-vae-fp16-fix/resolve/main/sdxl_vae.safetensors?download=true",
        "rel": "models/vae/sdxl_vae.safetensors",
        "packs": {"sdxl", "full"},
        "label": "SDXL VAE (~320 MB)",
    },
}

PACK_LABELS = {
    "flux": "Full local (FLUX + ffmpeg for video, ~23 GB)",
    "full": "FLUX + SDXL + ffmpeg (~30 GB)",
    "sdxl": "Lite SDXL + ffmpeg (~9 GB)",
}


@dataclass
class InstallStatus:
    comfy_root: Path | None
    comfy_python: Path | None
    flux: bool
    sdxl: bool
    online_hint: bool = False
    ffmpeg: bool = False
    ffmpeg_path: str = ""
    missing: list = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return bool(self.comfy_root and self.comfy_python and self.comfy_python.exists() and (self.flux or self.sdxl))

    @property
    def sprites_ready(self) -> bool:
        return self.ready

    @property
    def video_ready(self) -> bool:
        return self.ready and self.ffmpeg

    def checklist(self) -> list[tuple[str, bool, str]]:
        return [
            ("ComfyUI engine", bool(self.comfy_root and self.comfy_python), "sprites, animations, scenes"),
            ("FLUX image model", self.flux, "text-to-sprite, lock, Hades camera"),
            ("SDXL (optional)", self.sdxl, "lighter fallback"),
            ("ffmpeg", self.ffmpeg, "text-to-video, image-to-video, MP4 export"),
        ]


def detect_gpu() -> str:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            timeout=6,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        name = out.decode("utf-8", "ignore").strip()
        if name:
            return f"nvidia:{name.splitlines()[0]}"
    except Exception:
        pass
    return "unknown"


def inspect_install(comfy_root: Path | None = None, comfy_python: Path | None = None) -> InstallStatus:
    root, py = comfy_root, comfy_python
    if not root or not py or not Path(py).exists():
        found_root, found_py = discover_comfy()
        root = root or found_root
        py = py or found_py
    flux = sdxl = False
    if root:
        m = Path(root) / "models"
        flux = (m / "diffusion_models" / "flux1-dev-fp8.safetensors").exists() and (
            m / "clip" / "clip_l.safetensors"
        ).exists() and (
            (m / "text_encoders" / "t5xxl_fp8_e4m3fn.safetensors").exists()
            or (m / "clip" / "t5xxl_fp8_e4m3fn.safetensors").exists()
        ) and (m / "vae" / "ae.safetensors").exists()
        sdxl = (m / "checkpoints" / "sd_xl_base_1.0.safetensors").exists()
    ff = locate_ffmpeg()
    missing = []
    if not root or not py:
        missing.append("ComfyUI")
    if not flux and not sdxl:
        missing.append("image model (FLUX)")
    if not ff:
        missing.append("ffmpeg (needed for text-to-video / MP4)")
    return InstallStatus(
        Path(root) if root else None,
        Path(py) if py else None,
        flux,
        sdxl,
        ffmpeg=bool(ff),
        ffmpeg_path=str(ff) if ff else "",
        missing=missing,
    )


def locate_ffmpeg() -> Path | None:
    hits = [
        RUNTIME / "ffmpeg" / "bin" / "ffmpeg.exe",
        RUNTIME / "ffmpeg" / "ffmpeg.exe",
    ]
    if (RUNTIME / "ffmpeg").exists():
        hits.extend((RUNTIME / "ffmpeg").rglob("ffmpeg.exe"))
    w = shutil.which("ffmpeg")
    if w:
        hits.append(Path(w))
    home = Path.home()
    hits.extend((home / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages").glob("**/ffmpeg.exe"))
    hits += [
        Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
        Path(r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"),
    ]
    seen = set()
    for p in hits:
        rp = Path(p)
        key = str(rp).lower()
        if key in seen:
            continue
        seen.add(key)
        if rp.exists():
            return rp
    return None


def setup_needed(cfg: dict | None = None) -> bool:
    cfg = cfg or {}
    root = Path(cfg["comfy_root"]) if cfg.get("comfy_root") else None
    py = Path(cfg["comfy_python"]) if cfg.get("comfy_python") else None
    st = inspect_install(root, py)
    return (not st.ready) or (not st.ffmpeg)


def seven_zip() -> Path:
    bundled = BUNDLE / "tools" / "7zr.exe"
    if bundled.exists():
        return bundled
    dest = RUNTIME / "tools" / "7zr.exe"
    return dest


def _headers(extra: dict | None = None) -> dict:
    h = {
        "User-Agent": "SpriteForge/1.0 (Windows; local installer)",
        "Accept": "*/*",
    }
    if extra:
        h.update(extra)
    return h


def download_file(url: str, dest: Path, progress: ProgressFn | None = None, label: str = "") -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    existing = part.stat().st_size if part.exists() else 0
    headers = _headers()
    if existing:
        headers["Range"] = f"bytes={existing}-"

    last_error: Exception | None = None
    for attempt in range(5):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=60) as resp:
                total = resp.headers.get("Content-Length")
                total_n = int(total) if total and total.isdigit() else 0
                if resp.status == 200 and existing:
                    existing = 0
                    if part.exists():
                        part.unlink()
                if resp.headers.get("Content-Range"):
                    # bytes start-end/total
                    try:
                        total_n = int(resp.headers["Content-Range"].split("/")[-1])
                    except ValueError:
                        pass
                elif existing == 0:
                    total_n = total_n
                else:
                    total_n = existing + total_n
                mode = "ab" if existing and resp.status == 206 else "wb"
                if mode == "wb":
                    existing = 0
                done = existing
                t0 = time.time()
                with part.open(mode) as fh:
                    while True:
                        chunk = resp.read(1024 * 1024)
                        if not chunk:
                            break
                        fh.write(chunk)
                        done += len(chunk)
                        if progress:
                            pct = (done / total_n) if total_n else 0.0
                            speed = done / max(0.001, time.time() - t0)
                            msg = f"{label or dest.name}: {_fmt(done)}"
                            if total_n:
                                msg += f" / {_fmt(total_n)}"
                            msg += f"  ({_fmt(speed)}/s)"
                            progress(label or dest.name, min(0.99, pct), msg)
            part.replace(dest)
            if progress:
                progress(label or dest.name, 1.0, f"{label or dest.name}: done ({_fmt(dest.stat().st_size)})")
            return dest
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if progress:
                progress(label or dest.name, 0.0, f"Retry {attempt + 1}/5 — {exc}")
            time.sleep(2 + attempt * 2)
            existing = part.stat().st_size if part.exists() else 0
            headers = _headers({"Range": f"bytes={existing}-"} if existing else None)
    raise RuntimeError(f"Download failed for {url}: {last_error}")


def _fmt(n: float) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TB"


def ensure_7zip(progress: ProgressFn | None = None) -> Path:
    exe = seven_zip()
    if exe.exists():
        return exe
    exe.parent.mkdir(parents=True, exist_ok=True)
    download_file(SEVEN_ZIP_URL, exe, progress, "7-Zip extractor")
    return exe


def extract_7z(archive: Path, dest_dir: Path, progress: ProgressFn | None = None) -> None:
    exe = ensure_7zip(progress)
    dest_dir.mkdir(parents=True, exist_ok=True)
    if progress:
        progress("extract", 0.05, f"Extracting {archive.name}…")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(
        [str(exe), "x", str(archive), f"-o{dest_dir}", "-y"],
        capture_output=True,
        text=True,
        creationflags=flags,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"7-Zip extract failed ({proc.returncode}): {proc.stderr or proc.stdout}")
    if progress:
        progress("extract", 1.0, "Extracted ComfyUI portable")


def portable_root() -> Path:
    return RUNTIME / "ComfyUI_windows_portable"


def comfy_from_portable() -> tuple[Path, Path]:
    root = portable_root() / "ComfyUI"
    py = portable_root() / "python_embeded" / "python.exe"
    return root, py


def install_engine(pack: str = "flux", gpu: str = "nvidia", progress: ProgressFn | None = None) -> InstallStatus:
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    ensure_7zip(progress)

    spec = COMFY_PACKS.get(gpu, COMFY_PACKS["nvidia"])
    archive = DOWNLOADS / spec["archive"]
    extracted_marker = portable_root() / "ComfyUI" / "main.py"
    if not extracted_marker.exists():
        if progress:
            progress("comfy", 0.0, "Downloading ComfyUI portable (~2 GB)…")
        download_file(spec["url"], archive, progress, "ComfyUI portable")
        if progress:
            progress("comfy", 0.9, "Extracting ComfyUI (a few minutes)…")
        extract_7z(archive, RUNTIME, progress)
        # Official archive extracts to ComfyUI_windows_portable or *_amd
        extracted = RUNTIME / spec["folder"]
        target = portable_root()
        if extracted.exists() and extracted.resolve() != target.resolve():
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            extracted.rename(target)
        if not (target / "ComfyUI" / "main.py").exists():
            # Some archives nest an extra folder
            kids = [p for p in RUNTIME.iterdir() if p.is_dir() and (p / "ComfyUI" / "main.py").exists()]
            if kids:
                if target.exists() and target.resolve() != kids[0].resolve():
                    shutil.rmtree(target, ignore_errors=True)
                if kids[0].resolve() != target.resolve():
                    kids[0].rename(target)
        if not (target / "ComfyUI" / "main.py").exists():
            raise RuntimeError("ComfyUI portable extracted but main.py was not found")

    comfy_root, comfy_py = comfy_from_portable()
    wanted = [item for item in MODELS.values() if pack in item["packs"]]
    for item in wanted:
        dest = comfy_root / item["rel"]
        if dest.exists() and dest.stat().st_size > 1_000_000:
            if progress:
                progress(item["label"], 1.0, f"Already have {item['label']}")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        download_file(item["url"], dest, progress, item["label"])

    install_ffmpeg(progress)
    st = inspect_install(comfy_root, comfy_py)
    if not st.ready:
        raise RuntimeError("Download finished but image models are still incomplete. Run setup again to resume.")
    if not st.ffmpeg:
        raise RuntimeError("ffmpeg did not install. Text-to-video needs it — run setup again.")
    return st


def install_ffmpeg(progress: ProgressFn | None = None) -> Path:
    existing = locate_ffmpeg()
    if existing:
        if progress:
            progress("ffmpeg", 1.0, f"Already have ffmpeg ({existing})")
        return existing
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    archive = DOWNLOADS / "ffmpeg-release-essentials.zip"
    if progress:
        progress("ffmpeg", 0.0, "Downloading ffmpeg (~100 MB) for text-to-video / MP4…")
    download_file(FFMPEG_ZIP_URL, archive, progress, "ffmpeg")
    dest_root = RUNTIME / "ffmpeg"
    if dest_root.exists():
        shutil.rmtree(dest_root, ignore_errors=True)
    dest_root.mkdir(parents=True, exist_ok=True)
    if progress:
        progress("ffmpeg", 0.9, "Extracting ffmpeg…")
    with zipfile.ZipFile(archive, "r") as zf:
        zf.extractall(dest_root)
    found = next(dest_root.rglob("ffmpeg.exe"), None)
    if not found:
        raise RuntimeError("ffmpeg zip extracted but ffmpeg.exe was not inside it")
    if progress:
        progress("ffmpeg", 1.0, f"ffmpeg ready ({found})")
    return found


MIN_SIZES = {
    "flux_unet": 10_000_000_000,
    "t5xxl": 3_000_000_000,
    "sdxl": 4_000_000_000,
    "clip_l": 80_000_000,
    "ae": 80_000_000,
    "sdxl_vae": 80_000_000,
    "comfy": 200_000_000,
    "ffmpeg": 1_000_000,
    "seven": 100_000,
}


@dataclass
class Component:
    id: str
    label: str
    url: str
    dest: Path | None
    optional: bool
    status: str  # missing, broken, ok, update, unknown
    local_size: int = 0
    remote_size: int = 0
    detail: str = ""


def remote_size(url: str) -> int:
    try:
        req = Request(url, method="HEAD", headers=_headers())
        with urlopen(req, timeout=20) as resp:
            cl = resp.headers.get("Content-Length")
            return int(cl) if cl and cl.isdigit() else 0
    except Exception:
        return 0


def _file_state(path: Path | None, min_bytes: int) -> tuple[str, int]:
    if not path or not path.exists():
        return "missing", 0
    size = path.stat().st_size
    threshold = (min_bytes * 0.4) if min_bytes < 5_000_000 else max(1_000_000, min_bytes // 20)
    if size < threshold:
        return "broken", size
    return "ok", size


def diagnose_components(pack: str = "flux") -> list[Component]:
    st = inspect_install()
    root = st.comfy_root or (portable_root() / "ComfyUI")
    items: list[Component] = []

    seven = seven_zip()
    s, sz = _file_state(seven if seven.exists() else None, MIN_SIZES["seven"])
    items.append(Component("seven", "7-Zip extractor", SEVEN_ZIP_URL, seven if seven.exists() else RUNTIME / "tools" / "7zr.exe", False, s, sz, 0, "unpacks ComfyUI"))

    marker = None
    if st.comfy_root and (st.comfy_root / "main.py").exists():
        marker = st.comfy_root / "main.py"
    elif (portable_root() / "ComfyUI" / "main.py").exists():
        marker = portable_root() / "ComfyUI" / "main.py"
    s, sz = ("ok", 1) if marker else ("missing", 0)
    items.append(Component(
        "comfy", "ComfyUI engine", COMFY_PACKS["nvidia"]["url"],
        st.comfy_root, False, s, sz, 0, "local image + animation engine",
    ))

    show_keys = [k for k, v in MODELS.items() if pack in v["packs"] or k in {"flux_unet", "clip_l", "t5xxl", "ae"}]
    for key in show_keys:
        spec = MODELS[key]
        dest = root / spec["rel"]
        s, sz = _file_state(dest, MIN_SIZES.get(key, 1_000_000))
        opt = pack not in spec["packs"]
        items.append(Component(key, spec["label"], spec["url"], dest, opt, s, sz, 0, spec["rel"]))

    ff = locate_ffmpeg()
    s, sz = _file_state(ff, MIN_SIZES["ffmpeg"]) if ff else ("missing", 0)
    items.append(Component("ffmpeg", "ffmpeg (video / MP4)", FFMPEG_ZIP_URL, ff, False, s, sz, 0, "text-to-video, image-to-video"))
    return items


def check_updates(comps: list[Component], progress: ProgressFn | None = None) -> list[Component]:
    out = []
    for c in comps:
        if progress:
            progress(c.id, 0.0, f"Checking {c.label}…")
        remote = remote_size(c.url) if c.url else 0
        c.remote_size = remote
        if c.status == "ok" and remote and c.local_size and abs(remote - c.local_size) > 2_000_000:
            # size drift only meaningful for archives (ComfyUI, ffmpeg), not huge HF weights that rarely change
            if c.id in {"comfy", "ffmpeg", "seven"}:
                c.status = "update"
                c.detail = f"update available ({_fmt(c.local_size)} → {_fmt(remote)})"
            elif c.local_size < remote * 0.95:
                c.status = "broken"
                c.detail = f"file smaller than server ({_fmt(c.local_size)} vs {_fmt(remote)})"
        if progress:
            progress(c.id, 1.0, f"{c.label}: {c.status}")
        out.append(c)
    return out


def repair_components(
    pack: str = "flux",
    gpu: str = "nvidia",
    mode: str = "missing",
    progress: ProgressFn | None = None,
) -> InstallStatus:
    """mode: missing | broken | update | all"""
    comps = diagnose_components(pack)
    if mode in {"update", "all"}:
        comps = check_updates(comps, progress)
    for c in comps:
        need = False
        if mode == "missing" and c.status == "missing" and not c.optional:
            need = True
        elif mode == "broken" and c.status in {"missing", "broken"}:
            need = True
        elif mode == "update" and c.status in {"update", "broken", "missing"} and not c.optional:
            need = True
        elif mode == "all" and (not c.optional or c.status != "ok"):
            need = True
        if not need:
            if progress:
                progress(c.id, 1.0, f"{c.label}: skip ({c.status})")
            continue
        if progress:
            progress(c.id, 0.02, f"{c.label}: starting…")
        if c.id == "seven":
            ensure_7zip(progress)
        elif c.id == "comfy":
            existing = inspect_install()
            if existing.comfy_root and (existing.comfy_root / "main.py").exists() and mode != "update":
                if progress:
                    progress("comfy", 1.0, f"Using existing ComfyUI ({existing.comfy_root})")
                continue
            if mode == "update" and (portable_root() / "ComfyUI" / "main.py").exists():
                shutil.rmtree(portable_root(), ignore_errors=True)
            if not existing.comfy_root or not (existing.comfy_root / "main.py").exists() or (
                mode == "update" and existing.comfy_root and portable_root() in existing.comfy_root.parents
            ):
                install_engine(pack=pack, gpu=gpu, progress=progress)
                break
        elif c.id == "ffmpeg":
            if mode in {"update", "broken"} and (RUNTIME / "ffmpeg").exists():
                shutil.rmtree(RUNTIME / "ffmpeg", ignore_errors=True)
            install_ffmpeg(progress)
        elif c.id in MODELS:
            spec = MODELS[c.id]
            root = inspect_install().comfy_root or (portable_root() / "ComfyUI")
            dest = root / spec["rel"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists() and mode in {"update", "broken", "all"}:
                dest.unlink()
            download_file(spec["url"], dest, progress, spec["label"])
    return inspect_install()


def resolve_paths(cfg: dict) -> tuple[Path | None, Path | None]:
    root = Path(cfg["comfy_root"]) if cfg.get("comfy_root") else None
    py = Path(cfg["comfy_python"]) if cfg.get("comfy_python") else None
    if root and py and py.exists() and (root / "main.py").exists():
        return root, py
    return discover_comfy()
