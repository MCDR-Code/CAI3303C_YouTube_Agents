"""Loads config.yaml and .env, and resolves which backend each service uses."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

AGENT_NAMES = [
    "producer",
    "trend_researcher",
    "topic_strategist",
    "scriptwriter",
    "fact_checker",
    "seo_metadata",
    "visual_designer",
    "analytics",
    "business_manager",
]

_AUTO = {
    "mock": {"llm": "mock", "channel_stats": "mock", "images": "mock", "tts": "offline", "upload": "mock"},
    "real": {"llm": "prune", "channel_stats": "youtube", "images": "prune", "tts": "prune", "upload": "youtube"},
}


@dataclass
class Config:
    raw: dict[str, Any]
    root: Path = ROOT
    backends: dict[str, str] = field(default_factory=dict)

    @property
    def mode(self) -> str:
        return self.raw["mode"]

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)

    def path(self, key: str) -> Path:
        p = Path(self.raw["paths"][key])
        return p if p.is_absolute() else self.root / p

    @property
    def output_dir(self) -> Path:
        return self.path("output_dir")

    def prune_key(self, name: str) -> str | None:
        return os.getenv(f"PRUNE_KEY_{name.upper()}") or None


def load_config(path: str | Path | None = None, overrides: dict[str, Any] | None = None) -> Config:
    load_dotenv(ROOT / ".env")
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    with open(cfg_path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if overrides:
        for k, v in overrides.items():
            raw[k] = v
    mode = raw.get("mode", "mock")
    if mode not in _AUTO:
        raise ValueError(f"mode must be 'mock' or 'real', got {mode!r}")
    backends = {}
    for svc, choice in (raw.get("backends") or {}).items():
        backends[svc] = _AUTO[mode][svc] if choice in (None, "auto") else choice
    for svc, default in _AUTO[mode].items():
        backends.setdefault(svc, default)
    privacy = raw.get("channel", {}).get("upload_privacy", "private")
    if privacy != "private":
        raise ValueError("channel.upload_privacy must be 'private'. The professor publishes in YouTube Studio.")
    cfg = Config(raw=raw, backends=backends)
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    cfg.path("db_path").parent.mkdir(parents=True, exist_ok=True)
    return cfg
