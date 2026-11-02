import { useState } from "react";
import { api, setToken } from "../api.js";

export default function Auth({ onLogin }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const path = mode === "login" ? "/api/auth/login" : "/api/auth/signup";
      const body = mode === "login" ? { email, password } : { email, password, name };
      const data = await api(path, { method: "POST", body, auth: false });
      setToken(data.token);
      onLogin(data.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="wrap">
      <div className="card authbox">
        <h1>🧭 CareerPilot</h1>
        <p className="muted">Free job-search copilot. No key, no payment — jobs come only from free sources.</p>
        <div className="tabs">
          <button className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>Log in</button>
          <button className={mode === "signup" ? "active" : ""} onClick={() => setMode("signup")}>Sign up</button>
        </div>
        <form onSubmit={submit}>
          {mode === "signup" && (
            <>
              <label>Your name</label>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Chandani" />
            </>
          )}
          <label>Email</label>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required placeholder="you@example.com" />
          <label>Password</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required placeholder="At least 8 characters, with a letter and a number" />
          {error && <div className="error">{error}</div>}
          <div style={{ marginTop: 14 }}>
            <button className="btn" disabled={busy}>{busy ? "Please wait…" : mode === "login" ? "Log in" : "Create account"}</button>
          </div>
        </form>
        <p className="small muted" style={{ marginTop: 14 }}>
          Your account is private to you. Nothing is sent or applied for without your approval.
        </p>
      </div>
    </div>
  );
}
