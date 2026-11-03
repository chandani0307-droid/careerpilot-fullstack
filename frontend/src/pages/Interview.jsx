import { useState } from "react";
import { api } from "../api.js";

export default function Interview() {
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [desc, setDesc] = useState("");
  const [prep, setPrep] = useState(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [feedback, setFeedback] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function generate() {
    if (!title.trim()) { setError("Enter a job title first."); return; }
    setError(""); setBusy(true);
    try {
      const d = await api("/api/ai/interview-prep", { method: "POST", body: { job: { id: "adhoc", title, company, description: desc, tags: [] } } });
      setPrep(d);
      setQuestion(d.questions?.[0]?.question || "");
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function practice() {
    if (!question.trim() || !answer.trim()) { setError("Pick a question and write an answer first."); return; }
    setError(""); setBusy(true);
    try {
      setFeedback(await api("/api/ai/practice-feedback", { method: "POST", body: { question, answer } }));
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  return (
    <div>
      <h1>Interview Prep</h1>
      <p className="muted">Job-specific questions, tips and a practice room with feedback.</p>
      {error && <div className="error">{error}</div>}
      <div className="card">
        <label>Job title</label>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Data Analyst" />
        <label>Company</label>
        <input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="e.g. Bharat Retail Analytics" />
        <label>Job description (optional)</label>
        <textarea value={desc} onChange={(e) => setDesc(e.target.value)} />
        <div style={{ marginTop: 12 }}>
          <button className="btn" disabled={busy} onClick={generate}>{busy ? "Preparing…" : "Prepare interview sheet"}</button>
        </div>
      </div>
      {prep && (
        <div className="card">
          <h2>{prep.job?.title} at {prep.job?.company} {prep.ai_enhanced ? "(AI enhanced)" : "(template)"}</h2>
          <h3>Questions</h3>
          <ol>{prep.questions.map((q, i) => (
            <li key={i} style={{ marginBottom: 10 }}>
              <b>{q.question}</b>
              <div className="small muted">{q.type} — {q.tip}</div>
              <button className="btn ghost" style={{ marginTop: 4 }} onClick={() => setQuestion(q.question)}>Practise this one</button>
            </li>
          ))}</ol>
          <h3>Technical topics to revise</h3>
          <ul>{prep.technical_topics.map((t, i) => <li key={i}>{t}</li>)}</ul>
          <h3>STAR stories to prepare</h3>
          <ul>{prep.star_stories.map((t, i) => <li key={i}>{t}</li>)}</ul>
          <h3>Questions to ask them</h3>
          <ul>{prep.questions_to_ask.map((t, i) => <li key={i}>{t}</li>)}</ul>
        </div>
      )}
      <div className="card">
        <h2>Practice room</h2>
        <label>Question</label>
        <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Pick a question above, or write your own" />
        <label>Your answer</label>
        <textarea value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Answer in 60–150 words, with one number…" />
        <div style={{ marginTop: 12 }}>
          <button className="btn" disabled={busy} onClick={practice}>Get feedback</button>
        </div>
        {feedback && (
          <div style={{ marginTop: 12 }}>
            <p><b>Score: {feedback.score}/10</b></p>
            <ul>{feedback.improve.map((t, i) => <li key={i}>{t}</li>)}</ul>
            {feedback.ai && <p>{feedback.ai}</p>}
          </div>
        )}
      </div>
    </div>
  );
}
