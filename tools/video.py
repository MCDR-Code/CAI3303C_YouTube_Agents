"""Video assembly: slides + text-to-speech + captions, put together with ffmpeg.

For each scene: slide image + narration audio -> a short MP4 segment.
Segments are joined, then captions are burned in (and also kept as a
separate .srt file and as a soft subtitle track for YouTube).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from tools import images, tts
from tools.storage import Store

PAD = 0.6  # seconds of silence after each scene


def _ff(args: list[str], cwd: Path | None = None) -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is not installed or not on PATH. See README (winget install ffmpeg).")
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr.strip()[-600:]}")


def _ts(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _chunks(text: str, max_words: int = 9) -> list[str]:
    out = []
    for sent in re.split(r"(?<=[.!?])\s+", text.strip()):
        words = sent.split()
        while words:
            n = max_words if len(words) > max_words + 3 else len(words)
            out.append(" ".join(words[:n]))
            words = words[n:]
    return out


def build_srt(narrations: list[str], durations: list[float]) -> str:
    """Caption timing: each scene's chunks share that scene's measured audio length by character count."""
    lines, t0, idx = [], 0.0, 1
    for text, dur in zip(narrations, durations):
        chunks = _chunks(text)
        total = sum(len(c) for c in chunks) or 1
        t = t0
        for c in chunks:
            d = dur * len(c) / total
            lines.append(f"{idx}\n{_ts(t)} --> {_ts(t + d - 0.05)}\n{c}\n")
            idx += 1
            t += d
        t0 += dur + PAD
    return "\n".join(lines)


def render_episode(cfg, store: Store, ep_id: str) -> Path:
    ep = store.episode(ep_id)
    rev = ep["revision"]
    out = cfg.output_dir / "episodes" / ep_id
    work = out / f"build_r{rev}"
    if work.exists():
        shutil.rmtree(work)
    (work / "slides").mkdir(parents=True)
    scenes = ep["script"]["scenes"]
    art = (ep.get("visuals") or {}).get("images", [])
    channel = cfg["channel"]["name"]
    print(f"   rendering {ep_id} r{rev}: {len(scenes)} scenes")

    # 1) slides
    slides = []
    for i, sc in enumerate(scenes):
        p = work / "slides" / f"slide_{i:02d}.png"
        images.make_slide(cfg, sc, art[i] if i < len(art) else None, i + 1, len(scenes), channel, p)
        slides.append(p)

    # 2) text-to-speech
    narr = [sc["narration"] for sc in scenes]
    wavs, engine = tts.synthesize(cfg, narr, work / "audio")
    durs = [tts.probe_duration(w) for w in wavs]
    if cfg.backends["tts"] == "prune":
        chars = sum(len(t) for t in narr)
        store.add_cost(ep["week"], ep_id, "media", "tts", "gpt-4o-mini-tts", "prune", 0, 0,
                       chars / 1000 * cfg["pricing"]["tts_per_1k_chars"])

    # 3) one segment per scene
    fps = str(cfg["video"]["fps"])
    seg_list = []
    for i, (slide, wav, d) in enumerate(zip(slides, wavs, durs)):
        seg = work / f"seg_{i:02d}.mp4"
        _ff(["-loop", "1", "-framerate", fps, "-i", str(slide), "-i", str(wav),
             "-af", f"apad=pad_dur={PAD}", "-t", f"{d + PAD:.3f}",
             "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-pix_fmt", "yuv420p",
             "-r", fps, "-c:a", "aac", "-ar", "44100", "-ac", "2", str(seg)])
        seg_list.append(seg.name)
    (work / "segments.txt").write_text("".join(f"file '{s}'\n" for s in seg_list), encoding="utf-8")
    _ff(["-f", "concat", "-safe", "0", "-i", "segments.txt", "-c", "copy", "joined.mp4"], cwd=work)

    # 4) captions
    srt = build_srt(narr, durs)
    (work / "captions.srt").write_text(srt, encoding="utf-8")
    final_name = f"{ep_id}_r{rev}.mp4"
    fonts_rel = os.path.relpath(images.FONT.parent, work).replace("\\", "/")
    vf = []
    if cfg["video"]["burn_captions"]:
        style = ("FontName=DejaVu Sans,FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                 "BorderStyle=3,Outline=1,Shadow=0,BackColour=&H99000000,MarginV=42")
        vf = ["-vf", f"subtitles=captions.srt:fontsdir={fonts_rel}:force_style='{style}'"]
    _ff(["-i", "joined.mp4", "-i", "captions.srt", *vf, "-map", "0:v", "-map", "0:a", "-map", "1:0",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "copy", "-c:s", "mov_text",
         "-metadata:s:s:0", "language=eng", final_name], cwd=work)

    final = out / final_name
    shutil.move(str(work / final_name), final)
    shutil.copy(work / "captions.srt", out / f"{ep_id}_r{rev}.srt")
    duration = tts.probe_duration(final)
    store.update_episode(ep_id, video_path=str(final), srt_path=str(out / f"{ep_id}_r{rev}.srt"),
                         duration_sec=duration, status="pending_review")
    store.log("video", f"rendered {final.name} ({duration:.0f}s, voice: {engine})", ep["week"], ep_id)
    print(f"   video ready: {final.name} ({duration:.0f}s, voice: {engine}) -> waiting for professor review")
    return final
