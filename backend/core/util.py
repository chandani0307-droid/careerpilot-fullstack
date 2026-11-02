import json
import uuid
from datetime import datetime, timezone


def uid() -> str:
    return uuid.uuid4().hex


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")  # microseconds keep ordering exact


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def jdump(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def jload(text, default=None):
    try:
        return json.loads(text) if text else default
    except (TypeError, ValueError):
        return default
