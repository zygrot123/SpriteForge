from __future__ import annotations

from typing import Iterable

from .brain import Intent, understand

BG_HEX = {
    "green": (
        "#00FF00",
        "flat solid chroma-key lime green #00FF00 background, perfectly even #00FF00 with zero gradient, zero texture, zero floor",
    ),
    "magenta": ("#FF00FF", "flat solid chroma-key magenta #FF00FF background"),
    "cyan": ("#00FFFF", "flat solid chroma-key cyan #00FFFF background"),
    "black": ("#000000", "flat solid pure black #000000 background"),
    "gray": ("#808080", "flat solid mid gray #808080 background"),
}

SPRITE_LOCK = (
    "game sprite asset, isolated single subject only, full body visible and centered, "
    "subject standing on nothing, no ground plane, no cast shadow, no scenery, "
    "no background objects, no text, no watermark, no UI, no frame, no border, "
    "clean readable silhouette, even studio lighting, game-ready 2D production asset"
)

IDENTITY_KEEP = (
    "KEEP THIS EXACT CHARACTER. Same face, same body proportions, same height, "
    "same outfit, same armor, same colors, same materials, same equipment, "
    "same silhouette language, same lighting, same art style. Do not redesign. "
    "Do not add or remove gear. Change ONLY the requested pose or view."
)

STYLES = {
    "abyssal_iso": {
        "label": "Abyssal isometric (Hades-like)",
        "words": (
            "Supergiant Games Hades style, painterly 2D isometric character, "
            "visible brush strokes, high-contrast warm rim light against cool underworld shadow, "
            "saturated dark-fantasy palette, gold bone and ember, crisp readable silhouette, "
            "not photorealistic, not a 3D render, not anime, not pixel art"
        ),
    },
    "pixel_32": {
        "label": "Pixel 32-bit SNES",
        "words": (
            "authentic 32-bit SNES pixel art sprite, limited 16-color cluster, "
            "chunky pixels, no anti-alias, hard outlines, retro game sprite sheet style"
        ),
    },
    "pixel_16": {
        "label": "Pixel 16-bit NES",
        "words": (
            "authentic 16-bit pixel art sprite, very limited palette, chunky pixels, "
            "1px outline, no gradients, no anti-alias, classic NES/SNES sprite"
        ),
    },
    "cel": {
        "label": "Cel-shaded 2D",
        "words": (
            "clean 2D cel-shaded game character, bold ink outline, flat color fills, "
            "two-tone shadows, animated series look, production sprite"
        ),
    },
    "painterly": {
        "label": "Painterly RPG",
        "words": (
            "hand-painted RPG game sprite, oil-paint texture, rich midtones, "
            "readable silhouette, Diablo-like production art, not photoreal"
        ),
    },
    "realistic_dark": {
        "label": "Dark realistic fantasy",
        "words": (
            "hyper-detailed dark fantasy game character, worn metal and cloth, "
            "cinematic rim light, grounded materials, still isolated as a sprite"
        ),
    },
    "anime": {
        "label": "Anime game",
        "words": (
            "anime game sprite, clean line art, cel color, expressive but production-safe, "
            "full body character sheet style"
        ),
    },
    "chibi": {
        "label": "Chibi / cute",
        "words": (
            "chibi game sprite, oversized head, short limbs, cute proportions, "
            "clean cel color, toy-like readability"
        ),
    },
    "lowpoly": {
        "label": "Low-poly 3D look",
        "words": (
            "low-poly game character render, faceted geometry, simple materials, "
            "orthographic-friendly, isolated sprite"
        ),
    },
}

VIEWS = {
    "side": "strict side profile, orthographic, nose chest and toes point to the frame edge, platformer view",
    "front": "front view, character facing camera, orthographic, feet planted, turnaround sheet pose",
    "back": "true back view, character facing away, orthographic, turnaround sheet pose",
    "three_quarter": "three-quarter view, 30 degrees off front, both eyes visible, game character select pose",
    "isometric": (
        "Hades isometric camera locked: 2:1 projection, 30 degrees down, 45 degrees yaw, "
        "character stands on the diamond floor grid, camera never tilts"
    ),
    "iso_down": "same Hades isometric camera, character faces toward the camera-down corner of the diamond",
    "iso_up": "same Hades isometric camera, character faces the far-up corner, back three-quarter",
    "iso_left": "same Hades isometric camera, character faces the left diamond edge",
    "iso_right": "same Hades isometric camera, character faces the right diamond edge",
    "iso_down_left": "same Hades isometric camera, character faces down-left on the diamond",
    "iso_down_right": "same Hades isometric camera, character faces down-right on the diamond",
    "iso_up_left": "same Hades isometric camera, character faces up-left, back three-quarter",
    "iso_up_right": "same Hades isometric camera, character faces up-right, back three-quarter",
    "top": "top-down orthographic game view, head and shoulders readable, twin-stick presentation",
    "bottom": "worm's-eye view, camera below looking up, feet closer, heroic tall silhouette",
    "side_25d": "2.5D side-scroller view, mostly side-on with slight three-quarter depth, volumetric, still a platformer camera",
}

LOCK_STRENGTH = {
    "exact": {"denoise": 0.32, "label": "Exact (tiny change)"},
    "tight": {"denoise": 0.42, "label": "Tight (keep face/gear)"},
    "medium": {"denoise": 0.52, "label": "Medium pose"},
    "loose": {"denoise": 0.64, "label": "Loose (new pose)"},
}

ANIMATIONS = {
    "idle": {
        "label": "Idle breathe",
        "loop": True,
        "default_frames": 6,
        "hint": "subtle weight shift and chest breathe, feet planted, no travel",
        "frames": [
            "neutral rest pose, weight even on both feet, arms relaxed",
            "tiny inhale, chest rises a few millimeters, shoulders lift slightly",
            "peak inhale, head a hair taller, idle blink-ready",
            "exhale begins, shoulders ease down",
            "weight eases to the back foot a few millimeters",
            "settles back toward the first rest pose so the cycle loops",
        ],
    },
    "walk": {
        "label": "Walk cycle",
        "loop": True,
        "default_frames": 8,
        "hint": "in-place walk, alternating gait, camera locked, no sliding",
        "frames": [
            "contact: left heel down, right toe pushing, opposite arm forward",
            "down: both feet closer, knees flexed, lowest body height",
            "passing: right leg swings past, left planted, torso upright",
            "up: right heel reaching forward, body at highest point",
            "contact: right heel down, left toe pushing, arms swapped",
            "down: both feet closer, knees flexed, lowest body height",
            "passing: left leg swings past, right planted",
            "up: left heel reaching forward, ready to loop into first contact",
        ],
    },
    "run": {
        "label": "Run cycle",
        "loop": True,
        "default_frames": 8,
        "hint": "in-place run, bigger stride, camera locked",
        "frames": [
            "left contact, long stride, forward lean, opposite arm thrown",
            "left push, right knee driving up, body stretching",
            "airborne, both feet off implied ground, compact",
            "right reaching, preparing contact",
            "right contact, long stride, arms swapped",
            "right push, left knee driving up",
            "airborne again, mirrored",
            "left reaching, ready to loop",
        ],
    },
    "attack": {
        "label": "Melee attack",
        "loop": False,
        "default_frames": 6,
        "hint": "anticipation, strike, follow-through, recover",
        "frames": [
            "anticipation: weapon pulled back, weight on rear foot, coiled",
            "step-in: front foot plants, hips start to rotate",
            "strike: weapon at full extension, impact pose, weight forward",
            "follow-through: weapon overshoots, torso twists past the hit",
            "recover: weapon circling back, balance returning",
            "guard return: settled combat ready, close to idle so it can blend",
        ],
    },
    "cast": {
        "label": "Cast / spell",
        "loop": False,
        "default_frames": 6,
        "hint": "gather energy, release, recover",
        "frames": [
            "hands gather at the chest, head slightly down, charging",
            "energy collects in the palms, knees bent, focus",
            "arms rise, spell peak, light at the hands only — no extra scenery",
            "release: arms thrust forward or upward, energy leaving the hands",
            "recoil: shoulders drop, residual glow fading",
            "return to combat idle",
        ],
    },
    "hurt": {
        "label": "Hurt / hit",
        "loop": False,
        "default_frames": 4,
        "hint": "impact then recover, same character, no gore spray",
        "frames": [
            "impact: body flinches opposite the hit, eyes clenched, weapon dips",
            "peak recoil, off-balance, one foot dragging",
            "catching balance, grimace easing",
            "back to combat ready",
        ],
    },
    "death": {
        "label": "Death",
        "loop": False,
        "default_frames": 6,
        "hint": "collapse in place, last frame is a readable downed pose",
        "frames": [
            "stagger, weapon lowering",
            "knees buckle",
            "falling, one hand reaching the implied ground",
            "body folding",
            "almost down",
            "final downed pose, still the same character, isolated",
        ],
    },
    "jump": {
        "label": "Jump",
        "loop": False,
        "default_frames": 6,
        "hint": "crouch, launch, hang, land — in place",
        "frames": [
            "crouch anticipation, knees bent, arms back",
            "launch, legs extending, arms up",
            "apex hang, tucked slightly",
            "descent, legs reaching down",
            "land contact, knees compress",
            "settle standing",
        ],
    },
    "dash": {
        "label": "Dash / dodge",
        "loop": False,
        "default_frames": 5,
        "hint": "burst sideways or forward, smear ok, same gear",
        "frames": [
            "coil, eyes on the path",
            "burst, body stretched, motion lean",
            "mid dash, compact",
            "decelerate",
            "plant and recover",
        ],
    },
    "turnaround": {
        "label": "Turnaround views",
        "loop": False,
        "default_frames": 5,
        "hint": "same T/A-pose character, rotate the camera, do not redesign",
        "frames": [
            "front view, orthographic, neutral standing, feet parallel",
            "three-quarter front, same pose, true rotation not a new design",
            "strict side profile, same pose, toes to the frame edge",
            "three-quarter back, same pose",
            "true back view, same pose",
        ],
    },
}

STRUCTURES = {
    "building": {
        "label": "Building / house",
        "lock": (
            "isolated isometric game building, full structure visible, no people, "
            "no ground texture extending to the edges, small contact shadow only if needed, "
            "readable silhouette, production prop"
        ),
    },
    "dungeon": {
        "label": "Dungeon piece",
        "lock": (
            "isolated isometric dungeon architecture piece, modular game kitbash chunk, "
            "clean edges so it can sit on a tile grid, no characters"
        ),
    },
    "tile": {
        "label": "Seamless tile",
        "lock": (
            "seamless tileable game texture, no unique landmark that would repeat as a stamp, "
            "edge colors match, non-directional lighting, top-down or orthographic as requested, "
            "no character, no UI"
        ),
    },
    "prop": {
        "label": "Prop / item",
        "lock": (
            "isolated game prop, single object, centered, no ground plane, "
            "clean silhouette, inventory-icon friendly"
        ),
    },
    "vegetation": {
        "label": "Tree / plant",
        "lock": (
            "isolated vegetation sprite, single plant or tree, no terrain slab, "
            "readable at game camera, clean silhouette"
        ),
    },
    "furniture": {
        "label": "Furniture",
        "lock": (
            "isolated isometric furniture piece, single object, no room around it, "
            "game prop, clean edges"
        ),
    },
    "pillar": {
        "label": "Pillar / column",
        "lock": (
            "isolated architectural pillar or column sprite, full height visible, "
            "no floor tile attached, modular dungeon prop"
        ),
    },
    "gate": {
        "label": "Door / gate",
        "lock": (
            "isolated door or gate prop, front or isometric as requested, "
            "no extra hallway, modular entrance piece"
        ),
    },
}

SCENES = {
    "sky": {
        "label": "Sky / skybox",
        "pipeline": "plate",
        "example": "dusk abyss sky, torn cyan rift, ash clouds, two pale moons, no ground",
        "view": "front",
        "size": "1280 × 720  scene plate",
        "lock": (
            "full-frame game sky backdrop, fills the entire image edge to edge, "
            "no character, no building, no ground, no UI, no frame, no watermark, "
            "paintable environment plate"
        ),
    },
    "backdrop": {
        "label": "Background plate",
        "pipeline": "plate",
        "example": "distant ruined city on a cliff, fog, cyan lanterns, no hero in frame",
        "view": "front",
        "size": "1280 × 720  scene plate",
        "lock": (
            "full-frame painted game background plate, complete scene, "
            "no player character, no HUD, no letterbox, environment only"
        ),
    },
    "interior": {
        "label": "Room / interior",
        "pipeline": "plate",
        "example": "dark shrine interior, stone pillars, hanging chains, cyan brazier light",
        "view": "front",
        "size": "1280 × 720  scene plate",
        "lock": (
            "full-frame interior background, playable room, no hero, "
            "readable floor and walls, game environment plate"
        ),
    },
    "wall": {
        "label": "Wall (tileable)",
        "pipeline": "tile",
        "example": "cracked abyss stone brick wall, moss, cyan lichen, seamless",
        "view": "front",
        "size": "1024 × 1024  hero",
        "lock": (
            "seamless tileable wall texture, edges match left-right and top-bottom, "
            "no unique landmark, no character, no window unless asked, orthographic"
        ),
    },
    "floor": {
        "label": "Floor / ground (tileable)",
        "pipeline": "tile",
        "example": "wet dungeon flagstones, dark grout, faint cyan puddles, seamless top-down",
        "view": "top",
        "size": "1024 × 1024  hero",
        "lock": (
            "seamless tileable ground texture, top-down or orthographic, "
            "edge colors match, no unique stamp motif, no character"
        ),
    },
    "water": {
        "label": "Water / lava",
        "pipeline": "tile",
        "example": "still abyss water, cyan glow from below, gentle ripples, tileable",
        "view": "top",
        "size": "1024 × 1024  hero",
        "lock": (
            "seamless tileable liquid surface, no shoreline landmark, "
            "no character, usable as a repeating water or lava layer"
        ),
    },
    "clouds": {
        "label": "Clouds / fog",
        "pipeline": "prop",
        "example": "three layered storm clouds, cyan lightning veins, isolated",
        "view": "front",
        "size": "1024 × 768  wide / iso",
        "lock": (
            "isolated cloud or fog sprite, no ground, clean silhouette, "
            "usable as a parallax layer"
        ),
    },
    "prop": {
        "label": "Any prop",
        "pipeline": "prop",
        "example": "ornate treasure chest, dark iron, cyan lock, isolated",
        "view": "isometric",
        "size": "1024 × 1024  hero",
        "lock": (
            "isolated game prop, single object, centered, no room around it, "
            "no character, clean silhouette, drop-in world object"
        ),
    },
    "platform": {
        "label": "Platform / ledge",
        "pipeline": "prop",
        "example": "floating stone platform, cracked slab, hanging roots, isolated",
        "view": "side",
        "size": "1024 × 768  wide / iso",
        "lock": (
            "isolated platform or ledge sprite, flat top a character could stand on, "
            "no full landscape, clean edges"
        ),
    },
    "rock": {
        "label": "Rock / cliff chunk",
        "pipeline": "prop",
        "example": "jagged black basalt rock, cyan crystal veins, isolated",
        "view": "isometric",
        "size": "1024 × 1024  hero",
        "lock": (
            "isolated rock or cliff chunk, no huge terrain slab, modular landscape prop"
        ),
    },
    "chest": {
        "label": "Chest / crate / barrel",
        "pipeline": "prop",
        "example": "iron-bound barrel, wet wood, abyss moss, isolated",
        "view": "isometric",
        "size": "768 × 1024  character",
        "lock": "isolated loot container prop, single object, no room, clean silhouette",
    },
    "light": {
        "label": "Torch / lantern / brazier",
        "pipeline": "prop",
        "example": "iron wall torch, cyan flame, dripping wax, isolated",
        "view": "side",
        "size": "512 × 768  compact sprite",
        "lock": "isolated light source prop, single object, flame attached, no wall slab unless asked",
    },
    "banner": {
        "label": "Banner / hanging",
        "pipeline": "prop",
        "example": "tattered red banner, gold trim, abyss crest, hanging isolated",
        "view": "front",
        "size": "512 × 768  compact sprite",
        "lock": "isolated hanging banner or tapestry, no wall attached, clean silhouette",
    },
    "bridge": {
        "label": "Bridge / stairs",
        "pipeline": "prop",
        "example": "broken stone bridge span, missing planks, cyan fog below, isolated",
        "view": "isometric",
        "size": "1024 × 768  wide / iso",
        "lock": "isolated bridge or stair piece, modular, no huge landscape",
    },
    "parallax": {
        "label": "Parallax far layer",
        "pipeline": "plate",
        "example": "distant mountain silhouettes, two moons, haze, no foreground detail",
        "view": "front",
        "size": "1536 × 768  sky strip",
        "lock": (
            "wide parallax background layer, soft distant forms only, "
            "no foreground props, no character, edge-to-edge strip"
        ),
    },
}


def scene_catalog() -> dict:
    return {**STRUCTURES, **SCENES}


def _join(parts: Iterable[str]) -> str:
    return ", ".join(p.strip().rstrip(",") for p in parts if p and p.strip())


def compile_prompt(
    user_text: str,
    *,
    style: str = "abyssal_iso",
    view: str = "isometric",
    bg: str = "green",
    kind: str = "sprite",
    identity: str = "",
    pose: str = "",
    extra: str = "",
    structure_kind: str = "",
    intent: Intent | None = None,
    presentation: str = "",
) -> str:
    user_text = (user_text or "").strip()
    style_words = STYLES.get(style, STYLES["abyssal_iso"])["words"]
    view_words = VIEWS.get(view, VIEWS["isometric"])
    bg_words = BG_HEX.get(bg, BG_HEX["green"])[1]
    brain = intent if intent is not None else (Intent(raw=user_text, rewritten=user_text) if identity else understand(user_text))

    parts: list[str] = []
    if identity:
        parts.append(IDENTITY_KEEP)
        parts.append(identity.strip())
        if user_text:
            parts.append(user_text)
    else:
        parts.append(brain.visual())
        if brain.transformed and brain.negatives:
            parts.append(f"must not be: {brain.negatives}")
    if pose:
        parts.append(pose)
    if kind in {"structure", "scene"}:
        catalog = scene_catalog()
        sk = catalog.get(structure_kind or "prop", catalog["prop"])
        parts.append(sk["lock"])
    else:
        parts.append(SPRITE_LOCK)
    parts.append(view_words)
    parts.append(style_words)
    if presentation:
        parts.append(presentation)
    parts.append(bg_words)
    if extra:
        parts.append(extra)
    return _join(parts)


def compile_negative(kind: str = "sprite", extra: str = "") -> str:
    base = (
        "photobash, collage, multiple characters, extra limbs, extra heads, "
        "deformed hands, text, watermark, logo, frame, border, UI, HUD, "
        "busy background, landscape, ground plane stretching, drop shadow blob, "
        "blurry, lowres, cropped head, cropped feet, photograph of a toy"
    )
    if kind == "tile":
        base += ", unique landmark, off-center motif, character, UI"
    if extra:
        base = extra + ", " + base
    return base


def pixel_hint(pixel_size: int | None) -> str:
    if not pixel_size:
        return ""
    return (
        f"authentic pixel art at {pixel_size}x{pixel_size} logical resolution, "
        "visible square pixels, no smeared anti-alias"
    )
