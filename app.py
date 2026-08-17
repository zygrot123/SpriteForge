from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spriteforge.paths import LOG_PATH, ensure_dirs, is_frozen  # noqa: E402


def _hook_logs() -> None:
    ensure_dirs()
    if not is_frozen() and sys.stderr is not None:
        return
    fh = open(LOG_PATH, "a", encoding="utf-8")
    sys.stdout = fh
    sys.stderr = fh


def main() -> None:
    _hook_logs()
    ensure_dirs()
    try:
        from spriteforge.bootstrap import setup_needed
        from spriteforge.config import load_config
        from spriteforge.ui.setup import run_setup
        from spriteforge.ui.window import run

        if setup_needed(load_config()):
            run_setup()
        run()
    except Exception:
        traceback.print_exc()
        if is_frozen():
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(
                    0,
                    f"SpriteForge crashed. See log:\n{LOG_PATH}",
                    "SpriteForge",
                    0x10,
                )
            except Exception:
                pass
        raise


if __name__ == "__main__":
    main()
