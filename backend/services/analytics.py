"""Numbers and chart data for the dashboard and analytics pages (everything is for one user)."""
from collections import Counter
from datetime import datetime, timedelta, timezone

from core.util import today
from services import store
from services.search import attach_match
from services.skills import extract_skills


def summary(user_id: str) -> dict:
    apps, profile = store.list_applications(user_id), store.profile_data(user_id) or {}
    reached = Counter()
    for app in apps:
        for status in {e["status"] for e in store.events(user_id, app["id"])} | {app["status"]}:
            reached[status] += 1
    applied = sum(1 for a in apps if a["status"] != "saved")
    responded = sum(1 for a in apps if a["status"] in ("screening", "interview", "offer"))
    scores = [a["match_score"] for a in apps if a["match_score"]]

    week_start = datetime.now(timezone.utc).date() - timedelta(days=datetime.now(timezone.utc).weekday())
    weekly = {(week_start - timedelta(weeks=i)).isoformat(): 0 for i in range(7, -1, -1)}
    for app in apps:
        if app["applied_at"]:
            day = datetime.strptime(app["applied_at"], "%Y-%m-%d").date()
            monday = (day - timedelta(days=day.weekday())).isoformat()
            if monday in weekly:
                weekly[monday] += 1

    results = attach_match(store.load_results(user_id), profile) if profile else store.load_results(user_id)
    mine = {s.lower() for s in profile.get("skills") or []}
    demand, gaps = Counter(), Counter()
    for job in results:
        demand.update(set(extract_skills(f"{job['title']} {' '.join(job['tags'])} {job['description'][:1500]}")))
        gaps.update(job.get("missing") or [])
    due = [a for a in apps if a["follow_up"] and a["follow_up"] <= today() and a["status"] in ("applied", "screening", "interview")]
    stats = store.search_stats(user_id)
    return {
        "applications": len(apps), "applied": applied, "interviews": reached["interview"], "offers": reached["offer"], "saved": len(store.saved_ids(user_id)),
        "total_searches": stats["total_searches"], "total_jobs_found": stats["total_jobs_found"], "last_search": stats["last_search"],
        "response_rate": round(100 * responded / applied) if applied else 0, "avg_match": round(sum(scores) / len(scores)) if scores else 0,
        "by_status": {s: sum(1 for a in apps if a["status"] == s) for s in store.STATUSES},
        "funnel": {"Applied": applied, "Screening": reached["screening"] + reached["interview"] * 0, "Interview": reached["interview"], "Offer": reached["offer"]},
        "weekly": weekly, "by_region": dict(Counter(j["region"] for j in results)), "by_source": dict(Counter(j["source"] for j in results)),
        "gaps": dict(gaps.most_common(8)), "demand": [{"skill": s, "count": c, "have": s.lower() in mine} for s, c in demand.most_common(10)], "due": due,
        "results": len(results),
    }
