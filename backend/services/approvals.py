"""The ONLY place where a draft touches the outside world, and only after the user confirms."""
from urllib.parse import quote

from services import mailer, store


class ApprovalError(Exception):
    """A message that is safe to show to the user."""


def linkedin_search_url(company: str) -> str:
    return f"https://www.linkedin.com/search/results/people/?keywords={quote('recruiter ' + (company or ''))}"


def approve(user_id: str, draft_id: str, confirm: bool, recipient: str | None = None) -> dict:
    draft = store.get_draft(user_id, draft_id)
    if not draft:
        raise ApprovalError("Draft not found.")
    if draft["status"] != "draft":
        raise ApprovalError(f"This draft is already {draft['status']}.")
    if not confirm:
        raise ApprovalError("Please tick the confirmation box first.")
    job = store.get_job(draft["job_id"]) or {}
    if recipient is not None:
        store.update_draft(user_id, draft_id, recipient=recipient.strip())
        draft["recipient"] = recipient.strip()
    if draft["kind"] == "email":
        if "@" not in (draft["recipient"] or ""):
            raise ApprovalError("Add the HR email address before approving.")
        try:
            result = mailer.send_or_link(draft["recipient"], draft["subject"], draft["body"])
        except Exception as exc:  # noqa: BLE001
            raise ApprovalError(f"Could not send the email: {exc}")
    elif draft["kind"] == "linkedin":
        result = {"url": linkedin_search_url(job.get("company", "")), "message": "LinkedIn does not allow automation. Open the link, find a recruiter and paste your note."}
    else:
        store.add_application(user_id, job or None, title=draft["title"], status="applied", cover_letter=draft["body"], url=job.get("apply_url", ""))
        result = {"url": job.get("apply_url") or job.get("url", ""), "message": "Added to your applications as 'applied'. Open the job page and submit with your cover letter."}
    store.set_draft_status(user_id, draft_id, "executed", result)
    return result


def reject(user_id: str, draft_id: str) -> None:
    draft = store.get_draft(user_id, draft_id)
    if draft and draft["status"] == "draft":
        store.set_draft_status(user_id, draft_id, "rejected")
