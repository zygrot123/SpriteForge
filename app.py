from __future__ import annotations

import sys
import traceback
from pathlib import Path


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _exe_dir() -> Path:
    if _frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _alert(msg: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, msg, "SpriteForge", 0x10)
    except Exception:
        print(msg)


def _preflight() -> bool:
    if not _frozen():
        return True
    here = _exe_dir()
    internal = here / "_internal"
    if internal.is_dir():
        return True
    _alert(
        "SpriteForge cannot start because the _internal folder is missing.\n\n"
        "Do not run the .exe from inside the ZIP, and do not copy only SpriteForge.exe.\n\n"
        "1. Extract the FULL SpriteForge-Windows.zip to a folder\n"
        "   (Desktop or Documents is fine).\n"
        "2. Open that folder. You must see:\n"
        "      SpriteForge.exe\n"
        "      _internal\n"
        "3. Double-click SpriteForge.exe there.\n\n"
        f"This copy is in:\n{here}"
    )
    return False


def _write_crash(text: str) -> Path | None:
    try:
        from spriteforge.paths import LOG_PATH, ensure_dirs

        ensure_dirs()
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(text)
            if not text.endswith("\n"):
                fh.write("\n")
            fh.flush()
        return LOG_PATH
    except Exception:
        fallback = _exe_dir() / "spriteforge-crash.txt"
        try:
            fallback.write_text(text, encoding="utf-8")
            return fallback
        except Exception:
            return None


def main() -> None:
    if not _preflight():
        return
    root = _exe_dir()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from spriteforge.paths import LOG_PATH, ensure_dirs, is_frozen

        ensure_dirs()
        if is_frozen() or sys.stderr is None:
            fh = open(LOG_PATH, "a", encoding="utf-8")
            sys.stdout = fh
            sys.stderr = fh
        from spriteforge.bootstrap import setup_needed
        from spriteforge.config import load_config
        from spriteforge.ui.setup import run_setup
        from spriteforge.ui.window import run

        if setup_needed(load_config()):
            run_setup()
        run()
    except Exception:
        tb = traceback.format_exc()
        log = _write_crash(tb)
        extra = f"\n\nLog:\n{log}" if log else ""
        _alert("SpriteForge crashed." + extra)
        raise


if __name__ == "__main__":
    main()
