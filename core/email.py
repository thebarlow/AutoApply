"""Outbound email via Zoho SMTP. No-op (returns False) when SMTP env vars are
unset, so invite flows still work in local/dev without mail configured."""
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.zoho.com"
SMTP_PORT = 465


def _app_base_url() -> str:
    return os.getenv("APP_BASE_URL", "https://autoapply.matthewbarlow.me")


def send_invite(to_email: str) -> bool:
    """Send an invitation email. Returns True if sent, False if SMTP is unconfigured.

    Access is gated by the allowlist + OAuth login, so the message carries no
    token -- it just points the recipient at the app to sign in.
    """
    user = os.getenv("ZOHO_SMTP_USER")
    password = os.getenv("ZOHO_SMTP_PASSWORD")
    if not user or not password:
        logger.info("send_invite: SMTP not configured; skipping email to %s", to_email)
        return False

    url = _app_base_url()
    msg = EmailMessage()
    msg["Subject"] = "You're invited to Auto Apply"
    msg["From"] = user
    msg["To"] = to_email
    msg.set_content(
        "You've been invited to Auto Apply.\n\n"
        f"Sign in at {url} using this email address ({to_email}) "
        "with Google or GitHub to get started.\n"
    )

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)
    logger.info("send_invite: sent invite to %s", to_email)
    return True
