"""Outbound email via the Resend HTTP API. No-op (returns False) when
``RESEND_API_KEY`` is unset, so invite flows still work in local/dev without
mail configured.

Resend is used over raw SMTP because Railway throttles/blocks outbound SMTP
egress (Zoho :465 timed out); an HTTPS POST is never blocked.
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"
# From address must be on a Resend-verified domain (matthewbarlow.me).
DEFAULT_FROM = "Auto Apply <noreply@matthewbarlow.me>"

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
    """Send an invitation email. Returns True if sent, False if Resend is unconfigured.

    Access is gated by the allowlist + OAuth login, so the message carries no
    token -- it just points the recipient at the app to sign in.

    The visible ``From:`` is ``RESEND_FROM`` when set, otherwise ``DEFAULT_FROM``
    (must be an address on a Resend-verified domain). Raises ``httpx.HTTPError``
    on transport failure or a non-2xx response so the admin route can surface why.
    """
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        logger.info("send_invite: Resend not configured; skipping email to %s", to_email)
        return False

    from_addr = os.getenv("RESEND_FROM") or DEFAULT_FROM
    url = _app_base_url()
    payload = {
        "from": from_addr,
        "to": [to_email],
        "subject": "You're invited to Auto Apply",
        "html": _invite_html(to_email, url),
        "text": (
            "You've been invited to Auto Apply.\n\n"
            f"Sign in at {url} using this email address ({to_email}) "
            "with Google or GitHub to get started.\n"
        ),
    }
    # A bounded timeout keeps a hung connection from stalling the request.
    resp = httpx.post(
        RESEND_API_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=20,
    )
    if resp.is_error:
        # Resend returns a JSON body explaining *why* (e.g. unverified domain);
        # raise_for_status drops it, so include it in the surfaced message.
        raise httpx.HTTPStatusError(
            f"Resend {resp.status_code}: {resp.text}", request=resp.request, response=resp
        )
    logger.info("send_invite: sent invite from %s to %s", from_addr, to_email)
    return True
