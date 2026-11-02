"""Encrypt a user's own API key before it is stored.

A user can bring their own free Gemini key (Settings page). The key is
encrypted with Fernet, keyed by SECRET_KEY, so the database never holds it
in plain text. Only that user's own AI calls ever decrypt it, and the API
never returns the full key — only a masked preview (last 4 characters).

If SECRET_KEY changes, previously stored keys can no longer be decrypted;
they are then treated as missing and the user can simply enter the key again.
"""
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


def _fernet() -> Fernet:
    secret = os.environ.get("SECRET_KEY", "dev-only-change-me")
    digest = hashlib.sha256(secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_text(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_text(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError, TypeError):
        return None


def mask_key(key: str) -> str:
    key = (key or "").strip()
    return f"••••{key[-4:]}" if len(key) >= 4 else "••••"
