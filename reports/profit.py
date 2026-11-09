"""Profit math. All numbers here come from the database, never from an LLM.

Profit per video = revenue to date - AI cost.
AI cost of a video = its direct cost (calls made while working on that episode:
script, fact-check, SEO, visuals, TTS) + an equal share of that week's shared
cost (planning, research, analytics, the manager's report).
"""
from __future__ import annotations

from tools.storage import Store


def _shared_cost_by_week(store: Store) -> dict[int, float]:
    return {r[0]: float(r[1]) for r in store.q(
        "SELECT week, SUM(cost_usd) FROM ai_costs WHERE episode_id IS NULL GROUP BY week")}


def profit_per_video(store: Store) -> list[dict]:
    shared = _shared_cost_by_week(store)
    per_week_count = {r[0]: r[1] for r in store.q("SELECT week, COUNT(*) FROM episodes GROUP BY week")}
    out = []
    for ep in store.q("SELECT id, week, topic, category, status, json_extract(metadata_json,'$.titles[0]') "
                      "FROM episodes ORDER BY week, slot"):
        ep_id, week = ep[0], ep[1]
        direct = float(store.one("SELECT COALESCE(SUM(cost_usd),0) FROM ai_costs WHERE episode_id=?", (ep_id,))[0])
        share = shared.get(week, 0.0) / max(1, per_week_count.get(week, 1))
        st = store.one("SELECT COALESCE(SUM(views),0), COALESCE(SUM(revenue_usd),0) FROM daily_stats "
                       "WHERE episode_id=?", (ep_id,))
        revenue = float(st[1])
        cost = direct + share
        out.append({
            "episode_id": ep_id, "week": week, "title": ep[5] or ep[2], "category": ep[3], "status": ep[4],
            "views": int(st[0]), "revenue_usd": round(revenue, 2),
            "ai_cost_direct_usd": round(direct, 4), "ai_cost_shared_usd": round(share, 4),
            "ai_cost_usd": round(cost, 4), "profit_usd": round(revenue - cost, 2),
        })
    return out


def agent_costs(store: Store, week: int | None = None) -> list[dict]:
    sql = ("SELECT agent, COUNT(*), SUM(input_tokens), SUM(output_tokens), SUM(cost_usd) FROM ai_costs"
           + (" WHERE week=?" if week is not None else "") + " GROUP BY agent ORDER BY SUM(cost_usd) DESC")
    rows = store.q(sql, (week,) if week is not None else ())
    return [{"agent": r[0], "calls": r[1], "input_tokens": r[2] or 0, "output_tokens": r[3] or 0,
             "cost_usd": round(float(r[4] or 0), 4)} for r in rows]


def agent_costs_by_week(store: Store) -> dict[str, dict[int, float]]:
    out: dict[str, dict[int, float]] = {}
    for r in store.q("SELECT agent, week, SUM(cost_usd) FROM ai_costs GROUP BY agent, week"):
        out.setdefault(r[0], {})[r[1]] = float(r[2])
    return out


def category_summary(store: Store) -> list[dict]:
    rows: dict[str, dict] = {}
    for v in profit_per_video(store):
        c = rows.setdefault(v["category"], {"category": v["category"], "videos": 0, "views": 0,
                                            "revenue_usd": 0.0, "ai_cost_usd": 0.0, "profit_usd": 0.0})
        c["videos"] += 1
        c["views"] += v["views"]
        c["revenue_usd"] += v["revenue_usd"]
        c["ai_cost_usd"] += v["ai_cost_usd"]
        c["profit_usd"] += v["profit_usd"]
    for c in rows.values():
        for k in ("revenue_usd", "ai_cost_usd", "profit_usd"):
            c[k] = round(c[k], 2)
        c["profit_per_video"] = round(c["profit_usd"] / c["videos"], 2) if c["videos"] else 0
    return sorted(rows.values(), key=lambda c: c["profit_per_video"], reverse=True)


def used_topics(store: Store) -> list[str]:
    return [r[0] for r in store.q("SELECT topic_id FROM episodes WHERE status != 'rejected'")]


def totals(store: Store) -> dict:
    vids = profit_per_video(store)
    revenue = sum(v["revenue_usd"] for v in vids)
    ai = float(store.one("SELECT COALESCE(SUM(cost_usd),0) FROM ai_costs")[0])
    return {"videos_made": len(vids), "videos_published": sum(1 for v in vids if v["status"] == "uploaded"),
            "views": sum(v["views"] for v in vids), "revenue_usd": round(revenue, 2),
            "ai_cost_usd": round(ai, 4), "profit_usd": round(revenue - ai, 2)}
