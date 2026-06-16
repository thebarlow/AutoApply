from unittest.mock import MagicMock, patch

from core import email as email_mod


def test_send_invite_noop_when_unconfigured(monkeypatch):
    monkeypatch.delenv("ZOHO_SMTP_USER", raising=False)
    monkeypatch.delenv("ZOHO_SMTP_PASSWORD", raising=False)
    assert email_mod.send_invite("new@example.com") is False


def test_send_invite_sends_when_configured(monkeypatch):
    monkeypatch.setenv("ZOHO_SMTP_USER", "noreply@example.com")
    monkeypatch.setenv("ZOHO_SMTP_PASSWORD", "secret")
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
    assert sent["From"] == "noreply@example.com"
