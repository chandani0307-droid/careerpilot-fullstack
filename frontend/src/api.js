// Tiny fetch wrapper for the CareerPilot FastAPI backend.
// API base comes from VITE_API_URL, default http://localhost:8000
export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export function getToken() {
  return localStorage.getItem("careerpilot_token") || "";
}
export function setToken(t) {
  if (t) localStorage.setItem("careerpilot_token", t);
  else localStorage.removeItem("careerpilot_token");
}

export async function api(path, { method = "GET", body, form, auth = true } = {}) {
  const headers = {};
  let payload;
  if (form) {
    payload = form; // FormData: let the browser set the content type
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  if (auth) {
    const t = getToken();
    if (t) headers["Authorization"] = `Bearer ${t}`;
  }
  const res = await fetch(`${API_URL}${path}`, { method, headers, body: payload });
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const msg = (data && (data.detail || data.message)) || `Request failed (${res.status})`;
    const err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    err.status = res.status;
    throw err;
  }
  return data;
}
