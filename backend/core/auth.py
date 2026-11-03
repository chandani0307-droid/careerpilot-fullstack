"""Accounts: sign up, log in, change password, delete account.

Passwords are hashed with scrypt (standard library) and a random salt. After 5 wrong passwords an account is
locked for 10 minutes. Nothing is stored in plain text.
"""
import base64
import hashlib
import hmac
import os
import re
import time

from core import db
from core.util import now, uid

EMAIL_RX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
MAX_FAILS, LOCK_SECONDS = 5, 600
_N, _R, _P = 2 ** 14, 8, 1


class AuthError(Exception):
    """A message that is safe to show to the user."""


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(got, base64.b64decode(digest))
    except Exception:  # noqa: BLE001
        return False


def _check_password_rules(password: str) -> None:
    if len(password or "") < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise AuthError("Use a password with at least 8 characters, including a letter and a number.")


def _public(user: dict) -> dict:
    return {k: user[k] for k in ("id", "email", "name", "created_at", "last_login")}


def signup(email: str, password: str, name: str = "") -> dict:
    email = normalize_email(email)
    if not EMAIL_RX.match(email):
        raise AuthError("Enter a valid email address.")
    _check_password_rules(password)
    if db.one("SELECT id FROM users WHERE email = ?", (email,)):
        raise AuthError("An account with this email already exists. Try logging in.")
    user_id = uid()
    db.execute("INSERT INTO users (id, email, name, password_hash, created_at, last_login) VALUES (?, ?, ?, ?, ?, ?)",
               (user_id, email, (name or email.split("@")[0]).strip()[:60], hash_password(password), now(), now()))
    return _public(db.one("SELECT * FROM users WHERE id = ?", (user_id,)))


def login(email: str, password: str) -> dict:
    email = normalize_email(email)
    user = db.one("SELECT * FROM users WHERE email = ?", (email,))
    if not user or not user.get("password_hash"):
        hash_password("dummy-password-to-keep-timing-similar")  # do not reveal whether the email exists
        raise AuthError("Wrong email or password.")
    if (user.get("locked_until") or 0) > time.time():
        minutes = int(((user["locked_until"] - time.time()) // 60) + 1)
        raise AuthError(f"Too many wrong attempts. Try again in about {minutes} minute(s).")
    if not verify_password(password, user["password_hash"]):
        fails = (user.get("failed_count") or 0) + 1
        locked = time.time() + LOCK_SECONDS if fails >= MAX_FAILS else 0
        db.execute("UPDATE users SET failed_count = ?, locked_until = ? WHERE id = ?", (0 if locked else fails, locked, user["id"]))
        raise AuthError("Wrong email or password.")
    db.execute("UPDATE users SET failed_count = 0, locked_until = 0, last_login = ? WHERE id = ?", (now(), user["id"]))
    return _public(user)


def sso_user(email: str, name: str = "") -> dict:
    """Get or create an account for someone who signed in with Google (no password stored)."""
    email = normalize_email(email)
    if not EMAIL_RX.match(email):
        raise AuthError("Your Google account did not share an email address.")
    user = db.one("SELECT * FROM users WHERE email = ?", (email,))
    if not user:
        user_id = uid()
        db.execute("INSERT INTO users (id, email, name, password_hash, created_at, last_login) VALUES (?, ?, ?, ?, ?, ?)",
                   (user_id, email, (name or email.split("@")[0])[:60], "", now(), now()))
        user = db.one("SELECT * FROM users WHERE id = ?", (user_id,))
    else:
        db.execute("UPDATE users SET last_login = ? WHERE id = ?", (now(), user["id"]))
    return _public(user)


def get_user(user_id: str) -> dict | None:
    user = db.one("SELECT * FROM users WHERE id = ?", (user_id,))
    return _public(user) if user else None


def update_name(user_id: str, name: str) -> None:
    db.execute("UPDATE users SET name = ? WHERE id = ?", (name.strip()[:60], user_id))


def change_password(user_id: str, old: str, new: str) -> None:
    user = db.one("SELECT * FROM users WHERE id = ?", (user_id,))
    if not user or not user.get("password_hash") or not verify_password(old, user["password_hash"]):
        raise AuthError("Your current password is not correct.")
    _check_password_rules(new)
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new), user_id))


USER_TABLES = ["profiles", "results", "saved_jobs", "searches", "search_history", "applications", "app_events", "drafts", "agent_runs", "usage", "user_keys"]


def delete_account(user_id: str) -> None:
    """Remove the user and everything stored for them."""
    for table in USER_TABLES:
        db.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
