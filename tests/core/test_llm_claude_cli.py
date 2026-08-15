import json
import subprocess
from unittest import mock

import pytest

from core.llm_claude_cli import ClaudeCliClient


def _fake_run(stdout_obj, returncode=0, stderr=""):
    """Build a mock subprocess.run(...) return value."""
    result = mock.MagicMock()
    result.returncode = returncode
    result.stdout = json.dumps(stdout_obj) if stdout_obj is not None else ""
    result.stderr = stderr
    return result


def test_create_returns_openai_shaped_response():
    client = ClaudeCliClient()
    fake = _fake_run({"result": "hello world", "usage": {"input_tokens": 10, "output_tokens": 3}})
    with mock.patch("subprocess.run", return_value=fake) as run:
        resp = client.chat.completions.create(
            model="ignored", max_tokens=999,
            messages=[{"role": "user", "content": "hi"}],
        )
    assert resp.choices[0].message.content == "hello world"
    assert resp.choices[0].finish_reason == "stop"
    assert resp.usage.cost == 0.0
    assert resp.usage.prompt_tokens == 10
    assert resp.usage.completion_tokens == 3
    # prompt piped via stdin, not argv
    call_kwargs = run.call_args.kwargs
    assert call_kwargs["input"] == "hi"
    assert "claude" in run.call_args.args[0][0]


def test_create_defaults_missing_usage_fields_to_zero():
    client = ClaudeCliClient()
    fake = _fake_run({"result": "ok"})  # no "usage" key at all
    with mock.patch("subprocess.run", return_value=fake):
        resp = client.chat.completions.create(model="m", max_tokens=1, messages=[{"role": "user", "content": "x"}])
    assert resp.usage.prompt_tokens == 0
    assert resp.usage.completion_tokens == 0
    assert resp.usage.cost == 0.0


def test_create_concatenates_multiple_messages():
    client = ClaudeCliClient()
    fake = _fake_run({"result": "ok"})
    with mock.patch("subprocess.run", return_value=fake) as run:
        client.chat.completions.create(
            model="m", max_tokens=1,
            messages=[{"role": "user", "content": "part one"}, {"role": "user", "content": "part two"}],
        )
    assert "part one" in run.call_args.kwargs["input"]
    assert "part two" in run.call_args.kwargs["input"]


def test_nonzero_exit_raises_runtime_error_with_stderr():
    client = ClaudeCliClient()
    fake = _fake_run(None, returncode=1, stderr="claude: command failed")
    with mock.patch("subprocess.run", return_value=fake):
        with pytest.raises(RuntimeError, match="claude: command failed"):
            client.chat.completions.create(model="m", max_tokens=1, messages=[{"role": "user", "content": "x"}])


def test_malformed_json_raises_runtime_error():
    client = ClaudeCliClient()
    fake = mock.MagicMock(returncode=0, stdout="not json", stderr="")
    with mock.patch("subprocess.run", return_value=fake):
        with pytest.raises(RuntimeError, match="not json"):
            client.chat.completions.create(model="m", max_tokens=1, messages=[{"role": "user", "content": "x"}])


def test_timeout_raises_runtime_error():
    client = ClaudeCliClient()
    with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=300)):
        with pytest.raises(RuntimeError, match="timed out"):
            client.chat.completions.create(model="m", max_tokens=1, messages=[{"role": "user", "content": "x"}])
