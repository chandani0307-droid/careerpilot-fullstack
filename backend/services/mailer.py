"""Sends email only if SMTP is set up. Otherwise it returns a mailto: link for the user to open."""
import smtplib
from email.message import EmailMessage
from urllib.parse import quote

from core.config import cfg


def send_or_link(to: str, subject: str, body: str) -> dict:
    if cfg.smtp_ready:
        s = cfg.smtp
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = s["sender"], to, subject
        msg.set_content(body)
        with smtplib.SMTP(s["host"], s["port"], timeout=15) as server:
            server.starttls()
            server.login(s["user"], s["password"])
            server.send_message(msg)
        return {"message": f"Email sent to {to}"}
    return {"url": f"mailto:{quote(to)}?subject={quote(subject)}&body={quote(body)}", "message": "SMTP is not set up, so your email app opens with the draft."}
