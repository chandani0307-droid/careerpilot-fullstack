import { useEffect, useState } from "react";
import { api } from "../api.js";

const STATUSES = ["saved", "applied", "screening", "interview", "offer", "rejected"];

export default function Applications() {
  const [apps, setApps] = useState([]);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState(null);
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");

  function load() {
    api("/api/applications").then((d) => setApps(d.applications)).catch((e) => setError(e.message));
  }
  useEffect(load, []);

  async function setStatus(app, status) {
    await api(`/api/applications/${app.id}`, { method: "PATCH", body: { status } });
    load();
  }
  async function remove(app) {
    if (!confirm(`Delete the application for ${app.title} at ${app.company}?`)) return;
    await api(`/api/applications/${app.id}`, { method: "DELETE" });
    setDetail(null);
    load();
  }
  async function addManual(e) {
    e.preventDefault();
    if (!title.trim() || !company.trim()) return;
    await api("/api/applications", { method: "POST", body: { title, company, status: "saved" } });
    setTitle("");
    setCompany("");
    load();
  }
  async function openDetail(app) {
    const d = await api(`/api/applications/${app.id}`);
    setDetail(d);
  }

  return (
    <div>
      <h1>Applications</h1>
      <p className="muted">Every application, its status and its timeline.</p>
      {error && <div className="error">{error}</div>}
      <form className="card" onSubmit={addManual}>
        <h2>Add one manually</h2>
        <div className="row">
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Job title" />
          <input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Company" />
          <button className="btn">Add</button>
        </div>
      </form>
      {apps.length === 0 ? <p className="muted">No applications yet. Apply from Find Jobs, or add one above.</p> : (
        <div className="card">
          <table>
            <thead><tr><th>Job</th><th>Company</th><th>Status</th><th>Match</th><th>Applied</th><th></th></tr></thead>
            <tbody>
              {apps.map((a) => (
                <tr key={a.id}>
                  <td>{a.title}</td><td>{a.company}</td>
                  <td>
                    <select value={a.status} onChange={(e) => setStatus(a, e.target.value)}>
                      {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </td>
                  <td>{a.match_score ? `${a.match_score}%` : "–"}</td>
                  <td>{a.applied_at || "–"}</td>
                  <td><button className="btn ghost" onClick={() => openDetail(a)}>Details</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {detail && (
        <div className="card">
          <h2>{detail.application.title} at {detail.application.company}</h2>
          <p className="muted">{detail.application.location} · Status: {detail.application.status} · Follow-up: {detail.application.follow_up || "none"}</p>
          {detail.application.notes && <p>Notes: {detail.application.notes}</p>}
          {detail.application.cover_letter && <pre>{detail.application.cover_letter}</pre>}
          <h3>Timeline</h3>
          {detail.events.map((e) => (
            <p key={e.id} className="small">{e.created_at?.slice(0, 10)} · {e.status}{e.note ? ` — ${e.note}` : ""}</p>
          ))}
          <div className="row">
            <button className="btn ghost" onClick={() => setDetail(null)}>Close</button>
            <button className="btn danger" onClick={() => remove(detail.application)}>Delete application</button>
          </div>
        </div>
      )}
    </div>
  );
}
