from unittest.mock import MagicMock, patch

from core import email as email_mod


def test_send_invite_noop_when_unconfigured(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    assert email_mod.send_invite("new@example.com") is False


def test_send_invite_sends_when_configured(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.delenv("RESEND_FROM", raising=False)
    resp = MagicMock()
    with patch("core.email.httpx.post", return_value=resp) as post:
        assert email_mod.send_invite("new@example.com") is True
    resp.raise_for_status.assert_called_once()
    args, kwargs = post.call_args
    assert args[0] == email_mod.RESEND_API_URL
    assert kwargs["headers"]["Authorization"] == "Bearer re_test"
    payload = kwargs["json"]
    assert payload["to"] == ["new@example.com"]
    # From falls back to DEFAULT_FROM when RESEND_FROM is unset.
    assert payload["from"] == email_mod.DEFAULT_FROM
    assert "Auto Apply" in payload["html"] and "new@example.com" in payload["html"]
    assert "new@example.com" in payload["text"]


def test_send_invite_uses_from_override(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("RESEND_FROM", "Custom <noreply@example.com>")
    with patch("core.email.httpx.post", return_value=MagicMock()) as post:
        assert email_mod.send_invite("new@example.com") is True
    assert post.call_args.kwargs["json"]["from"] == "Custom <noreply@example.com>"
