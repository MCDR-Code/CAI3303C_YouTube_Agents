"""Text-to-speech, one audio file per scene.

offline : pyttsx3 (Windows SAPI5 voices, free, no internet). On Linux it falls back
          to the espeak-ng command line if pyttsx3 cannot drive it.
prune   : OpenAI-compatible /audio/speech through Prune (real mode, not tested here).
silent  : silence of the right length, so the pipeline still runs without a voice.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def probe_duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                          "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def _silent(text: str, path: Path, wpm: int) -> None:
    secs = max(1.5, len(text.split()) / wpm * 60)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "anullsrc=r=22050:cl=mono", "-t", f"{secs:.2f}", str(path)], check=True)


def _pyttsx3(texts: list[str], paths: list[Path], wpm: int) -> bool:
    try:
        import pyttsx3

        engine = pyttsx3.init()
        engine.setProperty("rate", wpm)
        for t, p in zip(texts, paths):
            engine.save_to_file(t, str(p))
        engine.runAndWait()
        engine.stop()
    except Exception:
        return False
    return all(p.exists() and p.stat().st_size > 1000 for p in paths)


def _espeak(texts: list[str], paths: list[Path], wpm: int) -> bool:
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        return False
    for t, p in zip(texts, paths):
        subprocess.run([exe, "-v", "en-us", "-s", str(wpm), "-w", str(p), t], check=True,
                       capture_output=True)
    return all(p.exists() and p.stat().st_size > 1000 for p in paths)


def _prune(cfg, texts: list[str], paths: list[Path]) -> None:  # pragma: no cover - paid API
    """REAL MODE (not tested in this build)."""
    from openai import OpenAI

    client = OpenAI(base_url=cfg["prune"]["base_url"], api_key=cfg.prune_key("media"))
    for t, p in zip(texts, paths):
        with client.audio.speech.with_streaming_response.create(
                model="gpt-4o-mini-tts", voice="onyx", input=t, response_format="wav") as r:
            r.stream_to_file(p)


def synthesize(cfg, texts: list[str], out_dir: Path) -> tuple[list[Path], str]:
    """Write scene_XX.wav files. Returns (paths, engine_used)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [out_dir / f"scene_{i:02d}.wav" for i in range(len(texts))]
    for p in paths:
        p.unlink(missing_ok=True)
    wpm = cfg["video"]["tts_rate"]
    backend = cfg.backends["tts"]
    if backend == "prune":
        _prune(cfg, texts, paths)
        return paths, "prune"
    if backend == "offline":
        if _pyttsx3(texts, paths, wpm):
            return paths, "pyttsx3"
        if _espeak(texts, paths, wpm):
            return paths, "espeak-ng"
        print("   (no offline voice found; using silent audio)")
    for t, p in zip(texts, paths):
        _silent(t, p, wpm)
    return paths, "silent"
