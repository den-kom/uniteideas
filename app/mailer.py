"""Development mailer: writes messages to data/outbox instead of sending email.

Replace with a real provider (SES / Postmark / Resend) before public launch.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.config import get_settings

logger = logging.getLogger("uniteideas.mail")


def send(to: str, subject: str, body: str) -> str:
    settings = get_settings()
    settings.outbox_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    safe_to = to.replace("@", "_at_").replace("/", "_")
    path = settings.outbox_dir / f"{stamp}-{safe_to}.txt"
    path.write_text(f"To: {to}\nSubject: {subject}\n\n{body}\n", encoding="utf-8")
    logger.info("Queued dev email to %s (%s)", to, path.name)
    return str(path)
