# CareerPilot frontend (React + Vite)

Plain React (JavaScript, no TypeScript) + Vite. No paid UI kit, plain CSS.
It calls the real FastAPI backend — nothing here is a mock.

## Run locally

```bash
npm install
npm run dev        # http://localhost:5173
```

The backend must be running at `http://localhost:8000` (see `../backend/README.md`).
To point at a deployed backend instead:

```bash
VITE_API_URL=https://your-backend.onrender.com npm run dev
```

## Pages

Login/Signup, Dashboard, Find Jobs, Applications, Autopilot, AI Studio,
Interview Prep, Assistant, Profile, Settings. The login token is stored in
`localStorage` (`careerpilot_token`).

## Build

```bash
npm run build      # outputs dist/
npm run preview    # serve the production build locally
```
