"""OpenAI-SDK-shaped client that shells out to the local `claude` CLI.

Dev-only local LLM backend, selected via LLM_PROVIDER_TYPE=claude_cli in
.env (see core/llm.py get_client_for_profile). Runs `claude -p` headless,
single-turn, no tool access, and bills against the user's Claude
subscription rather than the app's OpenRouter key. Never runs in
production — core/llm.py guards that before this class is constructed.
"""
from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace
from typing import Any

_TIMEOUT_SECONDS = 300


class ClaudeCliClient:
    """Duck-types the subset of the OpenAI SDK client surface this app uses."""

    @property
    def chat(self) -> "ClaudeCliClient":
        return self

    @property
    def completions(self) -> "ClaudeCliClient":
        return self

    def create(self, *, model: str = "", max_tokens: int = 0, messages: list[dict], **_ignored: Any) -> SimpleNamespace:
        prompt = "\n\n".join(m["content"] for m in messages)
        try:
            result = subprocess.run(
                ["claude", "-p", "--output-format", "json"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
            )
        except FileNotFoundError as e:
            raise RuntimeError(
                "claude CLI not found on PATH — install it or set LLM_PROVIDER_TYPE back to openrouter"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"claude -p timed out after {_TIMEOUT_SECONDS}s") from e

        if result.returncode != 0:
            raise RuntimeError(f"claude -p failed (exit {result.returncode}): {result.stderr.strip()}")

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"claude -p returned non-JSON stdout: {result.stdout[:500]!r}") from e

        content = payload.get("result", "")
        usage = payload.get("usage") or {}
        message = SimpleNamespace(content=content)
        choice = SimpleNamespace(message=message, finish_reason="stop")
        usage_ns = SimpleNamespace(
            cost=0.0,
            prompt_tokens=int(usage.get("input_tokens", 0) or 0),
            completion_tokens=int(usage.get("output_tokens", 0) or 0),
        )
        return SimpleNamespace(choices=[choice], usage=usage_ns)
