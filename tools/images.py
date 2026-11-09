"""Images for each episode: scene art, slides and the thumbnail.

Mock: seeded abstract placeholder art made with Pillow, clearly labeled.
Real: image generation through Prune (OpenAI Images API shape).
"""
from __future__ import annotations

import base64
import hashlib
import math
import random
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT = ROOT / "assets" / "fonts" / "DejaVuSans.ttf"
FONT_BOLD = ROOT / "assets" / "fonts" / "DejaVuSans-Bold.ttf"

NAVY = (15, 27, 45)
NAVY_2 = (24, 42, 68)
TEAL = (43, 179, 163)
AMBER = (242, 165, 65)
WHITE = (245, 247, 250)
GREY = (160, 172, 189)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT), size)


def _rng(text: str) -> random.Random:
    return random.Random(int(hashlib.md5(text.encode()).hexdigest()[:8], 16))


def placeholder_art(prompt: str, size: tuple[int, int], label: bool = True) -> Image.Image:
    """Abstract 'neural network' style art seeded by the prompt, so each scene looks different."""
    w, h = size
    rng = _rng(prompt)
    img = Image.new("RGB", size, NAVY_2)
    d = ImageDraw.Draw(img)
    c1 = rng.choice([TEAL, AMBER, (99, 132, 230), (200, 90, 140)])
    c2 = rng.choice([TEAL, AMBER, (99, 132, 230), (120, 200, 120)])
    for y in range(h):                                   # vertical gradient
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(NAVY_2[i] * (1 - t) + c1[i] * 0.35 * t) for i in range(3)))
    layers = rng.randint(3, 5)
    nodes = []
    for li in range(layers):
        x = int(w * (0.15 + 0.7 * li / (layers - 1)))
        n = rng.randint(3, 6)
        nodes.append([(x, int(h * (0.18 + 0.64 * (k + 0.5) / n))) for k in range(n)])
    for a, b in zip(nodes, nodes[1:]):
        for p in a:
            for q in b:
                if rng.random() < 0.7:
                    d.line([p, q], fill=tuple(int(v * 0.55) for v in c2), width=2)
    for layer in nodes:
        for (x, y) in layer:
            r = rng.randint(10, 18)
            d.ellipse([x - r, y - r, x + r, y + r], fill=c1, outline=WHITE, width=2)
    img = img.filter(ImageFilter.SMOOTH)
    if label:
        d = ImageDraw.Draw(img)
        d.rectangle([0, h - 54, w, h], fill=(0, 0, 0))
        d.text((12, h - 50), "PLACEHOLDER IMAGE (mock mode)", font=font(14, True), fill=AMBER)
        d.text((12, h - 30), textwrap.shorten(prompt, 80), font=font(13), fill=GREY)
    return img


def _real_image(cfg, prompt: str, path: Path) -> None:  # pragma: no cover - paid API
    """REAL MODE (not tested in this build): generate an image through Prune."""
    from openai import OpenAI

    from agents_system.cost_tracking import price_tokens  # noqa: F401

    client = OpenAI(base_url=cfg["prune"]["base_url"], api_key=cfg.prune_key("media"))
    res = client.images.generate(model="gpt-image-1", prompt=prompt, size="1024x1024")
    path.write_bytes(base64.b64decode(res.data[0].b64_json))


def render_episode_images(cfg, episode: dict, thumbnail: dict, scenes: list[dict], out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "art").mkdir(exist_ok=True)
    scene_paths = []
    for v in scenes:
        p = out_dir / "art" / f"scene_{v['scene_index']:02d}.png"
        if cfg.backends["images"] == "mock":
            placeholder_art(v["image_prompt"], (640, 480)).save(p)
        else:
            _real_image(cfg, v["image_prompt"], p)
            _charge_image(cfg, episode)
        scene_paths.append(str(p))
    thumb = out_dir / "thumbnail.png"
    make_thumbnail(cfg, thumbnail, thumb)
    return {"scenes": scene_paths, "thumbnail": str(thumb)}


def _charge_image(cfg, episode: dict) -> None:
    from tools.storage import Store

    Store(cfg.path("db_path")).add_cost(episode["week"], episode["id"], "media", "image", "gpt-image-1",
                                        "prune", 0, 0, cfg["pricing"]["image_each"])


def _outlined(d: ImageDraw.ImageDraw, xy, text, fnt, fill, outline=(0, 0, 0), width=4):
    x, y = xy
    for dx in range(-width, width + 1, 2):
        for dy in range(-width, width + 1, 2):
            d.text((x + dx, y + dy), text, font=fnt, fill=outline)
    d.text(xy, text, font=fnt, fill=fill)


def make_thumbnail(cfg, thumbnail: dict, path: Path) -> None:
    W, H = 1280, 720
    img = Image.new("RGB", (W, H), NAVY)
    art = placeholder_art(thumbnail["image_prompt"], (620, 720), label=False)
    mask = Image.new("L", art.size, 255)
    md = ImageDraw.Draw(mask)
    for x in range(200):                      # fade the art into the background
        md.line([(x, 0), (x, art.size[1])], fill=int(255 * x / 200))
    img.paste(art, (W - 620, 0), mask)
    d = ImageDraw.Draw(img)
    words = thumbnail["text"].upper().split()
    lines = textwrap.wrap(" ".join(words), 12) or [""]
    size = 120 if len(lines) <= 2 else 92
    y = H // 2 - len(lines) * size // 2 - 20
    for i, line in enumerate(lines):
        _outlined(d, (60, y), line, font(size, True), AMBER if i == len(lines) - 1 else WHITE)
        y += size + 10
    d.rectangle([60, H - 110, 60 + 330, H - 62], fill=TEAL)
    d.text((76, H - 104), "PROFESSOR EXPLAINS", font=font(26, True), fill=NAVY)
    if cfg.backends["images"] == "mock":
        d.text((W - 300, H - 32), "PLACEHOLDER THUMBNAIL", font=font(16, True), fill=GREY)
    img.save(path)


def make_slide(cfg, scene: dict, art_path: str | None, index: int, total: int, channel: str,
               path: Path) -> None:
    """One 1280x720 slide per scene: heading, on-screen text, scene art, channel bar."""
    W, H = cfg["video"]["width"], cfg["video"]["height"]
    img = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 8], fill=TEAL)
    if art_path and Path(art_path).exists():
        art = Image.open(art_path).convert("RGB").resize((560, 420))
        img.paste(art, (W - 560 - 50, 110))
    d.text((60, 70), f"{index}/{total}", font=font(22, True), fill=TEAL)
    y = 110
    for line in textwrap.wrap(scene["heading"], 22)[:3]:
        d.text((60, y), line, font=font(50, True), fill=WHITE)
        y += 62
    y += 24
    d.rectangle([60, y, 66, y + 110], fill=AMBER)
    yy = y + 4
    for line in textwrap.wrap(scene["on_screen_text"], 26)[:3]:
        d.text((84, yy), line, font=font(34), fill=AMBER)
        yy += 44
    # bottom bar (captions will sit above it)
    d.rectangle([0, H - 44, W, H], fill=(8, 15, 26))
    d.text((24, H - 34), channel, font=font(20, True), fill=GREY)
    img.save(path)
