"""Everything saved per user. Every query filters on user_id, so one account can never see another's data."""
from datetime import datetime, timedelta, timezone

from core import crypto, db
from core.util import jdump, jload, now, today, uid

STATUSES = ["saved", "applied", "screening", "interview", "offer", "rejected"]


# ───────────── profile ─────────────
def get_profile(user_id: str) -> dict | None:
    row = db.one("SELECT * FROM profiles WHERE user_id = ?", (user_id,))
    if not row:
        return None
    return {"filename": row["filename"], "resume_text": row["resume_text"] or "", "data": jload(row["data"], {}), "updated_at": row["updated_at"]}


def profile_data(user_id: str) -> dict | None:
    profile = get_profile(user_id)
    return profile["data"] if profile else None


def save_profile(user_id: str, filename: str, resume_text: str, data: dict) -> None:
    db.execute("DELETE FROM profiles WHERE user_id = ?", (user_id,))
    db.execute("INSERT INTO profiles (user_id, filename, resume_text, data, updated_at) VALUES (?, ?, ?, ?, ?)", (user_id, filename, resume_text, jdump(data), now()))


def patch_profile(user_id: str, **fields) -> dict:
    current = get_profile(user_id) or {"filename": "", "resume_text": "", "data": {}}
    data = {**current["data"], **fields}
    save_profile(user_id, current["filename"], current["resume_text"], data)
    return data


# ───────────── jobs (shared cache of postings, no personal data) ─────────────
def _job(row: dict) -> dict:
    job = dict(row)
    job["tags"] = jload(row.get("tags"), [])
    return job


def upsert_jobs(jobs: list[dict]) -> None:
    for j in jobs:
        db.execute(
            "INSERT INTO jobs (id, title, company, location, region, url, apply_url, description, source, tags, salary, posted_at, job_type, level, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET title = excluded.title, company = excluded.company, location = excluded.location, "
            "region = excluded.region, apply_url = excluded.apply_url, description = excluded.description, tags = excluded.tags, salary = excluded.salary, posted_at = excluded.posted_at, fetched_at = excluded.fetched_at",
            (j["id"], j["title"], j["company"], j["location"], j["region"], j["url"], j["apply_url"], j["description"], j["source"], jdump(j["tags"]), j["salary"], j["posted_at"], j["job_type"], j["level"], now()))


def get_job(job_id: str) -> dict | None:
    row = db.one("SELECT * FROM jobs WHERE id = ?", (job_id,))
    return _job(row) if row else None


# ───────────── last search results, saved jobs, search history ─────────────
def save_results(user_id: str, jobs: list[dict], query: str, region: str, location: str, filters: dict | None = None, sort: str = "best") -> str:
    """Save the latest results (for the dashboard) AND a permanent per-user
    history entry, so a search survives page switches, refresh and logout.
    The history entry keeps the full job list, so reopening it needs no
    re-search. Only the newest 20 entries per user are kept."""
    upsert_jobs(jobs)
    db.execute("DELETE FROM results WHERE user_id = ?", (user_id,))
    for pos, job in enumerate(jobs):
        db.execute("INSERT INTO results (user_id, job_id, pos, relevance) VALUES (?, ?, ?, ?)", (user_id, job["id"], pos, job.get("relevance", 0)))
    db.execute("INSERT INTO searches (id, user_id, query, region, location, found, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (uid(), user_id, query, region, location, len(jobs), now()))
    history_id = uid()
    db.execute(
        "INSERT INTO search_history (id, user_id, query, region, location, filters, sort, found, jobs, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (history_id, user_id, query, region, location, jdump(filters or {}), sort or "best", len(jobs), jdump(jobs), now()))
    # Keep only the newest 20 history entries per user.
    old = db.query("SELECT id FROM search_history WHERE user_id = ? ORDER BY created_at DESC", (user_id,))[20:]
    for row in old:
        db.execute("DELETE FROM search_history WHERE id = ?", (row["id"],))
    return history_id


def _history_row(row: dict, with_jobs: bool = False) -> dict:
    out = {"id": row["id"], "query": row["query"], "region": row["region"], "location": row["location"],
           "filters": jload(row.get("filters"), {}), "sort": row.get("sort") or "best",
           "found": row["found"], "created_at": row["created_at"]}
    if with_jobs:
        out["jobs"] = jload(row.get("jobs"), [])
    return out


def list_search_history(user_id: str, n: int = 10) -> list[dict]:
    rows = db.query("SELECT * FROM search_history WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    return [_history_row(r) for r in rows[:n]]


def get_search_history(user_id: str, history_id: str) -> dict | None:
    row = db.one("SELECT * FROM search_history WHERE id = ? AND user_id = ?", (history_id, user_id))
    return _history_row(row, with_jobs=True) if row else None


def get_last_search(user_id: str) -> dict | None:
    row = db.one("SELECT * FROM search_history WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    return _history_row(row, with_jobs=True) if row else None


def delete_search_history(user_id: str, history_id: str) -> bool:
    if not db.one("SELECT id FROM search_history WHERE id = ? AND user_id = ?", (history_id, user_id)):
        return False
    db.execute("DELETE FROM search_history WHERE id = ? AND user_id = ?", (history_id, user_id))
    return True


def search_stats(user_id: str) -> dict:
    rows = db.query("SELECT found, query, region, location, created_at FROM search_history WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    total_found = sum(r["found"] or 0 for r in rows)
    last = rows[0] if rows else None
    return {
        "total_searches": len(rows),
        "total_jobs_found": total_found,
        "last_search": {"query": last["query"], "region": last["region"], "location": last["location"],
                        "found": last["found"], "created_at": last["created_at"]} if last else None,
    }


def load_results(user_id: str) -> list[dict]:
    rows = db.query("SELECT j.*, r.relevance AS relevance FROM results r JOIN jobs j ON j.id = r.job_id WHERE r.user_id = ? ORDER BY r.pos", (user_id,))
    return [_job(r) for r in rows]


def recent_searches(user_id: str, n: int = 6) -> list[dict]:
    rows = db.query("SELECT query, region, location, found, created_at FROM searches WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    seen, out = set(), []
    for r in rows:
        key = (r["query"], r["region"], r["location"])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out[:n]


def toggle_saved(user_id: str, job_id: str) -> bool:
    if db.one("SELECT job_id FROM saved_jobs WHERE user_id = ? AND job_id = ?", (user_id, job_id)):
        db.execute("DELETE FROM saved_jobs WHERE user_id = ? AND job_id = ?", (user_id, job_id))
        return False
    db.execute("INSERT INTO saved_jobs (user_id, job_id, saved_at) VALUES (?, ?, ?)", (user_id, job_id, now()))
    return True


def saved_ids(user_id: str) -> set[str]:
    return {r["job_id"] for r in db.query("SELECT job_id FROM saved_jobs WHERE user_id = ?", (user_id,))}


def list_saved(user_id: str) -> list[dict]:
    rows = db.query("SELECT j.* FROM saved_jobs s JOIN jobs j ON j.id = s.job_id WHERE s.user_id = ? ORDER BY s.saved_at DESC", (user_id,))
    return [_job(r) for r in rows]


# ───────────── applications ─────────────
def _event(user_id: str, app_id: str, status: str, note: str = "") -> None:
    db.execute("INSERT INTO app_events (id, application_id, user_id, status, note, created_at) VALUES (?, ?, ?, ?, ?, ?)", (uid(), app_id, user_id, status, note, now()))


def add_application(user_id: str, job: dict | None = None, *, title: str = "", company: str = "", location: str = "", url: str = "", status: str = "applied",
                    notes: str = "", cover_letter: str = "", match_score: int = 0, follow_up: str = "") -> str:
    if job:
        existing = application_for_job(user_id, job["id"])
        if existing:
            return existing["id"]
        title, company, location, url = job["title"], job["company"], job["location"], job.get("apply_url") or job["url"]
        match_score = int(job.get("score", match_score) or 0)
    app_id = uid()
    db.execute("INSERT INTO applications (id, user_id, job_id, title, company, location, url, status, match_score, notes, cover_letter, follow_up, applied_at, created_at, updated_at) "
               "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (app_id, user_id, (job or {}).get("id", ""), title.strip(), company.strip(), location, url, status, match_score, notes, cover_letter, follow_up,
                today() if status != "saved" else "", now(), now()))
    _event(user_id, app_id, status, "Added")
    return app_id


def get_application(user_id: str, app_id: str) -> dict | None:
    return db.one("SELECT * FROM applications WHERE id = ? AND user_id = ?", (app_id, user_id))


def application_for_job(user_id: str, job_id: str) -> dict | None:
    return db.one("SELECT * FROM applications WHERE user_id = ? AND job_id = ?", (user_id, job_id)) if job_id else None


def list_applications(user_id: str) -> list[dict]:
    return db.query("SELECT * FROM applications WHERE user_id = ? ORDER BY updated_at DESC", (user_id,))


def set_status(user_id: str, app_id: str, status: str, note: str = "") -> None:
    app = get_application(user_id, app_id)
    if not app or status not in STATUSES or app["status"] == status:
        return
    applied_at = app["applied_at"] or (today() if status != "saved" else "")
    db.execute("UPDATE applications SET status = ?, applied_at = ?, updated_at = ? WHERE id = ? AND user_id = ?", (status, applied_at, now(), app_id, user_id))
    _event(user_id, app_id, status, note)


def update_application(user_id: str, app_id: str, **fields) -> None:
    allowed = {k: v for k, v in fields.items() if k in ("title", "company", "location", "url", "notes", "cover_letter", "follow_up")}
    for key, value in allowed.items():
        db.execute(f"UPDATE applications SET {key} = ?, updated_at = ? WHERE id = ? AND user_id = ?", (value, now(), app_id, user_id))


def delete_application(user_id: str, app_id: str) -> None:
    db.execute("DELETE FROM app_events WHERE application_id = ? AND user_id = ?", (app_id, user_id))
    db.execute("DELETE FROM applications WHERE id = ? AND user_id = ?", (app_id, user_id))


def events(user_id: str, app_id: str) -> list[dict]:
    return db.query("SELECT * FROM app_events WHERE application_id = ? AND user_id = ? ORDER BY created_at", (app_id, user_id))


def recent_events(user_id: str, n: int = 8) -> list[dict]:
    return db.query("SELECT e.status, e.note, e.created_at, a.title, a.company FROM app_events e JOIN applications a ON a.id = e.application_id "
                    "WHERE e.user_id = ? ORDER BY e.created_at DESC", (user_id,))[:n]


# ───────────── drafts (emails, cover letters, LinkedIn notes) waiting for the user's approval ─────────────
def save_draft(user_id: str, job_id: str, kind: str, title: str, subject: str, body: str, recipient: str = "") -> str:
    old = db.one("SELECT id FROM drafts WHERE user_id = ? AND job_id = ? AND kind = ? AND status IN ('draft', 'pending')", (user_id, job_id, kind))
    if old:
        db.execute("UPDATE drafts SET title = ?, subject = ?, body = ?, recipient = ?, updated_at = ? WHERE id = ?", (title, subject, body, recipient, now(), old["id"]))
        return old["id"]
    draft_id = uid()
    db.execute("INSERT INTO drafts (id, user_id, job_id, kind, title, recipient, subject, body, status, result, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', '{}', ?, ?)",
               (draft_id, user_id, job_id, kind, title, recipient, subject, body, now(), now()))
    return draft_id


def list_drafts(user_id: str, status: str | None = None, kind: str | None = None) -> list[dict]:
    sql, params = "SELECT * FROM drafts WHERE user_id = ?", [user_id]
    if status:
        sql, params = sql + " AND status = ?", params + [status]
    if kind:
        sql, params = sql + " AND kind = ?", params + [kind]
    rows = db.query(sql + " ORDER BY updated_at DESC", tuple(params))
    for r in rows:
        r["result"] = jload(r["result"], {})
    return rows


def get_draft(user_id: str, draft_id: str) -> dict | None:
    row = db.one("SELECT * FROM drafts WHERE id = ? AND user_id = ?", (draft_id, user_id))
    if row:
        row["result"] = jload(row["result"], {})
    return row


def update_draft(user_id: str, draft_id: str, **fields) -> None:
    for key, value in fields.items():
        if key in ("recipient", "subject", "body"):
            db.execute(f"UPDATE drafts SET {key} = ?, updated_at = ? WHERE id = ? AND user_id = ?", (value, now(), draft_id, user_id))


def set_draft_status(user_id: str, draft_id: str, status: str, result: dict | None = None) -> None:
    db.execute("UPDATE drafts SET status = ?, result = ?, updated_at = ? WHERE id = ? AND user_id = ?", (status, jdump(result or {}), now(), draft_id, user_id))


# ───────────── agent runs, AI usage, export ─────────────
def save_run(user_id: str, params: dict, trace: list, summary: dict, status: str) -> str:
    run_id = uid()
    db.execute("INSERT INTO agent_runs (id, user_id, params, trace, summary, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (run_id, user_id, jdump(params), jdump(trace), jdump(summary), status, now()))
    return run_id


def last_run(user_id: str) -> dict | None:
    row = db.one("SELECT * FROM agent_runs WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    if row:
        row["params"], row["trace"], row["summary"] = jload(row["params"], {}), jload(row["trace"], []), jload(row["summary"], {})
    return row


def bump_usage(user_id: str, limit: int) -> bool:
    """Count one AI call for today. Returns False once the daily limit is reached."""
    row = db.one("SELECT n FROM usage WHERE user_id = ? AND day = ?", (user_id, today()))
    used = row["n"] if row else 0
    if used >= limit:
        return False
    if row:
        db.execute("UPDATE usage SET n = ? WHERE user_id = ? AND day = ?", (used + 1, user_id, today()))
    else:
        db.execute("INSERT INTO usage (user_id, day, n) VALUES (?, ?, ?)", (user_id, today(), 1))
    return True


def usage_today(user_id: str) -> int:
    row = db.one("SELECT n FROM usage WHERE user_id = ? AND day = ?", (user_id, today()))
    return row["n"] if row else 0


# ───────────── the user's own Gemini API key (encrypted, per user) ─────────────
def save_user_gemini_key(user_id: str, key: str) -> None:
    """Store one user's own Gemini key, encrypted. Replaces any previous key."""
    db.execute("INSERT INTO user_keys (user_id, gemini_key_enc, updated_at) VALUES (?, ?, ?) "
               "ON CONFLICT (user_id) DO UPDATE SET gemini_key_enc = excluded.gemini_key_enc, updated_at = excluded.updated_at",
               (user_id, crypto.encrypt_text(key.strip()), now()))


def get_user_gemini_key(user_id: str) -> str | None:
    """Decrypt and return the user's own key, or None (no key, or undecryptable)."""
    row = db.one("SELECT gemini_key_enc FROM user_keys WHERE user_id = ?", (user_id,))
    if not row or not row["gemini_key_enc"]:
        return None
    return crypto.decrypt_text(row["gemini_key_enc"])


def has_user_gemini_key(user_id: str) -> bool:
    return get_user_gemini_key(user_id) is not None


def user_gemini_key_masked(user_id: str) -> str | None:
    key = get_user_gemini_key(user_id)
    return crypto.mask_key(key) if key else None


def delete_user_gemini_key(user_id: str) -> None:
    db.execute("DELETE FROM user_keys WHERE user_id = ?", (user_id,))


def export_all(user_id: str) -> dict:
    profile = get_profile(user_id) or {}
    return {"profile": profile, "applications": list_applications(user_id), "saved_jobs": list_saved(user_id), "drafts": list_drafts(user_id),
            "searches": db.query("SELECT query, region, location, found, created_at FROM searches WHERE user_id = ?", (user_id,))}
