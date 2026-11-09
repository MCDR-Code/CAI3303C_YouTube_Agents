"""Channel statistics. Mock: simulated daily stats. Real: YouTube Analytics API."""
from __future__ import annotations

from tools.storage import Store


def simulate_until(store: Store, cfg, sim_day: int) -> int:
    """MOCK: fill daily_stats for every uploaded video up to `sim_day` (inclusive)."""
    from mock.fake_data import simulate_day

    seed = cfg["simulation"]["seed"]
    written = 0
    for up in store.q("SELECT * FROM uploads ORDER BY sim_day"):
        ep = store.episode(up["episode_id"])
        for day in range(up["sim_day"], sim_day + 1):
            if store.one("SELECT 1 FROM daily_stats WHERE episode_id=? AND sim_day=?", (ep["id"], day)):
                continue
            subs = store.one("SELECT COALESCE(SUM(subscribers_gained),0) FROM daily_stats WHERE sim_day<?",
                             (day,))[0]
            d = simulate_day(ep, up["sim_day"], day, subs, cfg["economics"], seed)
            if not d:
                continue
            store.x("INSERT INTO daily_stats (episode_id, sim_day, views, impressions, watch_hours, avg_view_pct,"
                    " subscribers_gained, revenue_usd) VALUES (?,?,?,?,?,?,?,?)",
                    (ep["id"], day, d["views"], d["impressions"], d["watch_hours"], d["avg_view_pct"],
                     d["subscribers_gained"], d["revenue_usd"]))
            written += 1
    return written


def fetch_real(store: Store, cfg) -> int:  # pragma: no cover - needs OAuth + a live channel
    """REAL MODE (not tested in this build): pull per-video daily metrics from YouTube Analytics API.

    Requires the yt-analytics.readonly and yt-analytics-monetary.readonly scopes.
    """
    from tools.youtube_auth import get_credentials
    from googleapiclient.discovery import build

    creds = get_credentials()
    ya = build("youtubeAnalytics", "v2", credentials=creds)
    n = 0
    for up in store.q("SELECT * FROM uploads WHERE backend='youtube'"):
        res = ya.reports().query(
            ids="channel==MINE", startDate=up["uploaded_at"][:10], endDate="today",
            metrics="views,impressions,estimatedMinutesWatched,averageViewPercentage,subscribersGained,estimatedRevenue",
            dimensions="day", filters=f"video=={up['youtube_id']}").execute()
        for i, row in enumerate(res.get("rows", [])):
            store.x("INSERT OR REPLACE INTO daily_stats VALUES (?,?,?,?,?,?,?,?)",
                    (up["episode_id"], i, row[1], row[2], row[3] / 60.0, row[4] / 100.0, row[5], row[6]))
            n += 1
    return n


def per_video_totals(store: Store) -> list[dict]:
    rows = store.q("""
        SELECT e.id, e.week, e.topic, e.category, json_extract(e.metadata_json,'$.titles[0]') AS title,
               COUNT(d.sim_day) AS days_live, COALESCE(SUM(d.views),0) AS views,
               COALESCE(SUM(d.impressions),0) AS impressions, COALESCE(SUM(d.watch_hours),0) AS watch_hours,
               COALESCE(AVG(d.avg_view_pct),0) AS avg_view_pct,
               COALESCE(SUM(d.subscribers_gained),0) AS subscribers, COALESCE(SUM(d.revenue_usd),0) AS revenue_usd
        FROM episodes e JOIN uploads u ON u.episode_id = e.id
        LEFT JOIN daily_stats d ON d.episode_id = e.id
        GROUP BY e.id ORDER BY e.week, e.slot""")
    out = []
    for r in rows:
        d = dict(r)
        d["ctr"] = round(d["views"] / d["impressions"], 4) if d["impressions"] else 0.0
        d["watch_hours"] = round(d["watch_hours"], 2)
        d["avg_view_pct"] = round(d["avg_view_pct"], 3)
        d["revenue_usd"] = round(d["revenue_usd"], 2)
        out.append(d)
    return out
