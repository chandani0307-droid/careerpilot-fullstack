import { useEffect, useState } from "react";
import { api, getToken, setToken } from "./api.js";
import Auth from "./pages/Auth.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Jobs from "./pages/Jobs.jsx";
import Applications from "./pages/Applications.jsx";
import Studio from "./pages/Studio.jsx";
import Interview from "./pages/Interview.jsx";
import Profile from "./pages/Profile.jsx";
import Settings from "./pages/Settings.jsx";
import Autopilot from "./pages/Autopilot.jsx";
import Assistant from "./pages/Assistant.jsx";

const PAGES = [
  ["dashboard", "Dashboard"],
  ["jobs", "Find Jobs"],
  ["applications", "Applications"],
  ["autopilot", "Autopilot"],
  ["studio", "AI Studio"],
  ["interview", "Interview Prep"],
  ["assistant", "Assistant"],
  ["profile", "Profile"],
  ["settings", "Settings"],
];

export default function App() {
  const [user, setUser] = useState(null);
  const [page, setPage] = useState("dashboard");
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    if (!getToken()) {
      setChecking(false);
      return;
    }
    api("/api/auth/me")
      .then((d) => setUser(d.user))
      .catch(() => setToken(""))
      .finally(() => setChecking(false));
  }, []);

  if (checking) return <div className="wrap"><p className="muted">Loading CareerPilot…</p></div>;
  if (!user) return <Auth onLogin={setUser} />;

  function logout() {
    setToken("");
    setUser(null);
  }

  return (
    <div>
      <header className="topbar">
        <span className="brand">Career<span>Pilot</span></span>
        <nav>
          {PAGES.map(([key, label]) => (
            <button key={key} className={page === key ? "active" : ""} onClick={() => setPage(key)}>
              {label}
            </button>
          ))}
        </nav>
        <span className="spacer" />
        <span className="who">{user.name} · {user.email}</span>
        <button className="btn ghost" onClick={logout}>
          Log out
        </button>
      </header>
      <main className="wrap">
        {page === "dashboard" && <Dashboard go={setPage} />}
        {page === "jobs" && <Jobs />}
        {page === "applications" && <Applications />}
        {page === "autopilot" && <Autopilot />}
        {page === "studio" && <Studio />}
        {page === "interview" && <Interview />}
        {page === "assistant" && <Assistant />}
        {page === "profile" && <Profile />}
        {page === "settings" && <Settings />}
      </main>
      <footer className="footer">
        <b>CareerPilot</b> · Free forever — jobs only from free sources. Applying never costs anything.
      </footer>
    </div>
  );
}
