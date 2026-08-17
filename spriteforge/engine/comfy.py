from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from ..paths import COMFY_INPUT, OUTPUTS
from .progress import NODE_PHASE

ProgressCb = Callable[[dict], None]


class ComfyError(RuntimeError):
    pass


def _ws_send(sock: socket.socket, opcode: int, payload: bytes = b"") -> None:
    mask = os.urandom(4)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    header = bytes([0x80 | opcode])
    n = len(payload)
    if n < 126:
        header += bytes([0x80 | n])
    elif n < 65536:
        header += bytes([0x80 | 126]) + struct.pack("!H", n)
    else:
        header += bytes([0x80 | 127]) + struct.pack("!Q", n)
    sock.sendall(header + mask + masked)


def _recv_exact(sock: socket.socket, n: int) -> bytes | None:
    buf = b""
    while len(buf) < n:
        try:
            chunk = sock.recv(n - len(buf))
        except TimeoutError:
            return None
        except OSError:
            return None
        if not chunk:
            return None
        buf += chunk
    return buf


def _ws_read(sock: socket.socket) -> tuple[int, bytes] | None:
    old = sock.gettimeout()
    sock.settimeout(0.35)
    head = _recv_exact(sock, 2)
    if not head:
        sock.settimeout(old)
        return None
    sock.settimeout(4.0)
    try:
        opcode = head[0] & 0x0F
        masked = bool(head[1] & 0x80)
        length = head[1] & 0x7F
        if length == 126:
            ext = _recv_exact(sock, 2)
            if not ext:
                return None
            length = struct.unpack("!H", ext)[0]
        elif length == 127:
            ext = _recv_exact(sock, 8)
            if not ext:
                return None
            length = struct.unpack("!Q", ext)[0]
        mask = b""
        if masked:
            mask = _recv_exact(sock, 4) or b""
            if len(mask) != 4:
                return None
        payload = _recv_exact(sock, int(length)) if length else b""
        if payload is None:
            return None
        if mask:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return opcode, payload
    finally:
        sock.settimeout(old)


def _ws_connect(host: str, port: int, client_id: str, timeout: float = 4.0) -> socket.socket:
    sock = socket.create_connection((host, port), timeout=timeout)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    req = (
        f"GET /ws?clientId={client_id} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    )
    sock.sendall(req.encode("ascii"))
    buf = b""
    sock.settimeout(timeout)
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            sock.close()
            raise OSError("websocket handshake closed")
        buf += chunk
    if b" 101 " not in buf.split(b"\r\n", 1)[0] and b"101" not in buf.split(b"\r\n", 1)[0]:
        sock.close()
        raise OSError("websocket handshake failed")
    sock.settimeout(0.35)
    return sock


class _WsWatch:
    def __init__(self, host: str, port: int, client_id: str, on_msg: Callable[[dict], None]) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self.on_msg = on_msg
        self._stop = threading.Event()
        self._sock: socket.socket | None = None
        self.thread = threading.Thread(target=self._run, name="comfy-ws", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self._stop.set()
        sock = self._sock
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def _run(self) -> None:
        try:
            self._sock = _ws_connect(self.host, self.port, self.client_id)
        except OSError:
            return
        sock = self._sock
        while not self._stop.is_set():
            try:
                frame = _ws_read(sock)
            except OSError:
                break
            if frame is None:
                continue
            opcode, payload = frame
            if opcode == 0x8:
                break
            if opcode == 0x9:
                try:
                    _ws_send(sock, 0xA, payload)
                except OSError:
                    break
                continue
            if opcode != 0x1:
                continue
            try:
                msg = json.loads(payload.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if isinstance(msg, dict):
                try:
                    self.on_msg(msg)
                except Exception:
                    continue


class ComfyClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8188", comfy_root: str = "") -> None:
        self.base = base_url.rstrip("/")
        self.comfy_root = Path(comfy_root) if comfy_root else None
        self.client_id = f"spriteforge-{uuid.uuid4().hex[:8]}"
        self.on_progress: ProgressCb | None = None
        self.job_item = 0
        self.job_items = 0
        self._last_graph: dict = {}

    def mark_item(self, item: int, items: int, phase: str = "") -> None:
        self.job_item = int(item)
        self.job_items = int(items)
        self._emit({"phase": phase or f"{item} / {items}", "item": item, "items": items, "step": 0})

    def _emit(self, ev: dict) -> None:
        payload = {
            "item": self.job_item,
            "items": self.job_items,
            **ev,
        }
        cb = self.on_progress
        if cb:
            try:
                cb(payload)
            except Exception:
                pass

    def _host_port(self) -> tuple[str, int]:
        u = urlparse(self.base)
        return u.hostname or "127.0.0.1", int(u.port or 8188)

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

    def wait(self, prompt_id: str, timeout: float = 1800, poll: float = 0.6, steps: int = 0) -> dict:
        host, port = self._host_port()
        watch: _WsWatch | None = None
        expected = max(0, int(steps))

        def on_ws(msg: dict) -> None:
            kind = msg.get("type")
            data = msg.get("data") or {}
            if kind == "progress":
                value = int(data.get("value") or 0)
                mx = int(data.get("max") or expected or 0)
                self._emit({
                    "phase": "Sampling",
                    "step": value,
                    "steps": mx,
                    "node": str(data.get("node") or "KSampler"),
                })
                return
            if kind == "executing":
                nid = data.get("node")
                if nid is None:
                    self._emit({"phase": "Saving image", "node": "SaveImage"})
                    return
                nid = str(nid)
                cls = (self._last_graph or {}).get(nid, {}).get("class_type") or ""
                phase = NODE_PHASE.get(cls, f"Working ({cls or nid})")
                ev = {"phase": phase, "node": cls or nid}
                if cls == "UNETLoader":
                    ev["hint"] = (
                        "FLUX.1-dev is loading into VRAM. First time after opening the app "
                        "is the slow one (often 2–4 min). Later images skip this."
                    )
                self._emit(ev)
                return
            if kind == "status":
                left = ((data.get("status") or {}).get("exec_info") or {}).get("queue_remaining")
                try:
                    left_n = int(left)
                except (TypeError, ValueError):
                    left_n = 0
                if left_n > 1:
                    self._emit({"phase": f"Queued — {left_n - 1} job(s) ahead"})

        try:
            watch = _WsWatch(host, port, self.client_id, on_ws)
            watch.start()
        except OSError:
            watch = None

        t0 = time.time()
        try:
            while time.time() - t0 < timeout:
                hist = self._json(f"/history/{prompt_id}", timeout=30)
                job = hist.get(prompt_id)
                if job and job.get("outputs"):
                    if expected:
                        self._emit({"phase": "Saving image", "step": expected, "steps": expected})
                    return job
                if job and job.get("status", {}).get("status_str") == "error":
                    raise ComfyError(f"ComfyUI job failed: {job.get('status')}")
                time.sleep(poll)
        finally:
            if watch:
                watch.close()
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
        sampler_name: str = "euler",
        scheduler: str = "simple",
        batch_size: int = 1,
        hires_fix: bool = False,
        hires_scale: float = 2.0,
        hires_denoise: float = 0.45,
    ) -> dict:
        from .sampling import snap16

        width = snap16(width)
        height = snap16(height)
        batch_size = max(1, int(batch_size))
        base_w, base_h = width, height
        if hires_fix and hires_scale > 1.01:
            base_w = snap16(int(width / float(hires_scale)))
            base_h = snap16(int(height / float(hires_scale)))
        graph = {
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
                "inputs": {"width": int(base_w), "height": int(base_h), "batch_size": batch_size},
            },
            "6": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["1", 0],
                    "seed": int(seed),
                    "steps": int(steps),
                    "cfg": 1.0,
                    "sampler_name": sampler_name,
                    "scheduler": scheduler,
                    "denoise": 1.0,
                    "positive": ["4", 0],
                    "negative": ["4", 0],
                    "latent_image": ["5", 0],
                },
            },
        }
        decode_from = "6"
        if hires_fix and hires_scale > 1.01:
            graph["10"] = {
                "class_type": "LatentUpscale",
                "inputs": {
                    "samples": ["6", 0],
                    "upscale_method": "bislerp",
                    "width": int(width),
                    "height": int(height),
                    "crop": "disabled",
                },
            }
            graph["11"] = {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["1", 0],
                    "seed": int(seed) + 1,
                    "steps": max(8, int(steps) // 2),
                    "cfg": 1.0,
                    "sampler_name": sampler_name,
                    "scheduler": scheduler,
                    "denoise": float(hires_denoise),
                    "positive": ["4", 0],
                    "negative": ["4", 0],
                    "latent_image": ["10", 0],
                },
            }
            decode_from = "11"
        graph["7"] = {"class_type": "VAEDecode", "inputs": {"samples": [decode_from, 0], "vae": ["3", 0]}}
        graph["9"] = {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": prefix}}
        return graph

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
        sampler_name: str = "euler",
        scheduler: str = "simple",
        scale_width: int | None = None,
        scale_height: int | None = None,
        mask_name: str | None = None,
    ) -> dict:
        graph = {
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
        }
        pixels: list = ["5", 0]
        if scale_width and scale_height:
            graph["5b"] = {
                "class_type": "ImageScale",
                "inputs": {
                    "image": ["5", 0],
                    "upscale_method": "lanczos",
                    "width": int(scale_width),
                    "height": int(scale_height),
                    "crop": "disabled",
                },
            }
            pixels = ["5b", 0]
        graph["6"] = {"class_type": "VAEEncode", "inputs": {"pixels": pixels, "vae": ["3", 0]}}
        latent: list = ["6", 0]
        if mask_name:
            graph["5m"] = {"class_type": "LoadImage", "inputs": {"image": mask_name}}
            graph["5n"] = {"class_type": "ImageToMask", "inputs": {"image": ["5m", 0], "channel": "red"}}
            graph["6m"] = {
                "class_type": "SetLatentNoiseMask",
                "inputs": {"samples": ["6", 0], "mask": ["5n", 0]},
            }
            latent = ["6m", 0]
        graph.update({
            "7": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["1", 0],
                    "seed": int(seed),
                    "steps": int(steps),
                    "cfg": 1.0,
                    "sampler_name": sampler_name,
                    "scheduler": scheduler,
                    "denoise": float(denoise),
                    "positive": ["4", 0],
                    "negative": ["4", 0],
                    "latent_image": latent,
                },
            },
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
            "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": prefix}},
        })
        return graph

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
        sampler_name: str = "dpmpp_2m",
        scheduler: str = "karras",
        batch_size: int = 1,
    ) -> dict:
        return {
            "0": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}},
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["0", 1]}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["0", 1]}},
            "3": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": int(width), "height": int(height), "batch_size": max(1, int(batch_size))},
            },
            "4": {"class_type": "VAELoader", "inputs": {"vae_name": "sdxl_vae.safetensors"}},
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["0", 0],
                    "positive": ["1", 0],
                    "negative": ["2", 0],
                    "latent_image": ["3", 0],
                    "sampler_name": sampler_name,
                    "scheduler": scheduler,
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
        sampler_name: str = "euler",
        scheduler: str = "simple",
        batch_size: int = 1,
        hires_fix: bool = False,
        hires_scale: float = 2.0,
        hires_denoise: float = 0.45,
        cfg: float | None = None,
        scale_width: int | None = None,
        scale_height: int | None = None,
        mask_path: str | Path | None = None,
    ) -> list[Path]:
        dest = dest_dir or OUTPUTS
        sdxl_cfg = float(cfg if cfg is not None else 6.0)
        if engine == "sdxl" and not ref_path:
            graph = self.sdxl_txt2img(
                prompt, negative or "blurry, text, watermark",
                seed=seed, steps=steps, width=width, height=height, prefix=prefix,
                cfg=sdxl_cfg, sampler_name=sampler_name, scheduler=scheduler,
                batch_size=batch_size,
            )
        elif ref_path:
            name = self.upload(Path(ref_path))
            mask_name = self.upload(Path(mask_path)) if mask_path and Path(mask_path).exists() else None
            graph = self.flux_img2img(
                prompt, name, seed=seed, steps=steps, denoise=denoise,
                guidance=guidance, prefix=prefix,
                sampler_name=sampler_name, scheduler=scheduler,
                scale_width=scale_width, scale_height=scale_height,
                mask_name=mask_name,
            )
        else:
            graph = self.flux_txt2img(
                prompt, seed=seed, steps=steps, width=width, height=height,
                guidance=guidance, prefix=prefix,
                sampler_name=sampler_name, scheduler=scheduler,
                batch_size=batch_size, hires_fix=hires_fix,
                hires_scale=hires_scale, hires_denoise=hires_denoise,
            )
        self._last_graph = graph
        ks_steps = int(steps)
        for node in graph.values():
            if (node or {}).get("class_type") == "KSampler":
                try:
                    ks_steps = int((node.get("inputs") or {}).get("steps") or steps)
                except (TypeError, ValueError):
                    pass
                break
        self._emit({
            "phase": "Queued on local Flux",
            "step": 0,
            "steps": ks_steps,
            "item": self.job_item,
            "items": self.job_items,
        })
        pid = self.queue_prompt(graph)
        job = self.wait(pid, steps=ks_steps)
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
