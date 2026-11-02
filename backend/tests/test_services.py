from tests.conftest_env import fresh_db  # noqa: E402

fresh_db()
import json  # noqa: E402
import os  # noqa: E402
import threading  # noqa: E402
from http.server import BaseHTTPRequestHandler, HTTPServer  # noqa: E402

from core import auth  # noqa: E402
from services import agent, analytics, search, store, writer  # noqa: E402
from services.llm import llm  # noqa: E402
from tests import test_search as fixtures  # noqa: E402

RESUME = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_resume.txt"), encoding="utf-8").read()
JOB = {"id": "j1", "title": "Python Backend Engineer", "company": "Nimbus Labs", "location": "Bengaluru, India", "region": "india", "url": "https://x", "apply_url": "https://x/apply", "description": "Build APIs",
       "tags": ["Python", "FastAPI"], "matched": ["Python", "FastAPI"], "missing": ["Kafka"], "score": 90}


def setup_user(email="u@example.com"):
    uid = auth.signup(email, "secret123")["id"]
    store.save_profile(uid, "sample_resume.txt", RESUME, writer.analyze_resume(RESUME, "sample_resume.txt", uid))
    return uid


def test_resume_analysis_works_without_ai():
    for var in ("GEMINI_API_KEY",):
        os.environ.pop(var, None)
    profile = writer.analyze_resume(RESUME, "sample_resume.txt")
    assert profile["name"] and "Python" in profile["skills"] and profile["summary"] and profile["strengths"] and profile["gaps"] and profile["ai_enhanced"] is False


def test_gemini_client_parses_the_real_response_shape_and_enforces_daily_limit():
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            body = json.loads(self.rfile.read(length))
            assert self.headers["x-goog-api-key"] == "test-key" and body["systemInstruction"]["parts"][0]["text"]
            wants_json = body["generationConfig"].get("responseMimeType") == "application/json"
            text = '{"subject": "Hello", "body": "World body text"}' if wants_json else "Plain AI text"
            out = json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(out)
        def log_message(self, *a): pass
    server = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    os.environ.update(GEMINI_API_KEY="test-key", GEMINI_BASE=f"http://127.0.0.1:{server.server_port}", DAILY_AI_LIMIT="2")
    uid = auth.signup("ai@example.com", "secret123")["id"]
    assert llm.complete("sys", "hi", uid) == "Plain AI text"
    assert llm.json("sys", "hi", uid) == {"subject": "Hello", "body": "World body text"}
    assert llm.complete("sys", "third call", uid) is None and "limit" in llm.last_error.lower()
    assert llm.complete("sys", "no user, no limit") == "Plain AI text"
    server.shutdown()
    for var in ("GEMINI_API_KEY", "GEMINI_BASE", "DAILY_AI_LIMIT"):
        os.environ.pop(var, None)
    assert llm.complete("s", "p") is None  # no key: templates are used


def test_writers_fall_back_to_good_templates():
    profile = {"name": "Aarav Mehta", "skills": ["Python", "SQL"], "experience_years": 3, "target_roles": ["Backend Engineer"]}
    letter = writer.cover_letter(profile, JOB)
    assert "Nimbus Labs" in letter and "Aarav Mehta" in letter and "Python" in letter
    mail = writer.draft_email(profile, JOB)
    assert "Python Backend Engineer" in mail["subject"] and len(writer.draft_linkedin(profile, JOB)) <= 300
    assert "Kafka" in " ".join(writer.tailor_tips(profile, JOB)["tips"]) and writer.tailor_tips(profile, JOB)["keywords"][:2] == ["Python", "FastAPI"]
    weak, strong = writer.practice_feedback("Tell me about a project", "I did stuff."), writer.practice_feedback(
        "Tell me about a project", "The situation was a slow report. My task was to speed it up. I took action by adding indexes and caching, and the result was a 40% faster report, so the team saved 5 hours a week. I learned to measure first. " * 2)
    assert strong["score"] > weak["score"] and weak["improve"]
    assert "upload" in writer.assistant_reply(None, [{"role": "user", "content": "hi"}], {}).lower()


def test_autopilot_runs_all_seven_agents_and_creates_drafts_only_for_this_user():
    fixtures.setup_module_env()
    uid, other = setup_user("agent@example.com"), auth.signup("other@example.com", "secret123")["id"]
    seen = []
    result = agent.run_agent(uid, {"query": "python developer", "region": "all", "scan": 60, "prepare": 3}, on_step=seen.append)
    assert result["status"] == "waiting_approval" and [t["agent"] for t in result["trace"]] == agent.STEPS and len(seen) == 7
    assert result["summary"]["scanned"] == 60 and len(result["summary"]["top"]) == 3 and result["summary"]["interview"]["questions"]
    drafts = store.list_drafts(uid)
    assert sorted(d["kind"] for d in drafts) == ["apply"] * 3 + ["email"] * 3 + ["linkedin"] * 3
    assert all(d["status"] == "draft" for d in drafts), "agents must never send anything"
    assert store.list_drafts(other) == [] and store.load_results(other) == [] and len(store.load_results(uid)) == 60
    again = agent.run_agent(uid, {"query": "python developer", "region": "all", "scan": 60, "prepare": 3})
    assert len(store.list_drafts(uid)) == 9, "running again must not duplicate drafts"
    assert store.last_run(uid)["id"] == again["id"]


def test_autopilot_stops_politely_without_a_resume():
    uid = auth.signup("noresume@example.com", "secret123")["id"]
    result = agent.run_agent(uid, {"query": "python"})
    assert result["status"] == "blocked" and [t["agent"] for t in result["trace"]] == ["Planner"] and store.list_drafts(uid) == []


def test_analytics_numbers():
    fixtures.setup_module_env()
    uid = setup_user("stats@example.com")
    agent.run_agent(uid, {"query": "python developer", "region": "all", "scan": 40, "prepare": 2})
    job = store.load_results(uid)[0]
    a1 = store.add_application(uid, {**job, "score": 80}, status="applied", follow_up="2020-01-01")
    a2 = store.add_application(uid, {**store.load_results(uid)[1], "score": 60}, status="applied")
    store.set_status(uid, a1, "interview")
    store.set_status(uid, a2, "rejected")
    s = analytics.summary(uid)
    assert s["applications"] == 2 and s["applied"] == 2 and s["interviews"] == 1 and s["response_rate"] == 50 and s["avg_match"] == 70
    assert sum(s["weekly"].values()) == 2 and len(s["weekly"]) == 8 and s["by_status"]["interview"] == 1 and s["results"] == 40
    assert [a["id"] for a in s["due"]] == [a1] and s["demand"] and s["by_source"]
