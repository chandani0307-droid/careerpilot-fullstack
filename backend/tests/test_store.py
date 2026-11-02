from tests.conftest_env import fresh_db  # noqa: E402

fresh_db()
from core import auth, db  # noqa: E402
from services import store  # noqa: E402

JOB = {"id": "job1", "title": "Python Developer", "company": "Acme", "location": "Pune, India", "region": "india", "url": "https://x/1", "apply_url": "https://x/apply/1", "description": "Build things",
       "source": "Test", "tags": ["python"], "salary": "", "posted_at": "2026-01-01", "job_type": "full-time", "level": "mid", "relevance": 77.0, "score": 81}


def two_users():
    return auth.signup("a@example.com", "secret123")["id"], auth.signup("b@example.com", "secret123")["id"]


def test_profile_roundtrip_and_isolation():
    a, b = two_users()
    store.save_profile(a, "cv.txt", "resume text", {"skills": ["Python"], "name": "A"})
    assert store.profile_data(a)["skills"] == ["Python"] and store.profile_data(b) is None
    store.patch_profile(a, headline="Backend dev")
    assert store.profile_data(a) == {"skills": ["Python"], "name": "A", "headline": "Backend dev"}


def test_results_saved_jobs_and_history_are_per_user():
    a, b = two_users()
    store.save_results(a, [JOB], "python", "india", "pune")
    assert [j["id"] for j in store.load_results(a)] == ["job1"] and store.load_results(b) == []
    assert store.toggle_saved(a, "job1") is True and store.saved_ids(a) == {"job1"} and store.saved_ids(b) == set()
    assert store.toggle_saved(a, "job1") is False and store.saved_ids(a) == set()
    assert store.recent_searches(a)[0]["query"] == "python" and store.recent_searches(b) == []
    store.save_results(a, [], "python", "india", "pune")  # a new search replaces old results
    assert store.load_results(a) == []


def test_application_flow_status_events_and_isolation():
    a, b = two_users()
    store.upsert_jobs([JOB])
    app_id = store.add_application(a, JOB, status="saved")
    assert store.add_application(a, JOB) == app_id, "the same job must not be tracked twice"
    assert store.get_application(b, app_id) is None, "another user must not see it"
    store.set_status(a, app_id, "applied", "Sent via portal")
    store.set_status(a, app_id, "interview")
    app = store.get_application(a, app_id)
    assert app["status"] == "interview" and app["applied_at"] and app["match_score"] == 81
    assert [e["status"] for e in store.events(a, app_id)] == ["saved", "applied", "interview"]
    store.set_status(b, app_id, "offer")  # wrong user: nothing happens
    assert store.get_application(a, app_id)["status"] == "interview"
    store.update_application(a, app_id, notes="Call on Monday", follow_up="2026-02-01", status="hacked")
    assert store.get_application(a, app_id)["notes"] == "Call on Monday" and store.get_application(a, app_id)["status"] == "interview"
    store.delete_application(b, app_id)
    assert store.get_application(a, app_id) is not None
    store.delete_application(a, app_id)
    assert store.list_applications(a) == [] and store.events(a, app_id) == []


def test_drafts_replace_open_ones_and_track_approval():
    a, b = two_users()
    d1 = store.save_draft(a, "job1", "email", "Email", "Hi", "Body 1", "hr@acme.com")
    d2 = store.save_draft(a, "job1", "email", "Email", "Hi 2", "Body 2", "hr@acme.com")
    assert d1 == d2 and store.list_drafts(a)[0]["body"] == "Body 2" and store.list_drafts(b) == []
    store.update_draft(a, d1, body="Edited", status="executed")  # status cannot be changed this way
    assert store.get_draft(a, d1)["body"] == "Edited" and store.get_draft(a, d1)["status"] == "draft"
    store.set_draft_status(a, d1, "executed", {"message": "ok"})
    assert store.get_draft(a, d1)["result"]["message"] == "ok" and store.list_drafts(a, status="draft") == []
    d3 = store.save_draft(a, "job1", "email", "Email", "New", "New body")
    assert d3 != d1, "an approved draft is history; a new draft is a new row"


def test_ai_daily_limit_and_export():
    a, _ = two_users()
    assert [store.bump_usage(a, 2) for _ in range(3)] == [True, True, False] and store.usage_today(a) == 2
    store.save_profile(a, "cv.txt", "t", {"name": "A"})
    exported = store.export_all(a)
    assert exported["profile"]["data"]["name"] == "A" and set(exported) == {"profile", "applications", "saved_jobs", "drafts", "searches"}
