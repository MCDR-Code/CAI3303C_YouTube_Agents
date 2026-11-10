"""Weekly report: profit per video, cost per agent, analytics findings and next week's plan.

Written as Markdown (easy to read on GitHub) and as a self-contained HTML page.
All numbers come from the database (reports/profit.py), never from an LLM.
"""
from __future__ import annotations

from html import escape
from pathlib import Path

from reports.charts import CHART_CSS, TOOLTIP_JS, diverging_bars, magnitude_bars
from reports.profit import agent_costs, profit_per_video, totals


def _m(v: float, d: int = 2) -> str:
    return ("-" if v < 0 else "") + f"${abs(v):,.{d}f}"


def report_data(store, week: int) -> dict:
    vids = profit_per_video(store)
    return {
        "week": week,
        "start": store.one("SELECT start_date FROM weeks WHERE week=?", (week,))[0],
        "videos": vids,
        "this_week": [v for v in vids if v["week"] == week],
        "agents_week": agent_costs(store, week),
        "agents_all": agent_costs(store),
        "totals": totals(store),
        "insights": store.week_json(week, "insights_json") or {},
        "plan_next": store.week_json(week + 1, "plan_json") or {},
        "plan_this": store.week_json(week, "plan_json") or {},
        "decisions": [dict(r) for r in store.q(
            "SELECT d.* FROM decisions d JOIN episodes e ON e.id=d.episode_id WHERE e.week=? ORDER BY d.id",
            (week,))],
    }


def _video_tip(v: dict) -> str:
    return (f"{v['episode_id']} ({v['status']})\n{v['title']}\nViews {v['views']:,}\n"
            f"Revenue {_m(v['revenue_usd'])}\nAI cost {_m(v['ai_cost_usd'], 4)}\nProfit {_m(v['profit_usd'])}")


def _agent_tip(a: dict) -> str:
    return (f"{a['agent']}\n{a['calls']} calls\n{a['input_tokens']:,} in / {a['output_tokens']:,} out tokens\n"
            f"Cost {_m(a['cost_usd'], 4)}")


def to_markdown(d: dict, mode: str) -> str:
    t = d["totals"]
    L = [f"# Weekly report: week {d['week']} (starts {d['start']})", ""]
    if mode == "mock":
        L += ["> MOCK MODE: views and revenue are simulated, the LLM is the scripted mock model, and token costs "
              "are estimated from real prompt sizes at the prices in config.yaml.", ""]
    L += ["## Channel totals to date", "",
          f"Videos made: {t['videos_made']}, published (private uploads): {t['videos_published']}, "
          f"views: {t['views']:,}", "",
          f"Revenue {_m(t['revenue_usd'])} - AI cost {_m(t['ai_cost_usd'], 4)} = profit **{_m(t['profit_usd'])}**", "",
          "## Profit per video", "",
          "| Video | Week | Title | Status | Views | Revenue | AI cost | Profit |",
          "|---|---|---|---|---:|---:|---:|---:|"]
    for v in d["videos"]:
        L.append(f"| {v['episode_id']} | {v['week']} | {v['title']} | {v['status']} | {v['views']:,} | "
                 f"{_m(v['revenue_usd'])} | {_m(v['ai_cost_usd'], 4)} | {_m(v['profit_usd'])} |")
    L += ["", "AI cost = the video's own agent calls + an equal share of the week's planning and review calls.", "",
          f"## Cost per agent (week {d['week']})", "", "| Agent | Calls | Input tokens | Output tokens | Cost |",
          "|---|---:|---:|---:|---:|"]
    for a in d["agents_week"]:
        L.append(f"| {a['agent']} | {a['calls']} | {a['input_tokens']:,} | {a['output_tokens']:,} | "
                 f"{_m(a['cost_usd'], 4)} |")
    ins = d["insights"]
    L += ["", "## What the Analytics agent found", "", ins.get("summary", "")]
    L += [f"- {f}" for f in ins.get("findings", [])]
    p = d["plan_next"]
    L += ["", f"## Business Manager's plan for week {d['week'] + 1}", ""]
    if p:
        L += [p.get("summary", ""), "",
              f"- Videos next week: {p.get('videos_next_week')}",
              f"- Favor: {', '.join(p.get('favor_categories') or []) or 'none'}",
              f"- Avoid: {', '.join(p.get('avoid_categories') or []) or 'none'}",
              f"- Title guidance: {p.get('title_guidance') or 'none'}",
              "- Budget changes: " + (", ".join(f"{b['agent']} -> ${b['weekly_usd']:.2f}/week"
                                               for b in p.get("budget_changes") or []) or "none"),
              "", f"Why: {p.get('rationale', '')}"]
    L += ["", "## Professor decisions this week", "", "| Video | Revision | Decision | Notes | By |", "|---|---|---|---|---|"]
    for x in d["decisions"]:
        L.append(f"| {x['episode_id']} | {x['revision']} | {x['decision']} | {x['notes'] or ''} | {x['decided_by']} |")
    return "\n".join(L) + "\n"


def to_html(d: dict, mode: str) -> str:
    rows = "".join(
        f"<tr><td>{v['episode_id']}</td><td>{escape(v['title'])}</td><td>{v['status']}</td>"
        f"<td class='n'>{v['views']:,}</td><td class='n'>{_m(v['revenue_usd'])}</td>"
        f"<td class='n'>{_m(v['ai_cost_usd'], 4)}</td><td class='n'><b>{_m(v['profit_usd'])}</b></td></tr>"
        for v in d["videos"])
    arows = "".join(
        f"<tr><td>{a['agent']}</td><td class='n'>{a['calls']}</td><td class='n'>{a['input_tokens']:,}</td>"
        f"<td class='n'>{a['output_tokens']:,}</td><td class='n'>{_m(a['cost_usd'], 4)}</td></tr>"
        for a in d["agents_week"])
    t, ins, p = d["totals"], d["insights"], d["plan_next"]
    banner = ("<p class='banner'>MOCK MODE: views and revenue are simulated; the LLM is the scripted mock model; "
              "token costs are estimated from real prompt sizes at config.yaml prices.</p>" if mode == "mock" else "")
    findings = "".join(f"<li>{escape(f)}</li>" for f in ins.get("findings", []))
    budget = ", ".join(f"{b['agent']} &rarr; ${b['weekly_usd']:.2f}/week" for b in p.get("budget_changes") or []) or "none"
    decisions = "".join(f"<tr><td>{x['episode_id']}</td><td>r{x['revision']}</td><td>{x['decision']}</td>"
                        f"<td>{escape(x['notes'] or '')}</td><td>{escape(x['decided_by'])}</td></tr>"
                        for x in d["decisions"])
    chart_v = diverging_bars(d["videos"], "episode_id", "profit_usd", _video_tip)
    chart_a = magnitude_bars(d["agents_week"], "agent", "cost_usd", _agent_tip)
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Week {d['week']} report</title>
<style>{CHART_CSS}
body{{font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;max-width:900px;margin:32px auto;padding:0 20px;
background:var(--surface-1);color:var(--text-primary)}}
h1{{font-size:26px;margin-bottom:4px}} h2{{font-size:18px;margin-top:34px}}
table{{border-collapse:collapse;width:100%;font-size:14px}} td,th{{padding:6px 8px;border-bottom:1px solid var(--grid);text-align:left}}
td.n,th.n{{text-align:right;font-variant-numeric:tabular-nums}} .muted{{color:var(--muted)}}
.banner{{background:#fff4d6;color:#5a4300;padding:8px 12px;border-radius:6px}}
.kpis{{display:flex;gap:12px;flex-wrap:wrap}} .kpi{{border:1px solid var(--grid);border-radius:8px;padding:10px 14px;min-width:130px}}
.kpi b{{display:block;font-size:22px}} .kpi span{{color:var(--text-secondary);font-size:13px}}
</style></head><body class="viz-root">
<h1>Weekly report: week {d['week']}</h1><p class="muted">Simulated week starting {d['start']}</p>{banner}
<div class="kpis"><div class="kpi"><span>Revenue to date</span><b>{_m(t['revenue_usd'])}</b></div>
<div class="kpi"><span>AI cost (Prune)</span><b>{_m(t['ai_cost_usd'])}</b></div>
<div class="kpi"><span>Profit</span><b>{_m(t['profit_usd'])}</b></div>
<div class="kpi"><span>Published (private)</span><b>{t['videos_published']} / {t['videos_made']}</b></div>
<div class="kpi"><span>Views</span><b>{t['views']:,}</b></div></div>
<h2>Profit per video</h2>{chart_v}
<table><tr><th>Video</th><th>Title</th><th>Status</th><th class=n>Views</th><th class=n>Revenue</th><th class=n>AI cost</th><th class=n>Profit</th></tr>{rows}</table>
<p class="muted">AI cost = the video's own agent calls + an equal share of the week's planning and review calls.</p>
<h2>Cost per agent this week</h2>{chart_a}
<table><tr><th>Agent</th><th class=n>Calls</th><th class=n>Input tokens</th><th class=n>Output tokens</th><th class=n>Cost</th></tr>{arows}</table>
<h2>What the Analytics agent found</h2><p>{escape(ins.get('summary', ''))}</p><ul>{findings}</ul>
<h2>Business Manager's plan for week {d['week'] + 1}</h2>
<p>{escape(p.get('summary', ''))}</p>
<ul><li>Videos next week: <b>{p.get('videos_next_week', '')}</b></li>
<li>Favor: {escape(', '.join(p.get('favor_categories') or []) or 'none')}</li>
<li>Avoid: {escape(', '.join(p.get('avoid_categories') or []) or 'none')}</li>
<li>Title guidance: {escape(p.get('title_guidance') or 'none')}</li><li>Budget changes: {budget}</li></ul>
<p><b>Why:</b> {escape(p.get('rationale', ''))}</p>
<h2>Professor decisions this week</h2>
<table><tr><th>Video</th><th>Rev</th><th>Decision</th><th>Notes</th><th>By</th></tr>{decisions}</table>
{TOOLTIP_JS}</body></html>"""


def write_weekly_report(cfg, store, week: int) -> Path:
    d = report_data(store, week)
    out = cfg.output_dir / "reports"
    out.mkdir(parents=True, exist_ok=True)
    md = out / f"week_{week:02d}.md"
    html = out / f"week_{week:02d}.html"
    md.write_text(to_markdown(d, cfg.mode), encoding="utf-8")
    html.write_text(to_html(d, cfg.mode), encoding="utf-8")
    store.x("UPDATE weeks SET report_path=? WHERE week=?", (str(html), week))
    return html
