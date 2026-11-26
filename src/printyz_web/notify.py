"""Notifications: e-mail (SMTP) and free WhatsApp options.

- Owner WhatsApp: CallMeBot (free personal API; the owner activates it once for their own number).
- Customer WhatsApp: no paid API - the admin page builds a wa.me link with a ready message that the
  owner sends from their own WhatsApp in one tap.
"""

from __future__ import annotations

import logging
import smtplib
import threading
import urllib.parse
import urllib.request
from email.message import EmailMessage

from .settings import Settings

log = logging.getLogger("printyz.notify")
OUTBOX: list[dict] = []          # used by the "memory" backend (tests / local preview)


def send_email(s: Settings, to: str, subject: str, body: str, html: str | None = None,
               attachments: list[tuple[str, bytes, str]] | None = None) -> None:
    msg = {"to": to, "subject": subject, "body": body, "html": html,
           "attachments": [a[0] for a in (attachments or [])]}
    if s.email_backend == "memory":
        OUTBOX.append(msg)
        return
    if s.email_backend == "console" or not s.smtp_host:
        log.warning("EMAIL (not sent - no SMTP configured) to=%s subject=%s", to, subject)
        OUTBOX.append(msg)
        return

    def _send():
        try:
            m = EmailMessage()
            m["From"] = s.mail_from or s.smtp_user
            m["To"] = to
            m["Subject"] = subject
            m.set_content(body)
            if html:
                m.add_alternative(html, subtype="html")
            for name, data, mime in attachments or []:
                maintype, subtype = mime.split("/", 1)
                m.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30) as smtp:
                smtp.starttls()
                if s.smtp_user:
                    smtp.login(s.smtp_user, s.smtp_password)
                smtp.send_message(m)
        except Exception:  # noqa: BLE001 - a mail failure must never lose the order
            log.exception("email to %s failed", to)

    threading.Thread(target=_send, daemon=True).start()


def whatsapp_owner(s: Settings, text: str) -> None:
    """Free WhatsApp message to the owner's own number via CallMeBot (if configured)."""
    if not (s.owner_whatsapp and s.callmebot_apikey) or s.email_backend == "memory":
        OUTBOX.append({"to": "whatsapp:owner", "subject": "", "body": text})
        return
    url = ("https://api.callmebot.com/whatsapp.php?" +
           urllib.parse.urlencode({"phone": s.owner_whatsapp, "text": text, "apikey": s.callmebot_apikey}))

    def _send():
        try:
            urllib.request.urlopen(url, timeout=20).read()
        except Exception:  # noqa: BLE001
            log.exception("WhatsApp notification failed")

    threading.Thread(target=_send, daemon=True).start()


def wa_link(phone: str, text: str) -> str:
    """https://wa.me link that opens WhatsApp with a ready message (Israeli 05x numbers -> 9725x)."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits.startswith("0"):
        digits = "972" + digits[1:]
    return f"https://wa.me/{digits}?text={urllib.parse.quote(text)}"
