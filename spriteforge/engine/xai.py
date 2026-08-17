from __future__ import annotations

import base64
import json
from pathlib import Path
from urllib.request import Request, urlopen

from ..paths import OUTPUTS


class XAIError(RuntimeError):
    pass


class XAIClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = (api_key or "").strip()
        if not self.api_key:
            raise XAIError("Add an XAI_API_KEY in Settings to use SpaceXAI.")

    def _post(self, path: str, payload: dict) -> dict:
        req = Request(
            "https://api.x.ai/v1" + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        with urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _save(self, data: dict, dest: Path) -> Path:
        items = data.get("data") or []
        if not items:
            raise XAIError(f"No image in SpaceXAI response: {data}")
        item = items[0]
        dest.parent.mkdir(parents=True, exist_ok=True)
        if item.get("b64_json"):
            dest.write_bytes(base64.b64decode(item["b64_json"]))
            return dest
        url = item.get("url")
        if not url:
            raise XAIError("SpaceXAI returned neither url nor b64_json")
        with urlopen(url, timeout=120) as resp:
            dest.write_bytes(resp.read())
        return dest

    def chat(self, messages: list[dict], model: str = "grok-3-mini") -> str:
        last_err = None
        for mid in (model, "grok-3", "grok-4-1-fast-non-reasoning"):
            try:
                data = self._post(
                    "/chat/completions",
                    {"model": mid, "messages": messages, "temperature": 0.4},
                )
                choice = (data.get("choices") or [{}])[0]
                text = ((choice.get("message") or {}).get("content") or "").strip()
                if text:
                    return text
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                continue
        raise XAIError(f"Chat failed: {last_err}")

    def generate(self, prompt: str, dest: Path | None = None) -> Path:
        dest = dest or (OUTPUTS / "xai.png")
        data = self._post(
            "/images/generations",
            {
                "model": "grok-imagine-image-2.0",
                "prompt": prompt,
                "n": 1,
                "response_format": "b64_json",
            },
        )
        return self._save(data, dest)

    def video(self, prompt: str, dest: Path, image_path: Path | None = None, duration: int = 6) -> Path:
        payload: dict = {
            "model": "grok-imagine-video-1.5",
            "prompt": prompt,
            "duration": int(duration),
        }
        if image_path:
            raw = Path(image_path).read_bytes()
            b64 = base64.b64encode(raw).decode("ascii")
            mime = "image/png" if str(image_path).lower().endswith(".png") else "image/jpeg"
            payload["image"] = {"url": f"data:{mime};base64,{b64}", "type": "image_url"}
        data = self._post("/videos/generations", payload)
        req_id = data.get("request_id") or data.get("id")
        url = None
        if data.get("video", {}).get("url"):
            url = data["video"]["url"]
        elif data.get("url"):
            url = data["url"]
        else:
            if not req_id:
                raise XAIError(f"Video job did not return an id: {data}")
            import time
            for _ in range(60):
                rec = self._get(f"/videos/{req_id}")
                status = rec.get("status")
                if status == "done":
                    url = (rec.get("video") or {}).get("url") or rec.get("url")
                    break
                if status in {"failed", "expired"}:
                    raise XAIError(f"Video {status}: {rec}")
                time.sleep(5)
        if not url:
            raise XAIError("Video finished without a URL")
        dest.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(url, timeout=180) as resp:
            dest.write_bytes(resp.read())
        return dest

    def _get(self, path: str) -> dict:
        req = Request(
            "https://api.x.ai/v1" + path,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        with urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def edit(self, prompt: str, image_path: Path, dest: Path | None = None) -> Path:
        dest = dest or (OUTPUTS / "xai_edit.png")
        raw = Path(image_path).read_bytes()
        b64 = base64.b64encode(raw).decode("ascii")
        mime = "image/png" if str(image_path).lower().endswith(".png") else "image/jpeg"
        data = self._post(
            "/images/edits",
            {
                "model": "grok-imagine-image-2.0",
                "prompt": prompt,
                "image": {"url": f"data:{mime};base64,{b64}", "type": "image_url"},
                "response_format": "b64_json",
            },
        )
        return self._save(data, dest)
