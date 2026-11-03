import { useEffect, useState } from "react";
import { api } from "../api.js";

const TONES = ["professional", "friendly", "concise", "enthusiastic"];

export default function Studio() {
  const [drafts, setDrafts] = useState([]);
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [desc, setDesc] = useState("");
  const [tone, setTone] = useState("professional");
  const [letter, setLetter] = useState("");
  const [tips, setTips] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  function loadDrafts() {
    api("/api/drafts").then((d) => setDrafts(d.drafts)).catch(() => {});
  }
  useEffect(loadDrafts, []);

  const job = { id: "adhoc", title, company, description: desc, tags: [] };

  async function writeLetter() {
    if (!title.trim() || !company.trim()) { setError("Enter a job title and company first."); return; }
    setError(""); setBusy(true);
    try {
      const d = await api("/api/ai/cover-letter", { method: "POST", body: { job, tone } });
      setLetter(d.text);
      setMsg("Saved as a draft for your approval.");
      loadDrafts();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function getTips() {
    if (!title.trim()) { setError("Enter a job title first."); return; }
    setError(""); setBusy(true);
    try {
      setTips(await api("/api/ai/tailor-tips", { method: "POST", body: { job } }));
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function approve(draft) {
    try {
      const d = await api(`/api/drafts/${draft.id}/approve`, { method: "POST", body: { confirm: true, recipient: draft.recipient || null } });
      setMsg(d.result?.message || "Approved.");
      loadDrafts();
    } catch (e) { setError(e.message); }
  }
  async function reject(draft) {
    await api(`/api/drafts/${draft.id}/reject`, { method: "POST", body: {} });
    loadDrafts();
  }

  return (
    <div>
      <h1>AI Studio</h1>
      <p className="muted">Cover letters and resume tips. Nothing is sent until you approve it.</p>
      {error && <div className="error">{error}</div>}
      {msg && <div className="success">{msg}</div>}
      <div className="card">
        <label>Job title</label>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Python Backend Engineer" />
        <label>Company</label>
        <input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="e.g. Nimbus Labs" />
        <label>Job description (optional — paste a few lines for better tailoring)</label>
        <textarea value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="What the job asks for…" />
        <label>Tone</label>
        <select value={tone} onChange={(e) => setTone(e.target.value)}>
          {TONES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <div className="row" style={{ marginTop: 12 }}>
          <button className="btn" disabled={busy} onClick={writeLetter}>{busy ? "Writing…" : "Write cover letter"}</button>
          <button className="btn secondary" disabled={busy} onClick={getTips}>Resume tailoring tips</button>
        </div>
      </div>
      {letter && <div className="card"><h2>Cover letter</h2><pre>{letter}</pre></div>}
      {tips && (
        <div className="card">
          <h2>Tailoring tips</h2>
          {tips.keywords?.length > 0 && <p>{tips.keywords.map((k) => <span key={k} className="chip">{k}</span>)}</p>}
          <ul>{tips.tips.map((t, i) => <li key={i}>{t}</li>)}</ul>
        </div>
      )}
      <div className="card">
        <h2>Drafts waiting for approval ({drafts.filter((d) => d.status === "draft").length})</h2>
        {drafts.length === 0 ? <p className="muted">No drafts yet.</p> : drafts.map((d) => (
          <div key={d.id} style={{ borderTop: "1px solid #e5e7eb", paddingTop: 10, marginTop: 10 }}>
            <p><b>{d.kind}</b> · {d.title} · <i>{d.status}</i></p>
            {d.subject && <p className="small">Subject: {d.subject}</p>}
            <pre>{d.body}</pre>
            {d.result?.message && <p className="small muted">{d.result.message}</p>}
            {d.status === "draft" && (
              <div className="row">
                <button className="btn" onClick={() => approve(d)}>Approve</button>
                <button className="btn ghost" onClick={() => reject(d)}>Reject</button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
