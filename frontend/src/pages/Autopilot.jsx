import { useEffect, useState } from "react";
import { api } from "../api.js";

export default function Autopilot() {
  const [query, setQuery] = useState("");
  const [region, setRegion] = useState("all");
  const [location, setLocation] = useState("");
  const [run, setRun] = useState(null);
  const [last, setLast] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api("/api/autopilot/last").then((d) => setLast(d.run)).catch(() => {});
  }, []);

  async function start() {
    setError(""); setBusy(true); setRun(null);
    try {
      const d = await api("/api/autopilot/run", { method: "POST", body: { query, region, location, scan: 60, prepare: 3 } });
      setRun(d);
      setLast({ summary: d.summary, status: d.status, trace: d.trace });
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  const trace = run?.trace || last?.trace || [];
  const summary = run?.summary || last?.summary;

  return (
    <div>
      <h1>Autopilot</h1>
      <p className="muted">Seven agents — plan, scan, match, write letters, draft outreach, prepare interview, approval gate. They only draft; nothing is sent without your approval.</p>
      {error && <div className="error">{error}</div>}
      <div className="card">
        <label>Search (leave blank to use your profile)</label>
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. Python developer" />
        <div className="row">
          <div style={{ flex: 1 }}>
            <label>Region</label>
            <select value={region} onChange={(e) => setRegion(e.target.value)}>
              <option value="all">All regions</option><option value="india">India</option><option value="abroad">Abroad</option><option value="remote">Remote</option>
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label>Location</label>
            <input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="e.g. Pune" />
          </div>
        </div>
        <div style={{ marginTop: 12 }}>
          <button className="btn" disabled={busy} onClick={start}>{busy ? "Agents are working… (this can take a minute)" : "🚀 Run Autopilot"}</button>
        </div>
      </div>
      {summary && (
        <div className="card">
          <h2>Result — {run?.status || last?.status}</h2>
          <p>Scanned {summary.scanned} jobs · {summary.waiting} drafts waiting for approval · Engine: {summary.engine}</p>
          {summary.top?.length > 0 && (
            <ul>{summary.top.map((j) => <li key={j.id}>{j.title} at {j.company} — {j.score}% match</li>)}</ul>
          )}
        </div>
      )}
      {trace.length > 0 && (
        <div className="card">
          <h2>Agent trace</h2>
          {trace.map((t, i) => (
            <p key={i} className="small"><b>{t.agent}</b> [{t.status}] — {t.message}</p>
          ))}
          <p className="small muted">Review the drafts in AI Studio before approving anything.</p>
        </div>
      )}
    </div>
  );
}
