"""Transparent job-to-profile scoring. Rule based, explainable, no AI needed."""
import re

from .skills import extract_skills

_STOP = {"senior", "sr", "junior", "jr", "lead", "staff", "principal", "the", "a", "of", "and", "remote", "i", "ii", "iii", "-", "/", "&"}


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9+#.]+", (text or "").lower()) if t not in _STOP and len(t) > 1}


def match_job(profile: dict, job: dict) -> dict:
    """Return {score 0-100, reasons, matched skills, missing skills} for one job."""
    mine = {s.lower() for s in profile.get("skills") or []}
    blob = " ".join([job.get("title", ""), " ".join(job.get("tags") or []), (job.get("description") or "")[:3000]])
    wanted = extract_skills(blob)
    matched = [s for s in wanted if s.lower() in mine]
    missing = [s for s in wanted if s.lower() not in mine][:6]
    skill_c = (0.6 * len(matched) / len(wanted) + 0.4 * min(1.0, len(matched) / 5)) if wanted else 0.3

    roles = " ".join(profile.get("target_roles") or []) + " " + (profile.get("headline") or "")
    role_tokens = _tokens(roles) | {t.lower() for s in mine for t in re.findall(r"[A-Za-z0-9+#.]+", s)}
    title_tokens = _tokens(job.get("title", ""))
    shared = title_tokens & role_tokens
    title_c = min(1.0, len(shared) / max(1, len(title_tokens)) * 1.6) if title_tokens else 0.0

    pref = 0.0
    if job.get("region") in (profile.get("preferred_regions") or []):
        pref += 0.6
    if any(loc and loc.lower() in (job.get("location") or "").lower() for loc in profile.get("preferred_locations") or []):
        pref += 0.4

    years, title = float(profile.get("experience_years") or 0), (job.get("title") or "").lower()
    penalty = 0.12 if (years < 2 and re.search(r"senior|lead|principal|staff|head|manager|architect", title)) or \
        (years >= 6 and re.search(r"intern|junior|trainee|fresher|graduate", title)) else 0.0
    score = max(5, min(98, round(100 * (0.6 * skill_c + 0.3 * title_c + 0.1 * min(pref, 1.0) - penalty))))

    reasons = []
    if matched:
        reasons.append(f"Matches {len(matched)} of your skills: {', '.join(matched[:5])}")
    if shared:
        reasons.append(f"Title fits your profile ({', '.join(sorted(shared)[:3])})")
    if job.get("region") in (profile.get("preferred_regions") or []):
        reasons.append(f"In a region you prefer ({job['region']})")
    if penalty:
        reasons.append("Seniority may not match your experience")
    return {"score": score, "reasons": reasons or ["Little overlap with your listed skills"], "matched": matched, "missing": missing}
