from tests.conftest_env import fresh_db  # noqa: E402

fresh_db()
import os  # noqa: E402

from core import auth  # noqa: E402
from services import approvals, store  # noqa: E402

JOB = {"id": "j1", "title": "Python Dev", "company": "Acme", "location": "Pune, India", "region": "india", "url": "https://x/1", "apply_url": "https://x/apply", "description": "d", "source": "T",
       "tags": [], "salary": "", "posted_at": "", "job_type": "full-time", "level": "mid"}


def test_nothing_happens_without_confirmation_and_only_the_owner_can_approve():
    a, b = auth.signup("a@example.com", "secret123")["id"], auth.signup("b@example.com", "secret123")["id"]
    store.upsert_jobs([JOB])
    draft = store.save_draft(a, "j1", "email", "Python Dev @ Acme", "Hello", "Body", "hr@acme.com")
    for call in (lambda: approvals.approve(a, draft, confirm=False), lambda: approvals.approve(b, draft, confirm=True)):
        try:
            call()
            assert False
        except approvals.ApprovalError:
            pass
    assert store.get_draft(a, draft)["status"] == "draft"


def test_email_needs_a_recipient_then_returns_mailto_without_smtp():
    os.environ.pop("SMTP_HOST", None)
    uid = auth.signup("m@example.com", "secret123")["id"]
    store.upsert_jobs([JOB])
    draft = store.save_draft(uid, "j1", "email", "t", "Subject here", "Body here")
    try:
        approvals.approve(uid, draft, confirm=True)
        assert False
    except approvals.ApprovalError as exc:
        assert "email address" in str(exc)
    result = approvals.approve(uid, draft, confirm=True, recipient="hr@acme.com")
    assert result["url"].startswith("mailto:hr%40acme.com") and store.get_draft(uid, draft)["status"] == "executed"
    try:
        approvals.approve(uid, draft, confirm=True)
        assert False
    except approvals.ApprovalError as exc:
        assert "already" in str(exc)


def test_apply_creates_an_application_and_linkedin_gives_a_search_link():
    uid = auth.signup("p@example.com", "secret123")["id"]
    store.upsert_jobs([JOB])
    apply_draft = store.save_draft(uid, "j1", "apply", "Python Dev @ Acme", "Apply", "My cover letter")
    result = approvals.approve(uid, apply_draft, confirm=True)
    app = store.application_for_job(uid, "j1")
    assert app["status"] == "applied" and app["cover_letter"] == "My cover letter" and result["url"] == "https://x/apply"
    li = store.save_draft(uid, "j1", "linkedin", "t", "", "Hi")
    assert "linkedin.com/search/results/people" in approvals.approve(uid, li, confirm=True)["url"]
    other = store.save_draft(uid, "j1", "email", "t", "S", "B")
    approvals.reject(uid, other)
    assert store.get_draft(uid, other)["status"] == "rejected"
