"""Wraps any SDK Model so every call is priced and written to the cost ledger.

Each agent gets its own wrapped model, so cost is recorded per agent and per
episode. A local weekly budget per agent is checked before each call; Prune's
per-key spend cap is the hard limit on the gateway side.
"""
from __future__ import annotations

from typing import Any, AsyncIterator

from agents.models.interface import Model

from .config import Config
from .context import RunState


class BudgetExceeded(RuntimeError):
    pass


def price_tokens(cfg: Config, model: str, input_tokens: int, output_tokens: int) -> float:
    p = cfg["pricing"].get(model)
    if not p:
        return 0.0
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000


class CostTrackingModel(Model):
    def __init__(self, inner: Model, agent_name: str, model_name: str, backend: str, state: RunState):
        self.inner = inner
        self.agent_name = agent_name
        self.model_name = model_name
        self.backend = backend
        self.state = state

    def _check_budget(self) -> None:
        cap = self.state.cfg["budgets_weekly_usd"].get(self.agent_name)
        spent = self.state.store.agent_spend(self.agent_name, self.state.week)
        if cap is not None and spent >= cap:
            raise BudgetExceeded(
                f"{self.agent_name} spent ${spent:.4f} of its ${cap:.2f} weekly budget; stopping this run."
            )

    def _record(self, response: Any) -> None:
        u = response.usage
        cost = None
        # Prune returns a signed receipt with the real cost; use it when present.
        receipt = getattr(response, "prune_metadata", None) or (response.raw_usage or {}).get("prune_metadata")
        if isinstance(receipt, dict):
            cost = receipt.get("cost_with_prune_usd")
        if cost is None:
            cost = price_tokens(self.state.cfg, self.model_name, u.input_tokens, u.output_tokens)
        self.state.store.add_cost(
            week=self.state.week,
            episode_id=self.state.episode_id,
            agent=self.agent_name,
            kind="chat",
            model=self.model_name,
            backend=self.backend,
            input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            cost_usd=float(cost),
        )

    async def get_response(self, *args: Any, **kwargs: Any):
        self._check_budget()
        response = await self.inner.get_response(*args, **kwargs)
        self._record(response)
        return response

    def stream_response(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        # Streaming is not used by this system; delegate without pricing.
        return self.inner.stream_response(*args, **kwargs)
