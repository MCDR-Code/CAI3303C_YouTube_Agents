"""The weekly loop. Each stage starts one agent run at the Producer.

    plan_week        Producer -> Trend Researcher -> Topic Strategist
    produce_episode  Producer -> Scriptwriter <-> Fact-Checker -> SEO -> Visual Designer,
                     then the video is rendered (TTS + captions + ffmpeg) and waits for review
    (professor)      approves / requests changes / rejects on the review page
    revise           changes requested -> back through the production chain
    publish          approved videos are uploaded as PRIVATE (the gate re-checks approval)
    close_week       stats -> Producer -> Analytics -> Business Manager, then the weekly report
"""
from __future__ import annotations

import asyncio
import copy
from datetime import date, timedelta

from agents import Runner

from .config import Config
from .context import RunState
from .registry import build_agents
from tools.storage import Store

MAX_TURNS = 40


def _state(cfg: Config, store: Store, week: int, stage: str, episode_id: str | None = None,
           notes: str = "") -> RunState:
    # Apply the manager's budget changes for this week on top of config.yaml.
    eff = copy.copy(cfg)
    eff.raw = copy.deepcopy(cfg.raw)
    plan = store.week_json(week, "plan_json") or {}
    for bc in plan.get("budget_changes", []):
        if bc["agent"] in eff.raw["budgets_weekly_usd"]:
            base = cfg["budgets_weekly_usd"][bc["agent"]]
            eff.raw["budgets_weekly_usd"][bc["agent"]] = min(bc["weekly_usd"], base * 2)  # guard rail
    return RunState(cfg=eff, store=store, week=week, stage=stage, episode_id=episode_id, notes=notes)


def _run(state: RunState, message: str) -> str:
    agents = build_agents(state)
    result = asyncio.run(Runner.run(agents["producer"], message, context=state, max_turns=MAX_TURNS))
    chain = " -> ".join(dict.fromkeys(_agent_path(result)))
    state.store.log("pipeline", f"{state.stage} run finished; agents: {chain}", state.week, state.episode_id)
    print(f"   agents used: {chain}")
    return str(result.final_output)


def _agent_path(result) -> list[str]:
    names = ["producer"]
    for item in result.new_items:
        if item.type == "handoff_output_item":
            names.append(item.target_agent.name)
    return names


def week_start(cfg: Config, week: int) -> str:
    d0 = date.fromisoformat(cfg["simulation"]["start_date"])
    return (d0 + timedelta(days=7 * (week - 1))).isoformat()


def plan_week(cfg: Config, store: Store, week: int) -> list[str]:
    store.ensure_week(week, week_start(cfg, week))
    print(f"\n== Week {week}: planning ==")
    _run(_state(cfg, store, week, "plan"), f"Plan the videos for week {week}.")
    return [e["id"] for e in store.episodes(week=week)]


def produce_episode(cfg: Config, store: Store, ep_id: str, render: bool = True) -> None:
    ep = store.episode(ep_id)
    print(f"\n== {ep_id}: production ({ep['topic']}) ==")
    _run(_state(cfg, store, ep["week"], "produce", ep_id), f"Produce episode {ep_id}.")
    if render:
        from tools.video import render_episode

        render_episode(cfg, store, ep_id)


def revise_episode(cfg: Config, store: Store, ep_id: str, render: bool = True) -> None:
    ep = store.episode(ep_id)
    notes = ep.get("review_notes") or ""
    print(f"\n== {ep_id}: revision {ep['revision'] + 1} (professor notes: {notes!r}) ==")
    fc = ep.get("factcheck") or {}
    store.update_episode(ep_id, revision=ep["revision"] + 1,
                         factcheck={"rounds": [], "earlier_rounds": fc.get("rounds", [])})
    _run(_state(cfg, store, ep["week"], "revise", ep_id, notes),
         f"Revise episode {ep_id}. Professor's notes: {notes}")
    if render:
        from tools.video import render_episode

        render_episode(cfg, store, ep_id)


def publish_approved(cfg: Config, store: Store, sim_day: int | None = None) -> list[str]:
    from tools.youtube_upload import upload

    done = []
    for ep in store.episodes(status="approved"):
        res = upload(cfg, store, ep["id"], sim_day=sim_day)
        print(f"   upload {ep['id']}: {res}")
        if res.get("ok"):
            done.append(ep["id"])
    return done


def close_week(cfg: Config, store: Store, week: int, last_sim_day: int | None = None) -> str:
    from reports.weekly import write_weekly_report
    from tools import channel_stats

    print(f"\n== Week {week}: analytics, profit report and next-week plan ==")
    if cfg.backends["channel_stats"] == "mock":
        day = last_sim_day if last_sim_day is not None else week * cfg["simulation"]["days_per_week"] - 1
        n = channel_stats.simulate_until(store, cfg, day)
        print(f"   simulated {n} video-days of stats (through sim day {day})")
    else:
        channel_stats.fetch_real(store, cfg)
    _run(_state(cfg, store, week, "review_week"), f"Review week {week} and plan week {week + 1}.")
    path = write_weekly_report(cfg, store, week)
    print(f"   weekly report: {path}")
    return str(path)
