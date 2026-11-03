import { useEffect, useState } from "react";
import { api } from "../api.js";

export default function Dashboard({ go }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/api/dashboard").then(setData).catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="error">{error}</div>;
  if (!data) return <p className="muted">Loading dashboard…</p>;
  const s = data.summary;

  return (
    <div>
      <h1>Dashboard</h1>
      <p className="muted">Your next best actions, at a glance.</p>
      {!data.profile && (
        <div className="notice">
          Upload your resume on the Profile page to get match scores and missing skills on every job.
          <div style={{ marginTop: 8 }}><button className="btn" onClick={() => go("profile")}>Go to Profile</button></div>
        </div>
      )}
      <div className="grid">
        <div className="kpi"><div className="v">{s.applications}</div><div className="l">Applications</div></div>
        <div className="kpi"><div className="v">{s.saved}</div><div className="l">Saved jobs</div></div>
        <div className="kpi"><div className="v">{s.interviews}</div><div className="l">Interviews</div></div>
        <div className="kpi"><div className="v">{s.offers}</div><div className="l">Offers</div></div>
        <div className="kpi"><div className="v">{s.response_rate}%</div><div className="l">Response rate</div></div>
        <div className="kpi"><div className="v">{s.avg_match}%</div><div className="l">Average match</div></div>
        <div className="kpi"><div className="v">{s.total_searches ?? 0}</div><div className="l">Searches done</div></div>
        <div className="kpi"><div className="v">{s.total_jobs_found ?? s.results ?? 0}</div><div className="l">Jobs found in total</div></div>
      </div>
      {s.last_search && (
        <p className="muted">Last search: <b>{s.last_search.query}</b> · {s.last_search.found} jobs · {String(s.last_search.created_at || "").slice(0, 10)}</p>
      )}
      <div className="card">
        <h2>Recent searches — saved to your account</h2>
        {!data.recent_searches || data.recent_searches.length === 0 ? <p className="muted">No searches yet. Search once on Find Jobs and it will stay here, under your account.</p> : data.recent_searches.map((h) => (
          <p key={h.id} className="small">
            <b>{h.query}</b> · {h.region}{h.location ? ` · ${h.location}` : ""} · {h.found} jobs · {String(h.created_at || "").slice(0, 10)}{" "}
            <button className="btn secondary" onClick={() => go("jobs", { searchId: h.id })}>View jobs</button>
          </p>
        ))}
      </div>
      <div className="card">
        <h2>Follow-ups due</h2>
        {s.due.length === 0 ? <p className="muted">Nothing due.</p> : s.due.map((a) => (
          <p key={a.id}><b>{a.title}</b> at {a.company} · due {a.follow_up}</p>
        ))}
      </div>
      <div className="card">
        <h2>Skill gaps in your latest results</h2>
        {Object.keys(s.gaps || {}).length === 0 ? <p className="muted">Search for jobs first — gaps show up here.</p> : (
          <p>{Object.entries(s.gaps).map(([k, v]) => <span key={k} className="chip miss">{k} ×{v}</span>)}</p>
        )}
        <h3>Jobs by source</h3>
        <p>{Object.entries(s.by_source || {}).map(([k, v]) => <span key={k} className="chip src">{k}: {v}</span>)}</p>
      </div>
      <div className="card">
        <h2>Recent activity</h2>
        {data.recent_events.length === 0 ? <p className="muted">No activity yet.</p> : data.recent_events.map((e, i) => (
          <p key={i} className="small">{e.created_at?.slice(0, 10)} · {e.status} — {e.title} at {e.company}</p>
        ))}
      </div>
      <div className="row">
        <button className="btn" onClick={() => go("jobs")}>Find jobs</button>
        <button className="btn secondary" onClick={() => go("autopilot")}>Run Autopilot</button>
      </div>
    </div>
  );
}
