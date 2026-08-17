"""Hermes-style local memory: profiles, sessions, and taste that evolves with use."""
from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from ..paths import MEMORY, ensure_dirs

STOP = {
    "a", "an", "the", "and", "or", "of", "in", "on", "with", "to", "as", "for",
    "from", "at", "by", "is", "it", "its", "be", "this", "that", "into", "over",
    "under", "but", "not", "no", "yes", "my", "me", "we", "our", "your", "you",
    "like", "just", "very", "more", "some", "any", "all", "than", "then",
}

WORD = re.compile(r"[a-z0-9']+")


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _sid() -> str:
    return uuid.uuid4().hex[:10]


def _read(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return deepcopy(fallback)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return deepcopy(fallback)


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def extract_phrases(text: str) -> list[str]:
    words = [w for w in WORD.findall((text or "").lower()) if w not in STOP and len(w) > 2]
    out: list[str] = []
    seen: set[str] = set()
    for n in (3, 2, 1):
        for i in range(0, max(0, len(words) - n + 1)):
            phrase = " ".join(words[i : i + n])
            if phrase in seen:
                continue
            if n == 1 and len(phrase) < 4:
                continue
            seen.add(phrase)
            out.append(phrase)
    return out[:24]


def _bump(bag: dict[str, Any], key: str, weight: float, when: str) -> None:
    if not key:
        return
    row = bag.get(key) or {"count": 0.0, "last": when}
    row["count"] = float(row.get("count", 0)) + float(weight)
    row["last"] = when
    bag[key] = row


def _top(bag: dict[str, Any], n: int = 6) -> list[tuple[str, float]]:
    ranked = sorted(
        ((k, float(v.get("count", 0))) for k, v in bag.items()),
        key=lambda kv: kv[1],
        reverse=True,
    )
    return ranked[:n]


class MemoryStore:
    def __init__(self) -> None:
        ensure_dirs()
        MEMORY.mkdir(parents=True, exist_ok=True)
        self.index_path = MEMORY / "index.json"
        self.index = _read(self.index_path, {"active_profile": "default", "profiles": []})
        if not self.index.get("profiles"):
            self._create_profile("default", "Default", "First studio profile")
        if not self.profile_ids():
            self._create_profile("default", "Default", "First studio profile")
        if self.index.get("active_profile") not in self.profile_ids():
            self.index["active_profile"] = self.profile_ids()[0]
            self._save_index()
        if not self.active_session():
            self.new_session()

    def _save_index(self) -> None:
        _write(self.index_path, self.index)

    def root(self, pid: str | None = None) -> Path:
        return MEMORY / "profiles" / (pid or self.active_profile_id())

    def profile_ids(self) -> list[str]:
        return [p["id"] for p in self.index.get("profiles", []) if p.get("id")]

    def profiles(self) -> list[dict]:
        return list(self.index.get("profiles", []))

    def active_profile_id(self) -> str:
        return self.index.get("active_profile") or "default"

    def profile(self, pid: str | None = None) -> dict:
        pid = pid or self.active_profile_id()
        data = _read(
            self.root(pid) / "profile.json",
            {"id": pid, "name": pid, "note": "", "created": _now(), "uses": 0},
        )
        return data

    def longterm(self, pid: str | None = None) -> dict:
        return _read(
            self.root(pid) / "longterm.json",
            {
                "uses": 0,
                "updated": "",
                "styles": {},
                "aspects": {},
                "kinds": {},
                "variants": {},
                "subjects": {},
                "liked": [],
                "pins": [],
                "facts": [],
            },
        )

    def _save_longterm(self, data: dict, pid: str | None = None) -> None:
        _write(self.root(pid) / "longterm.json", data)

    def _create_profile(self, pid: str, name: str, note: str = "") -> dict:
        now = _now()
        meta = {"id": pid, "name": name, "created": now}
        self.index.setdefault("profiles", []).append(meta)
        self.index["active_profile"] = pid
        self._save_index()
        _write(
            self.root(pid) / "profile.json",
            {"id": pid, "name": name, "note": note, "created": now, "uses": 0},
        )
        self._save_longterm(self.longterm(pid), pid)
        return meta

    def create_profile(self, name: str, note: str = "") -> dict:
        base = re.sub(r"[^a-z0-9]+", "-", (name or "profile").strip().lower()).strip("-")[:24] or "profile"
        pid = base
        n = 2
        while pid in self.profile_ids():
            pid = f"{base}-{n}"
            n += 1
        meta = self._create_profile(pid, name.strip() or pid, note.strip())
        self.new_session()
        return meta

    def rename_profile(self, name: str, note: str | None = None) -> None:
        pid = self.active_profile_id()
        data = self.profile(pid)
        data["name"] = name.strip() or data.get("name") or pid
        if note is not None:
            data["note"] = note
        _write(self.root(pid) / "profile.json", data)
        for row in self.index.get("profiles", []):
            if row.get("id") == pid:
                row["name"] = data["name"]
        self._save_index()

    def switch_profile(self, pid: str) -> None:
        if pid not in self.profile_ids():
            return
        self.index["active_profile"] = pid
        self._save_index()
        if not self.active_session():
            self.new_session()

    def delete_profile(self, pid: str) -> bool:
        ids = self.profile_ids()
        if pid not in ids or len(ids) < 2:
            return False
        shutil.rmtree(self.root(pid), ignore_errors=True)
        self.index["profiles"] = [p for p in self.index.get("profiles", []) if p.get("id") != pid]
        if self.active_profile_id() == pid:
            self.index["active_profile"] = self.profile_ids()[0]
        self._save_index()
        if not self.active_session():
            self.new_session()
        return True

    def sessions_dir(self, pid: str | None = None) -> Path:
        d = self.root(pid) / "sessions"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def list_sessions(self, pid: str | None = None) -> list[dict]:
        rows = []
        for path in self.sessions_dir(pid).glob("*.json"):
            data = _read(path, {})
            if data.get("id"):
                rows.append(data)
        rows.sort(key=lambda r: r.get("updated") or r.get("created") or "", reverse=True)
        return rows

    def session_path(self, sid: str, pid: str | None = None) -> Path:
        return self.sessions_dir(pid) / f"{sid}.json"

    def active_session(self, pid: str | None = None) -> dict | None:
        data = self.profile(pid)
        sid = data.get("active_session")
        if not sid:
            return None
        path = self.session_path(sid, pid)
        if not path.exists():
            return None
        return _read(path, None)

    def new_session(self, title: str = "") -> dict:
        pid = self.active_profile_id()
        sid = _sid()
        now = _now()
        sess = {
            "id": sid,
            "title": title.strip() or "Untitled session",
            "created": now,
            "updated": now,
            "kept": False,
            "events": [],
        }
        _write(self.session_path(sid, pid), sess)
        prof = self.profile(pid)
        prof["active_session"] = sid
        _write(self.root(pid) / "profile.json", prof)
        return sess

    def _save_session(self, sess: dict, pid: str | None = None) -> None:
        _write(self.session_path(sess["id"], pid), sess)

    def keep_session(self, sid: str | None = None, kept: bool = True) -> None:
        sess = self._load_sid(sid)
        if not sess:
            return
        sess["kept"] = bool(kept)
        sess["updated"] = _now()
        self._save_session(sess)

    def delete_session(self, sid: str, forget: bool = False) -> bool:
        pid = self.active_profile_id()
        path = self.session_path(sid, pid)
        if not path.exists():
            return False
        if forget:
            self._forget_session_traces(_read(path, {}))
        path.unlink(missing_ok=True)
        prof = self.profile(pid)
        if prof.get("active_session") == sid:
            leftover = self.list_sessions(pid)
            if leftover:
                prof["active_session"] = leftover[0]["id"]
                _write(self.root(pid) / "profile.json", prof)
            else:
                self.new_session()
        return True

    def switch_session(self, sid: str) -> None:
        pid = self.active_profile_id()
        if not self.session_path(sid, pid).exists():
            return
        prof = self.profile(pid)
        prof["active_session"] = sid
        _write(self.root(pid) / "profile.json", prof)

    def _load_sid(self, sid: str | None) -> dict | None:
        sess = self.active_session() if not sid else _read(self.session_path(sid), None)
        return sess if sess and sess.get("id") else None

    def note(
        self,
        kind: str,
        prompt: str = "",
        *,
        style: str = "",
        aspect: str = "",
        variant: int | None = None,
        weight: float = 1.0,
        path: str = "",
    ) -> None:
        now = _now()
        prompt = (prompt or "").strip()
        sess = self.active_session()
        if not sess:
            sess = self.new_session(prompt[:60] if prompt else "")
        if sess.get("title") in {"", "Untitled session"} and prompt:
            sess["title"] = prompt[:72]
        sess.setdefault("events", []).append(
            {
                "when": now,
                "kind": kind,
                "prompt": prompt[:400],
                "style": style,
                "aspect": aspect,
                "variant": variant,
                "path": path,
                "weight": weight,
            }
        )
        sess["events"] = sess["events"][-200:]
        sess["updated"] = now
        self._save_session(sess)

        lt = self.longterm()
        lt["uses"] = int(lt.get("uses", 0)) + 1
        lt["updated"] = now
        _bump(lt.setdefault("kinds", {}), kind, weight, now)
        if style:
            _bump(lt.setdefault("styles", {}), style, weight, now)
        if aspect:
            _bump(lt.setdefault("aspects", {}), aspect, weight, now)
        if variant is not None:
            _bump(lt.setdefault("variants", {}), str(int(variant) + 1), weight, now)
        for phrase in extract_phrases(prompt):
            _bump(lt.setdefault("subjects", {}), phrase, weight, now)
        if weight >= 2 and prompt:
            liked = lt.setdefault("liked", [])
            liked.insert(0, {"when": now, "prompt": prompt[:300], "kind": kind})
            lt["liked"] = liked[:40]
        prof = self.profile()
        prof["uses"] = int(prof.get("uses", 0)) + 1
        _write(self.root() / "profile.json", prof)
        self._evolve(lt)
        self._save_longterm(lt)

    def _evolve(self, lt: dict) -> None:
        facts: list[str] = []
        styles = _top(lt.get("styles", {}), 2)
        aspects = _top(lt.get("aspects", {}), 1)
        subjects = _top(lt.get("subjects", {}), 6)
        variants = _top(lt.get("variants", {}), 1)
        if styles:
            facts.append("Favors " + " and ".join(s for s, _c in styles) + " work")
        if aspects:
            facts.append(f"Usually frames in {aspects[0][0]}")
        if variants and variants[0][1] >= 3:
            facts.append(f"Often keeps variation V{variants[0][0]}")
        if subjects:
            facts.append("Keeps returning to: " + ", ".join(s for s, _c in subjects[:4]))
        kinds = _top(lt.get("kinds", {}), 2)
        if kinds:
            facts.append("Hands-on with " + " and ".join(k for k, _c in kinds))
        if lt.get("uses", 0) >= 8:
            facts.append(f"Taste has evolved across {int(lt['uses'])} uses — stay consistent with past picks")
        lt["facts"] = facts[:8]

    def _forget_session_traces(self, sess: dict) -> None:
        lt = self.longterm()
        prompts = {str(e.get("prompt") or "") for e in sess.get("events", [])}
        lt["liked"] = [row for row in lt.get("liked", []) if row.get("prompt") not in prompts]
        for ev in sess.get("events", []):
            w = float(ev.get("weight") or 1)
            for bag, key in (
                (lt.get("styles", {}), ev.get("style")),
                (lt.get("aspects", {}), ev.get("aspect")),
                (lt.get("kinds", {}), ev.get("kind")),
            ):
                if key and key in bag:
                    bag[key]["count"] = max(0.0, float(bag[key].get("count", 0)) - w)
            for phrase in extract_phrases(ev.get("prompt") or ""):
                bag = lt.get("subjects", {})
                if phrase in bag:
                    bag[phrase]["count"] = max(0.0, float(bag[phrase].get("count", 0)) - w)
        self._evolve(lt)
        self._save_longterm(lt)

    def pin(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        lt = self.longterm()
        pins = lt.setdefault("pins", [])
        if text not in pins:
            pins.insert(0, text)
        lt["pins"] = pins[:30]
        self._save_longterm(lt)

    def unpin(self, text: str) -> None:
        lt = self.longterm()
        lt["pins"] = [p for p in lt.get("pins", []) if p != text]
        self._save_longterm(lt)

    def steer(self) -> str:
        lt = self.longterm()
        bits: list[str] = []
        pins = [p for p in lt.get("pins", []) if p]
        if pins:
            bits.append("Pinned: " + "; ".join(pins[:4]))
        facts = [f for f in lt.get("facts", []) if f]
        if facts:
            bits.append("Evolved: " + "; ".join(facts[:5]))
        liked = [row.get("prompt") for row in lt.get("liked", [])[:2] if row.get("prompt")]
        if liked:
            bits.append("Recently loved: " + " | ".join(liked))
        return " — ".join(bits)[:900]

    def summary(self) -> str:
        prof = self.profile()
        sess = self.active_session() or {}
        lt = self.longterm()
        kept = "kept" if sess.get("kept") else "open"
        return (
            f"{prof.get('name') or 'Profile'} · "
            f"{sess.get('title') or 'no session'} ({kept}) · "
            f"{int(lt.get('uses', 0))} memories"
        )
