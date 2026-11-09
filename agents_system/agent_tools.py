"""Function tools the agents call. Every tool reads or writes the shared RunState.

Agents never touch the database or files directly; they go through these
tools, which validate input and keep the cost ledger and audit log complete.
"""
from __future__ import annotations

import json
from agents import RunContextWrapper, function_tool
from pydantic import BaseModel, Field

from .context import RunState
from tools import channel_stats, images, trends

Ctx = RunContextWrapper[RunState]
MAX_FACTCHECK_ROUNDS = 2


# ----------------------------------------------------------------------
# Schemas (the LLM fills these in)
# ----------------------------------------------------------------------
class TopicFinding(BaseModel):
    topic_id: str
    topic: str
    category: str
    search_demand: float = Field(description="0-1, how much people are searching for this")
    competition: float = Field(description="0-1, how crowded the topic is on YouTube")
    why_now: str


class Brief(BaseModel):
    topic_id: str
    topic: str
    category: str
    audience: str
    angle: str = Field(description="The professor's unique angle on the topic")
    key_points: list[str]
    target_minutes: float


class Scene(BaseModel):
    heading: str
    narration: str = Field(description="Exactly what the professor's voice says")
    on_screen_text: str = Field(description="Short text shown on the slide, max 8 words")
    professor_note: str = Field("", description="Where the professor should add his own example; empty if none")


class Issue(BaseModel):
    scene_index: int
    claim: str
    problem: str
    suggested_fix: str


class Chapter(BaseModel):
    timestamp: str
    title: str


class SceneVisual(BaseModel):
    scene_index: int
    image_prompt: str
    layout: str = Field(description="title | split | full_image | list")


class Thumbnail(BaseModel):
    text: str = Field(description="Max 4 words")
    concept: str
    image_prompt: str


class BudgetChange(BaseModel):
    agent: str
    weekly_usd: float


class WeekPlan(BaseModel):
    videos_next_week: int
    favor_categories: list[str]
    avoid_categories: list[str]
    title_guidance: str
    budget_changes: list[BudgetChange]
    summary: str
    rationale: str


# ----------------------------------------------------------------------
# Producer
# ----------------------------------------------------------------------
@function_tool
def get_week_status(ctx: Ctx) -> str:
    """Return the current week, stage, and episode the Producer must coordinate."""
    s = ctx.context
    data = {"week": s.week, "stage": s.stage, "episode_id": s.episode_id, "professor_notes": s.notes or None,
            "videos_per_week": s.cfg["channel"]["videos_per_week"]}
    s.say("producer", f"Week {s.week}, stage '{s.stage}'" + (f", episode {s.episode_id}" if s.episode_id else ""))
    return json.dumps(data)


# ----------------------------------------------------------------------
# Trend researcher
# ----------------------------------------------------------------------
@function_tool
def search_trends(ctx: Ctx, query: str) -> str:
    """Search what AI/tech topics people are looking for right now. Returns demand and competition scores."""
    s = ctx.context
    rows = trends.search(s.cfg, s.week, query)
    s.say("trend_researcher", f"search_trends('{query}') -> {len(rows)} topics ({s.cfg.backends['channel_stats']} data)")
    return json.dumps(rows)


@function_tool
def save_research(ctx: Ctx, findings: list[TopicFinding]) -> str:
    """Save the shortlist of promising topics for the Topic Strategist."""
    s = ctx.context
    s.store.set_week_json(s.week, "research_json", [f.model_dump() for f in findings])
    s.say("trend_researcher", f"saved {len(findings)} topic findings")
    return "saved"


# ----------------------------------------------------------------------
# Topic strategist
# ----------------------------------------------------------------------
@function_tool
def get_research(ctx: Ctx) -> str:
    """Read this week's topic research."""
    return json.dumps(ctx.context.store.week_json(ctx.context.week, "research_json") or [])


@function_tool
def get_manager_plan(ctx: Ctx) -> str:
    """Read the Business Manager's plan for this week (written at the end of last week). Empty in week 1."""
    s = ctx.context
    return json.dumps(s.store.week_json(s.week, "plan_json") or {})


@function_tool
def get_past_performance(ctx: Ctx) -> str:
    """Per-category results so far: videos, views, revenue, AI cost, profit. Also lists topics already used."""
    s = ctx.context
    from reports.profit import category_summary, used_topics

    return json.dumps({"by_category": category_summary(s.store), "topics_already_used": used_topics(s.store)})


@function_tool
def save_briefs(ctx: Ctx, briefs: list[Brief]) -> str:
    """Save one brief per video for this week. Creates the episodes."""
    s = ctx.context
    used = set()
    for r in s.store.q("SELECT topic_id FROM episodes WHERE status != 'rejected'"):
        used.add(r[0])
    created = []
    slot = 1 + (s.store.one("SELECT COUNT(*) FROM episodes WHERE week=?", (s.week,))[0])
    for b in briefs:
        if b.topic_id in used:
            continue
        ep_id = f"W{s.week:02d}E{slot:02d}"
        s.store.create_episode(ep_id, s.week, slot, b.model_dump())
        created.append(ep_id)
        slot += 1
    s.say("topic_strategist", f"created episodes {', '.join(created) or '(none)'}")
    return json.dumps({"created": created})


# ----------------------------------------------------------------------
# Scriptwriter
# ----------------------------------------------------------------------
@function_tool
def get_episode_brief(ctx: Ctx) -> str:
    """Brief for the current episode, plus the previous draft, fact-check issues and professor notes if any."""
    s = ctx.context
    ep = s.store.episode(s.episode_id)
    return json.dumps({
        "episode_id": ep["id"], "brief": ep["brief"], "previous_script": ep["script"],
        "fact_check": ep["factcheck"], "professor_notes": s.notes or ep.get("review_notes"),
        "host": s.cfg["channel"]["host"], "channel": s.cfg["channel"]["name"],
    })


@function_tool
def save_script(ctx: Ctx, working_title: str, scenes: list[Scene]) -> str:
    """Save a full script draft as a list of scenes."""
    s = ctx.context
    ep = s.store.episode(s.episode_id)
    prev = ep["script"] or {}
    draft = (prev.get("draft") or 0) + 1
    words = sum(len(sc.narration.split()) for sc in scenes)
    s.store.update_episode(s.episode_id, script={
        "working_title": working_title, "draft": draft, "word_count": words,
        "scenes": [sc.model_dump() for sc in scenes]}, status="scripted")
    s.say("scriptwriter", f"saved draft {draft}: {len(scenes)} scenes, {words} words")
    return f"draft {draft} saved"


# ----------------------------------------------------------------------
# Fact checker
# ----------------------------------------------------------------------
@function_tool
def get_script(ctx: Ctx) -> str:
    """Read the current script draft for this episode."""
    ep = ctx.context.store.episode(ctx.context.episode_id)
    return json.dumps({"brief": ep["brief"], "script": ep["script"]})


@function_tool
def save_fact_check(ctx: Ctx, passed: bool, issues: list[Issue]) -> str:
    """Record the fact-check result. If issues are found, hand back to the Scriptwriter; if passed, to SEO."""
    s = ctx.context
    ep = s.store.episode(s.episode_id)
    hist = ep["factcheck"] or {"rounds": []}
    hist["rounds"].append({"draft": ep["script"]["draft"], "passed": passed,
                           "issues": [i.model_dump() for i in issues]})
    hist["passed"] = passed
    s.store.update_episode(s.episode_id, factcheck=hist)
    s.say("fact_checker", f"draft {ep['script']['draft']}: " + ("PASSED" if passed else f"{len(issues)} issue(s)"))
    if not passed and len(hist["rounds"]) >= MAX_FACTCHECK_ROUNDS:
        return ("Revision limit reached. Do not send back again: hand off to seo_metadata. "
                "The open issues are shown to the professor at review.")
    return "recorded"


# ----------------------------------------------------------------------
# SEO / metadata
# ----------------------------------------------------------------------
@function_tool
def get_channel_insights(ctx: Ctx) -> str:
    """Latest Analytics findings (what titles and topics worked) and the manager's title guidance."""
    s = ctx.context
    prev = s.store.week_json(s.week - 1, "insights_json") if s.week > 1 else None
    plan = s.store.week_json(s.week, "plan_json") or {}
    return json.dumps({"insights": prev or {}, "title_guidance": plan.get("title_guidance", "")})


@function_tool
def save_metadata(ctx: Ctx, titles: list[str], description: str, tags: list[str],
                  chapters: list[Chapter], pinned_comment: str) -> str:
    """Save title options (best first), description, tags, chapters and the pinned comment."""
    s = ctx.context
    s.store.update_episode(s.episode_id, metadata={
        "titles": titles, "description": description, "tags": tags,
        "chapters": [c.model_dump() for c in chapters], "pinned_comment": pinned_comment})
    s.say("seo_metadata", f"title: \"{titles[0]}\" (+{len(titles) - 1} options), {len(tags)} tags")
    return "saved"


# ----------------------------------------------------------------------
# Visual designer
# ----------------------------------------------------------------------
@function_tool
def save_visuals(ctx: Ctx, thumbnail: Thumbnail, scenes: list[SceneVisual]) -> str:
    """Save the thumbnail concept and one visual per scene. Images are generated (placeholders in mock mode)."""
    s = ctx.context
    ep = s.store.episode(s.episode_id)
    out = s.cfg.output_dir / "episodes" / s.episode_id
    paths = images.render_episode_images(s.cfg, ep, thumbnail.model_dump(), [v.model_dump() for v in scenes], out)
    s.store.update_episode(s.episode_id, visuals={
        "thumbnail": thumbnail.model_dump(), "scenes": [v.model_dump() for v in scenes],
        "images": paths["scenes"]}, thumbnail_path=paths["thumbnail"], status="packaged")
    s.say("visual_designer", f"thumbnail '{thumbnail.text}' + {len(scenes)} scene images ({s.cfg.backends['images']})")
    return "saved"


# ----------------------------------------------------------------------
# Analytics
# ----------------------------------------------------------------------
@function_tool
def get_channel_stats(ctx: Ctx) -> str:
    """Per-video stats to date: views, CTR, watch time, average view %, subscribers, revenue."""
    s = ctx.context
    rows = channel_stats.per_video_totals(s.store)
    s.say("analytics", f"read stats for {len(rows)} published videos ({s.cfg.backends['channel_stats']} data)")
    return json.dumps(rows)


@function_tool
def save_insights(ctx: Ctx, summary: str, findings: list[str], best_category: str,
                  title_pattern: str) -> str:
    """Save this week's analytics findings for the Business Manager and next week's SEO agent."""
    s = ctx.context
    s.store.set_week_json(s.week, "insights_json", {
        "summary": summary, "findings": findings, "best_category": best_category, "title_pattern": title_pattern})
    s.say("analytics", f"insights saved (best category: {best_category})")
    return "saved"


# ----------------------------------------------------------------------
# Business manager
# ----------------------------------------------------------------------
@function_tool
def get_profit_report(ctx: Ctx) -> str:
    """Profit per video (revenue minus AI cost from Prune), cost per agent, and analytics insights."""
    s = ctx.context
    from reports.profit import agent_costs, profit_per_video

    return json.dumps({
        "videos": profit_per_video(s.store),
        "cost_per_agent_this_week": agent_costs(s.store, s.week),
        "insights": s.store.week_json(s.week, "insights_json"),
        "current_budgets": s.cfg["budgets_weekly_usd"],
    })


@function_tool
def save_next_week_plan(ctx: Ctx, plan: WeekPlan) -> str:
    """Save the plan for next week. The Topic Strategist and SEO agent read it."""
    s = ctx.context
    nxt = s.week + 1
    start = s.store.one("SELECT start_date FROM weeks WHERE week=?", (s.week,))[0]
    from datetime import date, timedelta
    nstart = (date.fromisoformat(start) + timedelta(days=7)).isoformat()
    s.store.ensure_week(nxt, nstart)
    p = plan.model_dump()
    p["videos_next_week"] = max(1, min(5, p["videos_next_week"]))     # guard rails
    s.store.set_week_json(nxt, "plan_json", p)
    s.say("business_manager", f"plan for week {nxt}: {p['videos_next_week']} videos, favor {p['favor_categories']}")
    return "saved"


PRODUCER_TOOLS = [get_week_status]
RESEARCH_TOOLS = [search_trends, save_research]
STRATEGIST_TOOLS = [get_research, get_manager_plan, get_past_performance, save_briefs]
SCRIPT_TOOLS = [get_episode_brief, save_script]
FACTCHECK_TOOLS = [get_script, save_fact_check]
SEO_TOOLS = [get_script, get_channel_insights, save_metadata]
VISUAL_TOOLS = [get_script, save_visuals]
ANALYTICS_TOOLS = [get_channel_stats, save_insights]
MANAGER_TOOLS = [get_profit_report, save_next_week_plan]
