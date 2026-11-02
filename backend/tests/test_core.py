from tests.conftest_env import fresh_db  # noqa: E402  (also puts the project root on sys.path)

fresh_db()
import time  # noqa: E402

from core import auth, db  # noqa: E402


def test_signup_login_and_wrong_password():
    user = auth.signup("Priya@Example.com", "secret123", "Priya")
    assert user["email"] == "priya@example.com" and "password_hash" not in user
    assert auth.login("priya@example.com", "secret123")["id"] == user["id"]
    for bad in ("wrong-pass1", "", "SECRET123"):
        try:
            auth.login("priya@example.com", bad)
            assert False, "should fail"
        except auth.AuthError:
            pass
    stored = db.one("SELECT password_hash FROM users WHERE id = ?", (user["id"],))["password_hash"]
    assert stored.startswith("scrypt$") and "secret123" not in stored


def test_validation_and_duplicates():
    for email, pw in (("not-an-email", "secret123"), ("a@b.co", "short1"), ("a@b.co", "onlyletters"), ("a@b.co", "12345678")):
        try:
            auth.signup(email, pw)
            assert False, (email, pw)
        except auth.AuthError:
            pass
    auth.signup("dup@example.com", "secret123")
    try:
        auth.signup("DUP@example.com", "secret123")
        assert False
    except auth.AuthError as exc:
        assert "already exists" in str(exc)


def test_lockout_after_five_failures():
    auth.signup("lock@example.com", "secret123")
    for _ in range(5):
        try:
            auth.login("lock@example.com", "bad-pass-1")
        except auth.AuthError:
            pass
    try:
        auth.login("lock@example.com", "secret123")  # even the right password is refused while locked
        assert False
    except auth.AuthError as exc:
        assert "Too many" in str(exc)
    db.execute("UPDATE users SET locked_until = ? WHERE email = ?", (time.time() - 1, "lock@example.com"))
    assert auth.login("lock@example.com", "secret123")


def test_change_password_and_delete_account_removes_everything():
    user = auth.signup("del@example.com", "secret123")
    uid = user["id"]
    db.execute("INSERT INTO profiles (user_id, filename, resume_text, data, updated_at) VALUES (?, ?, ?, ?, ?)", (uid, "cv.txt", "text", "{}", "now"))
    db.execute("INSERT INTO saved_jobs (user_id, job_id, saved_at) VALUES (?, ?, ?)", (uid, "j1", "now"))
    auth.change_password(uid, "secret123", "newpass456")
    assert auth.login("del@example.com", "newpass456")
    auth.delete_account(uid)
    assert db.one("SELECT id FROM users WHERE id = ?", (uid,)) is None
    assert db.one("SELECT user_id FROM profiles WHERE user_id = ?", (uid,)) is None
    assert db.one("SELECT user_id FROM saved_jobs WHERE user_id = ?", (uid,)) is None


def test_sso_user_is_created_once():
    a, b = auth.sso_user("g@example.com", "G User"), auth.sso_user("G@example.com")
    assert a["id"] == b["id"]
    try:
        auth.login("g@example.com", "anything1")  # SSO accounts have no password
        assert False
    except auth.AuthError:
        pass
