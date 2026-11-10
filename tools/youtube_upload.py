"""Uploader. Refuses unless the approval gate passes. Every upload is PRIVATE.

Mock: writes the exact request that would be sent to YouTube to
output/uploads/<episode>.json and returns a fake video ID.
Real: YouTube Data API v3 videos.insert + thumbnails.set + captions.insert.
"""
from __future__ import annotations

import json
import uuid

from approval.gate import can_upload
from tools.storage import Store, now

PRIVACY = "private"   # fixed. The professor makes a video public in YouTube Studio.


def build_request(ep: dict) -> dict:
    meta = ep["metadata"]
    return {
        "snippet": {
            "title": meta["titles"][0][:100],
            "description": meta["description"][:5000],
            "tags": meta["tags"],
            "categoryId": "27",               # Education
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": PRIVACY,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,    # synthetic (AI) voice disclosure
        },
        "media": {"video": ep["video_path"], "thumbnail": ep["thumbnail_path"], "captions": ep["srt_path"]},
    }


def upload(cfg, store: Store, ep_id: str, sim_day: int | None = None) -> dict:
    ok, why = can_upload(store, ep_id)
    if not ok:
        store.log("uploader", f"REFUSED: {why}", None, ep_id)
        return {"ok": False, "reason": why}
    ep = store.episode(ep_id)
    req = build_request(ep)
    assert req["status"]["privacyStatus"] == "private"
    if cfg.backends["upload"] == "mock":
        vid = "MOCK-" + uuid.uuid4().hex[:11]
        d = cfg.output_dir / "uploads"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{ep_id}.json").write_text(json.dumps({"video_id": vid, "request": req, "gate": why}, indent=2),
                                         encoding="utf-8")
    else:
        vid = _real_upload(req)
    if sim_day is None:
        sim_day = ep["week"] * cfg["simulation"]["days_per_week"] - 3
    store.x("INSERT INTO uploads (episode_id, youtube_id, privacy, backend, uploaded_at, sim_day) VALUES (?,?,?,?,?,?)",
            (ep_id, vid, PRIVACY, cfg.backends["upload"], now(), sim_day))
    store.update_episode(ep_id, status="uploaded")
    store.log("uploader", f"uploaded as {PRIVACY} -> {vid} ({why})", ep["week"], ep_id)
    return {"ok": True, "video_id": vid, "privacy": PRIVACY}


def _real_upload(req: dict) -> str:  # pragma: no cover - needs OAuth and a real channel
    """REAL MODE (not tested in this build)."""
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.discovery import build

    from tools.youtube_auth import get_credentials

    yt = build("youtube", "v3", credentials=get_credentials())
    media = req.pop("media")
    res = yt.videos().insert(part="snippet,status", body=req,
                             media_body=MediaFileUpload(media["video"], chunksize=-1, resumable=True)).execute()
    vid = res["id"]
    yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(media["thumbnail"])).execute()
    yt.captions().insert(part="snippet", body={"snippet": {"videoId": vid, "language": "en", "name": "English"}},
                         media_body=MediaFileUpload(media["captions"])).execute()
    return vid
