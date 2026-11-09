"""SQLite storage: episodes, approval decisions, uploads, AI cost ledger, stats, plans."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS weeks (
    week INTEGER PRIMARY KEY,
    start_date TEXT,
    plan_json TEXT,            -- business manager's plan FOR this week
    research_json TEXT,
    insights_json TEXT,        -- analytics findings written at the end of this week
    report_path TEXT
);
CREATE TABLE IF NOT EXISTS episodes (
    id TEXT PRIMARY KEY,       -- e.g. W01E02
    week INTEGER,
    slot INTEGER,
    topic_id TEXT,
    topic TEXT,
    category TEXT,
    brief_json TEXT,
    script_json TEXT,
    factcheck_json TEXT,
    metadata_json TEXT,
    visuals_json TEXT,
    video_path TEXT,
    srt_path TEXT,
    thumbnail_path TEXT,
    duration_sec REAL,
    status TEXT,               -- planned, scripted, packaged, pending_review,
                               -- changes_requested, approved, rejected, uploaded
    revision INTEGER DEFAULT 1,
    review_notes TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id TEXT,
    revision INTEGER,
    decision TEXT,             -- approved | rejected | changes_requested
    notes TEXT,
    decided_by TEXT,
    decided_at TEXT
);
CREATE TABLE IF NOT EXISTS uploads (
    episode_id TEXT PRIMARY KEY,
    youtube_id TEXT,
    privacy TEXT,
    backend TEXT,
    uploaded_at TEXT,
    sim_day INTEGER            -- simulated day index the video went live
);
CREATE TABLE IF NOT EXISTS ai_costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    week INTEGER,
    episode_id TEXT,           -- NULL = shared weekly work (planning, analytics)
    agent TEXT,                -- agent name, or 'media' for TTS / images
    kind TEXT,                 -- chat | tts | image
    model TEXT,
    backend TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL
);
CREATE TABLE IF NOT EXISTS daily_stats (
    episode_id TEXT,
    sim_day INTEGER,
    views INTEGER,
    impressions INTEGER,
    watch_hours REAL,
    avg_view_pct REAL,
    subscribers_gained INTEGER,
    revenue_usd REAL,
    PRIMARY KEY (episode_id, sim_day)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    week INTEGER,
    episode_id TEXT,
    actor TEXT,
    message TEXT
);
"""


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Store:
    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.con = sqlite3.connect(self.path, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)
        self.con.commit()

    # ---- generic -------------------------------------------------------
    def q(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        return list(self.con.execute(sql, args))

    def one(self, sql: str, args: tuple = ()) -> sqlite3.Row | None:
        rows = self.q(sql, args)
        return rows[0] if rows else None

    def x(self, sql: str, args: tuple = ()) -> None:
        self.con.execute(sql, args)
        self.con.commit()

    def log(self, actor: str, message: str, week: int | None = None, episode_id: str | None = None) -> None:
        self.x("INSERT INTO events (ts, week, episode_id, actor, message) VALUES (?,?,?,?,?)",
               (now(), week, episode_id, actor, message))

    # ---- weeks ---------------------------------------------------------
    def ensure_week(self, week: int, start_date: str) -> None:
        self.x("INSERT OR IGNORE INTO weeks (week, start_date) VALUES (?,?)", (week, start_date))

    def set_week_json(self, week: int, column: str, value: Any) -> None:
        assert column in {"plan_json", "research_json", "insights_json"}
        self.x(f"UPDATE weeks SET {column}=? WHERE week=?", (json.dumps(value), week))

    def week_json(self, week: int, column: str) -> Any:
        row = self.one(f"SELECT {column} FROM weeks WHERE week=?", (week,))
        return json.loads(row[0]) if row and row[0] else None

    def latest_week(self) -> int:
        row = self.one("SELECT MAX(week) FROM weeks")
        return row[0] or 0

    # ---- episodes ------------------------------------------------------
    def create_episode(self, ep_id: str, week: int, slot: int, brief: dict) -> None:
        self.x(
            "INSERT OR REPLACE INTO episodes (id, week, slot, topic_id, topic, category, brief_json, status,"
            " revision, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,1,?,?)",
            (ep_id, week, slot, brief.get("topic_id"), brief["topic"], brief.get("category", ""),
             json.dumps(brief), "planned", now(), now()),
        )

    def episode(self, ep_id: str) -> dict | None:
        row = self.one("SELECT * FROM episodes WHERE id=?", (ep_id,))
        if not row:
            return None
        d = dict(row)
        for k in ("brief_json", "script_json", "factcheck_json", "metadata_json", "visuals_json"):
            d[k[:-5]] = json.loads(d[k]) if d[k] else None
        return d

    def episodes(self, week: int | None = None, status: str | None = None) -> list[dict]:
        sql, args = "SELECT id FROM episodes WHERE 1=1", []
        if week is not None:
            sql += " AND week=?"
            args.append(week)
        if status is not None:
            sql += " AND status=?"
            args.append(status)
        sql += " ORDER BY week, slot"
        return [self.episode(r[0]) for r in self.q(sql, tuple(args))]

    def update_episode(self, ep_id: str, **fields: Any) -> None:
        sets, args = [], []
        for k, v in fields.items():
            if k in ("brief", "script", "factcheck", "metadata", "visuals"):
                k, v = k + "_json", json.dumps(v)
            sets.append(f"{k}=?")
            args.append(v)
        sets.append("updated_at=?")
        args.append(now())
        args.append(ep_id)
        self.x(f"UPDATE episodes SET {', '.join(sets)} WHERE id=?", tuple(args))

    # ---- decisions -----------------------------------------------------
    def latest_decision(self, ep_id: str) -> dict | None:
        row = self.one("SELECT * FROM decisions WHERE episode_id=? ORDER BY id DESC LIMIT 1", (ep_id,))
        return dict(row) if row else None

    # ---- costs ---------------------------------------------------------
    def add_cost(self, week: int, episode_id: str | None, agent: str, kind: str, model: str,
                 backend: str, input_tokens: int, output_tokens: int, cost_usd: float) -> None:
        self.x(
            "INSERT INTO ai_costs (ts, week, episode_id, agent, kind, model, backend, input_tokens,"
            " output_tokens, cost_usd) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (now(), week, episode_id, agent, kind, model, backend, input_tokens, output_tokens, cost_usd),
        )

    def agent_spend(self, agent: str, week: int) -> float:
        row = self.one("SELECT COALESCE(SUM(cost_usd),0) FROM ai_costs WHERE agent=? AND week=?", (agent, week))
        return float(row[0])
