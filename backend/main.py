"""CareerPilot backend — FastAPI, no Streamlit.

Reuses core/ and services/ from the free Streamlit version verbatim:
same scrypt auth, same SQLite/PostgreSQL store, same free job search
(Remotive, RemoteOK, Arbeitnow, Jobicy, Himalayas, The Muse, RSS),
same Gemini-or-template AI writing. No paid job source, no paid API.

Run:  uvicorn main:app --reload --port 8000
"""
import base64
import hashlib
import hmac
import os
import time
from typing import Any, Optional

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from core import auth, db
from core.config import cfg
from services import analytics, approvals, search, store, writer
from services.agent import run_agent
from services.interview import generate as interview_generate
from services.llm import llm
from services.resume_parser import analyze_heuristic, extract_text

SECRET = os.environ.get("SECRET_KEY", "dev-only-change-me")
TOKEN_TTL = 30 * 24 * 3600  # 30 days
security = HTTPBearer(auto_error=False)

app = FastAPI(title="CareerPilot API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    db.init_schema()


# ───────────────────────── auth tokens (HMAC, stdlib only) ─────────────────────────
def make_token(user_id: str) -> str:
    exp = int(time.time()) + TOKEN_TTL
    payload = f"{user_id}.{exp}".encode()
    sig = hmac.new(SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{user_id}.{exp}.{sig}".encode()).decode()


def verify_token(token: str) -> Optional[str]:
    try:
        user_id, exp, sig = base64.urlsafe_b64decode(token.encode()).decode().split(".")
        if int(exp) < time.time():
            return None
        want = hmac.new(SECRET.encode(), f"{user_id}.{exp}".encode(), hashlib.sha256).hexdigest()
        return user_id if hmac.compare_digest(want, sig) else None
    except Exception:
        return None


def current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> dict:
    if not creds:
        raise HTTPException(401, "Log in first.")
    user_id = verify_token(creds.credentials)
    user = auth.get_user(user_id) if user_id else None
    if not user:
        raise HTTPException(401, "Invalid or expired token. Log in again.")
    return user


def optional_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Optional[dict]:
    if not creds:
        return None
    user_id = verify_token(creds.credentials)
    return auth.get_user(user_id) if user_id else None


def _err(exc: Exception, status: int = 400) -> HTTPException:
    return HTTPException(status, str(exc))


# ───────────────────────── models ─────────────────────────
class SignupIn(BaseModel):
    email: str
    password: str
    name: str = ""


class LoginIn(BaseModel):
    email: str
    password: str


class ApiKeyIn(BaseModel):
    key: str = ""


class PasswordIn(BaseModel):
    old: str
    new: str


class JobIn(BaseModel):
    job_id: str = ""
    job: Optional[dict] = None


class ApplicationIn(BaseModel):
    job_id: str = ""
    job: Optional[dict] = None
    title: str = ""
    company: str = ""
    location: str = ""
    url: str = ""
    status: str = "applied"
    notes: str = ""
    cover_letter: str = ""
    follow_up: str = ""


class ApplicationPatch(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    follow_up: Optional[str] = None
    cover_letter: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    url: Optional[str] = None


class ProfileTextIn(BaseModel):
    resume_text: str
    filename: str = "resume.txt"


class ProfilePatch(BaseModel):
    name: Optional[str] = None
    target_roles: Optional[list] = None
    skills: Optional[list] = None
    experience_years: Optional[float] = None
    preferred_locations: Optional[list] = None
    preferred_regions: Optional[list] = None
    summary: Optional[str] = None


class JobRef(BaseModel):
    job_id: str = ""
    job: Optional[dict] = None
    title: str = ""
    company: str = ""
    description: str = ""
    tags: list = []
    tone: str = "professional"


class AssistantIn(BaseModel):
    messages: list = Field(default_factory=list)


class PracticeIn(BaseModel):
    question: str
    answer: str


class AutopilotIn(BaseModel):
    query: str = ""
    region: str = "all"
    location: str = ""
    scan: int = 60
    prepare: int = 3


class DraftIn(BaseModel):
    job_id: str = ""
    kind: str = "apply"
    title: str = ""
    subject: str = ""
    body: str = ""
    recipient: str = ""


class ApproveIn(BaseModel):
    confirm: bool = True
    recipient: Optional[str] = None


# ───────────────────────── helpers ─────────────────────────
def _job_from_ref(ref: JobRef, user_id: str) -> dict:
    """A job from an id (stored), or from a dict the client sent, or from title/company fields."""
    if ref.job:
        return dict(ref.job)
    if ref.job_id:
        job = store.get_job(ref.job_id)
        if job:
            return job
    return {"id": ref.job_id or "adhoc", "title": ref.title, "company": ref.company,
            "location": "", "description": ref.description, "tags": ref.tags,
            "matched": [], "missing": []}


def _with_saved(user_id: str, jobs: list[dict]) -> list[dict]:
    saved = store.saved_ids(user_id)
    applied = {a["job_id"] for a in store.list_applications(user_id)}
    for j in jobs:
        j["saved"] = j["id"] in saved
        j["applied"] = j["id"] in applied
    return jobs


# ───────────────────────── health / status ─────────────────────────
@app.get("/api/health")
def health():
    return {"ok": True, "app": cfg.app_name, "sources": search.active_sources(), "ai": "gemini" if llm.available else "templates"}


@app.get("/api/settings/status")
def settings_status(user: dict = Depends(current_user)):
    mode = llm.mode_for(user["id"])
    own = mode == "own_key"
    return {
        "sources": search.active_sources(),
        "free": True,
        "free_note": "All job sources are free and need no key or payment. No paid job board is used.",
        "gemini": {"available": llm.available_for(user["id"]), "model": cfg.gemini_model if llm.available_for(user["id"]) else None},
        "ai_mode": mode,
        "own_key": {"has_key": own, "masked": store.user_gemini_key_masked(user["id"])},
        "ai_used_today": store.usage_today(user["id"]),
        "ai_daily_limit": None if own else cfg.daily_ai_limit,
        "ai_note": ("Real AI is on with YOUR OWN free Gemini key — your own quota applies, no daily limit here."
                    if own else "Real AI is on with the shared key (daily limit applies)."
                    if mode == "shared" else "No Gemini key yet — templates are used. Add your own free key below to turn real AI on."),
        "database": "PostgreSQL (hosted)" if db.is_postgres() else "SQLite (local file)",
        "email": "SMTP on" if cfg.smtp_ready else "opens your email app (mailto)",
    }


# ───────────────────────── the user's own Gemini API key ─────────────────────────
@app.get("/api/settings/api-key")
def get_api_key(user: dict = Depends(current_user)):
    masked = store.user_gemini_key_masked(user["id"])
    return {"has_key": bool(masked), "masked": masked, "mode": llm.mode_for(user["id"])}


@app.post("/api/settings/api-key")
def save_api_key(body: ApiKeyIn, user: dict = Depends(current_user)):
    key = (body.key or "").strip()
    if not (key.startswith("AIza") and 25 <= len(key) <= 60):
        raise HTTPException(400, "That doesn't look like a Gemini API key. Free keys from AI Studio start with 'AIza'.")
    store.save_user_gemini_key(user["id"], key)
    return {"ok": True, "masked": store.user_gemini_key_masked(user["id"]), "mode": "own_key",
            "note": "Saved. Real AI will now use your own key and your own free quota."}


@app.delete("/api/settings/api-key")
def delete_api_key(user: dict = Depends(current_user)):
    store.delete_user_gemini_key(user["id"])
    return {"ok": True, "mode": llm.mode_for(user["id"])}


# ───────────────────────── auth ─────────────────────────
@app.post("/api/auth/signup")
def signup(body: SignupIn):
    try:
        user = auth.signup(body.email, body.password, body.name)
    except auth.AuthError as exc:
        raise _err(exc)
    return {"token": make_token(user["id"]), "user": user}


@app.post("/api/auth/login")
def login(body: LoginIn):
    try:
        user = auth.login(body.email, body.password)
    except auth.AuthError as exc:
        raise HTTPException(401, str(exc))
    return {"token": make_token(user["id"]), "user": user}


@app.get("/api/auth/me")
def me(user: dict = Depends(current_user)):
    return {"user": user}


@app.post("/api/auth/change-password")
def change_password(body: PasswordIn, user: dict = Depends(current_user)):
    try:
        auth.change_password(user["id"], body.old, body.new)
    except auth.AuthError as exc:
        raise _err(exc)
    return {"ok": True}


@app.delete("/api/auth/me")
def delete_account(user: dict = Depends(current_user)):
    auth.delete_account(user["id"])
    return {"ok": True}


# ───────────────────────── jobs ─────────────────────────
@app.get("/api/jobs/search")
def jobs_search(q: str = "", region: str = "all", location: str = "", limit: int = 60,
                sort: str = "best", level: str = "any", job_type: str = "any",
                posted_days: int = 0, min_match: int = 0, user: Optional[dict] = Depends(optional_user)):
    profile = store.profile_data(user["id"]) if user else None
    filters = {"level": level, "job_type": job_type, "posted_days": posted_days}
    jobs, report = search.search_jobs(q, region, location, limit, profile, filters, sort)
    search_id = None
    if user:
        if min_match:
            jobs = [j for j in jobs if j.get("score", 0) >= min_match]
        # Saved per account: the full result list is stored in search_history
        # (plus the latest list in results, for the dashboard), so leaving
        # Find Jobs and coming back never asks the user to search again.
        search_id = store.save_results(user["id"], jobs, q or "(my profile)", region, location, filters, sort)
        jobs = _with_saved(user["id"], jobs)
    return {"jobs": jobs, "report": report, "search_id": search_id, "sources": search.active_sources(),
            "free_note": "Free to apply — CareerPilot never charges, and Apply links go to the employer's free listing."}


@app.get("/api/jobs/last")
def jobs_last(user: dict = Depends(current_user)):
    """The user's most recent search, with its jobs — used to restore Find Jobs
    when the page is reopened, after a refresh, or on another device."""
    last = store.get_last_search(user["id"])
    if not last:
        return {"search": None, "jobs": [], "report": None}
    profile = store.profile_data(user["id"])
    jobs = search.attach_match(list(last["jobs"]), profile)
    jobs = _with_saved(user["id"], jobs)
    return {"search": {k: v for k, v in last.items() if k != "jobs"}, "jobs": jobs, "report": None}


@app.get("/api/jobs/history")
def jobs_history(user: dict = Depends(current_user)):
    return {"history": store.list_search_history(user["id"], 10)}


@app.get("/api/jobs/history/{history_id}")
def jobs_history_one(history_id: str, user: dict = Depends(current_user)):
    entry = store.get_search_history(user["id"], history_id)
    if not entry:
        raise HTTPException(404, "That search is not in your history.")
    profile = store.profile_data(user["id"])
    jobs = search.attach_match(list(entry["jobs"]), profile)
    jobs = _with_saved(user["id"], jobs)
    return {"search": {k: v for k, v in entry.items() if k != "jobs"}, "jobs": jobs, "report": None}


@app.delete("/api/jobs/history/{history_id}")
def jobs_history_delete(history_id: str, user: dict = Depends(current_user)):
    if not store.delete_search_history(user["id"], history_id):
        raise HTTPException(404, "That search is not in your history.")
    return {"ok": True}


@app.get("/api/jobs/saved")
def jobs_saved(user: dict = Depends(current_user)):
    profile = store.profile_data(user["id"])
    jobs = search.attach_match(store.list_saved(user["id"]), profile)
    return {"jobs": _with_saved(user["id"], jobs)}


@app.post("/api/jobs/save")
def jobs_save(body: JobIn, user: dict = Depends(current_user)):
    if body.job:
        store.upsert_jobs([body.job])
        job_id = body.job["id"]
    elif body.job_id:
        job_id = body.job_id
    else:
        raise HTTPException(400, "Give a job_id or a job.")
    saved = store.toggle_saved(user["id"], job_id)
    return {"saved": saved, "job_id": job_id}


@app.post("/api/jobs/apply")
def jobs_apply(body: JobIn, user: dict = Depends(current_user)):
    job = body.job or (store.get_job(body.job_id) if body.job_id else None)
    if not job:
        raise HTTPException(404, "Job not found. Search first, then apply.")
    app_id = store.add_application(user["id"], job, status="applied")
    return {"application_id": app_id}


# ───────────────────────── applications ─────────────────────────
@app.get("/api/applications")
def list_applications(user: dict = Depends(current_user)):
    return {"applications": store.list_applications(user["id"])}


@app.post("/api/applications")
def create_application(body: ApplicationIn, user: dict = Depends(current_user)):
    job = body.job or (store.get_job(body.job_id) if body.job_id else None)
    if job:
        app_id = store.add_application(user["id"], job, status=body.status or "applied")
    else:
        app_id = store.add_application(user["id"], title=body.title, company=body.company,
                                       location=body.location, url=body.url, status=body.status or "saved",
                                       notes=body.notes, cover_letter=body.cover_letter, follow_up=body.follow_up)
    return {"application_id": app_id}


@app.get("/api/applications/{app_id}")
def get_application(app_id: str, user: dict = Depends(current_user)):
    app_row = store.get_application(user["id"], app_id)
    if not app_row:
        raise HTTPException(404, "Application not found.")
    return {"application": app_row, "events": store.events(user["id"], app_id)}


@app.patch("/api/applications/{app_id}")
def patch_application(app_id: str, body: ApplicationPatch, user: dict = Depends(current_user)):
    app_row = store.get_application(user["id"], app_id)
    if not app_row:
        raise HTTPException(404, "Application not found.")
    if body.status:
        if body.status not in store.STATUSES:
            raise HTTPException(400, f"Status must be one of {store.STATUSES}.")
        store.set_status(user["id"], app_id, body.status)
    fields = {k: v for k, v in body.model_dump(exclude_unset=True).items() if k != "status" and v is not None}
    if fields:
        store.update_application(user["id"], app_id, **fields)
    return {"application": store.get_application(user["id"], app_id)}


@app.delete("/api/applications/{app_id}")
def delete_application(app_id: str, user: dict = Depends(current_user)):
    store.delete_application(user["id"], app_id)
    return {"ok": True}


@app.get("/api/applications/{app_id}/events")
def application_events(app_id: str, user: dict = Depends(current_user)):
    return {"events": store.events(user["id"], app_id)}


# ───────────────────────── profile ─────────────────────────
@app.get("/api/profile")
def get_profile(user: dict = Depends(current_user)):
    profile = store.get_profile(user["id"])
    return {"profile": profile}


@app.post("/api/profile/text")
def upload_profile_text(body: ProfileTextIn, user: dict = Depends(current_user)):
    if len(body.resume_text.strip()) < 50:
        raise HTTPException(400, "Paste a longer resume (at least 50 characters).")
    data = writer.analyze_resume(body.resume_text, body.filename, user["id"])
    store.save_profile(user["id"], body.filename, body.resume_text, data)
    return {"profile": {"filename": body.filename, "resume_text": body.resume_text, "data": data}}


@app.post("/api/profile/upload")
async def upload_profile_file(file: UploadFile = File(...), user: dict = Depends(current_user)):
    data_bytes = await file.read()
    try:
        text = extract_text(file.filename or "", data_bytes)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if len(text.strip()) < 50:
        raise HTTPException(400, "Could not read enough text from that file. Try a TXT, PDF or DOCX resume.")
    data = writer.analyze_resume(text, file.filename or "", user["id"])
    store.save_profile(user["id"], file.filename or "", text, data)
    return {"profile": {"filename": file.filename or "", "resume_text": text, "data": data}}


@app.patch("/api/profile")
def patch_profile(body: ProfilePatch, user: dict = Depends(current_user)):
    fields = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if "name" in fields:
        auth.update_name(user["id"], fields.pop("name"))
    data = store.patch_profile(user["id"], **fields) if fields else (store.profile_data(user["id"]) or {})
    return {"profile": store.get_profile(user["id"]), "data": data}


@app.get("/api/profile/export")
def export_profile(user: dict = Depends(current_user)):
    return store.export_all(user["id"])


# ───────────────────────── AI ─────────────────────────
@app.post("/api/ai/cover-letter")
def ai_cover_letter(body: JobRef, user: dict = Depends(current_user)):
    profile = store.profile_data(user["id"])
    if not profile:
        raise HTTPException(400, "Upload your resume on the Profile page first.")
    job = _job_from_ref(body, user["id"])
    text = writer.cover_letter(profile, job, body.tone or "professional", user["id"])
    draft_id = store.save_draft(user["id"], job.get("id", ""), "apply", f"{job.get('title')} @ {job.get('company')}",
                                f"Apply: {job.get('title')}", text)
    return {"text": text, "draft_id": draft_id, "ai": llm.available_for(user["id"])}


@app.post("/api/ai/tailor-tips")
def ai_tailor_tips(body: JobRef, user: dict = Depends(current_user)):
    profile = store.profile_data(user["id"])
    if not profile:
        raise HTTPException(400, "Upload your resume on the Profile page first.")
    job = _job_from_ref(body, user["id"])
    job = search.attach_match([job], profile)[0]
    return writer.tailor_tips(profile, job)


@app.post("/api/ai/interview-prep")
def ai_interview_prep(body: JobRef, user: dict = Depends(current_user)):
    profile = store.profile_data(user["id"])
    if not profile:
        raise HTTPException(400, "Upload your resume on the Profile page first.")
    job = _job_from_ref(body, user["id"])
    prep = interview_generate(profile, job.get("title", ""), job.get("company", ""),
                              list(job.get("tags") or []), job.get("description", ""), user["id"])
    return {"job": {"title": job.get("title"), "company": job.get("company")}, **prep}


@app.post("/api/ai/practice-feedback")
def ai_practice_feedback(body: PracticeIn, user: dict = Depends(current_user)):
    return writer.practice_feedback(body.question, body.answer, user["id"])


@app.post("/api/ai/assistant")
def ai_assistant(body: AssistantIn, user: dict = Depends(current_user)):
    profile = store.profile_data(user["id"])
    stats = {"saved": len(store.saved_ids(user["id"])), "applications": len(store.list_applications(user["id"]))}
    history = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in body.messages][-8:]
    if not history:
        raise HTTPException(400, "Send at least one message.")
    return {"reply": writer.assistant_reply(profile, history, stats, user["id"]), "ai": llm.available_for(user["id"])}


@app.post("/api/ai/follow-up")
def ai_follow_up(app_id: str, user: dict = Depends(current_user)):
    app_row = store.get_application(user["id"], app_id)
    if not app_row:
        raise HTTPException(404, "Application not found.")
    profile = store.profile_data(user["id"]) or {}
    return writer.follow_up_email(profile, app_row, user["id"])


# ───────────────────────── autopilot ─────────────────────────
@app.post("/api/autopilot/run")
def autopilot_run(body: AutopilotIn, user: dict = Depends(current_user)):
    result = run_agent(user["id"], {"query": body.query, "region": body.region,
                                    "location": body.location, "scan": body.scan, "prepare": body.prepare})
    return result


@app.get("/api/autopilot/last")
def autopilot_last(user: dict = Depends(current_user)):
    return {"run": store.last_run(user["id"])}


# ───────────────────────── drafts (approval gate) ─────────────────────────
@app.get("/api/drafts")
def list_drafts(status: Optional[str] = None, kind: Optional[str] = None, user: dict = Depends(current_user)):
    return {"drafts": store.list_drafts(user["id"], status=status, kind=kind)}


@app.post("/api/drafts")
def create_draft(body: DraftIn, user: dict = Depends(current_user)):
    draft_id = store.save_draft(user["id"], body.job_id, body.kind, body.title, body.subject, body.body, body.recipient)
    return {"draft_id": draft_id}


@app.get("/api/drafts/{draft_id}")
def get_draft(draft_id: str, user: dict = Depends(current_user)):
    draft = store.get_draft(user["id"], draft_id)
    if not draft:
        raise HTTPException(404, "Draft not found.")
    return {"draft": draft}


@app.post("/api/drafts/{draft_id}/approve")
def approve_draft(draft_id: str, body: ApproveIn, user: dict = Depends(current_user)):
    try:
        result = approvals.approve(user["id"], draft_id, confirm=body.confirm, recipient=body.recipient)
    except approvals.ApprovalError as exc:
        raise HTTPException(400, str(exc))
    return {"result": result, "draft": store.get_draft(user["id"], draft_id)}


@app.post("/api/drafts/{draft_id}/reject")
def reject_draft(draft_id: str, user: dict = Depends(current_user)):
    approvals.reject(user["id"], draft_id)
    return {"ok": True}


# ───────────────────────── dashboard / analytics ─────────────────────────
@app.get("/api/dashboard")
def dashboard(user: dict = Depends(current_user)):
    summ = analytics.summary(user["id"])
    return {"summary": summ, "recent_events": store.recent_events(user["id"], 8),
            "recent_searches": store.list_search_history(user["id"], 5),
            "profile": store.profile_data(user["id"])}


@app.get("/api/analytics/summary")
def analytics_summary(user: dict = Depends(current_user)):
    return analytics.summary(user["id"])
