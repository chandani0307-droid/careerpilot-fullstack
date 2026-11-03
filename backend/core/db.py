"""A small database layer that works with SQLite (local) and PostgreSQL (hosted, e.g. Neon) with the same SQL.

Write SQL with ? placeholders. Dates are ISO text and JSON is stored as text, so one schema fits both databases.
"""
import sqlite3
import threading
from pathlib import Path

from core.config import cfg

_local = threading.local()
_schema_ready: set[str] = set()
_lock = threading.Lock()

SCHEMA = [
    "CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT, password_hash TEXT, created_at TEXT, last_login TEXT, failed_count INTEGER DEFAULT 0, locked_until DOUBLE PRECISION DEFAULT 0)",
    "CREATE TABLE IF NOT EXISTS profiles (user_id TEXT PRIMARY KEY, filename TEXT, resume_text TEXT, data TEXT, updated_at TEXT)",
    "CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, title TEXT, company TEXT, location TEXT, region TEXT, url TEXT, apply_url TEXT, description TEXT, source TEXT, tags TEXT, salary TEXT, posted_at TEXT, job_type TEXT, level TEXT, fetched_at TEXT)",
    "CREATE TABLE IF NOT EXISTS results (user_id TEXT, job_id TEXT, pos INTEGER, relevance DOUBLE PRECISION, PRIMARY KEY (user_id, job_id))",
    "CREATE TABLE IF NOT EXISTS saved_jobs (user_id TEXT, job_id TEXT, saved_at TEXT, PRIMARY KEY (user_id, job_id))",
    "CREATE TABLE IF NOT EXISTS searches (id TEXT PRIMARY KEY, user_id TEXT, query TEXT, region TEXT, location TEXT, found INTEGER, created_at TEXT)",
    "CREATE TABLE IF NOT EXISTS search_history (id TEXT PRIMARY KEY, user_id TEXT, query TEXT, region TEXT, location TEXT, filters TEXT, sort TEXT, found INTEGER, jobs TEXT, created_at TEXT)",
    "CREATE TABLE IF NOT EXISTS applications (id TEXT PRIMARY KEY, user_id TEXT, job_id TEXT, title TEXT, company TEXT, location TEXT, url TEXT, status TEXT, match_score INTEGER, notes TEXT, cover_letter TEXT, follow_up TEXT, applied_at TEXT, created_at TEXT, updated_at TEXT)",
    "CREATE TABLE IF NOT EXISTS app_events (id TEXT PRIMARY KEY, application_id TEXT, user_id TEXT, status TEXT, note TEXT, created_at TEXT)",
    "CREATE TABLE IF NOT EXISTS drafts (id TEXT PRIMARY KEY, user_id TEXT, job_id TEXT, kind TEXT, title TEXT, recipient TEXT, subject TEXT, body TEXT, status TEXT, result TEXT, created_at TEXT, updated_at TEXT)",
    "CREATE TABLE IF NOT EXISTS agent_runs (id TEXT PRIMARY KEY, user_id TEXT, params TEXT, trace TEXT, summary TEXT, status TEXT, created_at TEXT)",
    "CREATE TABLE IF NOT EXISTS usage (user_id TEXT, day TEXT, n INTEGER, PRIMARY KEY (user_id, day))",
    "CREATE TABLE IF NOT EXISTS user_keys (user_id TEXT PRIMARY KEY, gemini_key_enc TEXT, updated_at TEXT)",
    "CREATE INDEX IF NOT EXISTS idx_apps_user ON applications (user_id)",
    "CREATE INDEX IF NOT EXISTS idx_events_app ON app_events (application_id)",
    "CREATE INDEX IF NOT EXISTS idx_drafts_user ON drafts (user_id)",
    "CREATE INDEX IF NOT EXISTS idx_searches_user ON searches (user_id)",
    "CREATE INDEX IF NOT EXISTS idx_search_history_user ON search_history (user_id)",
]


def is_postgres() -> bool:
    return cfg.database_url.startswith(("postgres://", "postgresql://"))


def _key() -> str:
    return cfg.database_url if is_postgres() else cfg.sqlite_path


def _connect():
    if is_postgres():
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(cfg.database_url, row_factory=dict_row, autocommit=True, connect_timeout=15)
    path = Path(cfg.sqlite_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def _conn():
    key = _key()
    if getattr(_local, "key", None) != key or getattr(_local, "conn", None) is None:
        _local.conn, _local.key = _connect(), key
    return _local.conn


def _reset() -> None:
    try:
        if getattr(_local, "conn", None) is not None:
            _local.conn.close()
    except Exception:  # noqa: BLE001
        pass
    _local.conn = None


def _run(sql: str, params: tuple, fetch: bool):
    sql = sql.replace("?", "%s") if is_postgres() else sql
    for attempt in (1, 2):
        try:
            conn = _conn()
            if is_postgres():
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    return [dict(r) for r in cur.fetchall()] if fetch else cur.rowcount
            cur = conn.execute(sql, params)
            return [dict(r) for r in cur.fetchall()] if fetch else cur.rowcount
        except Exception as exc:  # noqa: BLE001
            # Hosted databases close idle connections: reconnect once, then give up
            if attempt == 1 and exc.__class__.__name__ in ("OperationalError", "InterfaceError") and is_postgres():
                _reset()
                continue
            raise


def execute(sql: str, params: tuple = ()) -> int:
    return _run(sql, tuple(params), fetch=False)


def query(sql: str, params: tuple = ()) -> list[dict]:
    return _run(sql, tuple(params), fetch=True)


def one(sql: str, params: tuple = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def init_schema() -> None:
    """Create the tables if they do not exist. Safe to call on every page run."""
    key = _key()
    if key in _schema_ready:
        return
    with _lock:
        for statement in SCHEMA:
            execute(statement)
        _schema_ready.add(key)
