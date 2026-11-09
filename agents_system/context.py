"""Shared state that travels with every agent run and every handoff.

The OpenAI Agents SDK passes this object to every tool through
RunContextWrapper, so all agents in one run see the same episode, week,
database and config. It is never sent to the LLM itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import Config
from tools.storage import Store


@dataclass
class RunState:
    cfg: Config
    store: Store
    week: int
    stage: str                       # plan | produce | revise | review_week
    episode_id: str | None = None
    notes: str = ""                  # professor's change request, when revising
    scratch: dict[str, Any] = field(default_factory=dict)   # per-run working memory
    trace: list[str] = field(default_factory=list)          # which agent did what (for logs/diagrams)

    def say(self, actor: str, msg: str) -> None:
        line = f"[{actor}] {msg}"
        self.trace.append(line)
        self.store.log(actor, msg, self.week, self.episode_id)
        print("   " + line)
