"""Tests for DeepSeek client request timeout behavior."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from deepseek_terminal_agent.config import DeepSeekConfig
from deepseek_terminal_agent.deepseek_client import DeepSeekClient, DeepSeekTimeoutError


def test_chat_completions_passes_configured_timeout_to_sdk():
    sdk_client = MagicMock()
    sdk_client.chat.completions.create.return_value = MagicMock()

    with patch("deepseek_terminal_agent.deepseek_client._build_openai_client", return_value=sdk_client):
        client = DeepSeekClient(DeepSeekConfig(
            api_key="sk-test-key", request_timeout_sec=42))
        client.chat_completions(
            messages=[{"role": "user", "content": "hello"}])

    assert sdk_client.chat.completions.create.call_args.kwargs["timeout"] == 42


def test_chat_completions_raises_typed_timeout_error():
    class FakeTimeoutError(Exception):
        pass

    sdk_client = MagicMock()
    sdk_client.chat.completions.create.side_effect = FakeTimeoutError(
        "request timed out")

    with patch("deepseek_terminal_agent.deepseek_client._build_openai_client", return_value=sdk_client):
        client = DeepSeekClient(DeepSeekConfig(
            api_key="sk-test-key", request_timeout_sec=17))
        with pytest.raises(DeepSeekTimeoutError, match="timed out after 17s"):
            client.chat_completions(
                messages=[{"role": "user", "content": "hello"}])
