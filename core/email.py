"""Outbound email via Zoho SMTP. No-op (returns False) when SMTP env vars are
unset, so invite flows still work in local/dev without mail configured."""
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.zoho.com"
SMTP_PORT = 465

# Brand palette mirrors the dashboard's dark "space" theme (react-dashboard/src/index.css).
_BG = "#0a0a1a"
_CARD = "#12121f"
_BORDER = "#2a2a3a"
_PURPLE = "#a855f7"
_TEXT = "#e2e8f0"
_MUTED = "#94a3b8"


def _app_base_url() -> str:
    return os.getenv("APP_BASE_URL", "https://autoapply.matthewbarlow.me")


def _invite_html(to_email: str, url: str) -> str:
    """Email-client-safe HTML (table layout, inline styles only, no external images)."""
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:{_BG};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_BG};padding:32px 12px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;background:{_CARD};border:1px solid {_BORDER};border-radius:16px;overflow:hidden;">
        <tr><td style="padding:32px 36px 0;text-align:center;">
          <div style="font:700 22px/1.2 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:{_PURPLE};letter-spacing:.5px;">Auto Apply</div>
        </td></tr>
        <tr><td style="padding:14px 36px 0;">
          <div style="height:3px;border-radius:2px;background:linear-gradient(90deg,#a855f7,#ec4899,#06b6d4);"></div>
        </td></tr>
        <tr><td style="padding:28px 36px 0;text-align:center;">
          <div style="font:700 24px/1.3 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:{_TEXT};">You're invited &#127881;</div>
        </td></tr>
        <tr><td style="padding:16px 36px 0;text-align:center;">
          <p style="margin:0;font:400 15px/1.6 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:{_MUTED};">
            You've been invited to Auto Apply. Sign in with Google or GitHub using this email address
            (<span style="color:{_TEXT};">{to_email}</span>) to get started.
          </p>
        </td></tr>
        <tr><td style="padding:28px 36px 0;text-align:center;">
          <a href="{url}" style="display:inline-block;background:{_PURPLE};color:#ffffff;text-decoration:none;font:600 15px/1 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;padding:14px 34px;border-radius:10px;">Sign in</a>
        </td></tr>
        <tr><td style="padding:28px 36px 32px;text-align:center;">
          <p style="margin:0;font:400 12px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:{_MUTED};">
            Or open <a href="{url}" style="color:{_PURPLE};text-decoration:none;">{url}</a>
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def send_invite(to_email: str) -> bool:
    """Send an invitation email. Returns True if sent, False if SMTP is unconfigured.

    Access is gated by the allowlist + OAuth login, so the message carries no
    token -- it just points the recipient at the app to sign in.

    Auth uses ``ZOHO_SMTP_USER``; the visible ``From:`` is ``ZOHO_SMTP_FROM`` when
    set (e.g. a verified alias), otherwise it falls back to the auth user.
    """
    user = os.getenv("ZOHO_SMTP_USER")
    password = os.getenv("ZOHO_SMTP_PASSWORD")
    if not user or not password:
        logger.info("send_invite: SMTP not configured; skipping email to %s", to_email)
        return False

    from_addr = os.getenv("ZOHO_SMTP_FROM") or user
    url = _app_base_url()
    msg = EmailMessage()
    msg["Subject"] = "You're invited to Auto Apply"
    msg["From"] = formataddr(("Auto Apply", from_addr))
    msg["To"] = to_email
    msg.set_content(
        "You've been invited to Auto Apply.\n\n"
        f"Sign in at {url} using this email address ({to_email}) "
        "with Google or GitHub to get started.\n"
    )
    msg.add_alternative(_invite_html(to_email, url), subtype="html")

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)
    logger.info("send_invite: sent invite from %s to %s", from_addr, to_email)
    return True
