"""Resume text extraction + heuristic analysis. Works with zero AI keys (the 'mock fallback')."""
from __future__ import annotations

import io
import re
from datetime import datetime

from .skills import extract_skills, infer_roles

INDIA_CITIES = ["Bengaluru", "Bangalore", "Hyderabad", "Pune", "Mumbai", "Delhi", "New Delhi", "Gurugram", "Gurgaon", "Noida", "Chennai", "Kolkata", "Ahmedabad", "Guwahati", "Jaipur", "Kochi", "Coimbatore", "Indore", "Chandigarh"]
EDU_WORDS = r"(b\.?tech|b\.?e\b|bachelor|master|m\.?tech|mba|b\.?sc|m\.?sc|bca|mca|degree|university|college|institute|school|diploma|ph\.?d)"
SECTION_WORDS = {"summary": r"summary|objective|profile", "experience": r"experience|employment|work history", "education": r"education|academic", "skills": r"skills|technologies|tech stack", "projects": r"projects"}


def extract_text(filename: str, data: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages).strip()
    if name.endswith(".docx"):
        import docx

        d = docx.Document(io.BytesIO(data))
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            for row in t.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        return "\n".join(parts).strip()
    if name.endswith((".txt", ".md")):
        return data.decode("utf-8", errors="ignore").strip()
    raise ValueError("Unsupported file type. Upload a PDF, DOCX or TXT resume.")


def _guess_name(lines: list[str]) -> str:
    for ln in lines[:6]:
        clean = ln.strip()
        words = clean.split()
        if 2 <= len(words) <= 4 and all(re.fullmatch(r"[A-Za-z.'-]+", w) for w in words) and "@" not in clean:
            return clean.title() if clean.isupper() else clean
    return ""


def _estimate_years(text: str) -> float:
    explicit = [int(m.group(1)) for m in re.finditer(r"(\d{1,2})\+?\s*(?:years|yrs)\b", text, re.I)]
    explicit = [y for y in explicit if y <= 40]
    if explicit:
        return float(max(explicit))
    now = datetime.now().year
    lines = text.splitlines()
    total = 0
    for i, ln in enumerate(lines):
        ctx = (lines[i - 1] if i else "") + " " + ln
        if re.search(EDU_WORDS, ctx, re.I):
            continue
        for m in re.finditer(r"((?:19|20)\d{2})\s*(?:-|–|—|to)\s*((?:19|20)\d{2}|present|current|now)", ln, re.I):
            start = int(m.group(1))
            end = now if m.group(2).lower() in {"present", "current", "now"} else int(m.group(2))
            if 0 <= end - start <= 25:
                total += end - start
    return float(min(total, 30))


def ats_check(text: str, skills: list[str], email: str, phone: str) -> tuple[int, list[str]]:
    score, issues = 0, []
    low = text.lower()
    if email and phone:
        score += 15
    else:
        issues.append("Add a professional email and phone number at the top.")
    present = 0
    for key, pat in SECTION_WORDS.items():
        if re.search(rf"^\s*(?:{pat})\b", low, re.M):
            present += 1
        else:
            issues.append(f"Add a clear '{key.title()}' section heading so ATS parsers can find it.")
    score += present * 5
    score += min(20, len(skills) * 2)
    if len(skills) < 8:
        issues.append("List at least 8 relevant skills using standard names (e.g. 'PostgreSQL', not 'DB stuff').")
    metrics = len(re.findall(r"\d+\s*%|\$\s*\d|₹\s*\d|\b\d{2,}[kKmM]?\+?\s*(?:users|requests|customers|records|ms|x)\b", text))
    score += min(20, metrics * 5)
    if metrics < 3:
        issues.append("Quantify achievements (e.g. 'cut API latency by 35%', 'served 20k users').")
    words = len(text.split())
    if 300 <= words <= 1200:
        score += 10
    else:
        issues.append("Aim for 1–2 pages (about 300–1000 words).")
    if re.search(r"linkedin\.com|github\.com", low):
        score += 10
    else:
        issues.append("Link your LinkedIn and/or GitHub profile.")
    return min(score, 100), issues


def _first(pattern: str, text: str, flags: int = 0) -> str:
    m = re.search(pattern, text, flags)
    return m.group(0) if m else ""


def analyze_heuristic(text: str, filename: str = "") -> dict:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    email = _first(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    phone_raw = _first(r"(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{3,5}\)?[\s-]?)\d{3,5}[\s-]?\d{3,5}", text).strip()
    phone = phone_raw if len(re.sub(r"\D", "", phone_raw)) >= 10 else ""
    linkedin = _first(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w-]+", text, re.I)
    github = _first(r"(?:https?://)?(?:www\.)?github\.com/[\w-]+", text, re.I)
    skills = extract_skills(text)
    years = _estimate_years(text)
    roles = infer_roles(skills)
    seniority = "Entry level" if years < 2 else "Mid level" if years < 5 else "Senior" if years < 9 else "Lead / Principal"
    cities = [c for c in INDIA_CITIES if re.search(rf"\b{c}\b", text, re.I)]
    education = [ln for ln in lines if re.search(EDU_WORDS, ln, re.I)][:3]
    ats, issues = ats_check(text, skills, email, phone)
    headline = f"{roles[0]} · {years:g} yrs" if years else roles[0]
    return {
        "name": _guess_name(lines), "email": email, "phone": phone, "linkedin": linkedin, "github": github,
        "headline": headline, "summary": "", "skills": skills, "experience_years": years, "seniority": seniority,
        "target_roles": roles, "education": education, "current_location": cities[0] if cities else "",
        "preferred_regions": ["india", "remote"], "preferred_locations": cities[:2],
        "strengths": [], "gaps": [], "suggestions": issues, "ats_score": ats, "ai_enhanced": False,
    }
