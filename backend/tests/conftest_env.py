"""Shared helper for tests: a fresh temporary database per test run."""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def fresh_db():
    path = os.path.join(tempfile.mkdtemp(), "test.db")
    os.environ["SQLITE_PATH"] = path
    os.environ.pop("DATABASE_URL", None)
    from core import db
    db._reset()
    db._schema_ready.clear()
    db.init_schema()
    return path
