from tests.conftest_env import fresh_db  # noqa: E402

fresh_db()
import json  # noqa: E402
import os  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from http.server import BaseHTTPRequestHandler, HTTPServer  # noqa: E402
from urllib.parse import parse_qs, urlparse  # noqa: E402

from services import search  # noqa: E402

TOPICS = ["Python Developer", "Senior Python Engineer", "Backend Engineer Python", "Python Data Engineer", "Machine Learning Engineer", "React Developer",
          "Marketing Manager", "Sales Executive", "Full Stack Developer", "Data Analyst"]
RECENT = time.strftime("%Y-%m-%d")


def _title(i, tag):
    return f"{TOPICS[i % len(TOPICS)]} {tag}{i}"


def fake_http(url, params=None, headers=None, timeout=None):
    params = params or {}
    page = int(params.get("page", 1))
    base = page * 100
    if "remotive" in url:
        return json.dumps({"jobs": [{"title": _title(i, "R"), "company_name": f"RemCo{i}", "candidate_required_location": "Worldwide", "url": f"https://remotive.com/j/{params.get('search')}/{i}",
                                     "description": "<p>Build with Python and Docker</p>", "tags": ["python"], "category": "Software Development", "publication_date": RECENT, "job_type": "full_time"} for i in range(25)]})
    if "remoteok" in url:
        return json.dumps([{"legal": "x"}] + [{"position": _title(i, "O"), "company": f"OkCo{i}", "location": "Remote", "tags": ["python", "dev"], "description": "Python work", "url": f"https://remoteok.com/{i}",
                                               "apply_url": f"https://remoteok.com/apply/{i}", "salary_min": 60000, "salary_max": 90000, "date": RECENT + "T10:00:00+00:00"} for i in range(25)])
    if "arbeitnow" in url:
        return json.dumps({"data": [{"title": _title(i, "A") + str(page), "company_name": f"EuCo{i}", "location": "Berlin, Germany", "remote": i % 2 == 0, "tags": ["python"], "job_types": ["full time"],
                                     "url": f"https://arbeitnow.com/{page}/{i}", "description": "Python role", "created_at": int(time.time())} for i in range(20)]})
    if "jobicy" in url:
        return json.dumps({"jobs": [{"jobTitle": _title(i, "J"), "companyName": f"JobiCo{i}", "jobGeo": "Anywhere", "jobType": ["full-time"], "url": f"https://jobicy.com/{params.get('tag')}/{i}",
                                     "jobExcerpt": "Python things", "pubDate": RECENT + " 08:00:00", "annualSalaryMin": 50000, "annualSalaryMax": 80000, "salaryCurrency": "USD"} for i in range(20)]})
    if "himalayas" in url:
        return json.dumps({"jobs": [{"title": _title(i, "H") + str(page), "companyName": f"HimCo{i}", "applicationLink": f"https://himalayas.app/{params.get('q')}/{page}/{i}", "categories": ["Python"], "seniority": ["Senior"],
                                     "employmentType": "Full Time", "locationRestrictions": ["India"] if i % 3 == 0 else [], "minSalary": 40000, "maxSalary": 70000, "currency": "USD", "pubDate": int(time.time())} for i in range(20)]})
    if "themuse" in url:
        return json.dumps({"results": [{"name": _title(i, "M") + str(page), "company": {"name": f"MuseCo{i}"}, "locations": [{"name": "New York, NY"}], "levels": [{"name": "Mid Level"}], "categories": [{"name": "Software Engineering"}],
                                        "refs": {"landing_page": f"https://themuse.com/{params.get('category')}/{page}/{i}"}, "contents": "<p>Python</p>", "publication_date": RECENT + "T00:00:00Z"} for i in range(20)]})
    if "weworkremotely" in url:
        return "<rss><channel><item><title>RssCo: Python Remote Developer</title><link>https://wwr.example/1</link><description>Python</description><pubDate>Mon, 06 Oct 2025 10:00:00 +0000</pubDate></item></channel></rss>"
    raise RuntimeError("unknown url " + url)


def setup_module_env(keys=True):
    # Free version: no keys at all. Even if old keys are set, they must be ignored.
    search.http_get = fake_http
    search._SEARCH_CACHE.clear()  # each test starts with a cold cache
    for name in ("ADZUNA_APP_ID", "ADZUNA_APP_KEY", "RAPIDAPI_KEY"):
        os.environ.pop(name, None)
    if keys:
        os.environ.update(ADZUNA_APP_ID="id", ADZUNA_APP_KEY="key", RAPIDAPI_KEY="rk")


def test_returns_sixty_unique_relevant_jobs():
    setup_module_env()
    jobs, report = search.search_jobs("python developer", "all", "", 60)
    assert len(jobs) == 60, len(jobs)
    assert len({j["id"] for j in jobs}) == 60
    assert not any("Marketing" in j["title"] or "Sales" in j["title"] for j in jobs), "irrelevant jobs must be filtered out"
    # Relevance order is kept inside each source; the list is interleaved by
    # source so no one board dominates the first page.
    for s in {j["source"] for j in jobs}:
        rels = [j["relevance"] for j in jobs if j["source"] == s]
        assert rels == sorted(rels, reverse=True), s
    assert len({j["source"] for j in jobs[:10]}) >= 3, "top results must mix sources"
    assert all(report["sources"][s]["count"] > 0 for s in ("Remotive", "RemoteOK", "Arbeitnow", "Jobicy", "Himalayas", "The Muse"))
    assert "Adzuna" not in report["sources"] and "JSearch" not in report["sources"], "paid-key sources must not be used in the free version"
    assert set(search.active_sources()) == {"Remotive", "RemoteOK", "Arbeitnow", "Jobicy", "Himalayas", "The Muse", "RSS"}
    assert report.get("sample", 0) == 0 and report["live"] >= 60
    top = jobs[0]
    assert "python" in top["title"].lower() and top["region"] in ("india", "abroad", "remote")


def test_regions_are_separate_and_correct():
    setup_module_env()
    for region in ("india", "abroad", "remote"):
        jobs, _ = search.search_jobs("python", region, "", 60)
        assert jobs and all(j["region"] == region for j in jobs), region
    # Free version: no JSearch/Adzuna, so no fake Pune jobs remain.
    # Location filtering is still checked with a place the free sources do return.
    india, _ = search.search_jobs("python", "india", "india", 60)
    assert india and all("india" in j["location"].lower() for j in india)
    berlin, _ = search.search_jobs("python", "abroad", "berlin", 60)
    assert berlin and all("berlin" in j["location"].lower() for j in berlin)


def test_one_broken_source_does_not_break_search():
    setup_module_env()
    def flaky(url, params=None, headers=None, timeout=None):
        if "remotive" in url or "jobicy" in url:
            raise TimeoutError("down")
        return fake_http(url, params, headers, timeout)
    search.http_get = flaky
    jobs, report = search.search_jobs("python developer", "all", "", 60)
    assert len(jobs) == 60
    assert "TimeoutError" in report["sources"]["Remotive"]["error"] and report["sources"]["Remotive"]["count"] == 0


def test_all_sources_down_falls_back_to_clearly_marked_samples():
    setup_module_env(keys=False)
    def dead(url, params=None, headers=None, timeout=None):
        raise OSError("offline")
    search.http_get = dead
    jobs, report = search.search_jobs("python", "all", "", 60)
    assert jobs and all(j["source"] == "Sample" for j in jobs) and report["sample"] == len(jobs) and report["live"] == 0


def test_diversify_interleaves_sources_without_reordering_inside_a_source():
    a = [{"source": "Himalayas", "relevance": 90}, {"source": "Himalayas", "relevance": 80}, {"source": "Himalayas", "relevance": 70}]
    b = [{"source": "RemoteOK", "relevance": 85}, {"source": "RemoteOK", "relevance": 75}]
    out = search._diversify(a + b)
    assert [j["source"] for j in out] == ["Himalayas", "RemoteOK", "Himalayas", "RemoteOK", "Himalayas"]
    assert [j["relevance"] for j in out if j["source"] == "Himalayas"] == [90, 80, 70]


def test_filters_and_sorting():
    setup_module_env()
    senior, _ = search.search_jobs("python", "all", "", 60, filters={"level": "senior"})
    assert senior and all(j["level"] == "senior" for j in senior)
    newest, _ = search.search_jobs("python", "all", "", 60, sort="newest")
    # Newest order is kept inside each source; sources are interleaved.
    for s in {j["source"] for j in newest}:
        dates = [j["posted_at"] or "0000" for j in newest if j["source"] == s]
        assert dates == sorted(dates, reverse=True), s


def test_profile_scoring_changes_order_and_adds_skill_chips():
    setup_module_env()
    profile = {"skills": ["Python", "Docker", "PostgreSQL"], "target_roles": ["Backend Engineer"], "experience_years": 4, "preferred_regions": ["india"]}
    jobs, _ = search.search_jobs("python", "all", "", 30, profile=profile)
    assert all("score" in j and "matched" in j and "missing" in j for j in jobs)
    assert any("Python" in j["matched"] for j in jobs)


def test_blank_query_uses_profile_roles():
    setup_module_env()
    profile = {"skills": ["Python"], "target_roles": ["Data Analyst", "Backend Engineer"]}
    assert search.expand_queries("", profile)[:2] == ["Data Analyst", "Backend Engineer"]
    assert "machine learning" in search.expand_queries("ml engineer", None)


def test_dates_regions_and_types():
    assert search.norm_date("2026-05-01T10:00:00Z") == "2026-05-01" and search.norm_date(1700000000) == "2023-11-14"
    assert search.norm_date(1700000000000) == "2023-11-14" and search.norm_date("Mon, 06 Oct 2025 10:00:00 +0000") == "2025-10-06" and search.norm_date("junk") == ""
    assert search.classify_region("Bengaluru, Karnataka") == "india" and search.classify_region("Remote (Worldwide)") == "remote" and search.classify_region("Berlin, Germany") == "abroad"
    assert search.infer_level("Senior Data Engineer") == "senior" and search.infer_level("Software Engineering Intern") == "junior"
    assert search.infer_type("Contract Python Developer") == "contract"


def test_india_jobs_rank_first_when_region_all():
    setup_module_env()
    jobs, report = search.search_jobs("python", "all", "", 60)
    india_idx = [i for i, j in enumerate(jobs) if j["region"] == "india"]
    abroad_idx = [i for i, j in enumerate(jobs) if j["region"] == "abroad"]
    assert india_idx and abroad_idx
    assert report.get("india_boost") is True
    assert min(india_idx) < min(abroad_idx), "India jobs must rank first when no region is chosen"


def test_dead_rss_feed_does_not_kill_other_feeds():
    setup_module_env()
    def flaky(url, params=None, headers=None, timeout=None):
        if "jobspresso" in url:
            raise OSError("feed down")
        return fake_http(url, params, headers, timeout)
    search.http_get = flaky
    jobs = search.p_rss("python", "all", "", 30)
    assert jobs and all(j["source"] == "RSS" for j in jobs)


def test_default_rss_feeds_have_no_dead_remoteok_feed():
    import os as _os
    _os.environ.pop("JOB_RSS_FEEDS", None)
    from core.config import cfg as fresh_cfg
    assert not any("remoteok.com/rss" in f for f in fresh_cfg.rss_feeds)
    assert any("weworkremotely" in f for f in fresh_cfg.rss_feeds)


def test_real_http_function_reads_json_from_a_local_server():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"q": parse_qs(urlparse(self.path).query).get("q", [""])[0], "ua": self.headers.get("User-Agent", "")}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)
        def log_message(self, *a): pass
    server = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    data = json.loads(__import__("urllib.request", fromlist=["x"]).urlopen(__import__("urllib.request", fromlist=["x"]).Request(f"http://127.0.0.1:{server.server_port}/x?q=python", headers={"User-Agent": search.UA})).read())
    assert data["q"] == "python"
    real = search.__dict__["http_get"]
    search.http_get = fake_http  # restore the fake afterwards
    server.shutdown()


def test_repeat_search_is_cached_and_fast():
    setup_module_env()
    calls = {"n": 0}
    def counting(url, params=None, headers=None, timeout=None):
        calls["n"] += 1
        return fake_http(url, params, headers, timeout)
    search.http_get = counting
    jobs1, report1 = search.search_jobs("python developer", "all", "", 60)
    assert report1.get("cached") is False
    first_calls = calls["n"]
    assert first_calls > 0
    jobs2, report2 = search.search_jobs("python developer", "all", "", 60)
    assert report2.get("cached") is True
    assert calls["n"] == first_calls, "repeat search must not hit the network again"
    assert [j["id"] for j in jobs1] == [j["id"] for j in jobs2]
    # A different profile still gets its own match scores from the same cache.
    profile = {"skills": ["Python", "Docker", "PostgreSQL"], "target_roles": ["Backend Engineer"], "experience_years": 4, "preferred_regions": ["india"]}
    jobs3, report3 = search.search_jobs("python developer", "all", "", 60, profile=profile)
    assert report3.get("cached") is True
    assert all("score" in j and "matched" in j for j in jobs3)
    assert any(j.get("score", 0) > 0 for j in jobs3)


def test_slow_pages_fetch_in_parallel_not_one_by_one():
    setup_module_env()
    def slow(url, params=None, headers=None, timeout=None):
        time.sleep(1.0)
        return fake_http(url, params, headers, timeout)
    search.http_get = slow
    try:
        start = time.monotonic()
        # "data analyst" hits 2 Muse categories x 3 pages, 3 Himalayas queries
        # and 3 RSS feeds; sequential pages would take ~6s inside one provider.
        jobs, report = search.search_jobs("data analyst", "all", "", 60)
        elapsed = time.monotonic() - start
    finally:
        search.http_get = fake_http
    assert jobs
    assert elapsed < 3.5, f"search took {elapsed:.1f}s, pages are not fetched in parallel"
