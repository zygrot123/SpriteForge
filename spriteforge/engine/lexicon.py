"""Large phrase dictionary so casual human speech becomes a visual prompt."""
from __future__ import annotations

import re

SPACE = re.compile(r"\s+")
FILLER = re.compile(
    r"\b(um+|uh+|er+|ah+|hmm+|you know|i mean|basically|literally|"
    r"kinda|kind of|sort of|sorta|just|please|pretty please|can you please|"
    r"would you|could you|will you)\b",
    re.I,
)

# Spoken / chat wrappers. Longest first when applied.
WRAPPERS = (
    r"^(hey|hi|hello|yo|ok|okay|so)\s+",
    r"^(can you|could you|would you|will you)\s+(please\s+)?",
    r"^(please\s+)?(try to\s+)?(make|draw|paint|generate|create|render|imagine|do)\s+(me\s+)?(a|an|some|this)?\s*",
    r"^(i want|i need|i'd like|i would like|i wanna|give me|gimme|show me|get me)\s+(a|an|some|to see)?\s*",
    r"^(how about|what about|maybe)\s+(a|an|some)?\s*",
    r"^(something like|kinda like|kind of like|similar to)\s+",
    r"\s+(please|thanks|thank you|for me)[\s.!?]*$",
)

# Multi-word slang / fluid talk → paint instructions. Longest keys win.
PHRASES: dict[str, str] = {
    # requests / intent
    "text to image": "still image",
    "text to video": "animated cinematic shot",
    "image to video": "animate this still into a moving shot",
    "make it move": "subtle living motion, same scene",
    "bring it to life": "subtle cinematic motion, atmosphere alive",
    "upscale it": "ultra sharp 4k detail pass, same composition",
    "make it 4k": "ultra sharp 4k master, more fine detail",
    "four variations": "four distinct variations of the same idea",
    "same character": "keep this exact character identity",
    "same person": "keep this exact character identity",
    "don't change them": "do not redesign the subject",
    "don't change it": "do not redesign the subject",
    "no people": "no person, no character, no figure, no silhouette",
    "no person": "no character, no figure, no human silhouette",
    "no characters": "empty of people, environment only",
    "nobody in it": "no person, no figure, empty of characters",
    "no ground": "no ground plane, no floor, no terrain underfoot",
    "no floor": "no ground plane, no floor",
    "no background": "isolated subject, clean empty backdrop",
    "punch out the background": "solid chroma-key backdrop, isolated subject",
    "cut out the background": "isolated subject, transparent-ready backdrop",
    "full body": "full body visible, head to feet in frame",
    "from the waist up": "waist-up portrait crop",
    "close up": "tight close-up, face readable",
    "wide shot": "wide establishing shot, environment readable",
    "bird's eye": "top-down bird's-eye view",
    "worm's eye": "low worm's-eye camera looking up",
    # mood
    "kinda moody": "melancholic mood, muted emotional atmosphere",
    "really moody": "heavy melancholic mood, brooding atmosphere",
    "dark and moody": "dark brooding mood, low-key lighting",
    "cozy and warm": "warm cozy atmosphere, soft amber light",
    "cold and lonely": "cold lonely atmosphere, sparse composition",
    "eerie as hell": "eerie unsettling atmosphere, quiet dread",
    "super epic": "epic cinematic scale, heroic framing",
    "low key": "low-key lighting, deep shadows",
    "high key": "high-key bright even lighting",
    "dream like": "dreamlike haze, soft focus atmosphere",
    "dream-like": "dreamlike haze, soft focus atmosphere",
    "nightmarish": "nightmarish, distorted dread, harsh contrast",
    "fairytale": "storybook fairytale, enchanted color",
    "slice of life": "quiet everyday slice-of-life moment",
    "bittersweet": "bittersweet mood, tender and sad",
    "hopeful dawn": "hopeful dawn light, soft gold on cool shadow",
    "end of the world": "apocalyptic ruin, ash sky, last-light mood",
    "after the rain": "wet surfaces, petrichor mood, puddle reflections",
    "golden hour": "golden hour sunlight, long warm shadows",
    "blue hour": "blue hour twilight, cool ambient sky",
    "dead of night": "dead of night, near-black, sparse practical lights",
    "high noon": "harsh noon sun, short hard shadows",
    # weather / sky
    "ripped cyan holes": "torn cyan rifts in the sky",
    "torn cyan rift": "torn cyan rift tearing the sky",
    "two faded moons": "two pale faded moons",
    "two pale moons": "two pale moons",
    "blood moon": "oversized crimson blood moon",
    "storm rolling in": "approaching storm front, dark anvil clouds",
    "clear skies": "clear open sky, clean horizon",
    "overcast gloom": "flat overcast gloom, soft shadowless light",
    "ash clouds": "ashen volcanic clouds",
    "toxic sky": "sickly toxic sky, unnatural green-cyan",
    "abyss sky": "abyssal underworld sky",
    "dusk sky": "dusk sky, last light",
    "northern lights": "aurora borealis curtains",
    "shooting stars": "meteor streaks across the sky",
    "heavy fog": "dense fog, depth planes disappearing",
    "light mist": "thin mist, soft depth",
    "pouring rain": "heavy rain streaks, wet shine",
    "light drizzle": "fine drizzle, damp surfaces",
    "blizzard": "white-out blizzard, driven snow",
    "heat haze": "desert heat haze, shimmering air",
    # camera / game
    "hades style": "Supergiant Hades painterly isometric, high-contrast underworld palette",
    "hades like": "Supergiant Hades painterly isometric, high-contrast underworld palette",
    "hades-like": "Supergiant Hades painterly isometric, high-contrast underworld palette",
    "like hades": "Supergiant Hades painterly isometric",
    "isometric view": "isometric 2:1 camera, 30 degrees down, 45 yaw",
    "top down": "top-down orthographic game view",
    "top-down": "top-down orthographic game view",
    "side scroller": "2D side-scroller camera, profile readable",
    "side-scroller": "2D side-scroller camera, profile readable",
    "2.5d": "2.5D side view with slight depth",
    "three quarter": "three-quarter view, both eyes visible",
    "three-quarter": "three-quarter view, both eyes visible",
    "turnaround sheet": "character turnaround sheet pose, neutral",
    "sprite sheet": "game sprite, isolated, production asset",
    "concept art": "finished concept art illustration",
    "key art": "marketing key art, heroic composition",
    "loading screen": "wide painted loading-screen plate",
    "skybox": "full-frame sky backdrop, edge to edge, no ground unless asked",
    "parallax layer": "soft far parallax layer, no foreground clutter",
    "tileable": "seamless tileable, edges match",
    "seamless tile": "seamless tileable texture, edges match",
    "pixel art": "authentic pixel art, visible pixels, limited palette",
    "16 bit": "16-bit era pixel art, limited palette, hard edges",
    "32 bit": "32-bit SNES-like pixel art",
    "cel shaded": "cel-shaded, bold ink, flat fills, two-tone shadow",
    "cel-shaded": "cel-shaded, bold ink, flat fills, two-tone shadow",
    "oil painted": "oil-paint texture, visible brush, rich midtones",
    "hand painted": "hand-painted game art",
    "photoreal": "grounded photoreal materials, still an illustration",
    "not photoreal": "stylized, not photorealistic, not a 3D render",
    "not 3d": "2D painted, not a 3D render",
    "low poly": "low-poly faceted look, simple materials",
    "low-poly": "low-poly faceted look, simple materials",
    "chibi cute": "chibi proportions, oversized head, short limbs",
    # light
    "rim light": "strong rim light separating the silhouette",
    "backlit": "backlit, subject as a dark shape against bright air",
    "god rays": "volumetric god rays",
    "neon glow": "neon practical lights, colored bloom",
    "candle light": "warm candle light, flickering practicals",
    "moonlight": "cool moonlight, silver-blue fill",
    "firelight": "warm firelight, orange bounce on nearby forms",
    "underlight": "underlighting from below, dramatic",
    "soft studio light": "even studio softbox lighting",
    "harsh spotlight": "single harsh spotlight, deep falloff",
    "bioluminescent": "bioluminescent glow from living forms",
    "cyan visor": "single cyan visor slit",
    "ember light": "ember and coal light, warm on cool shadow",
    # materials
    "blackened plate": "blackened plate armor, soot and oil sheen",
    "torn red cape": "torn red cape, frayed hem",
    "wet stone": "wet stone, dark grout, specular puddles",
    "cracked marble": "cracked marble, gold or moss in the breaks",
    "rusted iron": "rusted iron, flaking scale",
    "worn leather": "worn leather, creases and scuffs",
    "silk cloth": "silk cloth, sharp highlights",
    "chainmail": "chainmail rings, tight weave",
    "obsidian": "obsidian glass-rock, sharp facets",
    "gold leaf": "gold leaf ornament, thin bright metal",
    "cyan lichen": "cyan lichen growing in cracks",
    "rune cracks": "glowing rune-cracked stone",
    # places
    "underworld": "underworld abyss, cool shadow, warm ember",
    "dungeon hall": "dungeon hall, repeating pillars, torch pools",
    "ruined city": "ruined city silhouette, broken towers",
    "cliff shrine": "cliffside shrine, hanging chains",
    "black sea": "black sea, weak specular path",
    "lonely lantern": "a single lonely lantern as the hero light",
    "throne room": "vast throne room, one seat of power",
    "market street": "crowded market street, hanging cloth, stalls",
    "forest path": "forest path, filtered canopy light",
    "snow peak": "snow peak, thin air, hard sunlight",
    "desert ruin": "desert ruin, sand-choked stone",
    "space vista": "deep space vista, planet and debris",
    "underwater": "underwater, caustic light, suspended particles",
    "castle wall": "castle wall, merlons, weather stains",
    "village night": "quiet village night, window lamps",
    # motion
    "walk cycle": "in-place walk cycle, alternating gait",
    "idle breathe": "idle breathe, weight shift, feet planted",
    "slow push in": "slow camera push-in",
    "slow push-in": "slow camera push-in",
    "camera locked": "camera locked, subject moves in place",
    "orbit around": "camera orbits the subject",
    "wind in cloth": "cloth and hair reacting to wind",
    "living water": "water living, gentle swell",
    "clouds drifting": "clouds slowly drifting",
    "embers rising": "embers rising on a draft",
}

WORDS: dict[str, str] = {
    # mood
    "moody": "moody atmosphere",
    "gloomy": "gloomy somber atmosphere",
    "cozy": "warm cozy atmosphere",
    "eerie": "eerie quiet dread",
    "creepy": "creepy unsettling",
    "spooky": "spooky, not cartoon-halloween unless asked",
    "epic": "epic cinematic scale",
    "intimate": "intimate close framing",
    "lonely": "lonely sparse composition",
    "peaceful": "peaceful still air",
    "chaotic": "chaotic energy, controlled composition",
    "serene": "serene calm",
    "brutal": "brutal, heavy forms",
    "delicate": "delicate fine detail",
    "gritty": "gritty worn texture",
    "clean": "clean readable shapes",
    "messy": "lived-in messy detail",
    "sacred": "sacred quiet, ritual objects",
    "cursed": "cursed, wrong light",
    "holy": "holy radiance, soft gold",
    "profane": "profane, ash and iron",
    "melancholy": "melancholy mood",
    "nostalgic": "nostalgic faded color",
    "romantic": "romantic warm light",
    "tragic": "tragic still moment",
    "heroic": "heroic stance and framing",
    "villainous": "villainous presence, threatening silhouette",
    "whimsical": "whimsical playful shapes",
    "solemn": "solemn ceremonial",
    "tense": "tense held breath",
    "calm": "calm stable composition",
    "wild": "wild untamed forms",
    "ancient": "ancient weathered",
    "futuristic": "futuristic design language",
    "retro": "retro period design",
    "vintage": "vintage color and wear",
    "modern": "modern clean design",
    "ornate": "ornate decoration",
    "minimal": "minimal spare forms",
    "baroque": "baroque excess ornament",
    "gothic": "gothic pointed forms, stained dark",
    "noir": "noir, hard light, wet streets",
    "cyberpunk": "cyberpunk neon, rain, dense signage",
    "steampunk": "steampunk brass, steam, gears",
    "solarpunk": "solarpunk green tech, sun and plants",
    "dieselpunk": "dieselpunk interwar machines",
    "western": "western dust, wood, wide sky",
    "samurai": "samurai armor language, bakumatsu grit",
    "viking": "viking furs, rings, cold sea",
    "egyptian": "ancient egyptian motifs, gold and lapis",
    "greek": "classical greek marble and bronze",
    "aztec": "aztec stone geometry, jade and sun",
    # time / weather
    "dawn": "dawn, first light",
    "sunrise": "sunrise, warm low sun",
    "morning": "morning light, cool residual shadow",
    "noon": "noon, short hard shadows",
    "afternoon": "late afternoon warmth",
    "dusk": "dusk, last light",
    "sunset": "sunset, long color grade",
    "twilight": "twilight, mixed color temperature",
    "night": "night, practical lights only",
    "midnight": "midnight, deepest blue-black",
    "storm": "storm, moving weather",
    "rain": "rain, wet shine, streaks",
    "snow": "falling snow, cold air",
    "fog": "fog, lost depth",
    "mist": "mist, soft planes",
    "smoke": "smoke drift",
    "ash": "ash fall, gray air",
    "dust": "dust motes in shafts of light",
    "wind": "wind in cloth and particles",
    "thunder": "thunderhead, distant flash",
    "lightning": "lightning bolt, frozen flash",
    "aurora": "aurora curtains",
    "eclipse": "solar eclipse, strange twilight",
    # camera
    "isometric": "isometric game camera",
    "orthographic": "orthographic, no perspective warp",
    "perspective": "natural perspective",
    "macro": "macro close detail",
    "panorama": "wide panorama",
    "portrait": "portrait orientation framing",
    "landscape": "landscape orientation framing",
    "silhouette": "readable silhouette",
    "backlight": "backlight, glowing edge",
    "sidelight": "sidelight, form-revealing",
    "overcast": "overcast soft light",
    "volumetric": "volumetric light shafts",
    "bokeh": "shallow depth, background bokeh",
    "sharp": "optically sharp",
    "soft": "soft edges, gentle falloff",
    "grainy": "fine film grain",
    "crisp": "crisp edges, high local contrast",
    # color
    "cyan": "cyan",
    "teal": "teal",
    "ember": "ember orange",
    "crimson": "crimson",
    "gold": "gold",
    "ivory": "ivory",
    "obsidian": "obsidian black",
    "ashen": "ashen gray",
    "violet": "violet",
    "indigo": "indigo",
    "amber": "amber",
    "copper": "copper",
    "bronze": "bronze",
    "silver": "silver",
    "pastel": "pastel palette",
    "neon": "neon saturated lights",
    "muted": "muted desaturated palette",
    "saturated": "rich saturated color",
    "monochrome": "monochrome",
    "duotone": "duotone limited palette",
    # stuff
    "knight": "armored knight",
    "witch": "witch, ritual cloth and charms",
    "wizard": "wizard, robe and focus item",
    "rogue": "rogue, light armor, blades",
    "archer": "archer, bow and quiver",
    "priest": "priest, vestments",
    "hunter": "hunter, travel gear",
    "soldier": "soldier, practical kit",
    "king": "crowned king",
    "queen": "crowned queen",
    "prince": "prince",
    "princess": "princess",
    "merchant": "merchant, goods and coin",
    "blacksmith": "blacksmith, hammer and apron",
    "assassin": "assassin, dark wrap, quiet stance",
    "paladin": "paladin, holy plate",
    "necromancer": "necromancer, bone and green fire",
    "druid": "druid, living wood and leaf",
    "monk": "monk, simple cloth, ready stance",
    "bard": "bard, instrument and color",
    "pirate": "pirate, sea-worn cloth",
    "ninja": "ninja, wrap and short blade",
    "cyborg": "cyborg, flesh and machine join",
    "android": "android, designed humanoid machine",
    "alien": "alien, nonhuman anatomy",
    "fairy": "fairy, small, wing light",
    "elf": "elf, long features, fine cloth",
    "dwarf": "dwarf, compact powerful build",
    "orc": "orc, tusked, heavy",
    "goblin": "goblin, small cunning",
    "troll": "troll, huge coarse",
    "ogre": "ogre, massive crude",
    "giant": "giant, scale against the world",
    "vampire": "vampire, pale, formal dark",
    "werewolf": "werewolf, hybrid wolf-human",
    "lich": "lich, regal undead",
    "wraith": "wraith, torn spirit form",
    "phoenix": "phoenix, fire-bird",
    "griffin": "griffin, eagle-lion",
    "pegasus": "pegasus, winged horse",
    "unicorn": "unicorn, horned horse",
    "hydra": "hydra, many serpent heads",
    "kraken": "kraken, vast sea tentacles",
    "colossus": "colossus, architecture-scale being",
    "golem": "golem, animated matter",
    "elemental": "elemental, body of a single element",
    "lantern": "lantern as a hero light source",
    "anvil": "heavy anvil",
    "helm": "closed helm",
    "visor": "visor slit",
    "cape": "cape",
    "banner": "hanging banner",
    "torch": "torch",
    "brazier": "brazier",
    "chest": "loot chest",
    "gate": "gate or door",
    "bridge": "bridge span",
    "stairs": "stairs",
    "pillar": "pillar",
    "altar": "altar",
    "shrine": "shrine",
    "temple": "temple",
    "castle": "castle",
    "keep": "keep",
    "tower": "tower",
    "village": "village",
    "harbor": "harbor",
    "ship": "ship",
    "wagon": "wagon",
    "camp": "camp",
    "cave": "cave",
    "mine": "mine",
    "library": "library hall",
    "cathedral": "cathedral nave",
    "arena": "arena",
    "colosseum": "colosseum",
    "garden": "garden",
    "graveyard": "graveyard",
    "swamp": "swamp",
    "tundra": "tundra",
    "volcano": "volcano",
    "reef": "reef",
    "oasis": "oasis",
    "canyon": "canyon",
    "mesa": "mesa",
    "glacier": "glacier",
    "island": "island",
    "archipelago": "archipelago",
    "nebula": "nebula",
    "planet": "planet",
    "station": "space station",
    "alley": "narrow alley",
    "rooftop": "rooftop",
    "subway": "subway",
    "diner": "diner",
    "lab": "laboratory",
    "factory": "factory",
    "warehouse": "warehouse",
    "office": "office interior",
    "apartment": "apartment interior",
    "kitchen": "kitchen",
    "bedroom": "bedroom",
    "throne": "throne",
    "crown": "crown",
    "sword": "sword",
    "spear": "spear",
    "axe": "axe",
    "bow": "bow",
    "staff": "staff",
    "shield": "shield",
    "dagger": "dagger",
    "scythe": "scythe",
    "hammer": "warhammer",
    "gun": "designed firearm, still painted not a photo",
    "rifle": "long rifle",
    "pistol": "sidearm",
    "wand": "wand",
    "orb": "orb",
    "tome": "heavy tome",
    "scroll": "scroll",
    "potion": "potion bottle",
    "crystal": "crystal",
    "gem": "cut gem",
    "coin": "coin",
    "key": "ornate key",
    "mask": "mask",
    "wings": "wings",
    "horns": "horns",
    "tail": "tail",
    "halo": "halo",
    "aura": "soft aura",
    "runes": "runes",
    "sigil": "sigil",
    "circle": "magic circle",
}

# Extra spoken sentence templates → keep the meat, drop the chatter.
SENTENCE_CUTS = (
    re.compile(r"^(i was thinking( of| about)?|i had an idea( for)?|picture this[: ]*|imagine if )\s*", re.I),
    re.compile(r"^(it should (look|feel|be)|make it (look|feel|be)|i want it to (look|feel|be))\s+", re.I),
    re.compile(r"\b(if that makes sense|you know what i mean|or something( like that)?)\b", re.I),
    re.compile(r"\b(for the game|for my game|for the project|for unity|for unreal|for godot)\b", re.I),
)


def _strip_wrappers(text: str) -> str:
    t = text.strip()
    t = FILLER.sub(" ", t)
    for pat in SENTENCE_CUTS:
        t = pat.sub(" ", t)
    changed = True
    while changed:
        changed = False
        for pat in WRAPPERS:
            nxt = re.sub(pat, "", t, flags=re.I).strip(" ,.-")
            if nxt != t:
                t = nxt
                changed = True
    return SPACE.sub(" ", t).strip(" ,.-")


def _hold_replace(text: str, mapping: dict[str, str], holders: dict[str, str], start: int) -> tuple[str, int, int]:
    """Replace matches with placeholders so expansions are not rewritten again."""
    hits = 0
    n = start
    out = text
    for src, dest in sorted(mapping.items(), key=lambda kv: len(kv[0]), reverse=True):
        pat = re.compile(rf"\b{re.escape(src)}\b", re.I)

        def repl(_m: re.Match, d: str = dest, idx: list[int] | None = None) -> str:
            nonlocal n, hits
            key = f"\x00H{n}\x00"
            holders[key] = d
            n += 1
            hits += 1
            return key

        out, count = pat.subn(repl, out)
        if count:
            pass
    return out, hits, n


def _restore(text: str, holders: dict[str, str]) -> str:
    for _ in range(4):
        nxt = text
        for key, dest in holders.items():
            nxt = nxt.replace(key, dest)
        if nxt == text:
            break
        text = nxt
    return text


def fluidize(text: str, *, expand: bool = True) -> tuple[str, list[str]]:
    """Turn casual speech into a cleaner visual description.

    Returns (cleaned_text, notes).
    """
    raw = SPACE.sub(" ", (text or "").strip())
    notes: list[str] = []
    if not raw:
        return "", notes
    cleaned = _strip_wrappers(raw)
    if cleaned != raw:
        notes.append("heard the request, kept the idea")
    if expand:
        holders: dict[str, str] = {}
        cleaned, ph, n = _hold_replace(cleaned, PHRASES, holders, 0)
        cleaned, wo, _n = _hold_replace(cleaned, WORDS, holders, n)
        cleaned = _restore(cleaned, holders)
        if ph or wo:
            notes.append(f"understood {ph + wo} everyday phrases")
    cleaned = SPACE.sub(" ", cleaned).strip(" ,.-")
    return cleaned or raw, notes


def dictionary_size() -> int:
    return len(PHRASES) + len(WORDS)
