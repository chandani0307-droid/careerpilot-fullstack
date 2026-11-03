import { useEffect, useState } from "react";
import { api } from "../api.js";

export default function Settings() {
  const [status, setStatus] = useState(null);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");
  const [oldPw, setOldPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [msg, setMsg] = useState("");
  const [keyInput, setKeyInput] = useState("");
  const [keyStatus, setKeyStatus] = useState(null);
  const [keyMsg, setKeyMsg] = useState("");

  useEffect(() => {
    api("/api/settings/status").then(setStatus).catch((e) => setError(e.message));
    api("/api/analytics/summary").then(setSummary).catch(() => {});
    api("/api/settings/api-key").then(setKeyStatus).catch(() => {});
  }, []);

  async function changePassword(e) {
    e.preventDefault();
    setError(""); setMsg("");
    try {
      await api("/api/auth/change-password", { method: "POST", body: { old: oldPw, new: newPw } });
      setMsg("Password changed.");
      setOldPw(""); setNewPw("");
    } catch (err) { setError(err.message); }
  }
  async function saveKey(e) {
    e.preventDefault();
    setError(""); setKeyMsg("");
    try {
      const r = await api("/api/settings/api-key", { method: "POST", body: { key: keyInput } });
      setKeyStatus({ has_key: true, masked: r.masked, mode: "own_key" });
      setKeyInput("");
      setKeyMsg("Saved. Real AI will now use your own key and your own free quota.");
      const s = await api("/api/settings/status");
      setStatus(s);
    } catch (err) { setError(err.message); }
  }
  async function removeKey() {
    setError(""); setKeyMsg("");
    try {
      await api("/api/settings/api-key", { method: "DELETE" });
      setKeyStatus({ has_key: false, masked: null, mode: "templates" });
      setKeyMsg("Your key was removed. AI will use templates unless a shared key is set.");
      const s = await api("/api/settings/status");
      setStatus(s);
    } catch (err) { setError(err.message); }
  }
  async function exportData() {
    const d = await api("/api/profile/export");
    const blob = new Blob([JSON.stringify(d, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "careerpilot_my_data.json";
    a.click();
  }

  return (
    <div>
      <h1>Settings</h1>
      <p className="muted">Your account, your data and what is switched on in this app.</p>
      {error && <div className="error">{error}</div>}
      {msg && <div className="success">{msg}</div>}
      <div className="card">
        <h2>Job sources — 100% free</h2>
        {status ? (
          <>
            <p>{status.sources.join(", ")}</p>
            <div className="success">{status.free_note}</div>
            <h3>AI</h3>
            <p>Gemini is <b>{status.gemini.available ? `on (${status.gemini.model})` : "off — templates are used"}</b>. {status.ai_note}</p>
            {status.ai_daily_limit !== null && status.ai_daily_limit !== undefined && (
              <p>You have used {status.ai_used_today} of {status.ai_daily_limit} AI requests today.</p>
            )}
            <h3>Database</h3>
            <p>{status.database}</p>
            <p>Email sending: <b>{status.email}</b></p>
          </>
        ) : <p className="muted">Loading…</p>}
      </div>
      {summary && (
        <div className="card">
          <h2>Analytics</h2>
          <p>Applications: {summary.applications} · Applied: {summary.applied} · Response rate: {summary.response_rate}% · Avg match: {summary.avg_match}%</p>
          <p>By status: {Object.entries(summary.by_status).map(([k, v]) => `${k}: ${v}`).join(" · ")}</p>
          <p>By region: {Object.entries(summary.by_region).map(([k, v]) => `${k}: ${v}`).join(" · ")}</p>
        </div>
      )}
      <div className="card">
        <h2>Your own Gemini API key</h2>
        <p className="muted">
          Use your own free Gemini key and real AI runs on <b>your</b> quota — no shared limit.
          Get a free key from <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer">Google AI Studio</a> (free, 2 minutes).
          Your key is stored encrypted, only ever used for your own AI calls, and never shown to anyone else — not even its full value to you after saving.
        </p>
        {keyMsg && <div className="success">{keyMsg}</div>}
        {keyStatus?.has_key ? (
          <>
            <p>Saved key: <b>{keyStatus.masked}</b></p>
            <p className="muted">To change it, paste a new key below and save. To stop using it, remove it.</p>
          </>
        ) : (
          <p className="muted">No key saved yet. AI uses templates until you add one (or a shared key is set).</p>
        )}
        <form onSubmit={saveKey}>
          <label>{keyStatus?.has_key ? "New Gemini API key" : "Gemini API key"}</label>
          <input type="password" value={keyInput} onChange={(e) => setKeyInput(e.target.value)} placeholder="AIza..." required autoComplete="off" />
          <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
            <button className="btn">Save my key</button>
            {keyStatus?.has_key && (
              <button type="button" className="btn secondary" onClick={removeKey}>Remove my key</button>
            )}
          </div>
        </form>
      </div>
      <div className="card">
        <h2>Change password</h2>
        <form onSubmit={changePassword}>
          <label>Current password</label>
          <input type="password" value={oldPw} onChange={(e) => setOldPw(e.target.value)} required />
          <label>New password</label>
          <input type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} required />
          <div style={{ marginTop: 12 }}><button className="btn">Change password</button></div>
        </form>
      </div>
      <div className="card">
        <h2>Your data</h2>
        <button className="btn secondary" onClick={exportData}>Download all my data (JSON)</button>
      </div>
    </div>
  );
}
