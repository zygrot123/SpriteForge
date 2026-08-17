"""Shared studio tray — any tab can hold an image and pass it to another tab."""
from __future__ import annotations

from pathlib import Path

# Structures → floor-plan slot
STRUCTURE_SLOT = {
    "tile": "floor",
    "dungeon": "hall",
    "building": "solid",
    "gate": "door",
    "pillar": "solid",
    "furniture": "grave",
    "vegetation": "terrace",
    "prop": "floor",
}

# Scenes → floor-plan slot
SCENE_SLOT = {
    "floor": "floor",
    "wall": "solid",
    "water": "water",
    "interior": "floor",
    "sky": "backdrop",
    "backdrop": "backdrop",
    "clouds": "backdrop",
}

SLOTS = (
    "floor", "hall", "corner", "tee", "cross", "dead", "solid",
    "door", "water", "shore", "cave", "mouth", "stair", "grave", "terrace",
    "backdrop",
)


def suggest_slot(kind: str) -> str:
    kind = (kind or "").replace("scene_", "")
    return STRUCTURE_SLOT.get(kind) or SCENE_SLOT.get(kind) or "floor"


def as_path(value) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.exists() else None
