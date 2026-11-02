"""Google Gemini over plain HTTPS (no extra library). Every method returns None on any problem,
so the app falls back to offline templates.

Which key is used, in order:
1. The user's OWN Gemini key (Settings page) — their own free quota applies,
   so no daily limit is enforced for them.
2. The server's shared GEMINI_API_KEY (optional) — a per-user daily limit
   protects the shared free quota.
3. No key at all — templates are used.
"""
import json
import re
import urllib.request

from core.config import cfg
from services import store


class LLM:
    last_error = ""

    @property
    def available(self) -> bool:
        """Is there a shared server key? (Kept for the unauthenticated health check.)"""
        return bool(cfg.gemini_key)

    def key_for_user(self, user_id: str | None) -> tuple[str, bool]:
        """Return (key, is_own_key) for this user."""
        if user_id:
            own = store.get_user_gemini_key(user_id)
            if own:
                return own, True
        return cfg.gemini_key or "", False

    def available_for(self, user_id: str | None) -> bool:
        return bool(self.key_for_user(user_id)[0])

    def mode_for(self, user_id: str | None) -> str:
        """'own_key' | 'shared' | 'templates' — what this user's AI calls will use."""
        key, own = self.key_for_user(user_id)
        if own:
            return "own_key"
        return "shared" if key else "templates"

    def complete(self, system: str, prompt: str, user_id: str | None = None, json_mode: bool = False) -> str | None:
        key, own = self.key_for_user(user_id)
        if not key:
            return None
        if user_id and not own and not store.bump_usage(user_id, cfg.daily_ai_limit):
            self.last_error = "Daily AI limit reached. Templates are used until tomorrow."
            return None
        body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.4, **({"responseMimeType": "application/json"} if json_mode else {})}}
        try:
            req = urllib.request.Request(f"{cfg.gemini_base}/models/{cfg.gemini_model}:generateContent", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json", "x-goog-api-key": key})
            with urllib.request.urlopen(req, timeout=50) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"]).strip()
            self.last_error = ""
            return text or None
        except Exception as exc:  # noqa: BLE001  (any AI problem means: use the template instead)
            self.last_error = f"{type(exc).__name__}: {str(exc)[:160]}"
            return None

    def json(self, system: str, prompt: str, user_id: str | None = None) -> dict | None:
        text = self.complete(system + "\nReply with one valid JSON object only.", prompt, user_id, json_mode=True)
        match = re.search(r"\{.*\}", text or "", re.S)
        try:
            return json.loads(match.group(0)) if match else None
        except json.JSONDecodeError:
            return None


llm = LLM()
