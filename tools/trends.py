"""Trend research. Mock: seeded fake demand data. Real: YouTube Data API search."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone


def search(cfg, week: int, query: str) -> list[dict]:
    if cfg.backends["channel_stats"] == "mock":
        from mock.fake_data import trending

        return trending(week, cfg["simulation"]["seed"], query)
    return _youtube_search(query)


def _youtube_search(query: str) -> list[dict]:
    """REAL MODE (not tested in this build): rank recent popular videos for a query.

    Uses the public YouTube Data API v3 with an API key. The LLM agent turns these
    raw results into topic findings.
    """
    from googleapiclient.discovery import build

    yt = build("youtube", "v3", developerKey=os.environ["YOUTUBE_API_KEY"])
    since = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat().replace("+00:00", "Z")
    res = yt.search().list(q=query or "artificial intelligence explained", part="snippet", type="video",
                           order="viewCount", publishedAfter=since, maxResults=25,
                           relevanceLanguage="en").execute()
    return [{"title": it["snippet"]["title"], "channel": it["snippet"]["channelTitle"],
             "published": it["snippet"]["publishedAt"], "source": "YouTube Data API"}
            for it in res.get("items", [])]
