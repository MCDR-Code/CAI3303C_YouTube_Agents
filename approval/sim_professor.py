"""SIMULATED professor, used only by `python main.py simulate` for the demo weeks.

It makes its decisions through the same gate function as the review page,
and every decision it makes is labeled "SIMULATED professor (demo)" in the
database, the reports and the review page. It never runs in a normal week.
"""
from __future__ import annotations

from approval.gate import record_decision
from tools.storage import Store

LABEL = "SIMULATED professor (demo)"

# Scripted demo decisions: (week, slot, revision) -> (decision, notes).
# Anything not listed is approved.
SCRIPT = {
    (1, 2, 1): ("changes_requested", "Make it shorter and add a real example from my classroom."),
    (2, 3, 1): ("rejected", "I already cover this topic in class this semester; skip it for now."),
}


def review_pending(store: Store) -> list[dict]:
    out = []
    for ep in store.episodes(status="pending_review"):
        decision, notes = SCRIPT.get((ep["week"], ep["slot"], ep["revision"]), ("approved", "Looks good."))
        fc = ep.get("factcheck") or {}
        if fc.get("rounds") and not fc.get("passed"):
            decision, notes = "changes_requested", "The fact-check still has open issues. Fix them first."
        out.append(record_decision(store, ep["id"], decision, notes, LABEL))
        print(f"   {LABEL}: {ep['id']} r{ep['revision']} -> {decision}" + (f" ({notes})" if notes else ""))
    return out
