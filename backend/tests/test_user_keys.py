"""Each user can bring their own free Gemini key (Settings page).

The key is encrypted at rest, never returned in full, isolated per user,
and — when set — used for that user's AI calls on their own quota, with no
shared daily limit. Without any key, templates are used.
"""
from tests.conftest_env import fresh_db  # noqa: E402

fresh_db()
import json  # noqa: E402
import os  # noqa: E402
import threading  # noqa: E402
from http.server import BaseHTTPRequestHandler, HTTPServer  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from core import auth, db  # noqa: E402
from services import llm as llm_mod  # noqa: E402
from services import store  # noqa: E402

import main  # noqa: E402

llm = llm_mod.llm
client = TestClient(main.app)
OWN_KEY = "AIzaSyTestKey1234567890abcdef"  # fake key, last 4 chars: cdef
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _user(email="keyuser@example.com"):
    return auth.signup(email, "secret123")["id"]


def test_key_is_encrypted_at_rest_masked_and_isolated():
    uid_a, uid_b = _user("a@example.com"), _user("b@example.com")
    store.save_user_gemini_key(uid_a, OWN_KEY)
    row = db.one("SELECT gemini_key_enc FROM user_keys WHERE user_id = ?", (uid_a,))
    assert row and row["gemini_key_enc"] != OWN_KEY and "AIza" not in row["gemini_key_enc"]
    assert store.get_user_gemini_key(uid_a) == OWN_KEY
    assert store.user_gemini_key_masked(uid_a) == "••••cdef"
    assert store.get_user_gemini_key(uid_b) is None and store.user_gemini_key_masked(uid_b) is None
    store.delete_user_gemini_key(uid_a)
    assert store.get_user_gemini_key(uid_a) is None


def _fake_gemini_server(expect_key=None):
    """Fake Gemini that records every API key it receives. If expect_key is
    set, it rejects any other key (proves the user's own key is really sent)."""
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            key = self.headers["x-goog-api-key"]
            self.server.seen.append(key)
            if expect_key is not None:
                assert key == expect_key, "the user's own key must be sent, not the shared one"
            length = int(self.headers["Content-Length"])
            self.rfile.read(length)
            out = json.dumps({"candidates": [{"content": {"parts": [{"text": "AI text from own key"}]}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), H)
    server.seen = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_own_key_beats_shared_key_and_skips_shared_daily_limit():
    assert llm.mode_for(None) == "templates"
    server = _fake_gemini_server()
    os.environ.update(GEMINI_API_KEY="shared-key", GEMINI_BASE=f"http://127.0.0.1:{server.server_port}", DAILY_AI_LIMIT="1")
    try:
        uid_a, uid_b = _user("own@example.com"), _user("shared@example.com")
        assert llm.mode_for(uid_b) == "shared"
        store.save_user_gemini_key(uid_a, OWN_KEY)
        assert llm.mode_for(uid_a) == "own_key"
        # Own key: three calls all succeed — the shared daily limit (1) does not apply.
        assert [llm.complete("sys", "hi", uid_a) for _ in range(3)] == ["AI text from own key"] * 3
        # Shared key: first call succeeds, second hits the daily limit.
        assert llm.complete("sys", "hi", uid_b) == "AI text from own key"
        assert llm.complete("sys", "again", uid_b) is None and "limit" in llm.last_error.lower()
        # The server saw the own key for A's calls and the shared key for B's.
        assert server.seen == [OWN_KEY] * 3 + ["shared-key"]
    finally:
        server.shutdown()
        for var in ("GEMINI_API_KEY", "GEMINI_BASE", "DAILY_AI_LIMIT"):
            os.environ.pop(var, None)
    assert llm.mode_for(uid_a) == "own_key"  # own key still works with no shared key set


def _signup(email):
    r = client.post("/api/auth/signup", json={"email": email, "password": "secret123", "name": "Key User"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_api_key_endpoints_and_cover_letter_uses_own_key():
    for var in ("GEMINI_API_KEY", "GEMINI_BASE", "DAILY_AI_LIMIT"):
        os.environ.pop(var, None)
    assert client.get("/api/settings/api-key").status_code == 401
    token = _signup("api-key@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    r = client.get("/api/settings/api-key", headers=headers)
    assert r.status_code == 200 and r.json() == {"has_key": False, "masked": None, "mode": "templates"}

    r = client.post("/api/settings/api-key", json={"key": "not-a-gemini-key"}, headers=headers)
    assert r.status_code == 400
    r = client.post("/api/settings/api-key", json={"key": OWN_KEY}, headers=headers)
    assert r.status_code == 200 and r.json()["masked"] == "••••cdef" and r.json()["mode"] == "own_key"
    assert OWN_KEY not in r.text, "the full key must never be returned"

    r = client.get("/api/settings/api-key", headers=headers)
    assert r.json()["has_key"] is True and r.json()["masked"] == "••••cdef"
    # Another user cannot see this key.
    other = {"Authorization": f"Bearer {_signup('other-key@example.com')}"}
    assert client.get("/api/settings/api-key", headers=other).json()["has_key"] is False

    r = client.get("/api/settings/status", headers=headers)
    assert r.json()["ai_mode"] == "own_key" and r.json()["ai_daily_limit"] is None and r.json()["gemini"]["available"] is True

    # End to end: cover letter really calls Gemini with the user's own key.
    server = _fake_gemini_server(OWN_KEY)
    os.environ["GEMINI_BASE"] = f"http://127.0.0.1:{server.server_port}"
    try:
        r = client.post("/api/profile/text", json={"resume_text": open(os.path.join(ROOT, "sample_resume.txt")).read(), "filename": "sample_resume.txt"}, headers=headers)
        assert r.status_code == 200, r.text
        job = {"id": "x", "title": "Python Backend Engineer", "company": "Nimbus Labs",
               "description": "Build APIs with Python.", "tags": ["Python"]}
        r = client.post("/api/ai/cover-letter", json={"job": job}, headers=headers)
        assert r.status_code == 200 and r.json()["text"] == "AI text from own key" and r.json()["ai"] is True
    finally:
        server.shutdown()
        os.environ.pop("GEMINI_BASE", None)

    r = client.delete("/api/settings/api-key", headers=headers)
    assert r.status_code == 200
    assert client.get("/api/settings/api-key", headers=headers).json()["has_key"] is False
