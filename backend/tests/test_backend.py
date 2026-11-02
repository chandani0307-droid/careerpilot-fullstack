"""FastAPI smoke tests with fake job sources (no live network calls)."""
from tests.conftest_env import fresh_db  # noqa: E402

fresh_db()
import json  # noqa: E402
import os  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from services import search  # noqa: E402

import main  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

client = TestClient(main.app)


def _fake_http(url, params=None, headers=None, timeout=None):
    if "remotive" in url:
        return json.dumps({"jobs": [{"title": "Python Backend Engineer", "company_name": "Nimbus Labs",
                                     "candidate_required_location": "Bengaluru, India", "url": "https://example.com/j/1",
                                     "description": "Build with Python and Docker", "tags": ["python"],
                                     "category": "Software Development", "publication_date": "2026-11-01",
                                     "job_type": "full_time"}]})
    if "weworkremotely" in url or "remoteok.com/rss" in url:
        return "<rss><channel><item><title>RssCo: Python Remote Developer</title><link>https://wwr.example/1</link><description>Python</description><pubDate>Mon, 06 Oct 2025 10:00:00 +0000</pubDate></item></channel></rss>"
    raise OSError("fake source down")


search.http_get = _fake_http


def _signup(email="test@example.com"):
    r = client.post("/api/auth/signup", json={"email": email, "password": "secret123", "name": "Test User"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_health_lists_only_free_sources():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["sources"] == ["Remotive", "RemoteOK", "Arbeitnow", "Jobicy", "Himalayas", "The Muse", "RSS"]
    assert "Adzuna" not in r.json()["sources"] and "JSearch" not in r.json()["sources"]


def test_signup_login_me_and_search_save_apply_flow():
    token = _signup()
    headers = {"Authorization": f"Bearer {token}"}
    r = client.get("/api/auth/me", headers=headers)
    assert r.status_code == 200 and r.json()["user"]["email"] == "test@example.com"

    r = client.get("/api/jobs/search", params={"q": "python developer", "limit": 60}, headers=headers)
    assert r.status_code == 200, r.text
    jobs = r.json()["jobs"]
    assert jobs, "search must return jobs (live fake + clearly marked samples)"
    assert all(j["source"] != "Adzuna" and j["source"] != "JSearch" for j in jobs)
    job = jobs[0]

    r = client.post("/api/jobs/save", json={"job": job}, headers=headers)
    assert r.status_code == 200 and r.json()["saved"] is True
    r = client.get("/api/jobs/saved", headers=headers)
    assert any(j["id"] == job["id"] for j in r.json()["jobs"])

    r = client.post("/api/jobs/apply", json={"job": job}, headers=headers)
    assert r.status_code == 200
    app_id = r.json()["application_id"]
    r = client.get(f"/api/applications/{app_id}", headers=headers)
    assert r.status_code == 200 and r.json()["application"]["status"] == "applied"
    r = client.patch(f"/api/applications/{app_id}", json={"status": "interview"}, headers=headers)
    assert r.json()["application"]["status"] == "interview"
    r = client.get(f"/api/applications/{app_id}/events", headers=headers)
    assert len(r.json()["events"]) >= 2


def test_profile_and_ai_work_without_gemini_key():
    token = _signup("ai@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post("/api/profile/text", json={"resume_text": open(os.path.join(ROOT, "sample_resume.txt")).read(), "filename": "sample_resume.txt"}, headers=headers)
    assert r.status_code == 200, r.text
    assert "Python" in r.json()["profile"]["data"]["skills"]

    job = {"id": "x", "title": "Python Backend Engineer", "company": "Nimbus Labs",
           "description": "Build APIs with Python, FastAPI and PostgreSQL.", "tags": ["Python", "FastAPI"]}
    r = client.post("/api/ai/cover-letter", json={"job": job, "tone": "professional"}, headers=headers)
    assert r.status_code == 200 and "Nimbus Labs" in r.json()["text"]
    assert r.json()["ai"] is False, "no Gemini key set, so the template fallback must be used"
    r = client.post("/api/ai/interview-prep", json={"job": job}, headers=headers)
    assert r.status_code == 200 and len(r.json()["questions"]) >= 6
    r = client.post("/api/ai/assistant", json={"messages": [{"role": "user", "content": "summarise my resume"}]}, headers=headers)
    assert r.status_code == 200 and r.json()["reply"]

    r = client.get("/api/settings/status", headers=headers)
    assert r.status_code == 200
    assert r.json()["free"] is True and r.json()["gemini"]["available"] is False
    r = client.get("/api/dashboard", headers=headers)
    assert r.status_code == 200 and r.json()["summary"]["applications"] == 0


def test_unauthenticated_is_rejected():
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/applications").status_code == 401
    # search works without login too (no profile scoring), but still only free sources
    r = client.get("/api/jobs/search", params={"q": "python"})
    assert r.status_code == 200
