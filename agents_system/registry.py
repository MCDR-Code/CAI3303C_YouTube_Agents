"""Builds the nine agents from prompts/*.txt and wires the Swarm-style handoffs.

Handoff graph:
    producer -> trend_researcher -> topic_strategist                 (plan stage)
    producer -> scriptwriter <-> fact_checker -> seo_metadata
                                              -> visual_designer      (produce / revise)
    producer -> analytics -> business_manager                         (end-of-week review)
"""
from __future__ import annotations

from pathlib import Path

from agents import Agent
from agents.extensions.handoff_prompt import prompt_with_handoff_instructions

from . import agent_tools as T
from .config import AGENT_NAMES
from .context import RunState
from .gateway import model_for_agent

HANDOFFS = {
    "producer": ["trend_researcher", "scriptwriter", "analytics"],
    "trend_researcher": ["topic_strategist"],
    "topic_strategist": [],
    "scriptwriter": ["fact_checker"],
    "fact_checker": ["scriptwriter", "seo_metadata"],
    "seo_metadata": ["visual_designer"],
    "visual_designer": [],
    "analytics": ["business_manager"],
    "business_manager": [],
}

TOOLS = {
    "producer": T.PRODUCER_TOOLS,
    "trend_researcher": T.RESEARCH_TOOLS,
    "topic_strategist": T.STRATEGIST_TOOLS,
    "scriptwriter": T.SCRIPT_TOOLS,
    "fact_checker": T.FACTCHECK_TOOLS,
    "seo_metadata": T.SEO_TOOLS,
    "visual_designer": T.VISUAL_TOOLS,
    "analytics": T.ANALYTICS_TOOLS,
    "business_manager": T.MANAGER_TOOLS,
}

DESCRIPTIONS = {
    "producer": "Coordinates the weekly cycle and routes work to the right specialist.",
    "trend_researcher": "Finds AI/tech topics with high search demand and low competition.",
    "topic_strategist": "Chooses this week's videos and writes one brief per video.",
    "scriptwriter": "Writes or revises the video script in the professor's teaching voice.",
    "fact_checker": "Checks every technical claim in the script; sends it back if something is wrong.",
    "seo_metadata": "Writes titles, description, tags, chapters and pinned comment.",
    "visual_designer": "Designs the thumbnail and one visual per scene.",
    "analytics": "Reads channel stats and explains what worked.",
    "business_manager": "Computes profit per video and plans next week to maximize profit.",
}


def load_prompt(state: RunState, name: str) -> str:
    path = Path(state.cfg.path("prompts_dir")) / f"{name}.txt"
    text = path.read_text(encoding="utf-8")
    ch = state.cfg["channel"]
    for key, val in {"CHANNEL_NAME": ch["name"], "HOST": ch["host"], "NICHE": ch["niche"],
                     "VIDEOS_PER_WEEK": str(ch["videos_per_week"])}.items():
        text = text.replace("{{" + key + "}}", val)
    return text


def build_agents(state: RunState) -> dict[str, Agent]:
    """Fresh agents for one run (models are per-run so cost is tagged to the right episode)."""
    agents: dict[str, Agent] = {}
    for name in AGENT_NAMES:
        agents[name] = Agent(
            name=name,
            handoff_description=DESCRIPTIONS[name],
            instructions=prompt_with_handoff_instructions(load_prompt(state, name)),
            model=model_for_agent(name, state),
            tools=list(TOOLS[name]),
        )
    for name, targets in HANDOFFS.items():
        agents[name].handoffs = [agents[t] for t in targets]
    return agents
