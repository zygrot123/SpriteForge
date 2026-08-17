from __future__ import annotations

import json
import uuid
from pathlib import Path

from PIL import Image

from ..paths import ANIMS, ensure_dirs
from .assets import slugify, now_stamp
from .prompts import ANIMATIONS as BUILTIN

HEIGHT_LOCK = (
    "same character height as the reference image, same scale, same camera distance, "
    "do not grow, do not shrink, do not zoom, do not crop the head or feet"
)

GROUND_LOCK = (
    "feet stay on the same ground line as the reference, in-place motion, no sliding away"
)

SOLO_LOCK = (
    "exactly ONE character only, no second body, no overlapping figures, "
    "no ghost copy, no double exposure, no motion-smear duplicate, no extra silhouette"
)

DIR_SETS = {
    "this": None,
    "4-dir (down left up right)": [
        ("down", "front", "front", "facing the camera, moving toward the camera if the action travels"),
        ("left", "side", "side", "strict LEFT profile, facing left, motion to the left, nose points left"),
        ("up", "back", "back", "true BACK view, facing away, moving away if the action travels"),
        ("right", "side", "side", "strict RIGHT profile, facing right, motion to the right, nose points right"),
    ],
    "8-dir": [
        ("down", "front", "front", "facing the camera"),
        ("down_left", "three_quarter", "front", "three-quarter facing down-left"),
        ("left", "side", "side", "strict LEFT profile, facing left"),
        ("up_left", "three_quarter", "back", "three-quarter back facing up-left"),
        ("up", "back", "back", "true BACK view, facing away"),
        ("up_right", "three_quarter", "back", "three-quarter back facing up-right"),
        ("right", "side", "side", "strict RIGHT profile, facing right"),
        ("down_right", "three_quarter", "front", "three-quarter facing down-right"),
    ],
    "Isometric 4-dir": [
        ("iso_down", "iso_down", "front", "same Hades camera, faces down-toward the player"),
        ("iso_left", "iso_left", "side", "same Hades camera, faces left on the diamond"),
        ("iso_up", "iso_up", "back", "same Hades camera, faces away-up"),
        ("iso_right", "iso_right", "side", "same Hades camera, faces right on the diamond"),
    ],
    "Hades 8-dir": [
        ("iso_down", "iso_down", "front", "Hades camera locked, faces toward the player"),
        ("iso_down_left", "iso_down_left", "front", "Hades camera locked, faces down-left"),
        ("iso_left", "iso_left", "side", "Hades camera locked, faces left"),
        ("iso_up_left", "iso_up_left", "back", "Hades camera locked, faces up-left"),
        ("iso_up", "iso_up", "back", "Hades camera locked, faces away"),
        ("iso_up_right", "iso_up_right", "back", "Hades camera locked, faces up-right"),
        ("iso_right", "iso_right", "side", "Hades camera locked, faces right"),
        ("iso_down_right", "iso_down_right", "front", "Hades camera locked, faces down-right"),
    ],
    "2-dir (left right)": [
        ("left", "side", "side", "strict LEFT profile, facing left, side-scroller, nose to the left"),
        ("right", "side", "side", "strict RIGHT profile, facing right, side-scroller, nose to the right"),
    ],
    "2.5D side (left right up down)": [
        ("right", "side_25d", "side", "2.5D facing right, slight depth, platformer"),
        ("left", "side_25d", "side", "2.5D facing left, slight depth, platformer"),
        ("up", "back", "back", "2.5D going up / away, same character height"),
        ("down", "front", "front", "2.5D coming down / toward camera, same height"),
    ],
    "Top-down 4-dir": [
        ("down", "top", "front", "top-down facing down / toward bottom of screen"),
        ("left", "top", "side", "top-down facing left"),
        ("up", "top", "back", "top-down facing up / top of screen"),
        ("right", "top", "side", "top-down facing right"),
    ],
    "Top-down 8-dir": [
        ("down", "top", "front", "top-down facing down"),
        ("down_left", "top", "front", "top-down facing down-left"),
        ("left", "top", "side", "top-down facing left"),
        ("up_left", "top", "back", "top-down facing up-left"),
        ("up", "top", "back", "top-down facing up"),
        ("up_right", "top", "back", "top-down facing up-right"),
        ("right", "top", "side", "top-down facing right"),
        ("down_right", "top", "front", "top-down facing down-right"),
    ],
    "Bottom-up 4-dir": [
        ("down", "bottom", "front", "worm's-eye facing camera"),
        ("left", "bottom", "side", "worm's-eye facing left"),
        ("up", "bottom", "back", "worm's-eye facing away"),
        ("right", "bottom", "side", "worm's-eye facing right"),
    ],
}

PRESENTATIONS = {
    "2d_side": {
        "label": "2D side-scroller",
        "view": "side",
        "dirs": "2-dir (left right)",
        "style": None,
        "lock": (
            "classic 2D side-scrolling platformer sprite, strict side profile, "
            "orthographic, no perspective, no 3D camera tilt"
        ),
        "video": "locked side-scrolling camera, character animates in place, no camera move",
    },
    "side_25d": {
        "label": "2.5D side-scroller",
        "view": "side_25d",
        "dirs": "2.5D side (left right up down)",
        "style": None,
        "lock": (
            "2.5D side-scroller game sprite, mostly side-on with slight depth and volume, "
            "cel-shaded form, still a platformer not a full 3D scene"
        ),
        "video": "2.5D side-scroller camera, slight depth, character moves in place",
    },
    "hades": {
        "label": "Hades / isometric",
        "view": "isometric",
        "dirs": "Hades 8-dir",
        "style": "abyssal_iso",
        "lock": (
            "Supergiant Hades action-RPG sprite: the CAMERA STAYS FIXED in 2:1 isometric "
            "(30 degrees down, 45 yaw). The character rotates on the diamond floor. "
            "Painterly brush, warm rim vs cool underworld fill, gold and ember, "
            "compact fighter silhouette, one hero only, no arena, no other people"
        ),
        "video": (
            "Hades dungeon camera locked isometric, no orbit, no zoom, "
            "character performs the motion in place on the diamond floor"
        ),
    },
    "topdown": {
        "label": "Top-down",
        "view": "top",
        "dirs": "Top-down 4-dir",
        "style": None,
        "lock": (
            "top-down twin-stick game sprite, orthographic from above, "
            "head and shoulders readable, no horizon"
        ),
        "video": "top-down camera locked above the character, in-place motion",
    },
    "bottom": {
        "label": "Bottom-up / worm's eye",
        "view": "bottom",
        "dirs": "Bottom-up 4-dir",
        "style": None,
        "lock": (
            "worm's-eye game sprite, camera below looking up, feet closer, "
            "heroic tall silhouette, still isolated"
        ),
        "video": "low camera looking up at the character, locked, in-place motion",
    },
    "look3d": {
        "label": "3D-look sprite (fake 3D)",
        "view": "three_quarter",
        "dirs": "4-dir (down left up right)",
        "style": None,
        "lock": (
            "dimensional 3D-looking 2D game sprite, sculpted volumes, rim light, "
            "readable form, still a flat isolated sprite not a 3D scene render"
        ),
        "video": "orbit-feel but camera locked, 3D-looking sprite animates in place",
    },
}


def presentation_labels() -> list[str]:
    return [v["label"] for v in PRESENTATIONS.values()]


def presentation_by_label(label: str) -> tuple[str, dict]:
    for k, v in PRESENTATIONS.items():
        if v["label"] == label:
            return k, v
    return "hades", PRESENTATIONS["hades"]

EXTRAS: dict = {
    "crouch": {
        "label": "Crouch",
        "category": "locomotion",
        "loop": True,
        "grounded": True,
        "default_frames": 4,
        "hint": "duck down, same height scale, feet planted",
        "frames": [
            "standing, begins to bend the knees",
            "half crouch, back straight, weapon ready",
            "full crouch, lowest stance, head still the same size",
            "eases back toward a ready crouch so it can loop",
        ],
    },
    "block": {
        "label": "Block / guard",
        "category": "combat",
        "loop": False,
        "grounded": True,
        "default_frames": 4,
        "hint": "raise guard then hold",
        "frames": [
            "starts raising the shield or weapon to guard",
            "guard almost closed, weight forward",
            "full block pose, solid, same scale",
            "holds the guard, tiny settle",
        ],
    },
    "parry": {
        "label": "Parry",
        "category": "combat",
        "loop": False,
        "grounded": True,
        "default_frames": 5,
        "hint": "deflect then recover",
        "frames": [
            "anticipation, weapon angled to catch a blow",
            "contact, weapon knocks the hit aside",
            "spark of the parry, body twisted",
            "follow through of the deflect",
            "back to guard",
        ],
    },
    "slash": {
        "label": "Slash",
        "category": "combat",
        "loop": False,
        "grounded": True,
        "default_frames": 6,
        "hint": "horizontal cut",
        "frames": [
            "wind-up, blade pulled to the rear hip",
            "step in, hips start to turn",
            "blade crossing in front at full speed",
            "cut completes, torso twisted",
            "blade swings past",
            "recovers to combat idle, same height",
        ],
    },
    "thrust": {
        "label": "Thrust / stab",
        "category": "combat",
        "loop": False,
        "grounded": True,
        "default_frames": 5,
        "hint": "linear stab",
        "frames": [
            "coils, point aimed forward",
            "lunges, back leg pushing",
            "full extension, point farthest forward",
            "recoil the arm",
            "steps back to guard",
        ],
    },
    "spin_slash": {
        "label": "Spin slash",
        "category": "abilities",
        "loop": False,
        "grounded": True,
        "default_frames": 6,
        "hint": "360 cut, in place",
        "frames": [
            "coils into the spin",
            "quarter turn, blade out",
            "back view mid-spin, same character",
            "three-quarter out of the spin",
            "blade finishing the circle",
            "plants and recovers",
        ],
    },
    "slam": {
        "label": "Ground slam",
        "category": "abilities",
        "loop": False,
        "grounded": True,
        "default_frames": 6,
        "hint": "raise weapon and smash down",
        "frames": [
            "weapon rises overhead, knees bend",
            "peak overhead, body stretched up but same scale",
            "starts the downward smash",
            "impact, weapon hits the implied ground, shock in the arms",
            "dustless follow-through, no extra scenery",
            "lifts the weapon back to ready",
        ],
    },
    "uppercut": {
        "label": "Uppercut",
        "category": "combat",
        "loop": False,
        "grounded": True,
        "default_frames": 5,
        "hint": "rising strike",
        "frames": [
            "drops the shoulder, fist or blade low",
            "drives upward",
            "peak of the uppercut",
            "overshoot",
            "lands back on both feet, same height",
        ],
    },
    "kick": {
        "label": "Kick",
        "category": "combat",
        "loop": False,
        "grounded": True,
        "default_frames": 5,
        "hint": "one standing kick",
        "frames": [
            "chamber the kicking leg",
            "leg extending",
            "full kick, standing leg planted",
            "retract",
            "both feet down, idle",
        ],
    },
    "shoot": {
        "label": "Shoot / fire",
        "category": "abilities",
        "loop": False,
        "grounded": True,
        "default_frames": 5,
        "hint": "aim and release a projectile from the hands or weapon",
        "frames": [
            "raises the weapon or hands to aim",
            "aimed, still, same height",
            "fires, tiny recoil, energy leaving the weapon only",
            "recoil settle",
            "lowers back to ready",
        ],
    },
    "aim": {
        "label": "Aim hold",
        "category": "combat",
        "loop": True,
        "grounded": True,
        "default_frames": 4,
        "hint": "held aim pose, tiny breathe",
        "frames": [
            "aimed stance",
            "tiny inhale, weapon still aimed",
            "hold",
            "back to first aim pose",
        ],
    },
    "cast_burst": {
        "label": "Ability: burst cast",
        "category": "abilities",
        "loop": False,
        "grounded": True,
        "default_frames": 6,
        "hint": "gather then explode a spell from the body",
        "frames": [
            "hands gather at the chest",
            "energy builds, knees bent",
            "burst peak, arms thrown out, light only on the character",
            "shock of the release",
            "smoke-less recover",
            "combat idle",
        ],
    },
    "beam": {
        "label": "Ability: beam",
        "category": "abilities",
        "loop": False,
        "grounded": True,
        "default_frames": 6,
        "hint": "channel a beam from the hands or weapon",
        "frames": [
            "plants feet, aims both hands or the weapon forward",
            "charge glows at the source only",
            "beam fires forward, character leaning into it",
            "holds the beam",
            "cuts the beam, recoil",
            "lowers arms to idle",
        ],
    },
    "heal": {
        "label": "Ability: heal",
        "category": "abilities",
        "loop": False,
        "grounded": True,
        "default_frames": 5,
        "hint": "gentle restore, no scenery",
        "frames": [
            "bows the head, hands cup near the chest",
            "soft light in the palms only",
            "light peaks, character still the same size",
            "light fades",
            "stands ready",
        ],
    },
    "buff": {
        "label": "Ability: buff / aura",
        "category": "abilities",
        "loop": False,
        "grounded": True,
        "default_frames": 5,
        "hint": "aura around THIS character only",
        "frames": [
            "spreads the arms",
            "aura starts at the feet",
            "aura around the silhouette, no extra creatures",
            "aura settles",
            "combat ready with a faint leftover glow",
        ],
    },
    "summon": {
        "label": "Ability: summon",
        "category": "abilities",
        "loop": False,
        "grounded": True,
        "default_frames": 6,
        "hint": "cast a summon — keep only THIS character in frame",
        "frames": [
            "raises one hand, chanting pose",
            "circle glow at the feet of THIS character only",
            "peak of the cast, still a solo sprite",
            "releases",
            "watches the implied summon, still alone in frame",
            "idle",
        ],
    },
    "teleport_out": {
        "label": "Ability: teleport out",
        "category": "abilities",
        "loop": False,
        "grounded": True,
        "default_frames": 5,
        "hint": "character dissolves in place",
        "frames": [
            "braces",
            "body starts to break into particles, same pose",
            "mostly dissolved, silhouette still readable",
            "last scraps of the silhouette",
            "empty pose leftover then vanish — still isolated",
        ],
    },
    "teleport_in": {
        "label": "Ability: teleport in",
        "category": "abilities",
        "loop": False,
        "grounded": True,
        "default_frames": 5,
        "hint": "character reforms in place",
        "frames": [
            "particles gathering in a standing shape",
            "ghost of the body",
            "body half solid",
            "fully solid, landing the pose",
            "combat idle",
        ],
    },
    "transform": {
        "label": "Ability: transform",
        "category": "abilities",
        "loop": False,
        "grounded": True,
        "default_frames": 6,
        "hint": "same identity, powered-up state — do not become someone else",
        "frames": [
            "clutches the chest, power rising",
            "arches back, same face and gear",
            "peak flash, still the same character",
            "new energy on the SAME armor",
            "settles in the powered stance",
            "idle in the new state, same height",
        ],
    },
    "dodge_roll": {
        "label": "Dodge roll",
        "category": "locomotion",
        "loop": False,
        "grounded": True,
        "default_frames": 6,
        "hint": "in-place roll, same scale",
        "frames": [
            "drops and starts the roll",
            "tucked mid-roll",
            "upside-down tuck, same character",
            "coming out of the roll",
            "plants a hand",
            "stands back up, same height",
        ],
    },
    "climb": {
        "label": "Climb",
        "category": "locomotion",
        "loop": True,
        "grounded": False,
        "default_frames": 6,
        "hint": "in-place climb cycle",
        "frames": [
            "left hand high, right foot high",
            "pulls up",
            "right hand reaches",
            "left foot pushes",
            "right hand high, left foot high",
            "pulls, ready to loop",
        ],
    },
    "swim": {
        "label": "Swim",
        "category": "locomotion",
        "loop": True,
        "grounded": False,
        "default_frames": 6,
        "hint": "in-place swim, same scale",
        "frames": [
            "streamlined, left arm forward",
            "pull the left arm",
            "right arm forward",
            "kick",
            "left arm forward again",
            "glide, loop",
        ],
    },
    "fly": {
        "label": "Fly / hover",
        "category": "locomotion",
        "loop": True,
        "grounded": False,
        "default_frames": 6,
        "hint": "hovering flap or float, same size",
        "frames": [
            "hover, limbs slightly down",
            "rises a few pixels, same scale",
            "peak hover",
            "eases down",
            "lowest hover",
            "back to first hover",
        ],
    },
    "land": {
        "label": "Land",
        "category": "locomotion",
        "loop": False,
        "grounded": True,
        "default_frames": 4,
        "hint": "from air to plant",
        "frames": [
            "descending, legs reaching down",
            "contact, knees compress",
            "absorb the landing",
            "stands, same height as idle",
        ],
    },
    "pickup": {
        "label": "Pick up",
        "category": "states",
        "loop": False,
        "grounded": True,
        "default_frames": 5,
        "hint": "bend, grab, stand",
        "frames": [
            "looks down",
            "bends at the hips, same scale",
            "hand closes on an implied object",
            "lifts",
            "stands holding it",
        ],
    },
    "throw": {
        "label": "Throw",
        "category": "combat",
        "loop": False,
        "grounded": True,
        "default_frames": 5,
        "hint": "hurl then recover",
        "frames": [
            "winds the throwing arm back",
            "steps in",
            "release, arm forward",
            "follow through",
            "idle",
        ],
    },
    "taunt": {
        "label": "Taunt",
        "category": "states",
        "loop": False,
        "grounded": True,
        "default_frames": 5,
        "hint": "cocky gesture, same person",
        "frames": [
            "shifts weight",
            "gesture starts",
            "peak taunt pose",
            "holds it",
            "back to idle",
        ],
    },
    "victory": {
        "label": "Victory",
        "category": "states",
        "loop": False,
        "grounded": True,
        "default_frames": 5,
        "hint": "win pose",
        "frames": [
            "relaxes from combat",
            "raises a weapon or fist",
            "peak victory",
            "holds",
            "settles proud idle",
        ],
    },
    "stunned": {
        "label": "Stunned",
        "category": "states",
        "loop": True,
        "grounded": True,
        "default_frames": 4,
        "hint": "dazed wobble, same height",
        "frames": [
            "off balance left",
            "head lolls",
            "off balance right",
            "back toward first wobble",
        ],
    },
    "sleep": {
        "label": "Sleep",
        "category": "states",
        "loop": True,
        "grounded": True,
        "default_frames": 4,
        "hint": "asleep, tiny breathe",
        "frames": [
            "sleeping pose",
            "tiny inhale",
            "exhale",
            "back to sleep pose",
        ],
    },
    "kneel": {
        "label": "Kneel / pray",
        "category": "states",
        "loop": False,
        "grounded": True,
        "default_frames": 4,
        "hint": "down to one knee",
        "frames": [
            "begins to kneel",
            "one knee almost down",
            "kneeling, head bowed",
            "holds the kneel",
        ],
    },
    "interact": {
        "label": "Interact / use",
        "category": "states",
        "loop": False,
        "grounded": True,
        "default_frames": 4,
        "hint": "reach and use",
        "frames": [
            "reaches forward",
            "hand on the implied object",
            "uses it",
            "pulls back to idle",
        ],
    },
}

BUILTIN_META = {
    "idle": ("locomotion", True),
    "walk": ("locomotion", True),
    "run": ("locomotion", True),
    "attack": ("combat", True),
    "cast": ("abilities", True),
    "hurt": ("states", True),
    "death": ("states", False),
    "jump": ("locomotion", False),
    "dash": ("locomotion", False),
    "turnaround": ("states", True),
}

CATEGORIES = ["all", "locomotion", "combat", "abilities", "states", "custom"]


def _enrich(key: str, spec: dict) -> dict:
    out = dict(spec)
    out.setdefault("id", key)
    cat, grounded = BUILTIN_META.get(key, (spec.get("category", "combat"), spec.get("grounded", True)))
    out.setdefault("category", cat)
    out.setdefault("grounded", grounded)
    out.setdefault("label", key)
    return out


def load_custom() -> list[dict]:
    ensure_dirs()
    ANIMS.mkdir(parents=True, exist_ok=True)
    cards = []
    for folder in sorted(ANIMS.iterdir()) if ANIMS.exists() else []:
        meta = folder / "anim.json"
        if folder.is_dir() and meta.exists():
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
                data.setdefault("category", "custom")
                data.setdefault("grounded", True)
                data["id"] = data.get("id") or folder.name
                cards.append(data)
            except (json.JSONDecodeError, OSError):
                continue
    return cards


def all_animations() -> dict[str, dict]:
    merged = {}
    for k, spec in BUILTIN.items():
        merged[k] = _enrich(k, spec)
    for k, spec in EXTRAS.items():
        merged[k] = _enrich(k, spec)
    for card in load_custom():
        merged[card["id"]] = card
    return merged


def anim_labels(category: str = "all") -> list[str]:
    items = all_animations()
    labels = []
    for spec in items.values():
        if category != "all" and spec.get("category") != category:
            continue
        labels.append(spec["label"])
    return labels


def anim_by_label(label: str) -> tuple[str, dict]:
    for key, spec in all_animations().items():
        if spec.get("label") == label:
            return key, spec
    items = all_animations()
    return "idle", items["idle"]


def invent_frames(text: str, n: int = 6) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        raw = "a special ability"
    if "\n" in raw:
        lines = [ln.strip(" -•\t") for ln in raw.splitlines() if ln.strip()]
        if len(lines) >= 3:
            return _fit(lines, n)
    if ";" in raw:
        parts = [p.strip() for p in raw.split(";") if p.strip()]
        if len(parts) >= 3:
            return _fit(parts, n)
    action = raw.rstrip(".")
    phases = [
        f"anticipation: coils and prepares to {action}, {HEIGHT_LOCK}, {GROUND_LOCK}",
        f"startup: begins to {action}, same character, same height",
        f"active: peak of {action}, same scale as the reference",
        f"follow-through of {action}",
        f"recover from {action}, balance returning",
        f"returns to combat idle after {action}, {HEIGHT_LOCK}",
    ]
    return _fit(phases, n)


def _fit(frames: list[str], n: int) -> list[str]:
    if len(frames) >= n:
        return frames[:n]
    extra = frames[1:-1] or frames
    out = list(frames)
    i = 0
    while len(out) < n:
        out.insert(len(out) - 1, extra[i % len(extra)])
        i += 1
    return out[:n]


def save_animation(
    name: str,
    frames: list[str],
    *,
    hint: str = "",
    loop: bool = False,
    grounded: bool = True,
    default_frames: int | None = None,
) -> dict:
    ensure_dirs()
    ANIMS.mkdir(parents=True, exist_ok=True)
    slug = slugify(name) or "anim"
    aid = f"{slug}-{uuid.uuid4().hex[:4]}"
    folder = ANIMS / aid
    folder.mkdir(parents=True, exist_ok=True)
    card = {
        "id": aid,
        "name": name.strip() or aid,
        "label": f"{name.strip()} (saved)",
        "hint": hint or name,
        "loop": bool(loop),
        "grounded": bool(grounded),
        "default_frames": int(default_frames or len(frames)),
        "frames": list(frames),
        "category": "custom",
        "created": now_stamp(),
    }
    (folder / "anim.json").write_text(json.dumps(card, indent=2), encoding="utf-8")
    return card


def compose_direction_sheet(dir_frames: dict[str, list[Path]], dest: Path, pad: int = 20) -> Path:
    """One row per direction, one column per frame. Padding so cells never overlap."""
    rows = [k for k, v in dir_frames.items() if v]
    if not rows:
        raise ValueError("No frames")
    cols = max(len(dir_frames[k]) for k in rows)
    images: dict[tuple[int, int], Image.Image] = {}
    cw = ch = 0
    for r, key in enumerate(rows):
        for c, p in enumerate(dir_frames[key]):
            im = Image.open(p).convert("RGBA")
            images[(r, c)] = im
            cw = max(cw, im.width)
            ch = max(ch, im.height)
    cw += pad
    ch += pad
    sheet = Image.new("RGBA", (cols * cw + pad, len(rows) * ch + pad), (0, 0, 0, 0))
    for (r, c), im in images.items():
        cell = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        copy = im.copy()
        maxw, maxh = cw - pad, ch - pad
        if copy.width > maxw or copy.height > maxh:
            copy.thumbnail((maxw, maxh), Image.Resampling.LANCZOS)
        ox = (cw - copy.width) // 2
        oy = (ch - copy.height) // 2
        cell.alpha_composite(copy, (ox, oy))
        sheet.alpha_composite(cell, (pad // 2 + c * cw, pad // 2 + r * ch))
    dest.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dest)
    return dest


def stabilize_frames(paths: list[Path], *, grounded: bool = True, pad: int = 20) -> list[Path]:
    """Force every frame to the first frame's character height and, if grounded, foot line."""
    images: list[Image.Image] = []
    boxes: list[tuple[int, int, int, int] | None] = []
    for p in paths:
        im = Image.open(p).convert("RGBA")
        images.append(im)
        boxes.append(im.split()[-1].getbbox())
    first = next((b for b in boxes if b), None)
    if not first:
        return paths
    target_h = max(8, first[3] - first[1])
    foot_y = first[3]
    cx = (first[0] + first[2]) // 2
    cw, ch = images[0].size
    max_h = max(8, ch - 2 * pad)
    if target_h > max_h:
        target_h = max_h
        foot_y = min(ch - pad, max(pad + target_h, foot_y))
    out_paths: list[Path] = []
    for path, im, box in zip(paths, images, boxes):
        if not box:
            out_paths.append(path)
            continue
        x0, y0, x1, y1 = box
        crop = im.crop((x0, y0, x1, y1))
        h = max(1, y1 - y0)
        scale = target_h / h
        nw = max(1, int(crop.width * scale))
        nh = max(1, int(crop.height * scale))
        if nw > cw - 2 * pad:
            scale2 = (cw - 2 * pad) / nw
            nw = max(1, int(nw * scale2))
            nh = max(1, int(nh * scale2))
        crop = crop.resize((nw, nh), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ox = int(cx - nw // 2)
        oy = int(foot_y - nh) if grounded else int(min(ch - pad, max(pad, y1)) - nh)
        ox = max(pad, min(cw - nw - pad, ox))
        oy = max(pad, min(ch - nh - pad, oy))
        layer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        layer.paste(crop, (ox, oy), crop)
        canvas = Image.alpha_composite(canvas, layer)
        canvas.save(path)
        out_paths.append(path)
    return out_paths
