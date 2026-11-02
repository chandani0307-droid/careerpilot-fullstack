"""Settings come from environment variables (or a .env file).
On Streamlit Cloud, top-level keys in the app's Secrets are exposed as environment variables too.
Values are read on every access, so changing them at runtime (tests, secrets) just works.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


class Config:
    app_name = "CareerPilot"

    @property
    def database_url(self) -> str:        # empty = local SQLite file; postgresql://... = hosted Postgres (Neon, Supabase)
        return _env("DATABASE_URL")

    @property
    def sqlite_path(self) -> str:
        return _env("SQLITE_PATH") or str(ROOT / "data" / "careerpilot.db")

    # AI (optional)
    @property
    def gemini_key(self) -> str:
        return _env("GEMINI_API_KEY")

    @property
    def gemini_model(self) -> str:
        return _env("GEMINI_MODEL", "gemini-2.5-flash")

    @property
    def gemini_base(self) -> str:
        return _env("GEMINI_BASE", "https://generativelanguage.googleapis.com/v1beta")

    @property
    def daily_ai_limit(self) -> int:      # protects your free Gemini quota when many users share it
        return int(_env("DAILY_AI_LIMIT", "40"))

    # Job sources — 100% free, no key, no payment.
    # Paid-key sources were removed on purpose: no Adzuna, no JSearch/RapidAPI.
    # If an old .env still has those keys, they are simply ignored now.
    @property
    def rss_feeds(self) -> list[str]:
        # Checked 2026-11-02: RemoteOK's /rss feed is now 404, and Indeed India /
        # CareerJet RSS are 404 too, so they are NOT listed here. Only feeds that
        # actually return RSS are defaults; p_rss also isolates a dead feed.
        raw = _env("JOB_RSS_FEEDS", "https://weworkremotely.com/categories/remote-programming-jobs.rss,https://weworkremotely.com/categories/remote-data-science-jobs.rss,https://jobspresso.co/feed/")
        return [x.strip() for x in raw.split(",") if x.strip()]

    @property
    def mock_fallback(self) -> bool:
        return _env("MOCK_JOBS_FALLBACK", "true").lower() in ("1", "true", "yes")

    @property
    def http_timeout(self) -> float:
        return float(_env("HTTP_TIMEOUT", "9"))

    # Email (optional): without SMTP the app opens a mailto: draft
    @property
    def smtp_ready(self) -> bool:
        return bool(_env("SMTP_HOST") and _env("SMTP_USER") and _env("SMTP_PASSWORD"))

    @property
    def smtp(self) -> dict:
        return {"host": _env("SMTP_HOST"), "port": int(_env("SMTP_PORT", "587")), "user": _env("SMTP_USER"), "password": _env("SMTP_PASSWORD"), "sender": _env("SMTP_FROM") or _env("SMTP_USER")}


cfg = Config()
