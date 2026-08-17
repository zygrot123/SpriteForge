from __future__ import annotations

import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..paths import COMFY_INPUT, OUTPUTS


class ComfyError(RuntimeError):
    pass


class ComfyClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8188", comfy_root: str = "") -> None:
        self.base = base_url.rstrip("/")
        self.comfy_root = Path(comfy_root) if comfy_root else None
        self.client_id = f"spriteforge-{uuid.uuid4().hex[:8]}"

    def _json(self, path: str, payload: dict | None = None, timeout: float = 60) -> Any:
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = Request(self.base + path, data=data, headers=headers)
        try:
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except URLError as exc:
            raise ComfyError(f"ComfyUI is not reachable at {self.base}: {exc}") from exc
        except TimeoutError as exc:
            raise ComfyError(f"ComfyUI timed out on {path}") from exc

    def ping(self) -> dict:
        return self._json("/system_stats", timeout=4)

    def online(self) -> bool:
        try:
            self.ping()
            return True
        except ComfyError:
            return False

    def object_info(self, node: str | None = None) -> dict:
        path = f"/object_info/{node}" if node else "/object_info"
        return self._json(path, timeout=20)

    def flux_ready(self) -> bool:
        try:
            info = self.object_info()
            unets = info.get("UNETLoader", {}).get("input", {}).get("required", {}).get("unet_name", [[]])[0]
            clips = info.get("DualCLIPLoader", {}).get("input", {}).get("required", {}).get("clip_name1", [[]])[0]
            vaes = info.get("VAELoader", {}).get("input", {}).get("required", {}).get("vae_name", [[]])[0]
            return (
                "flux1-dev-fp8.safetensors" in unets
                and "t5xxl_fp8_e4m3fn.safetensors" in clips
                and "ae.safetensors" in vaes
            )
        except (ComfyError, KeyError, IndexError, TypeError):
            return False

    def sdxl_ready(self) -> bool:
        try:
            info = self.object_info()
            ckpts = info.get("CheckpointLoaderSimple", {}).get("input", {}).get("required", {}).get("ckpt_name", [[]])[0]
            return "sd_xl_base_1.0.safetensors" in ckpts
        except (ComfyError, KeyError, IndexError, TypeError):
            return False

    def queue_prompt(self, graph: dict) -> str:
        out = self._json("/prompt", {"prompt": graph, "client_id": self.client_id}, timeout=60)
        pid = out.get("prompt_id")
        if not pid:
            raise ComfyError(f"ComfyUI did not queue the job: {out}")
        return str(pid)

    def wait(self, prompt_id: str, timeout: float = 1800, poll: float = 1.5) -> dict:
        t0 = time.time()
        while time.time() - t0 < timeout:
            hist = self._json(f"/history/{prompt_id}", timeout=30)
            job = hist.get(prompt_id)
            if job and job.get("outputs"):
                return job
            if job and job.get("status", {}).get("status_str") == "error":
                raise ComfyError(f"ComfyUI job failed: {job.get('status')}")
            time.sleep(poll)
        raise ComfyError(f"Job {prompt_id} timed out after {int(timeout)}s")

    def download_outputs(self, job: dict, dest_dir: Path, prefix: str) -> list[Path]:
        dest_dir.mkdir(parents=True, exist_ok=True)
        saved: list[Path] = []
        index = 0
        for _nid, node in (job.get("outputs") or {}).items():
            for img in node.get("images") or []:
                filename = img.get("filename")
                if not filename:
                    continue
                query = urlencode(
                    {
                        "filename": filename,
                        "subfolder": img.get("subfolder") or "",
                        "type": img.get("type") or "output",
                    }
                )
                req = Request(f"{self.base}/view?{query}")
                with urlopen(req, timeout=120) as resp:
                    blob = resp.read()
                ext = Path(filename).suffix or ".png"
                index += 1
                out = dest_dir / f"{prefix}_{index:02d}{ext}"
                out.write_bytes(blob)
                saved.append(out)
        if not saved:
            raise ComfyError("ComfyUI finished but returned no images")
        return saved

    def upload(self, src: Path) -> str:
        src = Path(src)
        if not src.exists():
            raise ComfyError(f"Reference image missing: {src}")
        inp = self.comfy_root / "input" if self.comfy_root else COMFY_INPUT
        inp.mkdir(parents=True, exist_ok=True)
        dest = inp / f"sf_{uuid.uuid4().hex[:10]}{src.suffix.lower() or '.png'}"
        shutil.copyfile(src, dest)
        return dest.name

    def flux_txt2img(
        self,
        prompt: str,
        *,
        seed: int,
        steps: int = 24,
        width: int = 768,
        height: int = 1024,
        guidance: float = 3.5,
        prefix: str = "sprite",
    ) -> dict:
        return {
            "1": {
                "class_type": "UNETLoader",
                "inputs": {"unet_name": "flux1-dev-fp8.safetensors", "weight_dtype": "fp8_e4m3fn"},
            },
            "2": {
                "class_type": "DualCLIPLoader",
                "inputs": {
                    "clip_name1": "t5xxl_fp8_e4m3fn.safetensors",
                    "clip_name2": "clip_l.safetensors",
                    "type": "flux",
                },
            },
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
            "4": {
                "class_type": "CLIPTextEncodeFlux",
                "inputs": {"clip": ["2", 0], "clip_l": prompt, "t5xxl": prompt, "guidance": guidance},
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": int(width), "height": int(height), "batch_size": 1},
            },
            "6": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["1", 0],
                    "seed": int(seed),
                    "steps": int(steps),
                    "cfg": 1.0,
                    "sampler_name": "euler",
                    "scheduler": "simple",
                    "denoise": 1.0,
                    "positive": ["4", 0],
                    "negative": ["4", 0],
                    "latent_image": ["5", 0],
                },
            },
            "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["3", 0]}},
            "9": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": prefix}},
        }

    def flux_img2img(
        self,
        prompt: str,
        image_name: str,
        *,
        seed: int,
        steps: int = 24,
        denoise: float = 0.42,
        guidance: float = 3.5,
        prefix: str = "sprite_i2i",
    ) -> dict:
        return {
            "1": {
                "class_type": "UNETLoader",
                "inputs": {"unet_name": "flux1-dev-fp8.safetensors", "weight_dtype": "fp8_e4m3fn"},
            },
            "2": {
                "class_type": "DualCLIPLoader",
                "inputs": {
                    "clip_name1": "t5xxl_fp8_e4m3fn.safetensors",
                    "clip_name2": "clip_l.safetensors",
                    "type": "flux",
                },
            },
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
            "4": {
                "class_type": "CLIPTextEncodeFlux",
                "inputs": {"clip": ["2", 0], "clip_l": prompt, "t5xxl": prompt, "guidance": guidance},
            },
            "5": {"class_type": "LoadImage", "inputs": {"image": image_name}},
            "6": {"class_type": "VAEEncode", "inputs": {"pixels": ["5", 0], "vae": ["3", 0]}},
            "7": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["1", 0],
                    "seed": int(seed),
                    "steps": int(steps),
                    "cfg": 1.0,
                    "sampler_name": "euler",
                    "scheduler": "simple",
                    "denoise": float(denoise),
                    "positive": ["4", 0],
                    "negative": ["4", 0],
                    "latent_image": ["6", 0],
                },
            },
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
            "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": prefix}},
        }

    def sdxl_txt2img(
        self,
        prompt: str,
        negative: str,
        *,
        seed: int,
        steps: int = 28,
        width: int = 768,
        height: int = 1024,
        cfg: float = 6.0,
        prefix: str = "sprite",
    ) -> dict:
        return {
            "0": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}},
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["0", 1]}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["0", 1]}},
            "3": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": int(width), "height": int(height), "batch_size": 1},
            },
            "4": {"class_type": "VAELoader", "inputs": {"vae_name": "sdxl_vae.safetensors"}},
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["0", 0],
                    "positive": ["1", 0],
                    "negative": ["2", 0],
                    "latent_image": ["3", 0],
                    "sampler_name": "dpmpp_2m",
                    "scheduler": "karras",
                    "seed": int(seed),
                    "steps": int(steps),
                    "cfg": float(cfg),
                    "denoise": 1.0,
                },
            },
            "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["4", 0]}},
            "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": prefix, "images": ["6", 0]}},
        }

    def generate(
        self,
        prompt: str,
        *,
        engine: str = "flux",
        seed: int,
        steps: int = 24,
        width: int = 768,
        height: int = 1024,
        guidance: float = 3.5,
        negative: str = "",
        ref_path: str | Path | None = None,
        denoise: float = 0.42,
        prefix: str = "sprite",
        dest_dir: Path | None = None,
    ) -> list[Path]:
        dest = dest_dir or OUTPUTS
        if engine == "sdxl" and not ref_path:
            graph = self.sdxl_txt2img(
                prompt, negative or "blurry, text, watermark",
                seed=seed, steps=steps, width=width, height=height, prefix=prefix,
            )
        elif ref_path:
            name = self.upload(Path(ref_path))
            graph = self.flux_img2img(
                prompt, name, seed=seed, steps=steps, denoise=denoise,
                guidance=guidance, prefix=prefix,
            )
        else:
            graph = self.flux_txt2img(
                prompt, seed=seed, steps=steps, width=width, height=height,
                guidance=guidance, prefix=prefix,
            )
        pid = self.queue_prompt(graph)
        job = self.wait(pid)
        return self.download_outputs(job, dest, prefix)


def start_comfy(python_exe: Path, comfy_root: Path, log_path: Path | None = None) -> subprocess.Popen:
    python_exe = Path(python_exe)
    comfy_root = Path(comfy_root)
    if not python_exe.exists():
        raise ComfyError(f"ComfyUI python not found: {python_exe}")
    if not (comfy_root / "main.py").exists():
        raise ComfyError(f"ComfyUI main.py not found in {comfy_root}")
    args = [str(python_exe)]
    if python_exe.parent.name == "python_embeded":
        args.extend(["-s", "main.py", "--windows-standalone-build"])
    else:
        args.append("main.py")
    args.extend(["--listen", "127.0.0.1", "--port", "8188"])
    log_fh = None
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fh = open(log_path, "a", encoding="utf-8")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(
        args,
        cwd=str(comfy_root),
        stdout=log_fh or subprocess.DEVNULL,
        stderr=log_fh or subprocess.DEVNULL,
        creationflags=flags,
    )
