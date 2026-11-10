"""Run with:  python -m pytest -q

Checks the rules that must never break: no upload without approval, uploads
are private, a revision cancels an old approval, and the agent handoff chain
produces a complete package in mock mode.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from agents_system import pipeline
from agents_system.config import ROOT, load_config
from approval.gate import GateError, can_upload, record_decision
from tools.storage import Store, abspath
from tools.youtube_upload import upload


@pytest.fixture()
def env(tmp_path: Path):
    raw = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    raw["mode"] = "mock"
    raw["backends"]["tts"] = "silent"          # fast tests
    raw["paths"]["output_dir"] = str(tmp_path / "output")
    raw["paths"]["db_path"] = str(tmp_path / "test.db")
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml.safe_dump(raw), encoding="utf-8")
    cfg = load_config(cfg_file)
    store = Store(cfg.path("db_path"))
    eps = pipeline.plan_week(cfg, store, 1)
    pipeline.produce_episode(cfg, store, eps[0])
    yield cfg, store, eps[0]
    shutil.rmtree(tmp_path, ignore_errors=True)


def test_agents_build_a_complete_package(env):
    cfg, store, ep_id = env
    ep = store.episode(ep_id)
    assert ep["status"] == "pending_review"
    assert ep["script"]["scenes"] and ep["metadata"]["titles"] and ep["visuals"]["thumbnail"]
    assert abspath(ep["video_path"]).exists() and abspath(ep["srt_path"]).exists()
    agents = {r[0] for r in store.q("SELECT DISTINCT agent FROM ai_costs")}
    assert {"producer", "trend_researcher", "topic_strategist", "scriptwriter", "fact_checker",
            "seo_metadata", "visual_designer"} <= agents


def test_no_upload_without_approval(env):
    cfg, store, ep_id = env
    res = upload(cfg, store, ep_id)
    assert not res["ok"] and "approval" in res["reason"]
    assert store.one("SELECT COUNT(*) FROM uploads")[0] == 0


def test_rejected_video_never_uploads(env):
    cfg, store, ep_id = env
    record_decision(store, ep_id, "rejected", "no", "Professor")
    assert not upload(cfg, store, ep_id)["ok"]


def test_change_request_needs_notes(env):
    _, store, ep_id = env
    with pytest.raises(GateError):
        record_decision(store, ep_id, "changes_requested", "   ", "Professor")


def test_approved_upload_is_private(env):
    cfg, store, ep_id = env
    record_decision(store, ep_id, "approved", "", "Professor")
    res = upload(cfg, store, ep_id)
    assert res["ok"] and res["privacy"] == "private"
    assert store.one("SELECT privacy FROM uploads WHERE episode_id=?", (ep_id,))[0] == "private"
    assert not upload(cfg, store, ep_id)["ok"]          # no double upload


def test_revision_cancels_old_approval(env):
    _, store, ep_id = env
    record_decision(store, ep_id, "approved", "", "Professor")
    store.update_episode(ep_id, revision=2, status="approved")   # something changed after approval
    ok, why = can_upload(store, ep_id)
    assert not ok and "revision" in why


def test_public_privacy_is_refused(tmp_path):
    raw = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    raw["channel"]["upload_privacy"] = "public"
    f = tmp_path / "c.yaml"
    f.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(f)
