"""MockModel: a stand-in LLM for MOCK mode.

It plugs into the OpenAI Agents SDK exactly where a real model would, and it
emits real tool calls and real handoff calls. So in mock mode the SDK still
runs the actual agent graph, executes the actual tools, and performs the
actual Swarm-style handoffs. Only the "thinking" is scripted.

Each agent has a "brain": a generator that yields one action per model call.
Token usage is estimated from the real prompt size (instructions + history +
tool schemas), so the cost ledger looks like a real run.
"""
from __future__ import annotations

import json
import random
import re
import uuid
from typing import Any, Iterator

from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText

from .context import RunState
from mock.fake_data import TOPIC_BY_ID, trending

Action = tuple  # ("tool", name, args) | ("handoff", agent_name) | ("final", text)

QUESTION_TITLES = {
    "llm-how": "How Does ChatGPT Actually Work?",
    "rag": "How Do Chatbots Read Your PDFs? (RAG Explained)",
    "agents": "What Is an AI Agent, Really?",
    "python-first": "Can You Call AI in 10 Lines of Python?",
    "hallucinations": "Why Does AI Make Things Up?",
    "ai-jobs": "Will AI Take My Job? A Professor Answers",
    "embeddings": "How Do Computers Understand Meaning?",
    "ai-ethics-bias": "Where Does AI Bias Come From?",
    "prompting": "Why Do Some Prompts Work So Much Better?",
    "neural-net": "What Is a Neural Network? (One Neuron Explained)",
    "local-llm": "Can You Run AI on Your Own PC?",
    "ai-cheating": "Is Using AI in Class Cheating?",
}
THUMB_TEXT = {
    "llm-how": "IT'S GUESSING", "rag": "OPEN BOOK AI", "agents": "AGENTS, REALLY?",
    "python-first": "10 LINES", "hallucinations": "AI LIES?", "ai-jobs": "MY JOB?",
    "embeddings": "MEANING = MATH", "ai-ethics-bias": "BIASED AI", "prompting": "BETTER PROMPTS",
    "neural-net": "ONE NEURON", "local-llm": "AI ON YOUR PC", "ai-cheating": "CHEATING?",
}
WPM = 150


def _est_tokens(*parts: Any) -> int:
    n = 0
    for p in parts:
        n += len(p if isinstance(p, str) else json.dumps(p, default=str))
    return max(1, n // 4)


class MockModel(Model):
    def __init__(self, agent_name: str, state: RunState):
        self.agent_name = agent_name
        self.state = state
        self.brain: Iterator[Action] = BRAINS[agent_name](state)

    async def get_response(self, system_instructions, input, model_settings, tools, output_schema, handoffs,
                           tracing, *, previous_response_id=None, conversation_id=None, prompt=None):
        action = next(self.brain)
        if action[0] == "tool":
            item = ResponseFunctionToolCall(id=f"fc_{uuid.uuid4().hex[:12]}", call_id=f"call_{uuid.uuid4().hex[:12]}",
                                            name=action[1], arguments=json.dumps(action[2]),
                                            type="function_call", status="completed")
            out_text = item.arguments
        elif action[0] == "handoff":
            h = next(h for h in handoffs if h.agent_name == action[1])
            item = ResponseFunctionToolCall(id=f"fc_{uuid.uuid4().hex[:12]}", call_id=f"call_{uuid.uuid4().hex[:12]}",
                                            name=h.tool_name, arguments="{}", type="function_call",
                                            status="completed")
            out_text = h.tool_name
        else:
            item = ResponseOutputMessage(id=f"msg_{uuid.uuid4().hex[:12]}", role="assistant", status="completed",
                                         type="message",
                                         content=[ResponseOutputText(text=action[1], type="output_text",
                                                                     annotations=[])])
            out_text = action[1]
        tool_schemas = [getattr(t, "params_json_schema", {}) for t in tools]
        in_tok = _est_tokens(system_instructions or "", input, tool_schemas)
        out_tok = _est_tokens(out_text) + 12
        usage = Usage(requests=1, input_tokens=in_tok, output_tokens=out_tok, total_tokens=in_tok + out_tok)
        return ModelResponse(output=[item], usage=usage, response_id=None)

    def stream_response(self, *args, **kwargs):  # not used
        raise NotImplementedError("MockModel does not stream")


# ======================================================================
# Brains: one per agent. Each yields actions; tools run between yields.
# ======================================================================

def producer_brain(s: RunState) -> Iterator[Action]:
    yield ("tool", "get_week_status", {})
    target = {"plan": "trend_researcher", "produce": "scriptwriter", "revise": "scriptwriter",
              "review_week": "analytics"}[s.stage]
    yield ("handoff", target)
    yield ("final", "Done.")


def trend_researcher_brain(s: RunState) -> Iterator[Action]:
    query = "AI explained for beginners"
    yield ("tool", "search_trends", {"query": query})
    rows = trending(s.week, s.cfg["simulation"]["seed"], query)
    used = {r[0] for r in s.store.q("SELECT topic_id FROM episodes")}
    shortlist = [r for r in rows if r["topic_id"] not in used][:6]
    findings = [{
        "topic_id": r["topic_id"], "topic": r["topic"], "category": r["category"],
        "search_demand": r["search_demand"], "competition": r["competition"],
        "why_now": f"Demand {r['search_demand']:.2f} vs competition {r['competition']:.2f}; "
                   f"opportunity score {r['opportunity']:.3f}.",
    } for r in shortlist]
    yield ("tool", "save_research", {"findings": findings})
    yield ("handoff", "topic_strategist")
    yield ("final", "Research handed to strategist.")


def topic_strategist_brain(s: RunState) -> Iterator[Action]:
    yield ("tool", "get_research", {})
    yield ("tool", "get_manager_plan", {})
    yield ("tool", "get_past_performance", {})
    research = s.store.week_json(s.week, "research_json") or []
    plan = s.store.week_json(s.week, "plan_json") or {}
    n = plan.get("videos_next_week") or s.cfg["channel"]["videos_per_week"]
    favor, avoid = set(plan.get("favor_categories", [])), set(plan.get("avoid_categories", []))

    def score(f: dict) -> float:
        base = f["search_demand"] * (1.1 - f["competition"])
        if f["category"] in favor:
            base *= 1.35
        if f["category"] in avoid:
            base *= 0.5
        return base

    ranked = sorted(research, key=score, reverse=True)
    picks, cats = [], set()
    for f in ranked:                       # keep categories varied unless favored
        if f["category"] in cats and f["category"] not in favor:
            continue
        picks.append(f)
        cats.add(f["category"])
        if len(picks) == n:
            break
    briefs = []
    for f in picks:
        t = TOPIC_BY_ID[f["topic_id"]]
        briefs.append({
            "topic_id": t["topic_id"], "topic": t["topic"], "category": t["category"],
            "audience": "Curious beginners, college students and professionals new to AI",
            "angle": "A professor's classroom-tested explanation with one analogy students remember",
            "key_points": [p[0] for p in t["points"]], "target_minutes": 2.5,
        })
    yield ("tool", "save_briefs", {"briefs": briefs})
    yield ("final", f"Saved {len(briefs)} briefs for week {s.week}.")


def _build_script(s: RunState, ep: dict) -> tuple[str, list[dict]]:
    t = TOPIC_BY_ID[ep["topic_id"]]
    prev = ep.get("script") or {}
    draft = (prev.get("draft") or 0) + 1
    fc = ep.get("factcheck") or {}
    notes = (s.notes or ep.get("review_notes") or "").lower()
    rng = random.Random(f"{s.cfg['simulation']['seed']}-{ep['id']}")
    # Draft 1 sometimes contains an over-confident claim (as real drafts do).
    has_open_issue = bool(fc.get("rounds")) and not fc.get("passed")
    include_overclaim = draft == 1 and not has_open_issue and rng.random() < 0.6
    channel = s.cfg["channel"]["name"]
    pts = t["points"]
    scenes = [
        {"heading": "The question", "on_screen_text": t["topic"],
         "narration": t["hook"] + " In the next few minutes I will explain it the way I explain it to my students.",
         "professor_note": ""},
        {"heading": t["topic"], "on_screen_text": "A professor explains",
         "narration": f"I teach this in my college classes, and this is {channel}. Let's get into it.",
         "professor_note": ""},
    ]
    for i, (head, body) in enumerate(pts):
        narr = body
        if include_overclaim and i == 2:
            narr = body + " " + t["overclaim"]
        scenes.append({"heading": head, "on_screen_text": head, "narration": narr, "professor_note": ""})
    if "short" not in notes:
        scenes.append({"heading": "The picture I use in class", "on_screen_text": "An analogy",
                       "narration": "Here is the picture I use in class. " + t["analogy"],
                       "professor_note": "Add a 20-second story from your own class here."})
    if "example" in notes:
        scenes.append({"heading": "A real example", "on_screen_text": "From my classroom",
                       "narration": "Let me give you a real example from my own classroom, "
                                    "where students tried this for the first time.",
                       "professor_note": "Professor records this example himself (requested in review)."})
    if has_open_issue:   # apply the fact-checker's fix wording
        scenes.append({"heading": "One important caution", "on_screen_text": "Be careful",
                       "narration": t["overclaim_fix"], "professor_note": ""})
    scenes.append({"heading": "Recap", "on_screen_text": " / ".join(p[0] for p in pts),
                   "narration": "So, to recap. " + ". ".join(p[0] for p in pts) + ".", "professor_note": ""})
    scenes.append({"heading": "What should I explain next?", "on_screen_text": "Subscribe for more",
                   "narration": "If this helped, subscribe, and tell me in the comments what you want explained "
                                "next. I read every comment.", "professor_note": ""})
    return t["topic"], scenes


def scriptwriter_brain(s: RunState) -> Iterator[Action]:
    while True:
        yield ("tool", "get_episode_brief", {})
        ep = s.store.episode(s.episode_id)
        title, scenes = _build_script(s, ep)
        yield ("tool", "save_script", {"working_title": title, "scenes": scenes})
        yield ("handoff", "fact_checker")


def fact_checker_brain(s: RunState) -> Iterator[Action]:
    while True:
        yield ("tool", "get_script", {})
        ep = s.store.episode(s.episode_id)
        t = TOPIC_BY_ID[ep["topic_id"]]
        issues = []
        for i, sc in enumerate(ep["script"]["scenes"]):
            if t["overclaim"] in sc["narration"]:
                issues.append({"scene_index": i, "claim": t["overclaim"],
                               "problem": "Absolute claim that is not true as stated.",
                               "suggested_fix": t["overclaim_fix"]})
        yield ("tool", "save_fact_check", {"passed": not issues, "issues": issues})
        rounds = len((s.store.episode(s.episode_id)["factcheck"] or {}).get("rounds", []))
        if issues and rounds < 2:
            yield ("handoff", "scriptwriter")
        else:
            yield ("handoff", "seo_metadata")


def _chapters(scenes: list[dict]) -> list[dict]:
    t, out = 0.0, []
    for sc in scenes:
        if sc["heading"] not in ("The question",):
            out.append({"timestamp": f"{int(t // 60)}:{int(t % 60):02d}", "title": sc["heading"]})
        t += len(sc["narration"].split()) / WPM * 60 + 0.6
    out[0]["timestamp"] = "0:00"
    return out


def seo_brain(s: RunState) -> Iterator[Action]:
    while True:
        yield ("tool", "get_script", {})
        yield ("tool", "get_channel_insights", {})
        ep = s.store.episode(s.episode_id)
        t = TOPIC_BY_ID[ep["topic_id"]]
        prev = s.store.week_json(s.week - 1, "insights_json") if s.week > 1 else None
        plan = s.store.week_json(s.week, "plan_json") or {}
        guidance = ((prev or {}).get("title_pattern", "") + " " + plan.get("title_guidance", "")).lower()
        q = QUESTION_TITLES[t["topic_id"]]
        plain = t["topic"][0].upper() + t["topic"][1:]
        prof = f"{plain} | A Professor Explains"
        titles = [q, plain, prof] if "question" in guidance else [plain, q, prof]
        scenes = ep["script"]["scenes"]
        desc = (f"{t['hook']}\n\nIn this video a college professor explains {t['topic'].lower()}: "
                + "; ".join(p[0].lower() for p in t["points"]) + ".\n\n"
                "Chapters\n" + "\n".join(f"{c['timestamp']} {c['title']}" for c in _chapters(scenes))
                + "\n\nNarration in this video uses a synthetic (AI) voice. Script reviewed and approved by the "
                  "professor.\n\n#AI #MachineLearning #Education")
        tags = ["AI explained", t["topic"].lower(), t["category"].replace("_", " "), "artificial intelligence",
                "machine learning for beginners", "professor explains", "tech education"]
        yield ("tool", "save_metadata", {"titles": titles, "description": desc, "tags": tags,
                                         "chapters": _chapters(scenes),
                                         "pinned_comment": "What should I explain next? Reply with a topic."})
        yield ("handoff", "visual_designer")


def visual_brain(s: RunState) -> Iterator[Action]:
    while True:
        yield ("tool", "get_script", {})
        ep = s.store.episode(s.episode_id)
        scenes = ep["script"]["scenes"]
        vis = []
        for i, sc in enumerate(scenes):
            layout = "title" if i == 0 else ("list" if sc["heading"] == "Recap" else "split")
            vis.append({"scene_index": i, "layout": layout,
                        "image_prompt": f"Clean flat illustration of '{sc['heading']}', dark navy background, "
                                        f"teal and amber accents, no text"})
        thumb = {"text": THUMB_TEXT[ep["topic_id"]], "concept": "Big 2-3 word hook on the left, bold visual "
                 "metaphor on the right, high contrast",
                 "image_prompt": f"Bold visual metaphor for '{ep['topic']}', glowing network, high contrast"}
        yield ("tool", "save_visuals", {"thumbnail": thumb, "scenes": vis})
        yield ("final", f"Episode {ep['id']} package ready for rendering and review.")


def analytics_brain(s: RunState) -> Iterator[Action]:
    yield ("tool", "get_channel_stats", {})
    from tools.channel_stats import per_video_totals

    rows = per_video_totals(s.store)
    findings, best_cat, pattern = [], "", "no clear title pattern yet"
    if rows:
        by_cat: dict[str, list] = {}
        for r in rows:
            by_cat.setdefault(r["category"], []).append(r)
        rpv = {c: sum(r["revenue_usd"] for r in v) / len(v) for c, v in by_cat.items()}
        best_cat = max(rpv, key=rpv.get)
        top = max(rows, key=lambda r: r["views"])
        findings.append(f"Top video so far: {top['id']} '{top['title']}' with {top['views']} views "
                        f"and CTR {top['ctr']:.1%}.")
        for c, v in sorted(rpv.items(), key=lambda kv: -kv[1]):
            findings.append(f"Category {c}: ${v:.2f} revenue per video ({len(by_cat[c])} video(s)).")
        qs = [r["ctr"] for r in rows if r["title"] and "?" in r["title"]]
        ns = [r["ctr"] for r in rows if r["title"] and "?" not in r["title"]]
        if qs and ns:
            qa, na = sum(qs) / len(qs), sum(ns) / len(ns)
            pattern = ("question titles get higher CTR" if qa > na else "plain titles get higher CTR")
            findings.append(f"Question titles CTR {qa:.1%} vs plain titles {na:.1%}.")
        elif ns and not qs:
            pattern = "no question titles tested yet; try question titles"
            findings.append("All titles so far were plain statements; no question titles to compare yet.")
        avg_view = sum(r["avg_view_pct"] for r in rows) / len(rows)
        findings.append(f"Average view percentage {avg_view:.0%}. Short videos keep viewers to the end.")
    summary = f"{len(rows)} published video(s) analysed." if rows else "No published videos yet."
    yield ("tool", "save_insights", {"summary": summary, "findings": findings, "best_category": best_cat or "n/a",
                                     "title_pattern": pattern})
    yield ("handoff", "business_manager")
    yield ("final", "Insights handed to manager.")


def manager_brain(s: RunState) -> Iterator[Action]:
    yield ("tool", "get_profit_report", {})
    from reports.profit import agent_costs, category_summary, profit_per_video

    vids = profit_per_video(s.store)
    cats = category_summary(s.store)
    insights = s.store.week_json(s.week, "insights_json") or {}
    plan_now = s.store.week_json(s.week, "plan_json") or {}
    current_n = plan_now.get("videos_next_week") or s.cfg["channel"]["videos_per_week"]
    published = [v for v in vids if v["status"] == "uploaded"]
    profitable = [v for v in published if v["profit_usd"] > 0]
    favor = [c["category"] for c in cats if c["profit_per_video"] > 0][:1]
    avoid = [c["category"] for c in cats if c["profit_usd"] < 0]
    n = current_n + 1 if published and len(profitable) == len(published) and current_n < 3 else current_n
    budget_changes = []
    for a in agent_costs(s.store, s.week):
        cap = s.cfg["budgets_weekly_usd"].get(a["agent"])
        if cap and a["cost_usd"] > 0.8 * cap:
            budget_changes.append({"agent": a["agent"], "weekly_usd": round(cap * 1.25, 2)})
    total_rev = sum(v["revenue_usd"] for v in vids)
    total_cost = sum(v["ai_cost_usd"] for v in vids)
    summary = (f"Week {s.week}: {len(published)} video(s) live, revenue to date ${total_rev:.2f}, "
               f"AI cost ${total_cost:.2f}, profit ${total_rev - total_cost:.2f}.")
    rationale = (f"Every published video is profitable, so the AI cost per video is small compared with ad revenue; "
                 f"making {n} videos next week raises profit. " if n > current_n else
                 f"Keep {n} videos per week until more data comes in. ")
    if favor:
        rationale += f"Favor '{favor[0]}' because it earns the most profit per video. "
    if avoid:
        rationale += f"Avoid {avoid} for now because they lost money. "
    rationale += f"Analytics says: {insights.get('title_pattern', 'n/a')}."
    plan = {"videos_next_week": n, "favor_categories": favor, "avoid_categories": avoid,
            "title_guidance": insights.get("title_pattern", ""), "budget_changes": budget_changes,
            "summary": summary, "rationale": rationale}
    yield ("tool", "save_next_week_plan", {"plan": plan})
    yield ("final", summary)


BRAINS = {
    "producer": producer_brain,
    "trend_researcher": trend_researcher_brain,
    "topic_strategist": topic_strategist_brain,
    "scriptwriter": scriptwriter_brain,
    "fact_checker": fact_checker_brain,
    "seo_metadata": seo_brain,
    "visual_designer": visual_brain,
    "analytics": analytics_brain,
    "business_manager": manager_brain,
}
