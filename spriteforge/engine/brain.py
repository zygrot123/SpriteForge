from __future__ import annotations

import re
from dataclasses import dataclass, field

# Visual recipes the model actually paints. The raw word "fish" is too weak
# next to a celebrity token like "Pikachu", so we spell the new BODY first.
FORMS: dict[str, dict[str, str]] = {
    "fish": {
        "body": (
            "the body is a real fish, horizontal fish silhouette, scales, gills, "
            "pectoral fins instead of arms, tail fin, no legs, no feet, no standing pose, "
            "aquatic creature, swims"
        ),
        "forbid": "bipedal, standing on two legs, mouse body, rodent, land animal, feet, shoes, walking pose",
    },
    "shark": {
        "body": "shark body, dorsal fin, gills, crescent tail, no legs, predatory fish silhouette",
        "forbid": "standing, legs, cute land animal, mouse body",
    },
    "whale": {
        "body": "whale body, huge smooth flukes, blowhole, no legs, ocean mammal silhouette",
        "forbid": "standing, legs, small rodent body",
    },
    "bird": {
        "body": "bird body, wings instead of arms, talons, beak, feathers, no human hands",
        "forbid": "human arms, standing mammal, no wings",
    },
    "dragon": {
        "body": "dragon body, scales, wings, horns, claws, long tail, reptile snout",
        "forbid": "soft cartoon mascot body only, no wings",
    },
    "robot": {
        "body": "mechanical robot body, metal plates, pistons, visor, joints, no organic skin",
        "forbid": "soft flesh, fur, organic animal body",
    },
    "ghost": {
        "body": "ghostly floating body, translucent tail instead of legs, no feet on the ground",
        "forbid": "solid standing body, heavy feet planted",
    },
    "slime": {
        "body": "blob slime body, gelatinous, no hard limbs, eyes sitting in goo",
        "forbid": "articulated skeleton, hard armor body",
    },
    "skeleton": {
        "body": "exposed bones, skull, ribcage, skeletal limbs, no flesh",
        "forbid": "fully fleshed cute mascot",
    },
    "zombie": {
        "body": "undead rotting body, torn clothes, sagging posture, damaged limbs",
        "forbid": "clean healthy mascot, shiny fur",
    },
    "cat": {
        "body": "feline body, digitigrade legs, tail, whiskers, paws",
        "forbid": "human hands, rodent cheeks as the whole body",
    },
    "dog": {
        "body": "canine body, snout, paws, tail, quadruped or anthro dog",
        "forbid": "mouse ears as the only animal trait",
    },
    "frog": {
        "body": "frog body, wet skin, huge eyes, long hind legs, no fur",
        "forbid": "fur, dry mammal body",
    },
    "snake": {
        "body": "serpent body, no legs, long coiled tail, scales, forked tongue",
        "forbid": "legs, feet, standing pose",
    },
    "spider": {
        "body": "arachnid body, eight legs, abdomen, fangs",
        "forbid": "two-legged standing mascot",
    },
    "bee": {
        "body": "bee body, yellow-black stripes, translucent wings, antennae, insect legs",
        "forbid": "mammal body, no wings, no stripes",
    },
    "plant": {
        "body": "living plant body, leaves, vines, bark or petals instead of skin",
        "forbid": "ordinary animal fur, metal",
    },
    "tree": {
        "body": "tree-person, trunk torso, branch arms, leafy crown",
        "forbid": "ordinary mammal body",
    },
    "fire": {
        "body": "body made of living flame, ember core, heat distortion, no solid fur",
        "forbid": "ordinary cloth and flesh only",
    },
    "ice": {
        "body": "body of carved ice and frost, translucent, snow dust",
        "forbid": "warm fur only, no ice",
    },
    "crystal": {
        "body": "faceted crystal body, geometric shards, refractive",
        "forbid": "soft organic body only",
    },
    "golem": {
        "body": "stone or clay golem, carved blocky limbs, cracks, runes",
        "forbid": "soft cute mascot proportions only",
    },
    "angel": {
        "body": "winged angel, halo, feathered wings, flowing cloth",
        "forbid": "no wings, mundane street clothes only",
    },
    "demon": {
        "body": "demon body, horns, pointed tail, ember eyes, dark hide",
        "forbid": "innocent unchanged mascot",
    },
    "mermaid": {
        "body": "upper torso with a long fish tail instead of legs, scales from the waist down, fins",
        "forbid": "two human legs, standing on feet",
    },
    "octopus": {
        "body": "octopus body, eight tentacles, suckers, mantle, no legs",
        "forbid": "standing mammal, two arms two legs",
    },
    "bat": {
        "body": "bat body, leathery wings, pointed ears, hanging or flying pose",
        "forbid": "no wings, standing rodent only",
    },
    "wolf": {
        "body": "wolf body, muzzle, ruff, bushy tail, claws",
        "forbid": "round mouse face as the whole design",
    },
    "knight": {
        "body": "full plate armor over the character, visor, gauntlets, cape",
        "forbid": "naked mascot with no armor",
    },
}

ALIASES = {
    "fishes": "fish",
    "fishy": "fish",
    "goldfish": "fish",
    "koi": "fish",
    "salmon": "fish",
    "tuna": "fish",
    "sharky": "shark",
    "robotic": "robot",
    "mecha": "robot",
    "mech": "robot",
    "android": "robot",
    "undead": "zombie",
    "skelton": "skeleton",
    "skelly": "skeleton",
    "ghostly": "ghost",
    "spirit": "ghost",
    "avian": "bird",
    "eagle": "bird",
    "phoenix": "bird",
    "draconic": "dragon",
    "wyvern": "dragon",
    "feline": "cat",
    "kitty": "cat",
    "puppy": "dog",
    "canine": "dog",
    "serpent": "snake",
    "arachnid": "spider",
    "buzzy": "bee",
    "floral": "plant",
    "flame": "fire",
    "frost": "ice",
    "gem": "crystal",
    "stone": "golem",
    "rock": "golem",
    "devil": "demon",
    "fiend": "demon",
    "siren": "mermaid",
    "kraken": "octopus",
    "squid": "octopus",
}

# Famous subjects whose default look will crush a weak "but as a fish" clause.
KNOWN_MARKERS = {
    "pikachu": "keep only Pikachu identity markers: yellow color, red circular cheeks, long black-tipped ears, lightning-bolt motif",
    "charizard": "keep Charizard identity: orange hide, cream belly, flame tail tip, blue eyes",
    "mario": "keep Mario identity: red cap with M, blue overalls, brown moustache, round nose",
    "luigi": "keep Luigi identity: green cap, tall slim frame, moustache",
    "sonic": "keep Sonic identity: blue quills, red shoes motif, peach arms/muzzle",
    "link": "keep Link identity: green tunic, pointed ears, scabbard motif",
    "kirby": "keep Kirby identity: round pink body, red feet, oval eyes, blush",
    "yoshi": "keep Yoshi identity: green hide, orange saddle-back, long tongue motif",
    "bowser": "keep Bowser identity: spiked shell, orange hide, horns",
    "spider-man": "keep Spider-Man identity: red-blue suit, web pattern, eye lenses",
    "spiderman": "keep Spider-Man identity: red-blue suit, web pattern, eye lenses",
    "batman": "keep Batman identity: cowl ears, cape, chest emblem",
    "goku": "keep Goku identity: spiky black hair, orange gi, boots",
    "naruto": "keep Naruto identity: whisker cheeks, orange-black, forehead protector motif",
    "mickey": "keep Mickey identity: round black ears, red shorts, yellow shoes",
}

TRANSFORM_PATTERNS = [
    re.compile(
        r"(?P<sub>.+?)\s+but\s+(?:please\s+)?(?:make\s+(?:it|this|him|her|them)\s+)?"
        r"(?:look\s+)?(?:like\s+)?(?:as\s+)?(?:a\s+|an\s+)?(?P<form>.+)$",
        re.I,
    ),
    re.compile(
        r"(?P<sub>.+?)\s+(?:turned|transformed|morphed)\s+into\s+(?:a\s+|an\s+)?(?P<form>.+)$",
        re.I,
    ),
    re.compile(
        r"make\s+(?P<sub>.+?)\s+(?:into|as|become)\s+(?:a\s+|an\s+)?(?P<form>.+)$",
        re.I,
    ),
    re.compile(r"(?P<sub>.+?)\s+as\s+(?:a\s+|an\s+)?(?P<form>.+)$", re.I),
    re.compile(r"(?P<form>.+?)\s+version\s+of\s+(?P<sub>.+)$", re.I),
    re.compile(r"(?P<sub>.+?)\s+hybrid\s+(?:with\s+)?(?P<form>.+)$", re.I),
    re.compile(r"(?P<sub>.+?)\s+but\s+(?:it'?s|it is)\s+(?:a\s+|an\s+)?(?P<form>.+)$", re.I),
    re.compile(r"(?P<sub>.+?)\s+like\s+(?:a\s+|an\s+)?(?P<form>.+)$", re.I),
]

FILLER = re.compile(
    r"\b(please|just|really|kinda|kind of|sort of|like|looks? like|"
    r"make it|make this|make him|make her|turn it into|as a|as an|as|"
    r"a|an|the|but|its|it's|it is|very|super|more|of)\b",
    re.I,
)
SPACE = re.compile(r"\s+")


@dataclass
class Intent:
    raw: str
    subject: str = ""
    form_key: str = ""
    form_text: str = ""
    rewritten: str = ""
    negatives: str = ""
    summary: str = ""
    transformed: bool = False
    notes: list[str] = field(default_factory=list)

    def visual(self) -> str:
        return self.rewritten or self.raw


def _norm_form(text: str) -> str:
    cleaned = FILLER.sub(" ", text or "")
    cleaned = SPACE.sub(" ", cleaned).strip().lower()
    words = []
    for w in cleaned.split():
        if w not in words:
            words.append(w)
    return " ".join(words)


def _match_form(text: str) -> str:
    blob = _norm_form(text)
    if not blob:
        return ""
    if blob in FORMS:
        return blob
    if blob in ALIASES:
        return ALIASES[blob]
    for token in blob.split():
        if token in FORMS:
            return token
        if token in ALIASES:
            return ALIASES[token]
    return ""


def _markers(subject: str) -> str:
    s = (subject or "").lower()
    for name, mark in KNOWN_MARKERS.items():
        if name in s:
            return mark
    return f"keep the recognizable identity of {subject.strip()}: signature colors, face, and motifs only"


def understand(user_text: str) -> Intent:
    raw = (user_text or "").strip()
    intent = Intent(raw=raw, rewritten=raw, summary="literal description")
    if not raw:
        return intent

    sub = form = ""
    used_like = False
    for pat in TRANSFORM_PATTERNS:
        m = pat.search(raw)
        if not m:
            continue
        sub = (m.groupdict().get("sub") or "").strip(" ,.-")
        form = (m.groupdict().get("form") or "").strip(" ,.-")
        if sub and form and sub.lower() != form.lower():
            used_like = "like\\s+" in pat.pattern and "but" not in pat.pattern
            break
        sub = form = ""

    form_key = _match_form(form) if form else ""
    if used_like and not form_key:
        intent.rewritten = SPACE.sub(" ", raw)
        return intent
    if not form and not form_key:
        intent.rewritten = SPACE.sub(" ", raw)
        return intent

    recipe = FORMS.get(form_key)
    subject = sub or raw
    label = form_key or _norm_form(form) or form
    body = recipe["body"] if recipe else (
        f"the body is a {label}, redesigned so the silhouette reads as {label} first"
    )
    forbid = recipe["forbid"] if recipe else f"default {subject} body, ignoring the {label} redesign"

    markers = _markers(subject)
    intent.subject = subject
    intent.form_key = label
    intent.form_text = form or label
    intent.transformed = True
    intent.rewritten = (
        f"NOT a normal {subject}. NOT the default {subject} body. "
        f"This is a {label} redesign of {subject}. "
        f"The silhouette must read as a {label} first. {body}. "
        f"{markers}. "
        f"Merge {subject} into a {label} — a single hybrid creature, full body visible."
    )
    intent.negatives = (
        f"normal {subject}, default {subject}, unchanged {subject}, "
        f"{forbid}, ignoring the {label} body"
    )
    intent.summary = f"{subject}  →  {label} hybrid (not a normal {subject})"
    intent.notes.append(f"rewrote weak 'as a {label}' into a body-first prompt")
    return intent
