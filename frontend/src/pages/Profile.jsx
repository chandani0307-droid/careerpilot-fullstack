import { useEffect, useState } from "react";
import { api, API_URL, getToken } from "../api.js";

export default function Profile() {
  const [profile, setProfile] = useState(null);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  function load() {
    api("/api/profile").then((d) => setProfile(d.profile)).catch((e) => setError(e.message));
  }
  useEffect(load, []);

  async function uploadText() {
    if (text.trim().length < 50) { setError("Paste a longer resume (at least 50 characters)."); return; }
    setError(""); setBusy(true);
    try {
      const d = await api("/api/profile/text", { method: "POST", body: { resume_text: text, filename: "resume.txt" } });
      setProfile(d.profile);
      setMsg("Resume analysed and saved.");
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function uploadFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(""); setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API_URL}/api/profile/upload`, {
        method: "POST", headers: { Authorization: `Bearer ${getToken()}` }, body: form,
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || "Upload failed");
      setProfile(d.profile);
      setMsg("Resume analysed and saved.");
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  }

  const data = profile?.data || {};
  return (
    <div>
      <h1>Profile</h1>
      <p className="muted">Upload your resume to get match scores, skill gaps and tailored advice.</p>
      {error && <div className="error">{error}</div>}
      {msg && <div className="success">{msg}</div>}
      <div className="card">
        <label>Upload resume (PDF, DOCX or TXT)</label>
        <input type="file" accept=".pdf,.docx,.txt,.md" onChange={uploadFile} disabled={busy} />
        <label>…or paste your resume text</label>
        <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste your full resume here…" style={{ minHeight: 160 }} />
        <div style={{ marginTop: 12 }}>
          <button className="btn" disabled={busy} onClick={uploadText}>{busy ? "Analysing…" : "Analyse resume"}</button>
        </div>
      </div>
      {profile && (
        <div className="card">
          <h2>{data.headline || "Your profile"}</h2>
          <p><b>ATS score:</b> {data.ats_score}/100 · <b>Experience:</b> {data.experience_years} yrs · <b>Level:</b> {data.seniority}</p>
          {data.summary && <p>{data.summary}</p>}
          <h3>Skills</h3>
          <p>{(data.skills || []).map((s) => <span key={s} className="chip ok">{s}</span>)}</p>
          <h3>Target roles</h3>
          <p>{(data.target_roles || []).join(", ") || "—"}</p>
          <h3>Strengths</h3>
          <ul>{(data.strengths || []).map((s, i) => <li key={i}>{s}</li>)}</ul>
          <h3>Improve</h3>
          <ul>{(data.gaps || []).concat(data.suggestions || []).map((s, i) => <li key={i}>{s}</li>)}</ul>
          <p className="small muted">File: {profile.filename} · Updated: {profile.updated_at?.slice(0, 10)}</p>
        </div>
      )}
    </div>
  );
}
