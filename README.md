# SpriteForge

Private local Windows sprite studio. Talks to **ComfyUI + FLUX** on your GPU. No paid API is required.

Track this repo in **GitHub Desktop** (File → Add local repository → `SpriteForge`). Pull/push as you change the app.

## What it does

- **Generate** — type a character or prop. SpriteForge writes a game-ready prompt (isolated subject, keyable background, locked camera).
- **Lock model** — save a character as an exact identity (description + reference image + seed). Later images start from that reference instead of rolling a new person.
- **Animations** — idle, walk, run, attack, cast, hurt, death, jump, dash, turnaround. Each frame is img2img from the previous one so the model stays the same.
- **Structures** — buildings, dungeon pieces, tiles, props, trees, furniture, pillars, gates.
- **Floors** — Seeing Eyes-style local dungeon builder. Paint floor / hall / water / cave tiles, press R to rotate, Generate fills the rest so openings meet. Bake a matching Flux kit, then export isometric + top-down PNG or a zip.
- **Sheets** — overlay a grid, slice a sheet, compose a folder of frames, preview the loop.

## Run (this PC, from source)

Double-click `launch.bat`.

## Download the EXE (Release)

**[SpriteForge v1.0.11 — Windows zip](https://github.com/zygrot123/SpriteForge/releases/tag/v1.0.11)**

Unzip the whole folder, then run `SpriteForge.exe`. Keep `_internal` next to the exe.

GitHub Desktop → repo → **Releases** also lists this build.

## Windows EXE (this PC or another PC)

1. Or build yourself: double-click `build.bat`.
2. Copy the whole folder `dist\SpriteForge\` to the other computer.
3. First start on a new PC opens a setup window. It downloads ComfyUI and the FLUX models (~23 GB, needs an NVIDIA GPU + internet). Downloads resume if they drop.
4. After that the app works offline. Models live in `%LOCALAPPDATA%\SpriteForge\`.

If this PC already has ComfyUI, the setup window offers **Use existing ComfyUI** and skips the download.

First Flux job after a reboot can take a few minutes while the model loads into VRAM. After that, frames are much faster. The bottom bar shows exact image count (`2 / 4`), sampler step (`14 / 20`), percent, and time left. Click **?** for what the engine is doing right now.

Open **Settings → Download / repair engine** to re-run the installer.

## How to get a consistent character

1. Generate the hero until one frame is *the* look.
2. Name it and click **Lock as exact model**.
3. Write every visual fact into the identity box (armor color, visor, cape, weapon hand).
4. Open **Animations**, pick that model, pick Walk / Attack / etc.
5. Keep lock strength on **Tight** unless the pose is barely changing.

## Folders

| Path | What |
|---|---|
| `library/models/` | Locked character cards + reference views |
| `library/outputs/` | One-off sprites and structures |
| `library/frames/` | Animation frames |
| `library/sheets/` | Exported sprite sheets |
| `library/maps/` | Floor / dungeon grids, Flux kits, zip packs |

## Local only

No cloud AI, no API keys. Chat (Forge), Imagine, edits, and T2V/I2V all run on this PC through **ComfyUI + Flux + ffmpeg**. Memory and files stay in `%LOCALAPPDATA%\SpriteForge`.
