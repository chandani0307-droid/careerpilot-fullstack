"""AI writing. Each function asks the AI first and falls back to a good offline template."""
import re

from services.llm import llm
from services.resume_parser import analyze_heuristic

SYS = "You are CareerPilot, an honest career coach. Never invent skills, employers, degrees or numbers. Be concise and professional."
TONES = {"professional": "professional and confident", "friendly": "warm and friendly", "concise": "short and direct (under 120 words)", "enthusiastic": "enthusiastic but not exaggerated"}


def _name(p: dict) -> str:
    return (p.get("name") or "").strip() or "Candidate"


def _top(p: dict, n: int = 4) -> list[str]:
    return (p.get("skills") or [])[:n]


def _profile(p: dict) -> str:
    return f"Name: {_name(p)}\nExperience: {p.get('experience_years')} years\nSkills: {', '.join(p.get('skills') or [])}\nTarget roles: {', '.join(p.get('target_roles') or [])}\nSummary: {p.get('summary', '')}"


def _job(j: dict) -> str:
    return f"Title: {j.get('title')}\nCompany: {j.get('company')}\nLocation: {j.get('location')}\nTags: {', '.join(j.get('tags') or [])}\nDescription: {(j.get('description') or '')[:1500]}"


def summary_line(p: dict) -> str:
    role = (p.get("target_roles") or ["software professional"])[0]
    return f"{role} with {p.get('experience_years') or 0:g} years of experience in {', '.join(_top(p, 5)) or 'software development'}."


def analyze_resume(text: str, filename: str = "", user_id: str | None = None) -> dict:
    profile = analyze_heuristic(text, filename)
    data = llm.json(SYS, "Analyse this resume. JSON keys: summary (2 sentences, first person, facts only), strengths (3 strings), gaps (3 strings), "
                         "suggestions (5 concrete resume improvements).\n\n" + text[:6000], user_id)
    if data:
        for key in ("summary", "strengths", "gaps", "suggestions"):
            if data.get(key):
                profile[key] = data[key]
        profile["ai_enhanced"] = True
    profile["summary"] = profile.get("summary") or summary_line(profile)
    profile["strengths"] = profile.get("strengths") or [f"Hands-on with {s}" for s in profile["skills"][:3]] or ["Add more skills to your resume"]
    profile["gaps"] = profile.get("gaps") or ["Search for jobs to see which skills you are missing"]
    return profile


def cover_letter(profile: dict, job: dict, tone: str = "professional", user_id: str | None = None) -> str:
    text = llm.complete(SYS, f"Write a cover letter (150-200 words), tone: {TONES.get(tone, tone)}. Plain text, no placeholders, mention 2-3 real strengths that match the job, "
                             f"sign with the candidate's name.\n\nCANDIDATE:\n{_profile(profile)}\n\nJOB:\n{_job(job)}", user_id)
    if text:
        return text
    matched = job.get("matched") or _top(profile, 3)
    return (f"Dear Hiring Team at {job.get('company')},\n\nI am excited to apply for the {job.get('title')} role. With {profile.get('experience_years') or 'hands-on'} years of experience "
            f"and strengths in {', '.join(matched[:4]) or 'software development'}, I can contribute quickly to your team.\n\n"
            f"I enjoy turning requirements into reliable, measurable results, and I would welcome the chance to discuss how I can help {job.get('company')}. "
            f"Thank you for your time and consideration.\n\nSincerely,\n{_name(profile)}")


def tailor_tips(profile: dict, job: dict) -> dict:
    """Resume tailoring advice from the job itself. Works without AI."""
    matched, missing = job.get("matched") or [], job.get("missing") or []
    tips = []
    if matched:
        tips.append(f"Put these near the top of your resume, exactly as written in the job: {', '.join(matched[:6])}.")
    if missing:
        tips.append(f"The job also asks for {', '.join(missing[:4])}. If you have real experience, add it with one example. If not, list it under 'learning' only if true.")
    tips += ["Rewrite your headline to include the job title, for example: " + f"\"{job.get('title')} | {', '.join(matched[:3]) or ', '.join(_top(profile, 3))}\".",
             "Start each bullet with a verb and end with a result and a number (time saved, users, percentage).", "Move the project closest to this job's duties to the top of your experience section."]
    return {"keywords": (matched + missing)[:12], "tips": tips}


def draft_email(profile: dict, job: dict, user_id: str | None = None) -> dict:
    data = llm.json(SYS, 'Write a polite cold email (90-120 words) to a recruiter about this job. JSON: {"subject": "...", "body": "..."}. Plain text, no placeholders, '
                         "mention 2 relevant strengths, ask for a short chat, sign with the candidate's name.\n\nCANDIDATE:\n" + _profile(profile) + "\n\nJOB:\n" + _job(job), user_id)
    if data and data.get("subject") and data.get("body"):
        return {"subject": str(data["subject"]), "body": str(data["body"])}
    return {"subject": f"{job.get('title')}: application from {_name(profile)}",
            "body": f"Hi,\n\nI applied for the {job.get('title')} role at {job.get('company')} and wanted to reach out directly. I have {profile.get('experience_years') or 'hands-on'} years of "
                    f"experience with {', '.join(job.get('matched') or _top(profile, 3))}. Could we have a short conversation?\n\nBest regards,\n{_name(profile)}"}


def draft_linkedin(profile: dict, job: dict, user_id: str | None = None) -> str:
    text = llm.complete(SYS, "Write a LinkedIn connection note to a recruiter, max 280 characters, friendly, no hashtags. Output only the note.\n\nCANDIDATE:\n" + _profile(profile) + "\n\nJOB:\n" + _job(job), user_id)
    role = (profile.get("target_roles") or ["engineer"])[0]
    return (text or f"Hi! I'm a {role} ({', '.join(_top(profile, 3))}) and applied for {job.get('title')} at {job.get('company')}. Would love to connect.").strip()[:300]


def follow_up_email(profile: dict, app: dict, user_id: str | None = None) -> dict:
    data = llm.json(SYS, 'Write a short follow-up email (70-100 words) about a job application sent a week ago. JSON: {"subject": "...", "body": "..."}. Polite, no placeholders.\n\n'
                         f"CANDIDATE:\n{_profile(profile)}\nAPPLICATION: {app.get('title')} at {app.get('company')}, applied on {app.get('applied_at')}", user_id)
    if data and data.get("subject") and data.get("body"):
        return {"subject": str(data["subject"]), "body": str(data["body"])}
    return {"subject": f"Following up: {app.get('title')} application",
            "body": f"Hi,\n\nI applied for the {app.get('title')} role at {app.get('company')} on {app.get('applied_at') or 'recently'} and wanted to check on the status. "
                    f"I remain very interested and happy to share anything that helps.\n\nThank you,\n{_name(profile)}"}


def practice_feedback(question: str, answer: str, user_id: str | None = None) -> dict:
    """Feedback on a mock interview answer. Simple rules work without AI; AI adds detail."""
    words = len(answer.split())
    has_number = bool(re.search(r"\d", answer))
    has_star = sum(1 for w in ("situation", "task", "action", "result", "because", "so that", "learned") if w in answer.lower())
    score = min(10, 2 + (3 if 40 <= words <= 180 else 1 if words >= 20 else 0) + (2 if has_number else 0) + min(3, has_star))
    improve = []
    if words < 40:
        improve.append("Add more detail: aim for 60 to 150 words.")
    if words > 220:
        improve.append("Tighten it: keep the answer under about 2 minutes.")
    if not has_number:
        improve.append("Add one measurable result (a number, percentage or time saved).")
    if has_star < 2:
        improve.append("Use the STAR shape: Situation, Task, Action, Result.")
    result = {"score": score, "improve": improve or ["Strong answer. Practise saying it out loud in under two minutes."], "ai": ""}
    text = llm.complete(SYS, f"Interview question: {question}\nCandidate answer: {answer}\nGive 3 short, specific coaching tips. Do not rewrite the whole answer.", user_id)
    if text:
        result["ai"] = text
    return result


def assistant_reply(profile: dict | None, history: list[dict], stats: dict, user_id: str | None = None) -> str:
    convo = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in history[-8:])
    text = llm.complete(SYS + " Answer in under 130 words and suggest a next step inside the app (Search, Profile, Applications, AI Studio, Interview, Autopilot).",
                        f"CANDIDATE:\n{_profile(profile) if profile else 'No resume uploaded yet'}\n\nAPP STATS: {stats}\n\n{convo}", user_id)
    if text:
        return text
    last = history[-1]["content"].lower()
    if not profile:
        return "Upload your resume on the Profile page first. Then I can summarise it, match jobs and prepare applications."
    if "summar" in last or "resume" in last:
        return f"{summary_line(profile)} ATS score: {profile.get('ats_score', 0)}/100."
    if "job" in last or "find" in last:
        return f"Open Jobs and press Search, or run Autopilot. You have {stats.get('saved', 0)} saved jobs and {stats.get('applications', 0)} applications."
    if "interview" in last:
        return "Open Interview, choose a job, and I will prepare questions and let you practise answers."
    return "I can summarise your resume, find jobs, write cover letters and prepare interviews. What would you like to do?"
