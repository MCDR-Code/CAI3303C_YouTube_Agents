"""Prune gateway: one OpenAI client per agent, each with that agent's own Prune key.

Every LLM call in the system goes through `model_for_agent`. In real mode the
client points at Prune (base_url) with the agent's key; in mock mode a scripted
MockModel stands in, so the full handoff graph runs with no paid service.
"""
from __future__ import annotations

from agents import OpenAIChatCompletionsModel, set_tracing_disabled
from agents.models.interface import Model
from openai import AsyncOpenAI

from .config import Config
from .context import RunState
from .cost_tracking import CostTrackingModel

# The Agents SDK would otherwise try to upload traces to OpenAI directly,
# which bypasses Prune and fails without an OpenAI key.
set_tracing_disabled(True)

_clients: dict[str, AsyncOpenAI] = {}


def prune_client(cfg: Config, key_name: str) -> AsyncOpenAI:
    """Return a cached AsyncOpenAI client for one Prune key (one per agent)."""
    if key_name not in _clients:
        api_key = cfg.prune_key(key_name)
        if not api_key:
            raise RuntimeError(
                f"Missing PRUNE_KEY_{key_name.upper()} in .env. Each agent needs its own Prune key in real mode."
            )
        _clients[key_name] = AsyncOpenAI(base_url=cfg["prune"]["base_url"], api_key=api_key)
    return _clients[key_name]


def model_for_agent(agent_name: str, state: RunState) -> Model:
    cfg = state.cfg
    model_name = cfg["models"][agent_name]
    backend = cfg.backends["llm"]
    if backend == "prune":
        # Chat Completions is the most widely supported API shape on gateways.
        inner: Model = OpenAIChatCompletionsModel(model=model_name, openai_client=prune_client(cfg, agent_name))
    elif backend == "mock":
        from .mock_llm import MockModel

        inner = MockModel(agent_name, state)
    else:
        raise ValueError(f"Unknown llm backend {backend!r}")
    return CostTrackingModel(inner, agent_name, model_name, backend, state)
