import { useState } from "react";
import { api } from "../api.js";

export default function Assistant() {
  const [messages, setMessages] = useState([
    { role: "assistant", content: "Hi! I can summarise your resume, find jobs, write cover letters and prepare interviews. What would you like to do?" },
  ]);
  const [input, setInput] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function send(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text) return;
    const next = [...messages, { role: "user", content: text }];
    setMessages(next);
    setInput("");
    setBusy(true);
    setError("");
    try {
      const d = await api("/api/ai/assistant", { method: "POST", body: { messages: next.filter((m) => m.role !== "assistant" || m.content !== next[0].content).slice(-8) } });
      setMessages([...next, { role: "assistant", content: d.reply }]);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1>Assistant</h1>
      <p className="muted">Chat about your search and resume. Uses Gemini when a free key is set, otherwise templates.</p>
      {error && <div className="error">{error}</div>}
      <div className="card">
        {messages.map((m, i) => (
          <p key={i} style={{ background: m.role === "user" ? "#eef2ff" : "#f9fafb", padding: 10, borderRadius: 8 }}>
            <b>{m.role === "user" ? "You" : "CareerPilot"}:</b> {m.content}
          </p>
        ))}
        <form onSubmit={send} className="row" style={{ marginTop: 10 }}>
          <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask about your resume, jobs, interviews…" style={{ flex: 1 }} />
          <button className="btn" disabled={busy}>{busy ? "…" : "Send"}</button>
        </form>
      </div>
    </div>
  );
}
