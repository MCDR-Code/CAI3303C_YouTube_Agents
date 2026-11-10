"""Builds docs/screenshots/00_terminal_simulation.png and docs/storyboard/* from a real run.

    python docs/build_docs_images.py [episode_id]

Needs a finished simulation (python main.py simulate --weeks 2 --fresh).
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from agents_system.config import load_config  # noqa: E402
from tools.images import FONT, FONT_BOLD, wrap_px  # noqa: E402
from tools.storage import Store, abspath  # noqa: E402
from tools.tts import probe_duration  # noqa: E402

MONO = Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
if not MONO.exists():
    MONO = Path("C:/Windows/Fonts/consola.ttf")


def terminal_png(log: Path, out: Path, first: int = 0, n: int = 64) -> None:
    lines = log.read_text(encoding="utf-8").splitlines()[first:first + n]
    f = ImageFont.truetype(str(MONO), 17)
    W, lh = 1500, 24
    H = 60 + lh * len(lines) + 24
    img = Image.new("RGB", (W, H), (18, 20, 26))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 36], fill=(40, 43, 52))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([16 + i * 24, 11, 30 + i * 24, 25], fill=c)
    d.text((110, 9), "python main.py simulate --weeks 2 --fresh", font=f, fill=(190, 195, 205))
    y = 52
    for line in lines:
        color = (215, 220, 228)
        if line.startswith("=="):
            color = (242, 165, 65)
        elif "SIMULATED professor" in line:
            color = (255, 214, 120)
        elif "agents used" in line:
            color = (43, 179, 163)
        elif "issue(s)" in line or "REFUSED" in line:
            color = (255, 120, 120)
        elif "PASSED" in line or "'ok': True" in line:
            color = (120, 220, 140)
        d.text((20, y), line[:150], font=f, fill=color)
        y += lh
    img.save(out)


def storyboard(cfg, store: Store, ep_id: str, out_dir: Path) -> list[Path]:
    ep = store.episode(ep_id)
    rev = ep["revision"]
    build = cfg.output_dir / "episodes" / ep_id / f"build_r{rev}"
    scenes = ep["script"]["scenes"]
    durs = [probe_duration(build / "audio" / f"scene_{i:02d}.wav") + 0.6 for i in range(len(scenes))]
    fw, fh = 560, 315
    cols = 2
    cell_w, cell_h = fw + 520, fh + 40
    rows = (len(scenes) + cols - 1) // cols
    W, H = cols * cell_w + 60, 190 + rows * cell_h + 40
    img = Image.new("RGB", (W, H), (250, 250, 248))
    d = ImageDraw.Draw(img)
    fb, f, fs = ImageFont.truetype(str(FONT_BOLD), 34), ImageFont.truetype(str(FONT), 19), ImageFont.truetype(str(FONT), 16)
    fsb = ImageFont.truetype(str(FONT_BOLD), 18)
    title = ep["metadata"]["titles"][0]
    d.text((30, 26), f"Storyboard: {ep_id} (revision {rev})  \u2014  {title}", font=fb, fill=(15, 27, 45))
    decisions = store.q("SELECT revision, decision, notes, decided_by FROM decisions WHERE episode_id=? ORDER BY id",
                        (ep_id,))
    hist = "   ".join(f"r{r[0]}: {r[1]}" + (f' ("{r[2]}")' if r[2] and r[1] != "approved" else "")
                      for r in decisions)
    d.text((30, 78), f"{len(scenes)} scenes, {sum(durs):.0f} s. Review history: {hist}", font=f, fill=(82, 81, 78))
    d.text((30, 108), "Frames are the real rendered slides (placeholder art in mock mode). "
                      "Times come from the measured voice track.", font=fs, fill=(137, 135, 129))
    t = 0.0
    for i, sc in enumerate(scenes):
        r, c = divmod(i, cols)
        x, y = 30 + c * cell_w, 160 + r * cell_h
        frame = Image.open(build / "slides" / f"slide_{i:02d}.png").convert("RGB").resize((fw, fh))
        img.paste(frame, (x, y))
        d.rectangle([x, y, x + fw, y + fh], outline=(195, 194, 183), width=2)
        tx = x + fw + 20
        d.text((tx, y), f"Scene {i + 1}  \u00b7  {int(t // 60)}:{int(t % 60):02d}\u2013"
                        f"{int((t + durs[i]) // 60)}:{int((t + durs[i]) % 60):02d}", font=fsb, fill=(43, 140, 128))
        hf = ImageFont.truetype(str(FONT_BOLD), 21)
        yy = y + 28
        for line in wrap_px(sc["heading"], hf, 470)[:2]:
            d.text((tx, yy), line, font=hf, fill=(15, 27, 45))
            yy += 27
        yy += 6
        d.text((tx, yy), "VOICE:", font=fsb, fill=(82, 81, 78))
        yy += 24
        for line in wrap_px(sc["narration"], fs, 470)[:7]:
            d.text((tx, yy), line, font=fs, fill=(30, 30, 30))
            yy += 21
        yy += 6
        for line in wrap_px(f"ON SCREEN: {sc['on_screen_text']}", fs, 470)[:2]:
            d.text((tx, yy), line, font=fs, fill=(160, 100, 10))
            yy += 21
        yy -= 21
        if sc.get("professor_note"):
            yy += 26
            for line in wrap_px("PROFESSOR: " + sc["professor_note"], fs, 470)[:2]:
                d.text((tx, yy), line, font=fs, fill=(150, 40, 40))
                yy += 21
        t += durs[i]
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / f"storyboard_{ep_id}_r{rev}.png"
    pdf = out_dir / f"storyboard_{ep_id}_r{rev}.pdf"
    img.save(png)
    img.save(pdf, "PDF", resolution=150)
    thumb = Image.open(abspath(ep["thumbnail_path"]))
    thumb.save(out_dir / f"thumbnail_{ep_id}.png")
    return [png, pdf]


if __name__ == "__main__":
    cfg = load_config()
    store = Store(cfg.path("db_path"))
    docs = ROOT / "docs"
    log = docs / "simulation_log.txt"
    if log.exists():
        terminal_png(log, docs / "screenshots" / "00_terminal_week1.png", 0, 62)
    ep_id = sys.argv[1] if len(sys.argv) > 1 else "W01E02"
    for p in storyboard(cfg, store, ep_id, docs / "storyboard"):
        print(p)
