"""Forge — a small local companion I wrote for SpriteForge. No cloud model.

It talks, looks at files you upload, and evolves from daily use + memory.
"""
from __future__ import annotations

import json
import random
import re
import time
from pathlib import Path

from .filesight import inspect_any
from .lexicon import PHRASES, dictionary_size, fluidize
from .memory import MemoryStore, _now, _read, _write, extract_phrases

NAME_PAT = re.compile(r"\b(?:i am|i'm|im|my name is|call me)\s+([a-z][a-z0-9_\- ]{1,32})\b", re.I)
REMEMBER_PAT = re.compile(r"\b(?:remember|don't forget|dont forget|note that)\s+(.+)$", re.I)
FORGET_PAT = re.compile(r"\b(?:forget|unpin)\s+(.+)$", re.I)


def _day() -> str:
    return time.strftime("%Y-%m-%d")


class Forge:
    """Tiny handmade studio AI. Lives in the active profile folder."""

    def __init__(self, mind: MemoryStore) -> None:
        self.mind = mind

    def _path(self) -> Path:
        return self.mind.root() / "forge.json"

    def _log_path(self) -> Path:
        return self.mind.root() / "forge_chat.jsonl"

    def state(self) -> dict:
        data = _read(
            self._path(),
            {
                "name": "Forge",
                "born": _now(),
                "talks": 0,
                "days": {},
                "user_name": "",
                "echo": [],
                "seen": [],
                "last_day": "",
            },
        )
        return data

    def _save(self, data: dict) -> None:
        _write(self._path(), data)

    def history(self, limit: int = 24) -> list[dict]:
        path = self._log_path()
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    def _log(self, role: str, text: str, extra: dict | None = None) -> None:
        row = {"when": _now(), "role": role, "text": text[:2000]}
        if extra:
            row.update(extra)
        with self._log_path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def look(self, paths: list[Path]) -> list[dict]:
        seen = []
        st = self.state()
        bag = st.setdefault("seen", [])
        for p in paths:
            try:
                info = inspect_any(Path(p))
            except Exception as exc:  # noqa: BLE001
                info = {"kind": "error", "name": Path(p).name, "summary": f"Could not read {Path(p).name}: {exc}"}
            seen.append(info)
            bag.insert(0, {"when": _now(), "name": info.get("name"), "summary": info.get("summary", "")[:240]})
            self.mind.note("file", info.get("summary", Path(p).name), weight=1.2, path=str(p))
        st["seen"] = bag[:40]
        self._save(st)
        return seen

    def reply(self, text: str, files: list[Path] | None = None) -> str:
        raw = (text or "").strip()
        files = [Path(p) for p in (files or []) if Path(p).exists()]
        seen = self.look(files) if files else []
        st = self.state()
        st["talks"] = int(st.get("talks", 0)) + 1
        today = _day()
        days = st.setdefault("days", {})
        days[today] = int(days.get(today, 0)) + 1
        first_today = st.get("last_day") != today
        st["last_day"] = today
        nm = NAME_PAT.search(raw)
        if nm:
            st["user_name"] = nm.group(1).strip().title()
            self.mind.set_user_name(st["user_name"])
        for phrase in extract_phrases(raw):
            echo = st.setdefault("echo", [])
            if phrase not in echo:
                echo.insert(0, phrase)
            st["echo"] = echo[:40]
        self._save(st)
        self._log("user", raw, {"files": [p.name for p in files]})
        if raw:
            self.mind.deposit(raw, kind="chat", locked=True)
        for info in seen:
            self.mind.deposit(info.get("summary") or info.get("name") or "file", kind="file", locked=True, path=info.get("path") or "")

        cleaned, _notes = fluidize(raw, expand=True)
        low = raw.lower()
        lt = self.mind.longterm()
        who = lt.get("user_name") or st.get("user_name") or self.mind.profile().get("name") or "friend"
        age = st["talks"]
        streak = len(days)
        mem = self.mind.steer(raw)
        facts = lt.get("facts") or []
        pins = lt.get("pins") or []
        bank = self.mind.recall(raw, limit=10)

        out = self._compose(
            raw=raw,
            cleaned=cleaned,
            low=low,
            who=who,
            age=age,
            streak=streak,
            first_today=first_today,
            today_n=days[today],
            mem=mem,
            facts=facts,
            pins=pins,
            seen=seen,
            echo=st.get("echo") or [],
            bank=bank,
        )
        asking = bool(re.search(r"\b(what do you remember|do you remember|what do you know)\b", low))
        rem = None if asking else REMEMBER_PAT.search(raw)
        if rem:
            self.mind.pin(rem.group(1).strip().rstrip("."))
            out += "\n\nLocked into the memory bank. I will not drop it."
        forget = FORGET_PAT.search(raw)
        if forget:
            self.mind.unpin(forget.group(1).strip().rstrip("."))
            out += "\n\nRemoved that unlocked pin. Locked bank rows stay."

        if raw:
            self.mind.note("chat", raw[:400], weight=1.5)
        self._log("forge", out)
        return out

    def _compose(self, **k) -> str:
        low = k["low"]
        seen = k["seen"]
        if seen and any(w in low for w in ("see", "look", "watch", "open", "inside", "what is", "what's in", "inspire", "inspired")):
            return self._see(k)
        if seen and not low:
            return self._see(k)
        if any(w in low for w in ("inspire", "prompt", "idea for", "what should i")):
            return self._inspire(k)
        if any(w in low for w in ("who are you", "what are you", "are you ai", "are you gpt")):
            return self._who(k)
        if any(w in low for w in ("hello", "hi ", "hey", "yo ", "good morning", "good night", "sup")) or low in {"hi", "hey", "yo"}:
            return self._greet(k)
        if any(w in low for w in ("how are you", "how r u", "how's it")):
            return f"I'm well, {k['who']}. {k['age']} talks in, {k['streak']} days of us. Still local, still yours."
        if any(w in low for w in ("thank", "thanks", "thx")):
            return random.choice(
                [
                    "Anytime.",
                    "That's what I'm for.",
                    f"Glad it landed, {k['who']}.",
                ]
            )
        if any(w in low for w in ("what do you know", "what do you remember", "about me", "my taste", "memory")):
            return self._about(k)
        if any(w in low for w in ("help", "how do i", "what can you", "commands")):
            return self._help()
        if any(w in low for w in ("360", "480", "720", "1080", "4k", "upscale")):
            return (
                "On Imagine, set Output size to 360p, 480p, 720p, 1080p, or 4K. "
                "Then Upscale image, or make / upscale a video at that height."
            )
        if seen:
            return self._see(k) + "\n\n" + self._inspire(k)
        return self._talk(k)

    def _who(self, k: dict) -> str:
        return (
            f"I'm Forge — a small local mind written for SpriteForge, not a rented cloud model. "
            f"{dictionary_size()} studio phrases, and I write everything into your Hermes memory bank. "
            f"Born {self.state().get('born', 'recently')}. {k['age']} talks so far. "
            f"Chat, files, names, and picks stay locked. I do not forget them. Nothing leaves this PC."
        )

    def _greet(self, k: dict) -> str:
        bit = ""
        if k["first_today"]:
            bit = f" First hello of { _day() }. That's day {k['streak']} with you."
        facts = k["facts"][:1]
        tail = f" Lately: {facts[0]}." if facts else ""
        return f"Hey {k['who']}.{bit}{tail} Load a picture or a zip if you want me to look."

    def _about(self, k: dict) -> str:
        lines = [f"Memory bank for {k['who']} — I do not forget locked rows:"]
        if k["facts"]:
            lines += [f"• {f}" for f in k["facts"][:6]]
        if k["pins"]:
            lines.append("Pinned: " + "; ".join(k["pins"][:8]))
        bank = k.get("bank") or self.mind.recall(limit=8)
        if bank:
            lines.append("Bank:")
            for row in bank[:8]:
                lock = "🔒 " if row.get("locked") else ""
                lines.append(f"  {lock}[{row.get('kind','')}] {(row.get('text') or '')[:140]}")
        if k["echo"]:
            lines.append("Words you keep using: " + ", ".join(k["echo"][:8]))
        seen = self.state().get("seen") or []
        if seen:
            lines.append("Last file I saw: " + (seen[0].get("summary") or seen[0].get("name") or ""))
        if not k["facts"] and not bank:
            lines.append("• Bank is empty — talk, upload, generate. I keep it.")
        return "\n".join(lines)

    def _help(self) -> str:
        return (
            "Talk normally. I live here, and I write into the Memory bank.\n"
            "• Upload jpg / png / webp / zip / rar — I look, then lock what I saw.\n"
            "• Say “remember never put a person in skies.” That is locked.\n"
            "• “What do you remember?” reads the whole bank.\n"
            "• “Inspire me” uses bank + files.\n"
            "• Imagine is steered by the same bank. Sessions can be deleted; locked rows stay."
        )

    def _see(self, k: dict) -> str:
        seen = k["seen"]
        if not seen:
            last = (self.state().get("seen") or [None])[0]
            if last:
                return f"Last thing I looked at: {last.get('summary')}"
            return "Drop a jpg, png, zip, or rar and I’ll look."
        bits = ["I looked:"]
        for info in seen:
            bits.append("• " + info.get("summary", info.get("name", "file")))
            if info.get("kind") == "archive":
                names = info.get("files") or []
                if names:
                    bits.append("  inside: " + ", ".join(names[:12]))
        return "\n".join(bits)

    def _inspire(self, k: dict) -> str:
        colors = []
        moods = []
        for info in k["seen"]:
            if info.get("kind") == "image":
                colors.extend(info.get("palette") or [])
                moods.append(info.get("mood", ""))
            for im in info.get("images") or []:
                colors.extend(im.get("palette") or [])
                moods.append(im.get("mood", ""))
        taste = (k["facts"][:2] + k["echo"][:3])
        phrase_pool = list(PHRASES.keys())[:20]
        extra = random.sample(phrase_pool, k=min(3, len(phrase_pool)))
        idea = ", ".join(
            [
                k["cleaned"] or "same world, new still",
                *([m for m in moods if m][:2]),
                *taste[:2],
                *extra,
            ]
        )
        if colors:
            idea += f". Honor these colors: {', '.join(colors[:4])}"
        return (
            "From what I see and what you’ve taught me, try this on Imagine:\n\n"
            f"{idea}\n\n"
            "Load the same file there if you want Flux to paint from it."
        )

    def _talk(self, k: dict) -> str:
        cleaned = k["cleaned"] or k["raw"]
        bits = [
            f"{k['who']}, I hear: {cleaned[:220]}",
        ]
        if k["first_today"]:
            bits.append(f"New day. I’ve grown through {k['streak']} days of this.")
        bank = k.get("bank") or []
        if bank:
            bits.append("I still have: " + " | ".join((r.get("text") or "")[:90] for r in bank[:3]))
        elif k["facts"]:
            bits.append("That sits next to: " + k["facts"][0])
        if k["echo"]:
            overlap = [e for e in k["echo"] if e in cleaned.lower()]
            if overlap:
                bits.append("You’ve circled “" + overlap[0] + "” before. It’s in the bank.")
        bits.append("Logged in the memory bank. I keep it unless you unlock and forget it.")
        bits.append(
            random.choice(
                [
                    "Want me to turn that into an Imagine prompt, or look at a file?",
                    "Say inspire, or upload a pack, or tell me to remember something.",
                    "Ask what I remember if you want the whole bank.",
                ]
            )
        )
        return "\n".join(bits)
