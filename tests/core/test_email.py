from unittest.mock import MagicMock, patch

from core import email as email_mod


def test_send_invite_noop_when_unconfigured(monkeypatch):
    monkeypatch.delenv("ZOHO_SMTP_USER", raising=False)
    monkeypatch.delenv("ZOHO_SMTP_PASSWORD", raising=False)
    assert email_mod.send_invite("new@example.com") is False


def test_send_invite_sends_when_configured(monkeypatch):
    monkeypatch.setenv("ZOHO_SMTP_USER", "noreply@example.com")
    monkeypatch.setenv("ZOHO_SMTP_PASSWORD", "secret")
    monkeypatch.delenv("ZOHO_SMTP_FROM", raising=False)
    smtp = MagicMock()
    ctx = MagicMock()
    ctx.__enter__.return_value = smtp
    with patch("core.email.smtplib.SMTP_SSL", return_value=ctx) as ctor:
        assert email_mod.send_invite("new@example.com") is True
    ctor.assert_called_once_with("smtp.zoho.com", 465)
    smtp.login.assert_called_once_with("noreply@example.com", "secret")
    smtp.send_message.assert_called_once()
    sent = smtp.send_message.call_args[0][0]
    assert sent["To"] == "new@example.com"
    # From falls back to the auth user when ZOHO_SMTP_FROM is unset.
    assert "noreply@example.com" in sent["From"]
    # HTML alternative part is attached alongside the plain-text body.
    assert sent.get_content_type() == "multipart/alternative"
    html = sent.get_payload()[1].get_content()
    assert "Auto Apply" in html and "new@example.com" in html


def test_send_invite_uses_from_override(monkeypatch):
    monkeypatch.setenv("ZOHO_SMTP_USER", "hireme@example.com")
    monkeypatch.setenv("ZOHO_SMTP_PASSWORD", "secret")
    monkeypatch.setenv("ZOHO_SMTP_FROM", "noreply@example.com")
    smtp = MagicMock()
    ctx = MagicMock()
    ctx.__enter__.return_value = smtp
    with patch("core.email.smtplib.SMTP_SSL", return_value=ctx):
        assert email_mod.send_invite("new@example.com") is True
    # Auth uses the login user; visible From uses the alias.
    smtp.login.assert_called_once_with("hireme@example.com", "secret")
    sent = smtp.send_message.call_args[0][0]
    assert "noreply@example.com" in sent["From"]
