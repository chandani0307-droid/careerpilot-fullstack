import { useEffect, useState } from "react";
import { api } from "../api.js";

const REGIONS = [["all", "All regions"], ["india", "India"], ["abroad", "Abroad"], ["remote", "Remote"]];
const INDIA_CITIES = ["Bengaluru", "Hyderabad", "Pune", "Mumbai", "Delhi NCR", "Chennai"];

function JobCard({ job, onChanged }) {
  const [letter, setLetter] = useState("");
  const [showLetter, setShowLetter] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  async function save() {
    setBusy(true);
    try {
      const d = await api("/api/jobs/save", { method: "POST", body: { job } });
      onChanged({ saved: d.saved });
    } catch (e) { setMsg(e.message); } finally { setBusy(false); }
  }
  async function applied() {
    setBusy(true);
    try {
      await api("/api/jobs/apply", { method: "POST", body: { job } });
      onChanged({ applied: true });
    } catch (e) { setMsg(e.message); } finally { setBusy(false); }
  }
  async function coverLetter() {
    setBusy(true);
    setShowLetter(true);
    try {
      const d = await api("/api/ai/cover-letter", { method: "POST", body: { job, tone: "professional" } });
      setLetter(d.text);
    } catch (e) { setLetter(`Could not write a cover letter: ${e.message}`); } finally { setBusy(false); }
  }

  return (
    <div className="job">
      <div className="job-head">
        <h3>{job.title}</h3>
        {job.score > 0 && <span className="match">Match {job.score}%</span>}
      </div>
      <div className="meta">{[job.company, job.location, job.salary, job.posted_at].filter(Boolean).join(" · ")}</div>
      <div style={{ marginTop: 8 }}>
        <span className="chip src">{job.source}</span>
        <span className="chip">{job.region}</span>
        {(job.matched || []).slice(0, 5).map((s) => <span key={s} className="chip ok">{s}</span>)}
        {(job.missing || []).slice(0, 3).map((s) => <span key={s} className="chip miss">+ {s}</span>)}
        {(job.tags || []).slice(0, 4).map((s) => <span key={s} className="chip">{s}</span>)}
      </div>
      {(job.reasons || []).length > 0 && <p className="small muted">{job.reasons.slice(0, 2).join(" · ")}</p>}
      {job.description && (
        <details><summary>Job details</summary><p>{job.description.slice(0, 1200)}</p></details>
      )}
      <div className="actions">
        <a className="btn" href={job.apply_url || job.url} target="_blank" rel="noreferrer">Apply ↗</a>
        <button className="btn secondary" disabled={busy} onClick={save}>{job.saved ? "Saved" : "Save"}</button>
        <button className="btn secondary" disabled={busy || job.applied} onClick={applied}>{job.applied ? "Tracked" : "I applied"}</button>
        <button className="btn ghost" disabled={busy} onClick={coverLetter}>Cover letter</button>
      </div>
      <p className="small muted">{job.source === "Himalayas" ? "Apply on Himalayas — free, no plan needed. Himalayas Plus ($9/mo) is only for AI tools, not required to apply." : `Free to apply on ${job.source} — no payment needed to apply.`}</p>
      {msg && <div className="error">{msg}</div>}
      {showLetter && (
        <div>
          <h3>Cover letter {busy ? "(writing…)" : ""}</h3>
          <pre>{letter}</pre>
          <p className="small muted">Saved as a draft for your approval — check AI Studio / Drafts before using it.</p>
        </div>
      )}
    </div>
  );
}

export default function Jobs() {
  const [q, setQ] = useState("");
  const [location, setLocation] = useState("");
  const [region, setRegion] = useState("india");
  const [level, setLevel] = useState("any");
  const [jobType, setJobType] = useState("any");
  const [posted, setPosted] = useState(0);
  const [sort, setSort] = useState("best");
  const [minMatch, setMinMatch] = useState(0);
  const [jobs, setJobs] = useState([]);
  const [report, setReport] = useState(null);
  const [tab, setTab] = useState("India");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [searched, setSearched] = useState(false);

  async function search(params) {
    setError("");
    setBusy(true);
    try {
      const d = await api("/api/jobs/search?" + new URLSearchParams({
        q: params.q, region: params.region, location: params.location, limit: "60",
        sort: params.sort, level: params.level, job_type: params.jobType, posted_days: String(params.posted),
      }).toString());
      let list = d.jobs;
      if (params.minMatch) list = list.filter((j) => (j.score || 0) >= params.minMatch);
      setJobs(list);
      setReport(d.report);
      setSearched(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function submit(e) {
    e.preventDefault();
    search({ q, region, location, sort, level, jobType, posted, minMatch });
  }

  const groups = {
    All: jobs,
    India: jobs.filter((j) => j.region === "india"),
    Abroad: jobs.filter((j) => j.region === "abroad"),
    Remote: jobs.filter((j) => j.region === "remote"),
  };
  const shown = groups[tab] || jobs;
  // Update one card in place — saving/applying must not re-run the whole live search.
  function patchJob(id, patch) {
    setJobs((prev) => prev.map((j) => (j.id === id ? { ...j, ...patch } : j)));
  }

  return (
    <div>
      <h1>Find jobs</h1>
      <p className="muted">India-first: India jobs are shown first. One search looks across many free job sources at once and ranks the results for you.</p>
      <form className="card" onSubmit={submit}>
        <div className="row">
          <div style={{ flex: 3, minWidth: 220 }}>
            <label>What job are you looking for?</label>
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. Python developer, data analyst. Leave blank to use my profile" />
          </div>
          <div style={{ flex: 2, minWidth: 180 }}>
            <label>City or country (optional)</label>
            <input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="e.g. Bengaluru, Pune" />
          </div>
        </div>
        <p className="small" style={{ marginTop: 8 }}>Popular in India:{" "}
          {INDIA_CITIES.map((c) => (
            <button key={c} type="button" className="city-link" onClick={() => { setLocation(c); setRegion("india"); }}>{c}</button>
          ))}
        </p>
        <label>Where?</label>
        <div className="tabs">
          {REGIONS.map(([v, l]) => (
            <button type="button" key={v} className={region === v ? "active" : ""} onClick={() => setRegion(v)}>{l}</button>
          ))}
        </div>
        <div className="row">
          <div style={{ flex: 1, minWidth: 120 }}>
            <label>Level</label>
            <select value={level} onChange={(e) => setLevel(e.target.value)}>
              {["any", "junior", "mid", "senior", "lead"].map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>
          <div style={{ flex: 1, minWidth: 120 }}>
            <label>Job type</label>
            <select value={jobType} onChange={(e) => setJobType(e.target.value)}>
              {["any", "full-time", "contract", "internship", "part-time"].map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>
          <div style={{ flex: 1, minWidth: 120 }}>
            <label>Posted</label>
            <select value={posted} onChange={(e) => setPosted(Number(e.target.value))}>
              <option value={0}>Any time</option><option value={1}>Last 24 hours</option><option value={7}>Last 7 days</option><option value={30}>Last 30 days</option>
            </select>
          </div>
          <div style={{ flex: 1, minWidth: 120 }}>
            <label>Sort by</label>
            <select value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="best">Best match</option><option value="newest">Newest</option>
            </select>
          </div>
          <div style={{ flex: 1, minWidth: 120 }}>
            <label>Hide jobs below match %</label>
            <input type="number" min={0} max={90} step={5} value={minMatch} onChange={(e) => setMinMatch(Number(e.target.value))} />
          </div>
        </div>
        <div style={{ marginTop: 14 }}>
          <button className="btn" disabled={busy}>{busy ? "Searching…" : "Search jobs"}</button>
        </div>
      </form>

      {error && <div className="error">{error}</div>}
      {report && (
        <p><b>{jobs.length} jobs</b> from {Object.values(report.sources).filter((s) => s.count).length} sources in {report.elapsed}s · searched: <i>{report.queries.join(", ")}</i></p>
      )}
      {report?.sample > 0 && (
        <div className="notice">Live sources returned very few jobs, so some clearly marked sample jobs were added. Check your internet and try again — no key or payment is needed.</div>
      )}
      {searched && (
        <div className="tabs">
          {Object.entries(groups).map(([name, items]) => (
            <button key={name} className={tab === name ? "active" : ""} onClick={() => setTab(name)}>{name} ({items.length})</button>
          ))}
        </div>
      )}
      {searched && shown.length === 0 && <p className="muted">Nothing here for this search.</p>}
      {!searched && <p className="muted">Press Search jobs above. A blank search uses your profile.</p>}
      {shown.map((job) => (
        <JobCard key={job.id} job={job} onChanged={(patch) => patchJob(job.id, patch)} />
      ))}
    </div>
  );
}
