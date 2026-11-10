"""Local web app for the professor.

    /review            all videos by status
    /review/<id>       watch the video, read the script and fact-check, then
                       Approve / Request changes / Reject
    /upload/<id>       upload an approved video as PRIVATE (the gate re-checks)
    /dashboard         profit per video and cost per agent
    /reports           weekly reports

Run with:  python main.py serve      (opens on http://127.0.0.1:5000)
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, send_file, url_for

from agents_system.config import load_config
from approval.gate import GateError, can_upload, record_decision
from reports.charts import CHART_CSS, TOOLTIP_JS, diverging_bars, magnitude_bars
from reports.profit import agent_costs, agent_costs_by_week, category_summary, profit_per_video, totals
from reports.weekly import _agent_tip, _video_tip
from tools.storage import Store

STATUS_ORDER = [
    ("pending_review", "Waiting for your review"),
    ("changes_requested", "Changes requested (agents are revising)"),
    ("approved", "Approved, ready to upload as private"),
    ("uploaded", "Uploaded (private)"),
    ("rejected", "Rejected"),
    ("packaged", "In production"), ("scripted", "In production"), ("planned", "Planned"),
]


def create_app(cfg=None) -> Flask:
    cfg = cfg or load_config()
    app = Flask(__name__)
    app.secret_key = os.urandom(16)
    store = Store(cfg.path("db_path"))
    out_root = cfg.output_dir.resolve()

    def cost_of(ep_id: str) -> float:
        return float(store.one("SELECT COALESCE(SUM(cost_usd),0) FROM ai_costs WHERE episode_id=?", (ep_id,))[0])

    @app.context_processor
    def globals_():
        return {"mode": cfg.mode, "channel": cfg["channel"]["name"], "chart_css": CHART_CSS,
                "pending_count": len(store.episodes(status="pending_review"))}

    @app.route("/")
    def home():
        return redirect(url_for("review_list"))

    @app.route("/review")
    def review_list():
        groups, seen = [], set()
        for status, label in STATUS_ORDER:
            if label in seen and status in ("scripted", "packaged"):
                eps = store.episodes(status=status)
                if eps:
                    groups[-1][1].extend(eps)
                continue
            seen.add(label)
            eps = store.episodes(status=status)
            for e in eps:
                e["cost"] = cost_of(e["id"])
            groups.append((label, eps, status))
        groups = [(label, eps, s) for label, eps, s in groups if eps]
        return render_template("review_list.html", groups=groups)

    @app.route("/review/<ep_id>")
    def review_detail(ep_id: str):
        ep = store.episode(ep_id)
        if not ep:
            abort(404)
        decisions = [dict(r) for r in store.q("SELECT * FROM decisions WHERE episode_id=? ORDER BY id", (ep_id,))]
        costs = [dict(r) for r in store.q(
            "SELECT agent, COUNT(*) calls, SUM(cost_usd) cost FROM ai_costs WHERE episode_id=? GROUP BY agent "
            "ORDER BY cost DESC", (ep_id,))]
        upload = store.one("SELECT * FROM uploads WHERE episode_id=?", (ep_id,))
        ok, why = can_upload(store, ep_id)
        return render_template("review_detail.html", ep=ep, decisions=decisions, costs=costs,
                               total_cost=sum(c["cost"] for c in costs), upload=upload, can_up=ok, why=why)

    @app.route("/review/<ep_id>/decide", methods=["POST"])
    def decide(ep_id: str):
        decision = request.form.get("decision", "")
        notes = request.form.get("notes", "")
        who = request.form.get("who", "").strip() or "Professor"
        try:
            record_decision(store, ep_id, decision, notes, who)
            flash(f"{ep_id}: {decision.replace('_', ' ')} recorded.", "ok")
            if decision == "changes_requested":
                flash("Run `python main.py revise` (or the next cycle) to send it back through the agents.", "info")
        except GateError as e:
            flash(str(e), "err")
        return redirect(url_for("review_detail", ep_id=ep_id))

    @app.route("/upload/<ep_id>", methods=["POST"])
    def upload(ep_id: str):
        from tools.youtube_upload import upload as do_upload

        res = do_upload(cfg, store, ep_id)
        if res.get("ok"):
            flash(f"Uploaded as PRIVATE: {res['video_id']}", "ok")
        else:
            flash(f"Upload refused: {res['reason']}", "err")
        return redirect(url_for("review_detail", ep_id=ep_id))

    @app.route("/media/<path:rel>")
    def media(rel: str):
        p = (Path(cfg.root) / rel).resolve()
        if out_root not in p.parents:
            abort(403)
        if not p.exists():
            abort(404)
        return send_file(p)

    @app.route("/captions/<ep_id>.vtt")
    def captions(ep_id: str):
        ep = store.episode(ep_id)
        if not ep or not ep.get("srt_path") or not Path(ep["srt_path"]).exists():
            abort(404)
        srt = Path(ep["srt_path"]).read_text(encoding="utf-8")
        vtt = "WEBVTT\n\n" + re.sub(r"(\d\d:\d\d:\d\d),(\d\d\d)", r"\1.\2", srt)
        return vtt, 200, {"Content-Type": "text/vtt"}

    @app.route("/dashboard")
    def dashboard():
        vids = profit_per_video(store)
        agents = agent_costs(store)
        weeks = sorted({r[0] for r in store.q("SELECT DISTINCT week FROM ai_costs")})
        by_week = agent_costs_by_week(store)
        return render_template(
            "dashboard.html", t=totals(store), vids=vids, agents=agents, weeks=weeks, by_week=by_week,
            cats=category_summary(store),
            chart_profit=diverging_bars(vids, "episode_id", "profit_usd", _video_tip),
            chart_agents=magnitude_bars(agents, "agent", "cost_usd", _agent_tip),
            tooltip_js=TOOLTIP_JS)

    @app.route("/reports")
    def reports():
        rows = [dict(r) for r in store.q("SELECT week, start_date, report_path FROM weeks ORDER BY week")]
        return render_template("reports.html", rows=rows)

    @app.route("/reports/<int:week>")
    def report(week: int):
        p = cfg.output_dir / "reports" / f"week_{week:02d}.html"
        if not p.exists():
            abort(404)
        return send_file(p.resolve())

    @app.template_filter("rel")
    def rel(path: str) -> str:
        return Path(os.path.relpath(path, cfg.root)).as_posix() if path else ""

    @app.template_filter("money")
    def money(v, d=2):
        v = float(v or 0)
        return ("-" if v < 0 else "") + f"${abs(v):,.{d}f}"

    return app
