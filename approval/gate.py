"""The approval gate. Plain Python, not an agent, so no LLM can talk its way past it.

Only three decisions exist: approved, changes_requested, rejected.
A decision applies to one revision of a video. If the video is revised after
approval, the old approval no longer counts.
"""
from __future__ import annotations

from pathlib import Path

from tools.storage import Store, now

DECISIONS = {"approved", "changes_requested", "rejected"}


class GateError(Exception):
    pass


def record_decision(store: Store, ep_id: str, decision: str, notes: str, decided_by: str) -> dict:
    ep = store.episode(ep_id)
    if not ep:
        raise GateError(f"No episode {ep_id}")
    if decision not in DECISIONS:
        raise GateError(f"Decision must be one of {sorted(DECISIONS)}")
    if ep["status"] != "pending_review":
        raise GateError(f"{ep_id} is '{ep['status']}', not waiting for review")
    if decision == "changes_requested" and not notes.strip():
        raise GateError("Please write what should change.")
    store.x("INSERT INTO decisions (episode_id, revision, decision, notes, decided_by, decided_at) "
            "VALUES (?,?,?,?,?,?)", (ep_id, ep["revision"], decision, notes.strip(), decided_by, now()))
    fields = {"status": decision}
    if decision == "changes_requested":
        fields["review_notes"] = notes.strip()
    store.update_episode(ep_id, **fields)
    store.log(decided_by, f"{decision} r{ep['revision']}" + (f": {notes.strip()}" if notes.strip() else ""),
              ep["week"], ep_id)
    return {"episode_id": ep_id, "decision": decision, "revision": ep["revision"]}


def can_upload(store: Store, ep_id: str) -> tuple[bool, str]:
    """Every rule must pass. Called by the uploader immediately before any upload."""
    ep = store.episode(ep_id)
    if not ep:
        return False, "episode not found"
    if store.one("SELECT 1 FROM uploads WHERE episode_id=?", (ep_id,)):
        return False, "already uploaded"
    d = store.latest_decision(ep_id)
    if not d or d["decision"] != "approved":
        return False, "no professor approval on record"
    if d["revision"] != ep["revision"]:
        return False, f"approval was for revision {d['revision']}, current is {ep['revision']}"
    if ep["status"] != "approved":
        return False, f"status is '{ep['status']}'"
    if not ep.get("video_path") or not Path(ep["video_path"]).exists():
        return False, "video file missing"
    return True, f"approved by {d['decided_by']} at {d['decided_at']}"
