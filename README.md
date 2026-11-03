# CareerPilot — Full-stack version (FastAPI + React)

The same CareerPilot job-search copilot, rebuilt without Streamlit:
a **FastAPI backend** (`backend/`) and a **React + Vite frontend** (`frontend/`).
The Streamlit version still lives in `~/workspace/careerpilot-free/` and is untouched.

**100% free to use — no key, no payment, no paid job board.** Jobs come only
from free, no-key sources: Remotive, RemoteOK, Arbeitnow, Jobicy, Himalayas,
The Muse, RSS. Applying is free too: the Apply button goes to the employer's
free listing, and CareerPilot never asks anyone to pay to see or apply for a job.

**India-first, not US-only.** CareerPilot is built mainly for Indian users:
when no region is chosen, India jobs rank above equally relevant jobs
elsewhere, and Find Jobs defaults to the India region with one-tap city
shortcuts (Bengaluru, Hyderabad, Pune, Mumbai, Delhi NCR, Chennai).

**Fast search.** Each source's pages are fetched in parallel, and a repeat
search within 10 minutes is served instantly from a short-lived cache, so a
search that used to take ~24s now takes a few seconds the first time and is
instant on repeat. (The free Render backend still sleeps after ~15 minutes
idle, so the very first visit after a long pause takes ~1 minute to wake up —
after that it is fast.)

## What changed vs the Streamlit version

| | Streamlit version | This version |
|---|---|---|
| UI | Streamlit pages (`ui/`, `views/`, `app.py`) | React + Vite SPA (`frontend/`) |
| Server | Streamlit runs the Python UI | FastAPI REST API (`backend/main.py`, `/api/*`) |
| Auth | Streamlit session state | Bearer token (HMAC-signed, 30 days, in `localStorage`) |
| Data / AI / search | `core/` + `services/` | Same `core/` + `services/` copied verbatim |
| Deploy | Streamlit Cloud | Render (backend) + Vercel (frontend) |

`core/` and `services/` were copied unchanged from the free version — same
scrypt password hashing, same SQLite/PostgreSQL store, same free search, same
Gemini-or-template AI writing. Only the presentation layer is new.

## Run locally

Backend (port 8000):

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # optional; set a real SECRET_KEY for real use
uvicorn main:app --reload --port 8000
```

Frontend (port 5173):

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173, create an account, upload a resume on the Profile
page, then press Search. API docs: http://localhost:8000/docs

## Free deploy

| Piece | Free host | Notes |
|---|---|---|
| Backend | Render free web service | `render.yaml` in this repo is a ready Blueprint: Render > New > Blueprint, connect this repo. Or create the service manually with root `backend/`, build `pip install -r requirements.txt`, start `uvicorn main:app --host 0.0.0.0 --port $PORT`. Sleeps after 15 min idle, ~1 min to wake. |
| Frontend | Vercel free | Import `frontend/` (`vercel.json` is included, Vite + SPA fallback). Set env `VITE_API_URL=https://your-backend.onrender.com`. |
| Database | Neon free PostgreSQL | Set `DATABASE_URL` on Render. Without it the backend uses local SQLite (data is lost on Render restarts — use Neon for real use). |
| AI | Gemini, free AI Studio key | Optional shared fallback: set `GEMINI_API_KEY` on Render. Better: each user enters their OWN free key on the Settings page (encrypted, own quota, no shared limit). Without any key, templates are used. |

No job-search key is needed at all. There is no Adzuna / JSearch / RapidAPI
anywhere in this code (only a comment noting they were removed).

## Your own Gemini key (per user)

Each user can enter **their own free Gemini key** on the Settings page
(free key from [Google AI Studio](https://aistudio.google.com/apikey), 2 minutes).
The key is encrypted in the database, only ever used for that user's own AI
calls (cover letters, interview prep, assistant), and never shown in full —
only a masked preview like `••••cdef`. With your own key, your own free quota
applies and there is no shared daily limit. Without any key, templates are used.

## Tests

```bash
cd backend
python tests/run_all.py    # 32/32: original core/service tests + FastAPI TestClient smoke tests
```

## Honest limits

- Free job sources have thinner coverage for onsite jobs in India than paid
  boards do — that is the trade-off for keeping it 100% free. Remote and
  abroad coverage is much stronger. Checked 2026-11-02: Indeed India and
  CareerJet RSS feeds are 404, RemoteOK's RSS feed is 404, and Naukri /
  LinkedIn offer no free open API, so no free no-key source can list India
  onsite jobs the way a paid board does. What India-first means here: India
  jobs from the free sources (including remote roles open to India) rank
  first, the app defaults to India, and the RSS provider no longer dies
  when one feed goes down.
- No email verification or "forgot password" yet (needs an email service).
  Google sign-in from the Streamlit version was not carried over.
- Autopilot runs synchronously in the API request, so a run can take up to
  about a minute; the frontend shows a busy state while it runs.
- Render's free tier sleeps after inactivity; the first request after a
  quiet period can take a minute to wake.
- Respect each job site's terms. This app uses their public APIs and feeds
  only, and never automates LinkedIn.
