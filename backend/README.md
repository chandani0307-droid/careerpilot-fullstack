# CareerPilot backend (FastAPI)

REST API for CareerPilot. Reuses `core/` and `services/` from the free
Streamlit version verbatim — same scrypt auth, same store, same free job
search, same Gemini-or-template AI. The Streamlit UI (`ui/`, `views/`,
`app.py`) is **not** used here; the React frontend in `../frontend/` calls
this API instead.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # optional; edit SECRET_KEY for real use
uvicorn main:app --reload --port 8000
```

API docs: http://localhost:8000/docs — Health: `GET /api/health`

## Endpoints (all under `/api/`)

| Group | Endpoints |
|---|---|
| Auth | `POST auth/signup`, `POST auth/login`, `GET auth/me`, `POST auth/change-password`, `DELETE auth/me` |
| Jobs | `GET jobs/search?q=&region=&location=&limit=&sort=`, `GET jobs/saved`, `POST jobs/save`, `POST jobs/apply` |
| Applications | `GET/POST applications`, `GET/PATCH/DELETE applications/{id}`, `GET applications/{id}/events` |
| Profile | `GET profile`, `POST profile/text`, `POST profile/upload`, `PATCH profile`, `GET profile/export` |
| AI | `POST ai/cover-letter`, `POST ai/tailor-tips`, `POST ai/interview-prep`, `POST ai/practice-feedback`, `POST ai/assistant`, `POST ai/follow-up?app_id=` |
| Autopilot | `POST autopilot/run`, `GET autopilot/last` |
| Your Gemini key | `GET/POST/DELETE settings/api-key` | Save your own free key (encrypted at rest, masked preview only). `GET settings/status` reports `ai_mode`: `own_key` / `shared` / `templates`. |
| Drafts | `GET/POST drafts`, `GET drafts/{id}`, `POST drafts/{id}/approve`, `POST drafts/{id}/reject` |
| Other | `GET settings/status`, `GET dashboard`, `GET analytics/summary`, `GET health` |

Auth is a Bearer token: an HMAC-signed `user_id.expiry.signature` (stdlib
only, `SECRET_KEY` env, 30-day expiry). Passwords stay scrypt-hashed via
`core.auth` — no new password scheme was invented.

## Free by design

- Job sources (free, no key): Remotive, RemoteOK, Arbeitnow, Jobicy,
  Himalayas, The Muse, RSS. No Adzuna, no JSearch/RapidAPI — they were
  removed from the free version and are not re-added here.
- Gemini is optional: set `GEMINI_API_KEY` (free AI Studio key) for real AI
  writing; without it every AI endpoint falls back to offline templates.
- Database: local SQLite by default; set `DATABASE_URL` to a free Neon
  PostgreSQL URL when deploying.
- CORS allows `http://localhost:5173` (Vite dev) and `https://*.vercel.app`.

## Tests

```bash
python tests/run_all.py
```

Runs the copied original tests (search, store, auth, services, approvals —
the Streamlit UI smoke test is not included, there is no Streamlit UI here)
plus `tests/test_backend.py`, a FastAPI TestClient smoke test with fake job
sources (no live network calls).
