"""Job search: 100% free sources in parallel, merged, de-duplicated, filtered and ranked.

100% FREE: every source below needs no key and no payment, for CareerPilot
and for the person applying. No paid job board is used at all — Adzuna and
JSearch (which needed a key) were removed on purpose, so no user is ever sent
to a paid site to see or apply for a job.
Free sources: Remotive, RemoteOK, Arbeitnow, Jobicy, Himalayas, The Muse, RSS.
Every source is wrapped so one failure never breaks the search. Sample jobs only fill in when live results are very few.
"""
import hashlib
import html
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from core.config import cfg
from services.matching import match_job
from services.skills import extract_skills

UA = "CareerPilot/1.0 (personal job search assistant)"
URLS = {  # kept in one place so tests can point them at a fake server
    "remotive": "https://remotive.com/api/remote-jobs", "remoteok": "https://remoteok.com/api",
    "arbeitnow": "https://www.arbeitnow.com/api/job-board-api", "jobicy": "https://jobicy.com/api/v2/remote-jobs",
    "himalayas": "https://himalayas.app/jobs/api/search", "muse": "https://www.themuse.com/api/public/jobs",
}
INDIA = ["india", "bengaluru", "bangalore", "hyderabad", "pune", "mumbai", "delhi", "gurgaon", "gurugram", "noida", "chennai", "kolkata",
         "ahmedabad", "guwahati", "jaipur", "kochi", "coimbatore", "indore", "chandigarh", "thiruvananthapuram", "nagpur", "lucknow"]
REMOTE = ["remote", "anywhere", "worldwide", "work from home", "wfh", "flexible"]
STOP = {"developer", "engineer", "job", "jobs", "in", "and", "the", "of", "for", "a", "an", "to", "with", "at", "or", "role", "position"}
ALIASES = {"ml": ["machine learning"], "ai": ["machine learning", "artificial intelligence"], "js": ["javascript"], "frontend": ["front end", "react"],
           "front end": ["frontend", "react"], "backend": ["back end", "api"], "fullstack": ["full stack"], "full stack": ["fullstack"],
           "devops": ["site reliability", "cloud engineer"], "data scientist": ["machine learning"], "data analyst": ["business analyst", "analytics"],
           "qa": ["test automation", "quality assurance"], "sde": ["software engineer"], "software engineer": ["software developer"]}
MUSE_CATEGORIES = {"data": ["Data and Analytics", "Data Science"], "analy": ["Data and Analytics"], "design": ["Design and UX"], "product": ["Product Management"],
                   "market": ["Marketing"], "sales": ["Sales"], "devops": ["Software Engineering"], "software": ["Software Engineering"],
                   "engineer": ["Software Engineering"], "develop": ["Software Engineering"], "python": ["Software Engineering"], "react": ["Software Engineering"]}


# ───────────────────────── HTTP (tests replace http_get) ─────────────────────────
def http_get(url: str, params: dict | None = None, headers: dict | None = None, timeout: float | None = None) -> str:
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout or cfg.http_timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def get_json(url, params=None, headers=None):
    return json.loads(http_get(url, params, headers))


# ───────────────────────── normalising ─────────────────────────
def clean(text, limit: int = 3500) -> str:
    text = re.sub(r"<(script|style).*?</\1>", " ", str(text or ""), flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</p>|</li>|</div>", "\n", text, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", text)).strip()[:limit]


def norm_date(value) -> str:
    """Anything a source gives us (ISO text, RFC 2822, epoch seconds or milliseconds) -> YYYY-MM-DD, or ''."""
    try:
        if value in (None, "", 0):
            return ""
        if isinstance(value, (int, float)) or str(value).isdigit():
            v = float(value)
            return datetime.fromtimestamp(v / 1000 if v > 1e11 else v, tz=timezone.utc).strftime("%Y-%m-%d")
        text = str(value).strip()
        if re.match(r"\d{4}-\d{2}-\d{2}", text):
            return text[:10]
        return parsedate_to_datetime(text).astimezone(timezone.utc).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return ""


def classify_region(location: str, remote: bool = False) -> str:
    loc = (location or "").lower()
    if any(w in loc for w in INDIA):
        return "india"
    if remote or any(w in loc for w in REMOTE):
        return "remote"
    return "abroad"


def infer_level(title: str) -> str:
    t = (title or "").lower()
    if re.search(r"senior|\bsr\b|lead|principal|staff|architect", t):
        return "senior"
    if re.search(r"junior|\bjr\b|intern|trainee|graduate|fresher|entry", t):
        return "junior"
    if re.search(r"manager|head of|director|vp ", t):
        return "lead"
    return "mid"


def infer_type(text: str) -> str:
    t = (text or "").lower()
    if "intern" in t:
        return "internship"
    if re.search(r"contract|freelance|temporary", t):
        return "contract"
    if "part" in t and "time" in t:
        return "part-time"
    return "full-time"


def make_job(*, title, company, location, url, source, apply_url="", description="", tags=None, salary="", posted="", job_type="", remote=False):
    title, url = str(title or "").strip(), str(url or "").strip()
    if not title or not url:
        return None
    location = str(location or "").strip() or ("Remote" if remote else "Not specified")
    if remote and "remote" not in location.lower():
        location = "Remote" if location in ("Not specified", "Worldwide") else f"Remote ({location})"
    tags = [str(t).strip() for t in (tags or []) if t and str(t).strip()][:10]
    return {"id": hashlib.sha1(url.encode()).hexdigest()[:16], "title": title[:200], "company": str(company or "Unknown").strip()[:120], "location": location[:160],
            "region": classify_region(location, remote), "url": url, "apply_url": str(apply_url or url).strip(), "description": clean(description),
            "source": source, "tags": tags, "salary": str(salary or "").strip()[:60], "posted_at": norm_date(posted), "job_type": infer_type(str(job_type or title)),
            "level": infer_level(title)}


def salary_text(low, high, currency="", period=""):
    try:
        if low and high:
            return f"{currency} {int(float(low)):,}–{int(float(high)):,} {period}".strip()
    except (TypeError, ValueError):
        pass
    return ""


# ───────────────────────── providers: each returns a list of jobs and may raise (the caller catches) ─────────────────────────
def p_remotive(q, region, location, limit):
    data = get_json(URLS["remotive"], {"search": q, "limit": min(limit, 60)})
    return [make_job(title=j.get("title"), company=j.get("company_name"), location=j.get("candidate_required_location") or "Worldwide", remote=True, url=j.get("url"),
                     description=j.get("description"), source="Remotive", tags=(j.get("tags") or []) + [j.get("category")], salary=j.get("salary"),
                     posted=j.get("publication_date"), job_type=j.get("job_type")) for j in data.get("jobs", [])]


def p_remoteok(q, region, location, limit):
    return [make_job(title=j.get("position"), company=j.get("company"), location=j.get("location") or "Worldwide", remote=True, url=j.get("url"), apply_url=j.get("apply_url"),
                     description=j.get("description"), source="RemoteOK", tags=j.get("tags"), salary=salary_text(j.get("salary_min"), j.get("salary_max"), "$"),
                     posted=j.get("date") or j.get("epoch")) for j in get_json(URLS["remoteok"]) if isinstance(j, dict) and j.get("position")]


def p_arbeitnow(q, region, location, limit):
    out = []
    for page in (1, 2):
        for j in get_json(URLS["arbeitnow"], {"page": page}).get("data", []):
            out.append(make_job(title=j.get("title"), company=j.get("company_name"), location=j.get("location") or "Europe", remote=bool(j.get("remote")), url=j.get("url"),
                                description=j.get("description"), source="Arbeitnow", tags=j.get("tags"), posted=j.get("created_at"), job_type=" ".join(j.get("job_types") or [])))
    return out


def p_jobicy(q, region, location, limit):
    data = get_json(URLS["jobicy"], {"count": min(limit, 100), "tag": q})
    out = []
    for j in data.get("jobs", []):
        jt = j.get("jobType")
        out.append(make_job(title=j.get("jobTitle"), company=j.get("companyName"), location=j.get("jobGeo") or "Anywhere", remote=True, url=j.get("url"),
                            description=j.get("jobDescription") or j.get("jobExcerpt"), source="Jobicy", tags=([j.get("jobIndustry")] if isinstance(j.get("jobIndustry"), str) else j.get("jobIndustry")),
                            salary=salary_text(j.get("annualSalaryMin"), j.get("annualSalaryMax"), j.get("salaryCurrency") or "", "/yr"), posted=j.get("pubDate"),
                            job_type=" ".join(jt) if isinstance(jt, list) else jt))
    return out


def p_himalayas(q, region, location, limit):
    out = []
    for page in range(1, 3):
        for j in get_json(URLS["himalayas"], {"q": q, "sort": "recent", "page": page}).get("jobs", []):
            places = j.get("locationRestrictions") or []
            out.append(make_job(title=j.get("title"), company=j.get("companyName"), location=", ".join(places) if places else "Worldwide", remote=True,
                                url=j.get("applicationLink") or j.get("guid"), description=j.get("description") or j.get("excerpt"), source="Himalayas",
                                tags=(j.get("categories") or []) + [str(x) for x in (j.get("seniority") or [])] if isinstance(j.get("seniority"), list) else (j.get("categories") or []),
                                salary=salary_text(j.get("minSalary"), j.get("maxSalary"), j.get("currency") or "", j.get("salaryPeriod") or ""),
                                posted=j.get("pubDate") or j.get("publishedAt"), job_type=j.get("employmentType")))
    return out


def p_muse(q, region, location, limit):
    cats = []
    for key, names in MUSE_CATEGORIES.items():
        if key in q.lower():
            cats += [n for n in names if n not in cats]
    out = []
    for category in (cats or ["Software Engineering"])[:2]:
        for page in range(0, 2):
            for j in get_json(URLS["muse"], {"category": category, "page": page}).get("results", []):
                places = [x.get("name", "") for x in j.get("locations") or []]
                out.append(make_job(title=j.get("name"), company=(j.get("company") or {}).get("name"), location=", ".join(places) or "Flexible / Remote",
                                    url=(j.get("refs") or {}).get("landing_page"), description=j.get("contents"), source="The Muse",
                                    tags=[c.get("name") for c in j.get("categories") or []] + [lv.get("name") for lv in j.get("levels") or []], posted=j.get("publication_date")))
    return out


# NOTE: Adzuna and JSearch were removed here on purpose (2026-11-02).
# They needed an API key / paid plan, so no user is ever sent to a paid site.
# Only free, no-key sources remain below.


def p_rss(q, region, location, limit):
    out = []
    for feed in cfg.rss_feeds:
        root = ET.fromstring(http_get(feed))
        for item in root.iter("item"):
            raw = (item.findtext("title") or "").strip()
            company, title = ("", raw)
            if ":" in raw:
                company, title = [s.strip() for s in raw.split(":", 1)]
            out.append(make_job(title=title, company=company or "Unknown", location="Remote", remote=True, url=item.findtext("link"), description=item.findtext("description"),
                                source="RSS", posted=item.findtext("pubDate")))
    return out


# name -> (function, accepts a search term, is it available?)
PROVIDERS = {
    "Remotive": (p_remotive, True, lambda: True), "RemoteOK": (p_remoteok, False, lambda: True), "Arbeitnow": (p_arbeitnow, False, lambda: True),
    "Jobicy": (p_jobicy, True, lambda: True), "Himalayas": (p_himalayas, True, lambda: True), "The Muse": (p_muse, True, lambda: True),
    "RSS": (p_rss, False, lambda: bool(cfg.rss_feeds)),
}


def active_sources() -> list[str]:
    return [name for name, (_, _, ready) in PROVIDERS.items() if ready()]


# ───────────────────────── sample jobs (only used when live results are very few) ─────────────────────────
_SAMPLE = [("Python Backend Engineer", "Nimbus Labs", "Bengaluru, India", ["Python", "FastAPI", "PostgreSQL", "Docker"]), ("Full Stack Developer", "Kiteworks India", "Pune, India", ["React", "Node.js", "TypeScript"]),
           ("Machine Learning Engineer", "Sutra AI", "Hyderabad, India", ["Python", "PyTorch", "NLP"]), ("Data Analyst", "Bharat Retail Analytics", "Gurugram, India", ["SQL", "Power BI", "Excel"]),
           ("DevOps Engineer", "CloudKaveri", "Chennai, India", ["Kubernetes", "Terraform", "AWS"]), ("Frontend Engineer", "Pixelwise", "Mumbai, India", ["React", "TypeScript", "Tailwind CSS"]),
           ("Generative AI Engineer", "Orbit Intelligence", "Bengaluru, India", ["LLMs", "LangChain", "RAG"]), ("Software Engineer", "Nordlicht GmbH", "Berlin, Germany", ["Java", "Spring Boot", "Kafka"]),
           ("Senior Python Developer", "Thames Digital", "London, United Kingdom", ["Python", "Django", "AWS"]), ("Data Scientist", "Maple Insights", "Toronto, Canada", ["Python", "Pandas", "Machine Learning"]),
           ("Full Stack Engineer", "Marina Pay", "Singapore", ["React", "Node.js", "PostgreSQL"]), ("AI Engineer", "Dune Robotics", "Dubai, UAE", ["Python", "Computer Vision", "PyTorch"]),
           ("Remote Python Developer", "Distributed Co", "Remote (Worldwide)", ["Python", "FastAPI", "Docker"]), ("Remote React Developer", "Lumen Apps", "Remote (Worldwide)", ["React", "TypeScript", "Next.js"]),
           ("Remote LLM Application Engineer", "Quill Systems", "Remote (Asia-friendly)", ["LLMs", "LangChain", "Python"]), ("Remote Data Engineer", "Streamline Data", "Remote (Worldwide)", ["Python", "Spark", "SQL"]),
           ("Remote QA Automation Engineer", "Bugless", "Remote (Worldwide)", ["Selenium", "Cypress", "Testing"]), ("Business Analyst", "Rangoli Finance", "Mumbai, India", ["SQL", "Excel", "Tableau"])]


def sample_jobs() -> list[dict]:
    out = []
    for title, company, location, tags in _SAMPLE:
        slug = re.sub(r"[^a-z0-9]+", "-", f"{company}-{title}".lower()).strip("-")
        out.append(make_job(title=title, company=company, location=location, remote="remote" in location.lower(), url=f"https://example.com/jobs/{slug}", source="Sample",
                            description=f"{company} is hiring a {title}. You will build and ship features using {', '.join(tags)}. Requirements: experience with {', '.join(tags)}.", tags=tags))
    return out


# ───────────────────────── queries, relevance and ranking ─────────────────────────
def expand_queries(query: str, profile: dict | None) -> list[str]:
    query = (query or "").strip()
    if query:
        found = [query]
        for key, alts in ALIASES.items():
            if re.search(rf"\b{re.escape(key)}\b", query.lower()):
                found += alts
        return list(dict.fromkeys(found))[:4]
    profile = profile or {}
    roles = [r.replace(" / ", " ") for r in (profile.get("target_roles") or [])[:2]]
    skills = profile.get("skills") or []
    extra = [f"{skills[0]} developer"] if skills else []
    return list(dict.fromkeys(roles + extra)) or ["software developer"]


def tokens_of(queries: list[str]) -> list[str]:
    out = []
    for q in queries:
        out += [t for t in re.findall(r"[a-z0-9+#.]+", q.lower()) if t not in STOP and len(t) > 1]
    return list(dict.fromkeys(out))


def relevance(tokens: list[str], phrase: str, job: dict) -> float:
    """0-100 how well a job fits the words the user searched for (title counts most)."""
    title, tags, desc = job["title"].lower(), " ".join(job["tags"]).lower(), job["description"].lower()
    if not tokens:
        return 50.0
    t_hits = sum(1 for t in tokens if t in title)
    g_hits = sum(1 for t in tokens if t in tags)
    d_hits = sum(1 for t in tokens if t in desc)
    score = (40 if phrase and phrase in title else 0) + (35 if t_hits == len(tokens) else min(30, 14 * t_hits)) + min(15, 8 * g_hits) + min(10, 3 * d_hits)
    if job.get("posted_at"):
        try:
            age = (datetime.now(timezone.utc) - datetime.strptime(job["posted_at"], "%Y-%m-%d").replace(tzinfo=timezone.utc)).days
            score += 8 if age <= 3 else 4 if age <= 14 else 0
        except ValueError:
            pass
    return float(min(100, score))


def _is_relevant(tokens, job) -> bool:
    if not tokens:
        return True
    title, tags, desc = job["title"].lower(), " ".join(job["tags"]).lower(), job["description"].lower()
    return any(t in title or t in tags for t in tokens) or sum(1 for t in tokens if t in desc) >= 2


def _dedupe(jobs: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for job in jobs:
        key = re.sub(r"[^a-z0-9]", "", f"{job['title']}{job['company']}".lower())
        if key not in best or len(job["description"]) > len(best[key]["description"]):
            best[key] = job
    return list(best.values())


def _passes(job: dict, region: str, location: str, f: dict) -> bool:
    if region != "all" and job["region"] != region:
        return False
    if location and location.lower() not in job["location"].lower() and not (location.lower() in ("bengaluru", "bangalore") and any(x in job["location"].lower() for x in ("bengaluru", "bangalore"))):
        return False
    if f.get("job_type") and f["job_type"] != "any" and job["job_type"] != f["job_type"]:
        return False
    if f.get("level") and f["level"] != "any" and job["level"] != f["level"]:
        return False
    if f.get("posted_days") and job["posted_at"]:
        try:
            if (datetime.now(timezone.utc) - datetime.strptime(job["posted_at"], "%Y-%m-%d").replace(tzinfo=timezone.utc)).days > f["posted_days"]:
                return False
        except ValueError:
            pass
    return True


def search_jobs(query: str = "", region: str = "all", location: str = "", limit: int = 60, profile: dict | None = None, filters: dict | None = None, sort: str = "best"):
    """Return (jobs, report). Each job gets relevance, and (when a profile is given) match score, matched and missing skills."""
    started, filters = time.time(), filters or {}
    queries = expand_queries(query, profile)
    tokens, phrase = tokens_of(queries), queries[0].lower()
    tasks = [(name, q) for name, (_, searchable, ready) in PROVIDERS.items() if ready() for q in (queries if searchable else queries[:1])]
    report = {"queries": queries, "sources": {name: {"count": 0, "error": ""} for name in active_sources()}}
    raw: list[dict] = []
    pool = ThreadPoolExecutor(max_workers=10)
    futures = {pool.submit(PROVIDERS[name][0], q, region, location, max(limit, 30)): name for name, q in tasks}
    try:
        for future in as_completed(futures, timeout=cfg.http_timeout * 2 + 6):
            name = futures[future]
            try:
                found = [j for j in future.result() if j]
                report["sources"][name]["count"] += len(found)
                raw += found
            except Exception as exc:  # noqa: BLE001  (a broken source must never break the search)
                report["sources"][name]["error"] = f"{type(exc).__name__}: {str(exc)[:80]}"
    except Exception:  # noqa: BLE001  (overall deadline: keep what we already have)
        pass
    pool.shutdown(wait=False, cancel_futures=True)

    jobs = [j for j in _dedupe(raw) if _is_relevant(tokens, j) and _passes(j, region, location, filters)]
    report["live"] = len(jobs)
    if cfg.mock_fallback and len(jobs) < 15:
        have = {j["id"] for j in jobs}
        extra = [j for j in sample_jobs() if j["id"] not in have and _is_relevant(tokens, j) and _passes(j, region, location, filters)]
        jobs += extra
        report["sample"] = len(extra)
    for job in jobs:
        job["relevance"] = relevance(tokens, phrase, job)
    attach_match(jobs, profile)
    if sort == "newest":
        jobs.sort(key=lambda j: (j["posted_at"] or "0000", j["relevance"]), reverse=True)
    else:
        jobs.sort(key=lambda j: j["relevance"] * (0.55 if profile else 1) + j.get("score", 0) * (0.45 if profile else 0), reverse=True)
    report["elapsed"] = round(time.time() - started, 1)
    report["candidates"] = len(raw)
    return jobs[:limit], report


def attach_match(jobs: list[dict], profile: dict | None) -> list[dict]:
    """Add score / matched / missing / reasons for this user. The scores are computed on the fly and never stored."""
    for job in jobs:
        if profile:
            m = match_job(profile, job)
            job.update(score=m["score"], reasons=m["reasons"], matched=m["matched"], missing=m["missing"])
        else:
            job.update(score=0, reasons=[], matched=[], missing=[])
    return jobs
