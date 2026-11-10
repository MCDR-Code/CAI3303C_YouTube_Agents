"""YouTube Agent System - command line.

    python main.py week              plan + produce + render this week's videos, then stop for review
    python main.py serve             open the review page and dashboard (http://127.0.0.1:5000)
    python main.py revise            send videos with "changes requested" back through the agents
    python main.py publish           upload approved videos as PRIVATE
    python main.py close-week        stats -> analytics -> business manager -> weekly report
    python main.py simulate --weeks 2 --fresh
                                     DEMO ONLY: run whole weeks with a simulated professor
    python main.py status            show every episode and its status
"""
from __future__ import annotations

import argparse
import shutil
import sys

from agents_system import pipeline
from agents_system.config import load_config
from tools.storage import Store


def _current_week(store: Store) -> int:
    return max(1, store.latest_week())


def cmd_week(cfg, store, args):
    week = args.week or (_current_week(store) if not store.episodes(week=_current_week(store)) else
                         _current_week(store) + (1 if store.week_json(_current_week(store) + 1, "plan_json") else 0))
    eps = pipeline.plan_week(cfg, store, week)
    for ep in eps:
        if store.episode(ep)["status"] == "planned":
            pipeline.produce_episode(cfg, store, ep)
    print(f"\nWeek {week}: {len(eps)} video(s) are waiting for the professor. Run: python main.py serve")


def cmd_revise(cfg, store, args):
    eps = store.episodes(status="changes_requested")
    if not eps:
        print("No videos with changes requested.")
    for ep in eps:
        pipeline.revise_episode(cfg, store, ep["id"])


def cmd_publish(cfg, store, args):
    done = pipeline.publish_approved(cfg, store)
    print(f"Uploaded {len(done)} video(s) as private." if done else "Nothing approved to upload.")


def cmd_close(cfg, store, args):
    pipeline.close_week(cfg, store, args.week or _current_week(store))


def cmd_serve(cfg, store, args):
    from webapp.app import create_app

    print("Review page:  http://127.0.0.1:%d/review\nDashboard:    http://127.0.0.1:%d/dashboard" % (args.port, args.port))
    create_app(cfg).run(host="127.0.0.1", port=args.port, debug=False)


def cmd_status(cfg, store, args):
    for ep in store.episodes():
        title = (ep.get("metadata") or {}).get("titles", [ep["topic"]])[0]
        print(f"{ep['id']}  r{ep['revision']}  {ep['status']:<18} {title}")


def cmd_simulate(cfg, store, args):
    """DEMO: whole weeks end to end. The professor's decisions are simulated and labeled as such."""
    from approval.sim_professor import review_pending

    if cfg.mode != "mock":
        sys.exit("simulate only runs in mock mode.")
    dpw = cfg["simulation"]["days_per_week"]
    for week in range(1, args.weeks + 1):
        eps = pipeline.plan_week(cfg, store, week)
        for ep in eps:
            pipeline.produce_episode(cfg, store, ep)
        print(f"\n== Week {week}: professor review (SIMULATED for the demo) ==")
        review_pending(store)
        while store.episodes(status="changes_requested"):
            for ep in store.episodes(status="changes_requested"):
                pipeline.revise_episode(cfg, store, ep["id"])
            print(f"\n== Week {week}: professor review of revisions (SIMULATED) ==")
            review_pending(store)
        print(f"\n== Week {week}: publish (private) ==")
        pipeline.publish_approved(cfg, store, sim_day=(week - 1) * dpw + 4)   # Friday
        pipeline.close_week(cfg, store, week, last_sim_day=week * dpw - 1)     # Sunday
    print("\nDone. Run `python main.py serve` to see the review page and dashboard.")


def main(argv=None):
    ap = argparse.ArgumentParser(description="YouTube Agent System (CAI3303C)")
    ap.add_argument("--config", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("week"); w.add_argument("--week", type=int)
    sub.add_parser("revise")
    sub.add_parser("publish")
    c = sub.add_parser("close-week"); c.add_argument("--week", type=int)
    s = sub.add_parser("serve"); s.add_argument("--port", type=int, default=5000)
    sub.add_parser("status")
    sm = sub.add_parser("simulate"); sm.add_argument("--weeks", type=int, default=2)
    sm.add_argument("--fresh", action="store_true", help="delete the database and output first")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    if getattr(args, "fresh", False):
        cfg.path("db_path").unlink(missing_ok=True)
        shutil.rmtree(cfg.output_dir, ignore_errors=True)
        cfg.output_dir.mkdir(parents=True, exist_ok=True)
    store = Store(cfg.path("db_path"))
    print(f"Mode: {cfg.mode.upper()}  backends: {cfg.backends}")
    {"week": cmd_week, "revise": cmd_revise, "publish": cmd_publish, "close-week": cmd_close,
     "serve": cmd_serve, "status": cmd_status, "simulate": cmd_simulate}[args.cmd](cfg, store, args)


if __name__ == "__main__":
    main()
